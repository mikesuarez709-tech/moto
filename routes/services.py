from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from mysql.connector import Error

from database.db_connection import atomic, execute, row, rows
from routes.common import (Invalid, METHODS, STATES, amount, choice, existing, field, get_or_404, move_stock,
                           new_key, notify_error, number, pager, pattern, record_payment, request_key, roles, search)

bp = Blueprint("services", __name__, url_prefix="/services")
TRANSITIONS = {"Pending": ("In Progress", "Cancelled"), "In Progress": ("Completed", "Cancelled"),
               "Completed": (), "Cancelled": ()}


def financial(ident):
    return row(
        "SELECT s.labor+COALESCE((SELECT SUM(quantity*unit_price) FROM service_details "
        "WHERE service_id=s.id AND returned_at IS NULL),0) AS total, "
        "(SELECT COALESCE(SUM(amount),0) FROM payments WHERE service_id=s.id) AS paid "
        "FROM services s WHERE s.id=%s", (ident,)
    )


def parts(ident):
    return rows("SELECT * FROM service_details WHERE service_id=%s ORDER BY id", (ident,))


def payments(ident):
    return rows("SELECT p.*,u.name AS operator FROM payments p JOIN users u ON u.id=p.user_id "
                "WHERE service_id=%s ORDER BY p.id", (ident,))


def add_payment(ident, status):
    key = request_key()
    if row("SELECT id FROM payments WHERE request_key=%s AND service_id=%s", (key, ident)):
        return
    if status == "Cancelled":
        raise Invalid("Cancelled services cannot accept payments.")
    totals = financial(ident)
    value = amount("amount", Decimal("999999999999.99"))
    if value <= 0 or value > totals["total"] - totals["paid"]:
        raise Invalid("Enter an amount above zero and within the outstanding balance.")
    method = choice("method", METHODS)
    reference = field("reference", 100, required=method != "Cash")
    record_payment("service", ident, value, method, reference, key)


@bp.get("/billing")
@roles("admin", "cashier")
def billing():
    query = search()
    entries, pagination = pager(
        "SELECT s.id,s.service_type,s.status,s.created_at,c.name AS customer,"
        "CONCAT(m.brand,' ',m.model) AS motorcycle,"
        "s.labor+COALESCE((SELECT SUM(quantity*unit_price) FROM service_details "
        "WHERE service_id=s.id AND returned_at IS NULL),0) AS total,"
        "(SELECT COALESCE(SUM(amount),0) FROM payments WHERE service_id=s.id) AS paid "
        "FROM services s JOIN customers c ON c.id=s.customer_id JOIN motorcycles m ON m.id=s.motorcycle_id "
        "WHERE s.status<>'Cancelled' AND CONCAT_WS(' ',s.id,s.service_type,c.name,m.brand,m.model,m.plate) "
        "LIKE %s ESCAPE '!' ORDER BY s.id DESC", (pattern(query),),
    )
    return render_template("services/billing.html", title="Service payments", entries=entries, pagination=pagination,
                           query=query)


@bp.get("/requests")
@roles("admin", "cashier")
def requests_index():
    entries, pagination = pager(
        "SELECT r.*,c.name AS customer,c.phone,CONCAT(m.brand,' ',m.model) AS motorcycle,m.plate "
        "FROM service_requests r JOIN customers c ON c.id=r.customer_id "
        "JOIN motorcycles m ON m.id=r.motorcycle_id ORDER BY r.id DESC"
    )
    return render_template(
        "services/requests.html", title="Customer requests", entries=entries, pagination=pagination,
    )


@bp.post("/requests/<int:ident>")
@roles("admin", "cashier")
def review_request(ident):
    try:
        target = choice("status", ("Reviewed", "Declined"))
        with atomic():
            service_request = get_or_404("SELECT status FROM service_requests WHERE id=%s FOR UPDATE", (ident,))
            if service_request["status"] != "Pending":
                raise Invalid("Only pending requests can be updated.")
            execute("UPDATE service_requests SET status=%s,updated_at=NOW() WHERE id=%s", (target, ident))
        flash("Customer request updated.", "success")
    except (Invalid, Error) as error:
        notify_error(error)
    return redirect(url_for("services.requests_index"))


@bp.post("/<int:ident>/payment")
@roles("admin", "cashier")
def collect(ident):
    try:
        with atomic():
            job = locked_job(ident)
            add_payment(ident, job["status"])
        flash("Payment recorded.", "success")
    except (Invalid, Error) as error:
        notify_error(error)
    return redirect(url_for("services.receipt", ident=ident))


def locked_job(ident):
    job = get_or_404("SELECT * FROM services WHERE id=%s FOR UPDATE", (ident,))
    if current_user.role == "mechanic" and job["mechanic_id"] != current_user.mechanic_id:
        abort(404)
    return job


@bp.get("/")
@roles("admin", "mechanic")
def index():
    state = request.args.get("status", "")
    query = search()
    assigned = current_user.mechanic_id if current_user.role == "mechanic" else request.args.get("mechanic", type=int)
    sql = ("SELECT s.*,c.name AS customer,k.name AS mechanic,CONCAT(m.brand,' ',m.model) AS motorcycle,m.plate "
           "FROM services s JOIN customers c ON c.id=s.customer_id JOIN motorcycles m ON m.id=s.motorcycle_id "
           "JOIN mechanics k ON k.id=s.mechanic_id "
           "WHERE CONCAT_WS(' ',s.id,s.service_type,c.name,k.name,m.brand,m.model,m.plate) LIKE %s ESCAPE '!'")
    args = [pattern(query)]
    if state in STATES:
        sql += " AND s.status=%s"
        args.append(state)
    if assigned:
        sql += " AND s.mechanic_id=%s"
        args.append(assigned)
    customer_id = request.args.get("customer", type=int) if current_user.role == "admin" else None
    if customer_id:
        sql += " AND s.customer_id=%s"
        args.append(customer_id)
    entries, pagination = pager(sql + " ORDER BY s.id DESC", tuple(args))
    mechanics = rows("SELECT id,name FROM mechanics ORDER BY name") if current_user.role == "admin" else []
    return render_template("services/index.html", title="Services", entries=entries, pagination=pagination,
                           query=query, status=state, states=STATES, assigned=assigned, mechanics=mechanics, customer_id=customer_id)


@bp.route("/new", methods=["GET", "POST"])
@roles("admin")
def add():
    if request.method == "POST":
        try:
            key = request_key()
            owner = number("customer_id")
            bike = number("motorcycle_id")
            mechanic = number("mechanic_id")
            values = (field("service_type", 100), field("description", 2000), amount("labor"))
            with atomic():
                saved = row("SELECT id FROM services WHERE request_key=%s AND created_by=%s", (key, current_user.id))
                if saved:
                    ident = saved["id"]
                else:
                    existing("SELECT id FROM motorcycles WHERE id=%s AND customer_id=%s FOR UPDATE", (bike, owner),
                             "Select a motorcycle registered to that customer.")
                    existing("SELECT id FROM mechanics WHERE id=%s AND available=1 FOR UPDATE", (mechanic,),
                             "Select an available mechanic.")
                    ident = execute("INSERT INTO services (request_key,customer_id,motorcycle_id,mechanic_id,service_type,"
                                    "description,labor,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                                    (key, owner, bike, mechanic, *values, current_user.id))
            flash("Service job saved.", "success")
            return redirect(url_for("services.details", ident=ident))
        except (Invalid, Error) as error:
            notify_error(error)
    return render_template("services/add.html", title="New service job", key=new_key(),
                           customers=rows("SELECT id,name,phone FROM customers ORDER BY name"),
                           motorcycles=rows("SELECT id,customer_id,brand,model,plate FROM motorcycles ORDER BY brand,model"),
                           mechanics=rows("SELECT id,name FROM mechanics WHERE available=1 ORDER BY name"))


@bp.get("/<int:ident>")
@roles("admin", "mechanic")
def details(ident):
    job = get_or_404(
        "SELECT s.*,c.name AS customer,k.name AS mechanic,m.brand,m.model,m.plate,m.engine_number "
        "FROM services s JOIN customers c ON c.id=s.customer_id JOIN motorcycles m ON m.id=s.motorcycle_id "
        "JOIN mechanics k ON k.id=s.mechanic_id WHERE s.id=%s", (ident,)
    )
    is_admin = current_user.role == "admin"
    if not is_admin and job["mechanic_id"] != current_user.mechanic_id:
        abort(404)
    options = TRANSITIONS[job["status"]]
    if not is_admin:
        options = tuple(item for item in options if item != "Cancelled")
    open_job = job["status"] in ("Pending", "In Progress")
    catalog = rows("SELECT p.id,p.name,p.sku,p.price,i.quantity FROM products p JOIN inventory i ON i.product_id=p.id "
                   "WHERE p.active=1 AND i.quantity>0 ORDER BY p.name") if is_admin and open_job else []
    mechanics = rows("SELECT id,name FROM mechanics WHERE available=1 ORDER BY name") if is_admin and open_job else []
    return render_template("services/details.html", title=f"Service #{ident:05}", job=job, parts=parts(ident),
                           payment_rows=payments(ident) if is_admin else [], totals=financial(ident) if is_admin else {},
                           options=options, catalog=catalog, mechanics=mechanics, methods=METHODS,
                           pay_key=new_key(), part_key=new_key(), open_job=open_job)


@bp.post("/<int:ident>/update")
@roles("admin", "mechanic")
def update(ident):
    try:
        action = choice("action", ("status", "assign", "part", "return", "payment"))
        if current_user.role == "mechanic" and action != "status":
            abort(403)
        with atomic():
            job = locked_job(ident)
            status = job["status"]
            if action == "status":
                target = choice("status", TRANSITIONS[status])
                if target == "Cancelled":
                    if current_user.role != "admin":
                        abort(403)
                    if financial(ident)["paid"]:
                        raise Invalid("A service with recorded payments cannot be cancelled.")
                    outstanding = rows("SELECT product_id,SUM(quantity) AS quantity FROM service_details "
                                       "WHERE service_id=%s AND returned_at IS NULL GROUP BY product_id ORDER BY product_id", (ident,))
                    for part in outstanding:
                        move_stock(part["product_id"], int(part["quantity"]), "Cancelled service return", service_id=ident)
                    execute("UPDATE service_details SET returned_at=NOW() WHERE service_id=%s AND returned_at IS NULL", (ident,))
                execute("UPDATE services SET status=%s,completed_at=IF(%s='Completed',NOW(),NULL) WHERE id=%s",
                        (target, target, ident))
            elif action == "payment":
                add_payment(ident, status)
            else:
                if status not in ("Pending", "In Progress"):
                    raise Invalid("Only open service jobs can be edited.")
                if action == "assign":
                    mechanic = number("mechanic_id")
                    existing("SELECT id FROM mechanics WHERE id=%s AND available=1 FOR UPDATE", (mechanic,),
                             "Select an available mechanic.")
                    execute("UPDATE services SET mechanic_id=%s WHERE id=%s", (mechanic, ident))
                elif action == "part":
                    key = request_key()
                    if not row("SELECT id FROM service_details WHERE request_key=%s AND service_id=%s", (key, ident)):
                        product = number("product_id")
                        quantity = number("quantity", maximum=100_000)
                        item = move_stock(product, -quantity, "Service part used", service_id=ident)
                        if financial(ident)["total"] + item["price"] * quantity > Decimal("999999999999.99"):
                            raise Invalid("Service total exceeds the supported amount.")
                        execute("INSERT INTO service_details (request_key,service_id,product_id,product_name,quantity,unit_price) "
                                "VALUES (%s,%s,%s,%s,%s,%s)", (key, ident, product, item["name"], quantity, item["price"]))
                else:
                    part = existing("SELECT * FROM service_details WHERE id=%s AND service_id=%s AND returned_at IS NULL",
                                    (number("part_id"), ident), "That part has already been returned.")
                    totals = financial(ident)
                    if totals["total"] - part["quantity"] * part["unit_price"] < totals["paid"]:
                        raise Invalid("Returning this part would make the total lower than the amount already paid.")
                    move_stock(part["product_id"], part["quantity"], "Service part returned", service_id=ident)
                    execute("UPDATE service_details SET returned_at=NOW() WHERE id=%s", (part["id"],))
                execute("UPDATE services SET updated_at=NOW() WHERE id=%s", (ident,))
        flash("Service job updated.", "success")
    except (Invalid, Error) as error:
        notify_error(error)
    return redirect(url_for("services.details", ident=ident))


@bp.get("/<int:ident>/receipt")
@roles("admin", "cashier")
def receipt(ident):
    item = get_or_404(
        "SELECT s.*,c.name AS customer,CONCAT(m.brand,' ',m.model) AS motorcycle "
        "FROM services s JOIN customers c ON c.id=s.customer_id JOIN motorcycles m ON m.id=s.motorcycle_id WHERE s.id=%s", (ident,)
    )
    if current_user.role == "cashier" and item["status"] == "Cancelled":
        abort(404)
    return render_template("transactions/receipt.html", title="Service receipt", kind="service", item=item,
                           lines=[line for line in parts(ident) if not line["returned_at"]],
                           payments=payments(ident), totals=financial(ident), key=new_key(), methods=METHODS,
                           back=url_for("services.details", ident=ident) if current_user.role == "admin"
                           else url_for("services.billing"))
