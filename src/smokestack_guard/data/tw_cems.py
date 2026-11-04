"""Taiwan MOENV CEMS (AQX_P_186 15-min / AQX_P_187 1-hour) -> bronze, response bodies saved byte-for-byte.

Layout: <out>/<dataset>/cno=<plant>/since=YYYY-MM-DD/offset=NNNNNNN.json (m_time is Taiwan local time), plus an
empty _done file once the plant is complete. Re-running skips finished plants, so an interrupted run just resumes;
to top up later, run again with a newer --start.
The plant list (cno, one per line) comes from --cno-file; the API cannot list plants itself.
"""
from __future__ import annotations

import argparse
import os
import ssl
import time
from datetime import date
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from dotenv import load_dotenv

load_dotenv()

URL = "https://data.moenv.gov.tw/api/v2/{}"
PAGE = 1000


def api_key() -> str:
    # the stored key may contain a stray space; whitespace never belongs in the key
    return "".join(os.environ["MOENV_API_KEY"].split())


class _LenientTLS(HTTPAdapter):
    """Python 3.13+ rejects the MOENV certificate (no Subject Key Identifier) under strict X.509 checks.
    Certificate chain and hostname are still verified; only the strict-profile flag is dropped."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        super().init_poolmanager(*args, ssl_context=ctx, **kwargs)


def fetch_page(session: requests.Session, dataset: str, cno: str, since: date, offset: int) -> bytes:
    # The API only honours "m_time GR <date>" (day granularity; LE/EQ/GE on m_time return nothing), and a deep
    # offset over the whole country takes minutes. Filtering by one plant (cno) keeps every offset fast.
    params = {
        "api_key": api_key(),
        "format": "json",
        "limit": PAGE,
        "offset": offset,
        "sort": "m_time asc",
        "filters": f"cno,EQ,{cno}|m_time,GR,{since}",
    }
    last = "no attempt"
    for attempt in range(8):
        try:
            r = session.get(URL.format(dataset), params=params, timeout=180)
        except requests.RequestException as e:
            # the exception text carries the request URL, which contains the key; timeouts and drops are retried
            last = type(e).__name__
            time.sleep(30 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r.content
        last = f"HTTP {r.status_code}"
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(30 * (attempt + 1))
            continue
        break
    raise RuntimeError(f"{dataset} {cno} offset {offset}: gave up ({last})")


def collect_cno(session: requests.Session, dataset: str, cno: str, since: date, out: Path) -> int:
    folder = out / dataset / f"cno={cno}" / f"since={since}"
    if (folder / "_done").exists():
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    offset = rows = 0
    while True:
        body = fetch_page(session, dataset, cno, since, offset)
        n = body.count(b'"m_time"')
        if n:
            (folder / f"offset={offset:07d}.json").write_bytes(body)
        rows += n
        if n < PAGE:
            break
        offset += PAGE
    (folder / "_done").touch()
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="Taiwan CEMS API -> bronze (raw JSON pages)")
    p.add_argument("--dataset", default="aqx_p_186", choices=["aqx_p_186", "aqx_p_187"])
    p.add_argument("--start", type=date.fromisoformat, default=date(2026, 7, 3))
    p.add_argument("--cno-file", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("data/raw/tw_cems"))
    a = p.parse_args()
    cnos = sorted(set(a.cno_file.read_text(encoding="utf-8").split()))
    with requests.Session() as s:
        s.mount("https://", _LenientTLS())
        for i, cno in enumerate(cnos, 1):
            try:
                rows = collect_cno(s, a.dataset, cno, a.start, a.out)
            except RuntimeError as e:
                # no _done marker is written, so the next run retries this plant
                print(f"{a.dataset} {i}/{len(cnos)} {cno} FAILED {e}", flush=True)
                continue
            print(f"{a.dataset} {i}/{len(cnos)} {cno} rows {rows}", flush=True)


if __name__ == "__main__":
    main()
