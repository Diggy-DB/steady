"""Importing another calendar (Google Calendar, Apple iCloud, Outlook, Canvas, ...) through its private iCal address.

The person pastes the calendar's secret .ics address once (Settings › Calendar apps). Then:

- fetch_calendar downloads it, carefully: https only, to public internet addresses only (never this machine or its
  network, where the model server and other private services listen), at most MAX_BYTES, a few redirects.
- read_calendar turns it into Steady events in the person's time zone: one row per time an event happens, from
  PAST_DAYS ago to AHEAD_DAYS ahead. Repeating events are expanded, with moved and skipped times applied; all-day and
  cancelled events are left out.
- plan_sync compares those rows with the ones the last sync saved: what to add or change, and what to remove.
- sync does all of it for one import, with the person's own login token (SupabaseStore), and records when it worked
  or, in plain words, why not.

Imported events are fixed (changeable = false): the AI plans around them and never suggests moving or deleting them.
Nothing is ever written back to the other calendar. The tables are in
supabase/migrations/20261118120000_calendar_imports.sql.
"""

import hashlib
import ipaddress
import socket
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

PAST_DAYS = 7  # events a week back stay up to date; older ones are kept as they were
AHEAD_DAYS = 120  # about a semester ahead
MAX_BYTES = 10_000_000
MAX_EVENTS = 3000  # per import, earliest first
MAX_IMPORTS = 10  # per person
MAX_REDIRECTS = 3
TIMEOUT = httpx.Timeout(20, connect=10)
NO_END = timedelta(minutes=15)  # an event with no end time (a reminder) shows as 15 minutes
NAT64 = ipaddress.ip_network("64:ff9b::/96")  # IPv6-only networks reach IPv4 addresses through these

NOT_FOUND = ("That calendar wasn't found. For Google Calendar, copy the \"Secret address in iCal format\" again "
             "(resetting it makes a new one).")
NOT_A_CALENDAR = ("That address isn't a calendar file. For Google Calendar use the \"Secret address in iCal format\", "
                  "not the calendar's web page.")

WELL_KNOWN = {"calendar.google.com": "Google Calendar", "icloud.com": "iCloud Calendar", "outlook.live.com": "Outlook",
              "outlook.office365.com": "Outlook", "instructure.com": "Canvas"}


class CalendarLinkError(Exception):
    """A problem with the address or the calendar behind it, in words the person can act on."""


# ---- The address ----

def normalize_link(text: str) -> str:
    """The address to download: webcal:// and http:// become https://. Refuses anything else."""
    url = text.strip()
    for scheme in ("webcal://", "webcals://", "http://"):
        if url.lower().startswith(scheme):
            url = "https://" + url[len(scheme):]
    if len(url) > 2000:
        raise CalendarLinkError("That address is too long to be a calendar address.")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise CalendarLinkError("That isn't a web address.") from None
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise CalendarLinkError("That isn't a calendar address. It should start with https:// or webcal://.")
    if parts.username or parts.password or port not in (None, 443):
        raise CalendarLinkError("Steady can only read calendar addresses on the normal web port, without a login.")
    return url


def is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return is_public(address.ipv4_mapped)
        if address in NAT64:  # "64:ff9b::7f00:1" is 127.0.0.1
            return is_public(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
    return address.is_global and not address.is_multicast


def check_host(host: str, resolve=socket.getaddrinfo) -> None:
    """Refuse a host that is, or resolves to, a private, local or reserved address. With https only (the certificate
    must match the name), a name that changes its address after this check still can't reach a private plain-http
    service such as the model server."""
    try:
        found = resolve(host, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise CalendarLinkError(f"Couldn't find {host}. Check the address.") from None
    if not found:
        raise CalendarLinkError(f"Couldn't find {host}. Check the address.")
    for *_, sockaddr in found:
        if not is_public(ipaddress.ip_address(str(sockaddr[0]).split("%")[0])):
            raise CalendarLinkError("That address is on a private network, which Steady can't read.")


def fetch_calendar(url: str, transport: httpx.BaseTransport | None = None, resolve=socket.getaddrinfo) -> bytes:
    """Download the calendar file at a normalized address."""
    headers = {"User-Agent": "SteadyPlanner/1.0 (calendar import)", "Accept": "text/calendar, */*;q=0.5"}
    with httpx.Client(transport=transport, timeout=TIMEOUT, follow_redirects=False, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            check_host(urlsplit(url).hostname, resolve)
            try:
                with client.stream("GET", url) as response:
                    if response.is_redirect and "location" in response.headers:
                        url = normalize_link(urljoin(url, response.headers["location"]))  # checked again, every hop
                        continue
                    if response.status_code in (401, 403, 404, 410):
                        raise CalendarLinkError(NOT_FOUND)
                    if response.status_code >= 400:
                        raise CalendarLinkError(f"The calendar's server answered with an error ({response.status_code}). "
                                                "Try again later.")
                    data = bytearray()
                    for chunk in response.iter_bytes():  # unzipped as it comes, so the limit is on the real size
                        data += chunk
                        if len(data) > MAX_BYTES:
                            raise CalendarLinkError("That calendar is too big to import (over 10 MB).")
                    return bytes(data)
            except httpx.TimeoutException:
                raise CalendarLinkError("The calendar's server took too long to answer. Try again later.") from None
            except httpx.HTTPError as error:
                raise CalendarLinkError(f"Couldn't download the calendar ({type(error).__name__}).") from None
    raise CalendarLinkError("That address redirects too many times.")


# ---- The calendar ----

def parse_calendar(data: bytes) -> icalendar.Calendar:
    text = data.lstrip(b"\xef\xbb\xbf \t\r\n")
    if not text[:15].upper().startswith(b"BEGIN:VCALENDAR"):
        raise CalendarLinkError(NOT_A_CALENDAR)
    try:
        return icalendar.Calendar.from_ical(text)
    except ValueError:
        raise CalendarLinkError("That calendar file is damaged and couldn't be read.") from None


def calendar_name(calendar: icalendar.Calendar, url: str) -> str:
    """The calendar's own name, unless it's an email address (Google names your main calendar after it)."""
    own = str(calendar.get("X-WR-CALNAME") or "").strip()
    if own and "@" not in own:
        return own[:100]
    host = (urlsplit(url).hostname or "").lower()
    for domain, label in WELL_KNOWN.items():
        if host == domain or host.endswith("." + domain):
            return label
    return host[:100] or "Imported calendar"


def _local(moment: datetime, tz: ZoneInfo) -> datetime:
    return moment.replace(tzinfo=tz) if moment.tzinfo is None else moment.astimezone(tz)  # no zone = the person's


def _key(uid: str, repeats: bool, occurrence: datetime) -> str:
    """Which event this is in the other calendar: its UID, plus which time for a repeating one. A moved time keeps
    its original RECURRENCE-ID, so moving it changes the row instead of replacing it."""
    if repeats:
        uid = f"{uid}|{occurrence.astimezone(ZoneInfo('UTC')):%Y%m%dT%H%M%SZ}"
    return uid if len(uid) <= 900 else "sha256:" + hashlib.sha256(uid.encode()).hexdigest()


def _row(event, tz: ZoneInfo, repeating: set[str]) -> dict | None:
    if str(event.get("STATUS", "")).upper() == "CANCELLED":
        return None
    uid = str(event.get("UID") or "").strip()
    if uid.endswith("@steady-planner"):  # Steady's own calendar link, imported back: already here
        return None
    start = event.get("DTSTART").dt if event.get("DTSTART") else None
    if not isinstance(start, datetime):  # all-day (a date): birthdays, holidays; nothing to plan around
        return None
    start = _local(start, tz)
    end = event.get("DTEND").dt if event.get("DTEND") else None
    if end is None and event.get("DURATION"):
        end = start + event.get("DURATION").dt
    end = _local(end, tz) if isinstance(end, datetime) else start
    if end <= start:
        end = start + NO_END
    name = " ".join(str(event.get("SUMMARY") or "").split())[:200] or "(No title)"
    rid = event.get("RECURRENCE-ID")
    occurrence = _local(rid.dt, tz) if rid and isinstance(rid.dt, datetime) else start
    if not uid:  # not allowed, but it happens: use what the event says
        uid = "no-uid:" + hashlib.sha256(f"{name}|{start.isoformat()}".encode()).hexdigest()
    return {
        "external_id": _key(uid, uid in repeating, occurrence),
        "name": name,
        "start_date": start.date().isoformat(),
        "start_time": f"{start:%H:%M:%S}",
        "end_date": end.date().isoformat(),
        "end_time": f"{end:%H:%M:%S}",
    }


def read_calendar(calendar: icalendar.Calendar, tz: ZoneInfo, first_day: date, last_day: date) -> list[dict]:
    """The events that start between first_day and last_day (both included), as calendar_events rows."""
    repeating = {str(e.get("UID") or "").strip() for e in calendar.walk("VEVENT")
                 if e.get("RRULE") or e.get("RDATE") or e.get("RECURRENCE-ID")}
    try:
        happenings = list(recurring_ical_events.of(calendar).between(first_day - timedelta(days=1), last_day + timedelta(days=2)))
    except Exception as error:  # a rule the library can't follow, a broken time zone, ...
        raise CalendarLinkError(f"Part of that calendar couldn't be read ({type(error).__name__}).") from None
    rows: dict[str, dict] = {}
    for event in happenings:
        row = _row(event, tz, repeating)
        if row and first_day.isoformat() <= row["start_date"] <= last_day.isoformat():
            rows.setdefault(row["external_id"], row)
    return sorted(rows.values(), key=lambda r: (r["start_date"], r["start_time"], r["external_id"]))[:MAX_EVENTS]


FIELDS = ("name", "start_date", "start_time", "end_date", "end_time")


def plan_sync(saved: list[dict], wanted: list[dict]) -> tuple[list[dict], list[int]]:
    """(rows to add or change, event ids to remove). Unchanged rows are left alone."""
    old = {row["external_id"]: row for row in saved}
    write = []
    for row in wanted:
        before = old.pop(row["external_id"], None)
        if before is None or before.get("changeable") is not False or any(str(before.get(f)) != row[f] for f in FIELDS):
            write.append(row)
    return write, [row["event_id"] for row in old.values()]


# ---- Syncing (with the person's token: Row Level Security applies) ----

def window(today: date) -> tuple[date, date]:
    return today - timedelta(days=PAST_DAYS), today + timedelta(days=AHEAD_DAYS)


def sync(store, user_id: str, imported: dict, now: datetime, calendar: icalendar.Calendar | None = None,
         fetch=None) -> dict:
    """Bring one import's events up to date. Never raises for a problem with the calendar: it's recorded instead."""
    first, last = window(now.date())
    summary = {"import_id": imported["import_id"], "name": imported["name"]}
    try:
        if calendar is None:
            calendar = parse_calendar((fetch or fetch_calendar)(imported["url"]))
        wanted = read_calendar(calendar, now.tzinfo, first, last)
    except CalendarLinkError as error:
        store.finish_calendar_sync(user_id, imported["import_id"], now, error=str(error))
        return {**summary, "ok": False, "error": str(error)}
    write, remove = plan_sync(store.imported_events(user_id, imported["import_id"], first), wanted)
    store.delete_imported_events(user_id, imported["import_id"], remove)
    store.save_imported_events(user_id, imported["import_id"], write)
    store.finish_calendar_sync(user_id, imported["import_id"], now)
    return {**summary, "ok": True, "events": len(wanted), "changed": len(write), "removed": len(remove)}


def add_import(store, user_id: str, link: str, name: str, now: datetime, fetch=None) -> dict:
    """Check the address and the calendar behind it, save the import, and sync it. Raises CalendarLinkError, before
    saving anything, when the address or the calendar is no good."""
    url = normalize_link(link)
    imports = store.calendar_imports(user_id)
    if any(i["url"] == url for i in imports):
        raise CalendarLinkError("That calendar is already imported.")
    if len(imports) >= MAX_IMPORTS:
        raise CalendarLinkError(f"You can import up to {MAX_IMPORTS} calendars. Remove one first.")
    calendar = parse_calendar((fetch or fetch_calendar)(url))
    read_calendar(calendar, now.tzinfo, *window(now.date()))  # fails here, not after saving, if it can't be read
    imported = store.add_calendar_import(user_id, " ".join(name.split())[:100] or calendar_name(calendar, url), url)
    return sync(store, user_id, imported, now, calendar=calendar)


def sync_imports(store, user_id: str, now: datetime, import_id: int | None = None,
                 older_than: timedelta | None = None, fetch=None) -> list[dict]:
    """Sync one import, or all of them; with older_than, only the ones not tried for that long (when the app opens)."""
    results = []
    for imported in store.calendar_imports(user_id):
        if import_id is not None and imported["import_id"] != import_id:
            continue
        checked = imported.get("last_checked_at")
        if older_than and checked and now - datetime.fromisoformat(checked) < older_than:
            continue
        results.append(sync(store, user_id, imported, now, fetch=fetch))
    return results
