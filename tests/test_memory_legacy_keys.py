import unittest

from core.memory import _has_legacy_handled_keys


class TestLegacyHandledKeys(unittest.TestCase):
    def test_pid_keys_are_not_legacy(self):
        keys = [
            "pid:a0aHn00000YqkcnIAB:b85c8b13c5ef7d288f895f227522680e7a6112aee9d4e6e04484f9232f7b4d83",
            "ts:2026-07-08T02:05:49Z:abc123",
            "nots:1:def456",
        ]
        self.assertFalse(_has_legacy_handled_keys(keys))

    def test_mcp_positional_keys_are_legacy(self):
        keys = ["27:abcd1234", "pid:ok:hash"]
        self.assertTrue(_has_legacy_handled_keys(keys))


if __name__ == "__main__":
    unittest.main()
