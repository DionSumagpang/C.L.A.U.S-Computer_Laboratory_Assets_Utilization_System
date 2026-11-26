# C.L.A.U.S. - Computer Laboratory Assets Utilization System

Streamlit app for monitoring laboratory PCs (CPE LAB 1, CPE LAB 2, Com LAB 3) (Batangas State University).

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
(Equipment Monitoring, Maintenance Tracking, Equipment Summary, Audit Logs).

## Files and functions

| File | Purpose | Main functions |
|---|---|---|
| `main.py` | Entry point | - |
| `modules/__init__.py` | Constants, logo/subtitle helpers, shared UI helpers | `get_logo_path`, `subtitle_html`, `status_styled`, `count_by`, `pick_section`, `toast_and_rerun` |
| `modules/authentication.py` | Login / logout | `check_login`, `login_page`, `logout` |
| `modules/dashboard.py` | Sidebar menu, page switch, audit log page (fragment) | `render`, `render_audit_logs`, `action_label` |
| `modules/equipment.py` | Room picker + room page: view, search, edit, remove, add PCs | `render`, `render_room`, `filter_rows`, `show_edit_and_remove`, `show_add_form` |
| `modules/maintenance.py` | Maintenance tracking, issue logs, history & PDF/Excel export | `pick_pc`, `show_facts`, `show_add_maintenance_form`, `show_all_maintenance_records`, `show_edit_record_form`, `show_delete_record_section`, `show_computer_maintenance_history`, `show_export_tab`, `build_maintenance_pdf`, `build_maintenance_excel`, `show_sections`, `render` |
| `modules/reports.py` | Charts, summary text, PDF and Excel export (charts/exports are cached) | `pie_png`, `bar_png`, `warm_charts`, `build_summary_paragraph`, `build_pdf`, `build_excel`, `pdf_bytes`, `excel_bytes`, `show_pdf_excel_pair`, `render` (fragment) |
| `assets/database/database.py` | All SQLite code | `run_query`, `run_one`, `run_command`, `where_sql`, `init_db`, `get_*`, `add_*`, `update_*`, `delete_*` |

## Conventions

- Plain functions only (no classes); each function does one job.
- Each docstring lists its **Steps**, which map directly to pseudocode and flowchart blocks.
- Login errors use built-in exceptions: `ValueError` (empty field), `LookupError` (unknown user), `PermissionError` (wrong password).
- Every login, edit, add, remove, maintenance action, and export is written to the audit log. Actions are stored as short codes (e.g. `EDIT_PC`) and shown in plain words ("Edited PC") on the Audit Logs page.

## Speed notes

- **Only the section you are looking at is run.** Room tabs (Equipment) and the
  four Maintenance sections use `pick_section` (a tab-style row of choices)
  instead of `st.tabs`. `st.tabs` runs the code of *every* tab on every click;
  `pick_section` runs just the chosen one.
- **Clicks rerun only their own page.** The Equipment, Maintenance sections,
  Reports and Audit Logs pages are `st.fragment`s, so picking a table row,
  switching a room/section or (de)selecting rooms in Reports no longer redraws
  the sidebar and the rest of the app. After a save, edit or delete the whole
  app reloads (`toast_and_rerun`) so the metric cards stay correct.
- **Typing does not rerun the page.** The Edit PC and Add PC boxes are in an
  `st.form`: nothing is sent to Python until *Save changes* / *Add PC* is pressed
  (before, every box that lost focus reran the whole room page).
- Charts are drawn with matplotlib's `Figure` (not `pyplot`) and saved as PNG
  bytes; `warm_charts` (called from `main.setup`) draws the room pies and the
  all-rooms bar chart once at app start, so the first visits are instant. The PNGs, the PDF files and the Excel files are cached with
  `st.cache_data`. The cache key is the data itself (plus the admin name and the
  current minute for exports), so any edit shows up immediately while an
  unchanged rerun costs almost nothing.
- Status counts are calculated from the rows that are already loaded
  (`count_by`) instead of asking the database again.
- The sample data is inserted in one database transaction.
- Three database indexes (`idx_audit_action`, `idx_audit_username`,
  `idx_maintenance_pc`) are created by `init_db` (`IF NOT EXISTS`, existing rows
  and columns are untouched). They keep the Audit Logs filter lists and the
  per-PC maintenance lookups fast as the tables grow.
- Trade-off: Streamlit forgets the filter/search boxes of a section that is not
  drawn, so they reset when you switch to another section (they already reset
  when you switch pages in the sidebar).

## Rooms and sample data

| Room | PCs | PC codes |
|---|---|---|
| CPE LAB 1 | 16 | L1-PC01 to L1-PC16 |
| CPE LAB 2 | 26 | L2-PC01 to L2-PC26 |
| Com LAB 3 | 29 | L3-PC01 to L3-PC29 |

On first run the database is filled with sample PCs that get random specs and a
random status (70% Working, 15% Defective, 15% Needs Maintenance). Room names
and sizes are set in `modules/__init__.py` (`ROOMS`, `ROOM_SIZES`). After
changing them, delete `assets/database/claus.db` and restart the app to rebuild
the sample data.

## Maintenance report export

The Maintenance page has an **Export Report** tab. Pick the filters (status,
issue type, room, search), check the preview, then download a PDF (landscape
Letter) or an Excel file (Summary + Records sheets). Each download is written to
the audit log as `EXPORT_MAINTENANCE_PDF` or `EXPORT_MAINTENANCE_EXCEL`.

## Database tables

- `admins` (username, full_name, role, password_hash)
- `equipment` (pc_code, room, cpu, ram_gb, storage, gpu, os, monitor, status, last_updated)
- `maintenance` (equipment_id, pc_code, room, maintenance_date, maintenance_type, reported_problem, action_taken, status, created_by, created_at, updated_at)
- `audit_logs` (timestamp, username, action, room, target, details)
