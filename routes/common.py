from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from flask import abort, flash, request, url_for
from flask_login import current_user, login_required
from mysql.connector import Error, IntegrityError, errorcode

from database.db_connection import execute, row, rows

METHODS = ("Cash", "GCash", "Bank Transfer")
STATES = ("Pending", "In Progress", "Completed", "Cancelled")
ROLES = ("admin", "cashier", "mechanic")
PRODUCT_IMAGES = (
    "air_filter.jpg",
    "battery.jpg",
    "brake_disc.jpg",
    "brake_pads.jpg",
    "engine_oil_filters.jpg",
    "helmet.jpg",
    "motorcycle_tire.jpg",
    "riding_gloves.jpg",
    "spark_plug.jpg",
    "sprocket_chain.jpg",
)
PRODUCT_IMAGE_URLS = tuple(f"/static/assets/parts/{name}" for name in PRODUCT_IMAGES)


class Invalid(ValueError):
    pass


def roles(*allowed):
    def decorate(fn):
        @wraps(fn)
        @login_required
        def checked(*args, **kwargs):
            if current_user.role not in allowed:
                abort(403)
            return fn(*args, **kwargs)
        return checked
    return decorate


def notify_error(exc):
    if isinstance(exc, Invalid):
        message = str(exc)
    elif isinstance(exc, IntegrityError) and exc.errno == errorcode.ER_DUP_ENTRY:
        message = "That record or reference already exists."
    elif isinstance(exc, IntegrityError) and exc.errno == errorcode.ER_ROW_IS_REFERENCED_2:
        message = "This record is used elsewhere and cannot be deleted."
    elif isinstance(exc, Error) and exc.errno in (1205, 1213):
        message = "Another update is in progress. Please try again."
    else:
        raise exc
    flash(message, "error")


def field(name, limit, *, required=True):
    value = request.form.get(name, "").strip()
    if required and not value:
        raise Invalid(f"{name.replace('_', ' ').capitalize()} is required.")
    if len(value) > limit or "\x00" in value:
        raise Invalid(f"{name.replace('_', ' ').capitalize()} must be at most {limit} characters.")
    return value or None


def number(name, *, minimum=1, maximum=4_000_000_000, optional=False):
    return parse_number(request.form.get(name, ""), name, minimum, maximum, optional)


def parse_number(raw, name, minimum=1, maximum=4_000_000_000, optional=False):
    if optional and not raw:
        return None
    try:
        value = int(raw)
        if minimum <= value <= maximum:
            return value
    except (TypeError, ValueError):
        pass
    raise Invalid(f"Enter a valid {name.replace('_', ' ')}.")


def amount(name, maximum=Decimal("9999999999.99")):
    try:
        value = Decimal(request.form.get(name, "").strip())
        if value.is_finite() and 0 <= value <= maximum and value == value.quantize(Decimal(".01")):
            return value.quantize(Decimal(".01"))
    except InvalidOperation:
        pass
    raise Invalid(f"Enter a valid {name.replace('_', ' ')} with up to two decimal places.")


def choice(name, allowed):
    value = request.form.get(name)
    if value not in allowed:
        raise Invalid(f"Select a valid {name.replace('_', ' ')}.")
    return value


def image_url():
    value = field("image_url", 500, required=False)
    if value:
        if value in PRODUCT_IMAGE_URLS:
            return value
        try:
            parsed = urlsplit(value)
            if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
                return value
        except ValueError:
            pass
        raise Invalid("Enter a valid HTTPS image URL.")
    return None


def existing(sql, args, message="Select a valid record."):
    result = row(sql, args)
    if not result:
        raise Invalid(message)
    return result


def get_or_404(sql, args):
    result = row(sql, args)
    if not result:
        abort(404)
    return result


def request_key():
    try:
        return UUID(hex=request.form.get("request_key", "")).hex
    except (ValueError, AttributeError):
        raise Invalid("Reload this form before submitting it.")


def new_key():
    return uuid4().hex


def search():
    return request.args.get("q", "").strip()[:120]


def pattern(q):
    return "%" + q.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def pager(sql, args=(), *, size=15):
    page = max(1, request.args.get("page", 1, type=int))
    count = row(f"SELECT COUNT(*) AS n FROM ({sql}) listing", args)["n"]
    pages = max(1, (count + size - 1) // size)
    page = min(page, pages)
    return rows(sql + " LIMIT %s OFFSET %s", (*args, size, (page - 1) * size)), {
        "page": page, "pages": pages, "count": count,
    }


def page_url(page):
    args = request.args.to_dict(flat=True)
    args["page"] = page
    args.update(request.view_args or {})
    return url_for(request.endpoint, **args)


def record_payment(kind, record_id, paid_amount, method, reference, key):
    column = "transaction_id" if kind == "sale" else "service_id"
    execute(
        f"INSERT INTO payments ({column}, user_id, method, amount, reference, request_key) VALUES (%s,%s,%s,%s,%s,%s)",
        (record_id, current_user.id, method, paid_amount, reference, key),
    )


def move_stock(product_id, delta, reason, *, transaction_id=None, service_id=None, key=None):
    item = existing(
        "SELECT i.quantity, p.name, p.price, p.active FROM inventory i JOIN products p ON p.id=i.product_id "
        "WHERE i.product_id=%s FOR UPDATE", (product_id,), "Product is no longer available.",
    )
    if delta < 0 and not item["active"]:
        raise Invalid(f"{item['name']} is archived.")
    balance = item["quantity"] + delta
    if not 0 <= balance <= 4_000_000_000:
        raise Invalid(f"Stock adjustment exceeds the available quantity or stock limit for {item['name']}.")
    execute("UPDATE inventory SET quantity=%s WHERE product_id=%s", (balance, product_id))
    execute(
        "INSERT INTO stock_movements (product_id,user_id,quantity_delta,balance,reason,transaction_id,service_id,request_key) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (product_id, current_user.id, delta, balance, reason, transaction_id, service_id, key),
    )
    return item


def date_window():
    today = row("SELECT CURRENT_DATE AS today")["today"]
    period = request.args.get("period", "month")
    starts = {"day": today, "week": today - timedelta(days=today.weekday()), "month": today.replace(day=1)}
    try:
        start = date.fromisoformat(request.args["start"]) if request.args.get("start") else starts.get(period, starts["month"])
        end = date.fromisoformat(request.args["end"]) if request.args.get("end") else today
        if start < date(1000, 1, 1) or start > end or end >= date.max:
            raise ValueError
    except ValueError:
        raise Invalid("Enter a valid start and end date.")
    return period, start, end, end + timedelta(days=1)
