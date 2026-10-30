from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv


load_dotenv()

EPA_API_ENV_KEYS = ("EPA_API_KEY", "CAMD_API_KEY", "EPA_CAMD_API_KEY")


def _raise_for_http_error(response: requests.Response, *, context: str) -> None:
    status_code = getattr(response, "status_code", None)
    if status_code is None or status_code < 400:
        return

    body = getattr(response, "text", "") or ""
    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = payload.get("message") or payload.get("error", {}).get("message") or payload.get("error", {}).get("code") or str(payload)
    except Exception:
        detail = body[:300].strip()

    if status_code in {401, 403}:
        raise PermissionError(f"EPA API authorization failed for {context}: {detail or 'unauthorized request'}")
    raise RuntimeError(f"EPA API request failed for {context} ({status_code}): {detail or 'request failed'}")


def _fetch_epa_dataset(
    *,
    api_url: str,
    output_dir: Path,
    dataset_name: str,
    api_key_names: tuple[str, ...],
    params: dict[str, str] | None = None,
    area_nm: str | None = None,
    records: int = 48,
) -> Path:
    """Fetch a generic EPA dataset and save it under a dataset-specific raw file name."""
    if not api_url:
        env_key = f"{dataset_name.upper()}_API_URL"
        api_url = os.getenv(env_key) or os.getenv("EPA_API_URL") or "https://api.epa.gov/easey"

    api_key = next((os.getenv(key) for key in api_key_names if os.getenv(key)), None)
    headers = {"accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    request_params: dict[str, str] = {
        "type": "json",
        **(params or {}),
    }
    if area_nm and area_nm.strip():
        request_params["areaNm"] = area_nm.strip()

    rows: list[dict[str, Any]] = []
    payload: Any | None = None
    try:
        response = requests.get(api_url, params=request_params, headers=headers, timeout=20)
        _raise_for_http_error(response, context=f"{dataset_name} at {api_url}")
        payload = response.json()
        rows = extract_rows(payload)
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to parse real {dataset_name} data from '{api_url}'.") from exc

    if not rows:
        raise ValueError(f"No rows found in real {dataset_name} response from '{api_url}'.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{dataset_name}_raw.csv"
    json_path = output_dir / f"{dataset_name}_raw.json"

    append_rows_to_csv(csv_path, rows)
    append_rows_to_json(json_path, rows)

    return csv_path


def fetch_campd_data(
    api_url: str,
    output_dir: Path,
    params: dict[str, str] | None = None,
    area_nm: str | None = None,
    records: int = 48,
) -> Path:
    """Fetch a CAMPD dataset into a RAW file set."""
    return _fetch_epa_dataset(
        api_url=api_url,
        output_dir=output_dir,
        dataset_name="campd",
        api_key_names=("CAMPD_API_KEY", "EPA_API_KEY", "CAMD_API_KEY", "EPA_CAMD_API_KEY"),
        params=params,
        area_nm=area_nm,
        records=records,
    )


def fetch_ecmps_data(
    api_url: str,
    output_dir: Path,
    params: dict[str, str] | None = None,
    area_nm: str | None = None,
    records: int = 48,
) -> Path:
    """Fetch an ECMPS dataset into a RAW file set."""
    return _fetch_epa_dataset(
        api_url=api_url,
        output_dir=output_dir,
        dataset_name="ecmps",
        api_key_names=("ECMPS_API_KEY", "EPA_API_KEY", "CAMD_API_KEY", "EPA_CAMD_API_KEY"),
        params=params,
        area_nm=area_nm,
        records=records,
    )


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    """Best-effort extraction of list-like records from a JSON API response."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        raise ValueError(f"Unsupported payload type: {type(payload).__name__}")

    for key in ("items", "data", "result", "response", "body", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = extract_rows(value)
            if nested:
                return nested

    if "response" in payload and isinstance(payload["response"], dict):
        body = payload["response"].get("body")
        if isinstance(body, dict):
            items = body.get("items") or body.get("item")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]

    raise ValueError("No list-like data rows found in payload.")


def _normalize_epa_parameter_unit(parameter_code: str | None) -> str:
    if not parameter_code:
        return ""
    normalized = str(parameter_code).upper()
    if normalized in {"NOXC", "SO2C", "HCLC", "HFC"}:
        return "ppm"
    if normalized in {"CO2C", "O2C", "H2O"}:
        return "%"
    if normalized == "HGC":
        return "ug/scm"
    return ""


def extract_epa_concentration_rows(payload: Any) -> list[dict[str, Any]]:
    """Flatten an EPA emissions export payload into long-format concentration rows."""
    if not isinstance(payload, dict):
        raise ValueError(f"Unsupported EPA payload type: {type(payload).__name__}")

    hourly_data = payload.get("hourlyOperatingData")
    if not isinstance(hourly_data, list):
        raise ValueError("No hourlyOperatingData[] array found in EPA export payload.")

    rows: list[dict[str, Any]] = []
    monitor_plan_id = payload.get("monitorPlanId") or payload.get("monitorPlanID") or ""
    oris_code = payload.get("orisCode")
    facility_name = payload.get("facilityName") or payload.get("facility_name") or ""
    year = payload.get("year")
    quarter = payload.get("quarter")

    for hour_block in hourly_data:
        if not isinstance(hour_block, dict):
            continue

        date = hour_block.get("date")
        hour = hour_block.get("hour")
        operating_time = hour_block.get("operatingTime")
        unit_id = hour_block.get("unitId")
        stack_pipe_id = hour_block.get("stackPipeId")
        values = hour_block.get("monitorHourlyValueData")
        if not isinstance(values, list):
            continue

        for entry in values:
            if not isinstance(entry, dict):
                continue

            parameter_code = entry.get("parameterCode")
            if not parameter_code:
                continue

            rows.append(
                {
                    "source": "EPA",
                    "facility_id": oris_code,
                    "facility_name": facility_name,
                    "monitor_plan_id": monitor_plan_id,
                    "unit_id": unit_id,
                    "stack_pipe_id": stack_pipe_id,
                    "date": date,
                    "hour": hour,
                    "parameter_code": parameter_code,
                    "unit": entry.get("unit") or _normalize_epa_parameter_unit(parameter_code),
                    "unadjusted_hourly_value": entry.get("unadjustedHourlyValue"),
                    "adjusted_hourly_value": entry.get("adjustedHourlyValue"),
                    "modc_code": entry.get("modcCode"),
                    "component_id": entry.get("componentId"),
                    "monitoring_system_id": entry.get("monitoringSystemId"),
                    "operating_time": operating_time,
                    "year": year,
                    "quarter": quarter,
                    "reporting_period": f"{year}-Q{quarter}" if year is not None and quarter is not None else None,
                }
            )

    return rows


def fetch_epa_emissions_export(
    api_url: str,
    output_dir: Path,
    monitor_plan_id: str,
    year: int,
    quarter: int,
    reported_values_only: bool = True,
) -> Path:
    """Fetch a live EPA emissions export by monitorPlanId and save the flattened rows."""
    if not api_url:
        api_url = "https://api.epa.gov/easey/emissions-mgmt/emissions/export"

    api_key = next((os.getenv(key) for key in EPA_API_ENV_KEYS if os.getenv(key)), None)
    headers = {"accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    params: dict[str, str] = {
        "monitorPlanId": str(monitor_plan_id),
        "year": str(year),
        "quarter": str(quarter),
        "reportedValuesOnly": "true" if reported_values_only else "false",
    }

    response = requests.get(api_url, params=params, headers=headers, timeout=60)
    response.raise_for_status()
    payload = response.json()
    rows = extract_epa_concentration_rows(payload)
    for row in rows:
        row["monitor_plan_id"] = str(monitor_plan_id)
    if not rows:
        raise ValueError(f"No EPA concentration rows found for monitorPlanId '{monitor_plan_id}' and quarter {year}Q{quarter}.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"epa_emissions_{monitor_plan_id}_{year}q{quarter}.csv"
    json_path = output_dir / f"epa_emissions_{monitor_plan_id}_{year}q{quarter}.json"

    append_rows_to_csv(csv_path, rows)
    append_rows_to_json(json_path, rows)

    return csv_path


EPA_EASEY_URL = "https://api.epa.gov/easey"


def list_active_monitor_plan_ids(batch_size: int = 50) -> list[str]:
    """Return every active monitorPlanId (all facilities) via facilities-mgmt + monitor-plan-mgmt."""
    api_key = next((os.getenv(key) for key in EPA_API_ENV_KEYS if os.getenv(key)), None)
    headers = {"accept": "application/json", **({"x-api-key": api_key} if api_key else {})}

    response = requests.get(f"{EPA_EASEY_URL}/facilities-mgmt/facilities", headers=headers, timeout=60)
    response.raise_for_status()
    oris_codes = [str(item["facilityId"]) for item in response.json()["items"]]

    plan_ids: list[str] = []
    for i in range(0, len(oris_codes), batch_size):
        response = requests.get(
            f"{EPA_EASEY_URL}/monitor-plan-mgmt/configurations",
            params={"orisCodes": "|".join(oris_codes[i : i + batch_size])},
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        plan_ids.extend(item["id"] for item in response.json()["items"] if item.get("active"))
    return plan_ids


def fetch_campd_apportioned_hourly(output_dir: Path, oris_code: int | str, year: int, quarter: int) -> Path:
    """Fetch CAMPD hourly apportioned emissions (mass/rate/load per unit) for one facility-quarter."""
    api_key = next((os.getenv(key) for key in EPA_API_ENV_KEYS + ("CAMPD_API_KEY",) if os.getenv(key)), None)
    headers = {"accept": "application/json", **({"x-api-key": api_key} if api_key else {})}
    start_month = 3 * (quarter - 1) + 1
    end_day = (date(year + (quarter == 4), quarter * 3 % 12 + 1, 1) - timedelta(days=1)).day
    params = {
        "beginDate": f"{year}-{start_month:02d}-01",
        "endDate": f"{year}-{start_month + 2:02d}-{end_day:02d}",
        "facilityId": str(oris_code),
    }
    response = requests.get(f"{EPA_EASEY_URL}/streaming-services/emissions/apportioned/hourly", params=params, headers=headers, timeout=120)
    response.raise_for_status()
    rows = extract_rows(response.json())
    if not rows:
        raise ValueError(f"No CAMPD rows for orisCode {oris_code} {year}Q{quarter}.")

    output_dir = Path(output_dir)
    csv_path = output_dir / f"campd_apportioned_{oris_code}_{year}q{quarter}.csv"
    append_rows_to_csv(csv_path, rows)
    append_rows_to_json(output_dir / f"campd_apportioned_{oris_code}_{year}q{quarter}.json", rows)
    return csv_path


def collect_epa_all(output_dir: Path, quarters: Iterable[tuple[int, int]]) -> tuple[int, list[str]]:
    """Export every active plan for each (year, quarter). Returns (saved_count, failed_descriptions).

    Plans with no rows in a quarter are skipped; other errors are collected, not raised.
    """
    saved = 0
    failures: list[str] = []
    for plan_id in list_active_monitor_plan_ids():
        for year, quarter in quarters:
            try:
                fetch_epa_emissions_export(
                    api_url="",
                    output_dir=output_dir,
                    monitor_plan_id=plan_id,
                    year=year,
                    quarter=quarter,
                )
                saved += 1
            except ValueError:
                continue  # no concentration rows for this plan/quarter
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    continue  # no emissions report for this plan/quarter
                failures.append(f"{plan_id} {year}Q{quarter}: {exc}")
            except Exception as exc:
                failures.append(f"{plan_id} {year}Q{quarter}: {exc}")
    return saved, failures


def fetch_epa_camd(
    api_url: str,
    output_dir: Path,
    params: dict[str, str] | None = None,
    area_nm: str | None = None,
) -> Path:
    """Fetch EPA CAMD/ECMPS-like JSON records and save them cumulatively."""
    if not api_url:
        api_url = os.getenv("EPA_API_URL") or "https://api.epa.gov/easey"

    parsed = urlparse(api_url)
    query = parse_qs(parsed.query)
    monitor_plan_id = (query.get("monitorPlanId") or [None])[0]
    year = (query.get("year") or [None])[0]
    quarter = (query.get("quarter") or [None])[0]

    if parsed.path.endswith("/emissions/export") and monitor_plan_id and year and quarter:
        return fetch_epa_emissions_export(
            api_url=f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            output_dir=output_dir,
            monitor_plan_id=monitor_plan_id,
            year=int(year),
            quarter=int(quarter),
            reported_values_only=(query.get("reportedValuesOnly", ["true"])[0].lower() != "false"),
        )

    api_key = next((os.getenv(key) for key in EPA_API_ENV_KEYS if os.getenv(key)), None)
    headers = {"accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    request_params: dict[str, str] = {
        "type": "json",
        **(params or {}),
    }
    if area_nm and area_nm.strip():
        request_params["areaNm"] = area_nm.strip()

    response = requests.get(api_url, params=request_params, headers=headers, timeout=30)
    response.raise_for_status()

    payload = response.json()
    rows = extract_rows(payload)
    if not rows:
        raise ValueError(f"No EPA CAMD rows found at '{api_url}'.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "stack_epa_raw.csv"
    json_path = output_dir / "stack_epa_raw.json"

    append_rows_to_csv(csv_path, rows)
    append_rows_to_json(json_path, rows)

    return csv_path


def fetch_data_go_kr(
    api_url: str,
    output_dir: Path,
    params: dict[str, str] | None = None,
    area_nm: str | None = None,
    page_size: int = 1000,
) -> Path:
    """Fetch JSON rows from a public data.go.kr endpoint and save them as CSV."""
    api_key = os.getenv("DATA_GO_KR_KEY")
    if not api_key:
        raise RuntimeError(
            "DATA_GO_KR_KEY is not set. Add your public API key to the environment before requesting data.go.kr."
        )

    request_params: dict[str, str] = {
        "serviceKey": api_key,
        "type": "json",
        "pageNo": "1",
        "numOfRows": str(page_size),
        **(params or {}),
    }
    if area_nm and area_nm.strip():
        request_params["areaNm"] = area_nm.strip()

    rows: list[dict[str, Any]] = []
    total_count: int | None = None
    page_no = 1
    while True:
        request_params["pageNo"] = str(page_no)
        response = requests.get(api_url, params=request_params, timeout=30)
        response.raise_for_status()

        payload = response.json()
        body = payload.get("response", {}).get("body", {})
        items = body.get("items", [])
        if isinstance(items, dict):
            items = [items]

        page_rows = [item for item in items if isinstance(item, dict)]
        if not page_rows:
            break

        rows.extend(page_rows)

        if total_count is None:
            total_count = int(body.get("totalCount", len(rows)))

        if len(rows) >= total_count or len(page_rows) < page_size:
            break

        page_no += 1
        if page_no > 100:
            break

    if not rows:
        raise ValueError("Fetched payload did not contain any rows.")

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "public_monitoring_raw.csv"
    json_path = output_dir / "public_monitoring_raw.json"

    append_rows_to_csv(csv_path, rows)
    append_rows_to_json(json_path, rows)

    return csv_path


def _record_identity(row: dict[str, Any]) -> tuple[str, ...]:
    if "facilityId" in row and "unitId" in row and "hour" in row:  # CAMPD apportioned hourly
        return tuple(str(row.get(k) or "") for k in ("facilityId", "unitId", "date", "hour"))
    if row.get("source") == "EPA" and row.get("parameter_code"):
        keys = ("facility_id", "monitor_plan_id", "unit_id", "stack_pipe_id", "date", "hour", "parameter_code", "component_id")
        return tuple(str(row.get(k) or "") for k in keys)
    area = str(row.get("area_nm") or row.get("areaNm") or "")
    facility = str(row.get("fact_manage_nm") or row.get("facility_name") or "")
    stack_code = str(row.get("stack_code") or row.get("stackCode") or "")
    timestamp = str(row.get("mesure_dt") or row.get("measure_dt") or row.get("timestamp") or "")
    if not any([area, facility, stack_code, timestamp]):
        return tuple(sorted(str(value) for value in row.values()))
    return (area, facility, stack_code, timestamp)


def append_rows_to_csv(csv_path: Path | str, rows: Iterable[dict[str, Any]]) -> Path:
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    rows_list = list(rows)
    if not rows_list:
        return csv_path

    existing_rows: list[dict[str, Any]] = []
    if csv_path.exists() and csv_path.stat().st_size > 0:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames:
                existing_rows = list(reader)

    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in existing_rows + rows_list:
        merged[_record_identity(row)] = row

    final_rows = list(merged.values())
    final_rows.sort(key=lambda row: str(row.get("mesure_dt") or row.get("timestamp") or ""))

    fieldnames = list(dict.fromkeys(key for row in final_rows for key in row.keys()))
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)

    return csv_path


def append_rows_to_json(json_path: Path | str, rows: Iterable[dict[str, Any]]) -> Path:
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    rows_list = list(rows)
    if not rows_list:
        return json_path

    existing_rows: list[dict[str, Any]] = []
    if json_path.exists() and json_path.stat().st_size > 0:
        with json_path.open("r", encoding="utf-8") as fh:
            try:
                existing_rows = json.load(fh)
            except json.JSONDecodeError:
                existing_rows = []

    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in existing_rows + rows_list:
        merged[_record_identity(row)] = row

    final_rows = sorted(
        merged.values(),
        key=lambda row: str(row.get("mesure_dt") or row.get("timestamp") or ""),
    )

    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(final_rows, fh, ensure_ascii=False, indent=2)

    return json_path


def collect_data(
    source: str,
    output_dir: Path,
    records: int,
    api_url: str,
    area_nm: str | None = None,
    page_size: int = 1000,
) -> Path:
    output_dir = Path(output_dir)

    if source == "data-go-kr":
        if not api_url:
            raise ValueError("--api-url is required when source is data-go-kr.")
        return fetch_data_go_kr(
            api_url=api_url,
            output_dir=output_dir,
            area_nm=area_nm,
            page_size=page_size,
        )

    if source == "epa":
        return fetch_epa_camd(api_url=api_url, output_dir=output_dir, params=None, area_nm=area_nm)

    if source == "campd":
        return fetch_campd_data(
            api_url=api_url,
            output_dir=output_dir,
            params=None,
            area_nm=area_nm,
            records=records,
        )

    if source == "ecmps":
        return fetch_ecmps_data(
            api_url=api_url,
            output_dir=output_dir,
            params=None,
            area_nm=area_nm,
            records=records,
        )

    raise ValueError(f"Unsupported source '{source}'.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect stack monitoring data into a raw dataset.")
    parser.add_argument(
        "--source",
        choices=["data-go-kr", "epa", "campd", "ecmps"],
        default="campd",
        help="Collect from a public data.go.kr endpoint or an EPA CAMPD/ECMPS endpoint.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory to save raw CSV/JSON outputs.",
    )
    parser.add_argument(
        "--records",
        type=int,
        default=48,
        help="Number of records to request when a target API supports paging or row limits.",
    )
    parser.add_argument(
        "--api-url",
        default="",
        help="Public data source URL. Required with --source data-go-kr or --source epa. For emissions export, this can be the base API endpoint.",
    )
    parser.add_argument(
        "--monitor-plan-id",
        default="",
        help="EPA monitorPlanId used for direct emissions export requests.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Year for direct EPA emissions export requests.",
    )
    parser.add_argument(
        "--quarter",
        type=int,
        choices=[1, 2, 3, 4],
        default=None,
        help="Quarter (1-4) for direct EPA emissions export requests.",
    )
    parser.add_argument(
        "--area-nm",
        default="",
        help="Optional city/region filter, such as '울산'. Leave blank for nationwide data.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        help="Page size to use with the public API. Default is 1000.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    api_url = args.api_url
    if args.source == "epa" and not api_url:
        api_url = "https://api.epa.gov/easey/emissions-mgmt/emissions/export"

    if (
        args.source == "epa"
        and args.monitor_plan_id
        and args.year is not None
        and args.quarter is not None
    ):
        output_path = fetch_epa_emissions_export(
            api_url=api_url,
            output_dir=args.output_dir,
            monitor_plan_id=args.monitor_plan_id,
            year=args.year,
            quarter=args.quarter,
                    )
        print(f"Saved raw data: {output_path}")
        return

    output_path = collect_data(
        source=args.source,
        output_dir=args.output_dir,
        records=args.records,
        api_url=api_url,
        area_nm=args.area_nm,
        page_size=args.page_size,
    )
    print(f"Saved raw data: {output_path}")


if __name__ == "__main__":
    main()
