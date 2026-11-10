"""Main admin screen: sidebar menu and the page that was chosen."""
import streamlit as st

from modules import ROOMS, get_logo_path, subtitle_html
from modules import audit, equipment, reports
from modules.authentication import logout

MENU = ["🖥️ Equipment Monitoring", "📊 Reports", "📜 Audit Logs"]


def render():
    """Draw the sidebar, then the page that matches the chosen menu item.

    Steps:
      1. Show logo, admin name/role, menu and the Log out button.
      2. If 'Equipment Monitoring': one tab per room -> render_room.
      3. If 'Reports': show the report page.
      4. If 'Audit Logs': show the audit log page.
    """
    user = st.session_state["user"]

    with st.sidebar:
        st.image(get_logo_path(), width="stretch")
        st.markdown(subtitle_html("0.85rem"), unsafe_allow_html=True)
        st.divider()
        st.markdown("**" + user["full_name"] + "**  \n" + user["role"])
        st.divider()
        page = st.radio("Menu", MENU, label_visibility="collapsed")
        st.divider()
        if st.button("Log out", width="stretch"):
            logout()

    if page == MENU[0]:
        st.title("CpE Laboratory Equipment Monitoring")
        tab_names = []
        for room in ROOMS:
            tab_names.append("🏫 " + room)
        tabs = st.tabs(tab_names)

        for index, room in enumerate(ROOMS):
            with tabs[index]:
                equipment.render_room(room)
    elif page == MENU[1]:
        reports.render(user)
    else:
        audit.render_audit_logs()
