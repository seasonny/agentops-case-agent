import tempfile
import unittest
from pathlib import Path

from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker
from core.policy_compiler import PolicyConfigError, compile_policy, load_compiled_policy


class PolicyCompilerTests(unittest.TestCase):
    def test_diagnostic_profile_allows_cluster_read(self):
        compiled = compile_policy()
        self.assertEqual(compiled.profile, "diagnostic")
        self.assertEqual(compiled.mode, "denylist")
        self.assertTrue(compiled.capabilities["cluster_read"])
        self.assertTrue(compiled.capabilities["must_gather"])
        self.assertNotIn("resources_list", compiled.blocked_tools)
        self.assertNotIn("oc_adm_must_gather", compiled.blocked_tools)

    def test_diagnostic_allows_must_gather_when_enabled(self):
        compiled = compile_policy()
        self.assertTrue(compiled.capabilities["must_gather"])

    def test_enterprise_allowlist_blocks_exec(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles = root / "profiles"
            profiles.mkdir()
            (profiles / "enterprise.yaml").write_text(
                (Path(__file__).resolve().parents[1] / "config/policy_profiles/enterprise.yaml").read_text(),
                encoding="utf-8",
            )
            policy = root / "policy.yaml"
            policy.write_text("profile: enterprise\nmode: allowlist\n", encoding="utf-8")
            cap_map = Path(__file__).resolve().parents[1] / "config/policy_capability_map.yaml"
            compiled = compile_policy(
                policy_path=policy,
                capability_map_path=cap_map,
                profiles_dir=profiles,
            )
            self.assertEqual(compiled.mode, "allowlist")
            self.assertIn("resources_list", compiled.allowed_tools or set())
            self.assertNotIn("pods_exec", compiled.allowed_tools or set())
            self.assertNotIn("exec_argv", compiled.allowed_tools or set())

    def test_capability_override_disables_host_diag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles = root / "profiles"
            profiles.mkdir()
            for name in ("diagnostic", "enterprise", "minimal"):
                src = Path(__file__).resolve().parents[1] / f"config/policy_profiles/{name}.yaml"
                (profiles / f"{name}.yaml").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            policy = root / "policy.yaml"
            policy.write_text(
                "profile: diagnostic\ncapabilities:\n  host_diag: false\n",
                encoding="utf-8",
            )
            cap_map = Path(__file__).resolve().parents[1] / "config/policy_capability_map.yaml"
            compiled = compile_policy(
                policy_path=policy,
                capability_map_path=cap_map,
                profiles_dir=profiles,
            )
            self.assertFalse(compiled.capabilities["host_diag"])
            self.assertIn("exec_argv", compiled.blocked_tools)

    def test_checker_allowlist_blocks_unknown_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles = root / "profiles"
            profiles.mkdir()
            (profiles / "minimal.yaml").write_text(
                (Path(__file__).resolve().parents[1] / "config/policy_profiles/minimal.yaml").read_text(),
                encoding="utf-8",
            )
            policy = root / "policy.yaml"
            policy.write_text("profile: minimal\nmode: allowlist\n", encoding="utf-8")
            cap_map = Path(__file__).resolve().parents[1] / "config/policy_capability_map.yaml"
            compiled = compile_policy(
                policy_path=policy,
                capability_map_path=cap_map,
                profiles_dir=profiles,
            )
            checker = MCPPolicyChecker(compiled=compiled)
            ok, reason = checker.check_action(
                MCPAction(tool="resources_list", arguments={})
            )
            self.assertFalse(ok)
            self.assertIn("allowlist", reason)


    def test_missing_policy_yaml_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "policy.yaml"
            with self.assertRaises(PolicyConfigError):
                load_compiled_policy(policy_path=missing)


if __name__ == "__main__":
    unittest.main()
