import csv
from io import StringIO

from flask import Blueprint, Response, redirect, render_template, request, url_for

from database.db_connection import row, rows
from routes.common import Invalid, date_window, notify_error, pager, pattern, roles, search

bp = Blueprint("reports", __name__, url_prefix="/reports")
REPORTS = {
    "sales": ("Sales by date", (("day", "Date", "date"), ("sales_count", "Sales", ""),
                                ("sales_total", "Sales value", "money"), ("income", "Paid income", "money"))),
    "products": ("Best-selling products", (("product", "Product", ""), ("quantity", "Units sold", ""),
                                            ("revenue", "Sales value", "money"))),
    "inventory": ("Inventory and low stock", (("sku", "SKU", ""), ("product", "Product", ""), ("category", "Category", ""),
                                              ("quantity", "On hand", ""), ("minimum", "Minimum", ""), ("status", "Status", ""))),
    "services": ("Service jobs", (("id", "Job #", ""), ("created_at", "Opened", "date"), ("service_type", "Service", ""),
                                   ("mechanic", "Mechanic", ""), ("status", "Status", ""),
                                   ("cost", "Job total", "money"), ("paid", "Paid", "money"))),
    "mechanics": ("Mechanic performance", (("mechanic", "Mechanic", ""), ("pending", "Pending", ""),
                                           ("progress", "In progress", ""), ("completed", "Completed", ""),
                                           ("cancelled", "Cancelled", ""))),
}


def report_sql(report, start, until, query, low):
    like = pattern(query)
    window = (start, until)
    if report == "sales":
        return (
            "SELECT days.day, SUM(days.sales_count) AS sales_count,SUM(days.sales_total) AS sales_total,"
            "SUM(days.income) AS income FROM ("
            "SELECT DATE(t.created_at) AS day,COUNT(*) AS sales_count,SUM(t.total) AS sales_total,0 AS income "
            "FROM transactions t LEFT JOIN customers c ON c.id=t.customer_id "
            "WHERE t.created_at>=%s AND t.created_at<%s AND CONCAT_WS(' ',t.id,c.name,'Walk-in') LIKE %s ESCAPE '!' "
            "GROUP BY DATE(t.created_at) UNION ALL "
            "SELECT DATE(p.created_at),0,0,SUM(p.amount) FROM payments p "
            "LEFT JOIN transactions t ON t.id=p.transaction_id LEFT JOIN services s ON s.id=p.service_id "
            "LEFT JOIN customers c ON c.id=COALESCE(t.customer_id,s.customer_id) WHERE p.created_at>=%s AND p.created_at<%s "
            "AND CONCAT_WS(' ',COALESCE(t.id,s.id),c.name,IF(c.id IS NULL,'Walk-in',''),p.method) LIKE %s ESCAPE '!' "
            "GROUP BY DATE(p.created_at)) days GROUP BY days.day ORDER BY days.day DESC",
            (*window, like, *window, like),
        )
    if report == "products":
        return (
            "SELECT p.id,p.name AS product,SUM(i.quantity) AS quantity,SUM(i.quantity*i.unit_price) AS revenue "
            "FROM transaction_items i JOIN transactions t ON t.id=i.transaction_id JOIN products p ON p.id=i.product_id "
            "WHERE t.created_at>=%s AND t.created_at<%s AND CONCAT_WS(' ',p.sku,p.name) LIKE %s ESCAPE '!' "
            "GROUP BY p.id,p.name ORDER BY quantity DESC,p.name",
            (*window, like),
        )
    if report == "inventory":
        return (
            "SELECT p.sku,p.name AS product,c.name AS category,i.quantity,i.minimum,"
            "IF(i.quantity<=i.minimum,'Low stock','In stock') AS status FROM inventory i "
            "JOIN products p ON p.id=i.product_id JOIN categories c ON c.id=p.category_id "
            "WHERE p.active=1 AND CONCAT_WS(' ',p.sku,p.name,c.name) LIKE %s ESCAPE '!'"
            + (" AND i.quantity<=i.minimum" if low else "") + " ORDER BY i.quantity,p.name",
            (like,),
        )
    if report == "services":
        return (
            "SELECT s.id,s.created_at,s.service_type,m.name AS mechanic,s.status,"
            "IF(s.status='Cancelled',0,s.labor+COALESCE((SELECT SUM(quantity*unit_price) FROM service_details "
            "WHERE service_id=s.id AND returned_at IS NULL),0)) AS cost,"
            "(SELECT COALESCE(SUM(amount),0) FROM payments WHERE service_id=s.id) AS paid "
            "FROM services s JOIN mechanics m ON m.id=s.mechanic_id WHERE s.created_at>=%s AND s.created_at<%s AND "
            "CONCAT_WS(' ',s.id,s.service_type,m.name,s.status) LIKE %s ESCAPE '!' ORDER BY s.id DESC",
            (*window, like),
        )
    return (
        "SELECT m.id,m.name AS mechanic,COALESCE(SUM(s.status='Pending'),0) AS pending,"
        "COALESCE(SUM(s.status='In Progress'),0) AS progress,COALESCE(SUM(s.status='Completed'),0) AS completed,"
        "COALESCE(SUM(s.status='Cancelled'),0) AS cancelled FROM mechanics m LEFT JOIN services s "
        "ON s.mechanic_id=m.id AND COALESCE(s.completed_at,s.created_at)>=%s AND COALESCE(s.completed_at,s.created_at)<%s "
        "WHERE m.name LIKE %s ESCAPE '!' GROUP BY m.id,m.name ORDER BY completed DESC,m.name",
        (*window, like),
    )


def csv_value(value):
    if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n"))):
        return "'" + value
    return value


@bp.get("/")
@roles("admin")
def index():
    report = request.args.get("report", "sales")
    if report not in REPORTS:
        report = "sales"
    try:
        period, start, end, until = date_window()
    except Invalid as exc:
        notify_error(exc)
        return redirect(url_for("reports.index", report=report))
    query = search()
    low = request.args.get("low") == "1"
    sql, args = report_sql(report, start, until, query, low)
    label, columns = REPORTS[report]
    action = request.args.get("format")
    if action == "csv":
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow([name for _, name, _ in columns])
        for entry in rows(sql, args):
            writer.writerow([csv_value(entry[key]) for key, _, _ in columns])
        return Response("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="motorshop-{report}-{start}.csv"'})
    if action == "print":
        entries, pagination = rows(sql, args), None
    else:
        entries, pagination = pager(sql, args)
    summary = row(
        "SELECT (SELECT COALESCE(SUM(total),0) FROM transactions WHERE created_at>=%s AND created_at<%s) AS sales,"
        "(SELECT COALESCE(SUM(amount),0) FROM payments WHERE created_at>=%s AND created_at<%s) AS income,"
        "(SELECT COUNT(*) FROM services WHERE created_at>=%s AND created_at<%s) AS jobs,"
        "(SELECT COUNT(*) FROM inventory i JOIN products p ON p.id=i.product_id WHERE p.active=1 AND i.quantity<=i.minimum) AS low",
        (start, until) * 3,
    )
    params = {"report": report, "period": period, "start": start, "end": end, "q": query, "low": "1" if low else "0"}
    return render_template("reports/index.html", title="Reports", entries=entries, pagination=pagination,
                           reports=REPORTS, report=report, label=label, columns=columns, summary=summary,
                           params=params, print_view=action == "print")
