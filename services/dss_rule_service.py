"""IF–THEN rule management and evaluation for RealtyVision DSS."""

from __future__ import annotations

import math
import sqlite3
from typing import Any

from repositories import dss_repository
from repositories import dss_rule_repository as repository
from services.dss_service import (
    DssConflictError,
    DssNotFoundError,
    DssValidationError,
    get_matrix,
)


ALLOWED_OPERATORS = {"<", "<=", "=", ">=", ">"}
ALLOWED_ACTIONS = {"reject", "penalty", "bonus"}

ACTION_LABELS = {
    "reject": "Відхилити альтернативу",
    "penalty": "Зменшити оцінку",
    "bonus": "Збільшити оцінку",
}


def _text(
    value: Any,
    field: str,
    *,
    required: bool = False,
    max_length: int = 500,
) -> str:
    if value is None:
        result = ""
    elif isinstance(value, str):
        result = value.strip()
    else:
        raise DssValidationError(
            f"Поле «{field}» повинно бути текстом."
        )

    if required and not result:
        raise DssValidationError(
            f"Поле «{field}» є обов'язковим."
        )

    if len(result) > max_length:
        raise DssValidationError(
            f"Поле «{field}» перевищує {max_length} символів."
        )

    return result


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise DssValidationError(
            f"Поле «{field}» повинно бути числом."
        )

    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise DssValidationError(
            f"Поле «{field}» повинно бути числом."
        ) from error

    if not math.isfinite(result):
        raise DssValidationError(
            f"Поле «{field}» повинно містити скінченне число."
        )

    return result


def _integer(
    value: Any,
    field: str,
    *,
    default: int,
) -> int:
    if value in (None, ""):
        return default

    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise DssValidationError(
            f"Поле «{field}» повинно бути цілим числом."
        ) from error


def _boolean(value: Any, default: bool = True) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "1", "yes", "on"}:
            return True

        if normalized in {"false", "0", "no", "off"}:
            return False

    raise DssValidationError(
        "Поле «Активність» повинно бути логічним значенням."
    )


def _validate_payload(
    payload: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = dict(existing or {})
    source.update(payload)

    name = _text(
        source.get("name"),
        "Назва правила",
        required=True,
        max_length=120,
    )

    try:
        criterion_id = int(source.get("criterion_id"))
    except (TypeError, ValueError) as error:
        raise DssValidationError(
            "Потрібно вибрати критерій."
        ) from error

    criterion = dss_repository.get_criterion_by_id(criterion_id)

    if criterion is None:
        raise DssNotFoundError(
            f"Критерій з id={criterion_id} не знайдено."
        )

    operator = _text(
        source.get("operator"),
        "Оператор",
        required=True,
        max_length=2,
    )

    if operator not in ALLOWED_OPERATORS:
        raise DssValidationError(
            "Оператор повинен бути <, <=, =, >= або >."
        )

    condition_value = _number(
        source.get("condition_value"),
        "Значення умови",
    )
    action_type = _text(
        source.get("action_type"),
        "Дія",
        required=True,
        max_length=20,
    )

    if action_type not in ALLOWED_ACTIONS:
        raise DssValidationError(
            "Дія повинна бути reject, penalty або bonus."
        )

    action_value = _number(
        source.get("action_value", 0),
        "Величина коригування",
    )

    if action_type == "reject":
        action_value = 0.0
    elif not 0 <= action_value <= 1:
        raise DssValidationError(
            "Величина штрафу або бонусу повинна бути від 0 до 1."
        )

    message = _text(
        source.get("message"),
        "Пояснення",
        max_length=500,
    )

    if not message:
        if action_type == "reject":
            message = (
                f"Альтернативу відхилено правилом «{name}»."
            )
        elif action_type == "penalty":
            message = (
                f"Оцінку зменшено на {action_value * 100:g}% "
                f"за правилом «{name}»."
            )
        else:
            message = (
                f"Оцінку збільшено на {action_value * 100:g}% "
                f"за правилом «{name}»."
            )

    return {
        "name": name,
        "criterion_id": criterion_id,
        "operator": operator,
        "condition_value": condition_value,
        "action_type": action_type,
        "action_value": action_value,
        "message": message,
        "priority": _integer(
            source.get("priority"),
            "Пріоритет",
            default=100,
        ),
        "is_active": _boolean(
            source.get("is_active"),
            default=True,
        ),
    }


def list_rules(
    *,
    include_inactive: bool = True,
) -> list[dict[str, Any]]:
    return repository.list_rules(
        include_inactive=include_inactive,
    )


def add_rule(payload: dict[str, Any]) -> dict[str, Any]:
    data = _validate_payload(payload)

    try:
        return repository.create_rule(data)
    except sqlite3.IntegrityError as error:
        raise DssConflictError(
            "Правило з такою назвою вже існує."
        ) from error


def edit_rule(
    rule_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    existing = repository.get_rule(rule_id)

    if existing is None:
        raise DssNotFoundError(
            f"Правило з id={rule_id} не знайдено."
        )

    data = _validate_payload(
        payload,
        existing=existing,
    )

    try:
        result = repository.update_rule(rule_id, data)
    except sqlite3.IntegrityError as error:
        raise DssConflictError(
            "Правило з такою назвою вже існує."
        ) from error

    if result is None:
        raise DssNotFoundError(
            f"Правило з id={rule_id} не знайдено."
        )

    return result


def remove_rule(rule_id: int) -> None:
    if not repository.delete_rule(rule_id):
        raise DssNotFoundError(
            f"Правило з id={rule_id} не знайдено."
        )


def _compare(
    value: float,
    operator: str,
    expected: float,
) -> bool:
    if operator == "<":
        return value < expected
    if operator == "<=":
        return value <= expected
    if operator == "=":
        return math.isclose(
            value,
            expected,
            rel_tol=1e-9,
            abs_tol=1e-9,
        )
    if operator == ">=":
        return value >= expected
    if operator == ">":
        return value > expected

    return False


def evaluate_rules_for_values(
    raw_values: dict[int, float | None],
    alternative: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate active rules for one alternative."""
    rules = repository.list_rules(
        include_inactive=False,
    )
    events: list[dict[str, Any]] = []
    penalty_factor = 1.0
    bonus_factor = 1.0
    rejected = False

    for rule in rules:
        criterion_id = int(rule["criterion_id"])
        raw_value = raw_values.get(criterion_id)

        if raw_value is None:
            continue

        if not _compare(
            float(raw_value),
            rule["operator"],
            float(rule["condition_value"]),
        ):
            continue

        action_type = rule["action_type"]
        action_value = float(rule["action_value"])

        if action_type == "reject":
            rejected = True
        elif action_type == "penalty":
            penalty_factor *= 1.0 - action_value
        elif action_type == "bonus":
            bonus_factor *= 1.0 + action_value

        events.append(
            {
                "rule_id": int(rule["id"]),
                "rule": rule["name"],
                "criterion_id": criterion_id,
                "criterion": rule["criterion_name"],
                "operator": rule["operator"],
                "condition_value": float(
                    rule["condition_value"]
                ),
                "actual_value": float(raw_value),
                "action_type": action_type,
                "action_label": ACTION_LABELS[action_type],
                "action_value": action_value,
                "message": rule["message"],
                "priority": int(rule["priority"]),
            }
        )

    factor = penalty_factor * bonus_factor

    return {
        "alternative_id": int(alternative["id"]),
        "alternative": alternative["name"],
        "rejected": rejected,
        "penalty_factor": round(penalty_factor, 6),
        "bonus_factor": round(bonus_factor, 6),
        "score_factor": round(factor, 6),
        "events": events,
    }


def apply_rule_adjustments(
    base_score: float,
    evaluation: dict[str, Any],
) -> float:
    if evaluation["rejected"]:
        return 0.0

    adjusted = float(base_score) * float(
        evaluation["score_factor"]
    )
    return round(min(1.0, max(0.0, adjusted)), 6)


def evaluate_current_matrix() -> dict[str, Any]:
    matrix = get_matrix()
    values = matrix["values"]
    alternatives: list[dict[str, Any]] = []
    triggered_count = 0
    rejected_count = 0

    for alternative in matrix["alternatives"]:
        alternative_values = values.get(
            str(alternative["id"]),
            {},
        )
        raw_values: dict[int, float | None] = {}

        for criterion in matrix["criteria"]:
            saved = alternative_values.get(
                str(criterion["id"])
            )
            raw_values[int(criterion["id"])] = (
                float(saved["value"])
                if saved is not None
                else None
            )

        evaluation = evaluate_rules_for_values(
            raw_values,
            alternative,
        )
        triggered_count += len(evaluation["events"])

        if evaluation["rejected"]:
            rejected_count += 1

        alternatives.append(evaluation)

    return {
        "alternatives": alternatives,
        "active_rules_count": len(
            repository.list_rules(
                include_inactive=False,
            )
        ),
        "triggered_events_count": triggered_count,
        "rejected_alternatives_count": rejected_count,
    }
