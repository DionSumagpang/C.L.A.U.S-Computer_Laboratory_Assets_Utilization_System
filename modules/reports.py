"""Charts, summary paragraph, report page, and PDF / Excel export.

Plain functions only. Room data is passed around as a dictionary:
    room_counts = {"CpE Lab 1": {"Working": 20, "Defective": 5,
                                 "Needs Maintenance": 5}, ...}
"""
import io
from datetime import datetime

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
from modules import LOGO_PATH, ROOMS, STATUSES, STATUS_COLORS


# ===========================================================================
# DATA HELPERS
# ===========================================================================
def get_room_counts(rooms):
    """Build the room_counts dictionary for the chosen rooms."""
    room_counts = {}
    for room in rooms:
        room_counts[room] = db.get_status_counts(room)
    return room_counts


def total_of(counts):
    """Add up the three statuses of one room."""
    return counts["Working"] + counts["Defective"] + counts["Needs Maintenance"]


def percent(part, whole):
    """Return part/whole as a percentage rounded to 1 decimal (0 if whole=0)."""
    if whole == 0:
        return 0.0
    return round(part * 100 / whole, 1)


# ===========================================================================
# CHARTS
# ===========================================================================
def pie_figure(room, counts):
    """Pie chart of one room's status split (used in each room tab).

    Steps:
      1. Keep only the statuses that have at least one PC.
      2. If there are none, write 'No equipment' in the chart.
      3. Otherwise draw the pie with percentages and counts.
    """
    labels = []
    sizes = []
    pie_colors = []
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
            return str(round(pct, 1)) + "%\n(" + str(round(pct * total / 100)) + ")"

        axis.pie(sizes, labels=labels, colors=pie_colors,
                 autopct=label_maker, startangle=90,
                 wedgeprops={"edgecolor": "white"}, textprops={"fontsize": 9})

    axis.set_title(room + " (" + str(total) + " PCs)", fontweight="bold")
    figure.tight_layout()
    return figure


def bar_figure(room_counts):
    """ONE vertical bar chart for all chosen rooms.

    Every room is a group of three bars (Working, Defective, Needs
    Maintenance) placed side by side, so all rooms read as one chart.

    Steps:
      1. For each status, work out where its bar goes inside every room's
         group (left, middle, right) and what its height is.
      2. Draw those bars in the status colour and write the value on top.
      3. Put the room names under the groups; add legend, title, labels.
    """
    rooms = list(room_counts.keys())
    bar_width = 0.28
    tallest = 0

    figure, axis = plt.subplots(figsize=(8, 4.5))

    status_number = 0
    for status in STATUSES:
        positions = []
        heights = []
        room_number = 0
        for room in rooms:
            positions.append(room_number + (status_number - 1) * bar_width)
            heights.append(room_counts[room][status])
            if room_counts[room][status] > tallest:
                tallest = room_counts[room][status]
            room_number = room_number + 1

        bars = axis.bar(positions, heights, width=bar_width,
                        color=STATUS_COLORS[status], label=status)
        axis.bar_label(bars, padding=2, fontsize=9)
        status_number = status_number + 1

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
    """Convert a matplotlib figure to PNG bytes (for the PDF)."""
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=180)
    buffer.seek(0)
    return buffer


# ===========================================================================
# SUMMARY PARAGRAPH
# ===========================================================================
def condition_word(working_rate):
    """Turn an overall working percentage into a short description."""
    if working_rate >= 80:
        return "good condition"
    if working_rate >= 60:
        return "fair condition"
    return "poor condition that needs urgent attention"


def build_summary_paragraph(room_counts):
    """Write ONE paragraph that explains the numbers of the chosen rooms.

    Steps:
      1. Add up working / defective / maintenance PCs over all rooms.
      2. Find the room with the highest and lowest working rate, and the
         room with the most defective PCs.
      3. Write sentence 1: how many rooms and PCs.
      4. Write sentence 2: overall numbers and overall condition.
      5. Write sentence 3 (only if 2+ rooms): best vs. weakest room.
      6. Write sentence 4: what should be done next.
      7. Join the sentences into one paragraph.
    """
    total_working = 0
    total_defective = 0
    total_maintenance = 0
    best_room = ""
    best_rate = -1.0
    worst_room = ""
    worst_rate = 101.0
    defective_room = ""
    most_defective = 0
    rooms_with_pcs = 0

    for room in room_counts:
        counts = room_counts[room]
        room_total = total_of(counts)
        total_working = total_working + counts["Working"]
        total_defective = total_defective + counts["Defective"]
        total_maintenance = total_maintenance + counts["Needs Maintenance"]

        if counts["Defective"] > most_defective:
            most_defective = counts["Defective"]
            defective_room = room

        if room_total > 0:
            rooms_with_pcs = rooms_with_pcs + 1
            rate = percent(counts["Working"], room_total)
            if rate > best_rate:
                best_rate = rate
                best_room = room
            if rate < worst_rate:
                worst_rate = rate
                worst_room = room

    total_pcs = total_working + total_defective + total_maintenance
    if total_pcs == 0:
        return "No equipment records are available for the selected rooms."

    room_names = ", ".join(room_counts.keys())
    if len(room_counts) == 1:
        room_phrase = "1 laboratory room (" + room_names + ")"
    else:
        room_phrase = (str(len(room_counts)) + " laboratory rooms (" +
                       room_names + ")")
    working_rate = percent(total_working, total_pcs)

    sentences = []

    sentences.append(
        "As of " + datetime.now().strftime("%B %d, %Y") + ", this report covers " +
        room_phrase + " with " + str(total_pcs) + " PCs in total.")

    sentences.append(
        "Overall, " + str(total_working) + " PCs (" + str(working_rate) +
        "%) are working, " + str(total_defective) + " (" +
        str(percent(total_defective, total_pcs)) + "%) are defective, and " +
        str(total_maintenance) + " (" +
        str(percent(total_maintenance, total_pcs)) +
        "%) need maintenance, which puts the equipment in " +
        condition_word(working_rate) + ".")

    if rooms_with_pcs >= 2:
        if best_rate == worst_rate:
            sentences.append(
                "All rooms have the same working rate of " + str(best_rate) + "%.")
        else:
            sentences.append(
                best_room + " has the highest working rate at " +
                str(best_rate) + "%, while " + worst_room +
                " has the lowest at " + str(worst_rate) + "%.")

    not_usable = total_defective + total_maintenance
    if not_usable == 0:
        sentences.append(
            "Every PC is working, so only routine inspections are needed.")
    elif total_defective > 0 and total_maintenance > 0:
        sentences.append(
            str(not_usable) + " PCs (" + str(percent(not_usable, total_pcs)) +
            "%) are not fully usable, so repairs should be prioritized for the " +
            str(total_defective) + " defective units, starting with " +
            defective_room + ", followed by scheduled maintenance for the " +
            str(total_maintenance) + " flagged PCs.")
    elif total_defective > 0:
        sentences.append(
            "The " + str(total_defective) + " defective PCs need repair or "
            "replacement, starting with " + defective_room + ".")
    else:
        sentences.append(
            "The " + str(total_maintenance) +
            " PCs flagged for maintenance should be serviced soon "
            "before they become defective.")

    return " ".join(sentences)


# ===========================================================================
# TABLE FOR THE SUMMARY
# ===========================================================================
def build_summary_rows(room_counts):
    """List of rows: Room, Working, Defective, Needs Maintenance, Total."""
    rows = []
    for room in room_counts:
        counts = room_counts[room]
        rows.append({"Room": room,
                     "Working": counts["Working"],
                     "Defective": counts["Defective"],
                     "Needs Maintenance": counts["Needs Maintenance"],
                     "Total": total_of(counts)})
    return rows


# ===========================================================================
# EXPORT: PDF
# ===========================================================================
def build_pdf(room_counts, admin_name):
    """Create the PDF report and return it as bytes.

    Page order: logo header -> title -> bar chart -> summary table ->
    summary paragraph.
    """
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, topMargin=0.6 * inch,
                                 bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()

    # 1. Header with logo
    header = Table(
        [[Image(LOGO_PATH, width=1.3 * inch, height=1.22 * inch),
          [Paragraph("Batangas State University", styles["Heading3"]),
           Paragraph("The National Engineering University", styles["Normal"]),
           Paragraph("Computer Engineering Faculty", styles["Normal"])]]],
        colWidths=[1.5 * inch, 4.7 * inch])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (0, 0), colors.black)]))

    # 2. Bar chart
    figure = bar_figure(room_counts)
    chart_image = Image(figure_to_png(figure), width=6.4 * inch,
                        height=3.6 * inch)
    plt.close(figure)

    # 3. Summary table
    table_data = [["Room", "Working", "Defective", "Needs Maintenance", "Total"]]
    for row in build_summary_rows(room_counts):
        table_data.append([row["Room"], row["Working"], row["Defective"],
                           row["Needs Maintenance"], row["Total"]])
    summary_table = Table(table_data, colWidths=[1.6 * inch, 1 * inch,
                                                 1 * inch, 1.6 * inch,
                                                 0.9 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))

    # 4. Put everything on the page
    story = [
        header, Spacer(1, 8),
        Paragraph("Project C.L.A.U.S. - Equipment Status Report",
                  styles["Title"]),
        Paragraph("Generated by " + admin_name + " on " +
                  datetime.now().strftime("%B %d, %Y %I:%M %p"),
                  styles["Normal"]),
        Spacer(1, 12),
        chart_image,
        Spacer(1, 10),
        summary_table,
        Spacer(1, 14),
        Paragraph("Summary", styles["Heading2"]),
        Paragraph(build_summary_paragraph(room_counts), styles["BodyText"]),
    ]
    document.build(story)
    return output.getvalue()


# ===========================================================================
# EXPORT: EXCEL
# ===========================================================================
def build_excel(room_counts):
    """Create the Excel file (summary sheet + one sheet per room)."""
    output = io.BytesIO()
    summary_rows = build_summary_rows(room_counts)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary",
                                            index=False)
        for room in room_counts:
            records = pd.DataFrame(db.get_equipment_by_room(room))
            records = records.drop(columns=["id", "room"])
            records.to_excel(writer, sheet_name=room, index=False)

        # Style the header row and set column widths on every sheet
        for sheet in writer.book.worksheets:
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="333333")
            for column in sheet.columns:
                longest = 0
                for cell in column:
                    length = len(str(cell.value or ""))
                    if length > longest:
                        longest = length
                sheet.column_dimensions[column[0].column_letter].width = longest + 3

        # Write the summary paragraph under the summary table
        summary_sheet = writer.sheets["Summary"]
        paragraph_row = len(summary_rows) + 4
        summary_sheet.cell(row=paragraph_row - 1, column=1, value="Summary").font = Font(bold=True)
        summary_sheet.merge_cells(start_row=paragraph_row, start_column=1,
                                  end_row=paragraph_row, end_column=5)
        paragraph_cell = summary_sheet.cell(row=paragraph_row, column=1,
                                            value=build_summary_paragraph(room_counts))
        paragraph_cell.alignment = Alignment(wrap_text=True, vertical="top")
        summary_sheet.row_dimensions[paragraph_row].height = 120

    return output.getvalue()


# ===========================================================================
# PAGE
# ===========================================================================
def log_export(username, kind, rooms):
    """Callback: runs when a download button is clicked -> audit log."""
    db.add_audit_log(username, "EXPORT_" + kind, "", "",
                     "Rooms: " + ", ".join(rooms))


def render(user):
    """Draw the Reports page.

    Steps:
      1. Let the admin choose which rooms to include (rooms can be removed).
      2. Read the status counts of those rooms.
      3. Show the bar chart, the summary table and the paragraph.
      4. Show the PDF and Excel download buttons (each click is logged).
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
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    col_pdf, col_excel = st.columns(2)
    col_pdf.download_button(
        "⬇️ Download PDF report", build_pdf(room_counts, user["full_name"]),
        "CLAUS_report_" + stamp + ".pdf", "application/pdf",
        width="stretch", type="primary",
        on_click=log_export, args=(user["username"], "PDF", chosen_rooms))
    col_excel.download_button(
        "⬇️ Download Excel records", build_excel(room_counts),
        "CLAUS_equipment_" + stamp + ".xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
        on_click=log_export, args=(user["username"], "EXCEL", chosen_rooms))
