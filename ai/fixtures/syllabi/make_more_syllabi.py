"""More test syllabi, one category of edge case each, at least two syllabi per category (so one good
result can't be a fluke). Adds them to truth.json next to the first eight (make_syllabi.py).

    fall          e_hst201_fall.pdf, e_cse335_fall.pdf           Fall 2027: Thanksgiving, December finals
    summer        e_stt231_summer.pdf, e_iss215_online.pdf      six-week summer session (the second is online)
    formats       e_psy101_formats.pdf, e_ece230_formats.pdf    "29 January", "Feb. 15th", ISO dates, 24-hour times, noon
    relative      e_mth132_weeks.pdf, e_phl130_relative.pdf     "HW 3 (Wed)" in a week-of table; "Friday of Week 4"
    distractors   e_anth101_distractors.pdf, e_acc201_every.pdf TBA, revision dates, drop dates; "every Friday" unlisted
    long          e_bs162_long.pdf, e_cem251_long.pdf           6-7 pages; dates scattered; a schedule table split across pages
    meetings      e_phy231_meetings.pdf, e_iss215_online.pdf    three meeting types; none at all (online)
    hard photos   v_*.jpg                                       sideways, low resolution, dark, cropped, two pages in one photo

    uv run --with reportlab --with pymupdf --with pillow python fixtures/syllabi/make_more_syllabi.py
"""

import io
import json
import random
from datetime import date, timedelta

from PIL import Image, ImageEnhance
from reportlab.platypus import PageBreak, Paragraph, Spacer

import make_syllabi as base
from make_syllabi import BODY, H1, H2, HERE, SMALL, build_pdf, item, render, table

SPRING_BREAK = (date(2027, 3, 8), date(2027, 3, 12))
FILLER = [
    ("Course materials", "The required textbook is available at the campus bookstore and as an e-book. Lecture slides are "
     "posted on D2L after each class. You will also need a calculator for some assignments and all exams."),
    ("Grading scale", "4.0: 90-100%, 3.5: 85-89%, 3.0: 80-84%, 2.5: 75-79%, 2.0: 70-74%, 1.5: 65-69%, 1.0: 60-64%, "
     "0.0: below 60%. Grades are not curved, and extra credit is not offered."),
    ("Technology", "Bring a laptop or tablet to class when the schedule says so. If you don't have one, the library lends "
     "them for the semester. Report technical problems to the help desk before the deadline, not after."),
    ("Mental health", "College can be stressful. Counseling and Psychiatric Services offers free and confidential support. "
     "If you are struggling, please reach out to them or to me; I will help you find the right resources."),
    ("Title IX", "Instructors are required to report incidents of sexual misconduct to the Office of Institutional Equity. "
     "Confidential resources are available through the Center for Survivors and the counseling center."),
    ("Religious observance", "If a religious holiday conflicts with an assignment or exam, let me know during the first two "
     "weeks of class so that we can arrange an alternative."),
]


def d(y, m, dd) -> date:
    return date(y, m, dd)


def every(first: date, until: date, step_days: int = 7, skip: tuple[date, date] | None = None) -> list[date]:
    days, x = [], first
    while x <= until:
        if not (skip and skip[0] <= x <= skip[1]):
            days.append(x)
        x += timedelta(days=step_days)
    return days


def md(x: date) -> str:  # 9/17
    return f"{x.month}/{x.day}"


def long(x: date) -> str:  # Friday, September 17
    return f"{x:%A}, {x:%B} {x.day}"


def ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def filler(story, pages: int = 1) -> None:
    for _ in range(pages):
        for title, text in FILLER:
            story += [Paragraph(title, H2), Paragraph(text + " " + text, BODY)]
        base.policies(story, {"Attendance", "Academic integrity", "Accommodations", "Late work", "Communication"})


def course(code, term_start, term_end, meetings, items, **extra) -> dict:
    return {"course": code, "term_start": term_start.isoformat(), "term_end": term_end.isoformat(),
            "meetings": [{"kind": k, "days": days, "start": s, "end": e} for k, days, s, e in meetings],
            "items": items, **extra}


# --- fall ------------------------------------------------------------------------------------------
def hst201():
    rp = [d(2027, 9, 17), d(2027, 10, 8), d(2027, 11, 5)]
    items = [item(f"Response paper {i}", "assignment", x, "17:00") for i, x in enumerate(rp, 1)]
    items += [item("Midterm exam", "exam", d(2027, 10, 14), "11:30", "12:50"),
              item("Research paper", "assignment", d(2027, 12, 9), "12:00"),
              item("Final exam", "exam", d(2027, 12, 15), "07:45", "09:45")]
    story = [Paragraph("HST 201: American History Since 1877", H1), Paragraph("Fall 2027 - Section 002", BODY),
             Paragraph("We meet Tuesdays and Thursdays from 11:30 a.m. to 12:50 p.m. in 105 Berkey Hall, starting "
                       "Tuesday, August 31. There is no class on Thursday, November 25 (Thanksgiving break runs "
                       "November 24-28). The last class is Thursday, December 9.", BODY),
             Paragraph("Assignments", H2),
             Paragraph("Three short response papers (two pages each) are due on D2L by 5 p.m.: the first on Friday, Sept. 17, "
                       "the second on Friday, Oct. 8, and the third on Friday, Nov. 5.", BODY),
             Paragraph("The midterm exam is in class on Thursday, October 14. The research paper (10 pages) is due "
                       "Thursday, December 9 by noon. The final exam is Wednesday, December 15, 7:45-9:45 a.m.", BODY)]
    filler(story)
    build_pdf(HERE / "e_hst201_fall.pdf", story)
    return course("HST 201", d(2027, 8, 31), d(2027, 12, 9), [("lecture", ["Tue", "Thu"], "11:30", "12:50")], items,
                  category="fall")


def cse335():
    labs = every(d(2027, 9, 5), d(2027, 12, 5), skip=(d(2027, 11, 28), d(2027, 11, 28)))
    items = [item(f"Lab {i}", "assignment", x, "23:59") for i, x in enumerate(labs, 1)]
    items += [item(f"Project {i}", "project", x, "23:59") for i, x in enumerate([d(2027, 10, 1), d(2027, 11, 5), d(2027, 12, 10)], 1)]
    items += [item("Midterm", "exam", d(2027, 10, 20), "15:00", "16:20"), item("Final exam", "exam", d(2027, 12, 13), "10:00", "12:00")]
    rows = [["Week", "Dates", "Topics", "Due"]]
    for w in range(15):
        mon = d(2027, 8, 30) + timedelta(weeks=w)
        due = [f"Lab {i} (Sun {md(x)})" for i, x in enumerate(labs, 1) if mon <= x < mon + timedelta(days=7)]
        due += [f"Project {i} (Fri {md(x)})" for i, x in enumerate([d(2027, 10, 1), d(2027, 11, 5), d(2027, 12, 10)], 1)
                if mon <= x < mon + timedelta(days=7)]
        if mon <= d(2027, 10, 20) < mon + timedelta(days=7):
            due.append("MIDTERM in class (Wed 10/20)")
        if mon <= d(2027, 11, 25) < mon + timedelta(days=7):
            due.append("Thanksgiving: no lab Fri 11/26")
        rows.append([str(w + 1), f"{md(mon)} - {md(mon + timedelta(days=4))}", Paragraph(f"Topic {w + 1}", SMALL),
                     Paragraph("<br/>".join(due) or "-", SMALL)])
    rows.append(["Finals", "12/13 - 12/17", "", Paragraph("FINAL EXAM Mon 12/13, 10:00 AM - 12:00 PM", SMALL)])
    story = [Paragraph("CSE 335: Object-Oriented Software Design", H1), Paragraph("Fall 2027", BODY),
             table([["Lectures", "Mon & Wed 3:00 - 4:20 PM, 1279 Anthony Hall"], ["Lab", "Fri 10:20 AM - 12:10 PM, 3353 EB"],
                    ["Deadlines", "Labs: Sundays 11:59 PM. Projects: Fridays 11:59 PM."]], [1.3 * base.inch, 5.2 * base.inch]),
             Paragraph("Classes run August 30 to December 10, 2027.", BODY), Paragraph("Schedule", H2),
             table(rows, [0.5 * base.inch, 1.0 * base.inch, 2.0 * base.inch, 3.1 * base.inch])]
    build_pdf(HERE / "e_cse335_fall.pdf", story)
    return course("CSE 335", d(2027, 8, 30), d(2027, 12, 10),
                  [("lecture", ["Mon", "Wed"], "15:00", "16:20"), ("lab", ["Fri"], "10:20", "12:10")], items, category="fall")


# --- summer ----------------------------------------------------------------------------------------
def stt231():
    hw = [d(2027, 5, 20), d(2027, 5, 27), d(2027, 6, 3), d(2027, 6, 10), d(2027, 6, 17)]
    quizzes = [d(2027, 5, 24), d(2027, 6, 7), d(2027, 6, 14), d(2027, 6, 21)]
    items = [item(f"HW {i}", "assignment", x, "23:59") for i, x in enumerate(hw, 1)]
    items += [item(f"Quiz {i}", "quiz", x, "10:00", "11:50") for i, x in enumerate(quizzes, 1)]
    items += [item("Exam 1", "exam", d(2027, 6, 3), "10:00", "11:50"), item("Final exam", "exam", d(2027, 6, 24), "10:00", "11:50")]
    lines = [f"Mon {md(x)}: Quiz {i} in class" for i, x in enumerate(quizzes, 1)]
    lines += [f"Thu {md(x)}: HW {i} due 11:59 PM" for i, x in enumerate(hw, 1)]
    lines += ["Thu 6/3: Exam 1 in class", "Thu 6/24: Final exam in class", "Mon 5/31: Memorial Day, no class"]
    story = [Paragraph("STT 231: Statistics for Scientists (Summer 2027, first session)", H1),
             Paragraph("Class meets Monday through Thursday, 10:00-11:50 AM, in A102 Wells Hall, May 17 - June 24.", BODY),
             Paragraph("Key dates", H2)] + [Paragraph("&bull; " + line, BODY) for line in sorted(lines, key=lambda s: tuple(map(int, s[4:].split(":")[0].split("/"))))]
    filler(story)
    build_pdf(HERE / "e_stt231_summer.pdf", story)
    return course("STT 231", d(2027, 5, 17), d(2027, 6, 24), [("lecture", ["Mon", "Tue", "Wed", "Thu"], "10:00", "11:50")],
                  items, category="summer")


def iss215():
    posts = every(d(2027, 5, 19), d(2027, 6, 23))
    replies = every(d(2027, 5, 23), d(2027, 6, 27))
    items = [item(f"Discussion post {i}", "assignment", x, "23:59") for i, x in enumerate(posts, 1)]
    items += [item(f"Discussion replies {i}", "assignment", x, "23:59") for i, x in enumerate(replies, 1)]
    items += [item("Final project", "project", d(2027, 6, 25), "17:00")]
    story = [Paragraph("ISS 215: Social Differentiation and Inequality (Online, Summer 2027)", H1),
             Paragraph("This is a fully online, asynchronous course: there are no class meetings. Each week is a module on "
                       "D2L that opens on Monday. The course runs May 17 - June 25, 2027.", BODY),
             Paragraph("Weekly rhythm", H2),
             Paragraph("Each week you write one discussion post, due Wednesday at 11:59 PM, and reply to two classmates "
                       "by Sunday at 11:59 PM.", BODY),
             table([["Week", "Post due (Wed)", "Replies due (Sun)"]] +
                   [[str(i), long(p), long(r)] for i, (p, r) in enumerate(zip(posts, replies), 1)],
                   [0.7 * base.inch, 2.6 * base.inch, 2.6 * base.inch]),
             Paragraph("The final project is due Friday, June 25 at 5:00 PM.", BODY)]
    filler(story)
    build_pdf(HERE / "e_iss215_online.pdf", story)
    return course("ISS 215", d(2027, 5, 17), d(2027, 6, 25), [], items, category="summer+meetings")


# --- formats ---------------------------------------------------------------------------------------
def psy101():
    quizzes = [d(2027, 1, 29), d(2027, 2, 12), d(2027, 2, 26), d(2027, 3, 19), d(2027, 4, 2), d(2027, 4, 16)]
    items = [item(f"Reading quiz {i}", "quiz", x, "12:00") for i, x in enumerate(quizzes, 1)]
    items += [item("Essay 1", "assignment", d(2027, 2, 15), "23:59"), item("Essay 2", "assignment", d(2027, 4, 12), "23:59"),
              item("Exam 1", "exam", d(2027, 2, 24), "13:50", "14:40"), item("Final exam", "exam", d(2027, 5, 4), "15:00", "17:00")]
    quiz_text = ", ".join(f"{x.day} {x:%B}" for x in quizzes)
    story = [Paragraph("PSY 101 Introductory Psychology - Spring 2027", H1),
             Paragraph("Lectures: Mon/Wed/Fri 1:50-2:40pm, 108 Psychology Building. Term: 11 January - 30 April 2027.", BODY),
             Paragraph("Reading quizzes are due at noon on these Fridays: " + quiz_text + ".", BODY),
             Paragraph("Essay 1 is due Monday, February 15th, 11:59pm. Essay 2 is due Monday, April 12th, 11:59pm.", BODY),
             Paragraph("Exam 1 will be held in class on Wednesday the 24th of February. The final exam is Tuesday, May 4th, "
                       "3:00-5:00pm.", BODY)]
    filler(story)
    build_pdf(HERE / "e_psy101_formats.pdf", story)
    return course("PSY 101", d(2027, 1, 11), d(2027, 4, 30), [("lecture", ["Mon", "Wed", "Fri"], "13:50", "14:40")], items,
                  category="formats")


def ece230():
    ps = [d(2027, 1, 22), d(2027, 2, 5), d(2027, 2, 19), d(2027, 3, 5), d(2027, 3, 26), d(2027, 4, 16)]
    labs = [d(2027, 1, 29), d(2027, 3, 19), d(2027, 4, 23)]
    items = [item(f"PS{i}", "assignment", x, "23:59") for i, x in enumerate(ps, 1)]
    items += [item(f"Lab report {i}", "assignment", x, "17:00") for i, x in enumerate(labs, 1)]
    items += [item("Midterm", "exam", d(2027, 3, 2), "08:30", "09:50"), item("Final", "exam", d(2027, 5, 6), "07:45", "09:45")]
    rows = [["Item", "Due"]] + [[f"PS{i}", f"{x.isoformat()} 23:59"] for i, x in enumerate(ps, 1)]
    rows += [[f"Lab report {i}", f"{x.month}/{x.day}/{x.year} 17:00"] for i, x in enumerate(labs, 1)]
    rows += [["Midterm (in class)", "2027-03-02 08:30-09:50"], ["Final", "2027-05-06 07:45-09:45"]]
    story = [Paragraph("ECE 230: Digital Logic Fundamentals", H1), Paragraph("Spring 2027 | Tue/Thu 08:30-09:50 | 1300 EB", BODY),
             Paragraph("All times are 24-hour times. Classes: 2027-01-12 to 2027-04-29.", BODY), Paragraph("Deadlines", H2),
             table(rows, [2.5 * base.inch, 2.5 * base.inch])]
    filler(story)
    build_pdf(HERE / "e_ece230_formats.pdf", story)
    return course("ECE 230", d(2027, 1, 12), d(2027, 4, 29), [("lecture", ["Tue", "Thu"], "08:30", "09:50")], items,
                  category="formats")


# --- relative --------------------------------------------------------------------------------------
def mth132():
    weeks = [d(2027, 1, 11) + timedelta(weeks=w) for w in range(16)]  # Mondays; week 9 is spring break
    hw_weeks = [w for w in range(1, 15) if w != 8]  # weeks 2..15, not spring break
    hw = [weeks[w] + timedelta(days=2) for w in hw_weeks]
    quiz_weeks = [2, 5, 10, 13]
    quizzes = [weeks[w] + timedelta(days=3) for w in quiz_weeks]
    # the table gives only the week and a weekday: the date must be worked out ("derived" = which weekday)
    items = [{**item(f"HW {i}", "assignment", x, "23:59"), "derived": "Wed"} for i, x in enumerate(hw, 1)]
    items += [{**item(f"Quiz {i}", "quiz", x, "10:20", "11:10"), "derived": "Thu"} for i, x in enumerate(quizzes, 1)]
    items += [item("Exam 1", "exam", d(2027, 2, 23), "19:00", "20:30"), item("Exam 2", "exam", d(2027, 4, 6), "19:00", "20:30"),
              item("Final exam", "exam", d(2027, 5, 3), "07:45", "09:45")]
    rows = [["Week", "Week of", "Due (HW by 11:59 PM)"]]
    for w, mon in enumerate(weeks):
        due = [f"HW {hw_weeks.index(w) + 1} (Wed)"] if w in hw_weeks else []
        due += [f"Quiz {quiz_weeks.index(w) + 1} (Thu, recitation)"] if w in quiz_weeks else []
        rows.append([str(w + 1), md(mon), "Spring break" if w == 8 else (", ".join(due) or "-")])
    story = [Paragraph("MTH 132: Calculus I - Spring 2027", H1),
             Paragraph("Lecture MWF 10:20-11:10 AM; recitation Thursday 10:20-11:10 AM. Exam 1: Tuesday, February 23, "
                       "7:00-8:30 PM. Exam 2: Tuesday, April 6, 7:00-8:30 PM. Final: Monday, May 3, 7:45-9:45 AM.", BODY),
             Paragraph("Weekly schedule (the day in brackets is the day of that week)", H2), table(rows, [0.6 * base.inch, 1 * base.inch, 4 * base.inch])]
    filler(story)
    build_pdf(HERE / "e_mth132_weeks.pdf", story)
    return course("MTH 132", d(2027, 1, 11), d(2027, 4, 30),
                  [("lecture", ["Mon", "Wed", "Fri"], "10:20", "11:10"), ("recitation", ["Thu"], "10:20", "11:10")], items,
                  category="relative")


def phl130():
    week = lambda n: d(2027, 1, 11) + timedelta(weeks=n - 1 + (1 if n >= 9 else 0))  # noqa: E731  (spring break after week 8)
    journals = [week(n) + timedelta(days=6) for n in (2, 5, 7, 11, 13)]
    items = [{**item("Paper 1", "assignment", week(4) + timedelta(days=4), "17:00"), "derived": "Fri"},
             {**item("Paper 2", "assignment", week(10) + timedelta(days=4), "17:00"), "derived": "Fri"}]
    items += [{**item(f"Reflection journal {i}", "assignment", x, "23:59"), "derived": "Sun"} for i, x in enumerate(journals, 1)]
    items += [{**item("Midterm", "exam", week(7) + timedelta(days=2), "15:00", "16:20"), "derived": "Wed"},
              {**item("Final paper", "assignment", week(16) + timedelta(days=2), "15:00"), "derived": "Wed"}]
    story = [Paragraph("PHL 130: Introduction to Ethics", H1),
             Paragraph("Spring 2027. Monday and Wednesday, 3:00-4:20 PM. Week 1 begins Monday, January 11, 2027. Spring "
                       "break is the week after Week 8, so Week 9 begins on March 15.", BODY),
             Paragraph("Deadlines", H2),
             Paragraph("Paper 1 is due Friday of Week 4 by 5 PM. Paper 2 is due Friday of Week 10 by 5 PM.", BODY),
             Paragraph("Short reflection journals are due by 11:59 PM on the Sunday at the end of Weeks 2, 5, 7, 11 and 13.", BODY),
             Paragraph("The midterm is in class on Wednesday of Week 7. The final paper is due at the start of our last class "
                       "meeting, Wednesday of Week 16.", BODY)]
    filler(story)
    build_pdf(HERE / "e_phl130_relative.pdf", story)
    return course("PHL 130", d(2027, 1, 11), d(2027, 4, 28), [("lecture", ["Mon", "Wed"], "15:00", "16:20")], items,
                  category="relative")


# --- distractors -----------------------------------------------------------------------------------
def anth101():
    notes = [d(2027, 2, 1), d(2027, 2, 22), d(2027, 3, 22), d(2027, 4, 12)]
    items = [item(f"Field notes {i}", "assignment", x, "09:00") for i, x in enumerate(notes, 1)]
    items += [item("Midterm", "exam", d(2027, 3, 3), "12:40", "14:00"), item("Final project", "project", d(2027, 4, 30), "23:59")]
    story = [Paragraph("ANTH 101: Introduction to Anthropology", H1),
             Paragraph("Spring 2027 - Revised August 12, 2026 (replaces the Fall 2025 version)", SMALL),
             Paragraph("Class meets Monday and Wednesday, 12:40-2:00 PM. Office hours: Thursdays 2:00-3:30 PM. No class on "
                       "Monday, January 18 (Martin Luther King Jr. Day). Last day to drop with a full refund: January 29.", BODY),
             Paragraph("Assignments", H2),
             Paragraph("Field notes are due at 9:00 AM on " + ", ".join(f"{x:%B} {x.day}" for x in notes) + ". The midterm "
                       "is in class on Wednesday, March 3. The final project is due Friday, April 30 at 11:59 PM.", BODY),
             Paragraph("Still to be announced: a guest speaker (date TBA) and the final exam (date and time TBA; check the "
                       "university's finals schedule). These dates are tentative and may change.", BODY)]
    filler(story)
    build_pdf(HERE / "e_anth101_distractors.pdf", story)
    return course("ANTH 101", d(2027, 1, 11), d(2027, 4, 30), [("lecture", ["Mon", "Wed"], "12:40", "14:00")], items,
                  category="distractors")


def acc201():
    quizzes = every(d(2027, 1, 15), d(2027, 4, 23), skip=SPRING_BREAK)
    items = [{**item(f"Weekly quiz {i}", "quiz", x, "23:59"), "derived": "Fri"} for i, x in enumerate(quizzes, 1)]
    items += [item("Exam 1", "exam", d(2027, 2, 11), "18:00", "19:30"), item("Exam 2", "exam", d(2027, 4, 1), "18:00", "19:30"),
              item("Final exam", "exam", d(2027, 5, 6), "12:45", "14:45")]
    story = [Paragraph("ACC 201: Principles of Financial Accounting", H1),
             Paragraph("Spring 2027 - Tuesday/Thursday 10:20-11:40 AM", BODY),
             Paragraph("Weekly quizzes are due every Friday at 11:59 PM on D2L, from January 15 through April 23, except "
                       "during spring break (March 8-12).", BODY),
             Paragraph("Exam 1: Thursday, February 11, 6:00-7:30 PM. Exam 2: Thursday, April 1, 6:00-7:30 PM. Final exam: "
                       "Thursday, May 6, 12:45-2:45 PM.", BODY)]
    filler(story)
    build_pdf(HERE / "e_acc201_every.pdf", story)
    return course("ACC 201", d(2027, 1, 12), d(2027, 4, 29), [("lecture", ["Tue", "Thu"], "10:20", "11:40")], items,
                  category="distractors")


# --- long ------------------------------------------------------------------------------------------
def bs162():
    quizzes = every(d(2027, 1, 25), d(2027, 4, 26), skip=SPRING_BREAK)
    items = [item(f"Pre-lecture quiz {i}", "quiz", x, "08:00") for i, x in enumerate(quizzes, 1)]
    items += [item("Exam 1", "exam", d(2027, 2, 17), "08:00", "08:50"), item("Exam 2", "exam", d(2027, 3, 31), "08:00", "08:50"),
              item("Final exam", "exam", d(2027, 5, 4), "10:00", "12:00")]
    rows = [["Date", "Topic", "Due before class (8:00 AM)"]]
    day, n = d(2027, 1, 11), 0
    while day <= d(2027, 4, 30):
        if day.weekday() in (0, 2, 4) and not (SPRING_BREAK[0] <= day <= SPRING_BREAK[1]):
            n += 1
            due = [f"Pre-lecture quiz {quizzes.index(day) + 1}"] if day in quizzes else []
            due += ["EXAM 1 (in class)"] if day == d(2027, 2, 17) else []
            due += ["EXAM 2 (in class)"] if day == d(2027, 3, 31) else []
            rows.append([f"{day:%a} {md(day)}", Paragraph(f"Lecture {n}", SMALL), Paragraph(", ".join(due) or "-", SMALL)])
        day += timedelta(days=1)
    story = [Paragraph("BS 162: Organismal and Population Biology", H1), Paragraph("Spring 2027", BODY),
             Paragraph("Lectures MWF 8:00-8:50 AM in 100 Natural Science. The final exam is Tuesday, May 4, 10:00 AM-12:00 PM.", BODY)]
    filler(story, pages=3)
    story += [PageBreak(), Paragraph("Daily schedule", H2), table(rows, [1.0 * base.inch, 2.2 * base.inch, 3.3 * base.inch])]
    build_pdf(HERE / "e_bs162_long.pdf", story)
    return course("BS 162", d(2027, 1, 11), d(2027, 4, 30), [("lecture", ["Mon", "Wed", "Fri"], "08:00", "08:50")], items,
                  category="long")


def cem251():
    ps = [d(2027, 1, 25), d(2027, 2, 8), d(2027, 2, 22), d(2027, 3, 22), d(2027, 4, 5), d(2027, 4, 19)]
    items = [item(f"Problem set {i}", "assignment", x, "23:59") for i, x in enumerate(ps, 1)]
    items += [item("Exam 1", "exam", d(2027, 2, 18), "12:40", "14:00"), item("Exam 2", "exam", d(2027, 4, 8), "12:40", "14:00"),
              item("Final exam", "exam", d(2027, 5, 4), "07:45", "09:45")]
    story = [Paragraph("CEM 251: Organic Chemistry I", H1),
             Paragraph("Spring 2027. Lectures Tuesday and Thursday, 12:40-2:00 PM.", BODY)]
    filler(story)
    story += [Paragraph("Problem sets", H2),
              Paragraph(f"The first two problem sets are due on {long(ps[0])} and {long(ps[1])}, at 11:59 PM.", BODY)]
    filler(story)
    story += [Paragraph("Exams", H2), Paragraph(f"Exam 1 is in class on {long(d(2027, 2, 18))}.", BODY),
              Paragraph(f"Problem sets 3 and 4 are due {long(ps[2])} and {long(ps[3])} (11:59 PM).", BODY)]
    filler(story)
    story += [Paragraph(f"Exam 2 is in class on {long(d(2027, 4, 8))}. The last two problem sets are due {long(ps[4])} and "
                        f"{long(ps[5])}, 11:59 PM. The final exam is {long(d(2027, 5, 4))}, 7:45-9:45 AM.", BODY)]
    build_pdf(HERE / "e_cem251_long.pdf", story)
    return course("CEM 251", d(2027, 1, 12), d(2027, 4, 29), [("lecture", ["Tue", "Thu"], "12:40", "14:00")], items,
                  category="long")


# --- meetings --------------------------------------------------------------------------------------
def phy231():
    hw = [d(2027, 1, 19), d(2027, 2, 2), d(2027, 2, 16), d(2027, 3, 2), d(2027, 3, 23), d(2027, 4, 6), d(2027, 4, 20), d(2027, 4, 27)]
    items = [item(f"HW {i}", "assignment", x, "21:00") for i, x in enumerate(hw, 1)]
    items += [item("Exam 1", "exam", d(2027, 2, 25), "13:00", "14:50"), item("Exam 2", "exam", d(2027, 4, 15), "13:00", "14:50"),
              item("Final exam", "exam", d(2027, 5, 5), "10:00", "12:00")]
    story = [Paragraph("PHY 231: Introductory Physics I", H1), Paragraph("Spring 2027", BODY),
             table([["Lecture", "Mon, Wed, Fri 9:10-10:00 AM"], ["Recitation", "Tuesday 3:00-3:50 PM"], ["Lab", "Thursday 1:00-2:50 PM"]],
                   [1.3 * base.inch, 4 * base.inch]),
             Paragraph("Homework is due Tuesdays at 9:00 PM on these dates: " + ", ".join(md(x) for x in hw) + ".", BODY),
             Paragraph("Exams 1 and 2 are given during the lab period (Thursday 2/25 and Thursday 4/15). The final exam is "
                       "Wednesday, May 5, 10:00 AM-12:00 PM.", BODY)]
    filler(story)
    build_pdf(HERE / "e_phy231_meetings.pdf", story)
    return course("PHY 231", d(2027, 1, 11), d(2027, 4, 30),
                  [("lecture", ["Mon", "Wed", "Fri"], "09:10", "10:00"), ("recitation", ["Tue"], "15:00", "15:50"),
                   ("lab", ["Thu"], "13:00", "14:50")], items, category="meetings")


# --- hard photos (the same content as existing syllabi) ----------------------------------------------
def hard_photos(truth: dict) -> dict:
    _, mth_pdf = base.mth234()
    _, phy_pdf = base.phy183()
    mth_page = render(mth_pdf, dpi=200)[0]
    phy_pages = render(phy_pdf, dpi=200)
    random.seed(7)
    made = {}
    base.photo(mth_page).rotate(90, expand=True).save(HERE / "v_mth234_sideways.jpg", quality=72)
    made["v_mth234_sideways.jpg"] = "c_mth234_photo.jpg"
    low = base.photo(phy_pages[0])
    low.thumbnail((650, 650))
    low.save(HERE / "v_phy183_lowres.jpg", quality=65)
    made["v_phy183_lowres.jpg"] = "d_phy183_scan.pdf"
    dark = ImageEnhance.Contrast(ImageEnhance.Brightness(base.photo(mth_page)).enhance(0.45)).enhance(0.6)
    dark.save(HERE / "v_mth234_dark.jpg", quality=70)
    made["v_mth234_dark.jpg"] = "c_mth234_photo.jpg"
    page = phy_pages[0]
    page.crop((int(page.width * 0.05), int(page.height * 0.04), int(page.width * 0.97), page.height)).save(io.BytesIO(), "PNG")
    base.photo(page.crop((int(page.width * 0.05), int(page.height * 0.03), int(page.width * 0.96), int(page.height * 0.9)))).save(
        HERE / "v_phy183_cropped.jpg", quality=72)
    made["v_phy183_cropped.jpg"] = "d_phy183_scan.pdf"
    spread = Image.new("RGB", (phy_pages[0].width * 2 + 40, phy_pages[0].height), "white")
    spread.paste(phy_pages[0], (0, 0))
    spread.paste(phy_pages[1], (phy_pages[0].width + 40, 0))
    base.photo(spread).save(HERE / "v_phy183_two_pages.jpg", quality=72)
    made["v_phy183_two_pages.jpg"] = "d_phy183_scan.pdf"
    return {name: {**truth[source], "category": "hard photos"} for name, source in made.items()}


if __name__ == "__main__":
    truth = json.loads((HERE / "truth.json").read_text())
    truth = {k: v for k, v in truth.items() if not k.startswith(("e_", "v_"))}  # rebuild the extras from scratch
    for name in truth:
        truth[name].setdefault("category", "photo" if name.endswith(".jpg") else "scan" if "scan" in name else "digital")
    new = {f: build() for f, build in [
        ("e_hst201_fall.pdf", hst201), ("e_cse335_fall.pdf", cse335), ("e_stt231_summer.pdf", stt231),
        ("e_iss215_online.pdf", iss215), ("e_psy101_formats.pdf", psy101), ("e_ece230_formats.pdf", ece230),
        ("e_mth132_weeks.pdf", mth132), ("e_phl130_relative.pdf", phl130), ("e_anth101_distractors.pdf", anth101),
        ("e_acc201_every.pdf", acc201), ("e_bs162_long.pdf", bs162), ("e_cem251_long.pdf", cem251),
        ("e_phy231_meetings.pdf", phy231)]}
    new.update(hard_photos(truth))
    truth.update(new)
    (HERE / "truth.json").write_text(json.dumps(truth, indent=2))
    for name, t in new.items():
        print(f"{name:<28} {t['category']:<16} {len(t['items']):>2} items, {len(t['meetings'])} meetings")
    print(f"total: {len(truth)} syllabi, {sum(len(t['items']) for t in truth.values())} dated items")
