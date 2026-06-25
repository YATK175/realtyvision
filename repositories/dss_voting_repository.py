"""Repository for criterion voting in RealtyVision DSS."""

from __future__ import annotations

from typing import Any

from models.dss_database import get_connection
from models.dss_voting_database import init_dss_voting_database


def get_active_criteria() -> list[dict[str, Any]]:
    init_dss_voting_database()

    with get_connection() as connection:
        rows = connection.execute(
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
                is_active
            FROM dss_criteria
            WHERE is_active = 1
            ORDER BY id
            """
        ).fetchall()

    return [dict(row) for row in rows]


def replace_ballots(
    experts: list[dict[str, Any]],
    *,
    source_url: str,
) -> dict[str, int]:
    """Replace all imported ballots in one transaction."""
    init_dss_voting_database()

    with get_connection() as connection:
        connection.execute("DELETE FROM dss_voting_ballots")

        imported_ballots = 0

        for expert in experts:
            expert_name = str(expert["expert_name"]).strip()

            for item in expert["ranking"]:
                connection.execute(
                    """
                    INSERT INTO dss_voting_ballots (
                        expert_name,
                        criterion_id,
                        rank_position,
                        approved,
                        source
                    )
                    VALUES (?, ?, ?, ?, 'google_sheets')
                    """,
                    (
                        expert_name,
                        int(item["criterion_id"]),
                        int(item["rank_position"]),
                        int(item["approved"]),
                    ),
                )
                imported_ballots += 1

        connection.execute(
            """
            INSERT INTO dss_voting_imports (
                source_url,
                imported_experts,
                imported_ballots,
                status,
                message
            )
            VALUES (?, ?, ?, 'completed', ?)
            """,
            (
                source_url,
                len(experts),
                imported_ballots,
                "Імпорт голосування завершено.",
            ),
        )

    return {
        "imported_experts": len(experts),
        "imported_ballots": imported_ballots,
    }


def list_ballots() -> list[dict[str, Any]]:
    init_dss_voting_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                b.id,
                b.expert_name,
                b.criterion_id,
                c.name AS criterion_name,
                b.rank_position,
                b.approved,
                b.source,
                b.created_at,
                b.updated_at
            FROM dss_voting_ballots AS b
            JOIN dss_criteria AS c
                ON c.id = b.criterion_id
            ORDER BY
                b.expert_name COLLATE NOCASE,
                b.rank_position
            """
        ).fetchall()

    return [dict(row) for row in rows]


def save_result_and_apply_weights(
    method: str,
    results: list[dict[str, Any]],
) -> None:
    """Persist a voting result and apply its normalized weights."""
    init_dss_voting_database()

    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM dss_voting_results
            WHERE method = ?
            """,
            (method,),
        )

        for item in results:
            connection.execute(
                """
                INSERT INTO dss_voting_results (
                    method,
                    criterion_id,
                    raw_score,
                    normalized_weight
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    method,
                    int(item["criterion_id"]),
                    float(item["raw_score"]),
                    float(item["weight"]),
                ),
            )

            connection.execute(
                """
                UPDATE dss_criteria
                SET
                    weight = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    float(item["weight"]),
                    int(item["criterion_id"]),
                ),
            )


def list_results(method: str | None = None) -> list[dict[str, Any]]:
    init_dss_voting_database()

    query = """
        SELECT
            r.id,
            r.method,
            r.criterion_id,
            c.name AS criterion_name,
            r.raw_score,
            r.normalized_weight,
            r.created_at
        FROM dss_voting_results AS r
        JOIN dss_criteria AS c
            ON c.id = r.criterion_id
    """
    parameters: tuple[Any, ...] = ()

    if method:
        query += " WHERE r.method = ?"
        parameters = (method,)

    query += " ORDER BY r.method, r.normalized_weight DESC, c.id"

    with get_connection() as connection:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

    return [dict(row) for row in rows]


def list_imports(limit: int = 10) -> list[dict[str, Any]]:
    init_dss_voting_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                source_url,
                imported_experts,
                imported_ballots,
                status,
                message,
                created_at
            FROM dss_voting_imports
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [dict(row) for row in rows]
