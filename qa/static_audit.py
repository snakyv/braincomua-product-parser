"""Runs static checks for project-specific source quality rules."""
import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIT_FILE = Path(__file__).resolve()

SOURCE_PATHS = (
    PROJECT_ROOT / "manage.py",
    PROJECT_ROOT / "braincomua_project",
    PROJECT_ROOT / "parser_app",
    PROJECT_ROOT / "modules",
    PROJECT_ROOT / "qa",
)
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "htmlcov",
    "venv",
}

CHECKS = {
    "bare except": re.compile(r"^\s*except\s*:\s*$", re.MULTILINE),
    "except Exception": re.compile(r"except\s+Exception\s*:"),
    "absolute XPath": re.compile(r"/html/body"),
    "Selenium CSS selector": re.compile(r"By\.CSS_SELECTOR"),
    "Selenium class selector": re.compile(r"By\.CLASS_NAME"),
    "Selenium id selector": re.compile(r"By\.ID"),
    "Playwright role locator": re.compile(r"\.get_by_role\s*\("),
    "Playwright text locator": re.compile(r"\.get_by_text\s*\("),
    "Playwright query selector": re.compile(r"\.query_selector(?:_all)?\s*\("),
    "forced browser click": re.compile(r"\.click\s*\([^\n)]*force\s*=\s*True"),
    "deprecated Playwright no_wait_after": re.compile(r"no_wait_after\s*="),
    "blocking sleep": re.compile(r"\btime\.sleep\s*\("),
    "Django async safety bypass": re.compile(r"DJANGO_ALLOW_ASYNC_UNSAFE"),
    "Django defaults argument": re.compile(r"defaults\s*="),
    "model unique constraint": re.compile(r"unique\s*=\s*True"),
    "indexed find_all": re.compile(r"find_all\([^\n]*\)\s*\[\s*\d+\s*\]"),
    "placeholder missing value": re.compile(
        r"[\"'](?:Not found|N/A|Не найдено|Не знайдено|unknown|-)[\"']",
        re.IGNORECASE,
    ),
}
NUMERIC_XPATH_PREDICATE = re.compile(r"\[\s*\d+\s*\]")


def is_excluded(file_path):
    relative_parts = file_path.relative_to(PROJECT_ROOT).parts
    return any(part in EXCLUDED_DIRECTORY_NAMES for part in relative_parts)


def project_python_files():
    files = []
    for source_path in SOURCE_PATHS:
        if source_path.is_file():
            candidates = [source_path]
        elif source_path.is_dir():
            candidates = source_path.rglob("*.py")
        else:
            continue

        for file_path in candidates:
            file_path = file_path.resolve()
            if file_path == AUDIT_FILE or is_excluded(file_path):
                continue
            files.append(file_path)

    return sorted(set(files))


def has_numeric_xpath(tree):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value
        if ("//" in value or value.startswith("./")) and NUMERIC_XPATH_PREDICATE.search(value):
            return True
    return False


def playwright_locator_is_xpath(node):
    if not node.args:
        return False
    selector = node.args[0]
    if isinstance(selector, ast.Constant) and isinstance(selector.value, str):
        return selector.value.startswith("xpath=")
    if isinstance(selector, ast.JoinedStr) and selector.values:
        first_value = selector.values[0]
        return (
            isinstance(first_value, ast.Constant)
            and isinstance(first_value.value, str)
            and first_value.value.startswith("xpath=")
        )
    return False


def is_by_xpath(node):
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "XPATH"
        and isinstance(node.value, ast.Name)
        and node.value.id == "By"
    )


def ast_policy_failures(tree):
    failures = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue

        method_name = node.func.attr

        if method_name == "locator" and not playwright_locator_is_xpath(node):
            failures.append("Playwright locator is not XPath")

        if method_name in {"find_element", "find_elements"}:
            if not node.args or not is_by_xpath(node.args[0]):
                failures.append("Selenium find_element/find_elements is not XPath")

        if method_name == "get_or_create":
            if node.args:
                failures.append("get_or_create has positional arguments")
                continue
            if len(node.keywords) != 1 or node.keywords[0].arg is not None:
                failures.append("get_or_create must receive one **data dictionary only")

    return failures



def keyword_constant(call_node: ast.Call, keyword_name: str) -> object | None:
    """Return a constant keyword value from an AST call, when present."""
    for keyword in call_node.keywords:
        if keyword.arg == keyword_name and isinstance(keyword.value, ast.Constant):
            return keyword.value.value
    return None


def function_definition(
    tree: ast.Module,
    function_name: str,
) -> ast.FunctionDef | None:
    """Find a top-level function definition by name."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    return None


def attribute_calls(tree: ast.AST, attribute_name: str) -> list[ast.Call]:
    """Collect calls whose callable is an attribute with ``attribute_name``."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute_name
    ]


def navigation_helper_failures(
    navigation_helper: ast.FunctionDef | None,
) -> list[str]:
    """Validate the Playwright click-and-navigation helper contract."""
    if navigation_helper is None:
        return ["Playwright click/navigation helper is missing"]

    failures: list[str] = []
    click_calls = attribute_calls(navigation_helper, "click")
    wait_calls = attribute_calls(navigation_helper, "wait_for_url")

    if len(click_calls) != 1:
        failures.append(
            "Playwright navigation helper must contain exactly one normal click"
        )

    if not wait_calls:
        failures.append(
            "Playwright navigation helper must verify navigation with wait_for_url"
        )
    elif not all(
        keyword_constant(call, "wait_until") == "domcontentloaded"
        for call in wait_calls
    ):
        failures.append(
            "Playwright navigation waits must use DOMContentLoaded readiness"
        )

    return failures


def direct_click_lines(
    tree: ast.Module,
    navigation_helper: ast.FunctionDef | None,
) -> list[int | None]:
    """Return direct Playwright click locations outside the navigation helper."""
    helper_start = navigation_helper.lineno if navigation_helper is not None else None
    helper_end = navigation_helper.end_lineno if navigation_helper is not None else None
    direct_clicks: list[int | None] = []

    for call in attribute_calls(tree, "click"):
        line_number = getattr(call, "lineno", None)
        inside_helper = (
            helper_start is not None
            and helper_end is not None
            and line_number is not None
            and helper_start <= line_number <= helper_end
        )
        if not inside_helper:
            direct_clicks.append(line_number)

    return direct_clicks


def homepage_navigation_failures(tree: ast.Module) -> list[str]:
    """Validate Playwright homepage navigation readiness semantics."""
    goto_calls = attribute_calls(tree, "goto")
    if not goto_calls:
        return ["Playwright homepage navigation is missing"]

    if not all(
        keyword_constant(call, "wait_until") == "domcontentloaded"
        for call in goto_calls
    ):
        return ["Playwright homepage navigation must wait for DOMContentLoaded"]

    return []


def manual_scroll_failures(tree: ast.Module) -> list[str]:
    """Reject manual scrolling that bypasses Playwright's normal action auto-wait."""
    if attribute_calls(tree, "scroll_into_view_if_needed"):
        return [
            "Playwright should rely on action auto-wait instead of manual scroll"
        ]
    return []


def playwright_navigation_contract_failures(tree: ast.Module) -> list[str]:
    """Validate the high-level Playwright navigation and synchronization contract."""
    failures: list[str] = []

    if function_definition(tree, "fill_active_search_input") is None:
        failures.append("Playwright stable search-input helper is missing")

    navigation_helper = function_definition(tree, "click_and_wait_for_url")
    failures.extend(navigation_helper_failures(navigation_helper))

    direct_clicks = direct_click_lines(tree, navigation_helper)
    if direct_clicks:
        failures.append(
            "Playwright navigation must use click_and_wait_for_url; direct click at lines "
            + ", ".join(str(line) for line in direct_clicks)
        )

    failures.extend(homepage_navigation_failures(tree))
    failures.extend(manual_scroll_failures(tree))
    return failures


def main():
    failures = []
    python_files = project_python_files()

    for file_path in python_files:
        source = file_path.read_text(encoding="utf-8")
        relative_path = file_path.relative_to(PROJECT_ROOT)

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            failures.append(
                f"{relative_path}: syntax error at line {exc.lineno}"
            )
            continue

        if ast.get_docstring(tree, clean=False) is None:
            failures.append(f"{relative_path}: missing module docstring")

        for check_name, pattern in CHECKS.items():
            if pattern.search(source):
                failures.append(f"{relative_path}: {check_name}")

        if has_numeric_xpath(tree):
            failures.append(f"{relative_path}: numeric XPath predicate")

        for policy_failure in ast_policy_failures(tree):
            failures.append(f"{relative_path}: {policy_failure}")

        if relative_path.as_posix() == "modules/3_parse_playwright.py":
            for contract_failure in playwright_navigation_contract_failures(tree):
                failures.append(f"{relative_path}: {contract_failure}")

    if failures:
        print("Static audit failed:")
        for failure in sorted(set(failures)):
            print(f"- {failure}")
        raise SystemExit(1)

    print(f"Static audit passed for {len(python_files)} first-party Python files.")


if __name__ == "__main__":
    main()
