import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from smokestack_guard.data.collector import (
    collect_data,
    extract_epa_concentration_rows,
    fetch_campd_data,
)
from smokestack_guard.data.epa_probe import EPA_CANDIDATE_URLS, probe_epa_endpoints


class EpaProbeTests(unittest.TestCase):
    def test_probe_epa_endpoints_returns_result_per_url(self):
        class FakeResponse:
            status_code = 200
            headers = {"content-type": "application/json"}
            text = '{"ok": true}'

        with patch("smokestack_guard.data.epa_probe.requests.get", return_value=FakeResponse()):
            results = probe_epa_endpoints("dummy-key", urls=["https://test.example/one"])

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["status_code"], 200)

    def test_candidate_urls_are_declared(self):
        self.assertIn("https://campd.epa.gov", EPA_CANDIDATE_URLS)

    def test_collect_data_supports_epa_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("smokestack_guard.data.collector.fetch_epa_camd", return_value=Path(tmpdir) / "epa.csv") as mock_fetch:
                result = collect_data(
                    source="epa",
                    output_dir=Path(tmpdir),
                    records=0,
                    api_url="https://example.test/epa",
                )

        self.assertEqual(result, Path(tmpdir) / "epa.csv")
        mock_fetch.assert_called_once_with(api_url="https://example.test/epa", output_dir=Path(tmpdir), params=None, area_nm=None)

    def test_collect_data_supports_campd_and_ecmps_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("smokestack_guard.data.collector.fetch_campd_data", return_value=Path(tmpdir) / "campd.csv") as campd_fetch, \
                 patch("smokestack_guard.data.collector.fetch_ecmps_data", return_value=Path(tmpdir) / "ecmps.csv") as ecmps_fetch:
                campd_result = collect_data(
                    source="campd",
                    output_dir=Path(tmpdir),
                    records=0,
                    api_url="https://example.test/campd",
                )
                ecmps_result = collect_data(
                    source="ecmps",
                    output_dir=Path(tmpdir),
                    records=0,
                    api_url="https://example.test/ecmps",
                )

        self.assertEqual(campd_result, Path(tmpdir) / "campd.csv")
        self.assertEqual(ecmps_result, Path(tmpdir) / "ecmps.csv")
        campd_fetch.assert_called_once_with(api_url="https://example.test/campd", output_dir=Path(tmpdir), params=None, area_nm=None, records=0)
        ecmps_fetch.assert_called_once_with(api_url="https://example.test/ecmps", output_dir=Path(tmpdir), params=None, area_nm=None, records=0)

    def test_fetch_campd_data_raises_on_unauthorized_response(self):
        class FakeResponse:
            status_code = 403
            headers = {"content-type": "application/json"}
            text = '{"error":{"code":"API_KEY_UNAUTHORIZED","message":"bad key"}}'

            def raise_for_status(self):
                raise PermissionError("bad key")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("smokestack_guard.data.collector.requests.get", return_value=FakeResponse()):
                with self.assertRaises(PermissionError):
                    fetch_campd_data(
                        api_url="https://api.epa.gov/easey/camd-services/monitor-plans",
                        output_dir=Path(tmpdir),
                        records=2,
                    )

    def test_extract_epa_concentration_rows_handles_export_payload(self):
        payload = {
            "orisCode": 3,
            "monitorPlanId": "TWCORNEL5-123",
            "year": 2025,
            "quarter": 2,
            "hourlyOperatingData": [
                {
                    "date": "2025-04-13",
                    "hour": 13,
                    "operatingTime": 1.0,
                    "monitorHourlyValueData": [
                        {
                            "parameterCode": "SO2C",
                            "unadjustedHourlyValue": 2.3,
                            "adjustedHourlyValue": 2.6,
                            "modcCode": "01",
                            "componentId": "SD1",
                            "monitoringSystemId": "MS1",
                        },
                        {
                            "parameterCode": "NOXC",
                            "unadjustedHourlyValue": 157.0,
                            "adjustedHourlyValue": None,
                            "modcCode": "01",
                            "componentId": "NX1",
                            "monitoringSystemId": "MS1",
                        },
                    ],
                }
            ],
        }

        rows = extract_epa_concentration_rows(payload)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["parameter_code"], "SO2C")
        self.assertEqual(rows[0]["unadjusted_hourly_value"], 2.3)
        self.assertEqual(rows[1]["adjusted_hourly_value"], None)
        self.assertEqual(rows[1]["monitor_plan_id"], "TWCORNEL5-123")


if __name__ == "__main__":
    unittest.main()
