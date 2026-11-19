from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from mysql.connector import Error
from werkzeug.security import generate_password_hash

from database.db_connection import atomic, execute, row, rows
from routes.auth import account_identity, validate_password
from routes.common import (Invalid, choice, existing, field, get_or_404, new_key, notify_error, number,
                           request_key, roles)

bp = Blueprint("customer_portal", __name__, url_prefix="/portal")


@bp.route("/customers/<int:customer_id>/account", methods=["GET", "POST"])
@roles("admin")
def account_form(customer_id):
    customer = get_or_404("SELECT id,name FROM customers WHERE id=%s", (customer_id,))
    account = row(
        "SELECT id,username,active FROM customer_accounts WHERE customer_id=%s", (customer_id,)
    )
    editing = bool(account)
    if request.method == "POST":
        try:
            _, username = account_identity(customer["name"], field("username", 80))
            password = request.form.get("password", "")
            active = int(request.form.get("active") == "1")
            if not account or password:
                validate_password(password)
            if row("SELECT id FROM users WHERE username=%s", (username,)):
                raise Invalid("That username is already in use.")
            if row(
                "SELECT id FROM customer_accounts WHERE username=%s AND customer_id<>%s",
                (username, customer_id),
            ):
                raise Invalid("That username is already in use.")
            password_hash = generate_password_hash(password) if password else None
            with atomic():
                if account:
                    execute(
                        "UPDATE customer_accounts SET username=%s,password_hash=COALESCE(%s,password_hash),"
                        "active=%s,failed_attempts=0,locked_until=NULL,session_version=session_version+1 "
                        "WHERE customer_id=%s",
                        (username, password_hash, active, customer_id),
                    )
                else:
                    execute(
                        "INSERT INTO customer_accounts (customer_id,username,password_hash,active) "
                        "VALUES (%s,%s,%s,%s)",
                        (customer_id, username, password_hash, active),
                    )
            flash("Customer portal account saved.", "success")
            return redirect(url_for("customers.details", ident=customer_id))
        except (Invalid, Error) as error:
            notify_error(error)
            account = {
                **(account or {}), **request.form.to_dict(),
                "active": int(request.form.get("active") == "1"),
            }
    return render_template(
        "customer_portal/account.html", title="Customer portal account", customer=customer, account=account,
        editing=editing,
    )


@bp.get("/")
@roles("customer")
def index():
    customer = get_or_404("SELECT id,name FROM customers WHERE id=%s", (current_user.customer_id,))
    motorcycles = rows(
        "SELECT id,brand,model,plate FROM motorcycles WHERE customer_id=%s ORDER BY id DESC",
        (current_user.customer_id,),
    )
    services = rows(
        "SELECT s.id,s.service_type,s.status,s.created_at,CONCAT(m.brand,' ',m.model) AS motorcycle,"
        "s.labor+COALESCE((SELECT SUM(quantity*unit_price) FROM service_details "
        "WHERE service_id=s.id AND returned_at IS NULL),0) AS total,"
        "(SELECT COALESCE(SUM(amount),0) FROM payments WHERE service_id=s.id) AS paid "
        "FROM services s JOIN motorcycles m ON m.id=s.motorcycle_id "
        "WHERE s.customer_id=%s ORDER BY s.id DESC LIMIT 20",
        (current_user.customer_id,),
    )
    sales = rows(
        "SELECT t.id,t.total,t.created_at,"
        "(SELECT COALESCE(SUM(amount),0) FROM payments WHERE transaction_id=t.id) AS paid "
        "FROM transactions t WHERE t.customer_id=%s ORDER BY t.id DESC LIMIT 20",
        (current_user.customer_id,),
    )
    requests = rows(
        "SELECT r.id,r.service_type,r.status,r.created_at,CONCAT(m.brand,' ',m.model) AS motorcycle "
        "FROM service_requests r JOIN motorcycles m ON m.id=r.motorcycle_id "
        "WHERE r.customer_id=%s ORDER BY r.id DESC LIMIT 20",
        (current_user.customer_id,),
    )
    return render_template(
        "customer_portal/index.html", title="My workshop account", customer=customer, motorcycles=motorcycles,
        services=services, sales=sales, requests=requests, request_key=new_key(),
    )


@bp.get("/shop")
@roles("customer")
def shop():
    products = rows(
        "SELECT p.id,p.name,p.brand,p.description,p.image_url,p.price,i.quantity,c.name AS category "
        "FROM products p JOIN inventory i ON i.product_id=p.id "
        "JOIN categories c ON c.id=p.category_id "
        "WHERE p.active=TRUE AND i.quantity>0 ORDER BY c.name,p.name"
    )
    requests = rows(
        "SELECT id,product_name,quantity,unit_price,status,created_at FROM purchase_requests "
        "WHERE customer_id=%s ORDER BY id DESC LIMIT 20",
        (current_user.customer_id,),
    )
    return render_template(
        "customer_portal/shop.html", title="Shop", products=products, requests=requests,
        request_keys={product["id"]: new_key() for product in products},
    )


@bp.post("/shop/<int:product_id>/request")
@roles("customer")
def request_purchase(product_id):
    try:
        key = request_key()
        quantity = number("quantity", maximum=1000)
        with atomic():
            saved = row(
                "SELECT id FROM purchase_requests WHERE request_key=%s AND customer_id=%s",
                (key, current_user.customer_id),
            )
            if not saved:
                product = existing(
                    "SELECT p.id,p.name,p.price,i.quantity FROM products p "
                    "JOIN inventory i ON i.product_id=p.id "
                    "WHERE p.id=%s AND p.active=TRUE FOR UPDATE",
                    (product_id,),
                    "This item is no longer available.",
                )
                if product["quantity"] < quantity:
                    raise Invalid(f"Only {product['quantity']} in stock for {product['name']}.")
                execute(
                    "INSERT INTO purchase_requests "
                    "(request_key,customer_id,product_id,product_name,quantity,unit_price) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (key, current_user.customer_id, product_id, product["name"], quantity, product["price"]),
                )
        flash("Purchase request sent. The shop will confirm availability and payment with you.", "success")
    except (Invalid, Error) as error:
        notify_error(error)
    return redirect(url_for("customer_portal.shop"))


@bp.get("/purchase-requests")
@roles("admin", "cashier")
def purchase_requests():
    requests = rows(
        "SELECT r.id,r.product_name,r.quantity,r.unit_price,r.status,r.created_at,"
        "c.id AS customer_id,c.name AS customer,c.phone "
        "FROM purchase_requests r JOIN customers c ON c.id=r.customer_id "
        "ORDER BY (r.status='Pending') DESC,r.created_at DESC"
    )
    return render_template("customer_portal/purchase_requests.html", title="Purchase requests", requests=requests)


@bp.post("/purchase-requests/<int:request_id>/status")
@roles("admin", "cashier")
def update_purchase_request(request_id):
    try:
        status = choice("status", ("Confirmed", "Declined"))
        with atomic():
            item = get_or_404(
                "SELECT status,product_id,quantity FROM purchase_requests WHERE id=%s FOR UPDATE",
                (request_id,),
            )
            if item["status"] != "Pending":
                raise Invalid("Only pending purchase requests can be updated.")
            if status == "Confirmed":
                product = existing(
                    "SELECT p.active,p.name,i.quantity FROM products p "
                    "JOIN inventory i ON i.product_id=p.id WHERE p.id=%s FOR UPDATE",
                    (item["product_id"],),
                    "This product is no longer available.",
                )
                if not product["active"] or product["quantity"] < item["quantity"]:
                    raise Invalid(f"Not enough stock remains to confirm {product['name']}.")
            execute("UPDATE purchase_requests SET status=%s WHERE id=%s", (status, request_id))
        flash(f"Purchase request {status.lower()}.", "success")
    except (Invalid, Error) as error:
        notify_error(error)
    return redirect(url_for("customer_portal.purchase_requests"))


@bp.post("/requests")
@roles("customer")
def create_request():
    try:
        key = request_key()
        motorcycle_id = number("motorcycle_id")
        service_type = field("service_type", 100)
        description = field("description", 2000, required=False)
        with atomic():
            saved = row(
                "SELECT id FROM service_requests WHERE request_key=%s AND customer_id=%s",
                (key, current_user.customer_id),
            )
            if not saved:
                existing(
                    "SELECT id FROM motorcycles WHERE id=%s AND customer_id=%s FOR UPDATE",
                    (motorcycle_id, current_user.customer_id),
                    "Choose one of your registered motorcycles.",
                )
                execute(
                    "INSERT INTO service_requests "
                    "(request_key,customer_id,motorcycle_id,service_type,description) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (key, current_user.customer_id, motorcycle_id, service_type, description or ""),
                )
        flash("Service request submitted. The workshop will review it.", "success")
    except (Invalid, Error) as error:
        notify_error(error)
    return redirect(url_for("customer_portal.index"))


@bp.get("/receipt/<kind>/<int:ident>")
@roles("customer")
def receipt(kind, ident):
    if kind == "sale":
        item = get_or_404(
            "SELECT t.*,c.name AS customer,u.name AS operator,"
            "(SELECT COALESCE(SUM(amount),0) FROM payments WHERE transaction_id=t.id) AS paid "
            "FROM transactions t JOIN customers c ON c.id=t.customer_id "
            "JOIN users u ON u.id=t.created_by WHERE t.id=%s AND t.customer_id=%s",
            (ident, current_user.customer_id),
        )
        lines = rows("SELECT * FROM transaction_items WHERE transaction_id=%s ORDER BY id", (ident,))
        payments = rows(
            "SELECT method,amount,reference,created_at FROM payments WHERE transaction_id=%s ORDER BY id",
            (ident,),
        )
        totals = {"total": item["total"], "paid": item["paid"]}
    elif kind == "service":
        item = get_or_404(
            "SELECT s.*,c.name AS customer,CONCAT(m.brand,' ',m.model) AS motorcycle,"
            "(SELECT COALESCE(SUM(amount),0) FROM payments WHERE service_id=s.id) AS paid "
            "FROM services s JOIN customers c ON c.id=s.customer_id "
            "JOIN motorcycles m ON m.id=s.motorcycle_id WHERE s.id=%s AND s.customer_id=%s",
            (ident, current_user.customer_id),
        )
        lines = rows(
            "SELECT product_name,quantity,unit_price FROM service_details "
            "WHERE service_id=%s AND returned_at IS NULL ORDER BY id",
            (ident,),
        )
        payments = rows(
            "SELECT method,amount,reference,created_at FROM payments WHERE service_id=%s ORDER BY id",
            (ident,),
        )
        totals = row(
            "SELECT s.labor+COALESCE((SELECT SUM(quantity*unit_price) FROM service_details "
            "WHERE service_id=s.id AND returned_at IS NULL),0) AS total,"
            "(SELECT COALESCE(SUM(amount),0) FROM payments WHERE service_id=s.id) AS paid "
            "FROM services s WHERE s.id=%s AND s.customer_id=%s",
            (ident, current_user.customer_id),
        )
    else:
        abort(404)
    return render_template(
        "transactions/receipt.html", title="Customer receipt", kind=kind, item=item, lines=lines,
        payments=payments, totals=totals, customer=True, back=url_for("customer_portal.index"),
    )
