"""Maintenance Tracking Module for Project C.L.A.U.S.

Records computer issues, repair activities, and maintenance history, and
exports the records as a PDF or Excel report.
All database operations are handled by assets/database/database.py.
Only plain functions are used, with step-by-step docstrings for easy conversion
to pseudocode and flowcharts.

Page layout (tabs, in order):
  1. All Records        - search, filter, view, edit, delete
  2. Add Maintenance    - record a new issue for one PC
  3. History per PC     - lifetime service record of one computer
  4. Export Report      - filtered records -> PDF (landscape Letter) / Excel

Maintenance record = dictionary with: id, equipment_id, pc_code, room,
maintenance_date, maintenance_type, reported_problem, action_taken, status,
created_by, created_at, updated_at.
"""
import io
from datetime import date, datetime
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from assets.database import database as db
from modules import (
    MAINTENANCE_STATUS_COLORS,
    MAINTENANCE_STATUSES,
    MAINTENANCE_TYPES,
    ROOMS,
)
from modules.reports import make_pdf_header, style_sheet

# Display columns for the maintenance table
MAINTENANCE_COLUMNS = [
    "id",
    "pc_code",
    "room",
    "maintenance_date",
    "maintenance_type",
    "reported_problem",
    "action_taken",
    "status",
    "created_by",
]

MAINTENANCE_LABELS = {
    "id": "Log ID",
    "pc_code": "PC Code",
    "room": "Room",
    "maintenance_date": "Date",
    "maintenance_type": "Issue Type",
    "reported_problem": "Reported Problem",
    "action_taken": "Action Taken",
    "status": "Status",
    "created_by": "Logged By",
}


# ===========================================================================
# 1. HELPER & STYLING FUNCTIONS
# ===========================================================================
def color_maintenance_status(value):
    """Return CSS styling for a status cell in the table.

    Steps:
      1. Check if the status exists in MAINTENANCE_STATUS_COLORS.
      2. If found, return background and font color style.
      3. Otherwise return empty style string.
    """
    if value in MAINTENANCE_STATUS_COLORS:
        color = MAINTENANCE_STATUS_COLORS[value]
        return "background-color:" + color + "33;color:" + color + ";font-weight:600"
    return ""


def format_computer_option(pc):
    """Format a PC dictionary into a readable dropdown label.

    Steps:
      1. Extract pc_code, room, and status from the PC dict.
      2. Return a formatted string: '[Room] PC_CODE (Status)'.
    """
    return "[" + pc["room"] + "] " + pc["pc_code"] + " — " + pc["status"]


def get_status_badge(status):
    """Return an emoji and label for a maintenance status.

    Steps:
      1. Match the status string to its corresponding emoji indicator.
      2. Return emoji prefix with status name.
    """
    if status == "Pending":
        return "🟡 Pending"
    elif status == "In Progress":
        return "🔵 In Progress"
    elif status == "Completed":
        return "🟢 Completed"
    return status


# ===========================================================================
# 2. VALIDATION FUNCTIONS
# ===========================================================================
def validate_maintenance_data(equipment_id, reported_problem, maintenance_date):
    """Validate user inputs before creating or saving a maintenance record.

    Steps:
      1. Check if an equipment_id is selected (> 0).
      2. Check if the reported problem text is not empty.
      3. Check if maintenance date is not in the future beyond 30 days.
      4. Verify the equipment actually exists in the database.
      5. Return (True, '') if valid, or (False, error_message) if invalid.
    """
    if not equipment_id:
        return False, "Please select a valid computer."

    if reported_problem.strip() == "":
        return False, "Reported problem description cannot be empty."

    # Verify PC exists in database to prevent orphan references
    pc = db.get_equipment_by_id(equipment_id)
    if pc is None:
        return False, "The selected computer does not exist in the database."

    return True, ""


# ===========================================================================
# 3. METRICS DISPLAY
# ===========================================================================
def show_maintenance_metrics(room="All"):
    """Display count metric cards for maintenance records.

    Steps:
      1. Get count of records for each status from the database.
      2. Calculate the total count.
      3. Render 4 metric cards: Total, Pending, In Progress, Completed.
    """
    counts = db.get_maintenance_status_counts(room)
    total = sum(counts.values())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Records", total)
    col2.metric("🟡 Pending", counts["Pending"])
    col3.metric("🔵 In Progress", counts["In Progress"])
    col4.metric("🟢 Completed", counts["Completed"])


# ===========================================================================
# 4. TAB: ADD MAINTENANCE RECORD
# ===========================================================================
def show_add_maintenance_form(username):
    """Form to record a new computer issue and maintenance activity.

    Steps:
      1. Load all available computers from the database.
      2. Let user select room, then computer from that room.
      3. Collect maintenance date, issue type, problem, and initial action.
      4. On submit, validate inputs and check for potential duplicate.
      5. Insert record into database, write audit log, and notify user.
    """
    st.markdown("### ➕ Record New Computer Issue / Maintenance")
    st.caption("Log hardware or software issues, scheduled maintenance, or repairs.")

    all_pcs = db.get_all_equipment()
    if len(all_pcs) == 0:
        st.warning("No computers found in the database. Add computers first in Equipment Monitoring.")
        return

    # Filter computers by Room first for cleaner selection
    col_room, col_pc = st.columns([1, 2])
    selected_room = col_room.selectbox("1. Filter by Room", ["All Rooms"] + ROOMS, key="add_maint_room")

    if selected_room == "All Rooms":
        eligible_pcs = all_pcs
    else:
        eligible_pcs = [pc for pc in all_pcs if pc["room"] == selected_room]

    if len(eligible_pcs) == 0:
        st.info("No computers found in " + selected_room)
        return

    # Dropdown options mapping
    pc_options = {format_computer_option(pc): pc for pc in eligible_pcs}
    chosen_label = col_pc.selectbox("2. Select Computer *", list(pc_options.keys()), key="add_maint_pc")
    chosen_pc = pc_options[chosen_label]

    # Display selected PC specs for confirmation
    with st.expander("ℹ️ Selected PC Specifications", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.write("**Code:** " + chosen_pc["pc_code"])
        c2.write("**Room:** " + chosen_pc["room"])
        c3.write("**Status:** " + chosen_pc["status"])
        c4.write("**OS:** " + str(chosen_pc.get("os", "N/A")))
        c1.write("**CPU:** " + str(chosen_pc.get("cpu", "N/A")))
        c2.write("**RAM:** " + str(chosen_pc.get("ram_gb", "N/A")) + " GB")
        c3.write("**Storage:** " + str(chosen_pc.get("storage", "N/A")))
        c4.write("**GPU:** " + str(chosen_pc.get("gpu", "N/A")))

    # Form for maintenance details
    with st.form("form_add_maintenance"):
        col_date, col_type, col_status = st.columns(3)
        maint_date = col_date.date_input("Maintenance Date *", value=date.today())
        maint_type = col_type.selectbox("Issue / Maintenance Type *", MAINTENANCE_TYPES)
        status = col_status.selectbox("Status *", MAINTENANCE_STATUSES, index=0)

        reported_problem = st.text_area(
            "Reported Problem / Issue Description *",
            placeholder="Describe the defect, error message, or routine check needed...",
            help="Required: clearly explain what is wrong with the computer.",
        )

        action_taken = st.text_area(
            "Actions Taken / Initial Diagnosis",
            placeholder="Steps taken to diagnose or repair (optional if pending)...",
            help="What has been done so far to resolve the issue.",
        )

        # Option to automatically update PC's overall status
        update_pc_status = st.checkbox(
            "Also update this PC's overall status to 'Needs Maintenance' in Equipment table",
            value=(status != "Completed" and chosen_pc["status"] == "Working"),
        )

        submitted = st.form_submit_button("Submit Maintenance Record", type="primary", width="stretch")

    if submitted:
        # Step 1: Validation
        date_str = maint_date.strftime("%Y-%m-%d")
        is_valid, error_msg = validate_maintenance_data(chosen_pc["id"], reported_problem, date_str)

        if not is_valid:
            st.error("Validation error: " + error_msg)
            return

        # Step 2: Prevent accidental duplicates
        is_duplicate = db.check_maintenance_duplicate(chosen_pc["id"], date_str, maint_type)
        if is_duplicate:
            st.error("⚠️ Accidental duplicate prevented: A maintenance record for " + chosen_pc["pc_code"] +
                     " on " + date_str + " for '" + maint_type + "' already exists.")
            return

        # Step 3: Insert maintenance record into database
        try:
            record_values = {
                "equipment_id": chosen_pc["id"],
                "pc_code": chosen_pc["pc_code"],
                "room": chosen_pc["room"],
                "maintenance_date": date_str,
                "maintenance_type": maint_type,
                "reported_problem": reported_problem.strip(),
                "action_taken": action_taken.strip(),
                "status": status,
                "created_by": username,
            }
            new_id = db.add_maintenance(record_values)

            # Step 4: Optionally update PC status
            if update_pc_status and status != "Completed":
                updated_pc_values = dict(chosen_pc)
                updated_pc_values["status"] = "Needs Maintenance"
                db.update_equipment(chosen_pc["id"], updated_pc_values)

            # Step 5: Audit logging
            audit_details = (
                "Type: " + maint_type + " | Status: " + status +
                " | Problem: " + reported_problem.strip()[:60]
            )
            db.add_audit_log(username, "ADD_MAINTENANCE", chosen_pc["room"], chosen_pc["pc_code"], audit_details)

            st.session_state["maint_table_version"] = st.session_state.get("maint_table_version", 0) + 1
            st.toast("Maintenance record #" + str(new_id) + " created for " + chosen_pc["pc_code"], icon="✅")
            st.success("Successfully logged maintenance activity for " + chosen_pc["pc_code"] + " (ID: #" + str(new_id) + ")")
            st.rerun()

        except Exception as error:
            st.error("Failed to save maintenance record: " + str(error))


# ===========================================================================
# 4b. EXPORT: PDF AND EXCEL
# ===========================================================================
EXPORT_COLUMNS = [
    "id", "pc_code", "room", "maintenance_date", "maintenance_type",
    "reported_problem", "action_taken", "status", "created_by",
    "updated_at",
]
EXPORT_LABELS = dict(MAINTENANCE_LABELS, updated_at="Last Updated")


def build_export_dataframe(records):
    """Turn maintenance records into a table with readable column names.

    Steps:
      1. Build a DataFrame using the columns listed in EXPORT_COLUMNS.
      2. Rename each column using EXPORT_LABELS (e.g. pc_code -> PC Code).
      3. Return the DataFrame.
    """
    df = pd.DataFrame(records, columns=EXPORT_COLUMNS)
    return df.rename(columns=EXPORT_LABELS)


def count_by(records, field, choices):
    """Count how many records have each value of one field.

    Steps:
      1. Start every allowed choice (e.g. each status) at 0.
      2. Go through the records one by one.
      3. Add 1 to the count of the record's value (ignore unknown values).
      4. Return the dictionary, e.g. {"Pending": 2, "Completed": 5}.
    """
    counts = {choice: 0 for choice in choices}
    for record in records:
        if record[field] in counts:
            counts[record[field]] += 1
    return counts


def build_maintenance_summary(records, filter_text):
    """Build one paragraph that explains the exported records.

    Steps:
      1. If there are no records, return a 'no records match' message.
      2. Count the records per status and per issue type.
      3. Work out the open records (Pending + In Progress), the most common
         issue type, and the number of different PCs involved.
      4. Join everything into one paragraph and return it.
    """
    total = len(records)
    if total == 0:
        return "No maintenance records match the selected filters."
    by_status = count_by(records, "status", MAINTENANCE_STATUSES)
    open_count = by_status["Pending"] + by_status["In Progress"]
    by_type = count_by(records, "maintenance_type", MAINTENANCE_TYPES)
    top_type = max(by_type, key=by_type.get)
    pcs = len({record["pc_code"] + record["room"] for record in records})
    return (
        "As of " + datetime.now().strftime("%B %d, %Y") + ", this report "
        "covers " + str(total) + " maintenance record(s) for "
        + str(pcs) + " PC(s). Filters: " + filter_text + ". "
        "Pending: " + str(by_status["Pending"]) + ", in progress: "
        + str(by_status["In Progress"]) + ", completed: "
        + str(by_status["Completed"]) + ". "
        + str(open_count) + " record(s) are still open. "
        "The most common issue type is " + top_type + " ("
        + str(by_type[top_type]) + ")."
    )


def build_maintenance_pdf(records, admin_name, filter_text):
    """Create the maintenance PDF report and return its bytes.

    Page: landscape US Letter. Page order: header -> title -> summary -> table.

    Steps:
      1. Set up the landscape Letter page, margins and text styles.
      2. Build the table: a header row, then one row per record.
         Long text (issue type, problem, action) is wrapped in Paragraphs and
         escape() keeps characters such as & and < from breaking the PDF.
      3. Style the table (dark header, grid lines, alternating row colors,
         header row repeated on every page).
      4. Put the story together: logo header, title, 'Generated by' line,
         summary paragraph, then the table.
      5. Build the document and return the PDF bytes.
    """
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(letter),
                                 topMargin=0.5 * inch, bottomMargin=0.5 * inch,
                                 leftMargin=0.5 * inch, rightMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small")
    small.fontSize = 8
    small.leading = 10

    headers = ["Log ID", "PC Code", "Room", "Date", "Issue Type",
               "Reported Problem", "Action Taken", "Status", "Logged By"]
    data = [headers]
    for r in records:
        data.append([
            str(r["id"]), escape(r["pc_code"]), escape(r["room"]),
            r["maintenance_date"], Paragraph(escape(r["maintenance_type"]), small),
            Paragraph(escape(r["reported_problem"] or ""), small),
            Paragraph(escape(r["action_taken"] or "-"), small),
            r["status"], escape(r["created_by"] or ""),
        ])
    widths = [0.5, 0.8, 0.8, 0.8, 1.0, 2.5, 2.2, 0.7, 0.7]
    table = Table(data, colWidths=[w * inch for w in widths], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f3f3f3")]),
    ]))

    generated = ("Generated by " + escape(admin_name) + " on "
                 + datetime.now().strftime("%B %d, %Y %I:%M %p"))
    story = [make_pdf_header(styles), Spacer(1, 8),
             Paragraph("Project C.L.A.U.S. - Maintenance Report",
                       styles["Title"]),
             Paragraph(generated, styles["Normal"]), Spacer(1, 10),
             Paragraph("Summary", styles["Heading2"]),
             Paragraph(escape(build_maintenance_summary(records, filter_text)),
                       styles["BodyText"]),
             Spacer(1, 10), table]
    document.build(story)
    return output.getvalue()


def build_maintenance_excel(records, filter_text):
    """Create the maintenance Excel file and return its bytes.

    Sheets: Summary (counts and filters used) + Records (every record).

    Steps:
      1. Count the records per status and per issue type.
      2. Make the Summary rows: total, one row per status, one per type.
      3. Write the Summary sheet and the Records sheet.
      4. Style both sheets (bold header, fitted column widths).
      5. Write the filters that were used under the Summary table.
      6. Return the Excel file bytes.
    """
    output = io.BytesIO()
    by_status = count_by(records, "status", MAINTENANCE_STATUSES)
    by_type = count_by(records, "maintenance_type", MAINTENANCE_TYPES)

    summary_rows = [{"Category": "Total Records", "Count": len(records)}]
    summary_rows += [{"Category": "Status: " + k, "Count": v}
                     for k, v in by_status.items()]
    summary_rows += [{"Category": "Type: " + k, "Count": v}
                     for k, v in by_type.items()]

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(
            writer, sheet_name="Summary", index=False)
        build_export_dataframe(records).to_excel(
            writer, sheet_name="Records", index=False)
        for sheet in writer.book.worksheets:
            style_sheet(sheet)
        sheet = writer.sheets["Summary"]
        sheet.cell(row=len(summary_rows) + 3, column=1,
                   value="Filters: " + filter_text)
    return output.getvalue()


def log_maintenance_export(username, kind, filter_text):
    """Write an audit log entry when a download button is clicked.

    Steps:
      1. Build the action name: EXPORT_MAINTENANCE_PDF or _EXCEL.
      2. Save the username, action and the filters used in the audit log.
    This function is passed to download_button as its on_click callback.
    """
    db.add_audit_log(username, "EXPORT_MAINTENANCE_" + kind, "", "",
                     "Filters: " + filter_text)


def show_maintenance_downloads(records, user, filter_text):
    """Draw the PDF and Excel download buttons.

    Steps:
      1. Make a time stamp for the file names (YYYYMMDD_HHMM).
      2. Create the PDF and show its download button (left column).
      3. Create the Excel file and show its download button (right column).
      4. If either file cannot be created, show an error message in that
         column instead of crashing the page.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    col_pdf, col_excel = st.columns(2)

    try:
        col_pdf.download_button(
            "⬇️ Download Maintenance PDF",
            build_maintenance_pdf(records, user["full_name"], filter_text),
            "CLAUS_maintenance_" + stamp + ".pdf", "application/pdf",
            width="stretch", type="primary",
            on_click=log_maintenance_export,
            args=(user["username"], "PDF", filter_text))
    except Exception as error:
        col_pdf.error("Could not create the PDF: " + str(error))

    try:
        col_excel.download_button(
            "⬇️ Download Maintenance Excel",
            build_maintenance_excel(records, filter_text),
            "CLAUS_maintenance_" + stamp + ".xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            on_click=log_maintenance_export,
            args=(user["username"], "EXCEL", filter_text))
    except Exception as error:
        col_excel.error("Could not create the Excel file: " + str(error))


# ===========================================================================
# 5. TAB: VIEW & MANAGE ALL RECORDS (With Edit & Delete)
# ===========================================================================
def show_edit_record_form(record, username):
    """Draw the form to edit an existing maintenance record.

    Steps:
      1. Populate form fields with existing record values.
      2. Validate updated inputs when user clicks Save.
      3. Call database update and write audit log.
      4. Refresh display.
    """
    rid = str(record["id"])
    st.markdown("#### ✏️ Edit Maintenance Record `#" + rid + "` (" + record["pc_code"] + ")")

    with st.form("form_edit_maintenance_" + rid):
        col1, col2, col3 = st.columns(3)

        # Parse stored date string into datetime.date
        try:
            current_date = datetime.strptime(record["maintenance_date"], "%Y-%m-%d").date()
        except Exception:
            current_date = date.today()

        new_date = col1.date_input("Maintenance Date", value=current_date, key="edit_date_" + rid)

        type_index = 0
        if record["maintenance_type"] in MAINTENANCE_TYPES:
            type_index = MAINTENANCE_TYPES.index(record["maintenance_type"])
        new_type = col2.selectbox("Issue / Type", MAINTENANCE_TYPES, index=type_index, key="edit_type_" + rid)

        status_index = 0
        if record["status"] in MAINTENANCE_STATUSES:
            status_index = MAINTENANCE_STATUSES.index(record["status"])
        new_status = col3.selectbox("Status", MAINTENANCE_STATUSES, index=status_index, key="edit_status_" + rid)

        new_problem = st.text_area("Reported Problem", value=record["reported_problem"], key="edit_prob_" + rid)
        new_action = st.text_area("Action Taken", value=record.get("action_taken", ""), key="edit_act_" + rid)

        saved = st.form_submit_button("Save Changes", type="primary", width="stretch")

    if saved:
        date_str = new_date.strftime("%Y-%m-%d")
        is_valid, error_msg = validate_maintenance_data(record["equipment_id"], new_problem, date_str)

        if not is_valid:
            st.error("Validation error: " + error_msg)
            return

        try:
            update_values = {
                "maintenance_date": date_str,
                "maintenance_type": new_type,
                "reported_problem": new_problem.strip(),
                "action_taken": new_action.strip(),
                "status": new_status,
            }
            db.update_maintenance(record["id"], update_values)

            # Audit log
            details = "Updated record #" + rid + " -> Status: " + new_status + " | Type: " + new_type
            db.add_audit_log(username, "EDIT_MAINTENANCE", record["room"], record["pc_code"], details)

            st.session_state["maint_table_version"] = st.session_state.get("maint_table_version", 0) + 1
            st.toast("Record #" + rid + " updated.", icon="✅")
            st.rerun()
        except Exception as error:
            st.error("Error updating record: " + str(error))


def show_delete_record_section(record, username):
    """Draw deletion confirmation section for a maintenance record.

    Steps:
      1. Display record details and a warning banner.
      2. Require explicit confirmation button click before deleting.
      3. Delete from database, log to audit trail, and reload.
    """
    rid = str(record["id"])
    st.markdown("#### 🗑️ Delete Maintenance Record `#" + rid + "`")
    st.warning(
        "Are you sure you want to delete this maintenance record for **" +
        record["pc_code"] + "** (" + record["maintenance_date"] + ")? This action cannot be undone."
    )

    col1, col2 = st.columns([1, 3])
    if col1.button("Yes, permanently delete", type="primary", key="del_maint_" + rid):
        try:
            db.delete_maintenance(record["id"])
            details = "Deleted maintenance record #" + rid + " (" + record["maintenance_type"] + ")"
            db.add_audit_log(username, "DELETE_MAINTENANCE", record["room"], record["pc_code"], details)
            st.session_state["maint_table_version"] = st.session_state.get("maint_table_version", 0) + 1
            st.toast("Maintenance record #" + rid + " deleted.", icon="🗑️")
            st.rerun()
        except Exception as error:
            st.error("Error deleting record: " + str(error))


def show_all_maintenance_records(username):
    """Display searchable, filterable table of all maintenance activities.

    Steps:
      1. Provide filter controls: status, issue type, room, and search text.
      2. Fetch matching records from the database.
      3. Render table with color-coded status column.
      4. Allow selecting a row to view full details, edit, or delete.
    """
    st.markdown("### 📋 Maintenance Activity Logs")

    # Filter row
    f1, f2, f3, f4 = st.columns([1.2, 1.5, 1.2, 2])
    status_filter = f1.selectbox("Filter Status", ["All"] + MAINTENANCE_STATUSES, key="v_stat_filter")
    type_filter = f2.selectbox("Filter Issue Type", ["All"] + MAINTENANCE_TYPES, key="v_type_filter")
    room_filter = f3.selectbox("Filter Room", ["All"] + ROOMS, key="v_room_filter")
    search_query = f4.text_input("🔍 Search", placeholder="PC code, problem, technician...", key="v_search")

    records = db.get_all_maintenance(status_filter, type_filter, room_filter, search_query)
    st.caption(str(len(records)) + " maintenance records found.")

    if len(records) == 0:
        st.info("No maintenance records match your filters.")
        return

    # Convert records to DataFrame for presentation
    df = pd.DataFrame(records, columns=MAINTENANCE_COLUMNS)
    df = df.rename(columns=MAINTENANCE_LABELS)

    # Style status column
    table_ver = st.session_state.get("maint_table_version", 0)
    table_key = "maintenance_main_table_" + str(table_ver)
    table_event = st.dataframe(
        df.style.map(color_maintenance_status, subset=["Status"]),
        hide_index=True,
        width="stretch",
        height=320,
        selection_mode="single-row",
        on_select="rerun",
        key=table_key,
    )

    selected_rows = table_event.selection.rows
    if len(selected_rows) > 0 and selected_rows[0] < len(records):
        selected_record = records[selected_rows[0]]
        st.divider()

        # Detailed view with Edit and Delete tabs
        tab_view, tab_edit, tab_delete = st.tabs(["📄 Record Details", "✏️ Edit Record", "🗑️ Delete Record"])

        with tab_view:
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown("**Log ID:** #" + str(selected_record["id"]))
            c2.markdown("**PC Code:** `" + selected_record["pc_code"] + "`")
            c3.markdown("**Room:** " + selected_record["room"])
            c4.markdown("**Status:** " + get_status_badge(selected_record["status"]))

            c1.markdown("**Date:** " + selected_record["maintenance_date"])
            c2.markdown("**Type:** " + selected_record["maintenance_type"])
            c3.markdown("**Logged By:** " + selected_record["created_by"])
            c4.markdown("**Last Updated:** " + selected_record.get("updated_at", "N/A"))

            st.markdown("**Reported Problem:**")
            st.info(selected_record["reported_problem"])

            action_text = selected_record.get("action_taken", "")
            st.markdown("**Action Taken:**")
            if action_text and action_text.strip():
                st.success(action_text)
            else:
                st.caption("No repair action recorded yet.")

        with tab_edit:
            show_edit_record_form(selected_record, username)

        with tab_delete:
            show_delete_record_section(selected_record, username)


# ===========================================================================
# 5b. TAB: EXPORT REPORT
# ===========================================================================
def show_export_tab(user):
    """Export tab: pick filters, preview the records, download PDF / Excel.

    Steps:
      1. Provide filter controls: status, issue type, room, and search text.
      2. Fetch matching records and show a preview table.
      3. Show the PDF and Excel download buttons.
    """
    st.markdown("### 📤 Export Maintenance Report")
    st.caption("Choose what to include, then download the report as PDF or Excel.")

    f1, f2, f3, f4 = st.columns([1.2, 1.5, 1.2, 2])
    status_filter = f1.selectbox("Filter Status", ["All"] + MAINTENANCE_STATUSES, key="x_stat_filter")
    type_filter = f2.selectbox("Filter Issue Type", ["All"] + MAINTENANCE_TYPES, key="x_type_filter")
    room_filter = f3.selectbox("Filter Room", ["All"] + ROOMS, key="x_room_filter")
    search_query = f4.text_input("🔍 Search", placeholder="PC code, problem, technician...", key="x_search")

    records = db.get_all_maintenance(status_filter, type_filter, room_filter, search_query)
    st.caption(str(len(records)) + " maintenance records will be exported.")

    if len(records) == 0:
        st.info("No maintenance records match your filters.")
        return

    filter_text = ("Status=" + status_filter + ", Type=" + type_filter
                   + ", Room=" + room_filter
                   + (", Search='" + search_query + "'" if search_query else ""))

    st.markdown("**Summary**")
    st.info(build_maintenance_summary(records, filter_text))

    preview = build_export_dataframe(records)
    st.dataframe(preview.style.map(color_maintenance_status, subset=["Status"]),
                 hide_index=True, width="stretch", height=320)

    st.divider()
    st.markdown("**Export**")
    show_maintenance_downloads(records, user, filter_text)


# ===========================================================================
# 6. TAB: MAINTENANCE HISTORY PER COMPUTER
# ===========================================================================
def show_computer_maintenance_history():
    """Display the complete chronological maintenance history of a selected computer.

    Steps:
      1. Let user select a room and a PC.
      2. Retrieve all maintenance records linked to that PC's equipment_id.
      3. Show summary cards (total issues, resolved, pending).
      4. Render a chronological timeline table of all past maintenance events.
    """
    st.markdown("### 🖥️ Maintenance History per Computer")
    st.caption("Inspect the lifetime service and repair record of an individual PC.")

    all_pcs = db.get_all_equipment()
    if len(all_pcs) == 0:
        st.info("No computers found in the database.")
        return

    c_room, c_pc = st.columns([1, 2])
    selected_room = c_room.selectbox("Select Room", ROOMS, key="hist_room")

    room_pcs = [pc for pc in all_pcs if pc["room"] == selected_room]
    if len(room_pcs) == 0:
        st.info("No computers found in " + selected_room)
        return

    pc_choices = {pc["pc_code"] + " (" + pc["status"] + ")": pc for pc in room_pcs}
    chosen_label = c_pc.selectbox("Select PC Code", list(pc_choices.keys()), key="hist_pc")
    chosen_pc = pc_choices[chosen_label]

    # Fetch history for this computer
    history = db.get_maintenance_by_equipment(chosen_pc["id"])

    # Computer profile header card
    with st.container():
        st.markdown(
            "#### PC Profile: `" + chosen_pc["pc_code"] + "` (" + chosen_pc["room"] + ")"
        )
        p1, p2, p3, p4 = st.columns(4)
        p1.write("**Current PC Status:** " + chosen_pc["status"])
        p2.write("**CPU:** " + str(chosen_pc.get("cpu", "N/A")))
        p3.write("**RAM:** " + str(chosen_pc.get("ram_gb", "N/A")) + " GB")
        p4.write("**Storage:** " + str(chosen_pc.get("storage", "N/A")))

    # Summary counts for this PC
    total_issues = len(history)
    pending_count = sum(1 for h in history if h["status"] == "Pending")
    in_prog_count = sum(1 for h in history if h["status"] == "In Progress")
    completed_count = sum(1 for h in history if h["status"] == "Completed")

    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Total Issues Logged", total_issues)
    h2.metric("🟡 Pending", pending_count)
    h3.metric("🔵 In Progress", in_prog_count)
    h4.metric("🟢 Resolved / Completed", completed_count)

    st.divider()

    if total_issues == 0:
        st.success("✅ This computer has no recorded maintenance issues. All clean!")
        return

    st.markdown("**Chronological History (Newest First):**")

    # Render table of history
    hist_columns = ["id", "maintenance_date", "maintenance_type", "reported_problem", "action_taken", "status", "created_by"]
    hist_labels = {
        "id": "Log ID",
        "maintenance_date": "Date",
        "maintenance_type": "Issue Type",
        "reported_problem": "Problem",
        "action_taken": "Action Taken",
        "status": "Status",
        "created_by": "Logged By",
    }
    hist_df = pd.DataFrame(history, columns=hist_columns)
    hist_df = hist_df.rename(columns=hist_labels)

    st.dataframe(
        hist_df.style.map(color_maintenance_status, subset=["Status"]),
        hide_index=True,
        width="stretch",
    )

    # Detailed expandable cards for each history event
    st.markdown("**Detailed Timeline Cards:**")
    for event in history:
        badge = get_status_badge(event["status"])
        title = event["maintenance_date"] + " — " + event["maintenance_type"] + " (" + badge + ")"
        with st.expander(title, expanded=False):
            st.write("**Reported Problem:** " + event["reported_problem"])
            if event.get("action_taken"):
                st.write("**Action Taken:** " + event["action_taken"])
            else:
                st.write("**Action Taken:** _None recorded_")
            st.caption("Logged by " + event["created_by"] + " on " + event.get("created_at", "N/A") +
                       " | Last updated: " + event.get("updated_at", "N/A"))


# ===========================================================================
# 7. MAIN INTERFACE RENDER FUNCTION
# ===========================================================================
def render(user):
    """Main entry point to render the Maintenance Tracking page.

    Steps:
      1. Display the page header and overall metric summary.
      2. Render 3 tabs:
         - 📋 All Maintenance Records (Search, Filter, View, Edit, Delete)
         - ➕ Add Maintenance Record (Input validation, duplicate check, PC lookup)
         - 🔍 Computer History (Per-PC chronological lifecycle logs)
         - 📤 Export Report (PDF / Excel of filtered records)
      3. Route to the respective tab functions based on user interaction.
    """
    st.title("🔧 Computer Maintenance & Issue Tracking")
    st.caption("Monitor laboratory PC issues, maintenance schedules, and repair history.")

    # Top summary metrics across all labs
    show_maintenance_metrics()
    st.divider()

    tab_all, tab_add, tab_history, tab_export = st.tabs([
        "📋 All Records",
        "➕ Add Maintenance Record",
        "🔍 History per Computer",
        "📤 Export Report",
    ])

    with tab_all:
        show_all_maintenance_records(user["username"])

    with tab_add:
        show_add_maintenance_form(user["username"])

    with tab_history:
        show_computer_maintenance_history()

    with tab_export:
        show_export_tab(user)
