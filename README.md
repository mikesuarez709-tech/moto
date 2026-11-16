# MotorShop Management System

MotorShop is a Flask and MySQL application for a motorcycle repair and spare-parts shop. It manages parts, stock movements, customers, motorcycles, mechanics, service jobs, sales, recorded payments, receipts, reports, and staff accounts. Checkout and service parts use historical unit prices. All stock and payment changes are stored in MySQL.

## Start locally on Windows

1. Install Python 3.11 or newer and MySQL Server 8.0.16 or newer. Make sure the MySQL service is running. Open the MySQL command line or MySQL Workbench with an administrative account.
2. Create a database and a dedicated app user. Replace the sample password with a strong, unique password.

   ```sql
   CREATE DATABASE motor_shop_db CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
   CREATE USER 'motor_shop_app'@'127.0.0.1' IDENTIFIED BY 'REPLACE_WITH_A_STRONG_PASSWORD';
   GRANT CREATE, REFERENCES, SELECT, INSERT, UPDATE, DELETE
       ON motor_shop_db.* TO 'motor_shop_app'@'127.0.0.1';
   ```

3. Extract the ZIP and open PowerShell in the `MotorShop` folder. Run these commands.

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   Copy-Item .env.example .env
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
   ```

4. Open `.env` in a text editor. Copy the generated value into `SECRET_KEY`. Set `DB_PASSWORD` to the account password you chose, and verify `DB_HOST`, `DB_PORT`, `DB_USER`, and `DB_NAME`. The default business time zone is UTC+08:00. If a password contains `#` or spaces, quote its value in `.env`.

   ```powershell
   .\.venv\Scripts\python.exe -m flask --app app init-db
   .\.venv\Scripts\python.exe -m flask --app app create-admin
   .\.venv\Scripts\python.exe app.py
   ```

   The account command asks for a name, username, and password. Enter a unique password of at least 12 characters. There are no preset accounts or seeded business records. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) and sign in with the account you created.

On Linux or macOS, use `python3 -m venv .venv`, `cp .env.example .env`, and replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`. Alternatively, import `database.sql` into the selected MySQL database with Workbench or `mysql -u motor_shop_app -p -h 127.0.0.1 motor_shop_db < database.sql` from a shell that supports input redirection. Importing the schema and running `init-db` are equivalent for initial setup.

## Use the system

- **Administrator:** Open **Products → Categories**, create a category and product, then use **Inventory → Adjust stock** to add opening stock. Register a customer, their motorcycle, and an available mechanic before creating a service job. Use **User accounts** to add cashiers and mechanics. Link every mechanic login to the correct mechanic record.
- **Cashier:** Register or edit customers, create multi-item product sales, and view, collect payments for, or print receipts for sales created by their own account. Use **Transactions → Service payments** to record payments and print service receipts for non-cancelled jobs.
- **Mechanic:** View assigned jobs, including motorcycle details, and advance their progress from **Pending** to **In Progress** to **Completed**. The administrator controls cancellation and financial changes.
- **Payments:** Cash, GCash, and bank transfers are recorded in the system after collection. Enter a reference for GCash or bank transfers. The application does not initiate transfers or verify them with a provider. Outstanding balances accept installments. Records with payments cannot be cancelled since refunds and reversals are outside this scope.
- **Inventory:** Selling a product or adding a part to a service immediately decreases stock in the same database transaction as the new record. Returning a part or cancelling an unpaid job restores the outstanding parts. A product with historical references is archived when its stock reaches zero and the administrator deletes it. Unused products can be deleted.
- **Reports:** The sales report shows product sale value and payments received, including payments recorded for services. Report cards use the selected date range, while search filters narrow the detailed rows. Inventory is a current snapshot. Export the filtered report to CSV or open its print view. Reports and receipts use the browser’s print dialog, including Save as PDF.

## Deploy online with Render and an external MySQL database

Render runs the Python web application. Provision a separate MySQL 8 database on a host reachable by your Render service. Configure the database provider’s networking rules and TLS settings. Initialize the hosted schema and create the first administrator using the CLI with the hosted database connection settings, either from an allowed workstation or a shell with access to the database. The web service can use a runtime user restricted to `SELECT, INSERT, UPDATE, DELETE` once the schema is initialized.

1. Push the source files to a Git repository, keeping `.env` out of Git.
2. Create a **Python Web Service** on Render and connect that repository. If the repo contains a top-level `MotorShop/` directory, set **Root Directory** to `MotorShop`. Leave it blank if `app.py` is in the repository root.
3. Set **Build Command** to `pip install -r requirements.txt` and **Start Command** to `gunicorn app:app`. The included Gunicorn configuration binds to Render’s `PORT`.
4. Add `APP_ENV=production`, a stable random `SECRET_KEY` of at least 32 characters, and the external provider’s `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` as environment variables. Set `DB_TIME_ZONE` for the shop. If the provider supplies a CA certificate, upload it as a secret file and set `DB_SSL_CA` to its path. This enables certificate and hostname verification. Use the HTTPS service URL with production cookies.

[Render Flask deployment](https://render.com/docs/deploy-flask) · [Render environment variables and secret files](https://render.com/docs/configure-environment-variables)

## Project structure

```text
MotorShop/
├── app.py                    Application factory and setup commands
├── config.py                 Environment configuration
├── database.sql              MySQL schema
├── requirements.txt          Python dependencies
├── Procfile
├── gunicorn.conf.py          Production bind and workers
├── .env.example
├── .gitignore
├── database/
│   └── db_connection.py
├── routes/
│   ├── auth.py, dashboard.py, products.py, inventory.py
│   ├── customers.py, motorcycles.py, services.py, mechanics.py
│   ├── transactions.py, reports.py
│   └── common.py             Shared validation, authorization and financial helpers
├── templates/
│   ├── base.html, login.html, dashboard.html
│   ├── products/, inventory/, customers/, motorcycles/
│   ├── services/, mechanics/, transactions/, reports/
│   └── Shared UI, error and user-account templates
└── static/
    ├── css/                  Custom styles, local fonts and licenses
    ├── js/script.js          Vanilla JavaScript
    └── images/               Workshop artwork
```

The schema keeps all 12 specified tables and adds `payments` to record each installment with its amount, method, reference, operator, and parent sale or service. Additional templates support stock adjustment and history, category management, staff accounts, customer profiles, and shared inputs.

## Verification and scope

Integration checks ran against MySQL Community Server 8.4.13. They covered schema initialization, account creation, role restrictions, CSRF, product CRUD and archival, stock movements, customer and motorcycle registration, mechanic assignment and completion, service parts and returns, partial payments, duplicate prevention, historical prices, and a concurrent purchase of the last unit. Records remained available to a separately started Flask server. Chromium checks covered the desktop and mobile-width layouts, the dashboard chart selector, checkout totals, confirmations, and receipt printing. All five report types returned their filtered pages, CSV exports, and print views. Gunicorn started with the production configuration and issued secure session cookie attributes. Render deployment and physical mobile devices and printers were outside the test environment.

The workshop image in `static/images/workshop.webp` is generated artwork used on the sign-in page and dashboard. Its brief was an unbranded black cafe racer in a dark workshop under warm amber work lights. Product photos are optional HTTPS URLs. The browser aspect of the payment workflow is a record of payments received by staff.
