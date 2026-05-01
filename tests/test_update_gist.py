import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from update_gist import collect_records, main


class UpdateGistSafetyTests(unittest.TestCase):
    def test_collect_records_returns_named_json_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2026-05-01.json").write_text('[{"symbol":"QQQ"}]', encoding="utf-8")
            (root / "notes.txt").write_text("ignore", encoding="utf-8")

            files = collect_records(root)

        self.assertEqual(files, {"2026-05-01.json": '[{"symbol":"QQQ"}]'})

    def test_main_dry_run_does_not_call_external_upload_without_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            records.mkdir()
            (records / "2026-05-01.json").write_text(json.dumps([{"symbol": "QQQ"}]), encoding="utf-8")
            argv = ["update_gist.py", "--records", str(records), "--gist-id", "gist", "--token", "token"]
            with patch.object(sys, "argv", argv), patch("update_gist.update_gist") as upload:
                exit_code = main()

        self.assertEqual(exit_code, 0)
        upload.assert_not_called()

    def test_cli_dry_run_is_non_uploading_and_successful(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            records.mkdir()
            (records / "2026-05-01.json").write_text("[]", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, "update_gist.py", "--records", str(records), "--gist-id", "gist", "--token", "token"],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Dry-run:", result.stdout)
        self.assertIn("--confirm-upload", result.stdout)


if __name__ == "__main__":
    unittest.main()
