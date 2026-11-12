"""Syllabus import: an uploaded syllabus (PDF or photo) becomes PENDING suggestions for the student to review.

The model only READS the syllabus; code does everything else. In tests (notes/syllabus_import.md) a small
model read syllabi well, but as an agent adding items one tool call at a time it got the year wrong,
looped on failing calls and promised fixes it never made. So the import is a fixed pipeline:

    1. pages    PDFs with a text layer give their text; scans and photos give page images
    2. read     one model call returns the syllabus as JSON (optionally an OCR model transcribes images first)
    3. check    code fixes and flags what models get wrong: the year, 12-hour times, missing end times,
                impossible dates, duplicates, items already over, and dates that aren't in the syllabus text
    4. suggest  code creates the suggestions: deadlines, timed events (exams), and one weekly class each

The agent reaches all of this through one tool, import_syllabus (see IMPORT_SYLLABUS_TOOL).
"""

import base64
import io
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from openai import OpenAI

from ai.llm import thinking_off
from ai.schedule import ToolContext, ToolError

MIN_TEXT_PER_PAGE = 200  # characters; a PDF page with less text than this is treated as a scan
DPI = 150  # page images: readable small print at about 2,000 image tokens per page
MAX_SIDE = 1600  # photos are shrunk to this many pixels on the longest side
MAX_IMAGE_PAGES = 12  # scanned pages read in one go (about 2,000 tokens each)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
RRULE_DAYS = {"Mon": "MO", "Tue": "TU", "Wed": "WE", "Thu": "TH", "Fri": "FR", "Sat": "SA", "Sun": "SU"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]

PROMPT = """Read this course syllabus and extract the schedule as JSON.

- meetings: the class's weekly meetings (lectures, recitations, labs), with days and times. Not office hours.
- no_class: breaks and days without class.
- items: EVERY dated assignment, homework, quiz, exam, paper, project and presentation, one entry per
  date (for example 10 homeworks are 10 items). Not university deadlines like drop dates.
  A series that repeats (like weekly quizzes listed as "due January 17, January 24, ...") can be ONE item
  with "dates": [every date, in order] instead of "date"; they are numbered automatically.
- Dates as YYYY-MM-DD. If a date has no year, use the year of the semester (e.g. "Spring 2027" -> 2027).
- Times exactly as the syllabus writes them, with AM/PM if it has them (e.g. "11:59 PM", "7:00 PM", "14:00").
  For something due or held "in class" or "in lecture", use that class meeting's start and end time.
  Use null if there is no time.

Reply with only the JSON object, shaped like this example:
{"course": "ABC 101", "term": "Spring 2027", "term_start": "2027-01-11", "term_end": "2027-04-30",
 "meetings": [{"kind": "lecture", "days": ["Mon", "Wed"], "start": "1:00 PM", "end": "2:20 PM", "location": "Room 1"}],
 "no_class": [{"start": "2027-03-08", "end": "2027-03-12", "reason": "spring break"}],
 "items": [{"title": "Homework 1", "kind": "assignment", "date": "2027-01-15", "time": "11:59 PM", "end_time": null},
           {"title": "Online quiz", "kind": "quiz", "dates": ["2027-01-17", "2027-01-24"], "time": "11:59 PM"},
           {"title": "Exam 1", "kind": "exam", "date": "2027-02-10", "time": "1:00 PM", "end_time": "2:20 PM"}]}
kind is one of: assignment, quiz, exam, project, presentation, other. days use Mon Tue Wed Thu Fri Sat Sun."""

# For reading: little randomness and NO repetition penalty. Qwen3.5's chat defaults (presence_penalty
# 1.5) push it away from repeating words, which breaks lists like "WebWork 1 ... WebWork 14, 11:59 PM".
SAMPLING = {"temperature": 0.3, "top_p": 0.8, "presence_penalty": 0.0, "max_tokens": 6144}


# --- 1. pages --------------------------------------------------------------------------------------
@dataclass
class Page:
    text: str  # the PDF's text layer; "" for scans and photos
    image: bytes  # the page as PNG (or the photo as uploaded)
    mime: str = "image/png"


def load_pages(data: bytes, filename: str) -> list[Page]:
    """Split an upload into pages. PDFs give text and an image per page; a photo is one page."""
    if filename.lower().endswith(".pdf"):
        import pypdfium2 as pdfium

        pages = []
        for page in pdfium.PdfDocument(data):
            buffer = io.BytesIO()
            page.render(scale=DPI / 72).to_pil().save(buffer, format="PNG")
            pages.append(Page(text=page.get_textpage().get_text_range(), image=buffer.getvalue()))
        return pages
    lower = filename.lower()
    mime = "image/png" if lower.endswith(".png") else "image/webp" if lower.endswith(".webp") else "image/jpeg"
    return [Page(*prepare_image(data, mime))]


def prepare_image(data: bytes, mime: str) -> tuple[str, bytes, str]:
    """A photo as the model should see it: upright (phones save the turn as EXIF), and at most MAX_SIDE pixels.

    A 12-megapixel phone photo would cost about 15,000 image tokens; at 1,600 pixels it's about 2,500, and
    the print is still readable (all the test photos are this size). Small, upright images are left as they are.
    """
    from PIL import Image, ImageOps

    try:
        image = Image.open(io.BytesIO(data))
        turned = image.getexif().get(0x0112, 1) not in (1, None)  # the EXIF Orientation tag
        if not turned and max(image.size) <= MAX_SIDE:
            return "", data, mime
        upright = ImageOps.exif_transpose(image)
    except Exception:
        raise ToolError("that file isn't an image I can open; send a JPEG, PNG or PDF") from None
    upright.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    buffer = io.BytesIO()
    upright.convert("RGB").save(buffer, format="JPEG", quality=90)
    return "", buffer.getvalue(), "image/jpeg"


def has_text(pages: list[Page]) -> bool:
    """True for digital PDFs, whose text layer is more reliable to read than images of their pages.
    Scans and photos have no text at all; a digital PDF's cover page may have little, so count the total."""
    return sum(len(p.text.strip()) for p in pages) >= MIN_TEXT_PER_PAGE * len(pages)


# --- 2. read ----------------------------------------------------------------------------------------
@dataclass
class Reader:
    """Which model reads syllabi, on which server. extra_body carries server-specific settings."""

    client: OpenAI
    model: str
    ocr_model: str | None = None  # e.g. "glm-ocr:q8_0": transcribe scans and photos to text first
    extra_body: dict = field(default_factory=dict)

    @classmethod
    def for_server(cls, client: OpenAI, model: str, ocr_model: str | None = None) -> "Reader":
        """Thinking off and top_k 20, said the way the server understands (Ollama or vLLM)."""
        return cls(client, model, ocr_model, {"top_k": 20, **thinking_off(str(client.base_url))})

    def ask(self, model: str, parts: list[dict]) -> str:
        response = self.client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": parts}], **SAMPLING, extra_body=self.extra_body)
        return response.choices[0].message.content or ""


def image_part(page: Page) -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:{page.mime};base64,{base64.b64encode(page.image).decode()}"}}


def parse_json(answer: str) -> dict:
    """The JSON object in a reply, even if it's wrapped in ```json fences or follows some text."""
    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL)
    start, end = answer.find("{"), answer.rfind("}")
    if start == -1 or end < start:
        raise ValueError("the reply has no JSON object")
    data = json.loads(answer[start : end + 1])
    if "items" not in data and isinstance(data.get("properties"), dict):  # copied a JSON schema's shape
        data = data["properties"]
    return data


def read(reader: Reader, pages: list[Page]) -> tuple[dict, str | None, str]:
    """Returns (the syllabus as JSON, the text it was read from or None, how it was read)."""
    if has_text(pages):
        text, how = "\n\n".join(p.text for p in pages), "text"
    elif reader.ocr_model:
        text = "\n\n".join(reader.ask(reader.ocr_model, [{"type": "text", "text": "Text Recognition:"}, image_part(p)])
                           for p in pages)
        how = "ocr"
    else:
        text, how = None, "vision"
    if how != "text" and len(pages) > MAX_IMAGE_PAGES:
        raise ToolError(f"that scan has {len(pages)} pages, more than the {MAX_IMAGE_PAGES} I can read at once; "
                        "send the pages with the schedule and due dates, or the course's digital PDF")
    if text is not None:
        answer = reader.ask(reader.model, [{"type": "text", "text": f"{PROMPT}\n\nSYLLABUS:\n{text}"}])
    else:
        answer = reader.ask(reader.model, [{"type": "text", "text": PROMPT}, *[image_part(p) for p in pages]])
    return parse_json(answer), text, how


# --- 3. check ---------------------------------------------------------------------------------------
def clock(value) -> str | None:
    """'7:00 PM' -> '19:00', '7 pm' -> '19:00', '9:10' -> '09:10', '23:59:00' -> '23:59'; None if unreadable."""
    match = re.match(r"^(\d{1,2})(?::(\d{2}))?(?::\d{2})?\s*(am|pm|a|p)?$", str(value or "").strip().lower().replace(".", ""))
    if not match or (match.group(2) is None and match.group(3) is None):  # a bare "7" isn't a time
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if match.group(3):
        hour = hour % 12 + (12 if match.group(3).startswith("p") else 0)
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def has_am_pm(value) -> bool:
    return bool(re.search(r"\d\s*[ap]\.?m?\.?\s*$", str(value or "").strip().lower()))


def pm_if_written(value, start: str, text: str | None) -> tuple[str, str | None]:
    """'11:59' without AM/PM is ambiguous. Make it PM if the syllabus text writes it with PM; with no text
    (a photo), assume a deadline at 11:59 means 11:59 PM, which is how syllabi use it."""
    if has_am_pm(value) or int(start[:2]) >= 12:
        return start, None
    hour, minute = int(start[:2]), start[3:]
    pm = f"{hour + 12:02d}:{minute}"
    if text is not None:
        if re.search(rf"\b{hour}:{minute}\s*p\.?m", text, re.IGNORECASE) and not re.search(rf"\b{hour}:{minute}\s*a\.?m", text, re.IGNORECASE):
            return pm, f"{start} is written as PM in the syllabus"
        return start, None
    if start == "11:59":
        return pm, "assumed 11:59 PM"
    return start, None


def course_code(course: str) -> str:
    """'CSE 260: Discrete Structures' -> 'CSE 260'; 'BS 161 - Cell and Molecular Biology' -> 'BS 161'."""
    match = re.search(r"\b[A-Z]{2,5}\s?\d{3,4}[A-Z]?\b", course or "")
    return match.group(0) if match else (course or "").split(":")[0].split(" - ")[0].strip()[:20]


def semester_window(data: dict, text: str | None) -> tuple[date, date] | None:
    """The months the semester can have dates in: from "Spring 2027" in the syllabus text, or from what
    the model read. Dates outside it aren't moved into it (a stray "December 1" stays December 1)."""
    for source in (text or "", str(data.get("term") or ""), str(data.get("course") or "")):
        match = re.search(r"\b(Spring|Summer|Fall|Autumn|Winter)\b[^0-9\n]{0,20}(20\d\d)", source, re.IGNORECASE)
        if match:
            season, year = match.group(1).lower(), int(match.group(2))
            return {"spring": (date(year, 1, 1), date(year, 6, 30)), "summer": (date(year, 5, 1), date(year, 8, 31)),
                    "fall": (date(year, 8, 1), date(year + 1, 1, 15)), "autumn": (date(year, 8, 1), date(year + 1, 1, 15)),
                    "winter": (date(year - 1, 12, 1), date(year, 2, 28))}[season]
    try:
        start = date.fromisoformat(str(data.get("term_start") or "")[:10])
    except ValueError:
        return None
    return start - timedelta(days=30), start + timedelta(days=200)


def date_patterns(day: date) -> list[str]:
    """Ways a syllabus writes a date: 2/18, 02/18/2027, 2027-02-18, February 18, Feb. 18th, 18 February,
    the 18th of February."""
    month = MONTHS[day.month - 1]
    names = rf"(?:{month}|{month[:3]}|{month[:4]})\.?"  # February, Feb, Sept
    th = r"(?:st|nd|rd|th)?"
    return [rf"\b0?{day.month}/0?{day.day}\b", rf"\b{day.year}-{day.month:02d}-{day.day:02d}\b",
            rf"\b{names}\s+0?{day.day}{th}\b", rf"\b0?{day.day}{th}\s+(?:of\s+)?{names}"]


def mentions_date(text: str, day: date) -> bool:
    """Does the syllabus text mention this date, in any of the usual ways?"""
    return any(re.search(p, text, re.IGNORECASE) for p in date_patterns(day))


def class_time_on(meetings: list[dict], day: date, start: str | None) -> tuple[str, str] | None:
    """The (start, end) of a class meeting on that weekday, matching the start time if one is given."""
    for m in meetings:
        if DAYS[day.weekday()] in m["days"] and (start is None or m["start"] == start):
            return m["start"], m["end"]
    return None


def expand_series(raw_items: list) -> list[dict]:
    """{"title": "Online quiz", "dates": [d1, d2, ...]} -> "Online quiz 1" on d1, "Online quiz 2" on d2, ..."""
    expanded = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        dates = raw.get("dates")
        if isinstance(dates, list) and dates and not raw.get("date"):
            title = str(raw.get("title") or "").strip()
            if len(dates) == 1:
                expanded.append({**raw, "date": dates[0]})
                continue
            # "Online quiz" -> Online quiz 1, 2, ...; "Online quiz 1" (the first one's name) -> 1, 2, ... as well
            match = re.match(r"^(.*?)\s*#?(\d+)$", title)
            base, first = (match.group(1), int(match.group(2))) if match else (title, 1)
            expanded += [{**raw, "title": f"{base} {first + k}", "date": d} for k, d in enumerate(dates)]
        else:
            expanded.append(raw)
    return expanded


def dates_in_text(text: str, window: tuple[date, date]) -> set[date]:
    """Every date the syllabus text writes (2/18, February 18, Feb. 18) that falls in the semester."""
    found = set()
    month_names = "|".join(m for name in MONTHS for m in (name, name[:4], name[:3]))
    number = lambda m: next(i for i, name in enumerate(MONTHS, 1) if name.lower().startswith(m.lower()[:3]))  # noqa: E731
    candidates = [(int(m), int(d)) for m, d in re.findall(r"\b(\d{1,2})/(\d{1,2})\b", text)]
    candidates += [(int(m), int(d)) for _, m, d in re.findall(r"\b(20\d\d)-(\d{2})-(\d{2})\b", text)]
    candidates += [(number(m), int(d)) for m, d in re.findall(rf"\b({month_names})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", text, re.IGNORECASE)]
    candidates += [(number(m), int(d)) for d, m in re.findall(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({month_names})\b", text, re.IGNORECASE)]
    for month, day in candidates:
        for year in {window[0].year, window[1].year}:
            try:
                candidate = date(year, month, day)
            except ValueError:
                continue
            if window[0] <= candidate <= window[1]:
                found.add(candidate)
    return found


def not_imported(text: str | None, data: dict, checked: "Checked", now: datetime) -> list[str]:
    """Dates the syllabus text mentions that didn't become an item, a class day or a break: a safety net,
    so a missed deadline is shown to the student instead of silently missing."""
    window = semester_window(data, text)
    if text is None or window is None:
        return []
    used = {i["start"].date() for i in checked.items}
    for m in checked.meetings:
        used |= {m["first_day"], m["last_day"]} | {date.fromisoformat(d) for d in m["skip_dates"]}
    for b in data.get("no_class") or []:
        try:
            first, last = date.fromisoformat(str(b.get("start"))[:10]), date.fromisoformat(str(b.get("end"))[:10])
        except ValueError:
            continue
        used |= {first.replace(year=d.year) + timedelta(days=k) for d in (first,) for k in range(max(0, (last - first).days) + 1)}
    used |= {d.replace(year=y) for d in list(used) for y in (window[0].year, window[1].year)
             if not (d.month == 2 and d.day == 29)}
    return [f"{d:%a %b} {d.day}" for d in sorted(dates_in_text(text, window) - used) if d > now.date()]


@dataclass
class Checked:
    items: list[dict]  # {title, kind: deadline|event, start, end (datetimes), notes: [...]}
    meetings: list[dict]  # {name, days, start, end, first_day, last_day, skip_dates}
    dropped: list[str]  # what was left out, and why
    notes: list[str]  # what code changed


FULL_DAYS = {"monday": "Mon", "tuesday": "Tue", "wednesday": "Wed", "thursday": "Thu", "friday": "Fri",
             "saturday": "Sat", "sunday": "Sun"}
SHORT_DAYS = {"Mon": "Mon", "Tue": "Tue", "Tues": "Tue", "Wed": "Wed", "Thu": "Thu", "Thur": "Thu", "Thurs": "Thu",
              "Fri": "Fri", "Sat": "Sat", "Sun": "Sun"}
DAY_WORD = (r"(?:(?i:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
            r"Mon|Tues|Tue|Wed|Thurs|Thur|Thu|Fri|Sat|Sun)")
DAY_RANGE = re.compile(rf"\b({DAY_WORD})s?\.?\s*(?:through|thru|to|-|–)\s*({DAY_WORD})s?\b")
DAY_NAMED = re.compile(rf"\b({DAY_WORD})s?\b")
# Letter codes: MWF, TTh, TR, MTWRF, TuTh, M/W/F ("T" is Tuesday; "Th" and "R" are Thursday)
DAY_CODES = re.compile(r"\b(?:Tu|Th|Sa|Su|M|T|W|R|F)(?:[ /,&-]{0,2}(?:Tu|Th|Sa|Su|M|T|W|R|F))*\b")
CODE_LETTERS = {"M": "Mon", "T": "Tue", "Tu": "Tue", "W": "Wed", "Th": "Thu", "R": "Thu", "F": "Fri", "Sa": "Sat", "Su": "Sun"}
# A line's parts: "Lecture MWF 10:20-11:10 AM; recitation Thursday 10:20-11:10 AM" is two meetings.
SEGMENTS = re.compile(r"[;|]|(?<=[^.\s][^.\s])\.\s+(?=[A-Z])|\s{3,}")


def day_name(word: str) -> str:
    return FULL_DAYS.get(word.lower()) or SHORT_DAYS[word]


def days_in(segment: str) -> set[str]:
    """The weekdays a piece of syllabus text names: 'Monday through Thursday', 'Tues & Thurs', 'MWF', 'M/W/F'."""
    found = set()
    for a, b in DAY_RANGE.findall(segment):
        first, last = DAYS.index(day_name(a)), DAYS.index(day_name(b))
        found |= set(DAYS[first:last + 1]) if first <= last else set()
    found |= {day_name(w) for w in DAY_NAMED.findall(segment)}
    for code in DAY_CODES.findall(segment):
        letters = re.findall(r"Tu|Th|Sa|Su|M|T|W|R|F", code)
        if len(letters) == 2 and re.fullmatch(r"\w\s*[-–]\s*\w", code):  # "M-F": a range, not two days
            found |= set(DAYS[DAYS.index(CODE_LETTERS[letters[0]]):DAYS.index(CODE_LETTERS[letters[1]]) + 1])
        elif len(letters) >= 2 or code in ("Th", "Tu"):  # a lone "M" or "F" is too likely to be something else
            found |= {CODE_LETTERS[x] for x in letters}
    return found


def days_from_text(text: str, kind: str, start: str) -> list[str] | None:
    """The days the syllabus text gives for a meeting that starts at `start` ("13:00"), or None if it doesn't say
    clearly: the days named in the same part of a line as the start time; if parts disagree, the one naming `kind`."""
    hour, minute = int(start[:2]), start[3:]
    at = re.compile(rf"(?<![\d:])(?:{hour}|{hour % 12 or 12}|{hour:02d}):{minute}(?!\d)")
    named = [(part, days) for line in text.splitlines() for part in SEGMENTS.split(line)
             if at.search(part) and (days := days_in(part))]
    choices = {frozenset(days) for _, days in named}
    if len(choices) > 1:
        choices = {frozenset(days) for part, days in named if kind.lower() in part.lower()}
    return [d for d in DAYS if d in next(iter(choices))] if len(choices) == 1 else None


def check(data: dict, now: datetime, text: str | None) -> Checked:
    tz = now.tzinfo
    window = semester_window(data, text)
    course = course_code(str(data.get("course") or ""))
    notes, dropped = [], []

    def fix_year(raw) -> date | None:
        try:
            day = date.fromisoformat(str(raw or "")[:10])
        except ValueError:
            return None
        if window and not window[0] <= day <= window[1]:
            for year in sorted({window[0].year, window[1].year}):
                try:
                    candidate = day.replace(year=year)
                except ValueError:  # February 29
                    continue
                if window[0] <= candidate <= window[1]:
                    notes.append(f"used the semester's year {year} for {raw}")
                    return candidate
        elif not window and day < now.date():  # no semester anywhere: a date already over is probably next year's
            day = day.replace(year=day.year + 1) if not (day.month == 2 and day.day == 29) else day
            notes.append(f"moved {raw} to {day.year}")
        return day

    meetings, raw_meetings = [], []
    for m in data.get("meetings") or []:
        days = [d[:3].title() for d in m.get("days") or [] if d[:3].title() in DAYS]
        start, end = clock(m.get("start")), clock(m.get("end"))
        if not days or not start or not end:
            continue
        if end <= start and int(end[:2]) < 12:  # "12:40 - 2:00" without PM
            end = f"{int(end[:2]) + 12:02d}{end[2:]}"
        kind = str(m.get("kind") or "class")
        # The model has read "Monday, Wednesday, and Friday" as every weekday: the text, where there is one, decides.
        written = days_from_text(text, kind, start) if text else None
        if written and written != days:
            notes.append(f"{course} {kind}: days corrected to {'/'.join(written)} from the syllabus text "
                         f"(read as {'/'.join(days)})")
            days = written
        raw_meetings.append({"kind": kind, "days": days, "start": start, "end": end})

    first_day, last_day = fix_year(data.get("term_start")), fix_year(data.get("term_end"))
    breaks = []
    for b in data.get("no_class") or []:
        start_day, end_day = fix_year(b.get("start")), fix_year(b.get("end"))
        if start_day:
            breaks.append((start_day, end_day if end_day and end_day >= start_day else start_day))
    for m in raw_meetings:
        if not (first_day and last_day and first_day < last_day):
            dropped.append(f"{course} {m['kind']}: the semester's first and last day weren't found")
            continue
        if last_day < now.date():  # an old syllabus (one from 2024 was imported): no classes left to add
            dropped.append(f"{course} {m['kind']}: the semester ended on {last_day:%B} {last_day.day}, {last_day.year}")
            continue
        skip = [first_day + timedelta(days=k) for k in range((last_day - first_day).days + 1)]
        skip = [d.isoformat() for d in skip if any(a <= d <= b for a, b in breaks) and DAYS[d.weekday()] in m["days"]]
        meetings.append({"name": f"{course} {m['kind'].title()}".strip(), "days": m["days"], "start": m["start"],
                         "end": m["end"], "first_day": first_day, "last_day": last_day, "skip_dates": skip})

    items, seen = [], set()
    for raw in expand_series(data.get("items") or []):
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        if course and course.lower() not in title.lower():
            title = f"{course} {title}"
        day = fix_year(raw.get("date"))
        if day is None:
            dropped.append(f"{title}: {raw.get('date')!r} isn't a real date")
            continue
        item_notes = []
        start, end = clock(raw.get("time")), clock(raw.get("end_time"))
        if start:
            start, why = pm_if_written(raw.get("time"), start, text)
            item_notes += [why] if why else []
        kind = str(raw.get("kind"))
        # in-class quizzes and exams often have no time of their own ("Quiz 1 in recitation (Wed 2/3)")
        timed = (kind in ("exam", "presentation") or end is not None
                 or (kind == "quiz" and start is None and class_time_on(raw_meetings, day, None) is not None))
        if timed:
            if start and end and end <= start and int(end[:2]) < 12:
                end = f"{int(end[:2]) + 12:02d}{end[2:]}"
            if not start or not end:
                in_class = class_time_on(raw_meetings, day, start)
                if in_class:
                    start, end = in_class
                    item_notes.append("time taken from the class schedule")
                elif start:
                    hours = 2 if "final" in title.lower() else 1
                    end = (datetime.combine(day, datetime.strptime(start, "%H:%M").time()) + timedelta(hours=hours)).strftime("%H:%M")
                    item_notes.append("end time guessed")
                else:
                    timed = False
                    item_notes.append("no time found")
        if not timed:
            if start is None:
                start = "23:59"
                item_notes.append("no due time given; set to 11:59 PM")
            end = start
        if text is not None and not mentions_date(text, day):
            item_notes.append("this date isn't in the syllabus text; please check it")
        begin = datetime.combine(day, datetime.strptime(start, "%H:%M").time(), tzinfo=tz)
        finish = datetime.combine(day, datetime.strptime(end, "%H:%M").time(), tzinfo=tz)
        if begin <= now:
            dropped.append(f"{title} ({day}): already over")
            continue
        key = (title.lower(), day)
        if key in seen:
            continue
        seen.add(key)
        items.append({"title": title, "kind": "event" if timed else "deadline", "start": begin, "end": finish,
                      "notes": item_notes})
    return Checked(items, meetings, dropped, sorted(set(notes)))


# --- 4. suggest -------------------------------------------------------------------------------------
def suggest(ctx: ToolContext, checked: Checked) -> list[str]:
    """Create one PENDING suggestion per item and per weekly class. Returns their ids."""
    ids = []
    for item in checked.items:
        description = "From your syllabus" + (" (" + "; ".join(item["notes"]) + ")" if item["notes"] else "")
        needs_check = any("please check" in n for n in item["notes"])
        if item["kind"] == "deadline":  # a due date is a task, not a block of time on the calendar
            change = {"name": item["title"], "due": item["start"].isoformat(), "kind": "deadline", "needs_check": needs_check,
                      "source": "syllabus"}
            kind = "CREATE_TASK"
        else:
            change = {"name": item["title"], "start": item["start"].isoformat(), "end": item["end"].isoformat(),
                      "kind": "event", "needs_check": needs_check, "source": "syllabus"}
            kind = "CREATE_EVENT"
        suggestion = ctx.store.add_suggestion(ctx.user_id, {
            "type": kind, "target_id": None, "description": description, "proposed_change": change,
            "depends_on": [], "created_at": ctx.now.isoformat(), "expires_at": item["start"].isoformat(),
        })
        ids.append(suggestion["suggestion_id"])
    tz = ctx.now.tzinfo
    for m in checked.meetings:
        first = next(m["first_day"] + timedelta(days=k) for k in range(7)
                     if DAYS[(m["first_day"] + timedelta(days=k)).weekday()] in m["days"])
        start = datetime.combine(first, datetime.strptime(m["start"], "%H:%M").time(), tzinfo=tz)
        end = datetime.combine(first, datetime.strptime(m["end"], "%H:%M").time(), tzinfo=tz)
        rule = f"FREQ=WEEKLY;BYDAY={','.join(RRULE_DAYS[d] for d in m['days'])};UNTIL={m['last_day']:%Y%m%d}"
        if m["skip_dates"]:  # days without class (breaks), as an extension the app's calendar reads
            rule += ";X-SKIP=" + ",".join(d.replace("-", "") for d in m["skip_dates"])
        suggestion = ctx.store.add_suggestion(ctx.user_id, {
            "type": "CREATE_EVENT", "target_id": None, "description": "Weekly class from your syllabus",
            "proposed_change": {"name": m["name"], "start": start.isoformat(), "end": end.isoformat(),
                                "recurrence_rule": rule, "days": m["days"], "skip_dates": m["skip_dates"], "source": "syllabus"},
            "depends_on": [], "created_at": ctx.now.isoformat(),
            "expires_at": datetime.combine(m["last_day"], datetime.max.time(), tzinfo=tz).isoformat(),
        })
        ids.append(suggestion["suggestion_id"])
    return ids


def import_syllabus(ctx: ToolContext, reader: Reader, data: bytes, filename: str) -> dict:
    """The whole pipeline. Returns what was suggested, what needs checking, and what was left out."""
    started = time.perf_counter()
    pages = load_pages(data, filename)
    try:
        extracted, text, how = read(reader, pages)
    except (ValueError, json.JSONDecodeError) as error:
        raise ToolError(f"couldn't read the syllabus ({error}); ask the user for a clearer photo or the PDF") from None
    checked = check(extracted, ctx.now, text)
    ids = suggest(ctx, checked)
    missing = not_imported(text, extracted, checked, ctx.now)

    def when(i: dict) -> str:
        text = f"{i['start']:%a %b} {i['start'].day}, {i['start'].strftime('%I:%M %p').lstrip('0')}"
        return text + (f"-{i['end'].strftime('%I:%M %p').lstrip('0')}" if i["kind"] == "event" else "")

    return {
        "course": extracted.get("course"), "read_as": how, "suggestion_ids": ids,
        "items": [f"{i['title']} ({when(i)})" for i in checked.items],
        "weekly_classes": [f"{m['name']} {'/'.join(m['days'])} {m['start']}-{m['end']}" for m in checked.meetings],
        "needs_check": [f"{i['title']}: {'; '.join(i['notes'])}" for i in checked.items if i["notes"]],
        "left_out": checked.dropped, "fixes": checked.notes, "seconds": round(time.perf_counter() - started, 1),
        "dates_not_imported": missing,
        "summary": (f"Suggested {len(checked.items)} dated items and {len(checked.meetings)} weekly classes. Nothing "
                    "changes until the user accepts them. Tell the user how many were suggested, name any that need "
                    "checking, and ask them to review the suggestions; don't repeat the dates yourself."
                    + (f" These dates are in the syllabus but weren't imported: {', '.join(missing)}. Ask the user "
                       "whether any of them is a deadline." if missing else "")),
    }


IMPORT_SYLLABUS_TOOL = {
    "type": "function",
    "function": {
        "name": "import_syllabus",
        "description": (
            "Read a syllabus the user uploaded (PDF or photo) and suggest all its deadlines, exams and weekly "
            "classes at once. Use this instead of proposing syllabus items one by one. Nothing changes until "
            "the user accepts the suggestions."
        ),
        "parameters": {
            "type": "object",
            "properties": {"upload_id": {"type": "string", "description": "The id of the uploaded file, e.g. 'u1'"}},
            "required": ["upload_id"],
        },
    },
}
