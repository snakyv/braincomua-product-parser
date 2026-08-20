"""Export validated PostgreSQL ``Product`` records to a UTF-8 CSV file."""

import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

import load_django
from parser_app.models import Product
from parser_helpers import ProductData, validate_product_data


PROJECT_ROOT = load_django.PROJECT_ROOT
OUTPUT_PATH = PROJECT_ROOT / "results" / "products.csv"

FIELD_NAMES = [
    "id",
    "parser_method",
    "full_name",
    "color",
    "memory",
    "manufacturer",
    "regular_price",
    "sale_price",
    "image_urls",
    "product_code",
    "reviews_count",
    "screen_diagonal",
    "display_resolution",
    "characteristics",
]


class ExpectedProduct(TypedDict):
    """Identity values used to guard the final export."""

    product_code: str
    name_fragment: str


EXPECTED_PRODUCTS: dict[str, ExpectedProduct] = {
    "requests_bs4": {
        "product_code": "U0961530",
        "name_fragment": "iPhone 16 Pro Max 256GB Black Titanium",
    },
    "selenium": {
        "product_code": "U0854689",
        "name_fragment": "iPhone 15 128GB Black",
    },
    "playwright": {
        "product_code": "U0854689",
        "name_fragment": "iPhone 15 128GB Black",
    },
}


def serialize_json(value: object | None) -> str | None:
    """Serialize JSON-compatible model values for the CSV export."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def product_to_data(product: Product) -> ProductData:
    """Convert a Django model instance into the normalized parser payload shape."""
    return {
        "parser_method": product.parser_method,
        "full_name": product.full_name,
        "color": product.color,
        "memory": product.memory,
        "manufacturer": product.manufacturer,
        "regular_price": product.regular_price,
        "sale_price": product.sale_price,
        "image_urls": product.image_urls,
        "product_code": product.product_code,
        "reviews_count": product.reviews_count,
        "screen_diagonal": product.screen_diagonal,
        "display_resolution": product.display_resolution,
        "characteristics": product.characteristics,
    }


def validate_database_records(products: Sequence[Product]) -> None:
    """Ensure the database contains one complete record from each parser engine."""
    if len(products) != 3:
        raise RuntimeError(
            f"Expected exactly three final Product records, found {len(products)}. "
            "Remove invalid or duplicate rows before export."
        )

    method_counts: dict[str, int] = {}
    for product in products:
        method_counts[product.parser_method] = (
            method_counts.get(product.parser_method, 0) + 1
        )

    expected_methods = set(EXPECTED_PRODUCTS)
    if set(method_counts) != expected_methods or any(
        count != 1 for count in method_counts.values()
    ):
        raise RuntimeError(
            "Expected exactly one database row for each parser method: "
            "requests_bs4, selenium, playwright."
        )

    for product in products:
        expected = EXPECTED_PRODUCTS.get(product.parser_method)
        if expected is None:
            raise RuntimeError(
                f"Unexpected parser_method in database record id {product.id}: "
                f"{product.parser_method!r}"
            )

        try:
            validate_product_data(
                product_to_data(product),
                expected_parser_method=product.parser_method,
                expected_product_code=expected["product_code"],
                expected_name_fragment=expected["name_fragment"],
            )
        except ValueError as exc:
            raise RuntimeError(
                f"Database record id {product.id} is not valid for export: {exc}"
            ) from exc


def write_csv(products: Sequence[Product], output_path: Path) -> None:
    """Write validated product records to ``output_path``."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELD_NAMES)
        writer.writeheader()

        for product in products:
            writer.writerow(
                {
                    "id": product.id,
                    "parser_method": product.parser_method,
                    "full_name": product.full_name,
                    "color": product.color,
                    "memory": product.memory,
                    "manufacturer": product.manufacturer,
                    "regular_price": product.regular_price,
                    "sale_price": product.sale_price,
                    "image_urls": serialize_json(product.image_urls),
                    "product_code": product.product_code,
                    "reviews_count": product.reviews_count,
                    "screen_diagonal": product.screen_diagonal,
                    "display_resolution": product.display_resolution,
                    "characteristics": serialize_json(product.characteristics),
                }
            )


def main() -> None:
    """Validate PostgreSQL state and write the CSV artifact."""
    products = list(Product.objects.all().order_by("id"))
    if not products:
        raise RuntimeError(
            "No Product records exist. Run the parser scripts before CSV export."
        )

    validate_database_records(products)
    write_csv(products, OUTPUT_PATH)
    print(f"CSV export created: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
