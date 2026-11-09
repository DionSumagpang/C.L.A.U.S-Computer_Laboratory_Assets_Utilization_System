"""Project C.L.A.U.S. - ALL database code lives in this file.

Only plain functions are used (no classes). Every function does one job:

  Low-level helpers : get_connection, run_query, run_command, now_text
  Setup             : create_tables, seed_admins, seed_equipment, init_db
  Admin table       : get_admin
  Equipment table   : get_equipment_by_room, get_status_counts,
                      next_pc_code, add_equipment, update_equipment,
                      delete_equipment
  Audit log table   : add_audit_log, get_audit_logs,
                      get_audit_actions, get_audit_users

Data is passed around as plain dictionaries and lists.
"""
import os
import random
import sqlite3
from datetime import datetime

import bcrypt

from modules import ROOM_SIZES, STATUSES

DB_FOLDER = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_FOLDER, "claus.db")

# ---------------------------------------------------------------------------
# Sample data used to fill an empty database
# ---------------------------------------------------------------------------
# (username, full name, role). Demo password for everyone: Claus@2026
ADMIN_SAMPLES = [
      ("payengmahinhin", "Natalie Faye A. Claus", "Laboratory Head"),
      ("alniangsoftspoken", "Alnia Victoria B. Capulong", "Laboratory Technician"),
      ("nerishinggutom", "Nerish Regonay C. Peria", "CpE Faculty"),
      ("kurttalldarkhandsome", "Kurt D. Raz", "Laboratory Assistant"),
  ]
DEMO_PASSWORD = "Claus@2026"

CPU_CHOICES = ["Intel Core i3-10100", "Intel Core i5-10400",
               "Intel Core i5-12400", "Intel Core i7-12700",
               "AMD Ryzen 5 5600G", "AMD Ryzen 7 5700G"]
RAM_CHOICES = [8, 16, 16, 32]
STORAGE_CHOICES = ["256GB SSD", "512GB SSD", "1TB HDD",
                   "512GB SSD + 1TB HDD"]
GPU_CHOICES = ["Integrated Graphics", "Integrated Graphics",
               "NVIDIA GTX 1650", "NVIDIA RTX 3050",
               "AMD Radeon RX 6500 XT"]
OS_CHOICES = ["Windows 10 Pro", "Windows 11 Pro", "Ubuntu 22.04 LTS"]
MONITOR_CHOICES = ['21.5" Dell', '23.8" Acer', '24" ViewSonic', '27" LG']


# ===========================================================================
# LOW-LEVEL HELPERS
# ===========================================================================
def get_connection():
    """Open the SQLite file. Rows can be read like dictionaries."""
    os.makedirs(DB_FOLDER, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def run_query(sql, params=()):
    """Run a SELECT and return the rows as a list of dictionaries.

    Steps:
      1. Open connection.
      2. Execute the SQL and fetch every row.
      3. Close the connection.
      4. Convert each row to a dictionary and return the list.
    """
    connection = get_connection()
    try:
        cursor = connection.execute(sql, params)
        rows = cursor.fetchall()
    finally:
        connection.close()

    result = []
    for row in rows:
        result.append(dict(row))
    return result


def run_command(sql, params=()):
    """Run an INSERT / UPDATE / DELETE / CREATE and save the change.

    Steps:
      1. Open connection.
      2. Execute the SQL.
      3. Commit (save) and close the connection.
    """
    connection = get_connection()
    try:
        connection.execute(sql, params)
        connection.commit()
    finally:
        connection.close()


def now_text():
    """Current local date and time as text, e.g. 2026-11-08 14:30:00."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ===========================================================================
# SETUP
# ===========================================================================
def create_tables():
    """Create the three tables if they do not exist yet."""
    run_command(
        """CREATE TABLE IF NOT EXISTS admins (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               username TEXT UNIQUE NOT NULL,
               full_name TEXT NOT NULL,
               role TEXT NOT NULL,
               password_hash TEXT NOT NULL)""")

    run_command(
        """CREATE TABLE IF NOT EXISTS equipment (
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
               last_updated TEXT)""")

    run_command(
        """CREATE TABLE IF NOT EXISTS audit_logs (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               timestamp TEXT NOT NULL,
               username TEXT NOT NULL,
               action TEXT NOT NULL,
               room TEXT,
               target TEXT,
               details TEXT)""")


def seed_admins():
    """Insert the sample admins when the admins table is empty.

    Returns True if data was added, otherwise False.
    """
    rows = run_query("SELECT COUNT(*) AS total FROM admins")
    if rows[0]["total"] > 0:
        return False

    password_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(),
                                  bcrypt.gensalt()).decode()
    for sample in ADMIN_SAMPLES:
        username = sample[0]
        full_name = sample[1]
        role = sample[2]
        run_command(
            "INSERT INTO admins (username, full_name, role, password_hash) "
            "VALUES (?, ?, ?, ?)",
            (username, full_name, role, password_hash))
    return True


def seed_equipment():
    """Insert random PCs into every room when the equipment table is empty.

    Returns True if data was added, otherwise False.
    """
    rows = run_query("SELECT COUNT(*) AS total FROM equipment")
    if rows[0]["total"] > 0:
        return False

    for room in ROOM_SIZES:
        lab_number = room.split()[-1]
        number_of_pcs = ROOM_SIZES[room]

        for pc_number in range(1, number_of_pcs + 1):
            pc_code = "L" + lab_number + "-PC" + str(pc_number).zfill(2)
            # 70% working, 15% defective, 15% needs maintenance
            status = random.choices(STATUSES, weights=[70, 15, 15])[0]
            run_command(
                """INSERT INTO equipment
                   (pc_code, room, cpu, ram_gb, storage, gpu, os, monitor,
                    status, last_updated)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (pc_code, room, random.choice(CPU_CHOICES),
                 random.choice(RAM_CHOICES), random.choice(STORAGE_CHOICES),
                 random.choice(GPU_CHOICES), random.choice(OS_CHOICES),
                 random.choice(MONITOR_CHOICES), status, now_text()))
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


# ===========================================================================
# ADMIN TABLE
# ===========================================================================
def get_admin(username):
    """Return the admin dictionary for this username, or None if not found."""
    rows = run_query("SELECT * FROM admins WHERE username = ?", (username,))
    if len(rows) == 0:
        return None
    return rows[0]


# ===========================================================================
# EQUIPMENT TABLE
# ===========================================================================
def get_equipment_by_room(room):
    """Return every PC in one room (list of dictionaries), sorted by code."""
    return run_query(
        "SELECT * FROM equipment WHERE room = ? ORDER BY pc_code", (room,))


def get_status_counts(room):
    """Return how many PCs are in each status, e.g.
    {"Working": 20, "Defective": 3, "Needs Maintenance": 2}.

    Steps:
      1. Start every status at 0.
      2. Ask the database to count PCs per status for this room.
      3. Copy the counts into the dictionary.
    """
    counts = {}
    for status in STATUSES:
        counts[status] = 0

    rows = run_query(
        "SELECT status, COUNT(*) AS total FROM equipment "
        "WHERE room = ? GROUP BY status", (room,))
    for row in rows:
        counts[row["status"]] = row["total"]
    return counts


def next_pc_code(room):
    """Build the next free PC code for a room, e.g. L1-PC31.

    Steps:
      1. Read all existing PCs of the room.
      2. Find the biggest PC number.
      3. Return the room's lab number + (biggest + 1).
    """
    lab_number = room.split()[-1]
    biggest = 0
    for pc in get_equipment_by_room(room):
        number = int(pc["pc_code"].split("PC")[-1])
        if number > biggest:
            biggest = number
    return "L" + lab_number + "-PC" + str(biggest + 1).zfill(2)


def add_equipment(room, values):
    """Insert a new PC and return its new code.

    `values` is a dictionary with: cpu, ram_gb, storage, gpu, os, monitor,
    status.
    """
    pc_code = next_pc_code(room)
    run_command(
        """INSERT INTO equipment
           (pc_code, room, cpu, ram_gb, storage, gpu, os, monitor, status,
            last_updated)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (pc_code, room, values["cpu"], values["ram_gb"], values["storage"],
         values["gpu"], values["os"], values["monitor"], values["status"],
         now_text()))
    return pc_code


def update_equipment(pc_id, values):
    """Overwrite the details of one PC with the new `values` dictionary."""
    run_command(
        """UPDATE equipment
           SET cpu = ?, ram_gb = ?, storage = ?, gpu = ?, os = ?,
               monitor = ?, status = ?, last_updated = ?
           WHERE id = ?""",
        (values["cpu"], values["ram_gb"], values["storage"], values["gpu"],
         values["os"], values["monitor"], values["status"], now_text(),
         pc_id))


def delete_equipment(pc_id):
    """Remove one PC from the database."""
    run_command("DELETE FROM equipment WHERE id = ?", (pc_id,))


# ===========================================================================
# AUDIT LOG TABLE
# ===========================================================================
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


def get_audit_logs(action_filter="All", user_filter="All", search="",
                   limit=500):
    """Return audit log entries (newest first) that match the filters.

    Steps:
      1. Start with a list of conditions that is empty.
      2. Add a condition for every filter the user actually used.
      3. Join the conditions with AND, sort newest first, apply the limit.
    """
    conditions = []
    params = []

    if action_filter != "All":
        conditions.append("action = ?")
        params.append(action_filter)

    if user_filter != "All":
        conditions.append("username = ?")
        params.append(user_filter)

    if search != "":
        conditions.append("(details LIKE ? OR target LIKE ? OR room LIKE ?)")
        pattern = "%" + search + "%"
        params.append(pattern)
        params.append(pattern)
        params.append(pattern)

    sql = "SELECT * FROM audit_logs"
    if len(conditions) > 0:
        sql = sql + " WHERE " + " AND ".join(conditions)
    sql = sql + " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    return run_query(sql, tuple(params))


def get_audit_actions():
    """Distinct action names found in the audit log (for the filter box)."""
    rows = run_query("SELECT DISTINCT action FROM audit_logs ORDER BY action")
    names = []
    for row in rows:
        names.append(row["action"])
    return names


def get_audit_users():
    """Distinct usernames found in the audit log (for the filter box)."""
    rows = run_query(
        "SELECT DISTINCT username FROM audit_logs ORDER BY username")
    names = []
    for row in rows:
        names.append(row["username"])
    return names
