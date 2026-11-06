"""How well does a model read syllabi? Scores models on fixtures/syllabi/ (see make_syllabi.py).

The model gets each syllabus and must return JSON: the course's weekly meetings and every dated
item (assignments, quizzes, exams, ...). That's compared with truth.json:

- found:     share of the real dated items it returned with the right date (recall)
- made up:   items it returned that aren't in the syllabus (1 - precision)
- times:     of the found items that have a time, how many have the right time
- meetings:  weekly meetings with the right days, start and end

Routes, i.e. how the syllabus reaches the model:
    vision  every page as an image (works for photos, scans and PDFs)
    text    the PDF's text layer (only digital PDFs have one; photos and scans are skipped)
    ocr     an OCR model (default glm-ocr) turns each page into text, then the model reads the text

Runs on Ollama (its own API, for images and JSON schemas). From ai/:
    uv run --with pymupdf scripts/eval_syllabus.py --model qwen3.5:4b --route vision
    uv run --with pymupdf scripts/eval_syllabus.py --model qwen3.5:9b --route text --think
"""

import argparse
import base64
import json
import re
import time
from datetime import datetime
from pathlib import Path

import httpx

AI_DIR = Path(__file__).resolve().parents[1]
FIXTURES = AI_DIR / "fixtures" / "syllabi"
OLLAMA = "http://localhost:11434"

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SCHEMA = {
    "type": "object",
    "properties": {
        "course": {"type": "string"},
        "term_start": {"type": ["string", "null"], "description": "first day of classes, YYYY-MM-DD"},
        "term_end": {"type": ["string", "null"], "description": "last day of classes, YYYY-MM-DD"},
        "meetings": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "description": "lecture, recitation, lab, discussion, ..."},
            "days": {"type": "array", "items": {"type": "string", "enum": DAYS}},
            "start": {"type": "string", "description": "HH:MM, 24-hour"},
            "end": {"type": "string", "description": "HH:MM, 24-hour"},
            "location": {"type": ["string", "null"]},
        }, "required": ["kind", "days", "start", "end"]}},
        "no_class": {"type": "array", "items": {"type": "object", "properties": {
            "start": {"type": "string"}, "end": {"type": "string"}, "reason": {"type": "string"},
        }, "required": ["start", "end"]}},
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"},
            "kind": {"type": "string", "enum": ["assignment", "quiz", "exam", "project", "presentation", "other"]},
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "time": {"type": ["string", "null"], "description": "due time or start time, HH:MM 24-hour"},
            "end_time": {"type": ["string", "null"], "description": "HH:MM 24-hour, for exams and other events"},
        }, "required": ["title", "kind", "date", "time"]}},
    },
    "required": ["course", "meetings", "no_class", "items"],
}
PROMPT = """Read this course syllabus and extract the schedule as JSON.

- meetings: the class's weekly meetings (lectures, recitations, labs), with days and times. Not office hours.
- no_class: breaks and days without class.
- items: EVERY dated assignment, homework, quiz, exam, paper, project and presentation, one entry per
  date (for example 10 homeworks are 10 items). Not university deadlines like drop dates.
- Dates as YYYY-MM-DD. If a date has no year, use the year of the semester.
- Times as HH:MM in 24-hour time (11:59 PM is 23:59). For something due "in class" or "in lecture",
  use that class meeting's start and end time. Use null if there is no time.

Reply with only the JSON object, shaped like this example:
{"course": "ABC 101", "term_start": "2027-01-11", "term_end": "2027-04-30",
 "meetings": [{"kind": "lecture", "days": ["Mon", "Wed"], "start": "13:00", "end": "14:20", "location": "Room 1"}],
 "no_class": [{"start": "2027-03-08", "end": "2027-03-12", "reason": "spring break"}],
 "items": [{"title": "Homework 1", "kind": "assignment", "date": "2027-01-15", "time": "23:59", "end_time": null},
           {"title": "Exam 1", "kind": "exam", "date": "2027-02-10", "time": "13:00", "end_time": "14:20"}]}
kind is one of: assignment, quiz, exam, project, presentation, other. days use Mon Tue Wed Thu Fri Sat Sun."""

# Words that mean the same kind of item: "WebWork 3", "HW 3", "Problem Set 3" are all homework 3.
ALIASES = {"hw": "homework", "ww": "homework", "webwork": "homework", "ps": "homework", "pset": "homework",
           "problem": "homework", "midterms": "midterm", "quizzes": "quiz", "exams": "exam", "papers": "paper",
           "homeworks": "homework", "presentations": "presentation", "labs": "lab", "problems": "homework"}
KEYWORDS = {"homework", "webwork", "problem", "quiz", "exam", "midterm", "final", "paper", "bibliography",
            "proposal", "presentation", "practical", "lab"}


def words(title: str) -> tuple[set[str], set[str]]:
    """(key words, numbers) of a title, so 'HW 3' matches 'Homework 3' but not 'Homework 4'."""
    tokens = re.findall(r"[a-z]+|\d+", title.lower().replace("-", " "))
    tokens = [ALIASES.get(t, t) for t in tokens]
    return {t for t in tokens if t in KEYWORDS}, {t for t in tokens if t.isdigit()}


def same_item(truth: dict, guess: dict, strict_numbers: bool = True) -> bool:
    """Same date, the same kind of item and (if strict) the same number: "HW 3" is "Homework 3".
    Without strict numbers, "Field notes (Week 4)" on the right date still counts as "Field notes 2"."""
    if str(guess.get("date") or "")[:10] != truth["date"]:  # "2027-01-19T23:59" counts as 2027-01-19
        return False
    true_words, true_numbers = words(truth["title"])
    guess_words, guess_numbers = words(guess.get("title", ""))
    if strict_numbers and true_numbers and not true_numbers <= guess_numbers:
        return False
    return bool(true_words & guess_words) or guess.get("kind") == truth["kind"]


def hhmm(value) -> str | None:
    """'9:10', '9:10 AM', '09:10:00' -> '09:10', and '7:00 PM' -> '19:00', as the app's code would read them."""
    if not value:
        return None
    match = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?", str(value).strip())
    if not match:
        return str(value)
    hour = int(match.group(1)) % 12 + (12 if (match.group(3) or "").lower() == "pm" else 0) if match.group(3) else int(match.group(1))
    return f"{hour:02d}:{match.group(2)}"


def score(truth: dict, answer: dict) -> dict:
    guesses = [g for g in answer.get("items", []) if isinstance(g, dict)]
    unused = list(range(len(guesses)))
    matches = {}
    # two passes: first the same number too (so "Quiz 3" never takes Quiz 2's date), then any number
    for strict in (True, False):
        for n, t in enumerate(truth["items"]):
            if n in matches:
                continue
            match = next((i for i in unused if same_item(t, guesses[i], strict_numbers=strict)), None)
            if match is not None:
                matches[n] = match
                unused.remove(match)
    found, right_time, timed = len(matches), 0, 0
    missed = [f"{t['title']} {t['date']}" for n, t in enumerate(truth["items"]) if n not in matches]
    for n, match in matches.items():
        t = truth["items"][n]
        if t["time"]:
            timed += 1
            right_time += hhmm(guesses[match].get("time")) == t["time"]
    def same_meeting(m, g) -> bool:
        return set(g.get("days", [])) == set(m["days"]) and hhmm(g.get("start")) == m["start"] and hhmm(g.get("end")) == m["end"]

    meetings_right = sum(any(same_meeting(m, g) for g in answer.get("meetings", [])) for m in truth["meetings"])
    meetings_made_up = sum(not any(same_meeting(m, g) for m in truth["meetings"]) for g in answer.get("meetings", []))
    return {"items": len(truth["items"]), "found": found, "returned": len(guesses), "made_up": len(unused),
            "timed": timed, "right_time": right_time, "meetings": len(truth["meetings"]),
            "meetings_right": meetings_right, "meetings_made_up": meetings_made_up, "missed": missed,
            "extra": [f"{guesses[i].get('title')} {guesses[i].get('date')}" for i in unused]}


def pages(path: Path, dpi: int) -> tuple[list[bytes], str]:
    """(page images as PNG/JPEG bytes, text layer) of a PDF or an image file."""
    if path.suffix.lower() != ".pdf":
        return [path.read_bytes()], ""
    import pymupdf

    doc = pymupdf.open(path)
    return [page.get_pixmap(dpi=dpi).tobytes("png") for page in doc], "".join(page.get_text() for page in doc)


# For extraction: little randomness and NO repetition penalty. Qwen3.5's chat defaults in Ollama
# (temperature 1.0, presence_penalty 1.5) push it away from repeating words, which breaks lists like
# "WebWork 1 ... WebWork 14, 23:59, 23:59" (items went missing and JSON broke in tests).
EXTRACTION_OPTIONS = {"temperature": 0.3, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.0, "repeat_penalty": 1.0}


def chat(model: str, content: str, images: list[bytes] = (), think: bool = False, schema: dict | None = None,
         timeout: float = 1800, temperature: float | None = None) -> tuple[str, dict]:
    """One request to Ollama. Returns (answer text, stats)."""
    message = {"role": "user", "content": content}
    if images:
        message["images"] = [base64.b64encode(image).decode() for image in images]
    body = {"model": model, "messages": [message], "stream": False, "think": think,
            # a cap on the answer's length, so a model stuck repeating itself can't run forever
            "options": {"num_ctx": 32768, "num_predict": 16384 if think else 6144, **EXTRACTION_OPTIONS,
                        **({"temperature": temperature} if temperature is not None else {})}}
    if schema:
        body["format"] = schema
    started = time.perf_counter()
    response = httpx.post(f"{OLLAMA}/api/chat", json=body, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(f"Ollama said {response.status_code}: {response.text[:300]}")
    data = response.json()
    stats = {"seconds": round(time.perf_counter() - started, 1), "prompt_tokens": data.get("prompt_eval_count", 0),
             "output_tokens": data.get("eval_count", 0)}
    return data["message"]["content"], stats


def parse_json(answer: str) -> dict:
    """The JSON object in a reply, even if it's wrapped in ```json fences or follows some text."""
    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL)
    start, end = answer.find("{"), answer.rfind("}")
    if start == -1 or end < start:
        raise json.JSONDecodeError("no JSON object", answer, 0)
    data = json.loads(answer[start : end + 1])
    if "items" not in data and isinstance(data.get("properties"), dict):  # copied a JSON schema's shape
        data = data["properties"]
    return data


def read_syllabus(args, path: Path) -> tuple[dict | None, dict]:
    images, text = pages(path, args.dpi)
    schema = SCHEMA if args.constrained else None
    if args.route == "text":
        if not text.strip():
            return None, {"skipped": "no text layer"}
        answer, stats = chat(args.model, f"{PROMPT}\n\nSYLLABUS:\n{text}", think=args.think, schema=schema, temperature=args.temperature)
    elif args.route == "ocr":
        transcripts, ocr_seconds = [], 0.0
        for image in images:
            transcript, s = chat(args.ocr_model, "Text Recognition:", [image], schema=None)
            transcripts.append(transcript)
            ocr_seconds += s["seconds"]
        answer, stats = chat(args.model, f"{PROMPT}\n\nSYLLABUS:\n" + "\n\n".join(transcripts), think=args.think,
                             schema=schema, temperature=args.temperature)
        stats["seconds"] = round(stats["seconds"] + ocr_seconds, 1)
        stats["ocr_seconds"] = round(ocr_seconds, 1)
    else:
        answer, stats = chat(args.model, PROMPT, images, think=args.think, schema=schema, temperature=args.temperature)
    try:
        return parse_json(answer), stats
    except json.JSONDecodeError:
        return {}, {**stats, "error": "not valid JSON"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a model on reading the test syllabi.")
    parser.add_argument("--model", required=True, help="an Ollama model, e.g. qwen3.5:4b")
    parser.add_argument("--route", choices=["vision", "text", "ocr"], default="vision")
    parser.add_argument("--ocr-model", default="glm-ocr:q8_0", help="for --route ocr")
    parser.add_argument("--think", action="store_true", help="let the model think first")
    parser.add_argument("--constrained", action="store_true",
                        help="force the JSON schema with Ollama's constrained decoding (broke Qwen3.5's output in tests)")
    parser.add_argument("--temperature", type=float, help="override the extraction temperature (0.3)")
    parser.add_argument("--dpi", type=int, default=150, help="resolution for PDF pages sent as images")
    parser.add_argument("--only", nargs="*", help="syllabus files to use (default: all)")
    args = parser.parse_args()

    truth = json.loads((FIXTURES / "truth.json").read_text())
    label = f"{args.model} {args.route}{' +think' if args.think else ''}"
    results = []
    for name, expected in truth.items():
        if args.only and name not in args.only:
            continue
        answer, stats = read_syllabus(args, FIXTURES / name)
        if answer is None:
            print(f"{name}: skipped ({stats['skipped']})")
            continue
        s = {"file": name, **score(expected, answer), **stats, "answer": answer}
        results.append(s)
        print(f"{name}: found {s['found']}/{s['items']}, made up {s['made_up']}, times {s['right_time']}/{s['timed']}, "
              f"meetings {s['meetings_right']}/{s['meetings']}, {s['seconds']}s, {s['output_tokens']} tokens"
              + (f"  [{stats['error']}]" if "error" in stats else ""), flush=True)
        if s["missed"]:
            print(f"   missed: {', '.join(s['missed'])}")
        if s["extra"]:
            print(f"   made up: {', '.join(s['extra'])}")

    total = {k: sum(r[k] for r in results) for k in ("items", "found", "made_up", "timed", "right_time",
                                                       "meetings", "meetings_right", "seconds")}
    print(f"\nTOTAL {label}: found {total['found']}/{total['items']}, made up {total['made_up']}, "
          f"times {total['right_time']}/{total['timed']}, meetings {total['meetings_right']}/{total['meetings']}, "
          f"{total['seconds']:.0f}s")
    out = AI_DIR / "evals" / f"{datetime.now():%Y-%m-%d-%H%M}-syllabus-{args.model.replace(':', '_').replace('/', '_')}-{args.route}{'-think' if args.think else ''}.json"
    out.write_text(json.dumps({"label": label, "args": vars(args), "total": total, "results": results}, indent=2))


if __name__ == "__main__":
    main()
