"""Equipment page for one room: pie summary, search, table, edit, remove, add.

Plain functions only. All database work is done by assets/database/database.py.
"""
import pandas as pd
import streamlit as st

from assets.database import database as db
from modules import (ROOMS, STATUSES, STATUS_COLORS, count_by, pick_section,
                     status_styled, toast_and_rerun)
from modules.reports import EQUIPMENT_COLUMNS, pie_png

TABLE_LABELS = {"pc_code": "PC Code", "cpu": "CPU", "ram_gb": "RAM (GB)",
                "storage": "Storage", "gpu": "GPU", "os": "OS",
                "monitor": "Monitor", "status": "Status", "last_updated": "Last Updated"}


# -- Small helper functions
def filter_rows(rows, search_word, status_filter):
    """Keep only the PCs that match the search word and the status filter.

    A PC is kept when its status fits the filter ("All" fits everything) and,
    if a search word is set, any column contains it (ignoring upper/lower case).
    """
    word = search_word.lower()
    return [row for row in rows
            if status_filter in ("All", row["status"])
            and (not word or word in " ".join(
                str(row[column]) for column in EQUIPMENT_COLUMNS).lower())]


def describe_changes(old_row, new_values):
    """Text like 'status: Working -> Defective; ram_gb: 8 -> 16' ('' if unchanged)."""
    return "; ".join(f"{field}: {old_row[field]} -> {new_values[field]}"
                     for field in db.PC_FIELDS
                     if str(old_row[field]) != str(new_values[field]))


def show_pc_form(prefix, row, button, **button_options):
    """Draw the PC input boxes and a submit button; return (values, pressed).

    `values` is what the admin typed, as a dict. `row` holds the current values
    (use an empty dict for a new PC). The boxes sit in a form, so nothing is
    sent to Python (and the page does not rerun) until the button is pressed.
    """
    with st.form(prefix + "_form", border=False):
        col1, col2 = st.columns(2)
        cpu = col1.text_input("CPU", row.get("cpu", ""), key=prefix + "_cpu")
        ram = col2.number_input("RAM (GB)", 1, 512, int(row.get("ram_gb", 8)), key=prefix + "_ram")
        storage = col1.text_input("Storage", row.get("storage", ""), key=prefix + "_storage")
        gpu = col2.text_input("GPU", row.get("gpu", ""), key=prefix + "_gpu")
        os_name = col1.text_input("OS", row.get("os", ""), key=prefix + "_os")
        monitor = col2.text_input("Monitor", row.get("monitor", ""), key=prefix + "_monitor")
        status = st.selectbox("Status", STATUSES, key=prefix + "_status",
                              index=STATUSES.index(row.get("status", STATUSES[0])))
        pressed = st.form_submit_button(button, **button_options)
    return {"cpu": cpu, "ram_gb": ram, "storage": storage, "gpu": gpu,
            "os": os_name, "monitor": monitor, "status": status}, pressed


# -- Page sections
def show_summary(room, counts, total):
    """Draw the pie chart (left) and the four number cards (right)."""
    left, right = st.columns([1, 1.3])
    left.image(pie_png(room, counts), width="stretch")
    cards = [("Total PCs", total), ("🟢 Working", counts["Working"]),
             ("🔴 Defective", counts["Defective"]),
             ("🟡 Needs Maintenance", counts["Needs Maintenance"])]
    with right:
        for column, (label, value) in zip(st.columns(2) + st.columns(2), cards):
            column.metric(label, value)


def show_edit_and_remove(room, row, username, slug):
    """Draw the Edit / Remove choice for the selected PC (only the chosen one runs).

    Edit steps:   read form -> validate CPU -> find changes ->
                  if no changes show a message, else save + audit log.
    Remove steps: confirm button -> delete + audit log.
    """
    pc_code, key = row["pc_code"], f"{slug}_{row['id']}"
    st.markdown(f"#### Selected: `{pc_code}`")

    if pick_section(["✏️ Edit", "🗑️ Remove"], "pc_tab") == 0:
        new_values, pressed = show_pc_form("edit_" + key, row, "Save changes", type="primary")
        if pressed:
            if new_values["cpu"].strip() == "":
                st.error("CPU cannot be empty.")
            elif (changes := describe_changes(row, new_values)) == "":
                st.info("No changes to save.")
            else:
                db.update_equipment(int(row["id"]), new_values)
                db.add_audit_log(username, "EDIT_PC", room, pc_code, changes)
                toast_and_rerun("table_version", f"{pc_code} updated.")

    else:
        st.warning(f"This will permanently delete **{pc_code}** from {room}.")
        if st.button("Yes, remove this PC", type="primary", key="remove_" + key):
            db.delete_equipment(int(row["id"]))
            db.add_audit_log(username, "REMOVE_PC", room, pc_code,
                             f"Removed PC ({row['cpu']}, status was {row['status']})")
            toast_and_rerun("table_version", f"{pc_code} removed.", "🗑️")


def show_add_form(room, username, slug):
    """Draw the 'Add a new PC' section and save the new PC when asked."""
    with st.expander(f"➕ Add a new PC to {room}"):
        values, pressed = show_pc_form("add_" + slug, {}, "Add PC")
        if pressed:
            if values["cpu"].strip() == "":
                st.error("CPU cannot be empty.")
            else:
                new_code = db.add_equipment(room, values)
                db.add_audit_log(username, "ADD_PC", room, new_code,
                                 f"Added PC ({values['cpu']}, status {values['status']})")
                toast_and_rerun("table_version", f"{new_code} added.")


# -- Main functions of this file
def render_room(room):
    """Draw the whole page of one laboratory room.

    Steps:
      1. Read the PCs of the room and count the statuses.
      2. Show the summary (pie chart + number cards).
      3. Show the search box and status filter, then filter the PCs.
      4. Show the table; the admin can tick one row.
      5. If a row is ticked, show the Edit / Remove tabs for it.
      6. Show the 'Add a new PC' section.
    """
    username, slug = st.session_state["user"]["username"], room.replace(" ", "_")
    rows = db.get_equipment_by_room(room)
    show_summary(room, count_by(rows, "status", STATUSES), len(rows))

    col_search, col_status = st.columns([3, 1])
    search_word = col_search.text_input("🔍 Search", key="search_" + slug,
                                        placeholder="PC code, CPU, OS, GPU, ...")
    status_filter = col_status.selectbox("Status", ["All"] + STATUSES, key="filter_" + slug)
    shown_rows = filter_rows(rows, search_word, status_filter)

    st.caption("Click the checkbox at the left of a row to edit or remove that PC.")
    table = pd.DataFrame(shown_rows, columns=EQUIPMENT_COLUMNS).rename(columns=TABLE_LABELS)
    event = st.dataframe(
        status_styled(table, STATUS_COLORS), hide_index=True, width="stretch",
        height=380, on_select="rerun", selection_mode="single-row",
        key=f"table_{slug}_{st.session_state.get('table_version', 0)}")

    selected = event.selection.rows
    if selected and selected[0] < len(shown_rows):
        show_edit_and_remove(room, shown_rows[selected[0]], username, slug)
    show_add_form(room, username, slug)


@st.fragment
def render():
    """Room picker + the chosen room's page.

    This is a fragment: clicks inside it rerun only this part (not the sidebar),
    and only the chosen room is drawn, instead of all three rooms at once.
    """
    render_room(ROOMS[pick_section(["🏫 " + room for room in ROOMS], "room_tab")])
