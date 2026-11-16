from datetime import timedelta

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from database.db_connection import row, rows
from routes.common import STATES

bp = Blueprint("dashboard", __name__)


@bp.get("/")
@login_required
def index():
    role = current_user.role
    if role == "customer":
        return redirect(url_for("customer_portal.index"))
    stats = {}
    chart = []
    stock = []
    recent_sales = []
    jobs = []
    status = {}
    cashier_filter = " WHERE t.created_by=%s" if role == "cashier" else ""
    cashier_args = (current_user.id,) if role == "cashier" else ()
    if role in ("admin", "cashier"):
        paid_filter = "WHERE user_id=%s" if cashier_args else ""
        stats = {
            "sales": row("SELECT COALESCE(SUM(t.total),0) AS n FROM transactions t" + cashier_filter, cashier_args)["n"],
            "income": row("SELECT COALESCE(SUM(amount),0) AS n FROM payments " + paid_filter, cashier_args)["n"],
            "products": row("SELECT COUNT(*) AS n FROM products WHERE active=1")["n"],
            "customers": row("SELECT COUNT(*) AS n FROM customers")["n"],
            "motorcycles": row("SELECT COUNT(*) AS n FROM motorcycles")["n"],
        }
        recent_sales = rows(
            "SELECT t.id,t.total,t.created_at,COALESCE(c.name,'Walk-in') AS customer,"
            "(SELECT COALESCE(SUM(amount),0) FROM payments WHERE transaction_id=t.id) AS paid "
            "FROM transactions t LEFT JOIN customers c ON c.id=t.customer_id" +
            cashier_filter + " ORDER BY t.created_at DESC,t.id DESC LIMIT 6", cashier_args,
        )
        paid_trend = rows(
            "SELECT DATE(p.created_at) AS day,SUM(p.amount) AS amount FROM payments p "
            "WHERE p.created_at>=CURRENT_DATE-INTERVAL 6 DAY" +
            (" AND p.user_id=%s" if cashier_args else "") + " GROUP BY DATE(p.created_at)", cashier_args,
        )
        days = row("SELECT CURRENT_DATE AS today")["today"]
        sales_trend = rows(
            "SELECT DATE(t.created_at) AS day,SUM(t.total) AS amount FROM transactions t "
            "WHERE t.created_at>=CURRENT_DATE-INTERVAL 6 DAY" +
            (" AND t.created_by=%s" if cashier_args else "") + " GROUP BY DATE(t.created_at)", cashier_args,
        )
        paid_values = {item["day"]: item["amount"] for item in paid_trend}
        sales_values = {item["day"]: item["amount"] for item in sales_trend}
        chart = [{"label": day.strftime("%A"), "value": float(paid_values.get(day, 0)),
                  "sales": float(sales_values.get(day, 0))}
                 for day in (days - timedelta(days=i) for i in range(6, -1, -1))]
    if role in ("admin", "mechanic"):
        constraint = " WHERE s.mechanic_id=%s" if role == "mechanic" else ""
        args = (current_user.mechanic_id,) if constraint else ()
        status = dict.fromkeys(STATES, 0)
        status.update({item["status"]: item["n"] for item in rows(
            "SELECT s.status,COUNT(*) AS n FROM services s" + constraint + " GROUP BY s.status", args)})
        jobs = rows(
            "SELECT s.id,s.service_type,s.status,s.updated_at,CONCAT(m.brand,' ',m.model) AS motorcycle "
            "FROM services s JOIN motorcycles m ON m.id=s.motorcycle_id" + constraint +
            " ORDER BY s.updated_at DESC,s.id DESC LIMIT 5", args,
        )
    if role == "admin":
        stats["low"] = row("SELECT COUNT(*) AS n FROM inventory i JOIN products p ON p.id=i.product_id "
                           "WHERE p.active=1 AND i.quantity<=i.minimum")["n"]
        stock = rows("SELECT p.name,p.sku,i.quantity,i.minimum FROM inventory i JOIN products p ON p.id=i.product_id "
                     "WHERE p.active=1 AND i.quantity<=i.minimum ORDER BY i.quantity,p.name LIMIT 5")
    return render_template("dashboard.html", title="Dashboard", stats=stats, chart=chart,
                           recent_sales=recent_sales, jobs=jobs, status=status, stock=stock)
