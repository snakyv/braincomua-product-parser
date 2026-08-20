"""Validate PostgreSQL records, CSV export, and the PostgreSQL dump artifact."""

import csv
import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from pprint import pprint
from typing import TypedDict, cast

from modules import load_django
from modules.parser_helpers import ProductData, validate_product_data
from parser_app.models import Product


PROJECT_ROOT = load_django.PROJECT_ROOT

CSV_PATH = PROJECT_ROOT / "results" / "products.csv"
DUMP_PATH = PROJECT_ROOT / "results" / "database.dump"
EXPECTED_METHODS = {"requests_bs4", "selenium", "playwright"}
EXPECTED_CSV_FIELDS = [
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
    """Expected identity values for a parser result."""

    product_code: str
    name_fragment: str


class CheckedRecord(TypedDict):
    """Compact record summary displayed after successful validation."""

    id: int
    parser_method: str
    full_name: str | None
    product_code: str | None
    images: int
    characteristics: int
    sale_price: str | None


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


def require(condition: bool, message: str) -> None:
    """Raise ``RuntimeError`` when a validation condition is false."""
    if not condition:
        raise RuntimeError(message)


def product_to_data(product: Product) -> ProductData:
    """Convert a Django model instance to the normalized parser payload shape."""
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


def expected_product(parser_method: str, context: str) -> ExpectedProduct:
    """Return expected identity data for a known parser method."""
    expected = EXPECTED_PRODUCTS.get(parser_method)
    if expected is None:
        raise RuntimeError(f"{context} has unexpected parser_method: {parser_method!r}")
    return expected


def summarize_product(product: Product) -> CheckedRecord:
    """Build a compact, type-safe validation summary for one database record."""
    image_urls = product.image_urls
    characteristics = product.characteristics
    require(
        isinstance(image_urls, list),
        f"PostgreSQL record id {product.id} has invalid image_urls.",
    )
    require(
        isinstance(characteristics, dict),
        f"PostgreSQL record id {product.id} has invalid characteristics.",
    )

    return {
        "id": product.id,
        "parser_method": product.parser_method,
        "full_name": product.full_name,
        "product_code": product.product_code,
        "images": len(image_urls),
        "characteristics": len(characteristics),
        "sale_price": product.sale_price,
    }


def validate_database() -> tuple[list[Product], list[CheckedRecord]]:
    """Validate the final PostgreSQL state and return checked records."""
    products = list(Product.objects.all().order_by("id"))
    require(
        len(products) == 3,
        f"Expected exactly three final Product records in PostgreSQL, found {len(products)}.",
    )

    present_methods = {product.parser_method for product in products}
    missing_methods = EXPECTED_METHODS - present_methods
    require(
        not missing_methods,
        f"Missing parser methods in PostgreSQL: {sorted(missing_methods)}",
    )

    method_counts = {
        parser_method: sum(
            1 for product in products if product.parser_method == parser_method
        )
        for parser_method in EXPECTED_METHODS
    }
    require(
        all(count == 1 for count in method_counts.values()),
        f"Expected exactly one final row per parser method, found: {method_counts}",
    )

    checked_records: list[CheckedRecord] = []
    for product in products:
        expected = expected_product(
            product.parser_method,
            f"PostgreSQL record id {product.id}",
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
                f"Invalid PostgreSQL record id {product.id}: {exc}"
            ) from exc

        checked_records.append(summarize_product(product))

    return products, checked_records


def read_csv_rows() -> list[dict[str, str | None]]:
    """Read the CSV artifact after validating its exact header schema."""
    require(CSV_PATH.is_file(), f"CSV file is missing: {CSV_PATH}")
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        require(
            reader.fieldnames == EXPECTED_CSV_FIELDS,
            "CSV headers do not match the expected schema.",
        )
        return list(reader)


def required_csv_value(
    row: Mapping[str, str | None],
    field_name: str,
    row_id: str,
) -> str:
    """Return a required CSV value or raise a precise validation error."""
    value = row.get(field_name)
    if value is None or value == "":
        raise RuntimeError(f"CSV row id {row_id} has empty {field_name}.")
    return value


def optional_csv_value(
    row: Mapping[str, str | None],
    field_name: str,
) -> str | None:
    """Convert an empty nullable CSV field back to ``None``."""
    value = row.get(field_name)
    return value or None


def parse_csv_images(value: str, row_id: str) -> list[str]:
    """Parse and validate the serialized image URL list from one CSV row."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"CSV row id {row_id} has invalid JSON in image_urls: {exc}"
        ) from exc

    require(
        isinstance(parsed, list)
        and bool(parsed)
        and all(isinstance(item, str) and bool(item) for item in parsed),
        f"CSV row id {row_id} image_urls must be a non-empty string list.",
    )
    return cast(list[str], parsed)


def parse_csv_characteristics(value: str, row_id: str) -> dict[str, str]:
    """Parse and validate the serialized characteristics dictionary."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"CSV row id {row_id} has invalid JSON in characteristics: {exc}"
        ) from exc

    require(
        isinstance(parsed, dict)
        and bool(parsed)
        and all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in parsed.items()
        ),
        f"CSV row id {row_id} characteristics must be a non-empty string dictionary.",
    )
    return cast(dict[str, str], parsed)


def parse_csv_reviews_count(value: str | None, row_id: str) -> int | None:
    """Parse the nullable review count field from a CSV row."""
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(
            f"CSV row id {row_id} has invalid reviews_count: {value!r}"
        ) from exc


def csv_row_to_product_data(row: Mapping[str, str | None]) -> ProductData:
    """Convert one CSV row back to the normalized parser payload shape."""
    row_id = required_csv_value(row, "id", "<unknown>")
    parser_method = required_csv_value(row, "parser_method", row_id)
    image_urls = parse_csv_images(
        required_csv_value(row, "image_urls", row_id),
        row_id,
    )
    characteristics = parse_csv_characteristics(
        required_csv_value(row, "characteristics", row_id),
        row_id,
    )

    return {
        "parser_method": parser_method,
        "full_name": optional_csv_value(row, "full_name"),
        "color": optional_csv_value(row, "color"),
        "memory": optional_csv_value(row, "memory"),
        "manufacturer": optional_csv_value(row, "manufacturer"),
        "regular_price": optional_csv_value(row, "regular_price"),
        "sale_price": optional_csv_value(row, "sale_price"),
        "image_urls": image_urls,
        "product_code": optional_csv_value(row, "product_code"),
        "reviews_count": parse_csv_reviews_count(row.get("reviews_count"), row_id),
        "screen_diagonal": optional_csv_value(row, "screen_diagonal"),
        "display_resolution": optional_csv_value(row, "display_resolution"),
        "characteristics": characteristics,
    }


def validate_csv_row(row: Mapping[str, str | None]) -> None:
    """Validate one exported CSV row against parser identity and data rules."""
    row_id = required_csv_value(row, "id", "<unknown>")
    product_data = csv_row_to_product_data(row)
    parser_method = product_data["parser_method"]
    expected = expected_product(parser_method, f"CSV row id {row_id}")

    try:
        validate_product_data(
            product_data,
            expected_parser_method=parser_method,
            expected_product_code=expected["product_code"],
            expected_name_fragment=expected["name_fragment"],
        )
    except ValueError as exc:
        raise RuntimeError(f"Invalid CSV row id {row_id}: {exc}") from exc


def validate_csv(database_products: Sequence[Product]) -> int:
    """Cross-check CSV rows against the validated PostgreSQL records."""
    rows = read_csv_rows()
    require(
        len(rows) == len(database_products),
        "CSV row count does not match PostgreSQL record count.",
    )

    database_ids = {str(product.id) for product in database_products}
    csv_ids = {
        required_csv_value(row, "id", "<unknown>")
        for row in rows
    }
    require(
        csv_ids == database_ids,
        "CSV record IDs do not match PostgreSQL record IDs.",
    )

    for row in rows:
        validate_csv_row(row)

    return len(rows)


def postgres_version_key(path: Path) -> tuple[int, ...]:
    """Return a sortable numeric version extracted from a PostgreSQL tool path."""
    if len(path.parts) < 3:
        return (0,)
    version = path.parts[-3]
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (0,)


def find_pg_restore() -> str | None:
    """Locate ``pg_restore`` from configuration, PATH, or standard installations."""
    configured = os.getenv("PG_RESTORE_PATH")
    if configured and Path(configured).is_file():
        return configured

    pg_restore = shutil.which("pg_restore")
    if pg_restore:
        return pg_restore

    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        postgresql_root = Path(program_files) / "PostgreSQL"
        if postgresql_root.is_dir():
            candidates = sorted(
                postgresql_root.glob("*/bin/pg_restore.exe"),
                key=postgres_version_key,
                reverse=True,
            )
            if candidates:
                return str(candidates[0])

    pg_dump_path = os.getenv("PG_DUMP_PATH")
    if pg_dump_path:
        sibling = Path(pg_dump_path).with_name("pg_restore.exe")
        if sibling.is_file():
            return str(sibling)

    return None


def validate_dump() -> int:
    """Verify that the custom-format dump exists and is readable by ``pg_restore``."""
    require(DUMP_PATH.is_file(), f"PostgreSQL dump is missing: {DUMP_PATH}")
    require(DUMP_PATH.stat().st_size > 0, "PostgreSQL dump is empty.")

    pg_restore = find_pg_restore()
    if pg_restore is None:
        raise RuntimeError(
            "pg_restore was not found. Add PostgreSQL bin to PATH or set PG_RESTORE_PATH."
        )

    result = subprocess.run(
        [pg_restore, "--list", str(DUMP_PATH)],
        check=True,
        capture_output=True,
        text=True,
    )
    require(
        bool(result.stdout.strip()),
        "pg_restore returned an empty archive listing.",
    )
    return DUMP_PATH.stat().st_size


def main() -> None:
    """Run database, CSV, and dump validation and print the final summary."""
    database_products, checked_records = validate_database()
    csv_rows = validate_csv(database_products)
    dump_size = validate_dump()

    pprint(
        {
            "status": "passed",
            "database_rows": len(database_products),
            "csv_rows": csv_rows,
            "dump_size_bytes": dump_size,
            "checked_records": checked_records,
        }
    )


if __name__ == "__main__":
    main()
