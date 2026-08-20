<div align="center">

# Brain.com.ua Product Data Pipeline

**A multi-engine product extraction pipeline backed by Django and PostgreSQL.**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Selenium](https://img.shields.io/badge/Selenium-4.47-43B02A?logo=selenium&logoColor=white)](https://www.selenium.dev/)
[![Playwright](https://img.shields.io/badge/Playwright-1.62-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/)

Requests + BeautifulSoup · Selenium · Playwright · PostgreSQL · CSV · Database backup

</div>

---

## Overview

This repository implements the same product-data workflow through **three independent parsing engines**:

| Engine | Navigation model | Primary use |
|---|---|---|
| **Requests + BeautifulSoup** | Direct HTTP request | Fast server-side HTML parsing |
| **Selenium** | Real Chrome browser | Browser-driven extraction with explicit waits |
| **Playwright** | Real Chromium browser | Browser-driven extraction with built-in actionability and navigation waits |

All three parsers normalize data into the same Django `Product` model, persist it in PostgreSQL, print the collected dictionary with `pprint`, and feed the same export and validation pipeline.

### Collected product fields

- Full product name
- Color
- Built-in memory
- Manufacturer
- Regular price
- Sale price when available
- Product image URLs as a list
- Product code
- Review count
- Screen diagonal
- Display resolution
- Full characteristics map as a dictionary
- Parser method used to collect the record

Missing values are represented as `None` instead of placeholder strings.

---

## Architecture

```text
                         ┌─────────────────────┐
                         │    brain.com.ua     │
                         └──────────┬──────────┘
                                    │
                  ┌─────────────────┼─────────────────┐
                  │                 │                 │
                  ▼                 ▼                 ▼
        ┌─────────────────┐ ┌──────────────┐ ┌────────────────┐
        │ Requests + BS4  │ │   Selenium   │ │   Playwright   │
        └────────┬────────┘ └──────┬───────┘ └────────┬───────┘
                 │                 │                  │
                 └─────────────────┼──────────────────┘
                                   ▼
                         ┌─────────────────────┐
                         │ Django Product model│
                         └──────────┬──────────┘
                                    ▼
                         ┌─────────────────────┐
                         │     PostgreSQL      │
                         └───────┬─────┬───────┘
                                 │     │
                           CSV   │     │   pg_dump
                                 ▼     ▼
                       products.csv  database.dump
                                 │     │
                                 └──┬──┘
                                    ▼
                           runtime_validation.py
```

---

## Engineering Principles

The implementation is intentionally defensive against common scraping failures:

- **Semantic label-to-value extraction** — product characteristics are identified by their labels and sibling values instead of positional indexes.
- **XPath-only browser selectors** — Selenium and Playwright use concise structural XPath expressions rather than copied absolute DOM paths.
- **Explicit missing-value handling** — unavailable values become `None`.
- **Specific exceptions** — extraction code avoids broad `except Exception` handlers.
- **Container reuse** — characteristics are collected once and reused for derived fields such as color, memory, manufacturer, diagonal, and resolution.
- **Browser synchronization** — Selenium uses `WebDriverWait`; Playwright uses locator actionability, DOM readiness checks, bounded polling, and URL navigation waits.
- **Safe Django persistence** — records are saved with `Product.objects.get_or_create(**product_data)` without `defaults` or artificial uniqueness rules.
- **Runtime verification** — the final validator cross-checks PostgreSQL, CSV content, and the PostgreSQL custom-format backup.

---

## Repository Structure

```text
braincomua_project/
├── braincomua_project/          # Django project configuration
├── parser_app/                  # Product model and migrations
├── modules/
│   ├── 1_parse_requests_bs4.py  # Requests + BeautifulSoup parser
│   ├── 2_parse_selenium.py      # Selenium parser
│   ├── 3_parse_playwright.py    # Playwright parser
│   ├── 4_export_csv.py          # PostgreSQL -> CSV export
│   ├── 5_dump_database.py       # PostgreSQL custom-format backup
│   ├── load_django.py           # Django bootstrap for standalone scripts
│   └── parser_helpers.py        # Shared normalization and validation helpers
├── qa/
│   ├── static_audit.py          # Static source checks
│   └── runtime_validation.py    # Database / CSV / dump verification
├── results/
│   ├── products.csv             # Validated reference export
│   ├── database.dump            # PostgreSQL custom-format snapshot
│   └── README.txt
├── .env.example
├── .gitignore
├── DJANGO_SETUP_GUIDE.md
├── manage.py
└── requirements.txt
```

---

## Requirements

Recommended local environment:

- **Python 3.12**
- **PostgreSQL**
- **Chrome** for Selenium
- **Chromium installed by Playwright**
- Windows, macOS, or Linux for the Python application; the included setup guide uses Windows PowerShell commands

Pinned Python dependencies are defined in [`requirements.txt`](requirements.txt).

---

## Quick Start

### 1. Create and activate a virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Install Playwright Chromium

```powershell
python -m playwright install chromium
```

### 3. Create the PostgreSQL database

```sql
CREATE DATABASE brain_parser;
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and provide your local values:

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

`.env` is ignored by Git and must never be committed.

### 5. Initialize Django

```powershell
python manage.py check
python manage.py migrate
```

### 6. Run the parsers

```powershell
python modules/1_parse_requests_bs4.py
python modules/2_parse_selenium.py
python modules/3_parse_playwright.py
```

Each successful parser run prints the normalized product dictionary and the PostgreSQL record ID.

### 7. Generate data artifacts

```powershell
python modules/4_export_csv.py
python modules/5_dump_database.py
```

Generated files:

```text
results/products.csv
results/database.dump
```

### 8. Validate the complete pipeline

```powershell
python -m qa.runtime_validation
```

A healthy final state ends with:

```text
'status': 'passed'
```

For a more detailed setup walkthrough, see [`DJANGO_SETUP_GUIDE.md`](DJANGO_SETUP_GUIDE.md).

---

## Parser Workflows

### Requests + BeautifulSoup

`modules/1_parse_requests_bs4.py` parses the configured Brain.com.ua product page directly through HTTP. It uses semantic container and sibling relationships for characteristic extraction and does not depend on fixed element positions.

### Selenium

`modules/2_parse_selenium.py` performs a browser workflow in Chrome:

```text
Home page -> search query -> search submit -> first visible result -> product page -> extraction
```

The parser uses XPath selectors and explicit Selenium waits around browser actions and page state changes.

### Playwright

`modules/3_parse_playwright.py` performs the same user workflow independently in Chromium. It accounts for Brain.com's responsive search interface, including the quick-search overlay, and re-resolves the active search element when the header DOM changes.

Django ORM persistence is executed after the Playwright context closes so synchronous database access is kept outside Playwright's event-loop lifecycle.

---

## Data Model

The `Product` model stores normalized values from every parser:

| Field | Type | Notes |
|---|---|---|
| `parser_method` | `CharField` | `requests_bs4`, `selenium`, or `playwright` |
| `full_name` | `TextField` | Product title |
| `color` | `CharField` | Nullable |
| `memory` | `CharField` | Nullable |
| `manufacturer` | `CharField` | Nullable |
| `regular_price` | `CharField` | Preserves source formatting |
| `sale_price` | `CharField` | Nullable |
| `image_urls` | `JSONField` | List of product image URLs |
| `product_code` | `CharField` | Source product code |
| `reviews_count` | `IntegerField` | Nullable |
| `screen_diagonal` | `CharField` | Nullable |
| `display_resolution` | `CharField` | Nullable |
| `characteristics` | `JSONField` | Full label/value dictionary |

---

## Configuration

| Variable | Required | Purpose |
|---|---:|---|
| `DJANGO_SECRET_KEY` | Yes | Django secret key |
| `DJANGO_DEBUG` | No | `0` by default |
| `DB_NAME` | Yes | PostgreSQL database name |
| `DB_USER` | Yes | PostgreSQL user |
| `DB_PASSWORD` | Yes | PostgreSQL password |
| `DB_HOST` | Yes | PostgreSQL host |
| `DB_PORT` | Yes | PostgreSQL port |
| `BROWSER_HEADLESS` | No | `0` shows browser UI; `1` runs headless |
| `PG_DUMP_PATH` | No | Explicit `pg_dump` path for non-standard installations |
| `PG_RESTORE_PATH` | No | Explicit `pg_restore` path for non-standard installations |

The project also searches for PostgreSQL tools in `PATH` and standard Windows PostgreSQL installation directories.

---

## Data Export and Backup

### CSV

```powershell
python modules/4_export_csv.py
```

The exporter validates the database state before writing `results/products.csv`. JSON fields are serialized as JSON strings and the file is written as UTF-8 with BOM for reliable spreadsheet compatibility.

### PostgreSQL backup

```powershell
python modules/5_dump_database.py
```

This creates a custom-format PostgreSQL backup:

```text
results/database.dump
```

Inspect it with:

```powershell
pg_restore --list results/database.dump
```

Restore it into a separate empty database with:

```powershell
pg_restore --no-owner --dbname=brain_parser_restore results/database.dump
```

---

## Quality Checks

### Static audit

```powershell
python qa/static_audit.py
```

The audit checks first-party Python source for structural rules such as:

- XPath-only Selenium and Playwright task locators
- no broad exception handlers
- no absolute or positional XPath patterns
- no positional `find_all(...)[N]` extraction
- no `time.sleep()` browser synchronization
- no forced browser clicks
- `get_or_create(**data)` persistence shape

### Runtime validation

```powershell
python -m qa.runtime_validation
```

The runtime validator checks:

- expected parser records in PostgreSQL
- required fields and data types
- product identity for each parser workflow
- CSV/database record alignment
- valid JSON fields in CSV
- non-empty PostgreSQL backup
- `pg_restore --list` readability

---

## Reference Output

The repository includes a validated reference snapshot in `results/`:

| Parser | Product code | Images | Characteristics |
|---|---|---:|---:|
| Requests + BeautifulSoup | `U0961530` | 9 | 43 |
| Selenium | `U0854689` | 3 | 40 |
| Playwright | `U0854689` | 3 | 40 |

These values reflect the source pages at the time the reference run was created and may change when Brain.com.ua updates product content or pricing.

---

## Troubleshooting

### Playwright browser is missing

```powershell
python -m playwright install chromium
```

### PostgreSQL connection fails

Verify `.env`, confirm the PostgreSQL service is running, then run:

```powershell
python manage.py check
```

### `pg_dump` or `pg_restore` is not found

Add the PostgreSQL `bin` directory to `PATH`, or set:

```env
PG_DUMP_PATH=C:\Program Files\PostgreSQL\17\bin\pg_dump.exe
PG_RESTORE_PATH=C:\Program Files\PostgreSQL\17\bin\pg_restore.exe
```

### Browser selectors stop matching

Brain.com.ua is an external website and its DOM can change. Re-check affected elements in browser DevTools and update the existing semantic XPath/class selectors without replacing them with copied absolute DOM paths.

---

## Security Notes

- Never commit `.env`.
- Never commit local virtual environments.
- Keep database credentials outside source control.
- Use `.env.example` only as a configuration template.
- Treat `results/database.dump` as project data; review it before publishing if the database schema is extended with sensitive information later.

---

<div align="center">

**Three parsing engines. One normalized data model. One verified export pipeline.**

</div>
