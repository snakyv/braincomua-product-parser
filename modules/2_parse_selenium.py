"""Searches brain.com.ua with Selenium and saves the required product data."""
import os
from pprint import pprint

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

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
WAIT_SECONDS = 25

SEARCH_INPUT_XPATH = (
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' header-search-form ')]"
    "//input[@type='search' and "
    "contains(concat(' ', normalize-space(@class), ' '), ' quick-search-input ')]"
)
SEARCH_FORM_XPATH = "./ancestor::form"
SEARCH_BUTTON_RELATIVE_XPATH = ".//input[@type='submit']"
QSR_RESULT_LINKS_XPATH = (
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' qsr-products-list ')]"
    "//a[contains(@href, 'Mobilniy_telefon_')]"
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


def build_driver():
    options = webdriver.ChromeOptions()
    if is_headless():
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--disable-notifications")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1440, 1000)
    return driver


def first_visible_enabled(elements):
    for element in elements:
        try:
            if element.is_displayed() and element.is_enabled():
                return element
        except StaleElementReferenceException:
            continue
    return False


def wait_for_visible_xpath(driver, wait, expression, description):
    return wait.until(
        lambda current_driver: first_visible_enabled(
            current_driver.find_elements(By.XPATH, expression)
        ),
        message=description,
    )


def element_text_content(element):
    try:
        return normalize_text(element.get_attribute("textContent"))
    except StaleElementReferenceException:
        return None


def first_visible_product_link(container):
    try:
        links = container.find_elements(By.XPATH, SEARCH_RESULT_LINK_XPATH)
    except StaleElementReferenceException:
        return False
    return first_visible_enabled(links)


def get_first_search_result_link(driver, start_url):
    qsr_links = driver.find_elements(By.XPATH, QSR_RESULT_LINKS_XPATH)
    qsr_link = first_visible_enabled(qsr_links)
    if qsr_link:
        return qsr_link

    if driver.current_url == start_url:
        return False

    cards = driver.find_elements(By.XPATH, SEARCH_RESULT_CARDS_XPATH)
    for card in cards:
        try:
            if not card.is_displayed():
                continue
        except StaleElementReferenceException:
            continue

        product_link = first_visible_product_link(card)
        if product_link:
            return product_link

    return False


def click_search_button(search_input, wait):
    form = search_input.find_element(By.XPATH, SEARCH_FORM_XPATH)
    search_button = wait.until(
        lambda _driver: first_visible_enabled(
            form.find_elements(By.XPATH, SEARCH_BUTTON_RELATIVE_XPATH)
        ),
        message="visible submit button in the active header search form",
    )

    try:
        search_button.click()
    except ElementClickInterceptedException:
        wait.until(
            EC.invisibility_of_element_located((By.XPATH, "//*[@id='page-preloader']")),
            message="homepage preloader to disappear before clicking search",
        )
        search_button.click()


def search_product(driver, wait):
    print("Selenium step 1/6: homepage opened")

    search_input = wait_for_visible_xpath(
        driver,
        wait,
        SEARCH_INPUT_XPATH,
        "a visible Brain header search input",
    )
    print("Selenium step 2/6: visible search input found")

    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
        search_input,
    )
    search_input.clear()
    search_input.send_keys(SEARCH_QUERY)

    wait.until(
        lambda _driver: search_input.get_attribute("value") == SEARCH_QUERY,
        message="the complete search query to appear in the search input",
    )
    print("Selenium step 3/6: search query entered")

    start_url = driver.current_url
    click_search_button(search_input, wait)
    print("Selenium step 4/6: search button clicked")

    product_link = wait.until(
        lambda current_driver: get_first_search_result_link(current_driver, start_url),
        message="the first product link in Brain search results",
    )
    print("Selenium step 5/6: first search result found")

    product_link.click()
    wait.until(
        lambda current_driver: "Mobilniy_telefon_" in current_driver.current_url,
        message="navigation to the selected product page",
    )
    wait_for_visible_xpath(
        driver,
        wait,
        TITLE_XPATH,
        "a visible product title after opening the first search result",
    )
    wait.until(
        EC.presence_of_element_located((By.XPATH, PRODUCT_CODE_XPATH)),
        message="product code on the selected product page",
    )
    wait.until(
        EC.presence_of_element_located((By.XPATH, CHARACTERISTICS_CONTAINER_XPATH)),
        message="product characteristics container",
    )
    print("Selenium step 6/6: product page loaded")


def get_product_name(driver):
    try:
        title = first_visible_enabled(driver.find_elements(By.XPATH, TITLE_XPATH))
        if not title:
            return None
        return normalize_text(title.text)
    except StaleElementReferenceException:
        return None


def get_product_code(driver):
    try:
        return element_text_content(driver.find_element(By.XPATH, PRODUCT_CODE_XPATH))
    except NoSuchElementException:
        return None


def get_reviews_count(driver):
    try:
        return parse_reviews_count(
            element_text_content(driver.find_element(By.XPATH, REVIEWS_XPATH))
        )
    except NoSuchElementException:
        return None


def get_prices(driver):
    regular_price = None
    sale_price = None

    try:
        old_price = driver.find_element(By.XPATH, OLD_PRICE_XPATH)
        regular_price = element_text_content(old_price)
        try:
            sale_price = element_text_content(
                driver.find_element(By.XPATH, CURRENT_PRICE_XPATH)
            )
        except NoSuchElementException:
            sale_price = None
    except NoSuchElementException:
        try:
            regular_price = element_text_content(
                driver.find_element(By.XPATH, CURRENT_PRICE_XPATH)
            )
        except NoSuchElementException:
            regular_price = None

    return regular_price, sale_price


def get_product_images(driver):
    images = driver.find_elements(By.XPATH, GALLERY_IMAGES_XPATH)
    if not images:
        return None

    image_urls = []
    for image in images:
        try:
            image_url = (
                image.get_attribute("data-src")
                or image.get_attribute("data-observe-src")
                or srcset_url(image.get_attribute("srcset"))
                or image.get_attribute("src")
            )
        except StaleElementReferenceException:
            continue

        if image_url is not None:
            image_urls.append(image_url)
    return unique_urls(image_urls)


def get_characteristics(driver):
    rows = driver.find_elements(By.XPATH, CHARACTERISTIC_ROWS_XPATH)
    if not rows:
        return None

    characteristics = {}
    for row in rows:
        try:
            label = element_text_content(
                row.find_element(By.XPATH, ROW_LABEL_XPATH)
            )
        except NoSuchElementException:
            continue

        try:
            value = element_text_content(
                row.find_element(By.XPATH, ROW_VALUE_XPATH)
            )
        except NoSuchElementException:
            continue

        if label is not None and value is not None:
            characteristics[label] = value

    return characteristics or None


def collect_product_data(driver):
    characteristics = get_characteristics(driver)
    regular_price, sale_price = get_prices(driver)

    return {
        "parser_method": "selenium",
        "full_name": get_product_name(driver),
        "color": characteristic_value(characteristics, "Колір", "Цвет"),
        "memory": characteristic_value(
            characteristics, "Вбудована пам'ять", "Встроенная память"
        ),
        "manufacturer": characteristic_value(
            characteristics, "Виробник", "Производитель"
        ),
        "regular_price": regular_price,
        "sale_price": sale_price,
        "image_urls": get_product_images(driver),
        "product_code": get_product_code(driver),
        "reviews_count": get_reviews_count(driver),
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
    driver = build_driver()
    wait = WebDriverWait(driver, WAIT_SECONDS)

    try:
        driver.get(HOME_URL)
        search_product(driver, wait)
        product_data = collect_product_data(driver)
        pprint(product_data)

        try:
            validate_product_data(
                product_data,
                expected_parser_method="selenium",
                expected_product_code=EXPECTED_PRODUCT_CODE,
                expected_name_fragment=EXPECTED_NAME_FRAGMENT,
            )
        except ValueError as exc:
            print(f"Data validation failed: {exc}")
            return

        product, created = Product.objects.get_or_create(**product_data)
        print(f"Database record id: {product.id}; created: {created}")
    except TimeoutException as exc:
        print(f"Selenium timed out: {exc.msg}")
        print(f"Current URL: {driver.current_url}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
