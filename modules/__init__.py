"""Project C.L.A.U.S. - shared constants and logo helpers (no database code)."""
import os

import streamlit as st

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

LOGO_DARK = os.path.join(ASSETS_DIR, "logo.png")             # full logo (browser tab icon)
LOGO_MARK_DARK = os.path.join(ASSETS_DIR, "logo_mark.png")   # logo without subtitle
LOGO_MARK_LIGHT = os.path.join(ASSETS_DIR, "logo_mark_light.png")
SUBTITLE = "Computer Laboratory Assets Utilization System"

ROOMS = ["CPE LAB 1", "CPE LAB 2", "Com LAB 3"]
STATUSES = ["Working", "Defective", "Needs Maintenance"]
STATUS_COLORS = {
    "Working": "#2e9e5b",
    "Defective": "#d64545",
    "Needs Maintenance": "#e8a317",
}

# Maintenance constants
MAINTENANCE_STATUSES = ["Pending", "In Progress", "Completed"]
MAINTENANCE_STATUS_COLORS = {
    "Pending": "#e8a317",
    "In Progress": "#1b8fc9",
    "Completed": "#2e9e5b",
}
MAINTENANCE_TYPES = [
    "Hardware Repair",
    "Software Issue",
    "Preventive Maintenance",
    "Component Upgrade",
    "Network / Connectivity",
    "Other",
]

# How many sample PCs are created per room on first run.
# Room names must match ROOMS above. PC codes are built from the LAST word of
# the room name (e.g. "Com LAB 3" -> L3-PC01), so keep the lab number last.
# Each PC gets a random status (70% Working, 15% Defective,
# 15% Needs Maintenance) and random specs - see seed_equipment() in
# assets/database/database.py. To apply new sizes to an existing database,
# delete assets/database/claus.db and restart the app.
ROOM_SIZES = {"CPE LAB 1": 16, "CPE LAB 2": 26, "Com LAB 3": 29}


def is_dark_theme():
    """True when the app is shown in the dark theme."""
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def get_logo_path():
    """Logo picture (without subtitle) that suits the current theme."""
    return LOGO_MARK_DARK if is_dark_theme() else LOGO_MARK_LIGHT


def subtitle_html(font_size):
    """The subtitle under the logo as large, readable, centered text."""
    color = "#6cc8f5" if is_dark_theme() else "#1a6fb0"
    return ("<p style='text-align:center;font-weight:700;letter-spacing:1px;"
            "text-transform:uppercase;line-height:1.3;margin:0 0 8px 0;"
            f"color:{color};font-size:{font_size}'>{SUBTITLE}</p>")


def status_styled(df, palette):
    """Color the 'Status' column of a dataframe."""
    return df.style.map(
        lambda value: (f"background-color:{palette[value]}33;"
                       f"color:{palette[value]};font-weight:600"
                       if value in palette else ""), subset=["Status"])


def count_by(records, field, choices):
    """Count the records per value of `field`, e.g. {"Pending": 2, ...}.

    Every choice starts at 0; values that are not in `choices` are ignored.
    """
    counts = dict.fromkeys(choices, 0)
    for record in records:
        if record[field] in counts:
            counts[record[field]] += 1
    return counts


def toast_and_rerun(version_key, message, icon="✅"):
    """Bump a session counter (forces table redraw), show a toast, reload."""
    st.session_state[version_key] = st.session_state.get(version_key, 0) + 1
    st.toast(message, icon=icon)
    st.rerun()
