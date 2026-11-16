from flask import Blueprint, flash, redirect, render_template, request, url_for
from mysql.connector import Error

from database.db_connection import atomic, execute, rows
from routes.common import Invalid, existing, field, get_or_404, notify_error, number, pager, pattern, roles, search

bp = Blueprint("motorcycles", __name__, url_prefix="/motorcycles")


@bp.get("/")
@roles("admin")
def index():
    query = search()
    owner = request.args.get("owner", type=int)
    sql = ("SELECT m.*,c.name AS owner FROM motorcycles m JOIN customers c ON c.id=m.customer_id "
           "WHERE CONCAT_WS(' ',m.brand,m.model,m.plate,m.engine_number,c.name) LIKE %s ESCAPE '!'")
    entries, pagination = pager(sql + (" AND m.customer_id=%s" if owner else "") + " ORDER BY m.id DESC",
                                (pattern(query), owner) if owner else (pattern(query),))
    return render_template("motorcycles/index.html", title="Motorcycles", entries=entries,
                           pagination=pagination, query=query, owner=owner)


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<int:ident>/edit", methods=["GET", "POST"])
@roles("admin")
def form(ident=None):
    entry = (get_or_404("SELECT * FROM motorcycles WHERE id=%s", (ident,)) if ident else
             {"customer_id": request.args.get("owner", type=int)})
    if request.method == "POST":
        try:
            owner = number("customer_id")
            plate = field("plate", 30, required=False)
            values = (owner, field("brand", 80), field("model", 80), plate.upper() if plate else None,
                      field("engine_number", 80).upper())
            with atomic():
                existing("SELECT id FROM customers WHERE id=%s", (owner,), "Select an owner.")
                if ident:
                    existing("SELECT id FROM motorcycles WHERE id=%s FOR UPDATE", (ident,))
                    execute("UPDATE motorcycles SET customer_id=%s,brand=%s,model=%s,plate=%s,engine_number=%s WHERE id=%s",
                            (*values, ident))
                else:
                    execute("INSERT INTO motorcycles (customer_id,brand,model,plate,engine_number) VALUES (%s,%s,%s,%s,%s)", values)
            flash("Motorcycle saved.", "success")
            return redirect(url_for("motorcycles.index"))
        except (Invalid, Error) as error:
            notify_error(error)
            entry = {**entry, **request.form}
    return render_template("motorcycles/form.html", title="Edit motorcycle" if ident else "Register motorcycle", entry=entry,
                           customers=rows("SELECT id,name,phone FROM customers ORDER BY name"))
