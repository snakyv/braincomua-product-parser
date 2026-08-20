"""Create a PostgreSQL custom-format dump in the ``results`` directory."""

import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
OUTPUT_PATH = PROJECT_ROOT / "results" / "database.dump"


def postgres_version_key(path: Path) -> tuple[int, ...]:
    """Return a sortable numeric version extracted from a PostgreSQL tool path."""
    version = path.parts[-3]
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (0,)


def find_pg_dump() -> str | None:
    """Locate ``pg_dump`` from configuration, PATH, or standard Windows installs."""
    configured = os.getenv("PG_DUMP_PATH")
    if configured and Path(configured).is_file():
        return configured

    pg_dump = shutil.which("pg_dump")
    if pg_dump:
        return pg_dump

    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        postgresql_root = Path(program_files) / "PostgreSQL"
        if postgresql_root.is_dir():
            candidates = sorted(
                postgresql_root.glob("*/bin/pg_dump.exe"),
                key=postgres_version_key,
                reverse=True,
            )
            if candidates:
                return str(candidates[0])

    return None


def build_pg_dump_command(pg_dump: str) -> list[str]:
    """Build the ``pg_dump`` command from environment-backed database settings."""
    database_name = os.getenv("DB_NAME", "brain_parser")
    database_user = os.getenv("DB_USER", "postgres")
    database_host = os.getenv("DB_HOST", "127.0.0.1")
    database_port = os.getenv("DB_PORT", "5432")

    return [
        pg_dump,
        "--format=custom",
        "--no-owner",
        "--no-acl",
        f"--file={OUTPUT_PATH}",
        f"--host={database_host}",
        f"--port={database_port}",
        f"--username={database_user}",
        database_name,
    ]


def build_subprocess_environment() -> dict[str, str]:
    """Return the process environment, including ``PGPASSWORD`` when configured."""
    environment = os.environ.copy()
    database_password = os.getenv("DB_PASSWORD", "")
    if database_password:
        environment["PGPASSWORD"] = database_password
    return environment


def main() -> None:
    """Create and verify the PostgreSQL backup artifact."""
    pg_dump = find_pg_dump()
    if pg_dump is None:
        raise FileNotFoundError(
            "pg_dump was not found. Add PostgreSQL bin to PATH or set PG_DUMP_PATH."
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    subprocess.run(
        build_pg_dump_command(pg_dump),
        check=True,
        env=build_subprocess_environment(),
    )

    if not OUTPUT_PATH.is_file() or OUTPUT_PATH.stat().st_size == 0:
        raise RuntimeError(
            "pg_dump completed without creating a valid non-empty dump file."
        )

    print(f"PostgreSQL dump created: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
