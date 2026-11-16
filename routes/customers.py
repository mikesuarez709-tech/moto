from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from mysql.connector import Error

from database.db_connection import execute, rows
from routes.common import Invalid, field, get_or_404, notify_error, pager, pattern, roles, search

bp = Blueprint("customers", __name__, url_prefix="/customers")


@bp.get("/")
@roles("admin", "cashier")
def index():
    query = search()
    entries, pagination = pager(
        "SELECT c.*,(SELECT COUNT(*) FROM motorcycles m WHERE m.customer_id=c.id) AS bikes "
        "FROM customers c WHERE c.name LIKE %s ESCAPE '!' OR c.phone LIKE %s ESCAPE '!' "
        "OR c.address LIKE %s ESCAPE '!' ORDER BY c.name,c.id", (pattern(query),) * 3
    )
    return render_template("customers/index.html", title="Customers", entries=entries, pagination=pagination, query=query)


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<int:ident>/edit", methods=["GET", "POST"])
@roles("admin", "cashier")
def form(ident=None):
    entry = get_or_404("SELECT * FROM customers WHERE id=%s", (ident,)) if ident else {}
    if request.method == "POST":
        try:
            values = (field("name", 120), field("phone", 40), field("address", 255))
            if not any(char.isdigit() for char in values[1]):
                raise Invalid("Enter a phone number containing at least one digit.")
            if ident:
                execute("UPDATE customers SET name=%s,phone=%s,address=%s WHERE id=%s", (*values, ident))
            else:
                ident = execute("INSERT INTO customers (name,phone,address) VALUES (%s,%s,%s)", values)
            flash("Customer saved.", "success")
            return redirect(url_for("customers.details", ident=ident))
        except (Invalid, Error) as error:
            notify_error(error)
            entry = {**entry, **request.form}
    return render_template("customers/edit.html" if ident else "customers/add.html",
                           title="Edit customer" if ident else "Add customer", entry=entry)


@bp.get("/<int:ident>")
@roles("admin", "cashier")
def details(ident):
    customer = get_or_404("SELECT * FROM customers WHERE id=%s", (ident,))
    bikes = rows("SELECT * FROM motorcycles WHERE customer_id=%s ORDER BY id DESC", (ident,))
    limited = current_user.role == "cashier"
    sales, pagination = pager(
        "SELECT t.*,(SELECT COALESCE(SUM(amount),0) FROM payments WHERE transaction_id=t.id) AS paid "
        "FROM transactions t WHERE t.customer_id=%s" + (" AND t.created_by=%s" if limited else "") + " ORDER BY t.id DESC",
        (ident, current_user.id) if limited else (ident,),
    )
    jobs = rows(
        "SELECT s.id,s.service_type,s.status,s.created_at,CONCAT(m.brand,' ',m.model) AS motorcycle "
        "FROM services s JOIN motorcycles m ON m.id=s.motorcycle_id WHERE s.customer_id=%s ORDER BY s.id DESC LIMIT 10",
        (ident,),
    ) if not limited else []
    return render_template("customers/details.html", title=customer["name"], customer=customer, bikes=bikes,
                           sales=sales, jobs=jobs, pagination=pagination)
