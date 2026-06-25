"""Database schema for the RealtyVision decision-support module."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "realtyvision.db"


def get_database_path() -> Path:
    """Return the configured SQLite database path."""
    configured_path = os.getenv("DATABASE_PATH")

    if not configured_path:
        return DEFAULT_DB_PATH

    path = Path(configured_path)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with foreign keys and Row support enabled."""
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_dss_database() -> None:
    """Create the core DSS tables without deleting existing RealtyVision data."""
    schema = """
    CREATE TABLE IF NOT EXISTS dss_alternatives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        description TEXT NOT NULL DEFAULT '',
        address TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS dss_criteria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        criterion_type TEXT NOT NULL
            CHECK (criterion_type IN ('maximize', 'minimize')),
        weight REAL NOT NULL DEFAULT 0
            CHECK (weight >= 0 AND weight <= 1),
        unit TEXT NOT NULL DEFAULT '',
        scale_min REAL,
        scale_max REAL,
        threshold_operator TEXT
            CHECK (
                threshold_operator IS NULL
                OR threshold_operator IN ('<', '<=', '=', '>=', '>')
            ),
        threshold_value REAL,
        is_active INTEGER NOT NULL DEFAULT 1
            CHECK (is_active IN (0, 1)),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK (
            scale_min IS NULL
            OR scale_max IS NULL
            OR scale_max > scale_min
        )
    );

    CREATE TABLE IF NOT EXISTS dss_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alternative_id INTEGER NOT NULL,
        criterion_id INTEGER NOT NULL,
        value REAL NOT NULL,
        source TEXT NOT NULL DEFAULT 'manual'
            CHECK (
                source IN (
                    'manual',
                    'import',
                    'expert_consensus'
                )
            ),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (alternative_id, criterion_id),
        FOREIGN KEY (alternative_id)
            REFERENCES dss_alternatives(id)
            ON DELETE CASCADE,
        FOREIGN KEY (criterion_id)
            REFERENCES dss_criteria(id)
            ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_dss_scores_alternative
        ON dss_scores(alternative_id);

    CREATE INDEX IF NOT EXISTS idx_dss_scores_criterion
        ON dss_scores(criterion_id);

    CREATE INDEX IF NOT EXISTS idx_dss_criteria_active
        ON dss_criteria(is_active);
    """

    with get_connection() as connection:
        connection.executescript(schema)


def get_schema_summary() -> dict[str, int]:
    """Return row counts for the core DSS tables."""
    tables = (
        "dss_alternatives",
        "dss_criteria",
        "dss_scores",
    )

    with get_connection() as connection:
        result: dict[str, int] = {}

        for table_name in tables:
            row = connection.execute(
                f"SELECT COUNT(*) AS total FROM {table_name}"
            ).fetchone()
            result[table_name] = int(row["total"])

        return result


if __name__ == "__main__":
    init_dss_database()

    print(f"DSS database initialized: {get_database_path()}")

    for table_name, row_count in get_schema_summary().items():
        print(f"{table_name}: {row_count}")
