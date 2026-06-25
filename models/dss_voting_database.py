"""Database schema for criterion voting in RealtyVision DSS."""

from __future__ import annotations

from models.dss_database import get_connection, init_dss_database


def init_dss_voting_database() -> None:
    """Create voting tables without changing existing DSS data."""
    init_dss_database()

    schema = """
    CREATE TABLE IF NOT EXISTS dss_voting_ballots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expert_name TEXT NOT NULL,
        criterion_id INTEGER NOT NULL,
        rank_position INTEGER NOT NULL CHECK (rank_position > 0),
        approved INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0, 1)),
        source TEXT NOT NULL DEFAULT 'google_sheets'
            CHECK (source IN ('google_sheets', 'file', 'manual')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (expert_name, criterion_id),
        FOREIGN KEY (criterion_id)
            REFERENCES dss_criteria(id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS dss_voting_imports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_url TEXT NOT NULL DEFAULT '',
        imported_experts INTEGER NOT NULL DEFAULT 0,
        imported_ballots INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'completed',
        message TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS dss_voting_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        method TEXT NOT NULL,
        criterion_id INTEGER NOT NULL,
        raw_score REAL NOT NULL,
        normalized_weight REAL NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (criterion_id)
            REFERENCES dss_criteria(id)
            ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_dss_voting_ballots_expert
        ON dss_voting_ballots(expert_name);

    CREATE INDEX IF NOT EXISTS idx_dss_voting_ballots_criterion
        ON dss_voting_ballots(criterion_id);

    CREATE INDEX IF NOT EXISTS idx_dss_voting_results_method
        ON dss_voting_results(method);
    """

    with get_connection() as connection:
        connection.executescript(schema)


if __name__ == "__main__":
    init_dss_voting_database()
    print("DSS voting tables initialized.")
