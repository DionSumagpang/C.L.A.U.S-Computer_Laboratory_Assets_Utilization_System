"""Project C.L.A.U.S. entry point.  Run with:  python -m streamlit run main.py

Program flow:
  1. Set up the page.
  2. Prepare the database (create tables / sample data if needed).
  3. If nobody is logged in -> show the login page.
     Otherwise            -> show the dashboard.
"""
import streamlit as st

from assets.database import database as db
from modules import LOGO_PATH
from modules import authentication, dashboard

st.set_page_config(page_title="C.L.A.U.S.", page_icon=LOGO_PATH,
                   layout="wide")

db.init_db()

if "user" not in st.session_state:
    authentication.login_page()
else:
    dashboard.render()
