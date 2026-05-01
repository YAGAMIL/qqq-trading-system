import unittest

from skill_check import safety_contract


class SkillCheckSafetyContractTests(unittest.TestCase):
    def test_safety_contract_reports_no_external_writes(self):
        result = safety_contract({"QQQ_LIVE_TRADING": "1"})

        self.assertTrue(result["ok"])
        self.assertFalse(result["real_order_submission"])
        self.assertFalse(result["gist_upload"])
        self.assertEqual(result["external_writes"], ["none"])
        self.assertIn("live_trader.py --submit-live-orders", result["live_order_requires"])
        self.assertTrue(result["live_order_env_opt_in"])

    def test_safety_contract_does_not_treat_env_opt_in_as_submission(self):
        result = safety_contract({})

        self.assertTrue(result["ok"])
        self.assertFalse(result["real_order_submission"])
        self.assertFalse(result["gist_upload"])
        self.assertFalse(result["live_order_env_opt_in"])


if __name__ == "__main__":
    unittest.main()
