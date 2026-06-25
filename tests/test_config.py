import os
import unittest
from unittest import mock

from core.config import default_config, load_config
from core.dev_mode import is_dev_mode
from core.mcp_discovery import build_auto_mcp_providers
from core.trigger import TriggerConfig


class DefaultConfigTests(unittest.TestCase):
    def test_production_is_default(self):
        cfg = default_config()
        self.assertEqual(cfg["trigger"]["mode"], "production")
        self.assertTrue(cfg["trigger"]["ignore_customer_comments"])

    def test_minimal_user_config_merges(self):
        with mock.patch("core.config.CONFIG_FILE") as mock_path:
            mock_path.exists.return_value = True
            with mock.patch("core.config._load_json_file") as load_json:
                load_json.side_effect = lambda p: (
                    {
                        "case_id": "99999",
                        "llm": {"provider": "gemini", "model": "test-model"},
                    }
                    if p == mock_path
                    else None
                )
                with mock.patch("core.config.LOCAL_CONFIG_FILE") as local_path:
                    local_path.exists.return_value = False
                    with mock.patch("core.config.apply_mcp_auto_discovery", side_effect=lambda c: c):
                        cfg = load_config()
        self.assertEqual(cfg["case_id"], "99999")
        self.assertEqual(cfg["llm"]["model"], "test-model")
        self.assertEqual(cfg["trigger"]["mode"], "production")
        self.assertTrue(cfg["guardrails"]["reply"]["block_ungrounded_execution_output"])


class DevModeTests(unittest.TestCase):
    def test_dev_mode_env(self):
        with mock.patch.dict(os.environ, {"AGENT_DEV_MODE": "1"}):
            self.assertTrue(is_dev_mode())
            trigger = TriggerConfig({})
            self.assertEqual(trigger.mode, "demo")

    def test_production_without_dev(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("AGENT_DEV_MODE", None)
            trigger = TriggerConfig({})
            self.assertEqual(trigger.mode, "production")


class McpDiscoveryTests(unittest.TestCase):
    def test_fills_exec_from_path(self):
        with mock.patch("core.mcp_discovery._resolve_binary") as resolve:
            resolve.side_effect = lambda env, candidates: (
                "/usr/bin/mcp-shell-server" if "mcp-shell" in candidates[0] else None
            )
            providers = build_auto_mcp_providers({})
        self.assertIn("exec", providers)
        self.assertEqual(providers["exec"]["command"], "/usr/bin/mcp-shell-server")

    def test_default_platform_uses_npx_when_no_path(self):
        with mock.patch("core.mcp_discovery._resolve_binary", return_value=None):
            providers = build_auto_mcp_providers({})
        self.assertIn("platform", providers)
        self.assertEqual(providers["platform"]["command"], "npx")
        self.assertIn("rh-tam-kubernetes-mcp-server", providers["platform"]["args"][1])

    def test_explicit_platform_not_overridden(self):
        custom = {
            "mcp_providers": {
                "platform": {"command": "/opt/custom-mcp", "args": ["--foo"]},
            }
        }
        with mock.patch("core.mcp_discovery._resolve_binary", return_value=None):
            providers = build_auto_mcp_providers(custom)
        self.assertEqual(providers["platform"]["command"], "/opt/custom-mcp")


if __name__ == "__main__":
    unittest.main()
