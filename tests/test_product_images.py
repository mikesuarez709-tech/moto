import unittest
from unittest.mock import patch

from app import create_app
from routes.common import Invalid, image_url


class AdminAccount:
    id = 1
    name = "Test Administrator"
    role = "admin"
    is_authenticated = True
    is_active = True
    is_anonymous = False

    def get_id(self):
        return "1:1"


class ProductImageTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})

    def test_accepts_a_bundled_parts_image(self):
        with self.app.test_request_context(
            "/products/new",
            method="POST",
            data={"image_url": "/static/assets/parts/brake_pads.jpg"},
        ):
            self.assertEqual(image_url(), "/static/assets/parts/brake_pads.jpg")

    def test_rejects_an_unlisted_local_path(self):
        with self.app.test_request_context(
            "/products/new",
            method="POST",
            data={"image_url": "/static/assets/parts/../../secret.jpg"},
        ):
            with self.assertRaises(Invalid):
                image_url()

    def test_still_accepts_https_image_urls(self):
        value = "https://example.com/product.jpg"
        with self.app.test_request_context(
            "/products/new",
            method="POST",
            data={"image_url": value},
        ):
            self.assertEqual(image_url(), value)

    def test_product_form_offers_bundled_parts_images(self):
        with patch("routes.auth.load_user", side_effect=lambda _identity: AdminAccount()):
            app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
        client = app.test_client()
        with patch("routes.products.category_list", return_value=[]):
            with client.session_transaction() as session:
                session["_user_id"] = "1:1"
                session["_fresh"] = True
            response = client.get("/products/new")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/static/assets/parts/brake_pads.jpg", response.data)
        self.assertIn(b"data-product-image-preview", response.data)


if __name__ == "__main__":
    unittest.main()
