import re
from datetime import timedelta
from secrets import token_hex

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import UserMixin, current_user, login_required, login_user, logout_user
from mysql.connector import Error
from werkzeug.security import check_password_hash, generate_password_hash

from database.db_connection import atomic, execute, row, rows
from routes.common import Invalid, ROLES, choice, existing, field, get_or_404, notify_error, number, pager, roles

bp = Blueprint("auth", __name__)
DUMMY_HASH = generate_password_hash(token_hex(32))


class Account(UserMixin):
    def __init__(self, record):
        self.id = record["id"]
        self.name = record["name"]
        self.username = record["username"]
        self.role = record["role"]
        self.mechanic_id = record["mechanic_id"]
        self.version = record["session_version"]

    def get_id(self):
        return f"{self.id}:{self.version}"


def load_user(identity):
    user_id, separator, version = identity.partition(":")
    if not separator or not user_id.isascii() or not user_id.isdigit() or not version.isascii() or not version.isdigit():
        return None
    record = row("SELECT * FROM users WHERE id=%s AND session_version=%s AND active=TRUE", (user_id, version))
    return Account(record) if record else None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()[:80]
        password = request.form.get("password", "")
        allowed = False
        if 0 < len(password) <= 128:
            with atomic():
                record = row("SELECT users.*, NOW() AS checked_at FROM users WHERE username=%s FOR UPDATE", (username,))
                if record and record["active"]:
                    now = record["checked_at"]
                    locked = record["locked_until"]
                    if not locked or locked <= now:
                        allowed = check_password_hash(record["password_hash"], password)
                        if allowed:
                            execute("UPDATE users SET failed_attempts=0,locked_until=NULL WHERE id=%s", (record["id"],))
                        else:
                            failures = (0 if locked else record["failed_attempts"]) + 1
                            execute("UPDATE users SET failed_attempts=%s,locked_until=%s WHERE id=%s",
                                    (failures, now + timedelta(minutes=5) if failures >= 5 else None, record["id"]))
                    else:
                        check_password_hash(DUMMY_HASH, password)
                else:
                    check_password_hash(DUMMY_HASH, password)
        if allowed:
            session.clear()
            session.permanent = True
            login_user(Account(record))
            return redirect(url_for("dashboard.index"))
        flash("Sign-in failed. Check your credentials or retry in five minutes.", "error")
    return render_template("login.html", title="Sign in")


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


def account_identity(name, username):
    name, username = name.strip(), username.strip().lower()
    if not name or len(name) > 120 or "\x00" in name:
        raise Invalid("Enter a name up to 120 characters.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,79}", username):
        raise Invalid("Use 3–80 letters, digits, dots, underscores, or hyphens for the username.")
    return name, username


def validate_password(password):
    if not 12 <= len(password) <= 128:
        raise Invalid("Use a password of 12–128 characters.")


@bp.get("/users")
@roles("admin")
def users():
    accounts, pagination = pager(
        "SELECT u.id,u.name,u.username,u.role,u.active,m.name AS mechanic FROM users u "
        "LEFT JOIN mechanics m ON m.id=u.mechanic_id ORDER BY u.name,u.id"
    )
    return render_template("users.html", title="User accounts", accounts=accounts, pagination=pagination)


@bp.route("/users/new", methods=["GET", "POST"])
@bp.route("/users/<int:ident>/edit", methods=["GET", "POST"])
@roles("admin")
def user_form(ident=None):
    account = get_or_404("SELECT * FROM users WHERE id=%s", (ident,)) if ident else {}
    if request.method == "POST":
        try:
            name, username = account_identity(field("name", 120), field("username", 80))
            role = choice("role", ROLES)
            password = request.form.get("password", "")
            active = int(request.form.get("active") == "1")
            if ident == current_user.id and (not active or role != "admin"):
                raise Invalid("Keep your current Administrator account active.")
            mechanic = number("mechanic_id") if role == "mechanic" else None
            if password or not ident:
                validate_password(password)
            password_hash = generate_password_hash(password) if password else None
            with atomic():
                if mechanic:
                    existing("SELECT id FROM mechanics WHERE id=%s", (mechanic,))
                if ident:
                    execute(
                        "UPDATE users SET name=%s,username=%s,role=%s,mechanic_id=%s,active=%s,"
                        "password_hash=COALESCE(%s,password_hash),failed_attempts=0,locked_until=NULL,"
                        "session_version=session_version+1 WHERE id=%s",
                        (name, username, role, mechanic, active, password_hash, ident),
                    )
                else:
                    execute("INSERT INTO users (name,username,role,mechanic_id,active,password_hash) VALUES (%s,%s,%s,%s,%s,%s)",
                            (name, username, role, mechanic, active, password_hash))
            if ident == current_user.id:
                login_user(load_user(f"{ident}:{account['session_version'] + 1}"))
            flash("User account saved.", "success")
            return redirect(url_for("auth.users"))
        except (Invalid, Error) as error:
            notify_error(error)
            account = {**account, **request.form.to_dict(), "active": int(request.form.get("active") == "1")}
    return render_template("user_form.html", title="Edit account" if ident else "Add account",
                           account=account, editing=bool(ident), roles=ROLES,
                           mechanics=rows("SELECT id,name FROM mechanics ORDER BY name"))
