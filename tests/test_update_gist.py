import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import update_gist


class UpdateGistSafetyTests(unittest.TestCase):
    def test_main_dry_run_does_not_call_github_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = Path(tmp) / "records"
            records.mkdir()
            (records / "2026-05-01.json").write_text('{"trades": []}', encoding="utf-8")

            argv = ["update_gist.py", "--records", str(records)]
            with (
                patch.object(sys, "argv", argv),
                patch("update_gist.urllib.request.urlopen") as urlopen,
                patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                exit_code = update_gist.main()

        self.assertEqual(exit_code, 0)
        urlopen.assert_not_called()
        self.assertIn("Dry-run: 1 files ready", stdout.getvalue())
        self.assertIn("--confirm-upload", stdout.getvalue())

    def test_confirm_upload_requires_credentials_before_network_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = Path(tmp) / "records"
            records.mkdir()
            (records / "2026-05-01.json").write_text('{"trades": []}', encoding="utf-8")

            argv = ["update_gist.py", "--records", str(records), "--confirm-upload"]
            with (
                patch.object(sys, "argv", argv),
                patch("update_gist.urllib.request.urlopen") as urlopen,
                self.assertRaisesRegex(SystemExit, "GIST_ID and GITHUB_TOKEN are required"),
            ):
                update_gist.main()

        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
