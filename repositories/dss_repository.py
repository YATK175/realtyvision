"""Repository layer for the RealtyVision DSS module."""

from __future__ import annotations

import sqlite3
from typing import Any

from models.dss_database import get_connection, init_dss_database


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a SQLite row to a regular dictionary."""
    return dict(row) if row is not None else None


# =====================================================
# ALTERNATIVES
# =====================================================

def get_all_alternatives() -> list[dict[str, Any]]:
    """Return all alternatives ordered by creation time."""
    init_dss_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                name,
                description,
                address,
                created_at,
                updated_at
            FROM dss_alternatives
            ORDER BY id
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_alternative_by_id(
    alternative_id: int,
) -> dict[str, Any] | None:
    """Return one alternative by its identifier."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                name,
                description,
                address,
                created_at,
                updated_at
            FROM dss_alternatives
            WHERE id = ?
            """,
            (alternative_id,),
        ).fetchone()

    return _row_to_dict(row)


def create_alternative(
    name: str,
    description: str = "",
    address: str = "",
) -> dict[str, Any]:
    """Create and return an alternative."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO dss_alternatives (
                name,
                description,
                address
            )
            VALUES (?, ?, ?)
            """,
            (
                name.strip(),
                description.strip(),
                address.strip(),
            ),
        )
        alternative_id = int(cursor.lastrowid)

    alternative = get_alternative_by_id(alternative_id)

    if alternative is None:
        raise RuntimeError(
            "Не вдалося отримати створену альтернативу."
        )

    return alternative


def update_alternative(
    alternative_id: int,
    name: str,
    description: str = "",
    address: str = "",
) -> dict[str, Any] | None:
    """Update an alternative and return the updated document."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE dss_alternatives
            SET
                name = ?,
                description = ?,
                address = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                name.strip(),
                description.strip(),
                address.strip(),
                alternative_id,
            ),
        )

        if cursor.rowcount == 0:
            return None

    return get_alternative_by_id(alternative_id)


def delete_alternative(alternative_id: int) -> bool:
    """Delete an alternative and its related scores."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM dss_alternatives
            WHERE id = ?
            """,
            (alternative_id,),
        )

    return cursor.rowcount > 0


# =====================================================
# CRITERIA
# =====================================================

def get_all_criteria(
    include_inactive: bool = True,
) -> list[dict[str, Any]]:
    """Return all DSS criteria."""
    query = """
        SELECT
            id,
            name,
            criterion_type,
            weight,
            unit,
            scale_min,
            scale_max,
            threshold_operator,
            threshold_value,
            is_active,
            created_at,
            updated_at
        FROM dss_criteria
    """
    parameters: tuple[Any, ...] = ()

    if not include_inactive:
        query += " WHERE is_active = ?"
        parameters = (1,)

    query += " ORDER BY id"

    with get_connection() as connection:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

    result: list[dict[str, Any]] = []

    for row in rows:
        criterion = dict(row)
        criterion["is_active"] = bool(criterion["is_active"])
        result.append(criterion)

    return result


def get_criterion_by_id(
    criterion_id: int,
) -> dict[str, Any] | None:
    """Return one criterion by identifier."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                name,
                criterion_type,
                weight,
                unit,
                scale_min,
                scale_max,
                threshold_operator,
                threshold_value,
                is_active,
                created_at,
                updated_at
            FROM dss_criteria
            WHERE id = ?
            """,
            (criterion_id,),
        ).fetchone()

    criterion = _row_to_dict(row)

    if criterion is not None:
        criterion["is_active"] = bool(criterion["is_active"])

    return criterion


def create_criterion(
    name: str,
    criterion_type: str,
    weight: float,
    unit: str = "",
    scale_min: float | None = None,
    scale_max: float | None = None,
    threshold_operator: str | None = None,
    threshold_value: float | None = None,
    is_active: bool = True,
) -> dict[str, Any]:
    """Create and return a criterion."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO dss_criteria (
                name,
                criterion_type,
                weight,
                unit,
                scale_min,
                scale_max,
                threshold_operator,
                threshold_value,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name.strip(),
                criterion_type,
                weight,
                unit.strip(),
                scale_min,
                scale_max,
                threshold_operator,
                threshold_value,
                int(is_active),
            ),
        )
        criterion_id = int(cursor.lastrowid)

    criterion = get_criterion_by_id(criterion_id)

    if criterion is None:
        raise RuntimeError(
            "Не вдалося отримати створений критерій."
        )

    return criterion


def update_criterion(
    criterion_id: int,
    name: str,
    criterion_type: str,
    weight: float,
    unit: str = "",
    scale_min: float | None = None,
    scale_max: float | None = None,
    threshold_operator: str | None = None,
    threshold_value: float | None = None,
    is_active: bool = True,
) -> dict[str, Any] | None:
    """Update and return a criterion."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE dss_criteria
            SET
                name = ?,
                criterion_type = ?,
                weight = ?,
                unit = ?,
                scale_min = ?,
                scale_max = ?,
                threshold_operator = ?,
                threshold_value = ?,
                is_active = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                name.strip(),
                criterion_type,
                weight,
                unit.strip(),
                scale_min,
                scale_max,
                threshold_operator,
                threshold_value,
                int(is_active),
                criterion_id,
            ),
        )

        if cursor.rowcount == 0:
            return None

    return get_criterion_by_id(criterion_id)


def delete_criterion(criterion_id: int) -> bool:
    """Delete a criterion and all its related scores."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM dss_criteria
            WHERE id = ?
            """,
            (criterion_id,),
        )

    return cursor.rowcount > 0


# =====================================================
# EVALUATION MATRIX
# =====================================================

def save_score(
    alternative_id: int,
    criterion_id: int,
    value: float,
    source: str = "manual",
) -> dict[str, Any]:
    """Create or update one matrix value."""
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO dss_scores (
                alternative_id,
                criterion_id,
                value,
                source
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT (
                alternative_id,
                criterion_id
            )
            DO UPDATE SET
                value = excluded.value,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                alternative_id,
                criterion_id,
                value,
                source,
            ),
        )

        row = connection.execute(
            """
            SELECT
                id,
                alternative_id,
                criterion_id,
                value,
                source,
                created_at,
                updated_at
            FROM dss_scores
            WHERE alternative_id = ?
              AND criterion_id = ?
            """,
            (
                alternative_id,
                criterion_id,
            ),
        ).fetchone()

    result = _row_to_dict(row)

    if result is None:
        raise RuntimeError(
            "Не вдалося зберегти оцінку."
        )

    return result


def delete_score(
    alternative_id: int,
    criterion_id: int,
) -> bool:
    """Delete one value from the evaluation matrix."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM dss_scores
            WHERE alternative_id = ?
              AND criterion_id = ?
            """,
            (
                alternative_id,
                criterion_id,
            ),
        )

    return cursor.rowcount > 0


def get_evaluation_matrix() -> dict[str, Any]:
    """Return alternatives, criteria and all matrix values."""
    alternatives = get_all_alternatives()
    criteria = get_all_criteria(include_inactive=False)

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                alternative_id,
                criterion_id,
                value,
                source
            FROM dss_scores
            ORDER BY alternative_id, criterion_id
            """
        ).fetchall()

    values: dict[str, dict[str, Any]] = {}

    for row in rows:
        alternative_key = str(row["alternative_id"])
        criterion_key = str(row["criterion_id"])

        values.setdefault(
            alternative_key,
            {},
        )[criterion_key] = {
            "value": row["value"],
            "source": row["source"],
        }

    return {
        "alternatives": alternatives,
        "criteria": criteria,
        "values": values,
    }


def get_weight_sum() -> float:
    """Return the sum of active criterion weights."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COALESCE(SUM(weight), 0) AS total
            FROM dss_criteria
            WHERE is_active = 1
            """
        ).fetchone()

    return float(row["total"])
