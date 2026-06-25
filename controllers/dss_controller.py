"""HTTP controller for the RealtyVision DSS module."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, render_template, request

from services.dss_calculation_service import (
    calculate_ranking,
    compare_methods,
    sensitivity_analysis,
)
from services.dss_service import (
    DssConflictError,
    DssNotFoundError,
    DssValidationError,
    add_alternative,
    add_criterion,
    edit_alternative,
    edit_criterion,
    get_alternative,
    get_criterion,
    get_matrix,
    list_alternatives,
    list_criteria,
    remove_alternative,
    remove_criterion,
    remove_score,
    set_score,
)


dss_blueprint = Blueprint("dss", __name__)


def _json_payload() -> dict[str, Any]:
    """Return the request JSON object or raise a validation error."""
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        raise DssValidationError(
            "Тіло запиту повинно містити JSON-об'єкт."
        )

    return payload


def _success(
    data: Any = None,
    *,
    message: str | None = None,
    status_code: int = 200,
):
    """Create a consistent successful JSON response."""
    response: dict[str, Any] = {"success": True}

    if message is not None:
        response["message"] = message

    if data is not None:
        response["data"] = data

    return jsonify(response), status_code


@dss_blueprint.get("/dss")
def dss_page():
    """Render the DSS user interface."""
    return render_template("dss.html")


@dss_blueprint.get("/api/dss/status")
def dss_status():
    """Return the current implementation status."""
    return _success(
        {
            "module": "RealtyVision DSS",
            "laboratory": 2,
            "stage": "Decision calculation and analysis",
            "screens": [
                "Експертиза",
                "Модель та дані",
                "Експертна логіка",
                "Результати та аналіз",
            ],
            "implemented": [
                "SQLite schema",
                "Alternatives CRUD",
                "Criteria CRUD",
                "Evaluation matrix API",
                "Server-side validation",
                "Threshold filtering",
                "Additive aggregation",
                "Cautious aggregation",
                "Multiplicative aggregation",
                "Ranking and explanation",
                "Sensitivity analysis",
                "Method comparison",
            ],
        }
    )


@dss_blueprint.get("/api/dss/alternatives")
def alternatives_list():
    return _success(list_alternatives())


@dss_blueprint.post("/api/dss/alternatives")
def alternatives_create():
    alternative = add_alternative(_json_payload())
    return _success(
        alternative,
        message="Альтернативу успішно створено.",
        status_code=201,
    )


@dss_blueprint.get("/api/dss/alternatives/<int:alternative_id>")
def alternatives_get(alternative_id: int):
    return _success(get_alternative(alternative_id))


@dss_blueprint.put("/api/dss/alternatives/<int:alternative_id>")
def alternatives_update(alternative_id: int):
    alternative = edit_alternative(
        alternative_id,
        _json_payload(),
    )
    return _success(
        alternative,
        message="Альтернативу успішно оновлено.",
    )


@dss_blueprint.delete("/api/dss/alternatives/<int:alternative_id>")
def alternatives_delete(alternative_id: int):
    remove_alternative(alternative_id)
    return _success(
        message="Альтернативу успішно видалено."
    )


@dss_blueprint.get("/api/dss/criteria")
def criteria_list():
    raw_value = request.args.get(
        "include_inactive",
        "true",
    ).strip().lower()

    include_inactive = raw_value not in {
        "false",
        "0",
        "no",
        "off",
    }

    return _success(
        list_criteria(
            include_inactive=include_inactive
        )
    )


@dss_blueprint.post("/api/dss/criteria")
def criteria_create():
    criterion = add_criterion(_json_payload())
    return _success(
        criterion,
        message="Критерій успішно створено.",
        status_code=201,
    )


@dss_blueprint.get("/api/dss/criteria/<int:criterion_id>")
def criteria_get(criterion_id: int):
    return _success(get_criterion(criterion_id))


@dss_blueprint.put("/api/dss/criteria/<int:criterion_id>")
def criteria_update(criterion_id: int):
    criterion = edit_criterion(
        criterion_id,
        _json_payload(),
    )
    return _success(
        criterion,
        message="Критерій успішно оновлено.",
    )


@dss_blueprint.delete("/api/dss/criteria/<int:criterion_id>")
def criteria_delete(criterion_id: int):
    remove_criterion(criterion_id)
    return _success(
        message="Критерій успішно видалено."
    )


@dss_blueprint.get("/api/dss/matrix")
def matrix_get():
    return _success(get_matrix())


@dss_blueprint.put("/api/dss/scores")
def scores_save():
    score = set_score(_json_payload())
    return _success(
        score,
        message="Оцінку успішно збережено.",
    )


@dss_blueprint.delete(
    "/api/dss/scores/<int:alternative_id>/<int:criterion_id>"
)
def scores_delete(
    alternative_id: int,
    criterion_id: int,
):
    remove_score(alternative_id, criterion_id)
    return _success(
        message="Оцінку успішно видалено."
    )


@dss_blueprint.post("/api/dss/calculate")
def calculate():
    payload = _json_payload()
    method = payload.get("method", "additive")

    return _success(
        calculate_ranking(method),
        message="Рейтинг альтернатив успішно розраховано.",
    )


@dss_blueprint.get("/api/dss/compare-methods")
def methods_compare():
    return _success(compare_methods())


@dss_blueprint.post("/api/dss/sensitivity")
def sensitivity():
    payload = _json_payload()

    try:
        criterion_id = int(payload.get("criterion_id"))
        new_weight = float(payload.get("new_weight"))
    except (TypeError, ValueError) as error:
        raise DssValidationError(
            "criterion_id повинен бути цілим числом, "
            "а new_weight — числом."
        ) from error

    method = payload.get("method", "additive")

    return _success(
        sensitivity_analysis(
            criterion_id=criterion_id,
            new_weight=new_weight,
            method=method,
        )
    )


@dss_blueprint.errorhandler(DssValidationError)
def handle_validation_error(error: DssValidationError):
    return (
        jsonify(
            {
                "success": False,
                "error": "validation_error",
                "message": str(error),
            }
        ),
        400,
    )


@dss_blueprint.errorhandler(DssNotFoundError)
def handle_not_found_error(error: DssNotFoundError):
    return (
        jsonify(
            {
                "success": False,
                "error": "not_found",
                "message": str(error),
            }
        ),
        404,
    )


@dss_blueprint.errorhandler(DssConflictError)
def handle_conflict_error(error: DssConflictError):
    return (
        jsonify(
            {
                "success": False,
                "error": "conflict",
                "message": str(error),
            }
        ),
        409,
    )


@dss_blueprint.errorhandler(405)
def handle_method_not_allowed(error):
    return (
        jsonify(
            {
                "success": False,
                "error": "method_not_allowed",
                "message": "Цей HTTP-метод не підтримується.",
            }
        ),
        405,
    )
