"""Audit Logs page: shows who did what and when, with simple filters."""
import pandas as pd
import streamlit as st

from assets.database import database as db

LOG_COLUMNS = ["timestamp", "username", "action", "room", "target", "details"]
LOG_LABELS = {"timestamp": "Date & Time", "username": "User",
              "action": "Action", "room": "Room", "target": "PC / Target",
              "details": "Details"}


def render_audit_logs():
    """Draw the audit log page.

    Steps:
      1. Read the available actions and users for the filter boxes.
      2. Let the admin pick an action, a user and/or type a search word.
      3. Ask the database for the matching log entries.
      4. Show them in a table (newest first).
    """
    st.subheader("📜 Audit Logs")
    st.caption("Every login, edit, removal, addition and export is recorded here.")

    action_options = ["All"] + db.get_audit_actions()
    user_options = ["All"] + db.get_audit_users()

    col_action, col_user, col_search = st.columns([1, 1, 2])
    action_filter = col_action.selectbox("Action", action_options)
    user_filter = col_user.selectbox("User", user_options)
    search = col_search.text_input("🔍 Search", placeholder="PC code, room, details...")

    logs = db.get_audit_logs(action_filter, user_filter, search)
    st.caption(str(len(logs)) + " entries shown (latest 500 at most)")

    table = pd.DataFrame(logs, columns=LOG_COLUMNS)
    table = table.rename(columns=LOG_LABELS)
    st.dataframe(table, hide_index=True, width="stretch", height=500)
