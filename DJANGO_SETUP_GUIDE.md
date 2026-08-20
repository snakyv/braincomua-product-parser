# Django + PostgreSQL Setup Guide

A concise setup guide for running the Brain.com.ua product data pipeline locally with Python 3.12, Django, PostgreSQL, Selenium, and Playwright.

## 1. Open the Project Root

Open the `braincomua_project` directory — the folder that contains:

```text
manage.py
requirements.txt
modules/
parser_app/
```

## 2. Create a Python 3.12 Virtual Environment

### PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Verify the interpreter:

```powershell
python --version
```

Expected: Python `3.12.x`.

## 3. Install Playwright Chromium

```powershell
python -m playwright install chromium
```

The Python `playwright` package and the Chromium browser binary are installed separately, so this step is required before running the Playwright parser.

## 4. Create the PostgreSQL Database

Using `psql` or pgAdmin:

```sql
CREATE DATABASE brain_parser;
```

## 5. Configure `.env`

Copy `.env.example` to `.env` and replace the local values:

```env
DJANGO_SECRET_KEY=replace-with-a-local-secret
DJANGO_DEBUG=0
DB_NAME=brain_parser
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=127.0.0.1
DB_PORT=5432
BROWSER_HEADLESS=0
```

`BROWSER_HEADLESS=0` keeps Selenium and Playwright visible during local runs. Set it to `1` for headless execution.

### Optional PostgreSQL tool paths

The project searches for `pg_dump` and `pg_restore` in `PATH` and standard Windows PostgreSQL directories. For a custom installation, add:

```env
PG_DUMP_PATH=C:\Program Files\PostgreSQL\17\bin\pg_dump.exe
PG_RESTORE_PATH=C:\Program Files\PostgreSQL\17\bin\pg_restore.exe
```

## 6. Initialize Django

```powershell
python manage.py check
python manage.py migrate
```

Optional migration status check:

```powershell
python manage.py showmigrations parser_app
```

`parser_app.0001_initial` should be marked with `[X]` after migration.

## 7. Run Static Checks

```powershell
python qa/static_audit.py
python -m compileall -q manage.py braincomua_project parser_app modules qa
```

The static audit validates first-party source code only and excludes virtual environments and external packages.

## 8. Run the Three Parsers

Run them in order:

```powershell
python modules/1_parse_requests_bs4.py
python modules/2_parse_selenium.py
python modules/3_parse_playwright.py
```

A successful run prints one normalized dictionary with `pprint` and a PostgreSQL record result.

Expected parser methods:

```text
requests_bs4
selenium
playwright
```

## 9. Inspect PostgreSQL Records

```powershell
python manage.py shell
```

Then:

```python
from parser_app.models import Product
Product.objects.count()
list(Product.objects.values_list("parser_method", "product_code"))
```

Exit:

```python
exit()
```

## 10. Export CSV

```powershell
python modules/4_export_csv.py
```

Output:

```text
results/products.csv
```

The exporter validates the database state before writing the file.

## 11. Create a PostgreSQL Backup

```powershell
python modules/5_dump_database.py
```

Output:

```text
results/database.dump
```

Validate the backup manually if needed:

```powershell
pg_restore --list results/database.dump
```

## 12. Run End-to-End Validation

```powershell
python -m qa.runtime_validation
```

A successful run ends with:

```text
'status': 'passed'
```

The validator checks the PostgreSQL records, required product fields, CSV alignment, JSON payloads, backup existence, and PostgreSQL backup readability.

## 13. Restore the Backup in a Separate Database

Create an empty database:

```sql
CREATE DATABASE brain_parser_restore;
```

Restore:

```powershell
pg_restore --no-owner --dbname=brain_parser_restore results/database.dump
```

Use a separate database for restore checks so the active development database remains unchanged.

## Recommended Run Order

```text
1. python manage.py check
2. python manage.py migrate
3. python qa/static_audit.py
4. python modules/1_parse_requests_bs4.py
5. python modules/2_parse_selenium.py
6. python modules/3_parse_playwright.py
7. python modules/4_export_csv.py
8. python modules/5_dump_database.py
9. python -m qa.runtime_validation
```

## Common Issues

### Playwright cannot launch Chromium

```powershell
python -m playwright install chromium
```

### Django cannot connect to PostgreSQL

Check:

- PostgreSQL service is running
- database `brain_parser` exists
- `.env` credentials are correct
- host and port match the local PostgreSQL configuration

### `pg_dump` is not found

Set `PG_DUMP_PATH` in `.env` or add the PostgreSQL `bin` directory to `PATH`.

### Browser extraction stops after a website update

Inspect the current Brain.com.ua DOM in DevTools and update the semantic selectors. Keep browser locators XPath-based and avoid copied absolute `/html/body/...` paths.
