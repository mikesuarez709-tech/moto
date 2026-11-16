from flask import Blueprint, flash, redirect, render_template, request, url_for
from mysql.connector import Error

from database.db_connection import atomic, execute, row, rows
from routes.common import Invalid, choice, field, get_or_404, move_stock, new_key, notify_error, number, pager, pattern, request_key, roles, search

bp = Blueprint("inventory", __name__, url_prefix="/inventory")


@bp.get("/")
@roles("admin")
def index():
    query = search()
    filter_by = request.args.get("stock", "")
    criteria = {"low": " AND i.quantity<=i.minimum", "healthy": " AND i.quantity>i.minimum"}
    entries, pagination = pager(
        "SELECT i.*,p.name,p.sku,p.price,c.name AS category FROM inventory i JOIN products p ON i.product_id=p.id "
        "JOIN categories c ON c.id=p.category_id WHERE p.active=1 AND (p.name LIKE %s ESCAPE '!' OR p.sku LIKE %s ESCAPE '!')"
        + criteria.get(filter_by, "") + " ORDER BY p.name,p.id", (pattern(query), pattern(query))
    )
    moves = rows("SELECT m.*,p.name,p.sku,u.name AS operator FROM stock_movements m JOIN products p ON p.id=m.product_id "
                 "JOIN users u ON u.id=m.user_id ORDER BY m.id DESC LIMIT 8")
    return render_template("inventory/index.html", title="Inventory", entries=entries, pagination=pagination,
                           query=query, stock=filter_by, moves=moves)


@bp.route("/<int:ident>/adjust", methods=["GET", "POST"])
@roles("admin")
def adjust(ident):
    item = get_or_404("SELECT p.name,p.sku,i.* FROM products p JOIN inventory i ON i.product_id=p.id "
                      "WHERE p.active=1 AND p.id=%s", (ident,))
    if request.method == "POST":
        try:
            action = choice("action", ("in", "out", "minimum"))
            key = request_key()
            if action == "minimum":
                execute("UPDATE inventory SET minimum=%s WHERE product_id=%s", (number("minimum", minimum=0), ident))
            else:
                qty = number("quantity", maximum=1_000_000)
                reason = field("reason", 180)
                with atomic():
                    if not row("SELECT id FROM stock_movements WHERE request_key=%s", (key,)):
                        move_stock(ident, qty if action == "in" else -qty, reason, key=key)
            flash("Inventory updated.", "success")
            return redirect(url_for("inventory.index"))
        except (Invalid, Error) as error:
            notify_error(error)
    return render_template("inventory/adjust.html", title="Adjust inventory", item=item, key=new_key())


@bp.get("/history")
@roles("admin")
def history():
    query = search()
    entries, pagination = pager(
        "SELECT m.*,p.name,p.sku,u.name AS operator FROM stock_movements m JOIN products p ON p.id=m.product_id "
        "JOIN users u ON u.id=m.user_id WHERE p.name LIKE %s ESCAPE '!' OR p.sku LIKE %s ESCAPE '!' "
        "OR m.reason LIKE %s ESCAPE '!' ORDER BY m.id DESC", (pattern(query),) * 3
    )
    return render_template("inventory/history.html", title="Stock movements", moves=entries, pagination=pagination, query=query)
