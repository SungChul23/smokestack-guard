from __future__ import annotations

from typing import Any, Iterable

import requests

EPA_CANDIDATE_URLS: tuple[str, ...] = (
    "https://campd.epa.gov",
    "https://api.epa.gov/easey",
    "https://api.epa.gov/easey/account",
    "https://api.epa.gov/easey/air-emissions",
    "https://api.epa.gov/easey/emissions",
    "https://api.epa.gov/easey/monitoring-plans",
)


def probe_epa_endpoints(
    api_key: str,
    urls: Iterable[str] | None = None,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    """Probe likely EPA endpoints and return detailed status information for each path."""
    url_list = list(urls) if urls is not None else list(EPA_CANDIDATE_URLS)
    headers = {"x-api-key": api_key, "accept": "application/json"}
    results: list[dict[str, Any]] = []

    for url in url_list:
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            results.append(
                {
                    "url": url,
                    "status_code": response.status_code,
                    "ok": 200 <= response.status_code < 300,
                    "content_type": response.headers.get("content-type"),
                    "snippet": response.text[:200],
                }
            )
        except requests.RequestException as exc:
            results.append({
                "url": url,
                "status_code": None,
                "ok": False,
                "content_type": None,
                "snippet": "",
                "error": str(exc),
            })

    return results
