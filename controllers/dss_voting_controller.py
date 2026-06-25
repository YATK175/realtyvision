"""Controller for criterion voting in RealtyVision DSS."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request

from services.dss_service import DssValidationError
from services.dss_voting_service import (
    calculate_voting_weights,
    import_voting_from_google_sheets,
    list_voting_data,
)


dss_voting_blueprint = Blueprint(
    "dss_voting",
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

    if message:
        response["message"] = message

    if data is not None:
        response["data"] = data

    return jsonify(response), status_code


@dss_voting_blueprint.post(
    "/api/dss/voting/import/google-sheets"
)
def voting_import():
    data = _payload()
    result = import_voting_from_google_sheets(
        data.get("url", "")
    )

    return _success(
        result,
        message=result["message"],
        status_code=201,
    )


@dss_voting_blueprint.get(
    "/api/dss/voting"
)
def voting_list():
    return _success(list_voting_data())


@dss_voting_blueprint.post(
    "/api/dss/voting/calculate"
)
def voting_calculate():
    data = _payload()
    result = calculate_voting_weights(
        data.get("method", "borda")
    )

    return _success(
        result,
        message=result["message"],
    )


@dss_voting_blueprint.errorhandler(
    DssValidationError
)
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
