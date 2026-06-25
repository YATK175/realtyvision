"""Decision calculation engine for the RealtyVision DSS module."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from services.dss_service import DssValidationError, get_matrix


SUPPORTED_METHODS = {"additive", "cautious", "multiplicative"}
SUPPORTED_OPERATORS = {"<", "<=", "=", ">=", ">"}


def _compare(value: float, operator: str, threshold: float) -> bool:
    """Check whether a raw value satisfies a threshold condition."""
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    if operator == "=":
        return math.isclose(value, threshold, rel_tol=1e-9, abs_tol=1e-9)
    if operator == ">=":
        return value >= threshold
    if operator == ">":
        return value > threshold

    raise DssValidationError(
        f"Непідтримуваний оператор порога: {operator}."
    )


def _build_raw_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert the matrix structure into alternative-centred rows."""
    criteria = matrix["criteria"]
    values = matrix["values"]
    rows: list[dict[str, Any]] = []

    for alternative in matrix["alternatives"]:
        alternative_key = str(alternative["id"])
        alternative_values = values.get(alternative_key, {})
        raw_values: dict[int, float | None] = {}

        for criterion in criteria:
            criterion_key = str(criterion["id"])
            saved = alternative_values.get(criterion_key)

            raw_values[int(criterion["id"])] = (
                float(saved["value"])
                if saved is not None
                else None
            )

        rows.append(
            {
                "alternative": alternative,
                "raw_values": raw_values,
            }
        )

    return rows


def _criterion_bounds(
    criterion: dict[str, Any],
    rows: list[dict[str, Any]],
) -> tuple[float, float]:
    """Return configured or observed bounds for normalization."""
    configured_min = criterion.get("scale_min")
    configured_max = criterion.get("scale_max")

    if configured_min is not None and configured_max is not None:
        return float(configured_min), float(configured_max)

    criterion_id = int(criterion["id"])
    observed = [
        float(row["raw_values"][criterion_id])
        for row in rows
        if row["raw_values"][criterion_id] is not None
    ]

    if not observed:
        return 0.0, 1.0

    return min(observed), max(observed)


def _normalize(
    value: float,
    criterion: dict[str, Any],
    lower: float,
    upper: float,
) -> float:
    """Normalize one raw criterion value to the interval [0, 1]."""
    if math.isclose(upper, lower, abs_tol=1e-12):
        return 1.0

    if criterion["criterion_type"] == "maximize":
        normalized = (value - lower) / (upper - lower)
    else:
        normalized = (upper - value) / (upper - lower)

    return min(1.0, max(0.0, normalized))


def _check_thresholds(
    row: dict[str, Any],
    criteria: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Return admissibility and human-readable rejection reasons."""
    reasons: list[str] = []

    for criterion in criteria:
        criterion_id = int(criterion["id"])
        value = row["raw_values"].get(criterion_id)

        if value is None:
            reasons.append(
                f"відсутня оцінка за критерієм «{criterion['name']}»"
            )
            continue

        operator = criterion.get("threshold_operator")
        threshold = criterion.get("threshold_value")

        if operator is None or threshold is None:
            continue

        if operator not in SUPPORTED_OPERATORS:
            reasons.append(
                f"критерій «{criterion['name']}» має некоректний оператор порога"
            )
            continue

        if not _compare(float(value), operator, float(threshold)):
            reasons.append(
                f"«{criterion['name']}»: {value:g} не відповідає умові "
                f"{operator} {float(threshold):g}"
            )

    return len(reasons) == 0, reasons


def _normalized_values(
    row: dict[str, Any],
    criteria: list[dict[str, Any]],
    bounds: dict[int, tuple[float, float]],
) -> dict[int, float]:
    """Normalize all available values for one alternative."""
    result: dict[int, float] = {}

    for criterion in criteria:
        criterion_id = int(criterion["id"])
        value = row["raw_values"].get(criterion_id)

        if value is None:
            continue

        lower, upper = bounds[criterion_id]
        result[criterion_id] = _normalize(
            float(value),
            criterion,
            lower,
            upper,
        )

    return result


def _validate_weights(criteria: list[dict[str, Any]]) -> None:
    """Require positive weights with a sum equal to one."""
    if not criteria:
        raise DssValidationError("Активні критерії відсутні.")

    weights = [float(item["weight"]) for item in criteria]

    if any(weight < 0 for weight in weights):
        raise DssValidationError("Вага критерію не може бути від'ємною.")

    total = sum(weights)

    if not math.isclose(total, 1.0, abs_tol=1e-6):
        raise DssValidationError(
            f"Сума ваг активних критеріїв повинна дорівнювати 1. "
            f"Поточна сума: {total:.6f}."
        )


def _score(
    normalized: dict[int, float],
    criteria: list[dict[str, Any]],
    method: str,
) -> tuple[float, list[dict[str, Any]]]:
    """Calculate one integral score and criterion contributions."""
    details: list[dict[str, Any]] = []

    for criterion in criteria:
        criterion_id = int(criterion["id"])
        norm = float(normalized.get(criterion_id, 0.0))
        weight = float(criterion["weight"])

        details.append(
            {
                "criterion_id": criterion_id,
                "criterion": criterion["name"],
                "normalized_value": round(norm, 6),
                "weight": round(weight, 6),
                "weighted_contribution": round(norm * weight, 6),
            }
        )

    if method == "additive":
        score = sum(
            item["normalized_value"] * item["weight"]
            for item in details
        )
    elif method == "cautious":
        score = min(
            (item["normalized_value"] for item in details),
            default=0.0,
        )
    elif method == "multiplicative":
        score = 1.0

        for item in details:
            value = item["normalized_value"]
            weight = item["weight"]

            if weight <= 0:
                continue

            if value <= 0:
                score = 0.0
                break

            score *= value ** weight
    else:
        raise DssValidationError(
            "Метод згортки повинен бути additive, cautious "
            "або multiplicative."
        )

    return round(float(score), 6), details


def _build_explanation(
    result: dict[str, Any],
    method: str,
) -> list[str]:
    """Create concise user-facing reasons for a calculated result."""
    if not result["admissible"]:
        return [
            "Альтернативу виключено через порогові обмеження.",
            *result["threshold_reasons"],
        ]

    details = result["details"]

    if method == "cautious":
        limiting = min(
            details,
            key=lambda item: item["normalized_value"],
        )
        return [
            "Альтернатива пройшла всі порогові обмеження.",
            (
                f"Обмежувальним критерієм є «{limiting['criterion']}» "
                f"з нормованою оцінкою "
                f"{limiting['normalized_value']:.3f}."
            ),
        ]

    strongest = sorted(
        details,
        key=lambda item: item["weighted_contribution"],
        reverse=True,
    )[:3]

    reasons = ["Альтернатива пройшла всі порогові обмеження."]

    for item in strongest:
        reasons.append(
            f"Критерій «{item['criterion']}» додав "
            f"{item['weighted_contribution']:.3f} до інтегральної оцінки."
        )

    return reasons


def calculate_ranking(
    method: str = "additive",
    *,
    weight_overrides: dict[int, float] | None = None,
) -> dict[str, Any]:
    """Calculate thresholds, normalization, ranking and explanation."""
    method = str(method).strip().lower()

    if method not in SUPPORTED_METHODS:
        raise DssValidationError(
            "Метод згортки повинен бути additive, cautious "
            "або multiplicative."
        )

    matrix = get_matrix()

    if not matrix["validation"]["matrix_is_complete"]:
        raise DssValidationError(
            "Матриця оцінювання містить пропущені значення."
        )

    criteria = deepcopy(matrix["criteria"])

    if weight_overrides:
        for criterion in criteria:
            criterion_id = int(criterion["id"])

            if criterion_id in weight_overrides:
                criterion["weight"] = float(weight_overrides[criterion_id])

    _validate_weights(criteria)

    rows = _build_raw_rows(matrix)

    if not rows:
        raise DssValidationError("Альтернативи відсутні.")

    bounds = {
        int(criterion["id"]): _criterion_bounds(criterion, rows)
        for criterion in criteria
    }

    ranking: list[dict[str, Any]] = []

    for row in rows:
        admissible, threshold_reasons = _check_thresholds(row, criteria)
        normalized = _normalized_values(row, criteria, bounds)
        integral_score, details = _score(
            normalized,
            criteria,
            method,
        )

        result = {
            "alternative_id": int(row["alternative"]["id"]),
            "alternative": row["alternative"]["name"],
            "admissible": admissible,
            "score": integral_score if admissible else 0.0,
            "raw_values": row["raw_values"],
            "normalized_values": normalized,
            "details": details,
            "threshold_reasons": threshold_reasons,
        }
        result["explanation"] = _build_explanation(result, method)
        ranking.append(result)

    admissible_items = sorted(
        (item for item in ranking if item["admissible"]),
        key=lambda item: (-item["score"], item["alternative"]),
    )
    excluded_items = sorted(
        (item for item in ranking if not item["admissible"]),
        key=lambda item: item["alternative"],
    )

    for place, item in enumerate(admissible_items, start=1):
        item["place"] = place
        item["status"] = "recommended" if place == 1 else "admissible"

    for item in excluded_items:
        item["place"] = None
        item["status"] = "excluded"

    final_ranking = admissible_items + excluded_items
    best = admissible_items[0] if admissible_items else None

    return {
        "method": method,
        "ranking": final_ranking,
        "best_alternative": best,
        "admissible_count": len(admissible_items),
        "excluded_count": len(excluded_items),
        "criteria": criteria,
        "normalization_bounds": {
            str(criterion_id): {
                "min": lower,
                "max": upper,
            }
            for criterion_id, (lower, upper) in bounds.items()
        },
    }


def compare_methods() -> dict[str, Any]:
    """Calculate and compare all supported aggregation methods."""
    results = {
        method: calculate_ranking(method)
        for method in ("additive", "cautious", "multiplicative")
    }

    winners = {
        method: (
            result["best_alternative"]["alternative"]
            if result["best_alternative"]
            else None
        )
        for method, result in results.items()
    }

    non_empty_winners = {
        winner
        for winner in winners.values()
        if winner is not None
    }

    return {
        "results": results,
        "winners": winners,
        "stable": len(non_empty_winners) <= 1,
        "explanation": (
            "Переможець не змінюється при використанні різних методів згортки."
            if len(non_empty_winners) <= 1
            else "Переможець залежить від вибраного методу згортки."
        ),
    }


def sensitivity_analysis(
    criterion_id: int,
    new_weight: float,
    method: str = "additive",
) -> dict[str, Any]:
    """Recalculate a ranking after changing one criterion weight."""
    if not 0 <= new_weight <= 1:
        raise DssValidationError(
            "Нова вага повинна бути в межах від 0 до 1."
        )

    matrix = get_matrix()
    criteria = matrix["criteria"]
    selected = next(
        (
            criterion
            for criterion in criteria
            if int(criterion["id"]) == int(criterion_id)
        ),
        None,
    )

    if selected is None:
        raise DssValidationError(
            f"Критерій з id={criterion_id} не знайдено."
        )

    baseline = calculate_ranking(method)
    other_criteria = [
        criterion
        for criterion in criteria
        if int(criterion["id"]) != int(criterion_id)
    ]
    remaining_weight = 1.0 - new_weight
    other_total = sum(float(item["weight"]) for item in other_criteria)
    overrides: dict[int, float] = {
        int(criterion_id): float(new_weight)
    }

    if other_criteria:
        if math.isclose(other_total, 0.0, abs_tol=1e-12):
            equal_weight = remaining_weight / len(other_criteria)

            for criterion in other_criteria:
                overrides[int(criterion["id"])] = equal_weight
        else:
            for criterion in other_criteria:
                overrides[int(criterion["id"])] = (
                    float(criterion["weight"])
                    / other_total
                    * remaining_weight
                )
    elif not math.isclose(new_weight, 1.0, abs_tol=1e-9):
        raise DssValidationError(
            "За наявності одного критерію його вага повинна дорівнювати 1."
        )

    changed = calculate_ranking(
        method,
        weight_overrides=overrides,
    )

    baseline_winner = (
        baseline["best_alternative"]["alternative"]
        if baseline["best_alternative"]
        else None
    )
    changed_winner = (
        changed["best_alternative"]["alternative"]
        if changed["best_alternative"]
        else None
    )

    return {
        "method": method,
        "criterion_id": int(criterion_id),
        "criterion": selected["name"],
        "old_weight": float(selected["weight"]),
        "new_weight": float(new_weight),
        "normalized_weights": {
            str(key): round(value, 6)
            for key, value in overrides.items()
        },
        "baseline": baseline,
        "changed": changed,
        "winner_changed": baseline_winner != changed_winner,
        "explanation": (
            f"Переможець змінився з «{baseline_winner}» "
            f"на «{changed_winner}»."
            if baseline_winner != changed_winner
            else "Переможець не змінився — рішення стабільне "
            "до заданої зміни ваги."
        ),
    }
