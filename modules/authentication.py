"""Admin login. Plain functions only (no custom classes).

Login result is reported with Python's built-in exceptions:
  ValueError      -> a field was left empty
  LookupError     -> the username is not in the database
  PermissionError -> the username exists but the password is wrong
"""
import bcrypt
import streamlit as st

from assets.database import database as db
from modules import get_logo_path, subtitle_html


# Hides Streamlit's "Press Enter to submit form" hint under the login boxes.
# Enter still submits the form. The style is only added on the login page.
HIDE_INPUT_HINT = ("<style>[data-testid='InputInstructions'] "
                   "{display:none}</style>")


def check_login(username, password):
    """Check the typed username and password.

    Steps:
      1. Remove spaces around the username.
      2. If username or password is empty -> raise ValueError.
      3. Look the username up in the database.
      4. If it is not found -> raise LookupError.
      5. Compare the password with the stored bcrypt hash.
      6. If it does not match -> raise PermissionError.
      7. Otherwise return the admin's username, full name and role.
    """
    username = username.strip()
    if username == "" or password == "":
        raise ValueError("Please enter both username and password.")

    admin = db.get_admin(username)
    if admin is None:
        raise LookupError(f"User '{username}' is not in the database. "
                          "Only authorized personnel may access C.L.A.U.S.")
    if not bcrypt.checkpw(password.encode(), admin["password_hash"].encode()):
        raise PermissionError("Incorrect password. Please try again.")

    return {"username": admin["username"],
            "full_name": admin["full_name"],
            "role": admin["role"]}


def login_page():
    """Draw the login screen and handle the Log in button.

    Steps:
      1. Hide the input hint, then show the logo, title and the
         username/password form.
      2. When the button is pressed, call check_login inside try/except.
      3. On success: save the user in session, write LOGIN to the audit
         log, and reload the page.
      4. On each kind of failure: show the matching message and write
         LOGIN_FAILED to the audit log (except for empty fields).
    """
    st.markdown(HIDE_INPUT_HINT, unsafe_allow_html=True)
    _, middle, _ = st.columns([1, 1.2, 1])

    with middle:
        logo_column = st.columns([1, 2.4, 1])[1]
        logo_column.image(get_logo_path(), width="stretch")
        st.markdown(subtitle_html("1.15rem"), unsafe_allow_html=True)
        st.markdown(
            "<p style='text-align:center;color:gray'>"
            "CpE Faculty · Batangas State University</p>",
            unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            pressed = st.form_submit_button("Log in", type="primary",
                                            width="stretch")

        if pressed:
            typed_name = username.strip()[:50]
            try:
                user = check_login(username, password)
                st.session_state["user"] = user
                db.add_audit_log(user["username"], "LOGIN", "", "",
                                 "Logged in")
                st.rerun()
            except ValueError as error:
                st.warning(str(error))
            except LookupError as error:
                db.add_audit_log(typed_name, "LOGIN_FAILED", "", "",
                                 "Username not found")
                st.error(f"🚫 Access denied: {error}")
            except PermissionError as error:
                db.add_audit_log(typed_name, "LOGIN_FAILED", "", "",
                                 "Wrong password")
                st.error(f"🔒 {error}")
            except Exception as error:
                st.error(f"Unexpected error while logging in: {error}")

        with st.expander("Demo accounts"):
            st.caption("Usernames: natalieclaus, alniacapulong, "
                       "nerishperia, kurtraz")


def logout():
    """Write LOGOUT to the audit log, forget the user, reload the page."""
    user = st.session_state.get("user")
    if user is not None:
        db.add_audit_log(user["username"], "LOGOUT", "", "", "Logged out")
    st.session_state.pop("user", None)
    st.rerun()
