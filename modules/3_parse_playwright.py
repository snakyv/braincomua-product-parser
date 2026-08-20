"""Searches brain.com.ua with Playwright and saves the required product data."""
import os
import time
from pprint import pprint

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

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

HOME_URL = "https://brain.com.ua/"
SEARCH_QUERY = "Apple iPhone 15 128GB Black"
EXPECTED_PRODUCT_CODE = "U0854689"
EXPECTED_NAME_FRAGMENT = "iPhone 15 128GB Black"
WAIT_MILLISECONDS = 25000
QUICK_SEARCH_WAIT_MILLISECONDS = 4000
RETRY_ACTION_TIMEOUT_MILLISECONDS = 1500

HEADER_BOTTOM_XPATH = (
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' header-bottom ')]"
)
SEARCH_INPUT_XPATH = (
    HEADER_BOTTOM_XPATH
    + "//div[contains(concat(' ', normalize-space(@class), ' '), ' header-search-form ')]"
    "//input[@type='search' and "
    "contains(concat(' ', normalize-space(@class), ' '), ' quick-search-input ')]"
)
SEARCH_FORM_XPATH = "./ancestor::form"
SEARCH_BUTTON_RELATIVE_XPATH = ".//input[@type='submit']"
QSR_INPUT_XPATH = (
    HEADER_BOTTOM_XPATH
    + "//div[contains(concat(' ', normalize-space(@class), ' '), ' qsr-block ')]"
    "//input[contains(concat(' ', normalize-space(@class), ' '), ' qsr-input ')]"
)
QSR_SUBMIT_XPATH = (
    HEADER_BOTTOM_XPATH
    + "//div[contains(concat(' ', normalize-space(@class), ' '), ' qsr-block ')]"
    "//input[@type='submit' and "
    "contains(concat(' ', normalize-space(@class), ' '), ' qsr-submit ')]"
)
SEARCH_RESULT_CARDS_XPATH = (
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' goods-block__item ') and "
    "not(ancestor-or-self::*[contains(concat(' ', normalize-space(@class), ' '), ' hidden ')])]"
)
SEARCH_RESULT_LINK_XPATH = (
    ".//a[contains(@href, 'Mobilniy_telefon_') and "
    "not(ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' hidden ')])]"
)
TITLE_XPATH = (
    "//h1["
    "contains(concat(' ', normalize-space(@class), ' '), ' main-title ') or "
    "contains(concat(' ', normalize-space(@class), ' '), ' desktop-only-title ')"
    "]"
)
PRODUCT_CODE_XPATH = (
    "//div[@id='product_code']//span["
    "contains(concat(' ', normalize-space(@class), ' '), ' br-pr-code-val ')]"
)
REVIEWS_XPATH = (
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' main-comments-block ')]"
    "//a[contains(concat(' ', normalize-space(@class), ' '), ' reviews-count ')]/span"
)
MAIN_PRICE_XPATH = (
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' main-price-block ')]"
)
OLD_PRICE_XPATH = (
    MAIN_PRICE_XPATH
    + "/div[contains(concat(' ', normalize-space(@class), ' '), ' br-pr-op ')]"
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' price-wrapper ')]"
)
CURRENT_PRICE_XPATH = (
    MAIN_PRICE_XPATH
    + "/div[contains(concat(' ', normalize-space(@class), ' '), ' br-pr-np ')]"
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' price-wrapper ')]"
)
GALLERY_IMAGES_XPATH = (
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' br-image-links ')]"
    "//img[contains(concat(' ', normalize-space(@class), ' '), ' br-main-img ')]"
)
CHARACTERISTICS_CONTAINER_XPATH = "//div[@id='br-characteristics']"
CHARACTERISTIC_ROWS_XPATH = (
    CHARACTERISTICS_CONTAINER_XPATH
    + "//div[contains(concat(' ', normalize-space(@class), ' '), ' br-pr-chr-item ')]"
    "/div/div"
)
ROW_LABEL_XPATH = "./span[following-sibling::span]"
ROW_VALUE_XPATH = "./span[preceding-sibling::span]"


def is_headless():
    return os.getenv("BROWSER_HEADLESS", "0").strip().lower() in {"1", "true", "yes"}


def xpath(page_or_locator, expression):
    return page_or_locator.locator(f"xpath={expression}")


def first_visible(locator):
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible():
            return candidate
    return None


def locator_text_content(locator, timeout=3000):
    if locator.count() == 0:
        locator.first.wait_for(state="attached", timeout=timeout)

    candidate = first_visible(locator)
    if candidate is None:
        candidate = locator.first

    value = candidate.text_content(timeout=timeout)
    return normalize_text(value)


def wait_for_first_visible(page, expression, description, timeout_milliseconds=None):
    timeout = timeout_milliseconds or WAIT_MILLISECONDS
    locator = xpath(page, expression)
    deadline = time.monotonic() + (timeout / 1000)

    while time.monotonic() < deadline:
        candidate = first_visible(locator)
        if candidate is not None:
            return candidate
        page.wait_for_timeout(100)

    raise PlaywrightTimeoutError(f"Timed out waiting for {description}")


def wait_for_optional_visible(page, expression, timeout_milliseconds):
    try:
        return wait_for_first_visible(
            page,
            expression,
            "an optional visible element",
            timeout_milliseconds=timeout_milliseconds,
        )
    except PlaywrightTimeoutError:
        return None


def wait_for_homepage_ready(page):
    page.wait_for_load_state("domcontentloaded", timeout=WAIT_MILLISECONDS)
    wait_for_first_visible(
        page,
        SEARCH_INPUT_XPATH,
        "the desktop Brain search input after DOMContentLoaded",
    )


def fill_active_search_input(page):
    """Fills a currently visible search input and re-resolves it if the header changes."""
    deadline = time.monotonic() + (WAIT_MILLISECONDS / 1000)
    last_error = None

    while time.monotonic() < deadline:
        search_inputs = xpath(page, SEARCH_INPUT_XPATH)
        for index in range(search_inputs.count()):
            candidate = search_inputs.nth(index)
            if not candidate.is_visible():
                continue
            try:
                candidate.fill(
                    SEARCH_QUERY,
                    timeout=RETRY_ACTION_TIMEOUT_MILLISECONDS,
                )
                if candidate.input_value(timeout=1000) == SEARCH_QUERY:
                    return
            except PlaywrightTimeoutError as exc:
                last_error = exc
        page.wait_for_timeout(100)

    if last_error is not None:
        raise PlaywrightTimeoutError(
            "Timed out while filling the active Brain search input"
        ) from last_error
    raise PlaywrightTimeoutError("No stable visible Brain search input was available")


def first_visible_product_link(card):
    return first_visible(xpath(card, SEARCH_RESULT_LINK_XPATH))


def get_first_search_result_link(page):
    cards = xpath(page, SEARCH_RESULT_CARDS_XPATH)
    for index in range(cards.count()):
        card = cards.nth(index)
        if not card.is_visible():
            continue
        product_link = first_visible_product_link(card)
        if product_link is not None:
            return product_link
    return None


def wait_for_first_result(page):
    deadline = time.monotonic() + (WAIT_MILLISECONDS / 1000)

    while time.monotonic() < deadline:
        product_link = get_first_search_result_link(page)
        if product_link is not None:
            return product_link
        page.wait_for_timeout(100)

    raise PlaywrightTimeoutError("Timed out waiting for the first Brain search result")

def click_and_wait_for_url(page, locator, url_predicate, description):
    """Performs a normal user click, then verifies the resulting navigation explicitly."""
    click_error = None
    try:
        locator.click(timeout=WAIT_MILLISECONDS)
    except PlaywrightTimeoutError as exc:
        click_error = exc
        if not url_predicate(page.url):
            raise

    try:
        page.wait_for_url(
            lambda url: url_predicate(str(url)),
            wait_until="domcontentloaded",
            timeout=WAIT_MILLISECONDS,
        )
    except PlaywrightTimeoutError as exc:
        if click_error is not None:
            raise PlaywrightTimeoutError(
                f"{description}: the click changed the URL, but DOMContentLoaded did not finish"
            ) from exc
        raise PlaywrightTimeoutError(
            f"{description}: expected navigation did not complete"
        ) from exc


def click_quick_search_submit(page):
    qsr_input = wait_for_optional_visible(
        page,
        QSR_INPUT_XPATH,
        QUICK_SEARCH_WAIT_MILLISECONDS,
    )
    if qsr_input is None:
        return False

    qsr_submit = wait_for_optional_visible(
        page,
        QSR_SUBMIT_XPATH,
        QUICK_SEARCH_WAIT_MILLISECONDS,
    )
    if qsr_submit is None:
        return False

    if qsr_input.input_value() != SEARCH_QUERY:
        qsr_input.fill(SEARCH_QUERY, timeout=WAIT_MILLISECONDS)
        if qsr_input.input_value() != SEARCH_QUERY:
            raise PlaywrightTimeoutError(
                "The complete search query was not present in the active quick-search input"
            )

    click_and_wait_for_url(
        page,
        qsr_submit,
        lambda url: "/search/" in url,
        "Quick-search submission",
    )
    return True


def click_header_search_submit(page):
    search_input = wait_for_first_visible(
        page,
        SEARCH_INPUT_XPATH,
        "the active Brain header search input before submit",
    )
    form = xpath(search_input, SEARCH_FORM_XPATH)
    search_button = first_visible(xpath(form, SEARCH_BUTTON_RELATIVE_XPATH))
    if search_button is None:
        raise PlaywrightTimeoutError("No visible submit button exists in the active search form")

    try:
        click_and_wait_for_url(
            page,
            search_button,
            lambda url: "/search/" in url,
            "Header-search submission",
        )
    except PlaywrightTimeoutError:
        qsr_submit = wait_for_optional_visible(
            page,
            QSR_SUBMIT_XPATH,
            QUICK_SEARCH_WAIT_MILLISECONDS,
        )
        if qsr_submit is None:
            raise
        click_and_wait_for_url(
            page,
            qsr_submit,
            lambda url: "/search/" in url,
            "Quick-search fallback submission",
        )


def submit_search(page):
    if click_quick_search_submit(page):
        return
    click_header_search_submit(page)


def wait_for_product_page(page):
    page.wait_for_url(
        lambda url: "Mobilniy_telefon_" in str(url),
        wait_until="domcontentloaded",
        timeout=WAIT_MILLISECONDS,
    )
    product_title = wait_for_first_visible(
        page,
        TITLE_XPATH,
        "a visible product title after opening the first search result",
    )
    selected_name = normalize_text(product_title.inner_text(timeout=3000))
    if selected_name is None or EXPECTED_NAME_FRAGMENT.lower() not in selected_name.lower():
        raise PlaywrightTimeoutError(
            f"Unexpected product opened after search: {selected_name!r}"
        )

    xpath(page, PRODUCT_CODE_XPATH).first.wait_for(
        state="attached", timeout=WAIT_MILLISECONDS
    )
    xpath(page, CHARACTERISTICS_CONTAINER_XPATH).first.wait_for(
        state="attached", timeout=WAIT_MILLISECONDS
    )
    xpath(page, MAIN_PRICE_XPATH).first.wait_for(
        state="attached", timeout=WAIT_MILLISECONDS
    )
    xpath(page, GALLERY_IMAGES_XPATH).first.wait_for(
        state="attached", timeout=WAIT_MILLISECONDS
    )
    xpath(page, REVIEWS_XPATH).first.wait_for(
        state="attached", timeout=WAIT_MILLISECONDS
    )


def search_product(page):
    print("Playwright step 1/6: homepage opened")
    wait_for_homepage_ready(page)

    print("Playwright step 2/6: stable search input ready")
    fill_active_search_input(page)
    print("Playwright step 3/6: search query entered")

    submit_search(page)
    print("Playwright step 4/6: search submitted and results page opened")

    product_link = wait_for_first_result(page)
    print("Playwright step 5/6: first search result found")

    click_and_wait_for_url(
        page,
        product_link,
        lambda url: "Mobilniy_telefon_" in url,
        "Opening the first product result",
    )
    wait_for_product_page(page)
    print("Playwright step 6/6: product page loaded")


def get_product_name(page):
    try:
        title = first_visible(xpath(page, TITLE_XPATH))
        if title is None:
            return None
        return normalize_text(title.inner_text(timeout=3000))
    except PlaywrightTimeoutError:
        return None


def get_product_code(page):
    try:
        return locator_text_content(xpath(page, PRODUCT_CODE_XPATH))
    except PlaywrightTimeoutError:
        return None


def get_reviews_count(page):
    try:
        return parse_reviews_count(locator_text_content(xpath(page, REVIEWS_XPATH)))
    except PlaywrightTimeoutError:
        return None


def get_prices(page):
    regular_price = None
    sale_price = None

    try:
        regular_price = locator_text_content(xpath(page, OLD_PRICE_XPATH), timeout=2000)
        try:
            sale_price = locator_text_content(
                xpath(page, CURRENT_PRICE_XPATH), timeout=2000
            )
        except PlaywrightTimeoutError:
            sale_price = None
    except PlaywrightTimeoutError:
        try:
            regular_price = locator_text_content(
                xpath(page, CURRENT_PRICE_XPATH), timeout=2000
            )
        except PlaywrightTimeoutError:
            regular_price = None

    return regular_price, sale_price


def get_product_images(page):
    images = xpath(page, GALLERY_IMAGES_XPATH)
    if images.count() == 0:
        return None

    image_urls = []
    for image in images.all():
        image_url = (
            image.get_attribute("data-src")
            or image.get_attribute("data-observe-src")
            or srcset_url(image.get_attribute("srcset"))
            or image.get_attribute("src")
        )
        if image_url is not None:
            image_urls.append(image_url)
    return unique_urls(image_urls)


def get_characteristics(page):
    rows = xpath(page, CHARACTERISTIC_ROWS_XPATH)
    if rows.count() == 0:
        return None

    characteristics = {}
    for row in rows.all():
        try:
            label = locator_text_content(xpath(row, ROW_LABEL_XPATH), timeout=1000)
        except PlaywrightTimeoutError:
            continue

        try:
            value = locator_text_content(xpath(row, ROW_VALUE_XPATH), timeout=1000)
        except PlaywrightTimeoutError:
            continue

        if label is not None and value is not None:
            characteristics[label] = value

    return characteristics or None


def collect_product_data(page):
    characteristics = get_characteristics(page)
    regular_price, sale_price = get_prices(page)

    return {
        "parser_method": "playwright",
        "full_name": get_product_name(page),
        "color": characteristic_value(characteristics, "Колір", "Цвет"),
        "memory": characteristic_value(
            characteristics, "Вбудована пам'ять", "Встроенная память"
        ),
        "manufacturer": characteristic_value(
            characteristics, "Виробник", "Производитель"
        ),
        "regular_price": regular_price,
        "sale_price": sale_price,
        "image_urls": get_product_images(page),
        "product_code": get_product_code(page),
        "reviews_count": get_reviews_count(page),
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


def main():
    product_data = None

    # Playwright's sync runtime owns an event loop while this context is active.
    # Keep the synchronous Django ORM write after the context exits.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=is_headless())
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(WAIT_MILLISECONDS)
        page.set_default_navigation_timeout(WAIT_MILLISECONDS)

        try:
            page.goto(HOME_URL, wait_until="domcontentloaded", timeout=WAIT_MILLISECONDS)
            search_product(page)
            product_data = collect_product_data(page)
            pprint(product_data)
            validate_product_data(
                product_data,
                expected_parser_method="playwright",
                expected_product_code=EXPECTED_PRODUCT_CODE,
                expected_name_fragment=EXPECTED_NAME_FRAGMENT,
            )
        except PlaywrightTimeoutError as exc:
            print(f"Playwright timed out: {exc}")
            print(f"Current URL: {page.url}")
            product_data = None
        except ValueError as exc:
            print(f"Data validation failed: {exc}")
            product_data = None
        finally:
            browser.close()

    if product_data is None:
        return

    product, created = Product.objects.get_or_create(**product_data)
    print(f"Database record id: {product.id}; created: {created}")


if __name__ == "__main__":
    main()
