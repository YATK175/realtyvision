"""HTTP controller for persistent IF–THEN DSS rules."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request

from services.dss_rule_service import (
    add_rule,
    edit_rule,
    evaluate_current_matrix,
    list_rules,
    remove_rule,
)
from services.dss_service import (
    DssConflictError,
    DssNotFoundError,
    DssValidationError,
)


dss_rule_blueprint = Blueprint(
    "dss_rules",
    __name__,
)


def _payload() -> dict[str, Any]:
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        raise DssValidationError(
            "Тіло запиту повинно містити JSON-об'єкт."
        )

    return data


def _success(
    data: Any = None,
    *,
    message: str | None = None,
    status_code: int = 200,
):
    response: dict[str, Any] = {"success": True}

    if message is not None:
        response["message"] = message

    if data is not None:
        response["data"] = data

    return jsonify(response), status_code


@dss_rule_blueprint.get("/api/dss/rules")
def rules_list():
    raw = request.args.get(
        "include_inactive",
        "true",
    ).strip().lower()
    include_inactive = raw not in {
        "false",
        "0",
        "no",
        "off",
    }

    return _success(
        list_rules(
            include_inactive=include_inactive,
        )
    )


@dss_rule_blueprint.post("/api/dss/rules")
def rules_create():
    return _success(
        add_rule(_payload()),
        message="Правило IF–THEN створено.",
        status_code=201,
    )


@dss_rule_blueprint.put("/api/dss/rules/<int:rule_id>")
def rules_update(rule_id: int):
    return _success(
        edit_rule(rule_id, _payload()),
        message="Правило IF–THEN оновлено.",
    )


@dss_rule_blueprint.delete("/api/dss/rules/<int:rule_id>")
def rules_delete(rule_id: int):
    remove_rule(rule_id)
    return _success(
        message="Правило IF–THEN видалено."
    )


@dss_rule_blueprint.post("/api/dss/rules/evaluate")
def rules_evaluate():
    return _success(
        evaluate_current_matrix(),
        message="Правила застосовано до поточної матриці.",
    )


@dss_rule_blueprint.errorhandler(DssValidationError)
def validation_error(error: DssValidationError):
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


@dss_rule_blueprint.errorhandler(DssNotFoundError)
def not_found_error(error: DssNotFoundError):
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


@dss_rule_blueprint.errorhandler(DssConflictError)
def conflict_error(error: DssConflictError):
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
