"""Make the syllabus test set: four made-up Spring 2027 syllabi in the formats students upload,
plus the answer key (truth.json) used to score what a model reads from them.

    a_cse260.pdf        digital PDF, 3 pages, schedule as a table (dates as "1/22")
    b_bs161.pdf         digital PDF, 3 pages, dates inside paragraphs and lists, long policies
    c_mth234_photo.jpg  phone photo of a printed, dense one-page schedule (tilted, shadowed, blurry)
    d_phy183_scan.pdf   scanned PDF, 2 pages, images only (no text layer), slightly crooked

Variants of the same syllabi (same answers), for testing photos and scans more widely:
    a_cse260_scan.pdf, b_bs161_scan.pdf, c_mth234_scan.pdf (scans), d_phy183_photo.jpg (photo of page 1)

The courses and dates are made up; the weekdays are real (Spring 2027 starts Monday, January 11).

    uv run --with reportlab --with pymupdf --with pillow python fixtures/syllabi/make_syllabi.py
    ... make_syllabi.py variants     # only the variants; the original photo and scan stay as they are
"""

import io
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).parent
STYLES = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=STYLES["BodyText"], fontSize=10, leading=13)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.5, leading=10.5)
H1, H2 = STYLES["Title"], STYLES["Heading2"]
LOREM_POLICIES = [
    ("Attendance", "Attendance is expected at every class meeting. If you must miss class for an illness or a "
     "university-sanctioned activity, email the instructor before class when possible. Repeated absences will "
     "make it difficult to succeed in this course, because much of the material is introduced only in class."),
    ("Academic integrity", "Article 2.III.B.2 of the Student Rights and Responsibilities states that the student shares "
     "with the faculty the responsibility for maintaining the integrity of scholarship, grades, and professional "
     "standards. You may discuss ideas with classmates, but the work you submit must be your own. Using AI tools to "
     "write answers you submit is not allowed unless an assignment says otherwise."),
    ("Accommodations", "If you have a documented disability and need accommodations, contact the Resource Center for "
     "Persons with Disabilities (RCPD) and share your Verified Individualized Services and Accommodations (VISA) "
     "form with the instructor within the first two weeks of the semester."),
    ("Late work", "Late work is accepted up to 48 hours after the deadline with a 10% penalty per day. Work more than "
     "48 hours late receives no credit unless an extension was arranged in advance. Technology problems are not an "
     "excuse, so submit early and keep copies of your files."),
    ("Communication", "Announcements are posted on D2L. Check D2L and your MSU email at least once a day. Questions "
     "about the material are best asked in office hours or on the course discussion board, where classmates can "
     "benefit from the answers too."),
]


def d(month: int, day: int) -> date:
    return date(2027, month, day)


def short(x: date) -> str:
    return f"{x.month}/{x.day}"


def long_date(x: date) -> str:
    return f"{x:%A}, {x:%B} {x.day}"


def item(title, kind, when: date, time=None, end=None):
    return {"title": title, "kind": kind, "date": when.isoformat(), "time": time, "end_time": end}


def policies(story, names):
    for name, text in LOREM_POLICIES:
        if name in names:
            story += [Paragraph(name, H2), Paragraph(text, BODY)]


def table(rows, widths, font=9):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", font),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", font),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e2ec")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def build_pdf(path: Path, story) -> None:
    SimpleDocTemplate(str(path), pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                      topMargin=0.7 * inch, bottomMargin=0.7 * inch).build(story)


# --- A: CSE 260, digital PDF with a schedule table --------------------------------------------------
def cse260():
    homework = [d(1, 22), d(1, 29), d(2, 5), d(2, 12), d(2, 26), d(3, 5), d(3, 19), d(4, 2), d(4, 9), d(4, 23)]
    quizzes = [d(2, 3), d(3, 3), d(3, 31), d(4, 21)]
    items = [item(f"Homework {i}", "assignment", x, "23:59") for i, x in enumerate(homework, 1)]
    items += [item(f"Quiz {i}", "quiz", x, "15:00", "15:50") for i, x in enumerate(quizzes, 1)]
    items += [item("Midterm Exam 1", "exam", d(2, 18), "12:40", "14:00"),
              item("Midterm Exam 2", "exam", d(3, 25), "12:40", "14:00"),
              item("Final Exam", "exam", d(5, 4), "10:00", "12:00")]
    truth = {
        "course": "CSE 260", "term_start": "2027-01-11", "term_end": "2027-04-30",
        "meetings": [{"kind": "lecture", "days": ["Tue", "Thu"], "start": "12:40", "end": "14:00"},
                     {"kind": "recitation", "days": ["Wed"], "start": "15:00", "end": "15:50"}],
        "no_class": ["2027-03-08", "2027-03-12"], "items": items,
    }

    topics = ["Logic and proofs", "Predicates, quantifiers", "Sets and functions", "Sequences and sums",
              "Induction", "Strong induction, recursion", "Counting", "Permutations, combinations",
              "SPRING BREAK - no classes", "Discrete probability", "Relations", "Graphs",
              "Trees", "Graph algorithms", "Boolean algebra", "Review"]
    rows = [["Week", "Dates", "Topics", "Due / assessments"]]
    for week, topic in enumerate(topics):
        monday = d(1, 11) + timedelta(weeks=week)
        due = []
        for i, x in enumerate(homework, 1):
            if monday <= x < monday + timedelta(days=7):
                due.append(f"HW {i} (Fri {short(x)})")
        for i, x in enumerate(quizzes, 1):
            if monday <= x < monday + timedelta(days=7):
                due.append(f"Quiz {i} in recitation (Wed {short(x)})")
        if monday <= d(2, 18) < monday + timedelta(days=7):
            due.append("MIDTERM 1 in class (Thu 2/18)")
        if monday <= d(3, 25) < monday + timedelta(days=7):
            due.append("MIDTERM 2 in class (Thu 3/25)")
        rows.append([str(week + 1), f"{short(monday)} - {short(monday + timedelta(days=4))}",
                     Paragraph(topic, SMALL), Paragraph("<br/>".join(due) or "-", SMALL)])
    rows.append(["Finals", "5/3 - 5/7", Paragraph("Final exam (cumulative)", SMALL),
                 Paragraph("FINAL EXAM Tue 5/4, 10:00 AM - 12:00 PM, 1279 Anthony Hall", SMALL)])

    story = [Paragraph("CSE 260: Discrete Structures in Computer Science", H1),
             Paragraph("Spring 2027 - Section 001 - 4 credits", BODY), Spacer(1, 8),
             table([["Instructor", "Dr. Priya Raman (ramanpri@msu.edu)"],
                    ["Lectures", "Tuesday & Thursday, 12:40 - 2:00 PM, 1279 Anthony Hall"],
                    ["Recitation", "Wednesday, 3:00 - 3:50 PM, 1240 Engineering Building"],
                    ["Office hours", "Monday 1:00 - 2:30 PM and by appointment, 3132 Engineering Building"],
                    ["Course site", "D2L (all homework is submitted on D2L)"]], [1.3 * inch, 5.3 * inch]),
             Paragraph("Course description", H2),
             Paragraph("Discrete mathematics for computer science: propositional and predicate logic, proof techniques, "
                       "sets, functions, relations, counting, discrete probability, and graphs. The course emphasizes "
                       "writing clear and correct proofs.", BODY),
             Paragraph("Grading", H2),
             table([["Component", "Weight"], ["Homework (10, lowest dropped)", "25%"], ["Recitation quizzes (4)", "10%"],
                    ["Midterm exams (2)", "40%"], ["Final exam", "25%"]], [3.5 * inch, 1.2 * inch]),
             Paragraph("Homework is due on D2L by 11:59 PM on the Friday it is listed. Quizzes are given during "
                       "recitation. Classes start Monday, January 11, 2027 and end Friday, April 30, 2027. There are no "
                       "classes during spring break, March 8 - 12.", BODY),
             PageBreak()]
    policies(story, {"Attendance", "Academic integrity", "Late work", "Accommodations"})
    story += [PageBreak(), Paragraph("Tentative schedule", H2),
              table(rows, [0.5 * inch, 0.95 * inch, 2.4 * inch, 2.75 * inch])]
    build_pdf(HERE / "a_cse260.pdf", story)
    return truth


# --- B: BS 161, digital PDF with dates in prose -----------------------------------------------------
def bs161():
    quizzes = [d(1, 17), d(1, 24), d(1, 31), d(2, 7), d(2, 21), d(2, 28), d(3, 21), d(3, 28), d(4, 4), d(4, 11)]
    items = [item(f"Online Quiz {i}", "quiz", x, "23:59") for i, x in enumerate(quizzes, 1)]
    items += [item("Exam 1", "exam", d(2, 10), "09:10", "10:00"), item("Exam 2", "exam", d(3, 17), "09:10", "10:00"),
              item("Exam 3", "exam", d(4, 14), "09:10", "10:00"),
              item("Final Exam", "exam", d(5, 3), "07:45", "09:45"),
              item("Research paper topic proposal", "assignment", d(1, 29), "17:00"),
              item("Annotated bibliography", "assignment", d(2, 26), "17:00"),
              item("Final research paper", "assignment", d(4, 23), "17:00"),
              item("Group presentation", "presentation", d(4, 26), "09:10", "10:00")]
    truth = {
        "course": "BS 161", "term_start": "2027-01-11", "term_end": "2027-04-30",
        "meetings": [{"kind": "lecture", "days": ["Mon", "Wed", "Fri"], "start": "09:10", "end": "10:00"}],
        "no_class": ["2027-03-08", "2027-03-12"], "items": items,
        "optional": ["office hours (Tue 2-4 PM)", "drop deadline Feb 3"],
    }
    quiz_list = ", ".join(f"{x:%B} {x.day}" for x in quizzes)
    story = [Paragraph("BS 161 - Cell and Molecular Biology", H1),
             Paragraph("Spring Semester 2027", BODY), Spacer(1, 6),
             Paragraph("<b>Instructor:</b> Dr. Marcus Ellery, 214 Natural Science Building, elleryma@msu.edu. "
                       "<b>Office hours:</b> Tuesdays 2:00-4:00 PM or by appointment.", BODY),
             Paragraph("<b>Class meetings:</b> Lectures meet Monday, Wednesday and Friday from 9:10 to 10:00 AM in "
                       "100 Natural Science. The first lecture is Monday, January 11 and the last is Friday, April 30. "
                       "We do not meet during spring break (March 8-12).", BODY),
             Paragraph("Course goals", H2),
             Paragraph("This course introduces the molecular basis of life: the structure and function of "
                       "macromolecules, membranes, energy flow in cells, the flow of genetic information from DNA to "
                       "protein, and how cells communicate and divide. By the end of the semester you should be able to "
                       "explain how a change in a gene can change the behavior of a cell.", BODY),
             Paragraph("Exams", H2),
             Paragraph(f"There are three midterm exams, each given during the regular lecture period: Exam 1 on "
                       f"{long_date(d(2, 10))}, Exam 2 on {long_date(d(3, 17))}, and Exam 3 on {long_date(d(4, 14))}. "
                       f"The cumulative final exam is on {long_date(d(5, 3))} from 7:45 to 9:45 AM in our usual room. "
                       "Bring a #2 pencil and your student ID to every exam.", BODY),
             Paragraph("Online quizzes", H2),
             Paragraph("Weekly online quizzes on Mastering Biology cover the reading for the coming week. Each quiz is "
                       "due at 11:59 PM on a Sunday. There are no quizzes in exam weeks or during spring break. The quiz "
                       f"due dates are: {quiz_list}. Your lowest quiz score is dropped.", BODY),
             PageBreak(),
             Paragraph("Research paper", H2),
             Paragraph(f"You will write a short research paper on a cellular process of your choice. The paper has "
                       f"three parts. Your topic proposal (one paragraph) is due on D2L by 5:00 PM on "
                       f"{long_date(d(1, 29))}. An annotated bibliography with at least six sources is due by 5:00 PM "
                       f"on {long_date(d(2, 26))}. The final paper (2,000 words) is due by 5:00 PM on "
                       f"{long_date(d(4, 23))}.", BODY),
             Paragraph("Group presentation", H2),
             Paragraph(f"In teams of four, you will give a ten-minute presentation of your research topics during "
                       f"lecture on {long_date(d(4, 26))}. Teams will be assigned in March.", BODY),
             Paragraph("Grading", H2),
             table([["Exams 1-3", "36%"], ["Final exam", "24%"], ["Online quizzes", "15%"], ["Research paper", "18%"],
                    ["Group presentation", "7%"]], [2.5 * inch, 1 * inch]),
             Paragraph("Important university dates", H2),
             Paragraph("The last day to drop the course with a full refund is February 3. The last day to drop with no "
                       "grade reported is March 3.", BODY),
             PageBreak()]
    policies(story, {"Attendance", "Academic integrity", "Accommodations", "Late work", "Communication"})
    build_pdf(HERE / "b_bs161.pdf", story)
    return truth


# --- C: MTH 234, one dense page, photographed ---------------------------------------------------------
def mth234():
    webwork = [d(1, 19) + timedelta(weeks=w) for w in range(15) if w != 7]  # every Tuesday, none in spring break
    items = [item(f"WebWork {i}", "assignment", x, "23:59") for i, x in enumerate(webwork, 1)]
    items += [item("Exam 1", "exam", d(2, 11), "19:00", "20:20"), item("Exam 2", "exam", d(3, 25), "19:00", "20:20"),
              item("Final Exam", "exam", d(5, 5), "12:45", "14:45")]
    truth = {
        "course": "MTH 234", "term_start": "2027-01-11", "term_end": "2027-04-30",
        "meetings": [{"kind": "lecture", "days": ["Mon", "Tue", "Wed", "Fri"], "start": "10:20", "end": "11:10"}],
        "no_class": ["2027-03-08", "2027-03-12"], "items": items,
    }
    sections = ["12.1-12.2", "12.3-12.4", "12.5", "12.6, 13.1", "13.2-13.3", "14.1-14.3", "14.4-14.5",
                "14.6-14.7", "-", "14.8", "15.1-15.3", "15.4-15.6", "15.7-15.9", "16.1-16.3", "16.4-16.6", "16.7-16.8"]
    rows = [["Week of", "Sections", "Due (WebWork by 11:59 PM)", "Exams / notes"]]
    for week, sec in enumerate(sections):
        monday = d(1, 11) + timedelta(weeks=week)
        due = [f"WW{i} Tue {short(x)}" for i, x in enumerate(webwork, 1) if monday <= x < monday + timedelta(days=7)]
        note = ""
        if week == 4:
            note = "EXAM 1 Thu 2/11, 7:00-8:20 PM, 115 Intl Center"
        elif week == 8:
            note = "Spring break, no class"
        elif week == 10:
            note = "EXAM 2 Thu 3/25, 7:00-8:20 PM, 115 Intl Center"
        rows.append([short(monday), sec, ", ".join(due) or "-", note])
    rows.append(["5/3", "Finals", "-", "FINAL EXAM Wed 5/5, 12:45-2:45 PM"])
    story = [Paragraph("MTH 234 Multivariable Calculus - Spring 2027 Schedule", STYLES["Heading1"]),
             Paragraph("Lectures: Mon, Tue, Wed, Fri 10:20-11:10 AM, C304 Wells Hall. Exams are in the evening. "
                       "WebWork is due Tuesdays at 11:59 PM. Classes: Jan 11 - Apr 30.", BODY), Spacer(1, 6),
             table(rows, [0.7 * inch, 1.0 * inch, 2.1 * inch, 3.0 * inch], font=8.5)]
    pdf = io.BytesIO()
    SimpleDocTemplate(pdf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                      topMargin=0.6 * inch, bottomMargin=0.6 * inch).build(story)
    return truth, pdf.getvalue()


# --- D: PHY 183, scanned 2-page PDF -----------------------------------------------------------------
def phy183():
    problem_sets = [d(1, 20), d(2, 3), d(2, 17), d(3, 3), d(3, 24), d(4, 7), d(4, 21)]
    items = [item(f"Problem Set {i}", "assignment", x, "11:30") for i, x in enumerate(problem_sets, 1)]
    items += [item("Midterm 1", "exam", d(2, 22), "11:30", "12:20"), item("Midterm 2", "exam", d(4, 5), "11:30", "12:20"),
              item("Lab practical", "exam", d(4, 22), "15:00", "16:50"),
              item("Final Exam", "exam", d(5, 6), "15:00", "17:00")]
    truth = {
        "course": "PHY 183", "term_start": "2027-01-11", "term_end": "2027-04-30",
        "meetings": [{"kind": "lecture", "days": ["Mon", "Wed", "Fri"], "start": "11:30", "end": "12:20"},
                     {"kind": "lab", "days": ["Thu"], "start": "15:00", "end": "16:50"}],
        "no_class": ["2027-03-08", "2027-03-12"], "items": items,
    }
    ps_rows = [["Problem set", "Due (start of lecture, 11:30 AM)", "Covers"]] + [
        [f"PS {i}", long_date(x), c] for i, (x, c) in enumerate(zip(problem_sets, [
            "Ch. 1-2 kinematics", "Ch. 3-4 vectors, projectiles", "Ch. 5 Newton's laws", "Ch. 6-7 work, energy",
            "Ch. 8-9 momentum", "Ch. 10-11 rotation", "Ch. 12-13 gravity, oscillations"]), 1)]
    story = [Paragraph("PHY 183: Physics for Scientists and Engineers I", H1),
             Paragraph("Spring 2027", BODY), Spacer(1, 6),
             Paragraph("<b>Lecture:</b> MWF 11:30 AM - 12:20 PM, 1415 Biomedical &amp; Physical Sciences. "
                       "<b>Lab:</b> Thursdays 3:00 - 4:50 PM, room 1248 BPS (labs start the second week). "
                       "<b>Instructor:</b> Prof. Hana Okafor. No classes March 8 - 12 (spring break).", BODY),
             Paragraph("Assessments", H2),
             Paragraph(f"Midterm 1 is in lecture on {long_date(d(2, 22))}. Midterm 2 is in lecture on "
                       f"{long_date(d(4, 5))}. The lab practical is during your lab section on {long_date(d(4, 22))}. "
                       f"The final exam is {long_date(d(5, 6))}, 3:00 - 5:00 PM (room TBA).", BODY),
             Paragraph("Problem sets", H2), table(ps_rows, [1.1 * inch, 2.6 * inch, 2.8 * inch]),
             PageBreak()]
    policies(story, {"Attendance", "Academic integrity", "Late work"})
    pdf = io.BytesIO()
    SimpleDocTemplate(pdf, pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                      topMargin=0.7 * inch, bottomMargin=0.7 * inch).build(story)
    return truth, pdf.getvalue()


def render(pdf_bytes: bytes, dpi: int) -> list[Image.Image]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return [Image.open(io.BytesIO(page.get_pixmap(dpi=dpi).tobytes("png"))).convert("RGB") for page in doc]


def photo(page: Image.Image) -> Image.Image:
    """Make a clean page look like a phone photo of a printout on a desk."""
    rng = random.Random(234)
    w, h = page.size
    canvas = Image.new("RGB", (int(w * 1.18), int(h * 1.12)), (92, 74, 60))  # wooden desk
    canvas.paste(page, (int(w * 0.09), int(h * 0.05)))
    canvas = canvas.rotate(3.5, resample=Image.BICUBIC, fillcolor=(92, 74, 60))
    cw, ch = canvas.size
    # perspective: the top edge is a little narrower, as if the phone were tilted
    canvas = canvas.transform(canvas.size, Image.QUAD, (int(cw * 0.04), 0, int(cw * 0.01), ch, cw, ch,
                                                        int(cw * 0.97), int(ch * 0.01)), Image.BICUBIC)
    shadow = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(shadow).ellipse((-cw * 0.4, -ch * 0.2, cw * 0.9, ch * 1.3), fill=255)
    shadow = shadow.filter(ImageFilter.GaussianBlur(cw // 6))
    canvas = Image.composite(canvas, Image.blend(canvas, Image.new("RGB", canvas.size, (30, 25, 20)), 0.45), shadow)
    canvas = canvas.filter(ImageFilter.GaussianBlur(1.1))
    noise = Image.effect_noise(canvas.size, 18).convert("RGB")
    canvas = Image.blend(canvas, noise, 0.06)
    canvas.thumbnail((1600, 1600))
    rng.random()
    return canvas


def scan(page: Image.Image, angle: float) -> Image.Image:
    """Make a clean page look like a slightly crooked office scan."""
    gray = page.convert("L").rotate(angle, resample=Image.BICUBIC, fillcolor=255, expand=False)
    noise = Image.effect_noise(gray.size, 30)
    gray = Image.blend(gray, noise, 0.05).point(lambda v: 255 if v > 200 else v)  # whiten the paper, keep ink
    return gray.convert("RGB")


def save_scan(pdf_bytes: bytes, name: str, angles=(0.9, -0.6, 0.5)) -> None:
    pages = [scan(page, angles[i % len(angles)]) for i, page in enumerate(render(pdf_bytes, dpi=150))]
    pages[0].save(HERE / name, save_all=True, append_images=pages[1:], resolution=150)


if __name__ == "__main__":
    originals = "variants" not in sys.argv[1:]
    a, b = cse260(), bs161()
    (c, c_pdf), (d, d_pdf) = mth234(), phy183()
    if originals:  # their noise is random, so rebuilding them would change the files earlier results used
        photo(render(c_pdf, dpi=200)[0]).save(HERE / "c_mth234_photo.jpg", quality=72)
        save_scan(d_pdf, "d_phy183_scan.pdf")
    save_scan((HERE / "a_cse260.pdf").read_bytes(), "a_cse260_scan.pdf", (-0.7, 0.8, -0.4))
    save_scan((HERE / "b_bs161.pdf").read_bytes(), "b_bs161_scan.pdf", (0.6, -0.9, 0.3))
    save_scan(c_pdf, "c_mth234_scan.pdf", (-1.1,))
    photo(render(d_pdf, dpi=200)[0]).save(HERE / "d_phy183_photo.jpg", quality=72)
    truth = {"a_cse260.pdf": a, "b_bs161.pdf": b, "c_mth234_photo.jpg": c, "d_phy183_scan.pdf": d,
             "a_cse260_scan.pdf": a, "b_bs161_scan.pdf": b, "c_mth234_scan.pdf": c, "d_phy183_photo.jpg": d}
    (HERE / "truth.json").write_text(json.dumps(truth, indent=2))
    for name, t in truth.items():
        print(f"{name}: {len(t['items'])} dated items, {len(t['meetings'])} weekly meetings")
