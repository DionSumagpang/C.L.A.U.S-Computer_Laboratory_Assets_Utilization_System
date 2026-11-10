"""Reports: charts, summary paragraph, report page, PDF and Excel export.

Plain functions only. Room data is a dictionary:
    room_counts = {"CpE Lab 1": {"Working": 20, "Defective": 5,
                                 "Needs Maintenance": 5}, ...}
"""
import io
from datetime import datetime
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd
import streamlit as st
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from assets.database import database as db
from modules import (LOGO_MARK_DARK, ROOMS, STATUSES, STATUS_COLORS,
                     SUBTITLE)

SUMMARY_COLUMNS = ["Room", "Working", "Defective", "Needs Maintenance",
                   "Total"]
EQUIPMENT_COLUMNS = ["pc_code", "cpu", "ram_gb", "storage", "gpu", "os",
                     "monitor", "status", "last_updated"]


# ===========================================================================
# DATA HELPERS
# ===========================================================================
def get_room_counts(rooms):
    """Status counts for each chosen room."""
    room_counts = {}
    for room in rooms:
        room_counts[room] = db.get_status_counts(room)
    return room_counts


def total_of(counts):
    """Add up the three statuses of one room."""
    return sum(counts[status] for status in STATUSES)


def percent(part, whole):
    """part / whole as a percentage with 1 decimal (0 when whole is 0)."""
    if whole == 0:
        return 0.0
    return round(part * 100 / whole, 1)


def pc_text(number):
    """'1 PC' or '5 PCs'."""
    if number == 1:
        return "1 PC"
    return str(number) + " PCs"


def add_up(room_counts):
    """Totals over all rooms: Working, Defective, Needs Maintenance, Total."""
    totals = {status: 0 for status in STATUSES}
    for counts in room_counts.values():
        for status in STATUSES:
            totals[status] += counts[status]
    totals["Total"] = total_of(totals)
    return totals


def build_summary_rows(room_counts):
    """One row (dictionary) per room for the summary table."""
    rows = []
    for room, counts in room_counts.items():
        rows.append({"Room": room, "Working": counts["Working"],
                     "Defective": counts["Defective"],
                     "Needs Maintenance": counts["Needs Maintenance"],
                     "Total": total_of(counts)})
    return rows


# ===========================================================================
# CHARTS
# ===========================================================================
def pie_figure(room, counts):
    """Pie chart of one room's status split.

    Steps:
      1. Keep the statuses that have at least one PC.
      2. No PCs -> write 'No equipment'. Otherwise draw the pie.
    """
    labels, sizes, pie_colors = [], [], []
    for status in STATUSES:
        if counts[status] > 0:
            labels.append(status)
            sizes.append(counts[status])
            pie_colors.append(STATUS_COLORS[status])
    total = sum(sizes)

    figure, axis = plt.subplots(figsize=(4, 4))
    if total == 0:
        axis.text(0.5, 0.5, "No equipment", ha="center", va="center")
        axis.axis("off")
    else:
        def label_maker(pct):
            return f"{pct:.1f}%\n({round(pct * total / 100)})"

        axis.pie(sizes, labels=labels, colors=pie_colors,
                 autopct=label_maker, startangle=90,
                 wedgeprops={"edgecolor": "white"}, textprops={"fontsize": 9})
    axis.set_title(f"{room} ({total} PCs)", fontweight="bold")
    figure.tight_layout()
    return figure


def bar_figure(room_counts):
    """ONE bar chart: each room is a group of three bars (one per status).

    Steps:
      1. For each status, bar position = room number + offset, height = count.
      2. Draw the bars with their values on top.
      3. Name the groups with the rooms; add legend, title and labels.
    """
    rooms = list(room_counts)
    bar_width = 0.28
    tallest = 0

    figure, axis = plt.subplots(figsize=(8, 4.5))
    for status_number, status in enumerate(STATUSES):
        positions = []
        heights = []
        for room_number, room in enumerate(rooms):
            positions.append(room_number + (status_number - 1) * bar_width)
            heights.append(room_counts[room][status])
        tallest = max(tallest, max(heights))

        bars = axis.bar(positions, heights, width=bar_width,
                        color=STATUS_COLORS[status], label=status)
        axis.bar_label(bars, padding=2, fontsize=9)

    axis.set_xticks(range(len(rooms)))
    axis.set_xticklabels(rooms)
    axis.set_ylim(0, tallest * 1.15 + 1)
    axis.yaxis.set_major_locator(MaxNLocator(integer=True))
    axis.set_ylabel("Number of PCs")
    axis.set_title("Equipment Status per Laboratory Room", fontweight="bold")
    axis.legend()
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    figure.tight_layout()
    return figure


def figure_to_png(figure):
    """Matplotlib figure -> PNG bytes (for the PDF). Closes the figure."""
    buffer = io.BytesIO()
    try:
        figure.savefig(buffer, format="png", dpi=180)
    finally:
        plt.close(figure)
    buffer.seek(0)
    return buffer


# ===========================================================================
# SUMMARY PARAGRAPH  (four small sentence builders)
# ===========================================================================
def condition_word(working_rate):
    """Overall working % -> short description."""
    if working_rate >= 80:
        return "good condition"
    if working_rate >= 60:
        return "fair condition"
    return "poor condition that needs urgent attention"


def intro_sentence(room_counts, total_pcs):
    """Sentence 1: date, number of rooms and PCs."""
    count = len(room_counts)
    word = "room" if count == 1 else "rooms"
    names = ", ".join(room_counts)
    return (f"As of {datetime.now():%B %d, %Y}, this report covers {count} "
            f"laboratory {word} ({names}) with {pc_text(total_pcs)} in total.")


def overall_sentence(totals):
    """Sentence 2: overall numbers and condition."""
    total = totals["Total"]
    working = totals["Working"]
    defective = totals["Defective"]
    maintenance = totals["Needs Maintenance"]
    rate = percent(working, total)
    return (f"Overall, working: {working} ({rate}%), "
            f"defective: {defective} ({percent(defective, total)}%), "
            f"needs maintenance: {maintenance} "
            f"({percent(maintenance, total)}%), which puts the equipment in "
            f"{condition_word(rate)}.")


def compare_sentence(room_counts):
    """Sentence 3: best vs. weakest room ('' when fewer than 2 rooms)."""
    rates = {}
    for room, counts in room_counts.items():
        if total_of(counts) > 0:
            rates[room] = percent(counts["Working"], total_of(counts))
    if len(rates) < 2:
        return ""

    best = max(rates, key=rates.get)
    worst = min(rates, key=rates.get)
    if rates[best] == rates[worst]:
        return f"All rooms have the same working rate of {rates[best]}%."
    return (f"{best} has the highest working rate at {rates[best]}%, "
            f"while {worst} has the lowest at {rates[worst]}%.")


def action_sentence(room_counts, totals):
    """Sentence 4: what to do next."""
    defective = totals["Defective"]
    maintenance = totals["Needs Maintenance"]
    not_usable = defective + maintenance
    # room with the most defective PCs (the first one when tied)
    worst_room = max(room_counts, key=lambda r: room_counts[r]["Defective"])

    if not_usable == 0:
        return "Every PC is working, so only routine inspections are needed."
    if defective > 0 and maintenance > 0:
        return (f"{pc_text(not_usable)} "
                f"({percent(not_usable, totals['Total'])}%) in total are not "
                f"fully usable, so repairs should be prioritized for the "
                f"{defective} defective units, starting with {worst_room}, "
                f"followed by scheduled maintenance for the {maintenance} "
                f"flagged units.")
    if defective > 0:
        return (f"Defective: {pc_text(defective)}. These need repair or "
                f"replacement, starting with {worst_room}.")
    return (f"Flagged for maintenance: {pc_text(maintenance)}. These should "
            f"be serviced soon before they become defective.")


def build_summary_paragraph(room_counts):
    """One paragraph explaining the numbers (intro, overall, compare, action)."""
    totals = add_up(room_counts)
    if totals["Total"] == 0:
        return "No equipment records are available for the selected rooms."

    sentences = [intro_sentence(room_counts, totals["Total"]),
                 overall_sentence(totals),
                 compare_sentence(room_counts),
                 action_sentence(room_counts, totals)]
    return " ".join(s for s in sentences if s != "")


# ===========================================================================
# EXPORT: PDF
# ===========================================================================
def make_pdf_header(styles):
    """Logo (left) and university name + system subtitle (right)."""
    logo = Image(LOGO_MARK_DARK, width=1.3 * inch, height=1.12 * inch)
    subtitle_style = styles["Normal"].clone("subtitle", fontName="Helvetica-Bold",
                                            fontSize=10, leading=13)
    text = [Paragraph("Batangas State University", styles["Heading3"]),
            Paragraph("The National Engineering University", styles["Normal"]),
            Paragraph("Computer Engineering Faculty", styles["Normal"]),
            Spacer(1, 4),
            Paragraph(SUBTITLE.upper(), subtitle_style)]
    header = Table([[logo, text]], colWidths=[1.5 * inch, 4.7 * inch])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("BACKGROUND", (0, 0), (0, 0), colors.black)]))
    return header


def make_pdf_table(room_counts):
    """The Room / Working / Defective / Needs Maintenance / Total table."""
    data = [SUMMARY_COLUMNS]
    for row in build_summary_rows(room_counts):
        data.append([row[column] for column in SUMMARY_COLUMNS])
    table = Table(data, colWidths=[1.6 * inch, 1 * inch, 1 * inch,
                                   1.6 * inch, 0.9 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))
    return table


def build_pdf(room_counts, admin_name):
    """Create the PDF report and return its bytes.

    Page order: header -> title -> bar chart -> table -> summary.
    """
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, topMargin=0.6 * inch,
                                 bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()

    chart = Image(figure_to_png(bar_figure(room_counts)),
                  width=6.4 * inch, height=3.6 * inch)
    # escape() keeps names such as "A & B" from breaking the PDF text
    generated = (f"Generated by {escape(admin_name)} on "
                 f"{datetime.now():%B %d, %Y %I:%M %p}")

    story = [make_pdf_header(styles), Spacer(1, 8),
             Paragraph("Project C.L.A.U.S. - Equipment Status Report",
                       styles["Title"]),
             Paragraph(generated, styles["Normal"]),
             Spacer(1, 12), chart, Spacer(1, 10),
             make_pdf_table(room_counts), Spacer(1, 14),
             Paragraph("Summary", styles["Heading2"]),
             Paragraph(escape(build_summary_paragraph(room_counts)),
                       styles["BodyText"])]
    document.build(story)
    return output.getvalue()


# ===========================================================================
# EXPORT: EXCEL
# ===========================================================================
def style_sheet(sheet):
    """Bold white header on dark fill, and fit each column's width."""
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="333333")
    for column in sheet.columns:
        longest = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = longest + 3


def add_summary_text(sheet, row_count, paragraph):
    """Write the summary paragraph under the summary table."""
    title_row = row_count + 3
    text_row = row_count + 4
    sheet.cell(row=title_row, column=1, value="Summary").font = Font(bold=True)
    sheet.merge_cells(start_row=text_row, start_column=1,
                      end_row=text_row, end_column=5)
    cell = sheet.cell(row=text_row, column=1, value=paragraph)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.row_dimensions[text_row].height = 120


def build_excel(room_counts):
    """Excel file: Summary sheet + one sheet per room. Returns bytes.

    A room without PCs still gets a sheet (headers only).
    """
    output = io.BytesIO()
    summary_rows = build_summary_rows(room_counts)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS).to_excel(
            writer, sheet_name="Summary", index=False)
        for room in room_counts:
            records = pd.DataFrame(db.get_equipment_by_room(room),
                                   columns=EQUIPMENT_COLUMNS)
            records.to_excel(writer, sheet_name=room, index=False)

        for sheet in writer.book.worksheets:
            style_sheet(sheet)
        add_summary_text(writer.sheets["Summary"], len(summary_rows),
                         build_summary_paragraph(room_counts))
    return output.getvalue()


# ===========================================================================
# PAGE
# ===========================================================================
def log_export(username, kind, rooms):
    """Runs when a download button is clicked -> audit log."""
    db.add_audit_log(username, "EXPORT_" + kind, "", "",
                     "Rooms: " + ", ".join(rooms))


def show_downloads(room_counts, chosen_rooms, user):
    """PDF and Excel download buttons. A failed export shows a message
    instead of crashing the page."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    col_pdf, col_excel = st.columns(2)

    try:
        pdf_bytes = build_pdf(room_counts, user["full_name"])
        col_pdf.download_button(
            "⬇️ Download PDF report", pdf_bytes,
            f"CLAUS_report_{stamp}.pdf", "application/pdf",
            width="stretch", type="primary",
            on_click=log_export, args=(user["username"], "PDF", chosen_rooms))
    except Exception as error:
        col_pdf.error("Could not create the PDF: " + str(error))

    try:
        excel_bytes = build_excel(room_counts)
        col_excel.download_button(
            "⬇️ Download Excel records", excel_bytes,
            f"CLAUS_equipment_{stamp}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            on_click=log_export, args=(user["username"], "EXCEL", chosen_rooms))
    except Exception as error:
        col_excel.error("Could not create the Excel file: " + str(error))


def render(user):
    """Draw the Reports page.

    Steps:
      1. Admin picks the rooms to include.
      2. Read their status counts.
      3. Show bar chart, summary table and paragraph.
      4. Show the PDF / Excel download buttons.
    """
    st.subheader("📊 Equipment Status Report")
    chosen_rooms = st.multiselect("Rooms included (remove a room with ✕)",
                                  ROOMS, default=ROOMS)
    if len(chosen_rooms) == 0:
        st.info("Select at least one room.")
        return

    room_counts = get_room_counts(chosen_rooms)

    figure = bar_figure(room_counts)
    st.pyplot(figure)
    plt.close(figure)

    st.dataframe(pd.DataFrame(build_summary_rows(room_counts)),
                 hide_index=True, width="stretch")

    st.markdown("**Summary**")
    st.info(build_summary_paragraph(room_counts))

    st.divider()
    st.markdown("**Export**")
    show_downloads(room_counts, chosen_rooms, user)
