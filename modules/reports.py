"""Reports: charts, summary paragraph, report page, PDF and Excel export.

Plain functions only. Room data is a dictionary:
    room_counts = {"CPE LAB 1": {"Working": 20, "Defective": 5, "Needs Maintenance": 5}, ...}

Speed: charts are drawn with matplotlib's Figure (no pyplot); the PNGs, PDF and
Excel files are cached with st.cache_data, the room pies and the all-rooms bar
chart are drawn once at app start (warm_charts), and the report page is a fragment, so ticking a room
reruns only the page instead of the whole app.
"""
import io
from datetime import datetime
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from assets.database import database as db
from modules import (LOGO_MARK_LIGHT, ROOMS, STATUSES, STATUS_COLORS,
                     SUBTITLE, count_by)

SUMMARY_COLUMNS = ["Room", "Working", "Defective", "Needs Maintenance", "Total"]
EQUIPMENT_COLUMNS = ["pc_code", "cpu", "ram_gb", "storage", "gpu", "os",
                     "monitor", "status", "last_updated"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
cached = st.cache_data(show_spinner=False, max_entries=16)


# -- DATA HELPERS
def total_of(counts):
    """Add up the three statuses of one room."""
    return sum(counts[status] for status in STATUSES)


def percent(part, whole):
    """part / whole as a percentage with 1 decimal (0 when whole is 0)."""
    return round(part * 100 / whole, 1) if whole else 0.0


def pc_text(number):
    """'1 PC' or '5 PCs'."""
    return "1 PC" if number == 1 else f"{number} PCs"


def build_summary_rows(room_counts):
    """One row (dictionary) per room for the summary table."""
    return [{"Room": room, **{s: counts[s] for s in STATUSES},
             "Total": total_of(counts)} for room, counts in room_counts.items()]


# -- CHARTS  (each returns PNG bytes)
def figure_png(figure, **options):
    """Matplotlib Figure -> PNG bytes."""
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", **options)
    return buffer.getvalue()


@cached
def pie_png(room, counts):
    """Pie chart of one room's status split ('No equipment' when empty).

    Only the statuses that have at least one PC are drawn.
    """
    labels = [s for s in STATUSES if counts[s] > 0]
    sizes = [counts[s] for s in labels]
    total = sum(sizes)

    figure = Figure(figsize=(4, 4))
    axis = figure.subplots()
    if total == 0:
        axis.text(0.5, 0.5, "No equipment", ha="center", va="center")
        axis.axis("off")
    else:
        axis.pie(sizes, labels=labels, colors=[STATUS_COLORS[s] for s in labels],
                 autopct=lambda pct: f"{pct:.1f}%\n({round(pct * total / 100)})",
                 startangle=90, wedgeprops={"edgecolor": "white"},
                 textprops={"fontsize": 9})
    axis.set_title(f"{room} ({total} PCs)", fontweight="bold")
    figure.tight_layout()
    return figure_png(figure, dpi=140, bbox_inches="tight")


@cached
def bar_png(room_counts, for_pdf=False):
    """ONE bar chart: each room is a group of three bars (one per status).

    Steps:
      1. For each status, bar position = room number + offset, height = count.
      2. Draw the bars with their values on top.
      3. Name the groups with the rooms; add legend, title and labels.
    The picture keeps a fixed shape (no cropping), so it also fits the PDF slot.
    """
    rooms = list(room_counts)
    width = 0.28
    figure = Figure(figsize=(8, 4.5))
    axis = figure.subplots()
    tallest = 0
    for number, status in enumerate(STATUSES):
        heights = [room_counts[room][status] for room in rooms]
        tallest = max(tallest, *heights)
        bars = axis.bar([i + (number - 1) * width for i in range(len(rooms))],
                        heights, width=width, color=STATUS_COLORS[status],
                        label=status)
        axis.bar_label(bars, padding=2, fontsize=9)

    axis.set_xticks(range(len(rooms)))
    axis.set_xticklabels(rooms)
    axis.set_ylim(0, tallest * 1.15 + 1)
    axis.yaxis.set_major_locator(MaxNLocator(integer=True))
    axis.set_ylabel("Number of PCs")
    axis.set_title("Equipment Status per Laboratory Room", fontweight="bold")
    axis.legend()
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    return figure_png(figure, dpi=180 if for_pdf else 110)


def warm_charts():
    """Draw the pie of every room and the all-rooms bar chart once (called by main.setup).

    These are the first pictures an admin opens (the Equipment room tabs and
    the Reports page), so they are already cached instead of being drawn
    while the admin waits. Other room combinations are drawn when first used.
    """
    all_counts = {room: count_by(db.get_equipment_by_room(room), "status", STATUSES)
                  for room in ROOMS}
    for room, counts in all_counts.items():
        pie_png(room, counts)
    bar_png(all_counts)


# -- SUMMARY PARAGRAPH
def build_summary_paragraph(room_counts, now):
    """One paragraph explaining the numbers (intro, overall, compare, action).

    Steps:
      1. Sum the statuses across rooms; stop early when there are no PCs.
      2. Intro: date, room count and total PCs.
      3. Overall: working / defective / needs-maintenance rates and condition.
      4. Compare: best vs weakest room (skipped when fewer than two rooms).
      5. Action: what to repair or service next.
    """
    totals = {s: sum(c[s] for c in room_counts.values()) for s in STATUSES}
    total = sum(totals.values())
    if total == 0:
        return "No equipment records are available for the selected rooms."

    working, defective = totals["Working"], totals["Defective"]
    maintenance = totals["Needs Maintenance"]
    rate = percent(working, total)
    condition = ("good condition" if rate >= 80 else
                 "fair condition" if rate >= 60 else
                 "poor condition that needs urgent attention")

    count = len(room_counts)
    word = "room" if count == 1 else "rooms"
    intro = (f"As of {now:%B %d, %Y}, this report covers {count} laboratory "
             f"{word} ({', '.join(room_counts)}) with {pc_text(total)} in total.")
    overall = (f"Overall, working: {working} ({rate}%), "
               f"defective: {defective} ({percent(defective, total)}%), "
               f"needs maintenance: {maintenance} ({percent(maintenance, total)}%), "
               f"which puts the equipment in {condition}.")

    rates = {room: percent(c["Working"], total_of(c))
             for room, c in room_counts.items() if total_of(c) > 0}
    if len(rates) < 2:
        compare = ""
    else:
        best, worst = max(rates, key=rates.get), min(rates, key=rates.get)
        compare = (f"All rooms have the same working rate of {rates[best]}%."
                   if rates[best] == rates[worst] else
                   f"{best} has the highest working rate at {rates[best]}%, "
                   f"while {worst} has the lowest at {rates[worst]}%.")

    not_usable = defective + maintenance
    worst_room = max(room_counts, key=lambda r: room_counts[r]["Defective"])
    if not_usable == 0:
        action = "Every PC is working, so only routine inspections are needed."
    elif defective > 0 and maintenance > 0:
        action = (f"{pc_text(not_usable)} ({percent(not_usable, total)}%) in total "
                  f"are not fully usable, so repairs should be prioritized for the "
                  f"{defective} defective units, starting with {worst_room}, "
                  f"followed by scheduled maintenance for the {maintenance} "
                  f"flagged units.")
    elif defective > 0:
        action = (f"Defective: {pc_text(defective)}. These need repair or "
                  f"replacement, starting with {worst_room}.")
    else:
        action = (f"Flagged for maintenance: {pc_text(maintenance)}. These should "
                  f"be serviced soon before they become defective.")

    return " ".join(s for s in (intro, overall, compare, action) if s)


# -- EXPORT: PDF
def make_pdf_header(styles):
    """Logo (left) and university name + system subtitle (right)."""
    logo = Image(LOGO_MARK_LIGHT, width=1.3 * inch, height=1.12 * inch)
    text = [Paragraph("Batangas State University", styles["Heading3"]),
            Paragraph("The National Engineering University", styles["Normal"]),
            Paragraph("Computer Engineering Faculty", styles["Normal"]),
            Paragraph(f"<b>{SUBTITLE.upper()}</b>", styles["Normal"])]
    header = Table([[logo, text]], colWidths=[1.5 * inch, 4.7 * inch])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return header


HEADER_STYLE = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]


def pdf_top(styles, title, admin_name, now):
    """Top of every PDF: header, report title and the 'Generated by' line."""
    # escape() keeps names such as "A & B" from breaking the PDF text
    return [make_pdf_header(styles), Spacer(1, 8), Paragraph(title, styles["Title"]),
            Paragraph(f"Generated by {escape(admin_name)} on "
                      f"{now:%B %d, %Y %I:%M %p}", styles["Normal"])]


def pdf_bytes(story, **page):
    """Build a PDF from a list of flowables; `page` = SimpleDocTemplate options."""
    output = io.BytesIO()
    SimpleDocTemplate(output, **page).build(story)
    return output.getvalue()


def make_pdf_table(room_counts):
    """The Room / Working / Defective / Needs Maintenance / Total table."""
    data = [SUMMARY_COLUMNS] + [list(row.values())
                                for row in build_summary_rows(room_counts)]
    table = Table(data, colWidths=[1.6 * inch, 1 * inch, 1 * inch,
                                   1.6 * inch, 0.9 * inch])
    table.setStyle(TableStyle(HEADER_STYLE
                              + [("ALIGN", (1, 0), (-1, -1), "CENTER")]))
    return table


@cached
def build_pdf(room_counts, admin_name, now):
    """Create the PDF report and return its bytes.

    Page order: header -> title -> bar chart -> table -> summary.
    """
    styles = getSampleStyleSheet()
    chart = Image(io.BytesIO(bar_png(room_counts, True)),
                  width=6.4 * inch, height=3.6 * inch)
    return pdf_bytes([
        *pdf_top(styles, "Project C.L.A.U.S. - Equipment Status Report",
                 admin_name, now),
        Spacer(1, 12), chart, Spacer(1, 10),
        make_pdf_table(room_counts), Spacer(1, 14),
        Paragraph("Summary", styles["Heading2"]),
        Paragraph(escape(build_summary_paragraph(room_counts, now)),
                  styles["BodyText"])],
        pagesize=A4, topMargin=0.6 * inch, bottomMargin=0.6 * inch)


# -- EXPORT: EXCEL
def style_sheet(sheet):
    """Bold white header on dark fill, and fit each column's width."""
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="333333")
    for column in sheet.columns:
        longest = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = longest + 3


def excel_bytes(sheets, finish):
    """{sheet name: DataFrame} -> styled Excel bytes.

    `finish(summary_sheet)` writes the extra text under the Summary table.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
        for sheet in writer.book.worksheets:
            style_sheet(sheet)
        finish(writer.sheets["Summary"])
    return output.getvalue()


def add_summary_text(sheet, row_count, paragraph):
    """Write the summary paragraph under the summary table."""
    text_row = row_count + 4
    sheet.cell(row=row_count + 3, column=1, value="Summary").font = Font(bold=True)
    sheet.merge_cells(start_row=text_row, start_column=1,
                      end_row=text_row, end_column=5)
    cell = sheet.cell(row=text_row, column=1, value=paragraph)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.row_dimensions[text_row].height = 120


@cached
def build_excel(room_counts, records, now):
    """Excel file: Summary sheet + one sheet per room. Returns bytes.

    `records` = {room: list of PC dictionaries}. A room without PCs still
    gets a sheet (headers only).
    """
    summary_rows = build_summary_rows(room_counts)
    paragraph = build_summary_paragraph(room_counts, now)
    return excel_bytes(
        {"Summary": pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS),
         **{room: pd.DataFrame(rows, columns=EQUIPMENT_COLUMNS)
            for room, rows in records.items()}},
        lambda sheet: add_summary_text(sheet, len(summary_rows), paragraph))


# -- PAGE
def show_pdf_excel_pair(pdf, excel):
    """Two side-by-side download buttons (PDF primary, Excel secondary).

    Each argument is (label, build_function, file_name,
    (username, action, details)). The file is only built when the button is
    clicked; the click is written to the audit log.
    """
    for column, (label, build, name, log), mime, kind in zip(
            st.columns(2), (pdf, excel), ("application/pdf", XLSX_MIME),
            ("primary", "secondary")):
        column.download_button(
            label, build, name, mime, width="stretch", type=kind,
            on_click=db.add_audit_log, args=log[:2],
            kwargs={"details": log[2]})


def show_downloads(room_counts, records, chosen_rooms, user, now):
    """PDF and Excel download buttons for the equipment report."""
    stamp = f"{now:%Y%m%d_%H%M}"
    details = "Rooms: " + ", ".join(chosen_rooms)
    show_pdf_excel_pair(
        ("⬇️ Download PDF report",
         lambda: build_pdf(room_counts, user["full_name"], now),
         f"CLAUS_report_{stamp}.pdf",
         (user["username"], "EXPORT_PDF", details)),
        ("⬇️ Download Excel records",
         lambda: build_excel(room_counts, records, now),
         f"CLAUS_equipment_{stamp}.xlsx",
         (user["username"], "EXPORT_EXCEL", details)))


@st.fragment
def render(user):
    """Draw the Reports page (a fragment: ticking a room reruns only this page).

    Steps:
      1. Admin picks the rooms to include.
      2. Read their PCs and count the statuses.
      3. Show bar chart, summary table and paragraph.
      4. Show the PDF / Excel download buttons.
    """
    st.subheader("📊 Equipment Summary")
    chosen_rooms = st.multiselect("Rooms included (remove a room with ✕)",
                                  ROOMS, default=ROOMS)
    if not chosen_rooms:
        st.info("Select at least one room.")
        return

    now = datetime.now().replace(second=0, microsecond=0)
    all_pcs = db.get_all_equipment()
    records = {room: [pc for pc in all_pcs if pc["room"] == room] for room in chosen_rooms}
    room_counts = {room: count_by(rows, "status", STATUSES)
                   for room, rows in records.items()}

    st.image(bar_png(room_counts), width="stretch")
    st.dataframe(pd.DataFrame(build_summary_rows(room_counts)),
                 hide_index=True, width="stretch")

    st.markdown("**Summary**")
    st.info(build_summary_paragraph(room_counts, now))

    st.divider()
    st.markdown("**Export**")
    show_downloads(room_counts, records, chosen_rooms, user, now)
