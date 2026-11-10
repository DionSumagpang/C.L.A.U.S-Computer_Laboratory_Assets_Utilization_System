# C.L.A.U.S. - Computer Laboratory Assets Utilization System

Streamlit app for monitoring CpE laboratory PCs (Batangas State University).

## Run

```
pip install -r requirements.txt
python -m streamlit run main.py
```

Demo password for all accounts: `Claus@2026`

| Username | Name | Role |
|---|---|---|
| natalieclaus | Natalie Faye C. Claus | Laboratory Head |
| alniacapulong | Alnia Victoria R. Capulong | Laboratory Technician |
| nerishperia | Nerish R. Peria | CpE Faculty |
| kurtraz | Kurt Adrielle D. Raz | Laboratory Assistant |

## Program flow

`main.py` -> `init_db()` -> logged in? **no:** login page / **yes:** dashboard
(Equipment Monitoring, Reports, Audit Logs).

## Files and functions

| File | Purpose | Main functions |
|---|---|---|
| `main.py` | Entry point | - |
| `modules/__init__.py` | Constants, logo and subtitle helpers | `get_logo_path`, `subtitle_html` |
| `modules/authentication.py` | Login / logout | `check_login`, `login_page`, `logout` |
| `modules/dashboard.py` | Sidebar menu and page switch | `render` |
| `modules/equipment.py` | Room tab: view, search, edit, remove, add PCs | `render_room`, `filter_rows`, `show_edit_and_remove`, `show_add_form` |
| `modules/reports.py` | Charts, summary text, PDF and Excel export | `bar_figure`, `build_summary_paragraph`, `build_pdf`, `build_excel`, `render` |
| `modules/audit.py` | Audit log page with filters | `render_audit_logs` |
| `assets/database/database.py` | All SQLite code | `run_query`, `run_command`, `init_db`, `get_*`, `add_*`, `update_equipment`, `delete_equipment` |

## Conventions

- Plain functions only (no classes); each function does one job.
- Each docstring lists its **Steps**, which map directly to pseudocode and flowchart blocks.
- Login errors use built-in exceptions: `ValueError` (empty field), `LookupError` (unknown user), `PermissionError` (wrong password).
- Every login, edit, add, remove and export is written to the audit log.

## Database tables

`admins` (username, full_name, role, password_hash) - `equipment` (pc_code, room, cpu, ram_gb, storage, gpu, os, monitor, status, last_updated) - `audit_logs` (timestamp, username, action, room, target, details)
