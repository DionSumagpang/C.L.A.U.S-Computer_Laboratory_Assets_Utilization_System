"""Main admin screen: sidebar menu and the page that was chosen."""
import pandas as pd
import streamlit as st

from assets.database import database as db
from modules import ROOMS, get_logo_path, subtitle_html
from modules import equipment, maintenance, reports
from modules.authentication import logout

MENU = ["🖥️ Equipment Monitoring", "🔧 Maintenance", "📊 Reports", "📜 Audit Logs"]

LOG_LABELS = {"timestamp": "Date & Time", "username": "User",
              "action": "Action", "room": "Room", "target": "PC / Target",
              "details": "Details"}

# Audit log actions are stored as short codes (EDIT_PC, ...). These are the
# readable texts shown to the admin. The stored codes never change, so old log
# entries and the filters keep working.
ACTION_LABELS = {
    "LOGIN": "Logged in",
    "LOGIN_FAILED": "Failed login",
    "LOGOUT": "Logged out",
    "SYSTEM": "System setup",
    "ADD_PC": "Added PC",
    "EDIT_PC": "Edited PC",
    "REMOVE_PC": "Removed PC",
    "ADD_MAINTENANCE": "Added maintenance record",
    "EDIT_MAINTENANCE": "Edited maintenance record",
    "DELETE_MAINTENANCE": "Deleted maintenance record",
    "EXPORT_PDF": "Exported equipment report (PDF)",
    "EXPORT_EXCEL": "Exported equipment records (Excel)",
    "EXPORT_MAINTENANCE_PDF": "Exported maintenance report (PDF)",
    "EXPORT_MAINTENANCE_EXCEL": "Exported maintenance report (Excel)",
}


def action_label(action):
    """Readable text for a stored action code, e.g. EDIT_PC -> Edited PC.

    A code that is not in ACTION_LABELS is shown with the underscores removed.
    """
    return ACTION_LABELS.get(action, action.replace("_", " ").capitalize())


def render_audit_logs():
    """Draw the audit log page.

    Steps:
      1. Read the available actions and users for the filter boxes.
      2. Let the admin pick an action, a user and/or type a search word.
      3. Ask the database for the matching log entries.
      4. Show them in a table (newest first), with each action written
         in plain words (see action_label).
    """
    st.subheader("📜 Audit Logs")
    st.caption("Every login, edit, removal, addition and export is recorded here.")

    action_options = ["All"] + sorted(db.get_audit_values("action"),
                                      key=action_label)
    user_options = ["All"] + db.get_audit_values("username")

    col_action, col_user, col_search = st.columns([1, 1, 2])
    action_filter = col_action.selectbox("Action", action_options,
                                         format_func=action_label)
    user_filter = col_user.selectbox("User", user_options)
    search = col_search.text_input("🔍 Search", placeholder="PC code, room, details...")

    logs = db.get_audit_logs(action_filter, user_filter, search)
    st.caption(f"{len(logs)} entries shown (latest 500 at most)")

    table = pd.DataFrame(logs, columns=list(LOG_LABELS)).rename(columns=LOG_LABELS)
    table["Action"] = table["Action"].map(action_label)
    st.dataframe(table, hide_index=True, width="stretch", height=500)


def render():
    """Draw the sidebar, then the page that matches the chosen menu item.

    Steps:
      1. Show logo, admin name/role, menu and the Log out button.
      2. If 'Equipment Monitoring': one tab per room -> render_room.
      3. If 'Maintenance': show the maintenance tracking page.
      4. If 'Reports': show the report page.
      5. If 'Audit Logs': show the audit log page.
    """
    user = st.session_state["user"]

    with st.sidebar:
        st.image(get_logo_path(), width="stretch")
        st.markdown(subtitle_html("0.85rem"), unsafe_allow_html=True)
        st.divider()
        st.markdown(f"**{user['full_name']}**  \n{user['role']}")
        st.divider()
        page = st.radio("Menu", MENU, label_visibility="collapsed")
        st.divider()
        if st.button("Log out", width="stretch"):
            logout()

    if page == MENU[0]:
        st.title("CpE Laboratory Equipment Monitoring")
        for tab, room in zip(st.tabs(["🏫 " + room for room in ROOMS]), ROOMS):
            with tab:
                equipment.render_room(room)
    elif page == MENU[1]:
        maintenance.render(user)
    elif page == MENU[2]:
        reports.render(user)
    else:
        render_audit_logs()
