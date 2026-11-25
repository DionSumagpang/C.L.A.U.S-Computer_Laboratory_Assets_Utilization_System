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
from datetime import date, datetime
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from assets.database import database as db
from modules import (MAINTENANCE_STATUS_COLORS, MAINTENANCE_STATUSES,
                     MAINTENANCE_TYPES, ROOMS, count_by, status_styled,
                     toast_and_rerun)
from modules.reports import (HEADER_STYLE, cached, excel_bytes,
                             make_pdf_header, pdf_bytes, pdf_title,
                             show_pdf_excel_pair)

# Table columns (the dictionary key = database column, the value = heading)
MAINTENANCE_LABELS = {
    "id": "Log ID", "pc_code": "PC Code", "room": "Room",
    "maintenance_date": "Date", "maintenance_type": "Issue Type",
    "reported_problem": "Reported Problem", "action_taken": "Action Taken",
    "status": "Status", "created_by": "Logged By",
}
MAINTENANCE_COLUMNS = list(MAINTENANCE_LABELS)
EXPORT_LABELS = dict(MAINTENANCE_LABELS, updated_at="Last Updated")
EXPORT_COLUMNS = list(EXPORT_LABELS)
HISTORY_LABELS = {
    "id": "Log ID", "maintenance_date": "Date",
    "maintenance_type": "Issue Type", "reported_problem": "Problem",
    "action_taken": "Action Taken", "status": "Status", "created_by": "Logged By",
}
STATUS_BADGES = {"Pending": "🟡 Pending", "In Progress": "🔵 In Progress",
                 "Completed": "🟢 Completed"}


# -- 1. HELPER FUNCTIONS
def status_table(df):
    """Style the 'Status' column of a table with the status colors."""
    return status_styled(df, MAINTENANCE_STATUS_COLORS)


def filter_controls(prefix):
    """Draw the status / type / room / search boxes.

    Returns (status_filter, type_filter, room_filter, search_query).
    `prefix` keeps the boxes of different tabs apart.
    """
    f1, f2, f3, f4 = st.columns([1.2, 1.5, 1.2, 2])
    return (
        f1.selectbox("Filter Status", ["All"] + MAINTENANCE_STATUSES,
                     key=prefix + "_stat_filter"),
        f2.selectbox("Filter Issue Type", ["All"] + MAINTENANCE_TYPES,
                     key=prefix + "_type_filter"),
        f3.selectbox("Filter Room", ["All"] + ROOMS, key=prefix + "_room_filter"),
        f4.text_input("🔍 Search", placeholder="PC code, problem, technician...",
                      key=prefix + "_search"))


def validation_error(equipment_id, reported_problem):
    """Validate user inputs before creating or saving a maintenance record.

    Steps:
      1. Check if an equipment_id is selected.
      2. Check if the reported problem text is not empty.
      3. Verify the equipment actually exists in the database.
      4. Return '' if valid, or the error message if invalid.
    """
    if not equipment_id:
        return "Please select a valid computer."
    if reported_problem.strip() == "":
        return "Reported problem description cannot be empty."
    if db.get_equipment_by_id(equipment_id) is None:
        return "The selected computer does not exist in the database."
    return ""


def show_facts(facts):
    """Show (label, value) pairs as '**label:** value' in four columns."""
    columns = st.columns(4)
    for number, (label, value) in enumerate(facts):
        columns[number % 4].markdown(f"**{label}:** {value}")


def pick_pc(all_pcs, rooms, room_label, pc_label, key, option_text):
    """Room box + computer box. Returns the chosen PC (dictionary).

    Returns None (after showing a message) when the room has no computers.
    `key` keeps the boxes of different tabs apart.
    """
    col_room, col_pc = st.columns([1, 2])
    room = col_room.selectbox(room_label, rooms, key=key + "_room")
    pcs = [pc for pc in all_pcs if room in ("All Rooms", pc["room"])]
    if not pcs:
        st.info("No computers found in " + room)
        return None
    options = {option_text(pc): pc for pc in pcs}
    return options[col_pc.selectbox(pc_label, list(options), key=key + "_pc")]


def show_status_metrics(counts, total, total_label, done_label):
    """Four metric cards: total, Pending, In Progress, completed."""
    labels = [total_label, "🟡 Pending", "🔵 In Progress", done_label]
    values = [total, *(counts[s] for s in MAINTENANCE_STATUSES)]
    for column, label, value in zip(st.columns(4), labels, values):
        column.metric(label, value)


def show_maintenance_metrics():
    """Display count metric cards: Total, Pending, In Progress, Completed."""
    counts = db.get_maintenance_status_counts()
    show_status_metrics(counts, sum(counts.values()), "Total Records",
                        "🟢 Completed")


# -- 2. TAB: ADD MAINTENANCE RECORD
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
    if not all_pcs:
        st.warning("No computers found in the database. Add computers first in Equipment Monitoring.")
        return

    pc = pick_pc(all_pcs, ["All Rooms"] + ROOMS, "1. Filter by Room",
                 "2. Select Computer *", "add_maint",
                 lambda pc: f"[{pc['room']}] {pc['pc_code']} — {pc['status']}")
    if pc is None:
        return

    with st.expander("ℹ️ Selected PC Specifications", expanded=False):
        show_facts([("Code", pc["pc_code"]), ("Room", pc["room"]),
                    ("Status", pc["status"]), ("OS", pc["os"]),
                    ("CPU", pc["cpu"]), ("RAM", f"{pc['ram_gb']} GB"),
                    ("Storage", pc["storage"]), ("GPU", pc["gpu"])])

    with st.form("form_add_maintenance"):
        col_date, col_type, col_status = st.columns(3)
        maint_date = col_date.date_input("Maintenance Date *", value=date.today())
        maint_type = col_type.selectbox("Issue / Maintenance Type *", MAINTENANCE_TYPES)
        status = col_status.selectbox("Status *", MAINTENANCE_STATUSES, index=0)

        reported_problem = st.text_area(
            "Reported Problem / Issue Description *",
            placeholder="Describe the defect, error message, or routine check needed...",
            help="Required: clearly explain what is wrong with the computer.")
        action_taken = st.text_area(
            "Actions Taken / Initial Diagnosis",
            placeholder="Steps taken to diagnose or repair (optional if pending)...",
            help="What has been done so far to resolve the issue.")

        # Option to automatically update PC's overall status
        update_pc_status = st.checkbox(
            "Also update this PC's overall status to 'Needs Maintenance' in Equipment table",
            value=(status != "Completed" and pc["status"] == "Working"))

        submitted = st.form_submit_button("Submit Maintenance Record",
                                          type="primary", width="stretch")
    if not submitted:
        return

    date_str = maint_date.strftime("%Y-%m-%d")
    if error_msg := validation_error(pc["id"], reported_problem):
        st.error("Validation error: " + error_msg)
        return

    # Prevent accidental duplicates
    if db.check_maintenance_duplicate(pc["id"], date_str, maint_type):
        st.error(f"⚠️ Accidental duplicate prevented: A maintenance record for "
                 f"{pc['pc_code']} on {date_str} for '{maint_type}' already exists.")
        return

    try:
        problem = reported_problem.strip()
        new_id = db.add_maintenance({
            "equipment_id": pc["id"], "pc_code": pc["pc_code"],
            "room": pc["room"], "maintenance_date": date_str,
            "maintenance_type": maint_type, "reported_problem": problem,
            "action_taken": action_taken.strip(), "status": status,
            "created_by": username})

        if update_pc_status and status != "Completed":
            db.update_equipment(pc["id"], dict(pc, status="Needs Maintenance"))

        db.add_audit_log(
            username, "ADD_MAINTENANCE", pc["room"], pc["pc_code"],
            f"Type: {maint_type} | Status: {status} | Problem: {problem[:60]}")
        toast_and_rerun("maint_table_version",
                        f"Maintenance record #{new_id} created for {pc['pc_code']}")
    except Exception as error:
        st.error("Failed to save maintenance record: " + str(error))


# -- 3. EXPORT: PDF AND EXCEL
def build_export_dataframe(records):
    """Turn maintenance records into a table with readable column names."""
    return pd.DataFrame(records, columns=EXPORT_COLUMNS).rename(
        columns=EXPORT_LABELS)


def build_maintenance_summary(records, filter_text, now):
    """Build one paragraph that explains the exported records.

    Steps:
      1. If there are no records, return a 'no records match' message.
      2. Count the records per status and per issue type.
      3. Work out the open records (Pending + In Progress), the most common
         issue type, and the number of different PCs involved.
      4. Join everything into one paragraph and return it.
    """
    if not records:
        return "No maintenance records match the selected filters."
    by_status = count_by(records, "status", MAINTENANCE_STATUSES)
    by_type = count_by(records, "maintenance_type", MAINTENANCE_TYPES)
    top_type = max(by_type, key=by_type.get)
    pcs = len({record["pc_code"] + record["room"] for record in records})
    return (
        f"As of {now:%B %d, %Y}, this report covers {len(records)} "
        f"maintenance record(s) for {pcs} PC(s). Filters: {filter_text}. "
        f"Pending: {by_status['Pending']}, in progress: "
        f"{by_status['In Progress']}, completed: {by_status['Completed']}. "
        f"{by_status['Pending'] + by_status['In Progress']} record(s) are "
        f"still open. The most common issue type is {top_type} "
        f"({by_type[top_type]}).")


@cached
def build_maintenance_pdf(records, admin_name, filter_text, now):
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
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small")
    small.fontSize, small.leading = 8, 10

    data = [list(MAINTENANCE_LABELS.values())] + [[
        str(r["id"]), escape(r["pc_code"]), escape(r["room"]),
        r["maintenance_date"], Paragraph(escape(r["maintenance_type"]), small),
        Paragraph(escape(r["reported_problem"] or ""), small),
        Paragraph(escape(r["action_taken"] or "-"), small),
        r["status"], escape(r["created_by"] or "")] for r in records]
    widths = [0.5, 0.8, 0.8, 0.8, 1.0, 2.5, 2.2, 0.7, 0.7]
    table = Table(data, colWidths=[w * inch for w in widths], repeatRows=1)
    table.setStyle(TableStyle(HEADER_STYLE + [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f3f3f3")]),
    ]))

    return pdf_bytes([
        make_pdf_header(styles), Spacer(1, 8),
        *pdf_title(styles, "Project C.L.A.U.S. - Maintenance Report",
                   admin_name, now),
        Spacer(1, 10),
        Paragraph("Summary", styles["Heading2"]),
        Paragraph(escape(build_maintenance_summary(records, filter_text, now)),
                  styles["BodyText"]),
        Spacer(1, 10), table],
        pagesize=landscape(letter), topMargin=0.5 * inch,
        bottomMargin=0.5 * inch, leftMargin=0.5 * inch,
        rightMargin=0.5 * inch)


@cached
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
    summary_rows = (
        [{"Category": "Total Records", "Count": len(records)}]
        + [{"Category": f"Status: {k}", "Count": v} for k, v in
           count_by(records, "status", MAINTENANCE_STATUSES).items()]
        + [{"Category": f"Type: {k}", "Count": v} for k, v in
           count_by(records, "maintenance_type", MAINTENANCE_TYPES).items()])
    return excel_bytes(
        {"Summary": pd.DataFrame(summary_rows),
         "Records": build_export_dataframe(records)},
        lambda sheet: sheet.cell(row=len(summary_rows) + 3, column=1,
                                 value="Filters: " + filter_text))


def show_maintenance_downloads(records, user, filter_text, now):
    """Draw the PDF and Excel download buttons for the maintenance report."""
    stamp = f"{now:%Y%m%d_%H%M}"
    details = "Filters: " + filter_text
    show_pdf_excel_pair(
        ("⬇️ Download Maintenance PDF",
         lambda: build_maintenance_pdf(records, user["full_name"],
                                       filter_text, now),
         f"CLAUS_maintenance_{stamp}.pdf",
         (user["username"], "EXPORT_MAINTENANCE_PDF", details)),
        ("⬇️ Download Maintenance Excel",
         lambda: build_maintenance_excel(records, filter_text),
         f"CLAUS_maintenance_{stamp}.xlsx",
         (user["username"], "EXPORT_MAINTENANCE_EXCEL", details)))


# -- 4. TAB: VIEW & MANAGE ALL RECORDS (With Edit & Delete)
def show_edit_record_form(record, username):
    """Draw the form to edit an existing maintenance record.

    Steps:
      1. Populate form fields with existing record values.
      2. Validate updated inputs when user clicks Save.
      3. Call database update and write audit log.
      4. Refresh display.
    """
    rid = str(record["id"])
    st.markdown(f"#### ✏️ Edit Maintenance Record `#{rid}` ({record['pc_code']})")

    try:  # stored date text -> date
        current_date = datetime.strptime(record["maintenance_date"], "%Y-%m-%d").date()
    except Exception:
        current_date = date.today()
    type_index = (MAINTENANCE_TYPES.index(record["maintenance_type"])
                  if record["maintenance_type"] in MAINTENANCE_TYPES else 0)
    status_index = (MAINTENANCE_STATUSES.index(record["status"])
                    if record["status"] in MAINTENANCE_STATUSES else 0)

    with st.form("form_edit_maintenance_" + rid):
        col1, col2, col3 = st.columns(3)
        new_date = col1.date_input("Maintenance Date", value=current_date,
                                   key="edit_date_" + rid)
        new_type = col2.selectbox("Issue / Type", MAINTENANCE_TYPES,
                                  index=type_index, key="edit_type_" + rid)
        new_status = col3.selectbox("Status", MAINTENANCE_STATUSES,
                                    index=status_index, key="edit_status_" + rid)
        new_problem = st.text_area("Reported Problem",
                                   value=record["reported_problem"],
                                   key="edit_prob_" + rid)
        new_action = st.text_area("Action Taken",
                                  value=record.get("action_taken", ""),
                                  key="edit_act_" + rid)
        saved = st.form_submit_button("Save Changes", type="primary",
                                      width="stretch")
    if not saved:
        return

    if error_msg := validation_error(record["equipment_id"], new_problem):
        st.error("Validation error: " + error_msg)
        return

    try:
        db.update_maintenance(record["id"], {
            "maintenance_date": new_date.strftime("%Y-%m-%d"),
            "maintenance_type": new_type,
            "reported_problem": new_problem.strip(),
            "action_taken": new_action.strip(), "status": new_status})
        db.add_audit_log(
            username, "EDIT_MAINTENANCE", record["room"], record["pc_code"],
            f"Updated record #{rid} -> Status: {new_status} | Type: {new_type}")
        toast_and_rerun("maint_table_version", f"Record #{rid} updated.")
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
    st.markdown(f"#### 🗑️ Delete Maintenance Record `#{rid}`")
    st.warning(f"Are you sure you want to delete this maintenance record for "
               f"**{record['pc_code']}** ({record['maintenance_date']})? "
               f"This action cannot be undone.")

    if st.columns([1, 3])[0].button("Yes, permanently delete", type="primary",
                                    key="del_maint_" + rid):
        try:
            db.delete_maintenance(record["id"])
            db.add_audit_log(
                username, "DELETE_MAINTENANCE", record["room"],
                record["pc_code"],
                f"Deleted maintenance record #{rid} ({record['maintenance_type']})")
            toast_and_rerun("maint_table_version",
                           f"Maintenance record #{rid} deleted.", "🗑️")
        except Exception as error:
            st.error("Error deleting record: " + str(error))


def show_record_details(record):
    """Show the full details of one maintenance record (read only)."""
    show_facts([("Log ID", f"#{record['id']}"),
                ("PC Code", f"`{record['pc_code']}`"), ("Room", record["room"]),
                ("Status", STATUS_BADGES.get(record["status"], record["status"])),
                ("Date", record["maintenance_date"]),
                ("Type", record["maintenance_type"]),
                ("Logged By", record["created_by"]),
                ("Last Updated", record["updated_at"])])

    st.markdown("**Reported Problem:**")
    st.info(record["reported_problem"])

    action_text = record.get("action_taken", "")
    st.markdown("**Action Taken:**")
    if action_text and action_text.strip():
        st.success(action_text)
    else:
        st.caption("No repair action recorded yet.")


def show_all_maintenance_records(username):
    """Display searchable, filterable table of all maintenance activities.

    Steps:
      1. Provide filter controls: status, issue type, room, and search text.
      2. Fetch matching records from the database.
      3. Render table with color-coded status column.
      4. Allow selecting a row to view full details, edit, or delete.
    """
    st.markdown("### 📋 Maintenance Activity Logs")
    records = db.get_all_maintenance(*filter_controls("v"))
    st.caption(f"{len(records)} maintenance records found.")

    if not records:
        st.info("No maintenance records match your filters.")
        return

    df = pd.DataFrame(records, columns=MAINTENANCE_COLUMNS).rename(
        columns=MAINTENANCE_LABELS)
    table_event = st.dataframe(
        status_table(df), hide_index=True, width="stretch", height=320,
        selection_mode="single-row", on_select="rerun",
        key=f"maintenance_main_table_{st.session_state.get('maint_table_version', 0)}")

    selected = table_event.selection.rows
    if selected and selected[0] < len(records):
        record = records[selected[0]]
        st.divider()
        tab_view, tab_edit, tab_delete = st.tabs(
            ["📄 Record Details", "✏️ Edit Record", "🗑️ Delete Record"])
        with tab_view:
            show_record_details(record)
        with tab_edit:
            show_edit_record_form(record, username)
        with tab_delete:
            show_delete_record_section(record, username)


# -- 5. TAB: EXPORT REPORT
def show_export_tab(user):
    """Export tab: pick filters, preview the records, download PDF / Excel.

    Steps:
      1. Provide filter controls: status, issue type, room, and search text.
      2. Fetch matching records and show a preview table.
      3. Show the PDF and Excel download buttons.
    """
    st.markdown("### 📤 Export Maintenance Report")
    st.caption("Choose what to include, then download the report as PDF or Excel.")

    status_filter, type_filter, room_filter, search_query = filter_controls("x")
    records = db.get_all_maintenance(status_filter, type_filter, room_filter,
                                     search_query)
    st.caption(f"{len(records)} maintenance records will be exported.")

    if not records:
        st.info("No maintenance records match your filters.")
        return

    filter_text = (f"Status={status_filter}, Type={type_filter}, "
                   f"Room={room_filter}"
                   + (f", Search='{search_query}'" if search_query else ""))
    now = datetime.now().replace(second=0, microsecond=0)

    st.markdown("**Summary**")
    st.info(build_maintenance_summary(records, filter_text, now))
    st.dataframe(status_table(build_export_dataframe(records)),
                 hide_index=True, width="stretch", height=320)

    st.divider()
    st.markdown("**Export**")
    show_maintenance_downloads(records, user, filter_text, now)


# -- 6. TAB: MAINTENANCE HISTORY PER COMPUTER
def show_computer_maintenance_history():
    """Display the complete chronological maintenance history of a computer.

    Steps:
      1. Let user select a room and a PC.
      2. Retrieve all maintenance records linked to that PC's equipment_id.
      3. Show summary cards (total issues, resolved, pending).
      4. Render a chronological timeline table of all past maintenance events.
    """
    st.markdown("### 🖥️ Maintenance History per Computer")
    st.caption("Inspect the lifetime service and repair record of an individual PC.")

    all_pcs = db.get_all_equipment()
    if not all_pcs:
        st.info("No computers found in the database.")
        return

    pc = pick_pc(all_pcs, ROOMS, "Select Room", "Select PC Code", "hist",
                 lambda pc: f"{pc['pc_code']} ({pc['status']})")
    if pc is None:
        return
    history = db.get_maintenance_by_equipment(pc["id"])

    with st.container():
        st.markdown(f"#### PC Profile: `{pc['pc_code']}` ({pc['room']})")
        show_facts([("Current PC Status", pc["status"]), ("CPU", pc["cpu"]),
                    ("RAM", f"{pc['ram_gb']} GB"), ("Storage", pc["storage"])])

    show_status_metrics(count_by(history, "status", MAINTENANCE_STATUSES),
                        len(history), "Total Issues Logged",
                        "🟢 Resolved / Completed")

    st.divider()
    if not history:
        st.success("✅ This computer has no recorded maintenance issues. All clean!")
        return

    st.markdown("**Chronological History (Newest First):**")
    hist_df = pd.DataFrame(history, columns=list(HISTORY_LABELS)).rename(
        columns=HISTORY_LABELS)
    st.dataframe(status_table(hist_df), hide_index=True, width="stretch")

    st.markdown("**Detailed Timeline Cards:**")
    for event in history:
        badge = STATUS_BADGES.get(event["status"], event["status"])
        title = f"{event['maintenance_date']} — {event['maintenance_type']} ({badge})"
        with st.expander(title, expanded=False):
            st.write("**Reported Problem:** " + event["reported_problem"])
            st.write("**Action Taken:** "
                     + (event["action_taken"] or "_None recorded_"))
            st.caption(f"Logged by {event['created_by']} on "
                       f"{event.get('created_at', 'N/A')} | Last updated: "
                       f"{event.get('updated_at', 'N/A')}")


# -- 7. MAIN INTERFACE RENDER FUNCTION
def render(user):
    """Main entry point to render the Maintenance Tracking page.

    Steps:
      1. Display the page header and overall metric summary.
      2. Render 4 tabs:
         - 📋 All Maintenance Records (Search, Filter, View, Edit, Delete)
         - ➕ Add Maintenance Record (Input validation, duplicate check, PC lookup)
         - 🔍 Computer History (Per-PC chronological lifecycle logs)
         - 📤 Export Report (PDF / Excel of filtered records)
      3. Route to the respective tab functions based on user interaction.
    """
    st.title("🔧 Computer Maintenance & Issue Tracking")
    st.caption("Monitor laboratory PC issues, maintenance schedules, and repair history.")

    show_maintenance_metrics()
    st.divider()

    tab_all, tab_add, tab_history, tab_export = st.tabs([
        "📋 All Records", "➕ Add Maintenance Record",
        "🔍 History per Computer", "📤 Export Report"])
    with tab_all:
        show_all_maintenance_records(user["username"])
    with tab_add:
        show_add_maintenance_form(user["username"])
    with tab_history:
        show_computer_maintenance_history()
    with tab_export:
        show_export_tab(user)
