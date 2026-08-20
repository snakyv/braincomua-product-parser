"""Shared normalization, URL, and parsed-product validation helpers."""

import re
from collections.abc import Mapping, Sequence
from typing import TypedDict
from urllib.parse import urljoin


BASE_URL = "https://brain.com.ua/"
REQUIRED_PRODUCT_FIELDS = (
    "full_name",
    "color",
    "memory",
    "manufacturer",
    "regular_price",
    "image_urls",
    "product_code",
    "reviews_count",
    "screen_diagonal",
    "display_resolution",
    "characteristics",
)


class ProductData(TypedDict):
    """Normalized product payload shared by all parser engines."""

    parser_method: str
    full_name: str | None
    color: str | None
    memory: str | None
    manufacturer: str | None
    regular_price: str | None
    sale_price: str | None
    image_urls: list[str] | None
    product_code: str | None
    reviews_count: int | None
    screen_diagonal: str | None
    display_resolution: str | None
    characteristics: dict[str, str] | None


def normalize_text(value: object | None) -> str | None:
    """Collapse whitespace and convert empty values to ``None``."""
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized or None


def parse_reviews_count(value: object | None) -> int | None:
    """Extract the first integer from a review-count label."""
    normalized = normalize_text(value)
    if normalized is None:
        return None
    match = re.search(r"\d+", normalized)
    return int(match.group()) if match else None


def normalize_url(value: object | None) -> str | None:
    """Normalize a relative or absolute Brain.com.ua asset URL."""
    normalized = normalize_text(value)
    if normalized is None:
        return None
    return urljoin(BASE_URL, normalized)


def srcset_url(value: object | None) -> str | None:
    """Select the highest-resolution URL from an HTML ``srcset`` value."""
    normalized = normalize_text(value)
    if normalized is None:
        return None

    candidates: list[tuple[float, str]] = []
    for candidate in normalized.split(","):
        parts = candidate.strip().split()
        if not parts:
            continue

        image_url = parts[0]
        score = 0.0
        if len(parts) > 1:
            descriptor = parts[1].lower()
            try:
                if descriptor.endswith("w"):
                    score = float(descriptor[:-1])
                elif descriptor.endswith("x"):
                    score = float(descriptor[:-1]) * 1_000_000
            except ValueError:
                score = 0.0
        candidates.append((score, image_url))

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def unique_urls(values: Sequence[object | None]) -> list[str] | None:
    """Normalize, de-duplicate, and preserve the order of image URLs."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_url(value)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result or None


def characteristic_value(
    characteristics: Mapping[str, str] | None,
    *labels: str,
) -> str | None:
    """Return the first matching characteristic value by semantic label."""
    if not characteristics:
        return None
    for label in labels:
        if label in characteristics:
            return characteristics[label]
    return None


def _missing_required_fields(product_data: Mapping[str, object]) -> list[str]:
    """Return required field names whose values are missing or empty."""
    missing_fields: list[str] = []
    for field_name in REQUIRED_PRODUCT_FIELDS:
        value = product_data.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing_fields.append(field_name)
    return missing_fields


def _validate_collection_fields(product_data: Mapping[str, object]) -> None:
    """Validate the list and dictionary fields required by every parser payload."""
    image_urls = product_data.get("image_urls")
    if not isinstance(image_urls, list) or not image_urls:
        raise ValueError("image_urls must be a non-empty list")

    characteristics = product_data.get("characteristics")
    if not isinstance(characteristics, dict) or not characteristics:
        raise ValueError("characteristics must be a non-empty dictionary")


def _validate_expected_identity(
    product_data: Mapping[str, object],
    expected_parser_method: str | None,
    expected_product_code: str | None,
    expected_name_fragment: str | None,
) -> None:
    """Validate optional parser, product-code, and title identity constraints."""
    if (
        expected_parser_method is not None
        and product_data.get("parser_method") != expected_parser_method
    ):
        raise ValueError(
            "Unexpected parser_method: "
            f"{product_data.get('parser_method')!r}; expected {expected_parser_method!r}"
        )

    if (
        expected_product_code is not None
        and product_data.get("product_code") != expected_product_code
    ):
        raise ValueError(
            "Unexpected product_code: "
            f"{product_data.get('product_code')!r}; expected {expected_product_code!r}"
        )

    if expected_name_fragment is None:
        return

    full_name_value = product_data.get("full_name")
    full_name = full_name_value if isinstance(full_name_value, str) else ""
    if expected_name_fragment.lower() not in full_name.lower():
        raise ValueError(
            "Unexpected product title: "
            f"{full_name!r}; expected it to contain {expected_name_fragment!r}"
        )


def validate_product_data(
    product_data: Mapping[str, object],
    expected_parser_method: str | None = None,
    expected_product_code: str | None = None,
    expected_name_fragment: str | None = None,
) -> None:
    """Raise ``ValueError`` when a parsed payload is incomplete or unexpected."""
    missing_fields = _missing_required_fields(product_data)
    if missing_fields:
        raise ValueError(
            "Required parsed values are missing: " + ", ".join(missing_fields)
        )

    _validate_collection_fields(product_data)
    _validate_expected_identity(
        product_data,
        expected_parser_method,
        expected_product_code,
        expected_name_fragment,
    )
