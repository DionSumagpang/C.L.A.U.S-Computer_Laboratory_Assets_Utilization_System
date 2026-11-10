"""Equipment page for one room: pie summary, search, table, edit, remove, add.

Plain functions only. All database work is done by assets/database/database.py.
"""
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from assets.database import database as db
from modules import STATUSES, STATUS_COLORS
from modules.reports import pie_figure

TABLE_COLUMNS = ["pc_code", "cpu", "ram_gb", "storage", "gpu", "os",
                 "monitor", "status", "last_updated"]
TABLE_LABELS = {"pc_code": "PC Code", "cpu": "CPU", "ram_gb": "RAM (GB)",
                "storage": "Storage", "gpu": "GPU", "os": "OS",
                "monitor": "Monitor", "status": "Status",
                "last_updated": "Last Updated"}
FIELD_ORDER = ["cpu", "ram_gb", "storage", "gpu", "os", "monitor", "status"]


# ---------------------------------------------------------------------------
# Small helper functions
# ---------------------------------------------------------------------------
def color_status(value):
    """Return the CSS style for a status cell in the table."""
    if value in STATUS_COLORS:
        color = STATUS_COLORS[value]
        return ("background-color:" + color + "33;color:" + color +
                ";font-weight:600")
    return ""


def filter_rows(rows, search_word, status_filter):
    """Keep only the PCs that match the search word and the status filter.

    Steps:
      1. Go through every PC.
      2. Skip it if a status filter is set and the status is different.
      3. If a search word is set, check every column; skip the PC when
         none of them contains the word (ignoring upper/lower case).
      4. Otherwise keep the PC.
    """
    kept = []
    word = search_word.lower()

    for row in rows:
        if status_filter != "All" and row["status"] != status_filter:
            continue

        if word != "":
            text = " ".join(str(row[column]) for column in TABLE_COLUMNS)
            if word not in text.lower():
                continue

        kept.append(row)
    return kept


def describe_changes(old_row, new_values):
    """Build a text like 'status: Working -> Defective; ram_gb: 8 -> 16'.

    Returns an empty text when nothing changed.
    """
    changes = []
    for field in FIELD_ORDER:
        old_value = str(old_row[field])
        new_value = str(new_values[field])
        if old_value != new_value:
            changes.append(field + ": " + old_value + " -> " + new_value)
    return "; ".join(changes)


def show_pc_form(prefix, row):
    """Draw the PC input boxes and return what the admin typed as a dict.

    `row` holds the current values (use an empty dict for a new PC).
    """
    col1, col2 = st.columns(2)

    cpu = col1.text_input("CPU", row.get("cpu", ""), key=prefix + "_cpu")
    ram = col2.number_input("RAM (GB)", 1, 512, int(row.get("ram_gb", 8)),
                            key=prefix + "_ram")
    storage = col1.text_input("Storage", row.get("storage", ""),
                              key=prefix + "_storage")
    gpu = col2.text_input("GPU", row.get("gpu", ""), key=prefix + "_gpu")
    os_name = col1.text_input("OS", row.get("os", ""), key=prefix + "_os")
    monitor = col2.text_input("Monitor", row.get("monitor", ""),
                              key=prefix + "_monitor")

    current_status = row.get("status", STATUSES[0])
    status = st.selectbox("Status", STATUSES,
                          index=STATUSES.index(current_status),
                          key=prefix + "_status")

    return {"cpu": cpu, "ram_gb": ram, "storage": storage, "gpu": gpu,
            "os": os_name, "monitor": monitor, "status": status}


# ---------------------------------------------------------------------------
# Page sections
# ---------------------------------------------------------------------------
def show_summary(room, counts, total):
    """Draw the pie chart (left) and the four number cards (right)."""
    left, right = st.columns([1, 1.3])

    with left:
        figure = pie_figure(room, counts)
        st.pyplot(figure)
        plt.close(figure)

    with right:
        row1 = st.columns(2)
        row2 = st.columns(2)
        row1[0].metric("Total PCs", total)
        row1[1].metric("🟢 Working", counts["Working"])
        row2[0].metric("🔴 Defective", counts["Defective"])
        row2[1].metric("🟡 Needs Maintenance", counts["Needs Maintenance"])


def show_edit_and_remove(room, row, username, slug):
    """Draw the Edit and Remove tabs for the selected PC.

    Edit steps:  read form -> validate CPU -> find changes ->
                 if no changes show a message, else save + audit log.
    Remove steps: confirm button -> delete + audit log.
    """
    pc_code = row["pc_code"]
    st.markdown("#### Selected: `" + pc_code + "`")
    tab_edit, tab_remove = st.tabs(["✏️ Edit", "🗑️ Remove"])

    with tab_edit:
        new_values = show_pc_form("edit_" + slug + "_" + str(row["id"]), row)
        if st.button("Save changes", type="primary",
                     key="save_" + slug + "_" + str(row["id"])):
            if new_values["cpu"].strip() == "":
                st.error("CPU cannot be empty.")
            else:
                changes = describe_changes(row, new_values)
                if changes == "":
                    st.info("No changes to save.")
                else:
                    db.update_equipment(int(row["id"]), new_values)
                    db.add_audit_log(username, "EDIT_PC", room, pc_code,
                                     changes)
                    st.session_state["table_version"] += 1
                    st.toast(pc_code + " updated.", icon="✅")
                    st.rerun()

    with tab_remove:
        st.warning("This will permanently delete **" + pc_code +
                   "** from " + room + ".")
        if st.button("Yes, remove this PC", type="primary",
                     key="remove_" + slug + "_" + str(row["id"])):
            db.delete_equipment(int(row["id"]))
            details = ("Removed PC (" + str(row["cpu"]) + ", status was " +
                       str(row["status"]) + ")")
            db.add_audit_log(username, "REMOVE_PC", room, pc_code, details)
            st.session_state["table_version"] += 1
            st.toast(pc_code + " removed.", icon="🗑️")
            st.rerun()


def show_add_form(room, username, slug):
    """Draw the 'Add a new PC' section and save the new PC when asked."""
    with st.expander("➕ Add a new PC to " + room):
        values = show_pc_form("add_" + slug, {})
        if st.button("Add PC", key="add_button_" + slug):
            if values["cpu"].strip() == "":
                st.error("CPU cannot be empty.")
            else:
                new_code = db.add_equipment(room, values)
                details = ("Added PC (" + values["cpu"] + ", status " +
                           values["status"] + ")")
                db.add_audit_log(username, "ADD_PC", room, new_code, details)
                st.session_state["table_version"] += 1
                st.toast(new_code + " added.", icon="✅")
                st.rerun()


# ---------------------------------------------------------------------------
# Main function of this file
# ---------------------------------------------------------------------------
def render_room(room):
    """Draw the whole tab of one laboratory room.

    Steps:
      1. Read the PCs and status counts of the room from the database.
      2. Show the summary (pie chart + number cards).
      3. Show the search box and status filter, then filter the PCs.
      4. Show the table; the admin can tick one row.
      5. If a row is ticked, show the Edit / Remove tabs for it.
      6. Show the 'Add a new PC' section.
    """
    username = st.session_state["user"]["username"]
    slug = room.replace(" ", "_")
    if "table_version" not in st.session_state:
        st.session_state["table_version"] = 0

    rows = db.get_equipment_by_room(room)
    counts = db.get_status_counts(room)
    show_summary(room, counts, len(rows))

    col_search, col_status = st.columns([3, 1])
    search_word = col_search.text_input(
        "🔍 Search", key="search_" + slug,
        placeholder="PC code, CPU, OS, GPU, ...")
    status_filter = col_status.selectbox(
        "Status", ["All"] + STATUSES, key="filter_" + slug)
    shown_rows = filter_rows(rows, search_word, status_filter)

    st.caption("Click the checkbox at the left of a row to edit or remove that PC.")
    table = pd.DataFrame(shown_rows, columns=TABLE_COLUMNS)
    table = table.rename(columns=TABLE_LABELS)
    table_key = "table_" + slug + "_" + str(st.session_state["table_version"])
    event = st.dataframe(
        table.style.map(color_status, subset=["Status"]),
        hide_index=True, width="stretch", height=380,
        on_select="rerun", selection_mode="single-row", key=table_key)

    selected_rows = event.selection.rows
    if len(selected_rows) > 0 and selected_rows[0] < len(shown_rows):
        selected_pc = shown_rows[selected_rows[0]]
        show_edit_and_remove(room, selected_pc, username, slug)

    show_add_form(room, username, slug)
