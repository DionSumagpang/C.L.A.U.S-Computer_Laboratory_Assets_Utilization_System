"""Maintenance Tracking Module for Project C.L.A.U.S.

Records computer issues, repair activities and maintenance history, and exports
the records as a PDF or Excel report. All database work is done by
assets/database/database.py. Plain functions only, with step-by-step docstrings
for easy conversion to pseudocode and flowcharts.

Sections (chosen with pick_section; only the chosen one is run):
  1. All Records     - search, filter, view, edit (not Completed), delete
  2. Add Maintenance - record a new issue for one PC
  3. History per PC  - lifetime service record of one computer
  4. Export Report   - filtered records -> PDF (landscape Letter) / Excel

Rules:
  - One UNRESOLVED (Pending / In Progress) record per PC and issue type. A new report
    of a type that is already open is added to that record as one more problem line
    (no new record, no stamps); the same problem is never added twice. A Completed
    report cannot close an open record (it becomes In Progress); use Edit to complete.
  - Every edit is written to the audit log (EDIT_MAINTENANCE) and shown as the
    record's "Edit history", so who changed what and when is not repeated in the text.
  - A Completed record is locked (cannot be edited) but can still be deleted.

Maintenance record = dictionary with: id, equipment_id, pc_code, room,
maintenance_date, maintenance_type, reported_problem, action_taken, status,
created_by, created_at, updated_at.
"""
import io
import re
from datetime import date, datetime
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from assets.database import database as db
from modules import (MAINTENANCE_STATUS_COLORS, MAINTENANCE_STATUSES, MAINTENANCE_TYPES,
                     ROOMS, count_by, pick_section, status_styled, toast_and_rerun)
from modules.reports import (HEADER_STYLE, cached, excel_bytes, figure_png, pdf_bytes,
                             pdf_top, show_pdf_excel_pair)

# Table columns (dictionary key = database column, value = heading)
MAINTENANCE_LABELS = {
    "id": "Log ID", "pc_code": "PC Code", "room": "Room", "maintenance_date": "Date",
    "maintenance_type": "Issue Type", "reported_problem": "Reported Problem(s)",
    "action_taken": "Action Taken", "status": "Status", "created_by": "Logged By"}
EXPORT_LABELS = dict(MAINTENANCE_LABELS, updated_at="Last Updated")
HISTORY_LABELS = {
    "id": "Log ID", "maintenance_date": "Date", "maintenance_type": "Issue Type",
    "reported_problem": "Problem", "action_taken": "Action Taken",
    "status": "Status", "created_by": "Logged By"}
STATUS_BADGES = {"Pending": "🟡 Pending", "In Progress": "🔵 In Progress",
                 "Completed": "🟢 Completed"}
UNRESOLVED = MAINTENANCE_STATUSES[:2]  # Pending, In Progress
NOTE_TAG = re.compile(r"^(\[[^\]]*\]|[•*-])\s*")  # leading bullet, old '[stamp | ...]' or '[label]'
TRAIL_ID = re.compile(r"#(\d+)\b")        # record number inside an audit-log detail
SECTIONS = ["📋 All Records", "➕ Add Maintenance Record",
            "🔍 History per Computer", "📤 Export Report"]


# -- 1. HELPER FUNCTIONS
def status_table(df):
    """Style the 'Status' column of a table with the status colors."""
    return status_styled(df, MAINTENANCE_STATUS_COLORS)


def maintenance_frame(records, labels, short=True):
    """Turn maintenance records into a table with readable column names.

    With `short`, a record with more than one problem shows only '3 problems' in the
    Reported Problem column (the full list is in the record details).
    """
    table = pd.DataFrame(records, columns=list(labels)).rename(columns=labels)
    if short and "reported_problem" in labels:
        table[labels["reported_problem"]] = [problem_summary(r["reported_problem"])
                                             for r in records]
    return table


def index_of(options, value):
    """Position of `value` in `options` (0 when it is not there)."""
    return options.index(value) if value in options else 0


def filter_controls(prefix):
    """Draw the status / type / room / search boxes (`prefix` keeps tabs apart).

    Returns (status_filter, type_filter, room_filter, search_query).
    """
    f1, f2, f3, f4 = st.columns([1.2, 1.5, 1.2, 2])
    return (f1.selectbox("Filter Status", ["All"] + MAINTENANCE_STATUSES,
                         key=prefix + "_stat_filter"),
            f2.selectbox("Filter Issue Type", ["All"] + MAINTENANCE_TYPES,
                         key=prefix + "_type_filter"),
            f3.selectbox("Filter Room", ["All"] + ROOMS, key=prefix + "_room_filter"),
            f4.text_input("🔍 Search", placeholder="PC code, problem, technician...",
                          key=prefix + "_search"))


def validation_error(equipment_id, reported_problem):
    """Return '' when the inputs are valid, otherwise the error message.

    Checks: a computer is selected, the problem text is not empty, and the
    computer really exists in the database.
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
    options = {pc["id"]: pc for pc in all_pcs if room in ("All Rooms", pc["room"])}
    if not options:
        st.info("No computers found in " + room)
        return None
    return options[col_pc.selectbox(pc_label, list(options), key=key + "_pc",
                                    format_func=lambda pc_id: option_text(options[pc_id]))]


def pc_history(pc):
    """Maintenance records of exactly this PC (matched by ID, then room and code checked)."""
    return [r for r in db.get_maintenance_by_equipment(pc["id"])
            if r["room"] == pc["room"] and r["pc_code"] == pc["pc_code"]]


def show_status_metrics(counts, total, total_label, done_label):
    """Four metric cards: total, Pending, In Progress, completed."""
    labels = [total_label, "🟡 Pending", "🔵 In Progress", done_label]
    values = [total, *(counts[s] for s in MAINTENANCE_STATUSES)]
    for column, label, value in zip(st.columns(4), labels, values):
        column.metric(label, value)

def fresh_record(record):
    """Reload one record from the database (None when it was deleted meanwhile)."""
    return next((r for r in db.get_maintenance_by_equipment(record["equipment_id"])
                 if r["id"] == record["id"]), None)


def record_trail(pc_code):
    """Edit history of a PC's records, read from the audit log.

    Returns {record id: [audit rows, newest first]}.
    """
    trail = {}
    for log in db.get_audit_logs("EDIT_MAINTENANCE", "All", pc_code):
        found = TRAIL_ID.search(log["details"] or "")
        if found:
            trail.setdefault(int(found.group(1)), []).append(log)
    return trail


def show_trail(logs):
    """Show who edited a record and when (read only)."""
    if not logs:
        st.caption("No edits recorded: this record has not been updated since it was created.")
    for log in logs:
        st.caption(f"🕘 {log['timestamp']} · {log['username']} — {log['details']}")


def describe_changes(old, new):
    """Short text of what changed between the old record and the new values."""
    parts = [f"{label}: {old[field]} -> {new[field]}"
             for field, label in (("status", "Status"), ("maintenance_type", "Type"),
                                  ("maintenance_date", "Date")) if old[field] != new[field]]
    parts += [f"{label} edited" for field, label in
              (("reported_problem", "Problem"), ("action_taken", "Action"))
              if (old[field] or "") != (new[field] or "")]
    return "; ".join(parts)


def strip_tag(line):
    """A note line without its leading bullet, '[stamp | type | name]' or '[label]' tag."""
    return NOTE_TAG.sub("", line.strip()).strip()


def add_notes(old, new):
    """Append each new, non-duplicate problem/action line; keep existing entries first."""
    lines = [strip_tag(line) for line in (old or "").splitlines() if line.strip()]
    seen = {line.casefold() for line in lines}
    fresh = [clean for line in (new or "").splitlines()
             if (clean := strip_tag(line)) and clean.casefold() not in seen
             and not seen.add(clean.casefold())]
    return "\n".join(f"• {line}" for line in lines + fresh) if fresh else (old or "")


def problem_lines(text):
    """The problems of a note text, one per non-empty line, without bullets or tags."""
    return [strip_tag(line) for line in (text or "").splitlines() if line.strip()]


def problem_summary(text):
    """The single problem as text, or 'N problems' when there is more than one."""
    lines = problem_lines(text)
    return f"{len(lines)} problems" if len(lines) > 1 else (lines[0] if lines else "")


def bullet_list(text):
    """Markdown bullet rows, one per problem / action line."""
    return "\n".join("- " + line for line in problem_lines(text))


def is_duplicate_report(history, entry):
    """True when every submitted problem line is already recorded for that date/type."""
    wanted = {strip_tag(line).casefold() for line in entry["reported_problem"].splitlines()
              if strip_tag(line)}
    return bool(wanted) and any(
        r["maintenance_date"] == entry["maintenance_date"]
        and r["maintenance_type"] == entry["maintenance_type"]
        and wanted.issubset({strip_tag(line).casefold()
                             for line in (r["reported_problem"] or "").splitlines()})
        for r in history)


def open_record_of_type(history, maintenance_type):
    """Newest unresolved record of this issue type (None when there is none)."""
    return next((r for r in history if r["status"] in UNRESOLVED
                 and r["maintenance_type"] == maintenance_type), None)


# -- 2. SECTION: ADD MAINTENANCE RECORD
def save_maintenance(pc, entry, username):
    """Create a new maintenance record for `pc`, write the audit log and notify the user."""
    try:
        record_id = db.add_maintenance(
            dict(entry, pc_code=pc["pc_code"], room=pc["room"], created_by=username))
        db.add_audit_log(username, "ADD_MAINTENANCE", pc["room"], pc["pc_code"],
                         f"Record #{record_id} | Type: {entry['maintenance_type']} | "
                         f"Status: {entry['status']} | Problem: {entry['reported_problem'][:60]}")
        if entry["update_pc_status"] and entry["status"] != "Completed":
            db.update_equipment(pc["id"], dict(pc, status="Needs Maintenance"))
        clear_pending_report()
        toast_and_rerun("maint_table_version",
                        f"Maintenance record #{record_id} created for {pc['pc_code']}")
    except Exception as error:
        st.error("Failed to save maintenance record: " + str(error))


def clear_pending_report():
    """Forget the submitted report."""
    st.session_state.pop("maint_entry", None)


def merged_values(target, entry):
    """Values of the open record `target` once the new report `entry` is added to it.

    The new problem / action lines are added only when the record does not have them
    yet. A Completed report only makes the record In Progress; the status never moves
    backwards.
    """
    reported = entry["status"] if entry["status"] != "Completed" else "In Progress"
    return {"maintenance_date": target["maintenance_date"],
            "maintenance_type": target["maintenance_type"],
            "reported_problem": add_notes(target["reported_problem"], entry["reported_problem"]),
            "action_taken": add_notes(target["action_taken"], entry["action_taken"]),
            "status": max(target["status"], reported, key=MAINTENANCE_STATUSES.index)}


def add_to_record(pc, entry, target, new, changes, username):
    """After the user confirmed: save `new` into the open record, log it, tell the user."""
    try:
        db.update_maintenance(target["id"], new)
        db.add_audit_log(username, "EDIT_MAINTENANCE", pc["room"], pc["pc_code"],
                         f"Record #{target['id']} updated | New report added | {changes} | "
                         f"Problem: {entry['reported_problem'][:60]}")
        if entry["update_pc_status"] and new["status"] != "Completed":
            db.update_equipment(pc["id"], dict(pc, status="Needs Maintenance"))
        clear_pending_report()
        toast_and_rerun("maint_table_version",
                        f"Added to the existing {target['maintenance_type']} record "
                        f"#{target['id']} of {pc['pc_code']}")
    except Exception as error:
        st.error("Failed to update maintenance record: " + str(error))


def handle_submission(pc, entry, username):
    """Decide what to do with a submitted report (re-run until the user chooses).

    Steps:
      1. Read the PC's own history once; stop if the same report was already saved.
      2. Find the unresolved record (Pending / In Progress) of this PC with the SAME
         issue type. Completed records never count.
      3. None found -> create a new record.
      4. Found, but the problem is already in it -> tell the user, change nothing.
      5. Found -> show the record and the new problem and wait: the report is added
         to that existing record only when the user presses the Add button.
    """
    history = pc_history(pc)
    if is_duplicate_report(history, entry):
        clear_pending_report()
        st.error(f"⚠️ Accidental duplicate prevented: this same report for {pc['pc_code']} "
                 f"on {entry['maintenance_date']} is already recorded.")
        return
    target = open_record_of_type(history, entry["maintenance_type"])
    if target is None:
        save_maintenance(pc, entry, username)
        return
    new = merged_values(target, entry)
    if not (changes := describe_changes(target, new)):
        clear_pending_report()
        st.warning(f"⚠️ This problem is already in record #{target['id']} of {pc['pc_code']} "
                   f"({target['maintenance_type']}). Nothing was added.")
        return

    st.warning(f"⚠️ {pc['pc_code']} already has an open **{entry['maintenance_type']}** "
               f"record (#{target['id']}). A PC keeps one open record per issue type, so "
               f"your report can only be added to it as another problem.")
    st.markdown("**Existing record:**")
    show_record_details(target)
    st.markdown("**Your new report (not added yet):**")
    st.info(bullet_list(entry["reported_problem"]))
    col_add, col_cancel = st.columns(2)
    if col_add.button(f"➕ Add to existing record #{target['id']}", type="primary",
                      width="stretch"):
        add_to_record(pc, entry, target, new, changes, username)
    if col_cancel.button("Cancel", width="stretch", key="maint_cancel_add"):
        clear_pending_report()
        st.rerun()


def show_add_maintenance_form(username):
    """Form to record a new computer issue and maintenance activity.

    Steps:
      1. Load all computers; let the user pick a room, then a computer.
      2. Collect date, issue type, status, problem and initial action.
      3. On submit, validate the inputs.
      4. Create a new record, or add the problem to the PC's open record of the same
         issue type (see handle_submission), write the audit log and notify the user.
    """
    st.markdown("### ➕ Record New Computer Issue / Maintenance")
    st.caption("Log hardware or software issues, scheduled maintenance, or repairs.")

    all_pcs = db.get_all_equipment()
    if not all_pcs:
        st.warning("No computers found in the database. Add computers first in Equipment Monitoring.")
        return
    pc = pick_pc(all_pcs, ["All Rooms"] + ROOMS, "1. Filter by Room", "2. Select Computer *",
                 "add_maint", lambda pc: f"[{pc['room']}] {pc['pc_code']} — {pc['status']}")
    if pc is None:
        return

    with st.expander("ℹ️ Selected PC Specifications"):
        show_facts([("Code", pc["pc_code"]), ("Room", pc["room"]), ("Status", pc["status"]),
                    ("OS", pc["os"]), ("CPU", pc["cpu"]), ("RAM", f"{pc['ram_gb']} GB"),
                    ("Storage", pc["storage"]), ("GPU", pc["gpu"])])

    # Field keys include the PC and the save counter, so text typed for one PC (or left
    # over from the last saved report) never shows up in the form of another PC.
    k = f"{pc['id']}_{st.session_state.get('maint_table_version', 0)}"
    with st.form("form_add_maintenance_" + k):
        col_date, col_type, col_status = st.columns(3)
        maint_date = col_date.date_input("Maintenance Date *", value=date.today(), key="add_date_" + k)
        maint_type = col_type.selectbox("Issue / Maintenance Type *", MAINTENANCE_TYPES,
                                      key="add_type_" + k)
        status = col_status.selectbox("Status *", MAINTENANCE_STATUSES, key="add_status_" + k,
                                      help="A record saved as Completed is locked (delete-only).")
        reported_problem = st.text_area(
            "Reported Problem(s) / Issue Description *",
            placeholder="Describe the defect, error message, or routine check needed...",
            help="Required. Enter one or more problems, one per line; new unique lines append to an open record.",
            key="add_prob_" + k)
        action_taken = st.text_area(
            "Actions Taken / Initial Diagnosis",
            placeholder="Steps taken to diagnose or repair (optional if pending)...",
            help="What has been done so far to resolve the issue.", key="add_act_" + k)
        update_pc_status = st.checkbox(
            "Also update this PC's overall status to 'Needs Maintenance' in Equipment table",
            value=(status != "Completed" and pc["status"] == "Working"), key="add_flag_" + k)
        submitted = st.form_submit_button("Submit Maintenance Record", type="primary",
                                          width="stretch")
    if submitted:
        if error_msg := validation_error(pc["id"], reported_problem):
            clear_pending_report()
            st.error("Validation error: " + error_msg)
        else:  # keep the report in session state so it survives the confirmation step
            st.session_state["maint_entry"] = {
                "equipment_id": pc["id"], "maintenance_date": maint_date.strftime("%Y-%m-%d"),
                "maintenance_type": maint_type, "reported_problem": reported_problem.strip(),
                "action_taken": action_taken.strip(), "status": status,
                "update_pc_status": update_pc_status}
    entry = st.session_state.get("maint_entry")
    if entry and entry["equipment_id"] != pc["id"]:  # report of another PC: drop it
        clear_pending_report()
    elif entry:
        handle_submission(pc, entry, username)


# -- 3. EXPORT: PDF AND EXCEL
def build_maintenance_summary(records, filter_text, now):
    """Build one paragraph that explains the exported records.

    Steps:
      1. If there are no records, return a 'no records match' message.
      2. Count the records per status and per issue type.
      3. Work out the open records (Pending + In Progress), the most common
         issue type and the number of different PCs involved.
      4. Join everything into one paragraph.
    """
    if not records:
        return "No maintenance records match the selected filters."
    by_status = count_by(records, "status", MAINTENANCE_STATUSES)
    by_type = count_by(records, "maintenance_type", MAINTENANCE_TYPES)
    top_type = max(by_type, key=by_type.get)
    pcs = len({record["pc_code"] + record["room"] for record in records})
    return (f"As of {now:%B %d, %Y}, this report covers {len(records)} maintenance "
            f"record(s) for {pcs} PC(s). Filters: {filter_text}. Pending: "
            f"{by_status['Pending']}, in progress: {by_status['In Progress']}, "
            f"completed: {by_status['Completed']}. "
            f"{by_status['Pending'] + by_status['In Progress']} record(s) are still "
            f"open. The most common issue type is {top_type} ({by_type[top_type]}).")


@cached
def maintenance_png(by_status, by_type, for_pdf=False):
    """Two bar charts side by side: records per status and per issue type (PNG bytes)."""
    figure = Figure(figsize=(9, 3.8))
    status_axis, type_axis = figure.subplots(1, 2, gridspec_kw={"width_ratios": [1, 1.5]})
    bars = status_axis.bar(list(by_status), list(by_status.values()),
                           color=[MAINTENANCE_STATUS_COLORS[s] for s in by_status])
    status_axis.bar_label(bars, padding=2, fontsize=9)
    status_axis.set_title("Records by Status", fontweight="bold")
    status_axis.margins(y=0.15)
    status_axis.yaxis.set_major_locator(MaxNLocator(integer=True))
    bars = type_axis.barh(list(by_type), list(by_type.values()), color="#1b8fc9")
    type_axis.bar_label(bars, padding=2, fontsize=9)
    type_axis.invert_yaxis()
    type_axis.set_title("Records by Issue Type", fontweight="bold")
    type_axis.margins(x=0.12)
    type_axis.xaxis.set_major_locator(MaxNLocator(integer=True))
    for axis in (status_axis, type_axis):
        axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    return figure_png(figure, dpi=180 if for_pdf else 100)


def record_chart(records, for_pdf=False):
    """Chart PNG for these records, built from their status and type counts."""
    return maintenance_png(count_by(records, "status", MAINTENANCE_STATUSES),
                           count_by(records, "maintenance_type", MAINTENANCE_TYPES), for_pdf)


@cached
def build_maintenance_pdf(records, admin_name, filter_text, now):
    """Create the maintenance PDF report (landscape Letter) and return its bytes.

    Page order: header -> title -> summary -> charts -> table.

    Steps:
      1. Build the table: a header row, then one row per record. Long text is
         wrapped in Paragraphs; escape() keeps characters such as & and < from
         breaking the PDF.
      2. Style it (dark header, grid, alternating row colors, header repeated
         on every page).
      3. Put the story together and build the document.
    """
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small")
    small.fontSize, small.leading = 8, 10
    wrap = lambda text: Paragraph(escape(text).replace("\n", "<br/>"), small)

    data = [list(MAINTENANCE_LABELS.values())] + [[
        str(r["id"]), escape(r["pc_code"]), escape(r["room"]), r["maintenance_date"],
        wrap(r["maintenance_type"]), wrap(r["reported_problem"] or ""),
        wrap(r["action_taken"] or "-"), r["status"], escape(r["created_by"] or "")]
        for r in records]
    widths = [0.5, 0.8, 0.8, 0.8, 1.0, 2.5, 2.2, 0.7, 0.7]
    table = Table(data, colWidths=[w * inch for w in widths], repeatRows=1)
    table.setStyle(TableStyle(HEADER_STYLE + [
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f3f3")])]))

    return pdf_bytes([
        *pdf_top(styles, "Project C.L.A.U.S. - Maintenance Report", admin_name, now),
        Spacer(1, 10), Paragraph("Summary", styles["Heading2"]),
        Paragraph(escape(build_maintenance_summary(records, filter_text, now)),
                  styles["BodyText"]),
        Spacer(1, 8),
        Image(io.BytesIO(record_chart(records, True)), width=7 * inch, height=2.96 * inch),
        Spacer(1, 8), table],
        pagesize=landscape(letter), topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch)


@cached
def build_maintenance_excel(records, filter_text):
    """Create the maintenance Excel file (Summary + Records sheets), return its bytes.

    Summary rows: total, one row per status, one row per issue type; the
    filters that were used are written under the Summary table.
    """
    summary_rows = (
        [{"Category": "Total Records", "Count": len(records)}]
        + [{"Category": f"Status: {k}", "Count": v}
           for k, v in count_by(records, "status", MAINTENANCE_STATUSES).items()]
        + [{"Category": f"Type: {k}", "Count": v}
           for k, v in count_by(records, "maintenance_type", MAINTENANCE_TYPES).items()])
    return excel_bytes(
        {"Summary": pd.DataFrame(summary_rows),
         "Records": maintenance_frame(records, EXPORT_LABELS, short=False)},
        lambda sheet: sheet.cell(row=len(summary_rows) + 3, column=1,
                                 value="Filters: " + filter_text))


# -- 4. SECTION: VIEW & MANAGE ALL RECORDS (with Edit & Delete)
def show_edit_record_form(record, username):
    """Draw the form to edit an existing maintenance record.

    Steps:
      1. Reload the record; a Completed record is locked, so stop with a message.
      2. Fill the form fields with the record's current values.
      3. On Save, validate the inputs; stop when nothing changed or when the PC already
         has another open record of the chosen type.
      4. Update the database, write the audit log (what changed), reload.
    """
    record = fresh_record(record)
    if record is None:
        st.warning("This record no longer exists.")
        return
    rid = str(record["id"])
    if record["status"] == "Completed":
        st.markdown(f"#### 🔒 Maintenance Record `#{rid}` ({record['pc_code']}) is Completed")
        st.info("Completed records are locked and cannot be edited. "
                "Open the 🗑️ Delete Record tab if it has to be removed.")
        return
    st.markdown(f"#### ✏️ Edit Maintenance Record `#{rid}` ({record['pc_code']})")
    try:  # stored date text -> date
        current_date = datetime.strptime(record["maintenance_date"], "%Y-%m-%d").date()
    except Exception:
        current_date = date.today()

    with st.form("form_edit_maintenance_" + rid):
        col1, col2, col3 = st.columns(3)
        new_date = col1.date_input("Maintenance Date", value=current_date,
                                   key="edit_date_" + rid)
        new_type = col2.selectbox("Issue / Type", MAINTENANCE_TYPES, key="edit_type_" + rid,
                                  index=index_of(MAINTENANCE_TYPES, record["maintenance_type"]))
        new_status = col3.selectbox("Status", MAINTENANCE_STATUSES, key="edit_status_" + rid,
                                    index=index_of(MAINTENANCE_STATUSES, record["status"]),
                                    help="Once saved as Completed, the record is locked "
                                         "and can only be deleted.")
        new_problem = st.text_area("Reported Problem", value=record["reported_problem"],
                                   key="edit_prob_" + rid)
        new_action = st.text_area("Action Taken", value=record.get("action_taken") or "",
                                  key="edit_act_" + rid)
        saved = st.form_submit_button("Save Changes", type="primary", width="stretch")
    if not saved:
        return
    if error_msg := validation_error(record["equipment_id"], new_problem):
        st.error("Validation error: " + error_msg)
        return
    new = {"maintenance_date": new_date.strftime("%Y-%m-%d"), "maintenance_type": new_type,
           "reported_problem": new_problem.strip(), "action_taken": new_action.strip(),
           "status": new_status}
    if not (changes := describe_changes(record, new)):
        st.info("Nothing was changed, so nothing was saved.")
        return
    if new_status in UNRESOLVED and any(
            r["id"] != record["id"] and r["status"] in UNRESOLVED
            and r["maintenance_type"] == new_type for r in db.get_maintenance_by_equipment(
                record["equipment_id"])):
        st.error(f"{record['pc_code']} already has an open {new_type} record. Add the "
                 "problem to that record instead, or complete it first.")
        return

    try:
        db.update_maintenance(record["id"], new)
        db.add_audit_log(username, "EDIT_MAINTENANCE", record["room"], record["pc_code"],
                         f"Record #{rid} updated | {changes}")
        toast_and_rerun("maint_table_version", f"Record #{rid} updated.")
    except Exception as error:
        st.error("Error updating record: " + str(error))


def show_delete_record_section(record, username):
    """Draw the deletion confirmation section for a maintenance record.

    Steps: show the warning -> wait for the confirm button ->
           delete from the database, write the audit log, reload.
    """
    rid = str(record["id"])
    st.markdown(f"#### 🗑️ Delete Maintenance Record `#{rid}`")
    st.warning(f"Are you sure you want to delete this maintenance record for "
               f"**{record['pc_code']}** ({record['maintenance_date']})? "
               f"This action cannot be undone."
               + (" The Completed count will go down by one." if record["status"] == "Completed" else ""))
    if st.columns([1, 3])[0].button("Yes, permanently delete", type="primary",
                                    key="del_maint_" + rid):
        try:
            db.delete_maintenance(record["id"])
            db.add_audit_log(username, "DELETE_MAINTENANCE", record["room"], record["pc_code"],
                             f"Deleted maintenance record #{rid} ({record['maintenance_type']})")
            toast_and_rerun("maint_table_version", f"Maintenance record #{rid} deleted.", "🗑️")
        except Exception as error:
            st.error("Error deleting record: " + str(error))


def show_record_details(record):
    """Show the full details of one maintenance record (read only)."""
    show_facts([("Log ID", f"#{record['id']}"), ("PC Code", f"`{record['pc_code']}`"),
                ("Room", record["room"]),
                ("Status", STATUS_BADGES.get(record["status"], record["status"])),
                ("Date", record["maintenance_date"]), ("Type", record["maintenance_type"]),
                ("Logged By", record["created_by"]), ("Last Updated", record["updated_at"])])
    st.markdown(f"**Reported Problem(s) ({len(problem_lines(record['reported_problem']))}):**")
    st.info(bullet_list(record["reported_problem"]))
    st.markdown("**Action Taken:**")
    if (record.get("action_taken") or "").strip():
        st.success(bullet_list(record["action_taken"]))
    else:
        st.caption("No repair action recorded yet.")
    with st.expander("🕘 Edit history"):
        show_trail(record_trail(record["pc_code"]).get(record["id"], []))


def show_all_maintenance_records(username):
    """Display a searchable, filterable table of all maintenance activities.

    Steps:
      1. Show the filter boxes and fetch the matching records.
      2. Show the table with a color-coded status column.
      3. When a row is picked, show its details / edit / delete (only the chosen one runs).
    """
    st.markdown("### 📋 Maintenance Activity Logs")
    filters = filter_controls("v")
    records = db.get_all_maintenance(*filters)
    st.caption(f"{len(records)} maintenance records found.")
    if not records:
        st.info("No maintenance records match your filters.")
        return

    event = st.dataframe(
        status_table(maintenance_frame(records, MAINTENANCE_LABELS)),
        hide_index=True, width="stretch", height=320, selection_mode="single-row",
        on_select="rerun", key=f"maintenance_main_table_{st.session_state.get('maint_table_version', 0)}_{'|'.join(filters)}")
    selected = event.selection.rows
    if selected and selected[0] < len(records):
        record = records[selected[0]]
        st.divider()
        section = pick_section(["📄 Record Details", "✏️ Edit Record", "🗑️ Delete Record"],
                               "record_tab")
        if section == 0:
            show_record_details(record)
        elif section == 1:
            show_edit_record_form(record, username)
        else:
            show_delete_record_section(record, username)


# -- 5. SECTION: EXPORT REPORT
def show_export_tab(user):
    """Pick filters, preview the records, download PDF / Excel.

    Steps:
      1. Show the filter boxes and fetch the matching records.
      2. Show the status cards, charts, summary and a preview table.
      3. Show the PDF and Excel download buttons (each click is audit-logged).
    """
    st.markdown("### 📤 Export Maintenance Report")
    st.caption("Choose what to include, then download the report as PDF or Excel.")

    status_filter, type_filter, room_filter, search_query = filter_controls("x")
    records = db.get_all_maintenance(status_filter, type_filter, room_filter, search_query)
    st.caption(f"{len(records)} maintenance records will be exported.")
    if not records:
        st.info("No maintenance records match your filters.")
        return

    filter_text = (f"Status={status_filter}, Type={type_filter}, Room={room_filter}"
                   + (f", Search='{search_query}'" if search_query else ""))
    now = datetime.now().replace(second=0, microsecond=0)
    counts = count_by(records, "status", MAINTENANCE_STATUSES)
    show_status_metrics(counts, len(records), "Records to Export", "🟢 Completed")
    st.image(record_chart(records), width="stretch")
    st.markdown("**Summary**")
    st.info(build_maintenance_summary(records, filter_text, now))
    st.dataframe(status_table(maintenance_frame(records, EXPORT_LABELS)),
                 hide_index=True, width="stretch", height=320)

    st.divider()
    st.markdown("**Export**")
    stamp, details = f"{now:%Y%m%d_%H%M}", "Filters: " + filter_text
    show_pdf_excel_pair(
        ("⬇️ Download Maintenance PDF",
         lambda: build_maintenance_pdf(records, user["full_name"], filter_text, now),
         f"CLAUS_maintenance_{stamp}.pdf",
         (user["username"], "EXPORT_MAINTENANCE_PDF", details)),
        ("⬇️ Download Maintenance Excel",
         lambda: build_maintenance_excel(records, filter_text),
         f"CLAUS_maintenance_{stamp}.xlsx",
         (user["username"], "EXPORT_MAINTENANCE_EXCEL", details)))


# -- 6. SECTION: MAINTENANCE HISTORY PER COMPUTER
def show_computer_maintenance_history():
    """Display the complete maintenance history of one computer.

    Steps:
      1. Let the user pick a room and a PC.
      2. Read all maintenance records of that PC.
      3. Show summary cards (total issues, resolved, pending).
      4. Show the history table and one expandable card per event.
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
    history = pc_history(pc)

    st.markdown(f"#### PC Profile: `{pc['pc_code']}` ({pc['room']})")
    show_facts([("Current PC Status", pc["status"]), ("CPU", pc["cpu"]),
                ("RAM", f"{pc['ram_gb']} GB"), ("Storage", pc["storage"])])
    show_status_metrics(count_by(history, "status", MAINTENANCE_STATUSES), len(history),
                        "Total Issues Logged", "🟢 Resolved / Completed")

    st.divider()
    if not history:
        st.success("✅ This computer has no recorded maintenance issues. All clean!")
        return

    st.markdown("**Chronological History (Newest First):**")
    st.dataframe(status_table(maintenance_frame(history, HISTORY_LABELS)),
                 hide_index=True, width="stretch")
    st.markdown("**Detailed Timeline Cards:**")
    trail = record_trail(pc["pc_code"])
    for event in history:
        badge = STATUS_BADGES.get(event["status"], event["status"])
        with st.expander(f"{event['maintenance_date']} — {event['maintenance_type']} ({badge})"):
            st.markdown(f"**Reported Problem(s) ({len(problem_lines(event['reported_problem']))}):**\n\n"
                + bullet_list(event["reported_problem"]))
            st.markdown("**Action Taken:**\n\n" + (bullet_list(event["action_taken"])
                                                   or "_None recorded_"))
            st.caption(f"Logged by {event['created_by']} on {event.get('created_at', 'N/A')}"
                       f" | Last updated: {event.get('updated_at', 'N/A')}")
            st.markdown("**Edit history:**")
            show_trail(trail.get(event["id"], []))


# -- 7. MAIN INTERFACE
@st.fragment
def show_sections(user):
    """Section picker + the chosen section.

    A fragment: clicks inside it rerun only this part, and the three sections
    that are not chosen are not run at all (st.tabs would run all four).
    """
    section = pick_section(SECTIONS, "maint_tab")
    if section == 0:
        show_all_maintenance_records(user["username"])
    elif section == 1:
        show_add_maintenance_form(user["username"])
    elif section == 2:
        show_computer_maintenance_history()
    else:
        show_export_tab(user)


def render(user):
    """Main entry point of the Maintenance Tracking page.

    Steps:
      1. Show the page header and the overall metric cards.
      2. Show the four sections (see show_sections).
    """
    st.title("🔧 Computer Maintenance & Issue Tracking")
    st.caption("Monitor laboratory PC issues, maintenance schedules, and repair history.")
    counts = db.get_maintenance_status_counts()
    show_status_metrics(counts, sum(counts.values()), "Total Records", "🟢 Completed")
    st.divider()
    show_sections(user)