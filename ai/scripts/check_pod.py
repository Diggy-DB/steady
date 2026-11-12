"""Check the deployed AI API from outside, the way the website reaches it. No login needed.

    uv run scripts/check_pod.py https://<POD_ID>-8000.proxy.runpod.net

Besides health and CORS, it sends chat requests whose history holds a very long reply that reads like the
model's thinking (with <tool_call> tags), as a chat looks after the thinking leaked into a reply. Our API
answers "401 missing Authorization" to all of them. Anything else, or no CORS header, means something in
between (RunPod's proxy, Cloudflare's firewall, a size limit) stops them: the browser then only says
"Can't reach the AI server", which is what the team saw for some prompts while the server was up.
"""

import sys

import httpx

SITE = "https://diggy-db.github.io"
THINKING = ("Thinking Process:\n1. The user wants to study before the makeup session. Let me check the schedule.\n"
            '<tool_call>{"name": "get_schedule", "arguments": {"start_date": "2026-11-09"}}</tool_call>\n') * 60


def main() -> None:
    url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else sys.exit(__doc__)
    api = httpx.Client(base_url=url, timeout=60, headers={"Origin": SITE})
    health = api.get("/health")
    print(f"health: {health.status_code} {health.text[:120]}")
    pre = api.options("/chat/start", headers={"Access-Control-Request-Method": "POST",
                                             "Access-Control-Request-Headers": "authorization,content-type"})
    print(f"preflight: {pre.status_code}, allow-origin: {pre.headers.get('access-control-allow-origin')}")
    cases = {
        "a short message": {"message": "hi", "history": []},
        "a 2,000-character history turn": {"message": "yes", "history": [{"role": "assistant", "content": "Okay. " * 330}]},
        "a long thinking-like history turn": {"message": "yes", "history": [{"role": "assistant", "content": THINKING}]},
        "ten long history turns": {"message": "yes", "history": [{"role": "assistant", "content": THINKING[:4000]}] * 10},
    }
    for name, body in cases.items():
        r = api.post("/chat/start", json=body, headers={"Authorization": "Bearer not-a-real-token"})
        ok = r.status_code == 401 and r.headers.get("access-control-allow-origin") == SITE
        print(f"{'OK  ' if ok else 'FAIL'} {name} ({len(str(body))} chars): {r.status_code}, "
              f"CORS {r.headers.get('access-control-allow-origin')}, server {r.headers.get('server')}, {r.text[:100]!r}")


if __name__ == "__main__":
    main()
