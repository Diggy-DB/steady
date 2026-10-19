"""HTTP API for the planning assistant, for the backend and frontend to call.

    POST /chat                          ask a question; returns the reply and any new suggestions
    GET  /suggestions                   the user's pending suggestions
    POST /suggestions/{id}/check        re-run the checks (what Accept does first)
    POST /suggestions/{id}/accept       check again, apply the change, mark it ACCEPTED, log it
    POST /suggestions/{id}/decline      mark it DECLINED, log it
    GET  /health

Two modes, chosen with the STORE environment variable:
- STORE=fixture (default, "demo mode"): the fake week in fixtures/week.json, kept in memory.
  The user is taken from an X-User-Id header (default user-1), and the clock is fixed at
  DEMO_NOW (default Monday Oct 5, 2026, 6:30 PM) so the fake week makes sense.
- STORE=supabase: real data. The caller sends the user's Supabase access token as
  "Authorization: Bearer <token>"; it is checked with Supabase, and every database request
  is made with it, so Row Level Security applies.

Run locally (from ai/):
    uv run uvicorn ai.server:app --port 8000
"""

import os
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
import openai
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ai.agent import run_agent
from ai.llm import load_settings, make_client
from ai.planning import recheck
from ai.schedule import FixtureStore, ToolContext
from ai.supabase_store import SupabaseStore

settings = load_settings()  # also loads ai/.env, so it must come before the os.getenv calls below
llm = make_client(settings)

STORE = os.getenv("STORE", "fixture")
DEMO_NOW = os.getenv("DEMO_NOW", "2026-10-05 18:30")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
if STORE == "supabase" and not (SUPABASE_URL and SUPABASE_ANON_KEY):
    raise RuntimeError("STORE=supabase needs SUPABASE_URL and SUPABASE_ANON_KEY (see .env.example)")
# Web pages allowed to call this API from the browser (the frontend's dev server by default).
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app = FastAPI(title="Steady Planner AI")
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["Authorization", "Content-Type", "X-User-Id"]
)
demo_store = FixtureStore()  # one shared copy, so suggestions survive between requests in demo mode


# Turn failures of the services we depend on into clear JSON errors. An unhandled crash would also
# lose the CORS headers, and the browser would only say "Failed to fetch".
@app.exception_handler(openai.APIError)
def model_unavailable(request: Request, error: openai.APIError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": f"The AI model isn't available right now: {error.message}"})


@app.exception_handler(httpx.HTTPError)
def database_unavailable(request: Request, error: httpx.HTTPError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": f"The database request failed: {error}"})


@app.exception_handler(LookupError)
def not_applied(request: Request, error: LookupError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]  # never "system": callers can't add instructions
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default=[], max_length=20)  # earlier turns, final answers only


class ChatResponse(BaseModel):
    reply: str
    suggestions: list[dict]  # suggestions created while answering, for Accept / Decline cards
    run_id: str


def context(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> ToolContext:
    """Work out who is asking, and build the ToolContext. This, not the model, decides the user."""
    if STORE == "fixture":
        store = demo_store
        user_id = x_user_id or "user-1"
        now_text = DEMO_NOW
    else:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing Authorization: Bearer <access token>")
        token = authorization.removeprefix("Bearer ")
        response = httpx.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if response.status_code != 200:
            raise HTTPException(401, "invalid or expired access token")
        user_id = response.json()["id"]
        store = SupabaseStore(SUPABASE_URL, SUPABASE_ANON_KEY, token)
        now_text = None
    try:
        timezone = ZoneInfo(store.user(user_id)["timezone"])
    except KeyError:
        raise HTTPException(404, f"no profile for user {user_id}") from None
    now = datetime.fromisoformat(now_text).replace(tzinfo=timezone) if now_text else datetime.now(timezone)
    return ToolContext(store=store, user_id=user_id, now=now)


def find_suggestion(ctx: ToolContext, suggestion_id: str) -> dict:
    for s in ctx.store.suggestions(ctx.user_id):
        if s["suggestion_id"] == suggestion_id:
            return s
    raise HTTPException(404, f"no suggestion {suggestion_id}")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "store": STORE, "model": settings.model}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, ctx: ToolContext = Depends(context)) -> ChatResponse:
    before = {s["suggestion_id"] for s in ctx.store.suggestions(ctx.user_id)}
    history = [turn.model_dump() for turn in request.history]
    result = run_agent(llm, settings.model, ctx, request.message, verbose=False, history=history)
    new = [s for s in ctx.store.suggestions(ctx.user_id) if s["suggestion_id"] not in before]
    return ChatResponse(reply=result["answer"], suggestions=new, run_id=result["run_id"])


@app.get("/suggestions")
def pending_suggestions(ctx: ToolContext = Depends(context)) -> list[dict]:
    return ctx.store.suggestions(ctx.user_id, status="PENDING")


@app.post("/suggestions/{suggestion_id}/check")
def check_suggestion(suggestion_id: str, ctx: ToolContext = Depends(context)) -> dict:
    suggestion = find_suggestion(ctx, suggestion_id)
    problems = recheck(ctx, suggestion)
    waiting_for = [
        s["suggestion_id"]
        for s in ctx.store.suggestions(ctx.user_id, status="PENDING")
        if s["suggestion_id"] in suggestion.get("depends_on", [])
    ]
    return {"valid": not problems, "problems": problems, "accept_first": waiting_for}


@app.post("/suggestions/{suggestion_id}/accept")
def accept(suggestion_id: str, ctx: ToolContext = Depends(context)) -> dict:
    suggestion = find_suggestion(ctx, suggestion_id)
    checked = check_suggestion(suggestion_id, ctx)
    if checked["accept_first"]:
        raise HTTPException(409, f"accept {', '.join(checked['accept_first'])} first")
    if not checked["valid"]:
        raise HTTPException(409, "; ".join(checked["problems"]))
    ctx.store.apply(suggestion)
    ctx.store.set_status(suggestion_id, "ACCEPTED")
    ctx.store.log(ctx.user_id, "SUGGESTION_ACCEPTED", "ai_suggestion", suggestion_id, "USER",
                  {"type": suggestion["type"], "target_id": suggestion["target_id"], "change": suggestion["proposed_change"]})
    return {"suggestion_id": suggestion_id, "status": "ACCEPTED"}


@app.post("/suggestions/{suggestion_id}/decline")
def decline(suggestion_id: str, ctx: ToolContext = Depends(context)) -> dict:
    suggestion = find_suggestion(ctx, suggestion_id)
    if suggestion["status"] != "PENDING":
        raise HTTPException(409, f"it is already {suggestion['status']}")
    ctx.store.set_status(suggestion_id, "DECLINED")
    ctx.store.log(ctx.user_id, "SUGGESTION_DECLINED", "ai_suggestion", suggestion_id, "USER", {"type": suggestion["type"]})
    return {"suggestion_id": suggestion_id, "status": "DECLINED"}
