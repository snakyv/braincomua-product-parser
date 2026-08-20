"""Parses the required brain.com.ua product using Requests and BeautifulSoup."""
from pprint import pprint

import requests
from bs4 import BeautifulSoup

from load_django import *
from parser_app.models import Product
from parser_helpers import (
    characteristic_value,
    normalize_text,
    parse_reviews_count,
    srcset_url,
    unique_urls,
    validate_product_data,
)

EXPECTED_PRODUCT_CODE = "U0961530"
EXPECTED_NAME_FRAGMENT = "iPhone 16 Pro Max 256GB Black Titanium"

PRODUCT_URL = (
    "https://brain.com.ua/ukr/"
    "Mobilniy_telefon_Apple_iPhone_16_Pro_Max_256GB_Black_Titanium-p1145443.html"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
}


def get_product_name(soup):
    try:
        return normalize_text(soup.find("h1", class_="main-title").get_text(" ", strip=True))
    except AttributeError:
        return None


def get_product_code(soup):
    try:
        code_container = soup.find("div", id="product_code")
        return normalize_text(
            code_container.find("span", class_="br-pr-code-val").get_text(" ", strip=True)
        )
    except AttributeError:
        return None


def get_reviews_count(soup):
    try:
        comments_container = soup.find("div", class_="main-comments-block")
        reviews_link = comments_container.find("a", class_="reviews-count")
        return parse_reviews_count(reviews_link.get_text(" ", strip=True))
    except AttributeError:
        return None


def get_prices(soup):
    regular_price = None
    sale_price = None

    try:
        price_container = soup.find("div", class_="main-price-block")
        old_price = price_container.find("div", class_="br-pr-op")
        current_price = price_container.find("div", class_="br-pr-np")

        if old_price is not None:
            regular_price = normalize_text(old_price.get_text(" ", strip=True))
            if current_price is not None:
                sale_price = normalize_text(current_price.get_text(" ", strip=True))
        elif current_price is not None:
            regular_price = normalize_text(current_price.get_text(" ", strip=True))
    except AttributeError:
        regular_price = None
        sale_price = None

    return regular_price, sale_price


def get_product_images(soup):
    try:
        gallery_container = soup.find("div", class_="br-image-links")
        image_urls = []
        for image in gallery_container.find_all("img", class_="br-main-img"):
            image_url = (
                image.get("data-src")
                or image.get("data-observe-src")
                or srcset_url(image.get("srcset"))
                or image.get("src")
            )
            if image_url is not None:
                image_urls.append(image_url)
        return unique_urls(image_urls)
    except AttributeError:
        return None


def get_characteristics(soup):
    try:
        characteristics_container = soup.find("div", id="br-characteristics")
        characteristics_block = characteristics_container.find("div", class_="br-pr-chr")
    except AttributeError:
        return None

    characteristics = {}
    for section in characteristics_block.find_all("div", class_="br-pr-chr-item", recursive=False):
        section_body = section.find("div", recursive=False)
        if section_body is None:
            continue

        for row in section_body.find_all("div", recursive=False):
            label_tag = row.find("span", recursive=False)
            if label_tag is None:
                continue

            value_tag = label_tag.find_next_sibling("span")
            if value_tag is None:
                continue

            label = normalize_text(label_tag.get_text(" ", strip=True))
            value = normalize_text(value_tag.get_text(" ", strip=True))
            if label is not None and value is not None:
                characteristics[label] = value

    return characteristics or None


def parse_product_html(html):
    soup = BeautifulSoup(html, "html.parser")
    characteristics = get_characteristics(soup)
    regular_price, sale_price = get_prices(soup)

    return {
        "parser_method": "requests_bs4",
        "full_name": get_product_name(soup),
        "color": characteristic_value(characteristics, "Колір", "Цвет"),
        "memory": characteristic_value(
            characteristics, "Вбудована пам'ять", "Встроенная память"
        ),
        "manufacturer": characteristic_value(
            characteristics, "Виробник", "Производитель"
        ),
        "regular_price": regular_price,
        "sale_price": sale_price,
        "image_urls": get_product_images(soup),
        "product_code": get_product_code(soup),
        "reviews_count": get_reviews_count(soup),
        "screen_diagonal": characteristic_value(
            characteristics, "Діагональ екрану", "Диагональ экрана"
        ),
        "display_resolution": characteristic_value(
            characteristics,
            "Роздільна здатність екрану",
            "Разрешение экрана",
            "Разрешение дисплея",
        ),
        "characteristics": characteristics,
    }


def fetch_product_html():
    response = requests.get(PRODUCT_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    if response.encoding is None or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def main():
    try:
        html = fetch_product_html()
    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        return

    product_data = parse_product_html(html)
    pprint(product_data)

    try:
        validate_product_data(
            product_data,
            expected_parser_method="requests_bs4",
            expected_product_code=EXPECTED_PRODUCT_CODE,
            expected_name_fragment=EXPECTED_NAME_FRAGMENT,
        )
    except ValueError as exc:
        print(f"Data validation failed: {exc}")
        return

    product, created = Product.objects.get_or_create(**product_data)
    print(f"Database record id: {product.id}; created: {created}")


if __name__ == "__main__":
    main()
