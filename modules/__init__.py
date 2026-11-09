"""Project C.L.A.U.S. - shared constants (no classes, no database code here)."""
import os

import streamlit as st

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")

ROOMS = ["CpE Lab 1", "CpE Lab 2", "CpE Lab 3"]
STATUSES = ["Working", "Defective", "Needs Maintenance"]
STATUS_COLORS = {
    "Working": "#2e9e5b",
    "Defective": "#d64545",
    "Needs Maintenance": "#e8a317",
}

# How many sample PCs are created per room on first run
ROOM_SIZES = {"CpE Lab 1": 30, "CpE Lab 2": 25, "CpE Lab 3": 20}


def get_logo_path():
    """Return the C.L.A.U.S. logo file."""
    return LOGO_PATH
