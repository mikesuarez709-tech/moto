from flask import Blueprint, flash, redirect, render_template, request, url_for
from mysql.connector import Error

from database.db_connection import atomic, execute, row, rows
from routes.common import (Invalid, PRODUCT_IMAGE_URLS, amount, existing, field, get_or_404, image_url,
                           notify_error, number, pager, pattern, roles, search)

bp = Blueprint("products", __name__, url_prefix="/products")


@bp.get("/")
@roles("admin")
def index():
    query = search()
    category = request.args.get("category", type=int)
    view = request.args.get("view", "active")
    matches = [pattern(query)] * 3
    sql = ("SELECT p.*,c.name AS category,i.quantity FROM products p JOIN categories c ON c.id=p.category_id "
           "JOIN inventory i ON i.product_id=p.id WHERE (p.name LIKE %s ESCAPE '!' OR p.sku LIKE %s ESCAPE '!' "
           "OR p.brand LIKE %s ESCAPE '!')")
    if view != "all":
        sql += " AND p.active=%s"
        matches.append(view != "archived")
    if category:
        sql += " AND c.id=%s"
        matches.append(category)
    entries, pagination = pager(sql + " ORDER BY p.name,p.id", tuple(matches))
    return render_template("products/index.html", title="Products", entries=entries, pagination=pagination,
                           query=query, category=category, view=view, categories=category_list())


def category_list():
    return rows("SELECT id,name FROM categories ORDER BY name")


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<int:ident>/edit", methods=["GET", "POST"])
@roles("admin")
def form(ident=None):
    entry = get_or_404("SELECT p.*,i.minimum FROM products p JOIN inventory i ON i.product_id=p.id WHERE p.id=%s",
                       (ident,)) if ident else {}
    if request.method == "POST":
        try:
            values = (number("category_id"), field("sku", 40).upper(), field("name", 120),
                      field("brand", 80, required=False), field("description", 1000, required=False),
                      image_url(), amount("price"))
            minimum = number("minimum", minimum=0)
            with atomic():
                existing("SELECT id FROM categories WHERE id=%s", (values[0],), "Select a product category.")
                if ident:
                    execute("UPDATE products SET category_id=%s,sku=%s,name=%s,brand=%s,description=%s,image_url=%s,price=%s WHERE id=%s",
                            (*values, ident))
                    execute("UPDATE inventory SET minimum=%s WHERE product_id=%s", (minimum, ident))
                else:
                    product = execute("INSERT INTO products (category_id,sku,name,brand,description,image_url,price) "
                                      "VALUES (%s,%s,%s,%s,%s,%s,%s)", values)
                    execute("INSERT INTO inventory (product_id,minimum) VALUES (%s,%s)", (product, minimum))
            flash("Product saved.", "success")
            return redirect(url_for("products.index"))
        except (Invalid, Error) as error:
            notify_error(error)
            entry = {**entry, **request.form}
    return render_template("products/edit.html" if ident else "products/add.html", title="Edit product" if ident else "Add product",
                           entry=entry, categories=category_list(),
                           product_images=[
                               {"url": url, "label": url.rsplit("/", 1)[-1].removesuffix(".jpg").replace("_", " ").title()}
                               for url in PRODUCT_IMAGE_URLS
                           ],
                           product_image_urls=PRODUCT_IMAGE_URLS)


@bp.post("/<int:ident>/delete")
@roles("admin")
def delete(ident):
    try:
        with atomic():
            item = get_or_404("SELECT p.id,i.quantity FROM products p JOIN inventory i ON i.product_id=p.id "
                              "WHERE p.id=%s FOR UPDATE", (ident,))
            if item["quantity"]:
                raise Invalid("Move remaining stock out before deleting this product.")
            used = row("SELECT EXISTS(SELECT 1 FROM stock_movements WHERE product_id=%s) OR "
                       "EXISTS(SELECT 1 FROM transaction_items WHERE product_id=%s) OR "
                       "EXISTS(SELECT 1 FROM service_details WHERE product_id=%s) AS used", (ident, ident, ident))["used"]
            if used:
                execute("UPDATE products SET active=FALSE WHERE id=%s", (ident,))
            else:
                execute("DELETE FROM products WHERE id=%s", (ident,))
        flash("Product archived to preserve its history." if used else "Product deleted.", "success")
    except (Invalid, Error) as error:
        notify_error(error)
    return redirect(url_for("products.index"))


@bp.post("/<int:ident>/restore")
@roles("admin")
def restore(ident):
    get_or_404("SELECT id FROM products WHERE id=%s", (ident,))
    execute("UPDATE products SET active=TRUE WHERE id=%s", (ident,))
    flash("Product restored.", "success")
    return redirect(url_for("products.index"))


@bp.route("/categories", methods=["GET", "POST"])
@roles("admin")
def categories():
    if request.method == "POST":
        try:
            action = request.form.get("action")
            if action == "add":
                execute("INSERT INTO categories (name) VALUES (%s)", (field("name", 90),))
            elif action == "edit":
                execute("UPDATE categories SET name=%s WHERE id=%s", (field("name", 90), number("category_id")))
            elif action == "delete":
                execute("DELETE FROM categories WHERE id=%s", (number("category_id"),))
            else:
                raise Invalid("Select a valid action.")
            flash("Categories updated.", "success")
        except (Invalid, Error) as error:
            notify_error(error)
        return redirect(url_for("products.categories"))
    entries, pagination = pager(
        "SELECT c.id,c.name,(SELECT COUNT(*) FROM products p WHERE p.category_id=c.id) AS products "
        "FROM categories c ORDER BY c.name"
    )
    return render_template("products/categories.html", title="Categories", entries=entries, pagination=pagination)
