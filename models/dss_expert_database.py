"""Database schema for expert assessments in RealtyVision DSS."""

from __future__ import annotations

from models.dss_database import get_connection, init_dss_database


def init_dss_expert_database() -> None:
    """Create expert-assessment tables without modifying existing DSS data."""
    init_dss_database()

    schema = """
    CREATE TABLE IF NOT EXISTS dss_experts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS dss_expert_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expert_id INTEGER NOT NULL,
        alternative_id INTEGER NOT NULL,
        criterion_id INTEGER NOT NULL,
        value REAL NOT NULL,
        source TEXT NOT NULL DEFAULT 'google_sheets'
            CHECK (source IN ('google_sheets', 'file', 'manual')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (expert_id, alternative_id, criterion_id),
        FOREIGN KEY (expert_id)
            REFERENCES dss_experts(id)
            ON DELETE CASCADE,
        FOREIGN KEY (alternative_id)
            REFERENCES dss_alternatives(id)
            ON DELETE CASCADE,
        FOREIGN KEY (criterion_id)
            REFERENCES dss_criteria(id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS dss_import_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,
        source_url TEXT NOT NULL DEFAULT '',
        imported_rows INTEGER NOT NULL DEFAULT 0,
        imported_scores INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'completed',
        message TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_dss_expert_scores_expert
        ON dss_expert_scores(expert_id);

    CREATE INDEX IF NOT EXISTS idx_dss_expert_scores_alternative
        ON dss_expert_scores(alternative_id);

    CREATE INDEX IF NOT EXISTS idx_dss_expert_scores_criterion
        ON dss_expert_scores(criterion_id);
    """

    with get_connection() as connection:
        connection.executescript(schema)


if __name__ == "__main__":
    init_dss_expert_database()
    print("DSS expert tables initialized.")
