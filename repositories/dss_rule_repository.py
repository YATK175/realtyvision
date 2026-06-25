"""Repository for persistent IF–THEN rules in RealtyVision DSS."""

from __future__ import annotations

from typing import Any

from models.dss_database import get_connection
from models.dss_rule_database import init_dss_rule_database


def list_rules(
    *,
    include_inactive: bool = True,
) -> list[dict[str, Any]]:
    init_dss_rule_database()

    query = """
        SELECT
            r.id,
            r.name,
            r.criterion_id,
            c.name AS criterion_name,
            c.unit AS criterion_unit,
            r.operator,
            r.condition_value,
            r.action_type,
            r.action_value,
            r.message,
            r.priority,
            r.is_active,
            r.created_at,
            r.updated_at
        FROM dss_rules AS r
        JOIN dss_criteria AS c
            ON c.id = r.criterion_id
    """
    parameters: tuple[Any, ...] = ()

    if not include_inactive:
        query += " WHERE r.is_active = ?"
        parameters = (1,)

    query += " ORDER BY r.priority, r.id"

    with get_connection() as connection:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

    result: list[dict[str, Any]] = []

    for row in rows:
        item = dict(row)
        item["is_active"] = bool(item["is_active"])
        result.append(item)

    return result


def get_rule(rule_id: int) -> dict[str, Any] | None:
    init_dss_rule_database()

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                r.id,
                r.name,
                r.criterion_id,
                c.name AS criterion_name,
                c.unit AS criterion_unit,
                r.operator,
                r.condition_value,
                r.action_type,
                r.action_value,
                r.message,
                r.priority,
                r.is_active,
                r.created_at,
                r.updated_at
            FROM dss_rules AS r
            JOIN dss_criteria AS c
                ON c.id = r.criterion_id
            WHERE r.id = ?
            """,
            (int(rule_id),),
        ).fetchone()

    if row is None:
        return None

    item = dict(row)
    item["is_active"] = bool(item["is_active"])
    return item


def create_rule(data: dict[str, Any]) -> dict[str, Any]:
    init_dss_rule_database()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO dss_rules (
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"],
                data["criterion_id"],
                data["operator"],
                data["condition_value"],
                data["action_type"],
                data["action_value"],
                data["message"],
                data["priority"],
                int(data["is_active"]),
            ),
        )
        rule_id = int(cursor.lastrowid)

    rule = get_rule(rule_id)

    if rule is None:
        raise RuntimeError("Не вдалося отримати створене правило.")

    return rule


def update_rule(
    rule_id: int,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    init_dss_rule_database()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE dss_rules
            SET
                name = ?,
                criterion_id = ?,
                operator = ?,
                condition_value = ?,
                action_type = ?,
                action_value = ?,
                message = ?,
                priority = ?,
                is_active = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                data["name"],
                data["criterion_id"],
                data["operator"],
                data["condition_value"],
                data["action_type"],
                data["action_value"],
                data["message"],
                data["priority"],
                int(data["is_active"]),
                int(rule_id),
            ),
        )

        if cursor.rowcount == 0:
            return None

    return get_rule(rule_id)


def delete_rule(rule_id: int) -> bool:
    init_dss_rule_database()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM dss_rules
            WHERE id = ?
            """,
            (int(rule_id),),
        )

    return cursor.rowcount > 0
