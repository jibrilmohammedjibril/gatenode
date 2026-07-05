import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "client/core/utility_payments.py"
SPEC = importlib.util.spec_from_file_location("utility_payments", MODULE_PATH)
utility_payments = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(utility_payments)


class UtilityPaymentAmountTests(unittest.TestCase):
    def test_ngn_amount_is_converted_to_kobo(self):
        product = {"minimum_amount": 10000, "maximum_amount": 10000}

        amount_kobo, used_legacy = utility_payments.resolve_service_amount_kobo(100, product)

        self.assertEqual(amount_kobo, 10000)
        self.assertFalse(used_legacy)

    def test_legacy_kobo_is_accepted_when_ngn_interpretation_is_invalid(self):
        product = {"minimum_amount": 10000, "maximum_amount": 10000}

        amount_kobo, used_legacy = utility_payments.resolve_service_amount_kobo(10000, product)

        self.assertEqual(amount_kobo, 10000)
        self.assertTrue(used_legacy)

    def test_ngn_interpretation_wins_when_both_units_fit_variable_range(self):
        product = {"minimum_amount": 10000, "maximum_amount": 1000000}

        amount_kobo, used_legacy = utility_payments.resolve_service_amount_kobo(10000, product)

        self.assertEqual(amount_kobo, 1000000)
        self.assertFalse(used_legacy)

    def test_out_of_range_amount_reports_fixed_product_price(self):
        product = {"minimum_amount": 10000, "maximum_amount": 10000}

        with self.assertRaisesRegex(ValueError, "Selected product costs NGN 100.00"):
            utility_payments.resolve_service_amount_kobo(50, product)

    def test_product_selection_accepts_slug_or_id(self):
        products = [{"id": "product-1", "slug": "mtn-data-100"}]

        self.assertIs(
            utility_payments.select_service_product(products, "mtn-data-100"),
            products[0],
        )
        self.assertIs(
            utility_payments.select_service_product(products, "product-1"),
            products[0],
        )

    def test_unknown_product_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Selected product is not available"):
            utility_payments.select_service_product(
                [{"id": "product-1", "slug": "mtn-data-100"}],
                "missing-product",
            )

    def test_missing_product_is_rejected_when_provider_has_multiple_options(self):
        with self.assertRaisesRegex(ValueError, "Select a product"):
            utility_payments.select_service_product(
                [
                    {"id": "product-1", "slug": "prepaid"},
                    {"id": "product-2", "slug": "postpaid"},
                ],
                None,
            )

    def test_decimal_string_product_prices_are_supported(self):
        self.assertEqual(
            utility_payments.product_price_kobo(
                {"minimum_amount": "10000.00"},
                "minimum_amount",
            ),
            10000,
        )


if __name__ == "__main__":
    unittest.main()
