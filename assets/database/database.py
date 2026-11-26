"""Project C.L.A.U.S. - ALL database code lives in this file.

Plain functions only (no classes); data is passed around as dictionaries and lists.
  Helpers     : get_connection, run_query, run_one, run_command, where_sql, now_text
  Setup       : create_tables, seed_admins, seed_equipment, init_db
  Admins      : get_admin
  Equipment   : get_equipment_by_room, next_pc_code, add_equipment, update_equipment,
                delete_equipment, get_all_equipment, get_equipment_by_id
  Maintenance : add_maintenance, get_all_maintenance, get_maintenance_by_equipment,
                check_maintenance_duplicate, update_maintenance, delete_maintenance,
                get_maintenance_status_counts
  Audit log   : add_audit_log, get_audit_logs, get_audit_values
"""
import os
import random
import sqlite3
from contextlib import closing
from datetime import datetime

import bcrypt

from modules import MAINTENANCE_STATUSES, ROOM_SIZES, STATUSES

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claus.db")

# (username, full name, role). Demo password for everyone: Claus@2026
ADMIN_SAMPLES = [
    ("natalieclaus", "Natalie Faye C. Claus", "Laboratory Head"),
    ("alniacapulong", "Alnia Victoria R. Capulong", "Laboratory Technician"),
    ("nerishperia", "Nerish R. Peria", "CpE Faculty"),
    ("kurtraz", "Kurt Adrielle D. Raz", "Laboratory Assistant"),
]
DEMO_PASSWORD = "Claus@2026"

CPU_CHOICES = ["Intel Core i3-10100", "Intel Core i5-10400",
               "Intel Core i5-12400", "Intel Core i7-12700",
               "AMD Ryzen 5 5600G", "AMD Ryzen 7 5700G"]
RAM_CHOICES = [8, 16, 16, 32]
STORAGE_CHOICES = ["256GB SSD", "512GB SSD", "1TB HDD", "512GB SSD + 1TB HDD"]
GPU_CHOICES = ["Integrated Graphics", "Integrated Graphics",
               "NVIDIA GTX 1650", "NVIDIA RTX 3050", "AMD Radeon RX 6500 XT"]
OS_CHOICES = ["Windows 10 Pro", "Windows 11 Pro", "Ubuntu 22.04 LTS"]
MONITOR_CHOICES = ['21.5" Dell', '23.8" Acer', '24" ViewSonic', '27" LG']

PC_FIELDS = ("cpu", "ram_gb", "storage", "gpu", "os", "monitor", "status")

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pc_code TEXT UNIQUE NOT NULL,
    room TEXT NOT NULL,
    cpu TEXT,
    ram_gb INTEGER,
    storage TEXT,
    gpu TEXT,
    os TEXT,
    monitor TEXT,
    status TEXT NOT NULL,
    last_updated TEXT);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    room TEXT,
    target TEXT,
    details TEXT);
CREATE TABLE IF NOT EXISTS maintenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id INTEGER NOT NULL,
    pc_code TEXT NOT NULL,
    room TEXT NOT NULL,
    maintenance_date TEXT NOT NULL,
    maintenance_type TEXT NOT NULL,
    reported_problem TEXT NOT NULL,
    action_taken TEXT,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (equipment_id) REFERENCES equipment(id));
-- Indexes only speed up reads (audit filter lists, per-PC maintenance lookups).
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_username ON audit_logs(username);
CREATE INDEX IF NOT EXISTS idx_maintenance_pc
    ON maintenance(equipment_id, maintenance_date, maintenance_type);
"""
EQUIPMENT_INSERT = """INSERT INTO equipment
    (pc_code, room, cpu, ram_gb, storage, gpu, os, monitor, status, last_updated)
    VALUES (?,?,?,?,?,?,?,?,?,?)"""
EQUIPMENT_UPDATE = ("UPDATE equipment SET " + ", ".join(f"{f} = ?" for f in PC_FIELDS)
                    + ", last_updated = ? WHERE id = ?")
MAINTENANCE_ORDER = " ORDER BY maintenance_date DESC, id DESC"


# -- LOW-LEVEL HELPERS
def get_connection():
    """Open the SQLite file. Rows can be read like dictionaries."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def run_query(sql, params=()):
    """Run a SELECT and return the rows as a list of dictionaries."""
    with closing(get_connection()) as connection:
        return [dict(row) for row in connection.execute(sql, params)]


def run_one(sql, params=()):
    """Run a SELECT and return the first row as a dictionary (or None)."""
    with closing(get_connection()) as connection:
        row = connection.execute(sql, params).fetchone()
    return dict(row) if row else None


def run_command(sql, params=(), many=False):
    """Run an INSERT / UPDATE / DELETE, save the change, return the new row ID.

    With many=True, `params` is a list of parameter tuples (one INSERT each,
    all saved together in one go).
    """
    with closing(get_connection()) as connection, connection:  # commits
        run = connection.executemany if many else connection.execute
        return run(sql, params).lastrowid


def where_sql(filters):
    """Join the used filters into (' WHERE a AND b', params).

    Each filter is a (condition, params) pair, or a falsy value when that
    filter was not used (it is then skipped).
    """
    used = [f for f in filters if f]
    sql = " WHERE " + " AND ".join(cond for cond, _ in used) if used else ""
    return sql, [p for _, values in used for p in values]


def now_text():
    """Current local date and time as text, e.g. 2026-11-08 14:30:00."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# -- SETUP
def create_tables():
    """Create the four tables and their indexes if they do not exist yet."""
    with closing(get_connection()) as connection:
        connection.executescript(SCHEMA)


def is_empty(table):
    """True when the table has no rows."""
    return run_one(f"SELECT COUNT(*) AS total FROM {table}")["total"] == 0


def seed_admins():
    """Insert the sample admins when the admins table is empty.

    Returns True if data was added, otherwise False.
    """
    if not is_empty("admins"):
        return False
    password_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(),
                                  bcrypt.gensalt()).decode()
    run_command("INSERT INTO admins (username, full_name, role, password_hash) "
                "VALUES (?, ?, ?, ?)",
                [sample + (password_hash,) for sample in ADMIN_SAMPLES],
                many=True)
    return True


def seed_equipment():
    """Insert random PCs into every room when the equipment table is empty.

    Returns True if data was added, otherwise False.
    """
    if not is_empty("equipment"):
        return False
    stamp = now_text()
    rows = [
        (f"L{room.split()[-1]}-PC{number:02d}", room,
         random.choice(CPU_CHOICES), random.choice(RAM_CHOICES),
         random.choice(STORAGE_CHOICES), random.choice(GPU_CHOICES),
         random.choice(OS_CHOICES), random.choice(MONITOR_CHOICES),
         # 70% working, 15% defective, 15% needs maintenance
         random.choices(STATUSES, weights=[70, 15, 15])[0], stamp)
        for room, size in ROOM_SIZES.items()
        for number in range(1, size + 1)]
    run_command(EQUIPMENT_INSERT, rows, many=True)
    return True


def init_db():
    """Prepare the database. Safe to call on every app start.

    Steps:
      1. Create the tables.
      2. Fill admins and equipment with sample data if they are empty.
      3. If anything was added, write a SYSTEM entry in the audit log.
    """
    create_tables()
    admins_added = seed_admins()
    equipment_added = seed_equipment()
    if admins_added or equipment_added:
        add_audit_log("SYSTEM", "SYSTEM", "", "",
                      "Database created and filled with sample data")


# -- ADMIN TABLE
def get_admin(username):
    """Return the admin dictionary for this username, or None if not found."""
    return run_one("SELECT * FROM admins WHERE username = ?", (username,))


# -- EQUIPMENT TABLE
def get_equipment_by_room(room):
    """Return every PC in one room (list of dictionaries), sorted by code."""
    return run_query(
        "SELECT * FROM equipment WHERE room = ? ORDER BY pc_code", (room,))


def next_pc_code(room):
    """Build the next free PC code for a room, e.g. L1-PC31.

    Steps:
      1. Read all existing PCs of the room.
      2. Find the biggest PC number.
      3. Return the room's lab number + (biggest + 1).
    """
    numbers = [int(digits) for pc in get_equipment_by_room(room)
               if (digits := pc["pc_code"].split("PC")[-1]).isdecimal()]
    return f"L{room.split()[-1]}-PC{max(numbers, default=0) + 1:02d}"


def add_equipment(room, values):
    """Insert a new PC and return its new code.

    `values` is a dictionary with: cpu, ram_gb, storage, gpu, os, monitor,
    status.
    """
    pc_code = next_pc_code(room)
    run_command(EQUIPMENT_INSERT, (pc_code, room, *(values[f] for f in PC_FIELDS), now_text()))
    return pc_code


def update_equipment(pc_id, values):
    """Overwrite the details of one PC with the new `values` dictionary."""
    run_command(EQUIPMENT_UPDATE, (*(values[f] for f in PC_FIELDS), now_text(), pc_id))


def get_all_equipment():
    """Return every PC across all rooms, sorted by room and pc_code."""
    return run_query("SELECT * FROM equipment ORDER BY room, pc_code")


def get_equipment_by_id(pc_id):
    """Return one PC dictionary by its database ID, or None if not found."""
    return run_one("SELECT * FROM equipment WHERE id = ?", (pc_id,))


def delete_equipment(pc_id):
    """Remove one PC and all its maintenance records from the database.

    Both deletes are saved together, so no orphan maintenance logs remain.
    """
    with closing(get_connection()) as connection, connection:  # commits
        connection.execute("DELETE FROM maintenance WHERE equipment_id = ?",
                           (pc_id,))
        connection.execute("DELETE FROM equipment WHERE id = ?", (pc_id,))


# -- MAINTENANCE TABLE
def add_maintenance(values):
    """Insert a new maintenance record and return its new database ID.

    `values` is a dictionary with: equipment_id, pc_code, room,
    maintenance_date, maintenance_type, reported_problem, action_taken,
    status, created_by.
    """
    now = now_text()
    return run_command(
        """INSERT INTO maintenance
           (equipment_id, pc_code, room, maintenance_date, maintenance_type,
            reported_problem, action_taken, status, created_by, created_at,
            updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (values["equipment_id"], values["pc_code"], values["room"],
         values["maintenance_date"], values["maintenance_type"],
         values["reported_problem"], values.get("action_taken", ""),
         values["status"], values["created_by"], now, now))


def get_all_maintenance(status_filter="All", type_filter="All",
                        room_filter="All", search=""):
    """Return maintenance records that match the filters, newest date first.

    Steps:
      1. Add a condition for every filter that is not "All" / empty
         (the search looks in pc_code, reported_problem, action_taken and
         created_by).
      2. Query the database, ordered by maintenance_date DESC, id DESC.
    """
    search = search.strip()
    sql, params = where_sql([
        status_filter != "All" and ("status = ?", [status_filter]),
        type_filter != "All" and ("maintenance_type = ?", [type_filter]),
        room_filter != "All" and ("room = ?", [room_filter]),
        search != "" and (
            "(pc_code LIKE ? OR reported_problem LIKE ? OR "
            "action_taken LIKE ? OR created_by LIKE ?)", [f"%{search}%"] * 4),
    ])
    return run_query("SELECT * FROM maintenance" + sql + MAINTENANCE_ORDER,
                     params)


def get_maintenance_by_equipment(equipment_id):
    """Return all maintenance records for one computer, sorted newest first."""
    return run_query("SELECT * FROM maintenance WHERE equipment_id = ?"
                     + MAINTENANCE_ORDER, (equipment_id,))


def check_maintenance_duplicate(equipment_id, maintenance_date,
                                maintenance_type):
    """Return True if an identical record exists for this PC, date, and type."""
    return run_one("SELECT 1 AS found FROM maintenance WHERE equipment_id = ? "
                   "AND maintenance_date = ? AND maintenance_type = ?",
                   (equipment_id, maintenance_date, maintenance_type)) is not None


def update_maintenance(record_id, values):
    """Overwrite the details of one maintenance record with new values."""
    run_command(
        """UPDATE maintenance
           SET maintenance_date = ?, maintenance_type = ?,
               reported_problem = ?, action_taken = ?,
               status = ?, updated_at = ?
           WHERE id = ?""",
        (values["maintenance_date"], values["maintenance_type"],
         values["reported_problem"], values.get("action_taken", ""),
         values["status"], now_text(), record_id))


def delete_maintenance(record_id):
    """Remove one maintenance record from the database by its ID."""
    run_command("DELETE FROM maintenance WHERE id = ?", (record_id,))


def get_maintenance_status_counts():
    """Return how many maintenance records are in each status.

    Returns: {'Pending': x, 'In Progress': y, 'Completed': z}
    """
    totals = {row["status"]: row["total"] for row in run_query(
        "SELECT status, COUNT(*) AS total FROM maintenance GROUP BY status")}
    return {status: totals.get(status, 0) for status in MAINTENANCE_STATUSES}


# -- AUDIT LOG TABLE
def add_audit_log(username, action, room="", target="", details=""):
    """Write one line to the audit log.

    A problem while logging must never crash the app, so errors are only
    printed to the terminal.
    """
    try:
        run_command(
            """INSERT INTO audit_logs
               (timestamp, username, action, room, target, details)
               VALUES (?,?,?,?,?,?)""",
            (now_text(), username, action, room, target, details))
    except Exception as error:
        print("Audit log failed:", error)


def get_audit_logs(action_filter="All", user_filter="All", search=""):
    """Return the latest 500 audit log entries (newest first) that match.

    Steps:
      1. Add a condition for every filter the user actually used.
      2. Join the conditions with AND, sort newest first, keep 500.
    """
    sql, params = where_sql([
        action_filter != "All" and ("action = ?", [action_filter]),
        user_filter != "All" and ("username = ?", [user_filter]),
        search != "" and ("(details LIKE ? OR target LIKE ? OR room LIKE ?)",
                          [f"%{search}%"] * 3),
    ])
    return run_query("SELECT * FROM audit_logs" + sql
                     + " ORDER BY id DESC LIMIT 500", params)


def get_audit_values(column):
    """Distinct values of 'action' or 'username' in the audit log (filter boxes)."""
    return [row[column] for row in run_query(
        f"SELECT DISTINCT {column} FROM audit_logs ORDER BY {column}")]
