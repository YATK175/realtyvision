"""Google Sheets import and consensus services for RealtyVision DSS."""

from __future__ import annotations

import csv
import io
import math
import re
import statistics
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from repositories import dss_expert_repository as repository
from repositories.dss_repository import save_score
from services.dss_service import DssValidationError


SUPPORTED_CONSENSUS_METHODS = {
    "arithmetic_mean",
    "median",
    "geometric_mean",
}

EXPERT_HEADER_ALIASES = {
    "експерт",
    "імя експерта",
    "ім'я експерта",
    "ім’я експерта",
    "expert",
    "expert name",
    "expert_name",
}

ALTERNATIVE_HEADER_ALIASES = {
    "альтернатива",
    "обєкт",
    "об'єкт",
    "об’єкт",
    "alternative",
    "object",
}


def _normalize_name(value: Any) -> str:
    """Normalize headers and entity names for case-insensitive matching."""
    text = str(value or "").strip().casefold()
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"[_\\-]+", " ", text)
    text = re.sub(r"\\s+", " ", text)
    return text


def _parse_number(value: Any, field_name: str) -> float:
    """Parse Ukrainian or English decimal notation."""
    text = str(value or "").strip()
    text = text.replace("\\u00a0", "").replace(" ", "")

    if "," in text and "." not in text:
        text = text.replace(",", ".")

    try:
        number = float(text)
    except ValueError as error:
        raise DssValidationError(
            f"Поле «{field_name}» повинно містити число."
        ) from error

    if not math.isfinite(number):
        raise DssValidationError(
            f"Поле «{field_name}» повинно містити скінченне число."
        )

    return number


def build_google_sheets_csv_url(url: str) -> str:
    """Convert a normal Google Sheets URL to a public CSV export URL."""
    raw_url = str(url or "").strip()

    if not raw_url:
        raise DssValidationError(
            "Вкажіть посилання на Google Таблицю."
        )

    parsed = urlparse(raw_url)

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
        return raw_url

    match = re.search(
        r"/spreadsheets/d/([A-Za-z0-9_-]+)",
        parsed.path,
    )

    if not match:
        raise DssValidationError(
            "Не вдалося визначити ідентифікатор Google Таблиці."
        )

    spreadsheet_id = match.group(1)
    gid = query.get("gid", [""])[0]

    if not gid and parsed.fragment:
        fragment_values = parse_qs(parsed.fragment)
        gid = fragment_values.get("gid", [""])[0]

    gid = gid or "0"

    return (
        "https://docs.google.com/spreadsheets/d/"
        f"{spreadsheet_id}/export?format=csv&gid={gid}"
    )


def _download_csv(csv_url: str) -> str:
    """Download public CSV text with a finite timeout."""
    request = Request(
        csv_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 RealtyVision-DSS/2.0 "
                "(Google Sheets CSV importer)"
            )
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get(
                "Content-Type",
                "",
            ).lower()
            data = response.read()
    except HTTPError as error:
        raise DssValidationError(
            "Google Таблиця недоступна. Перевірте спільний доступ "
            f"або публікацію. HTTP {error.code}."
        ) from error
    except URLError as error:
        raise DssValidationError(
            "Не вдалося підключитися до Google Sheets."
        ) from error

    text = data.decode("utf-8-sig", errors="replace")

    if "text/html" in content_type and "<html" in text.lower():
        raise DssValidationError(
            "Замість CSV отримано HTML. Надайте доступ "
            "«Усі, хто має посилання» або опублікуйте таблицю."
        )

    if not text.strip():
        raise DssValidationError(
            "Google Таблиця не містить даних."
        )

    return text


def _find_required_header(
    fieldnames: list[str],
    aliases: set[str],
    label: str,
) -> str:
    normalized = {
        _normalize_name(header): header
        for header in fieldnames
    }

    for alias in aliases:
        if _normalize_name(alias) in normalized:
            return normalized[_normalize_name(alias)]

    raise DssValidationError(
        f"У таблиці відсутній обов'язковий стовпець «{label}»."
    )


def _parse_csv(csv_text: str) -> list[dict[str, Any]]:
    """Validate a wide expert table and convert it to repository rows."""
    reader = csv.DictReader(io.StringIO(csv_text))

    if not reader.fieldnames:
        raise DssValidationError(
            "У CSV відсутній рядок заголовків."
        )

    fieldnames = [
        str(header or "").strip()
        for header in reader.fieldnames
    ]
    expert_header = _find_required_header(
        fieldnames,
        EXPERT_HEADER_ALIASES,
        "Експерт",
    )
    alternative_header = _find_required_header(
        fieldnames,
        ALTERNATIVE_HEADER_ALIASES,
        "Альтернатива",
    )

    references = repository.get_reference_data()
    alternatives_by_name = {
        _normalize_name(item["name"]): item
        for item in references["alternatives"]
    }
    criteria_by_name = {
        _normalize_name(item["name"]): item
        for item in references["criteria"]
    }

    criterion_headers: dict[str, dict[str, Any]] = {}

    for header in fieldnames:
        if header in {expert_header, alternative_header}:
            continue

        criterion = criteria_by_name.get(
            _normalize_name(header)
        )

        if criterion is not None:
            criterion_headers[header] = criterion

    if not criterion_headers:
        expected = ", ".join(
            item["name"]
            for item in references["criteria"]
        )
        raise DssValidationError(
            "Не знайдено стовпців критеріїв. "
            f"Очікувані назви: {expected}."
        )

    prepared_rows: list[dict[str, Any]] = []

    for row_number, raw_row in enumerate(reader, start=2):
        if not any(
            str(value or "").strip()
            for value in raw_row.values()
        ):
            continue

        expert_name = str(
            raw_row.get(expert_header, "")
        ).strip()
        alternative_name = str(
            raw_row.get(alternative_header, "")
        ).strip()

        if not expert_name:
            raise DssValidationError(
                f"Рядок {row_number}: не вказано експерта."
            )

        alternative = alternatives_by_name.get(
            _normalize_name(alternative_name)
        )

        if alternative is None:
            raise DssValidationError(
                f"Рядок {row_number}: альтернативу "
                f"«{alternative_name}» не знайдено в системі."
            )

        scores: dict[int, float] = {}

        for header, criterion in criterion_headers.items():
            raw_value = raw_row.get(header, "")

            if str(raw_value or "").strip() == "":
                raise DssValidationError(
                    f"Рядок {row_number}: відсутня оцінка "
                    f"за критерієм «{criterion['name']}»."
                )

            value = _parse_number(
                raw_value,
                f"{criterion['name']} у рядку {row_number}",
            )
            scale_min = criterion.get("scale_min")
            scale_max = criterion.get("scale_max")

            if (
                scale_min is not None
                and value < float(scale_min)
            ):
                raise DssValidationError(
                    f"Рядок {row_number}: значення "
                    f"«{criterion['name']}» менше за "
                    f"мінімум {scale_min}."
                )

            if (
                scale_max is not None
                and value > float(scale_max)
            ):
                raise DssValidationError(
                    f"Рядок {row_number}: значення "
                    f"«{criterion['name']}» більше за "
                    f"максимум {scale_max}."
                )

            scores[int(criterion["id"])] = value

        prepared_rows.append(
            {
                "expert_name": expert_name,
                "alternative_id": int(alternative["id"]),
                "alternative_name": alternative["name"],
                "scores": scores,
            }
        )

    if not prepared_rows:
        raise DssValidationError(
            "У Google Таблиці немає рядків для імпорту."
        )

    return prepared_rows


def import_from_google_sheets(url: str) -> dict[str, Any]:
    """Download, validate and save expert assessments."""
    csv_url = build_google_sheets_csv_url(url)
    csv_text = _download_csv(csv_url)
    rows = _parse_csv(csv_text)

    result = repository.import_expert_rows(
        rows,
        source_url=url,
        source="google_sheets",
    )
    result["csv_url"] = csv_url
    result["message"] = (
        "Експертні оцінки успішно імпортовано "
        "з Google Sheets."
    )

    return result


def list_expert_data() -> dict[str, Any]:
    """Return flat scores and a convenient display matrix."""
    scores = repository.list_expert_scores()
    experts: list[str] = []
    alternatives: list[str] = []
    criteria: list[str] = []
    matrix: dict[str, dict[str, dict[str, float]]] = {}

    for item in scores:
        expert = item["expert_name"]
        alternative = item["alternative_name"]
        criterion = item["criterion_name"]

        if expert not in experts:
            experts.append(expert)
        if alternative not in alternatives:
            alternatives.append(alternative)
        if criterion not in criteria:
            criteria.append(criterion)

        matrix.setdefault(expert, {}).setdefault(
            alternative,
            {},
        )[criterion] = float(item["value"])

    return {
        "scores": scores,
        "experts": experts,
        "alternatives": alternatives,
        "criteria": criteria,
        "matrix": matrix,
        "imports": repository.list_import_batches(),
    }


def calculate_consensus(method: str) -> dict[str, Any]:
    """Aggregate expert scores and save them as the DSS matrix."""
    normalized_method = str(method or "").strip().lower()

    if normalized_method not in SUPPORTED_CONSENSUS_METHODS:
        raise DssValidationError(
            "Метод узгодження повинен бути arithmetic_mean, "
            "median або geometric_mean."
        )

    groups = repository.get_grouped_expert_values()

    if not groups:
        raise DssValidationError(
            "Спочатку імпортуйте оцінки експертів."
        )

    results: list[dict[str, Any]] = []

    for group in groups:
        values = [
            float(value)
            for value in group["values"]
        ]

        if normalized_method == "arithmetic_mean":
            consensus_value = statistics.fmean(values)
        elif normalized_method == "median":
            consensus_value = statistics.median(values)
        else:
            if any(value <= 0 for value in values):
                raise DssValidationError(
                    "Середнє геометричне можна обчислити "
                    "лише для додатних оцінок."
                )
            consensus_value = math.exp(
                statistics.fmean(
                    math.log(value)
                    for value in values
                )
            )

        saved = save_score(
            alternative_id=int(group["alternative_id"]),
            criterion_id=int(group["criterion_id"]),
            value=float(consensus_value),
            source="expert_consensus",
        )

        results.append(
            {
                "alternative_id": group["alternative_id"],
                "alternative": group["alternative_name"],
                "criterion_id": group["criterion_id"],
                "criterion": group["criterion_name"],
                "experts_count": len(values),
                "values": values,
                "consensus_value": round(
                    float(consensus_value),
                    6,
                ),
                "saved_score_id": saved["id"],
            }
        )

    return {
        "method": normalized_method,
        "groups_count": len(results),
        "results": results,
        "message": (
            "Узгоджені оцінки записано до матриці "
            "альтернатив."
        ),
    }
