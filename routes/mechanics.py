from flask import Blueprint, flash, redirect, render_template, request, url_for
from mysql.connector import Error

from database.db_connection import execute
from routes.common import Invalid, field, get_or_404, notify_error, pager, pattern, roles, search

bp = Blueprint("mechanics", __name__, url_prefix="/mechanics")


@bp.get("/")
@roles("admin")
def index():
    query = search()
    availability = request.args.get("availability", "")
    criteria = {"yes": " AND m.available=1", "no": " AND m.available=0"}
    entries, pagination = pager(
        "SELECT m.*,(SELECT COUNT(*) FROM services WHERE mechanic_id=m.id AND status IN ('Pending','In Progress')) AS open_jobs,"
        "(SELECT COUNT(*) FROM services WHERE mechanic_id=m.id AND status='Completed') AS completed "
        "FROM mechanics m WHERE CONCAT_WS(' ',m.name,m.phone) LIKE %s ESCAPE '!'" +
        criteria.get(availability, "") + " ORDER BY m.name,m.id", (pattern(query),)
    )
    return render_template("mechanics/index.html", title="Mechanics", entries=entries, pagination=pagination,
                           query=query, availability=availability)


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<int:ident>/edit", methods=["GET", "POST"])
@roles("admin")
def form(ident=None):
    entry = get_or_404("SELECT * FROM mechanics WHERE id=%s", (ident,)) if ident else {"available": True}
    if request.method == "POST":
        try:
            values = (field("name", 120), field("phone", 40), request.form.get("available") == "1")
            if not any(char.isdigit() for char in values[1]):
                raise Invalid("Enter a phone number containing at least one digit.")
            if ident:
                execute("UPDATE mechanics SET name=%s,phone=%s,available=%s WHERE id=%s", (*values, ident))
            else:
                execute("INSERT INTO mechanics (name,phone,available) VALUES (%s,%s,%s)", values)
            flash("Mechanic saved.", "success")
            return redirect(url_for("mechanics.index"))
        except (Invalid, Error) as error:
            notify_error(error)
            entry = {**entry, **request.form, "available": request.form.get("available") == "1"}
    return render_template("mechanics/form.html", title="Edit mechanic" if ident else "Add mechanic", entry=entry)
