import unittest
from contextlib import nullcontext
from datetime import datetime
from unittest.mock import patch

from app import create_app
from routes.common import Invalid


class TestAccount:
    id = 1
    name = "Test Customer"
    username = "test.customer"
    mechanic_id = None
    customer_id = 7
    version = 1
    is_authenticated = True
    is_active = True
    is_anonymous = False

    def __init__(self, role="customer"):
        self.role = role

    def get_id(self):
        return "1:1"


class CustomerPortalTests(unittest.TestCase):
    def setUp(self):
        self.account = TestAccount()
        with patch("routes.auth.load_user", return_value=self.account):
            self.app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = "1:1"
            session["_fresh"] = True

    def test_portal_scopes_all_customer_queries_to_the_authenticated_customer(self):
        calls = []

        def fake_rows(sql, args=()):
            calls.append((sql, args))
            return []

        with patch("routes.customer_portal.get_or_404", return_value={"id": 7, "name": "Test Customer"}), \
                patch("routes.customer_portal.rows", side_effect=fake_rows):
            response = self.client.get("/portal/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(calls)
        self.assertTrue(all(args == (7,) for _, args in calls))
        self.assertTrue(all("customer_id=%s" in sql for sql, _ in calls))

    def test_customer_receipt_is_restricted_to_the_authenticated_customer(self):
        item = {
            "id": 12,
            "total": 25,
            "paid": 0,
            "created_at": None,
            "customer": "Test Customer",
            "operator": "Staff",
        }
        with patch("routes.customer_portal.get_or_404", return_value=item) as get_record, \
                patch("routes.customer_portal.rows", return_value=[]):
            response = self.client.get("/portal/receipt/sale/12")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_record.call_args.args[1], (12, 7))
        self.assertIn("t.customer_id=%s", get_record.call_args.args[0])

    def test_customer_cannot_request_service_for_another_customers_motorcycle(self):
        with patch("routes.customer_portal.atomic", return_value=nullcontext()), \
                patch("routes.customer_portal.row", return_value=None), \
                patch("routes.customer_portal.existing", side_effect=Invalid("Choose one of your registered motorcycles.")) as check_bike, \
                patch("routes.customer_portal.execute") as save_request:
            response = self.client.post(
                "/portal/requests",
                data={
                    "request_key": "11111111111111111111111111111111",
                    "motorcycle_id": "22",
                    "service_type": "Oil change",
                    "description": "",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(check_bike.call_args.args[1], (22, 7))
        save_request.assert_not_called()

    def test_staff_account_cannot_open_customer_portal(self):
        self.account.role = "cashier"
        with patch("routes.auth.load_user", return_value=self.account):
            response = self.client.get("/portal/")

        self.assertEqual(response.status_code, 403)

    def test_customer_login_redirects_to_the_portal(self):
        client = self.app.test_client()
        customer_record = {
            "id": 9,
            "name": "Test Customer",
            "username": "test.customer",
            "role": "customer",
            "mechanic_id": None,
            "customer_id": 7,
            "active": True,
            "password_hash": "hash",
            "checked_at": datetime.now(),
            "locked_until": None,
            "failed_attempts": 0,
            "session_version": 1,
        }
        with patch("routes.auth.atomic", return_value=nullcontext()), \
        patch("routes.auth.row", side_effect=[None, customer_record]) as find_account, \
                patch("routes.auth.check_password_hash", return_value=True), \
                patch("routes.auth.execute"):
            response = client.post(
                "/login", data={"username": "test.customer", "password": "valid-password"}
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/portal/"))
        self.assertIn("a.password_hash", find_account.call_args_list[1].args[0])
        with client.session_transaction() as session:
            self.assertEqual(session["_user_id"], "customer:9:1")

    def test_admin_creates_a_separate_customer_portal_account(self):
        self.account.role = "admin"
        with patch("routes.customer_portal.get_or_404", return_value={"id": 7, "name": "Test Customer"}), \
                patch("routes.customer_portal.row", side_effect=[None, None, None]), \
                patch("routes.customer_portal.atomic", return_value=nullcontext()), \
                patch("routes.customer_portal.generate_password_hash", return_value="hashed"), \
                patch("routes.customer_portal.execute") as save_account:
            response = self.client.post(
                "/portal/customers/7/account",
                data={"username": "test.customer", "password": "valid-password", "active": "1"},
            )

        self.assertEqual(response.status_code, 302)
        query = save_account.call_args.args[0]
        self.assertIn("INSERT INTO customer_accounts", query)
        self.assertEqual(save_account.call_args.args[1], (7, "test.customer", "hashed", 1))

    def test_admin_can_open_customer_portal_account_form(self):
        self.account.role = "admin"
        with patch("routes.customer_portal.get_or_404", return_value={"id": 7, "name": "Test Customer"}), \
                patch("routes.customer_portal.row", return_value=None):
            response = self.client.get("/portal/customers/7/account")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Create sign-in access", response.data)


if __name__ == "__main__":
    unittest.main()
