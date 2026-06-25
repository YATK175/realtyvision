"""Repository for expert assessments in RealtyVision DSS."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from models.dss_database import get_connection
from models.dss_expert_database import init_dss_expert_database


def get_reference_data() -> dict[str, list[dict[str, Any]]]:
    """Return alternatives and active criteria used during import validation."""
    init_dss_expert_database()

    with get_connection() as connection:
        alternatives = connection.execute(
            """
            SELECT id, name
            FROM dss_alternatives
            ORDER BY id
            """
        ).fetchall()

        criteria = connection.execute(
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
                threshold_value
            FROM dss_criteria
            WHERE is_active = 1
            ORDER BY id
            """
        ).fetchall()

    return {
        "alternatives": [dict(row) for row in alternatives],
        "criteria": [dict(row) for row in criteria],
    }


def import_expert_rows(
    rows: Iterable[dict[str, Any]],
    *,
    source_url: str,
    source: str = "google_sheets",
) -> dict[str, Any]:
    """Import validated rows in one SQLite transaction."""
    init_dss_expert_database()
    prepared_rows = list(rows)
    expert_ids: set[int] = set()
    imported_scores = 0

    with get_connection() as connection:
        for row in prepared_rows:
            expert_name = str(row["expert_name"]).strip()

            connection.execute(
                """
                INSERT INTO dss_experts (name)
                VALUES (?)
                ON CONFLICT(name) DO UPDATE SET
                    updated_at = CURRENT_TIMESTAMP
                """,
                (expert_name,),
            )

            expert = connection.execute(
                """
                SELECT id
                FROM dss_experts
                WHERE name = ? COLLATE NOCASE
                """,
                (expert_name,),
            ).fetchone()

            if expert is None:
                raise RuntimeError(
                    f"Не вдалося створити експерта «{expert_name}»."
                )

            expert_id = int(expert["id"])
            expert_ids.add(expert_id)

            for criterion_id, value in row["scores"].items():
                connection.execute(
                    """
                    INSERT INTO dss_expert_scores (
                        expert_id,
                        alternative_id,
                        criterion_id,
                        value,
                        source
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (
                        expert_id,
                        alternative_id,
                        criterion_id
                    )
                    DO UPDATE SET
                        value = excluded.value,
                        source = excluded.source,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        expert_id,
                        int(row["alternative_id"]),
                        int(criterion_id),
                        float(value),
                        source,
                    ),
                )
                imported_scores += 1

        cursor = connection.execute(
            """
            INSERT INTO dss_import_batches (
                source_type,
                source_url,
                imported_rows,
                imported_scores,
                status,
                message
            )
            VALUES (?, ?, ?, ?, 'completed', ?)
            """,
            (
                source,
                source_url,
                len(prepared_rows),
                imported_scores,
                "Імпорт експертних оцінок завершено.",
            ),
        )
        batch_id = int(cursor.lastrowid)

    return {
        "batch_id": batch_id,
        "imported_rows": len(prepared_rows),
        "imported_scores": imported_scores,
        "experts_count": len(expert_ids),
    }


def list_expert_scores() -> list[dict[str, Any]]:
    """Return all expert values with joined names."""
    init_dss_expert_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                es.id,
                es.expert_id,
                e.name AS expert_name,
                es.alternative_id,
                a.name AS alternative_name,
                es.criterion_id,
                c.name AS criterion_name,
                es.value,
                es.source,
                es.created_at,
                es.updated_at
            FROM dss_expert_scores AS es
            JOIN dss_experts AS e
                ON e.id = es.expert_id
            JOIN dss_alternatives AS a
                ON a.id = es.alternative_id
            JOIN dss_criteria AS c
                ON c.id = es.criterion_id
            ORDER BY
                e.name COLLATE NOCASE,
                a.id,
                c.id
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_grouped_expert_values() -> list[dict[str, Any]]:
    """Return score groups for each alternative and criterion."""
    init_dss_expert_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                es.alternative_id,
                a.name AS alternative_name,
                es.criterion_id,
                c.name AS criterion_name,
                es.value
            FROM dss_expert_scores AS es
            JOIN dss_alternatives AS a
                ON a.id = es.alternative_id
            JOIN dss_criteria AS c
                ON c.id = es.criterion_id
            WHERE c.is_active = 1
            ORDER BY es.alternative_id, es.criterion_id, es.expert_id
            """
        ).fetchall()

    groups: dict[tuple[int, int], dict[str, Any]] = {}

    for row in rows:
        key = (
            int(row["alternative_id"]),
            int(row["criterion_id"]),
        )
        group = groups.setdefault(
            key,
            {
                "alternative_id": key[0],
                "alternative_name": row["alternative_name"],
                "criterion_id": key[1],
                "criterion_name": row["criterion_name"],
                "values": [],
            },
        )
        group["values"].append(float(row["value"]))

    return list(groups.values())


def list_import_batches(limit: int = 10) -> list[dict[str, Any]]:
    """Return the latest import history."""
    init_dss_expert_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                source_type,
                source_url,
                imported_rows,
                imported_scores,
                status,
                message,
                created_at
            FROM dss_import_batches
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [dict(row) for row in rows]
