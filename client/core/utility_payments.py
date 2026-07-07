from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


def product_price_kobo(product: dict[str, Any], field: str) -> int | None:
    value = product.get(field)
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def amount_within_product_range(amount_kobo: int, product: dict[str, Any]) -> bool:
    minimum = product_price_kobo(product, "minimum_amount")
    maximum = product_price_kobo(product, "maximum_amount")
    if minimum is not None and amount_kobo < minimum:
        return False
    if maximum is not None and amount_kobo > maximum:
        return False
    return True


def resolve_service_amount_kobo(
    requested_amount: float,
    product: dict[str, Any],
) -> tuple[int, bool]:
    try:
        amount = Decimal(str(requested_amount))
    except (InvalidOperation, ValueError):
        raise ValueError("Amount must be a valid number")

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be greater than zero")

    amount_from_naira = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    has_price_range = (
        product_price_kobo(product, "minimum_amount") is not None
        or product_price_kobo(product, "maximum_amount") is not None
    )
    if not has_price_range or amount_within_product_range(amount_from_naira, product):
        return amount_from_naira, False

    # Older GateNode docs described this request field as kobo. Accept that
    # format only when the NGN interpretation is invalid and the kobo value
    # is an integer inside the selected product's advertised price range.
    integral_amount = amount.to_integral_value()
    if amount == integral_amount:
        legacy_kobo = int(integral_amount)
        if amount_within_product_range(legacy_kobo, product):
            return legacy_kobo, True

    minimum = product_price_kobo(product, "minimum_amount")
    maximum = product_price_kobo(product, "maximum_amount")
    if minimum is not None and maximum is not None and minimum == maximum:
        raise ValueError(f"Selected product costs NGN {minimum / 100:.2f}")

    bounds = []
    if minimum is not None:
        bounds.append(f"minimum NGN {minimum / 100:.2f}")
    if maximum is not None:
        bounds.append(f"maximum NGN {maximum / 100:.2f}")
    raise ValueError(f"Amount is outside the selected product range ({', '.join(bounds)})")


def select_service_product(
    products: list[dict[str, Any]],
    product_code: str | None,
) -> dict[str, Any]:
    if product_code:
        for product in products:
            if product.get("slug") == product_code or product.get("id") == product_code:
                return product
        raise ValueError("Selected product is not available for this service provider")
    if len(products) > 1:
        raise ValueError("Select a product before making this utility payment")
    return products[0]
