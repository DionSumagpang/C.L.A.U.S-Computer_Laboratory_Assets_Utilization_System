"""Project C.L.A.U.S. - shared constants and logo helpers (no database code)."""
import os

import streamlit as st

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

LOGO_DARK = os.path.join(ASSETS_DIR, "logo.png")             # full logo (browser tab icon)
LOGO_MARK_DARK = os.path.join(ASSETS_DIR, "logo_mark.png")   # logo without subtitle
LOGO_MARK_LIGHT = os.path.join(ASSETS_DIR, "logo_mark_light.png")
SUBTITLE = "Computer Laboratory Assets Utilization System"

ROOMS = ["CpE Lab 1", "CpE Lab 2", "CpE Lab 3"]
STATUSES = ["Working", "Defective", "Needs Maintenance"]
STATUS_COLORS = {
    "Working": "#2e9e5b",
    "Defective": "#d64545",
    "Needs Maintenance": "#e8a317",
}

# How many sample PCs are created per room on first run
ROOM_SIZES = {"CpE Lab 1": 30, "CpE Lab 2": 25, "CpE Lab 3": 20}


def is_dark_theme():
    """True when the app is shown in the dark theme."""
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def get_logo_path():
    """Logo picture (without subtitle) that suits the current theme."""
    if is_dark_theme():
        return LOGO_MARK_DARK
    return LOGO_MARK_LIGHT


def subtitle_html(font_size):
    """The subtitle under the logo as large, readable, centered text."""
    color = "#6cc8f5" if is_dark_theme() else "#1a6fb0"
    return ("<p style='text-align:center;font-weight:700;letter-spacing:1px;"
            "text-transform:uppercase;line-height:1.3;margin:0 0 8px 0;"
            "color:" + color + ";font-size:" + font_size + "'>"
            + SUBTITLE + "</p>")
