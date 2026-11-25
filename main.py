"""Project C.L.A.U.S. entry point.  Run with:  python -m streamlit run main.py

Program flow:
  1. Set up the page.
  2. Prepare the database (create tables / sample data if needed).
  3. If nobody is logged in -> show the login page.
     Otherwise            -> show the dashboard.
"""
import streamlit as st

from assets.database import database as db
from modules import LOGO_DARK
from modules import authentication, dashboard
from modules.reports import warm_charts

st.set_page_config(page_title="C.L.A.U.S.", page_icon=LOGO_DARK,
                   layout="wide")
# Hides Streamlit's "Press Enter to submit form" hint under every input box
# (Enter still submits). st.html with only a <style> takes no space on the page.
st.html("<style>[data-testid='InputInstructions']{display:none}</style>")


@st.cache_resource
def setup():
    db.init_db()


setup()
warm_charts()

if "user" not in st.session_state:
    authentication.login_page()
else:
    dashboard.render()
