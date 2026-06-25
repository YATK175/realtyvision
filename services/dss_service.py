"""Service layer for the RealtyVision DSS module."""

from __future__ import annotations

import math
import sqlite3
from typing import Any

from repositories import dss_repository as repository


ALLOWED_CRITERION_TYPES = {"maximize", "minimize"}
ALLOWED_THRESHOLD_OPERATORS = {"<", "<=", "=", ">=", ">"}
ALLOWED_SCORE_SOURCES = {"manual", "import", "expert_consensus"}


class DssValidationError(ValueError):
    """Raised when input data does not satisfy DSS validation rules."""


class DssNotFoundError(LookupError):
    """Raised when a requested DSS entity does not exist."""


class DssConflictError(RuntimeError):
    """Raised when a unique database constraint is violated."""


def _clean_text(
    value: Any,
    field_name: str,
    *,
    required: bool = False,
    max_length: int = 500,
) -> str:
    """Normalize and validate a text field."""
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise DssValidationError(
            f"Поле «{field_name}» повинно бути текстом."
        )

    if required and not text:
        raise DssValidationError(
            f"Поле «{field_name}» є обов'язковим."
        )

    if len(text) > max_length:
        raise DssValidationError(
            f"Поле «{field_name}» не може містити більше "
            f"{max_length} символів."
        )

    return text


def _to_float(
    value: Any,
    field_name: str,
    *,
    required: bool = True,
) -> float | None:
    """Convert a value to a finite floating-point number."""
    if value in (None, ""):
        if required:
            raise DssValidationError(
                f"Поле «{field_name}» є обов'язковим."
            )
        return None

    if isinstance(value, bool):
        raise DssValidationError(
            f"Поле «{field_name}» повинно бути числом."
        )

    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise DssValidationError(
            f"Поле «{field_name}» повинно бути числом."
        ) from error

    if not math.isfinite(number):
        raise DssValidationError(
            f"Поле «{field_name}» повинно містити скінченне число."
        )

    return number


def _to_bool(value: Any, default: bool = True) -> bool:
    """Convert common JSON and form values to bool."""
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value != 0

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "1", "yes", "on", "так"}:
            return True

        if normalized in {"false", "0", "no", "off", "ні"}:
            return False

    raise DssValidationError(
        "Поле активності повинно бути логічним значенням."
    )


def _translate_integrity_error(error: sqlite3.IntegrityError) -> None:
    """Convert low-level SQLite errors into user-facing service errors."""
    message = str(error).lower()

    if "dss_alternatives.name" in message:
        raise DssConflictError(
            "Альтернатива з такою назвою вже існує."
        ) from error

    if "dss_criteria.name" in message:
        raise DssConflictError(
            "Критерій з такою назвою вже існує."
        ) from error

    if "foreign key constraint failed" in message:
        raise DssValidationError(
            "Не знайдено пов'язану альтернативу або критерій."
        ) from error

    raise DssConflictError(
        "Не вдалося зберегти дані через обмеження бази даних."
    ) from error


# =====================================================
# ALTERNATIVES
# =====================================================

def list_alternatives() -> list[dict[str, Any]]:
    """Return all alternatives."""
    return repository.get_all_alternatives()


def get_alternative(alternative_id: int) -> dict[str, Any]:
    """Return one alternative or raise a not-found error."""
    alternative = repository.get_alternative_by_id(alternative_id)

    if alternative is None:
        raise DssNotFoundError(
            f"Альтернативу з id={alternative_id} не знайдено."
        )

    return alternative


def add_alternative(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and create an alternative."""
    if not isinstance(payload, dict):
        raise DssValidationError(
            "Дані альтернативи повинні бути JSON-об'єктом."
        )

    name = _clean_text(
        payload.get("name"),
        "Назва",
        required=True,
        max_length=120,
    )
    description = _clean_text(
        payload.get("description"),
        "Опис",
        max_length=1000,
    )
    address = _clean_text(
        payload.get("address"),
        "Адреса",
        max_length=250,
    )

    try:
        return repository.create_alternative(
            name=name,
            description=description,
            address=address,
        )
    except sqlite3.IntegrityError as error:
        _translate_integrity_error(error)
        raise


def edit_alternative(
    alternative_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Validate and update an alternative."""
    get_alternative(alternative_id)

    if not isinstance(payload, dict):
        raise DssValidationError(
            "Дані альтернативи повинні бути JSON-об'єктом."
        )

    name = _clean_text(
        payload.get("name"),
        "Назва",
        required=True,
        max_length=120,
    )
    description = _clean_text(
        payload.get("description"),
        "Опис",
        max_length=1000,
    )
    address = _clean_text(
        payload.get("address"),
        "Адреса",
        max_length=250,
    )

    try:
        updated = repository.update_alternative(
            alternative_id=alternative_id,
            name=name,
            description=description,
            address=address,
        )
    except sqlite3.IntegrityError as error:
        _translate_integrity_error(error)
        raise

    if updated is None:
        raise DssNotFoundError(
            f"Альтернативу з id={alternative_id} не знайдено."
        )

    return updated


def remove_alternative(alternative_id: int) -> None:
    """Delete an alternative."""
    deleted = repository.delete_alternative(alternative_id)

    if not deleted:
        raise DssNotFoundError(
            f"Альтернативу з id={alternative_id} не знайдено."
        )


# =====================================================
# CRITERIA
# =====================================================

def list_criteria(
    include_inactive: bool = True,
) -> list[dict[str, Any]]:
    """Return criteria."""
    return repository.get_all_criteria(
        include_inactive=include_inactive
    )


def get_criterion(criterion_id: int) -> dict[str, Any]:
    """Return one criterion or raise a not-found error."""
    criterion = repository.get_criterion_by_id(criterion_id)

    if criterion is None:
        raise DssNotFoundError(
            f"Критерій з id={criterion_id} не знайдено."
        )

    return criterion


def _validate_criterion_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Validate and normalize criterion input."""
    if not isinstance(payload, dict):
        raise DssValidationError(
            "Дані критерію повинні бути JSON-об'єктом."
        )

    name = _clean_text(
        payload.get("name"),
        "Назва критерію",
        required=True,
        max_length=120,
    )

    criterion_type = _clean_text(
        payload.get("criterion_type"),
        "Тип критерію",
        required=True,
        max_length=20,
    ).lower()

    if criterion_type not in ALLOWED_CRITERION_TYPES:
        raise DssValidationError(
            "Тип критерію повинен бути maximize або minimize."
        )

    weight = _to_float(
        payload.get("weight"),
        "Вага",
    )
    assert weight is not None

    if not 0 <= weight <= 1:
        raise DssValidationError(
            "Вага критерію повинна бути в межах від 0 до 1."
        )

    unit = _clean_text(
        payload.get("unit"),
        "Одиниця вимірювання",
        max_length=50,
    )
    scale_min = _to_float(
        payload.get("scale_min"),
        "Мінімум шкали",
        required=False,
    )
    scale_max = _to_float(
        payload.get("scale_max"),
        "Максимум шкали",
        required=False,
    )

    if (
        scale_min is not None
        and scale_max is not None
        and scale_max <= scale_min
    ):
        raise DssValidationError(
            "Максимум шкали повинен бути більшим за мінімум."
        )

    threshold_operator_raw = payload.get("threshold_operator")

    if threshold_operator_raw in (None, ""):
        threshold_operator = None
    else:
        threshold_operator = _clean_text(
            threshold_operator_raw,
            "Оператор порога",
            max_length=2,
        )

        if threshold_operator not in ALLOWED_THRESHOLD_OPERATORS:
            raise DssValidationError(
                "Оператор порога повинен бути одним із: "
                "<, <=, =, >=, >."
            )

    threshold_value = _to_float(
        payload.get("threshold_value"),
        "Порогове значення",
        required=False,
    )

    if (
        threshold_operator is not None
        and threshold_value is None
    ):
        raise DssValidationError(
            "Для вибраного оператора потрібно вказати порогове значення."
        )

    if (
        threshold_operator is None
        and threshold_value is not None
    ):
        raise DssValidationError(
            "Для порогового значення потрібно вибрати оператор."
        )

    is_active = _to_bool(
        payload.get("is_active"),
        default=True,
    )

    return {
        "name": name,
        "criterion_type": criterion_type,
        "weight": weight,
        "unit": unit,
        "scale_min": scale_min,
        "scale_max": scale_max,
        "threshold_operator": threshold_operator,
        "threshold_value": threshold_value,
        "is_active": is_active,
    }


def _validate_weight_total(
    new_weight: float,
    new_is_active: bool,
    *,
    replaced_criterion: dict[str, Any] | None = None,
) -> None:
    """Prevent the active criterion weight sum from exceeding 1."""
    current_total = repository.get_weight_sum()

    if replaced_criterion and replaced_criterion["is_active"]:
        current_total -= float(replaced_criterion["weight"])

    if new_is_active:
        current_total += new_weight

    if current_total > 1.000001:
        raise DssValidationError(
            "Сума ваг активних критеріїв не може перевищувати 1."
        )


def add_criterion(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and create a criterion."""
    data = _validate_criterion_payload(payload)

    _validate_weight_total(
        data["weight"],
        data["is_active"],
    )

    try:
        return repository.create_criterion(**data)
    except sqlite3.IntegrityError as error:
        _translate_integrity_error(error)
        raise


def edit_criterion(
    criterion_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Validate and update a criterion."""
    current = get_criterion(criterion_id)
    data = _validate_criterion_payload(payload)

    _validate_weight_total(
        data["weight"],
        data["is_active"],
        replaced_criterion=current,
    )

    try:
        updated = repository.update_criterion(
            criterion_id=criterion_id,
            **data,
        )
    except sqlite3.IntegrityError as error:
        _translate_integrity_error(error)
        raise

    if updated is None:
        raise DssNotFoundError(
            f"Критерій з id={criterion_id} не знайдено."
        )

    return updated


def remove_criterion(criterion_id: int) -> None:
    """Delete a criterion."""
    deleted = repository.delete_criterion(criterion_id)

    if not deleted:
        raise DssNotFoundError(
            f"Критерій з id={criterion_id} не знайдено."
        )


# =====================================================
# EVALUATION MATRIX
# =====================================================

def set_score(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and save one evaluation matrix value."""
    if not isinstance(payload, dict):
        raise DssValidationError(
            "Дані оцінки повинні бути JSON-об'єктом."
        )

    try:
        alternative_id = int(payload.get("alternative_id"))
        criterion_id = int(payload.get("criterion_id"))
    except (TypeError, ValueError) as error:
        raise DssValidationError(
            "alternative_id і criterion_id повинні бути цілими числами."
        ) from error

    alternative = get_alternative(alternative_id)
    criterion = get_criterion(criterion_id)

    value = _to_float(
        payload.get("value"),
        "Оцінка",
    )
    assert value is not None

    scale_min = criterion.get("scale_min")
    scale_max = criterion.get("scale_max")

    if scale_min is not None and value < float(scale_min):
        raise DssValidationError(
            f"Значення для критерію «{criterion['name']}» "
            f"не може бути меншим за {scale_min}."
        )

    if scale_max is not None and value > float(scale_max):
        raise DssValidationError(
            f"Значення для критерію «{criterion['name']}» "
            f"не може бути більшим за {scale_max}."
        )

    source = _clean_text(
        payload.get("source", "manual"),
        "Джерело оцінки",
        required=True,
        max_length=30,
    )

    if source not in ALLOWED_SCORE_SOURCES:
        raise DssValidationError(
            "Джерело оцінки повинно бути manual, import "
            "або expert_consensus."
        )

    try:
        saved = repository.save_score(
            alternative_id=alternative_id,
            criterion_id=criterion_id,
            value=value,
            source=source,
        )
    except sqlite3.IntegrityError as error:
        _translate_integrity_error(error)
        raise

    saved["alternative_name"] = alternative["name"]
    saved["criterion_name"] = criterion["name"]

    return saved


def remove_score(
    alternative_id: int,
    criterion_id: int,
) -> None:
    """Delete one evaluation matrix value."""
    deleted = repository.delete_score(
        alternative_id,
        criterion_id,
    )

    if not deleted:
        raise DssNotFoundError(
            "Оцінку для вибраної альтернативи та критерію не знайдено."
        )


def get_matrix() -> dict[str, Any]:
    """Return the evaluation matrix with validation metadata."""
    matrix = repository.get_evaluation_matrix()

    alternative_ids = {
        str(item["id"])
        for item in matrix["alternatives"]
    }
    criterion_ids = {
        str(item["id"])
        for item in matrix["criteria"]
    }

    missing_values: list[dict[str, int]] = []

    for alternative_id in alternative_ids:
        current_values = matrix["values"].get(
            alternative_id,
            {},
        )

        for criterion_id in criterion_ids:
            if criterion_id not in current_values:
                missing_values.append(
                    {
                        "alternative_id": int(alternative_id),
                        "criterion_id": int(criterion_id),
                    }
                )

    weight_sum = repository.get_weight_sum()

    matrix["validation"] = {
        "weight_sum": round(weight_sum, 6),
        "weights_are_normalized": math.isclose(
            weight_sum,
            1.0,
            abs_tol=1e-6,
        ),
        "expected_values_count": (
            len(alternative_ids) * len(criterion_ids)
        ),
        "saved_values_count": sum(
            len(values)
            for values in matrix["values"].values()
        ),
        "missing_values": missing_values,
        "matrix_is_complete": len(missing_values) == 0,
    }

    return matrix
