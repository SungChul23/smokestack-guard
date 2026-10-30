import unittest
from pathlib import Path
from unittest import mock

from smokestack_guard.data.collector import _record_identity, build_parser, collect_epa_all, extract_rows


class CollectorTests(unittest.TestCase):
    def test_build_parser_accepts_area_nm(self):
        parser = build_parser()
        args = parser.parse_args([
            "--source",
            "data-go-kr",
            "--area-nm",
            "울산",
            "--api-url",
            "http://example.com/api",
        ])
        self.assertEqual(args.area_nm, "울산")

    def test_extract_rows_handles_data_go_kr_payload(self):
        payload = {
            "response": {
                "body": {
                    "items": [
                        {"area_nm": "서울특별시", "mesure_dt": "2026-10-29 10:00"}
                    ]
                }
            }
        }
        rows = extract_rows(payload)
        self.assertEqual(rows[0]["area_nm"], "서울특별시")

    def test_epa_rows_with_different_hours_are_distinct(self):
        base = {"source": "EPA", "facility_id": 1, "unit_id": "1", "date": "2026-01-01", "parameter_code": "NOXC"}
        self.assertNotEqual(_record_identity({**base, "hour": 0}), _record_identity({**base, "hour": 1}))
        self.assertNotEqual(_record_identity(base), _record_identity({**base, "parameter_code": "SO2C"}))

    def test_collect_epa_all_skips_empty_and_collects_failures(self):
        def fake_export(**kw):
            if kw["monitor_plan_id"] == "empty":
                raise ValueError("no rows")
            if kw["monitor_plan_id"] == "bad":
                raise RuntimeError("boom")

        with mock.patch("smokestack_guard.data.collector.list_active_monitor_plan_ids", return_value=["ok", "empty", "bad"]),                 mock.patch("smokestack_guard.data.collector.fetch_epa_emissions_export", side_effect=fake_export):
            saved, failures = collect_epa_all(Path("."), [(2024, 3)])
        self.assertEqual(saved, 1)
        self.assertEqual(len(failures), 1)


if __name__ == "__main__":
    unittest.main()
