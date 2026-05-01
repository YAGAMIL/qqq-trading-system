from pathlib import Path
import tempfile
import unittest

from skill_check import env_readiness, runtime_artifacts, safety_guards
from state_store import default_state, write_state


class SkillCheckDiagnosticsTests(unittest.TestCase):
    def test_safety_guards_report_non_real_order_defaults(self):
        checks = safety_guards({})

        self.assertTrue(checks["ok"])
        self.assertTrue(checks["dry_run_default"])
        self.assertTrue(checks["live_requires_env_opt_in"])
        self.assertTrue(checks["live_order_submission_requires_submit_flag"])
        self.assertTrue(checks["gist_upload_requires_confirm_upload"])
        self.assertTrue(checks["notification_disabled_without_target"])

    def test_env_readiness_redacts_credential_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("LONGBRIDGE_APP_KEY=secret\n", encoding="utf-8")
            checks = env_readiness(
                env_file,
                {
                    "LONGBRIDGE_APP_KEY": "secret",
                    "LONGBRIDGE_APP_SECRET": "",
                    "LONGBRIDGE_ACCESS_TOKEN": "token",
                    "QQQ_LIVE_TRADING": "0",
                    "GIST_ID": "gist",
                    "GITHUB_TOKEN": "",
                },
            )

        self.assertTrue(checks["ok"])
        self.assertTrue(checks["env_file_exists"])
        self.assertEqual(
            checks["longbridge_credentials"],
            {
                "LONGBRIDGE_APP_KEY": True,
                "LONGBRIDGE_APP_SECRET": False,
                "LONGBRIDGE_ACCESS_TOKEN": True,
            },
        )
        self.assertNotIn("secret", str(checks))
        self.assertFalse(checks["gist_configured"])

    def test_runtime_artifacts_are_inspected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = default_state()
            state["running"] = True
            state["updated"] = "2026-05-01T09:35:00-04:00"
            write_state(state, root / "state.json")
            (root / "today.csv").write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
            (root / "records").mkdir()
            (root / "records" / "2026-05-01.json").write_text("[]", encoding="utf-8")
            (root / ".live_trader.lock").write_text('{"pid": 123}', encoding="utf-8")

            checks = runtime_artifacts(
                root / "state.json",
                root / "today.csv",
                root / "records",
                root / ".live_trader.lock",
            )

        self.assertTrue(checks["ok"])
        self.assertTrue(checks["state_exists"])
        self.assertTrue(checks["state_running"])
        self.assertEqual(checks["state_updated"], "2026-05-01T09:35:00-04:00")
        self.assertTrue(checks["today_csv_exists"])
        self.assertEqual(checks["record_files"], 1)
        self.assertTrue(checks["lock_exists"])


if __name__ == "__main__":
    unittest.main()
