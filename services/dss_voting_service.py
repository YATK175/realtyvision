"""Voting methods for criterion-weight determination in RealtyVision DSS."""

from __future__ import annotations

import csv
import io
import math
import re
from itertools import combinations
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from repositories import dss_voting_repository as repository
from services.dss_service import DssValidationError


SUPPORTED_METHODS = {
    "plurality",
    "borda",
    "approval",
    "copeland",
}

METHOD_LABELS = {
    "plurality": "Відносна більшість",
    "borda": "Метод Борда",
    "approval": "Схвальне голосування",
    "copeland": "Попарне порівняння (Коупленд)",
}

EXPERT_ALIASES = {
    "експерт",
    "імя експерта",
    "ім'я експерта",
    "ім’я експерта",
    "expert",
    "expert name",
}

APPROVED_ALIASES = {
    "схвалені",
    "схвалені критерії",
    "approved",
    "approved criteria",
}


def _normalize(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"[_\\-]+", " ", text)
    text = re.sub(r"\\s+", " ", text)
    return text


def build_csv_url(url: str) -> str:
    """Accept both published CSV URLs and normal editable Sheets URLs."""
    raw = str(url or "").strip()

    if not raw:
        raise DssValidationError(
            "Вкажіть посилання на Google Таблицю з голосуванням."
        )

    parsed = urlparse(raw)

    if parsed.scheme not in {"http", "https"}:
        raise DssValidationError(
            "Посилання повинно починатися з http:// або https://."
        )

    if "docs.google.com" not in parsed.netloc:
        raise DssValidationError(
            "Підтримуються лише посилання Google Sheets."
        )

    query = parse_qs(parsed.query)

    if (
        query.get("output", [""])[0].lower() == "csv"
        or query.get("format", [""])[0].lower() == "csv"
    ):
        return raw

    match = re.search(
        r"/spreadsheets/d/([A-Za-z0-9_-]+)",
        parsed.path,
    )

    if not match:
        raise DssValidationError(
            "Для імпорту використайте опубліковане CSV-посилання "
            "або звичайне посилання Google Sheets."
        )

    spreadsheet_id = match.group(1)
    gid = query.get("gid", ["0"])[0] or "0"

    return (
        "https://docs.google.com/spreadsheets/d/"
        f"{spreadsheet_id}/export?format=csv&gid={gid}"
    )


def _download_csv(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 RealtyVision-DSS-Voting/2.0"
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            data = response.read()
            content_type = response.headers.get(
                "Content-Type",
                "",
            ).lower()
    except HTTPError as error:
        raise DssValidationError(
            "Google Таблиця голосування недоступна. "
            f"HTTP {error.code}."
        ) from error
    except URLError as error:
        raise DssValidationError(
            "Не вдалося підключитися до Google Sheets."
        ) from error

    text = data.decode("utf-8-sig", errors="replace")

    if "text/html" in content_type and "<html" in text.lower():
        raise DssValidationError(
            "Замість CSV отримано HTML. Опублікуйте аркуш у форматі CSV."
        )

    if not text.strip():
        raise DssValidationError(
            "Таблиця голосування порожня."
        )

    return text


def _find_header(
    fieldnames: list[str],
    aliases: set[str],
    label: str,
) -> str:
    normalized = {
        _normalize(item): item
        for item in fieldnames
    }

    for alias in aliases:
        key = _normalize(alias)

        if key in normalized:
            return normalized[key]

    raise DssValidationError(
        f"У таблиці відсутній стовпець «{label}»."
    )


def _rank_headers(fieldnames: list[str]) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []

    for header in fieldnames:
        normalized = _normalize(header)
        match = re.match(
            r"^(\d+)\s*(місце|место|place)?$",
            normalized,
        )

        if match:
            result.append((int(match.group(1)), header))

    return sorted(result)


def _parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise DssValidationError(
            "У CSV відсутні заголовки."
        )

    fieldnames = [
        str(item or "").strip()
        for item in reader.fieldnames
    ]
    expert_header = _find_header(
        fieldnames,
        EXPERT_ALIASES,
        "Експерт",
    )
    approved_header = _find_header(
        fieldnames,
        APPROVED_ALIASES,
        "Схвалені критерії",
    )
    rank_headers = _rank_headers(fieldnames)
    criteria = repository.get_active_criteria()

    if not criteria:
        raise DssValidationError(
            "Активні критерії відсутні."
        )

    if len(rank_headers) != len(criteria):
        raise DssValidationError(
            "Кількість стовпців місць повинна дорівнювати "
            f"кількості активних критеріїв ({len(criteria)})."
        )

    criteria_by_name = {
        _normalize(item["name"]): item
        for item in criteria
    }
    experts: list[dict[str, Any]] = []

    for row_number, row in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in row.values()):
            continue

        expert_name = str(
            row.get(expert_header, "")
        ).strip()

        if not expert_name:
            raise DssValidationError(
                f"Рядок {row_number}: не вказано експерта."
            )

        ranked_ids: set[int] = set()
        ranking: list[dict[str, Any]] = []

        approved_names = {
            _normalize(item)
            for item in re.split(
                r"[,;|]",
                str(row.get(approved_header, "")),
            )
            if str(item).strip()
        }

        for position, header in rank_headers:
            criterion_name = str(
                row.get(header, "")
            ).strip()
            criterion = criteria_by_name.get(
                _normalize(criterion_name)
            )

            if criterion is None:
                raise DssValidationError(
                    f"Рядок {row_number}: критерій "
                    f"«{criterion_name}» не знайдено."
                )

            criterion_id = int(criterion["id"])

            if criterion_id in ranked_ids:
                raise DssValidationError(
                    f"Рядок {row_number}: критерій "
                    f"«{criterion_name}» повторюється."
                )

            ranked_ids.add(criterion_id)
            ranking.append(
                {
                    "criterion_id": criterion_id,
                    "criterion_name": criterion["name"],
                    "rank_position": int(position),
                    "approved": int(
                        _normalize(criterion["name"])
                        in approved_names
                    ),
                }
            )

        if len(ranked_ids) != len(criteria):
            raise DssValidationError(
                f"Рядок {row_number}: рейтинг має містити "
                "всі активні критерії."
            )

        experts.append(
            {
                "expert_name": expert_name,
                "ranking": ranking,
            }
        )

    if not experts:
        raise DssValidationError(
            "У таблиці немає голосів експертів."
        )

    return experts


def import_voting_from_google_sheets(url: str) -> dict[str, Any]:
    csv_url = build_csv_url(url)
    text = _download_csv(csv_url)
    experts = _parse_csv(text)
    result = repository.replace_ballots(
        experts,
        source_url=url,
    )
    result["csv_url"] = csv_url
    result["message"] = "Голоси експертів успішно імпортовано."
    return result


def list_voting_data() -> dict[str, Any]:
    ballots = repository.list_ballots()
    experts: list[str] = []
    matrix: dict[str, list[dict[str, Any]]] = {}

    for item in ballots:
        expert = item["expert_name"]

        if expert not in experts:
            experts.append(expert)

        matrix.setdefault(expert, []).append(
            {
                "criterion_id": item["criterion_id"],
                "criterion": item["criterion_name"],
                "rank_position": item["rank_position"],
                "approved": bool(item["approved"]),
            }
        )

    return {
        "experts": experts,
        "ballots": ballots,
        "matrix": matrix,
        "imports": repository.list_imports(),
        "results": repository.list_results(),
        "methods": METHOD_LABELS,
    }


def _normalize_scores(
    scores: dict[int, float],
) -> dict[int, float]:
    total = sum(scores.values())

    if math.isclose(total, 0.0, abs_tol=1e-12):
        equal = 1.0 / len(scores)
        return {
            criterion_id: equal
            for criterion_id in scores
        }

    return {
        criterion_id: value / total
        for criterion_id, value in scores.items()
    }


def calculate_voting_weights(method: str) -> dict[str, Any]:
    normalized_method = str(method or "").strip().lower()

    if normalized_method not in SUPPORTED_METHODS:
        raise DssValidationError(
            "Метод голосування повинен бути plurality, "
            "borda, approval або copeland."
        )

    criteria = repository.get_active_criteria()
    ballots = repository.list_ballots()

    if not ballots:
        raise DssValidationError(
            "Спочатку імпортуйте результати голосування."
        )

    criterion_names = {
        int(item["id"]): item["name"]
        for item in criteria
    }
    scores = {
        int(item["id"]): 0.0
        for item in criteria
    }
    experts: dict[str, list[dict[str, Any]]] = {}

    for ballot in ballots:
        experts.setdefault(
            ballot["expert_name"],
            [],
        ).append(ballot)

    for expert_ballots in experts.values():
        expert_ballots.sort(
            key=lambda item: int(item["rank_position"])
        )

    if normalized_method == "plurality":
        for expert_ballots in experts.values():
            first = expert_ballots[0]
            scores[int(first["criterion_id"])] += 1.0

    elif normalized_method == "borda":
        criterion_count = len(criteria)

        for expert_ballots in experts.values():
            for ballot in expert_ballots:
                points = (
                    criterion_count
                    - int(ballot["rank_position"])
                )
                scores[int(ballot["criterion_id"])] += float(points)

    elif normalized_method == "approval":
        for ballot in ballots:
            if bool(ballot["approved"]):
                scores[int(ballot["criterion_id"])] += 1.0

    else:
        wins = {
            criterion_id: 0.0
            for criterion_id in scores
        }
        losses = {
            criterion_id: 0.0
            for criterion_id in scores
        }
        criterion_ids = list(scores)

        for first_id, second_id in combinations(criterion_ids, 2):
            first_votes = 0
            second_votes = 0

            for expert_ballots in experts.values():
                positions = {
                    int(item["criterion_id"]):
                    int(item["rank_position"])
                    for item in expert_ballots
                }

                if positions[first_id] < positions[second_id]:
                    first_votes += 1
                elif positions[second_id] < positions[first_id]:
                    second_votes += 1

            if first_votes > second_votes:
                wins[first_id] += 1.0
                losses[second_id] += 1.0
            elif second_votes > first_votes:
                wins[second_id] += 1.0
                losses[first_id] += 1.0
            else:
                wins[first_id] += 0.5
                wins[second_id] += 0.5

        copeland = {
            criterion_id:
            wins[criterion_id] - losses[criterion_id]
            for criterion_id in criterion_ids
        }
        minimum = min(copeland.values())
        shift = -minimum if minimum < 0 else 0.0
        scores = {
            criterion_id: value + shift
            for criterion_id, value in copeland.items()
        }

    weights = _normalize_scores(scores)
    results = [
        {
            "criterion_id": criterion_id,
            "criterion": criterion_names[criterion_id],
            "raw_score": round(scores[criterion_id], 6),
            "weight": round(weights[criterion_id], 6),
        }
        for criterion_id in scores
    ]
    results.sort(
        key=lambda item: (
            -item["weight"],
            item["criterion_id"],
        )
    )

    repository.save_result_and_apply_weights(
        normalized_method,
        results,
    )

    return {
        "method": normalized_method,
        "method_label": METHOD_LABELS[normalized_method],
        "experts_count": len(experts),
        "results": results,
        "weight_sum": round(
            sum(item["weight"] for item in results),
            6,
        ),
        "message": (
            "Ваги критеріїв розраховано та застосовано "
            "до моделі СППР."
        ),
    }
