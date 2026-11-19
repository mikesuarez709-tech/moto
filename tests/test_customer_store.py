import unittest
from contextlib import nullcontext
from unittest.mock import patch

from app import create_app


class CustomerAccount:
    id = 4
    name = "Test Customer"
    username = "test.customer"
    role = "customer"
    mechanic_id = None
    customer_id = 7
    version = 1
    is_authenticated = True
    is_active = True
    is_anonymous = False

    def get_id(self):
        return "customer:4:1"


class CustomerStoreTests(unittest.TestCase):
    def setUp(self):
        with patch("routes.auth.load_user", side_effect=lambda _identity: CustomerAccount()):
            self.app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = "customer:4:1"
            session["_fresh"] = True

    def test_customer_can_browse_in_stock_products(self):
        product = {
            "id": 5, "name": "Brake pads", "brand": "Moto", "description": "",
            "image_url": "/static/assets/parts/brake_pads.jpg", "price": 125,
            "quantity": 3, "category": "Parts",
        }
        with patch("routes.customer_portal.rows", side_effect=[[product], []]):
            response = self.client.get("/portal/shop")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Brake pads", response.data)
        self.assertIn(b"Request to buy", response.data)
        self.assertIn(b"/static/assets/parts/brake_pads.jpg", response.data)

    def test_customer_purchase_request_checks_stock_and_records_a_request(self):
        product = {"id": 5, "name": "Brake pads", "price": 125, "quantity": 3}
        with patch("routes.customer_portal.atomic", return_value=nullcontext()), \
                patch("routes.customer_portal.row", return_value=None), \
                patch("routes.customer_portal.existing", return_value=product), \
                patch("routes.customer_portal.execute") as save:
            response = self.client.post(
                "/portal/shop/5/request",
                data={"request_key": "11111111111111111111111111111111", "quantity": "2"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn("INSERT INTO purchase_requests", save.call_args.args[0])
        self.assertEqual(save.call_args.args[1][1:], (7, 5, "Brake pads", 2, 125))

    def test_customer_cannot_request_more_than_available_stock(self):
        product = {"id": 5, "name": "Brake pads", "price": 125, "quantity": 1}
        with patch("routes.customer_portal.atomic", return_value=nullcontext()), \
                patch("routes.customer_portal.row", return_value=None), \
                patch("routes.customer_portal.existing", return_value=product), \
                patch("routes.customer_portal.execute") as save:
            response = self.client.post(
                "/portal/shop/5/request",
                data={"request_key": "11111111111111111111111111111111", "quantity": "2"},
            )

        self.assertEqual(response.status_code, 302)
        save.assert_not_called()

    def test_customer_registration_creates_customer_and_portal_account(self):
        client = self.app.test_client()
        with patch("routes.auth.row", side_effect=[None, None]), \
                patch("routes.auth.atomic", return_value=nullcontext()), \
                patch("routes.auth.execute", side_effect=[17, 22]) as save, \
                patch("routes.auth.generate_password_hash", return_value="hashed"):
            response = client.post(
                "/register",
                data={
                    "name": "New Customer",
                    "phone": "09123456789",
                    "address": "Sample Address",
                    "username": "new.customer",
                    "password": "secure-example-password",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/portal/"))
        self.assertIn("INSERT INTO customers", save.call_args_list[0].args[0])
        self.assertIn("INSERT INTO customer_accounts", save.call_args_list[1].args[0])
        with client.session_transaction() as session:
            self.assertEqual(session["_user_id"], "customer:22:1")


if __name__ == "__main__":
    unittest.main()
