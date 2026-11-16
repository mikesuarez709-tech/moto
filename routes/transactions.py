from collections import Counter
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from mysql.connector import Error

from database.db_connection import atomic, execute, row, rows
from routes.common import (Invalid, METHODS, amount, choice, date_window, existing, field, get_or_404,
                           move_stock, new_key, notify_error, number, pager, parse_number, pattern, record_payment,
                           request_key, roles, search)

bp = Blueprint("transactions", __name__, url_prefix="/transactions")

SUMMARY = (
    "SELECT t.*,COALESCE(c.name,'Walk-in') AS customer,u.name AS operator,"
    "(SELECT COALESCE(SUM(amount),0) FROM payments WHERE transaction_id=t.id) AS paid "
    "FROM transactions t LEFT JOIN customers c ON c.id=t.customer_id JOIN users u ON u.id=t.created_by"
)


def scope():
    return (" AND t.created_by=%s", (current_user.id,)) if current_user.role == "cashier" else ("", ())


@bp.get("/")
@roles("admin", "cashier")
def index():
    query = search()
    status = request.args.get("status", "")
    method = request.args.get("method", "")
    period = request.args.get("period", "all")
    start, end = request.args.get("start", ""), request.args.get("end", "")
    limited, args = scope()
    sql = SUMMARY + " WHERE CONCAT_WS(' ',t.id,c.name,u.name) LIKE %s ESCAPE '!'" + limited
    args = (pattern(query), *args)
    if method in METHODS:
        sql += " AND EXISTS(SELECT 1 FROM payments p WHERE p.transaction_id=t.id AND p.method=%s)"
        args += (method,)
    if period != "all" or start or end:
        try:
            _, start, end, until = date_window()
            sql += " AND t.created_at >= %s AND t.created_at < %s"
            args += (start, until)
        except Invalid as error:
            notify_error(error)
    criteria = {"Paid": "paid>=total", "Partial": "paid>0 AND paid<total", "Unpaid": "paid=0"}
    outer = "SELECT listing.* FROM (" + sql + ") listing"
    if status in criteria:
        outer += " WHERE " + criteria[status]
    entries, pagination = pager(outer + " ORDER BY id DESC", args)
    return render_template("transactions/index.html", title="Transactions", entries=entries, pagination=pagination,
                           query=query, status=status, method=method, methods=METHODS, period=period, start=start, end=end)


@bp.route("/checkout", methods=["GET", "POST"])
@roles("admin", "cashier")
def checkout():
    if request.method == "POST":
        try:
            key = request_key()
            products = request.form.getlist("product_id")
            quantities = request.form.getlist("quantity")
            if not 1 <= len(products) == len(quantities) <= 50:
                raise Invalid("Add between one and 50 valid line items.")
            basket = Counter()
            for product, qty in zip(products, quantities):
                if product == "" and qty in ("", "1"):
                    continue
                basket[parse_number(product, "product")] += parse_number(qty, "quantity", maximum=100_000)
            if not basket:
                raise Invalid("Add at least one product.")
            customer = number("customer_id", optional=True)
            status = choice("payment_status", ("Paid", "Unpaid", "Partial"))
            with atomic():
                sale = row("SELECT id FROM transactions WHERE request_key=%s AND created_by=%s", (key, current_user.id))
                if sale:
                    ident = sale["id"]
                else:
                    if customer:
                        existing("SELECT id FROM customers WHERE id=%s", (customer,), "Select a valid customer.")
                    lines = []
                    for product_id, quantity in sorted(basket.items()):
                        item = existing("SELECT p.id,p.name,p.price,i.quantity FROM products p "
                                        "JOIN inventory i ON i.product_id=p.id WHERE p.id=%s AND p.active=1 FOR UPDATE",
                                        (product_id,), "A selected product is unavailable.")
                        if item["quantity"] < quantity:
                            raise Invalid(f"Only {item['quantity']} in stock for {item['name']}.")
                        lines.append((item, quantity))
                    total = sum(item["price"] * qty for item, qty in lines)
                    if not 0 < total <= Decimal("999999999999.99"):
                        raise Invalid("Sale total must be positive and within the supported amount.")
                    payment = total if status == "Paid" else amount("amount", total) if status == "Partial" else Decimal(0)
                    if status == "Partial" and not 0 < payment < total:
                        raise Invalid("A partial payment must be greater than zero and less than the sale total.")
                    method = choice("method", METHODS) if payment else None
                    reference = field("reference", 100, required=method != "Cash") if payment else None
                    ident = execute("INSERT INTO transactions (request_key,customer_id,created_by,total) VALUES (%s,%s,%s,%s)",
                                    (key, customer, current_user.id, total))
                    for item, qty in lines:
                        execute("INSERT INTO transaction_items (transaction_id,product_id,product_name,quantity,unit_price) "
                                "VALUES (%s,%s,%s,%s,%s)", (ident, item["id"], item["name"], qty, item["price"]))
                        move_stock(item["id"], -qty, "Product sale", transaction_id=ident)
                    if payment:
                        record_payment("sale", ident, payment, method, reference, key)
            flash("Sale recorded.", "success")
            return redirect(url_for("transactions.receipt", ident=ident))
        except (Invalid, Error) as error:
            notify_error(error)
    catalog = rows("SELECT p.id,p.name,p.sku,p.price,i.quantity FROM products p JOIN inventory i ON i.product_id=p.id "
                   "WHERE p.active=1 AND i.quantity>0 ORDER BY p.name")
    customers = rows("SELECT id,name,phone FROM customers ORDER BY name")
    return render_template("transactions/checkout.html", title="New sale", catalog=catalog, customers=customers,
                           methods=METHODS, key=new_key(),
                           submitted=list(zip(request.form.getlist("product_id"), request.form.getlist("quantity")))[:50] or [("", 1)])


def sale_or_404(ident, *, lock=False):
    limited, args = scope()
    sql = "SELECT t.* FROM transactions t" if lock else SUMMARY
    return get_or_404(sql + " WHERE t.id=%s" + limited + (" FOR UPDATE" if lock else ""), (ident, *args))


@bp.get("/<int:ident>/receipt")
@roles("admin", "cashier")
def receipt(ident):
    sale = sale_or_404(ident)
    return render_template(
        "transactions/receipt.html", title="Sale receipt", item=sale, kind="sale",
        lines=rows("SELECT * FROM transaction_items WHERE transaction_id=%s ORDER BY id", (ident,)),
        payments=rows("SELECT p.*,u.name AS operator FROM payments p JOIN users u ON u.id=p.user_id "
                      "WHERE transaction_id=%s ORDER BY p.id", (ident,)),
        totals={"total": sale["total"], "paid": sale["paid"]},
        key=new_key(), methods=METHODS, back=url_for("transactions.index"),
    )


@bp.post("/<int:ident>/payment")
@roles("admin", "cashier")
def payment(ident):
    try:
        key = request_key()
        value = amount("amount", Decimal("999999999999.99"))
        method = choice("method", METHODS)
        reference = field("reference", 100, required=method != "Cash")
        with atomic():
            sale = sale_or_404(ident, lock=True)
            if not row("SELECT id FROM payments WHERE request_key=%s AND transaction_id=%s", (key, ident)):
                paid = row("SELECT COALESCE(SUM(amount),0) AS paid FROM payments WHERE transaction_id=%s", (ident,))["paid"]
                if not 0 < value <= sale["total"] - paid:
                    raise Invalid("Enter an amount above zero and within the outstanding balance.")
                record_payment("sale", ident, value, method, reference, key)
        flash("Payment recorded.", "success")
    except (Invalid, Error) as error:
        notify_error(error)
    return redirect(url_for("transactions.receipt", ident=ident))
