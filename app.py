from datetime import date, datetime, timezone, timedelta

import click
from flask import Flask, g, render_template
from flask_login import AnonymousUserMixin, LoginManager
from flask_wtf import CSRFProtect
from mysql.connector import Error
from werkzeug.security import generate_password_hash

from config import settings
from database.db_connection import atomic, close_connection, connection, execute, row
from routes import (auth, customer_portal, customers, dashboard, inventory, mechanics, motorcycles, products,
                    reports, services, transactions)
from routes.common import page_url


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.update(settings())
    if overrides:
        app.config.update(overrides)
    app.teardown_appcontext(close_connection)
    CSRFProtect(app)
    login = LoginManager(app)
    login.login_view = "auth.login"
    login.login_message = "Sign in to continue."
    login.login_message_category = "error"
    login.user_loader(auth.load_user)

    for module in (auth, customer_portal, dashboard, products, inventory, customers, motorcycles,
                   services, mechanics, transactions, reports):
        app.register_blueprint(module.bp)

    @app.context_processor
    def shell():
        db_zone = app.config["DATABASE"].get("time_zone", "+08:00")
        if db_zone[:1] in ("+", "-") and len(db_zone) == 6:
            offset = timedelta(hours=int(db_zone[1:3]), minutes=int(db_zone[4:6]))
            today = datetime.now(timezone(offset if db_zone[0] == "+" else -offset)).date()
        else:
            today = datetime.now(timezone(timedelta(hours=8))).date()
        return {"shop_name": app.config["SHOP_NAME"], "today": today, "page_url": page_url}

    app.jinja_env.filters["money"] = lambda x: f"₱{(x or 0):,.2f}"
    app.jinja_env.filters["shortdate"] = lambda x: x.strftime("%b %d, %Y") if isinstance(x, date) else "—"

    @app.errorhandler(400)
    def bad_request(_error):
        return render_template("error.html", title="Request could not be submitted",
                               message="Reload the page and try again. Form sessions expire for security."), 400

    @app.errorhandler(403)
    def denied(_error):
        return render_template("error.html", title="Access restricted",
                               message="Your account does not have permission to open this page."), 403

    @app.errorhandler(404)
    def missing(_error):
        return render_template("error.html", title="Page not found",
                               message="This page or record may have moved or been removed."), 404

    @app.errorhandler(413)
    def too_large(_error):
        return render_template("error.html", title="Request too large",
                               message="Reduce the number of entries and try again."), 413

    @app.errorhandler(Error)
    def database_error(error):
        app.logger.error("MySQL operation failed (errno=%s).", error.errno)
        if "_login_user" not in g:
            g._login_user = AnonymousUserMixin()
        return render_template("error.html", title="Database unavailable",
                               message="Your request could not be completed. Check the MySQL connection and try again."), 503

    @app.cli.command("init-db")
    def initialize():
        """Create the MotorShop tables in the configured database."""
        from pathlib import Path
        sql = Path(app.root_path, "database.sql").read_text(encoding="utf-8")
        with connection().cursor() as cursor:
            for statement in sql.split(";"):
                if statement.strip():
                    cursor.execute(statement)
        click.echo("MySQL tables are ready.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Full name")
    @click.option("--username", prompt=True)
    @click.password_option()
    def create_admin(name, username, password):
        """Create an administrator using a privately entered password."""
        try:
            name, username = auth.account_identity(name, username)
            auth.validate_password(password)
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        if (row("SELECT id FROM users WHERE username=%s", (username,))
                or row("SELECT id FROM customer_accounts WHERE username=%s", (username,))):
            raise click.ClickException("That username is already in use.")
        execute("INSERT INTO users (name,username,password_hash,role) VALUES (%s,%s,%s,'admin')",
                (name, username, generate_password_hash(password)))
        click.echo(f"Created Administrator account {username}.")

    @app.cli.command("create-demo-customer")
    def create_demo_customer():
        """Create a demo customer and print its one-time sign-in credentials."""
        from secrets import token_urlsafe

        username = "demo.customer"
        if (row("SELECT id FROM users WHERE username=%s", (username,))
                or row("SELECT id FROM customer_accounts WHERE username=%s", (username,))):
            raise click.ClickException("The demo customer account already exists.")
        name, username = auth.account_identity("MotorShop Demo Customer", username)
        password = token_urlsafe(24)
        with atomic():
            customer_id = execute(
                "INSERT INTO customers (name,phone,address) VALUES (%s,%s,%s)",
                (name, "0000000000", "Demo account only"),
            )
            execute(
                "INSERT INTO customer_accounts (customer_id,username,password_hash) VALUES (%s,%s,%s)",
                (customer_id, username, generate_password_hash(password)),
            )
        click.echo(f"Demo customer username: {username}")
        click.echo(f"Temporary password: {password}")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
