"""Database schema for persistent IF–THEN rules in RealtyVision DSS."""

from __future__ import annotations

from models.dss_database import get_connection, init_dss_database


def init_dss_rule_database() -> None:
    """Create rule tables and add demonstration rules when possible."""
    init_dss_database()

    schema = """
    CREATE TABLE IF NOT EXISTS dss_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        criterion_id INTEGER NOT NULL,
        operator TEXT NOT NULL
            CHECK (operator IN ('<', '<=', '=', '>=', '>')),
        condition_value REAL NOT NULL,
        action_type TEXT NOT NULL
            CHECK (action_type IN ('reject', 'penalty', 'bonus')),
        action_value REAL NOT NULL DEFAULT 0
            CHECK (action_value >= 0 AND action_value <= 1),
        message TEXT NOT NULL DEFAULT '',
        priority INTEGER NOT NULL DEFAULT 100,
        is_active INTEGER NOT NULL DEFAULT 1
            CHECK (is_active IN (0, 1)),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (criterion_id)
            REFERENCES dss_criteria(id)
            ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_dss_rules_active
        ON dss_rules(is_active, priority);

    CREATE INDEX IF NOT EXISTS idx_dss_rules_criterion
        ON dss_rules(criterion_id);
    """

    with get_connection() as connection:
        connection.executescript(schema)

        criteria = {
            row["name"]: int(row["id"])
            for row in connection.execute(
                """
                SELECT id, name
                FROM dss_criteria
                WHERE is_active = 1
                """
            ).fetchall()
        }

        defaults = [
            {
                "name": "Критично мала площа",
                "criterion": "Площа",
                "operator": "<",
                "condition_value": 50,
                "action_type": "reject",
                "action_value": 0,
                "message": (
                    "Альтернативу відхилено: площа менша за "
                    "мінімально допустимі 50 м²."
                ),
                "priority": 10,
            },
            {
                "name": "Низький стан об'єкта",
                "criterion": "Стан",
                "operator": "<",
                "condition_value": 7,
                "action_type": "penalty",
                "action_value": 0.10,
                "message": (
                    "До оцінки застосовано штраф 10% через "
                    "недостатній стан об'єкта."
                ),
                "priority": 20,
            },
            {
                "name": "Вигідна локація",
                "criterion": "Локація",
                "operator": ">=",
                "condition_value": 8,
                "action_type": "bonus",
                "action_value": 0.05,
                "message": (
                    "До оцінки додано бонус 5% за вигідну локацію."
                ),
                "priority": 30,
            },
        ]

        for item in defaults:
            criterion_id = criteria.get(item["criterion"])

            if criterion_id is None:
                continue

            connection.execute(
                """
                INSERT OR IGNORE INTO dss_rules (
                    name,
                    criterion_id,
                    operator,
                    condition_value,
                    action_type,
                    action_value,
                    message,
                    priority,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    item["name"],
                    criterion_id,
                    item["operator"],
                    item["condition_value"],
                    item["action_type"],
                    item["action_value"],
                    item["message"],
                    item["priority"],
                ),
            )


if __name__ == "__main__":
    init_dss_rule_database()
    print("DSS IF–THEN rule tables initialized.")
