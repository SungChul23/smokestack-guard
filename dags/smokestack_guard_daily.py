from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from smokestack_guard.data.collector import collect_epa_all

load_dotenv(ROOT_DIR / ".env")

RAW_DIR = ROOT_DIR / "data" / "raw"


def _collect_epa_raw() -> None:
    # Hourly data is reported quarterly, so also refresh the previous quarter.
    today = date.today()
    quarter = (today.month - 1) // 3 + 1
    previous = (today.year, quarter - 1) if quarter > 1 else (today.year - 1, 4)
    saved, failures = collect_epa_all(RAW_DIR, [previous, (today.year, quarter)])
    if failures:
        raise RuntimeError(f"{saved} saved, {len(failures)} failed; first: {failures[:3]}")


with DAG(
    dag_id="smokestack_guard_epa_daily",
    description="Export hourly concentration data for all active EPA monitoring plans once a day.",
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["smokestack-guard", "epa"],
) as dag:
    PythonOperator(task_id="collect_epa_raw", python_callable=_collect_epa_raw)
