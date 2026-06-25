import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.approval import (
    action_fingerprint,
    approve_fingerprint,
    filter_unapproved_actions,
    register_pending_approvals,
)
from core.audit_trail import AuditTrail, append_audit_record, summarize_audit
from core import audit_trail as audit_module
from core.mcp_action import MCPAction
from core.outage import poll_interval_seconds, should_notify
from core.secrets import load_secrets_from_files


class AuditTrailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(audit_module, "AUDIT_ROOT", Path(self.tmp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_append_and_summarize(self):
        append_audit_record("c1", {"event": "mcp_call", "tool": "pods_list"})
        append_audit_record("c1", {"event": "policy_check", "policy_passed": False})
        summary = summarize_audit("c1")
        self.assertEqual(summary["total_events"], 2)
        self.assertEqual(summary["mcp_calls"], 1)
        self.assertEqual(summary["policy_blocks"], 1)


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(
            __import__("core.approval", fromlist=["approval"]),
            "APPROVAL_ROOT",
            Path(self.tmp.name),
        )
        # patch path in approval module
        import core.approval as approval_mod
        self.approval_patch = mock.patch.object(approval_mod, "APPROVAL_ROOT", Path(self.tmp.name))
        self.approval_patch.start()

    def tearDown(self):
        self.approval_patch.stop()
        self.tmp.cleanup()

    def test_approve_flow(self):
        action = MCPAction(tool="pods_exec", arguments={"command": ["dig", "x"]}, label="dig")
        config = {"approval": {"enabled": True, "required_tools": ["pods_exec"]}}
        pending = register_pending_approvals("99", [action], comment_id=1)
        fp = pending[0]["fingerprint"]
        self.assertEqual(fp, action_fingerprint(action))
        self.assertEqual(len(filter_unapproved_actions("99", [action], config)), 1)
        self.assertTrue(approve_fingerprint("99", fp, approved_by="sre"))
        self.assertEqual(len(filter_unapproved_actions("99", [action], config)), 0)


class SecretsTests(unittest.TestCase):
    def test_load_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret_path = Path(tmp) / "key"
            secret_path.write_text("secret-value", encoding="utf-8")
            env_key = "TEST_SECRET_LOAD_XYZ"
            import os
            os.environ.pop(env_key, None)
            load_secrets_from_files({
                "secrets": {"env_from_files": {env_key: str(secret_path)}},
            })
            self.assertEqual(os.environ.get(env_key), "secret-value")
            os.environ.pop(env_key, None)


class OutageTests(unittest.TestCase):
    def test_poll_interval(self):
        normal = poll_interval_seconds({"polling": {"interval_seconds": 10}, "outage": {"enabled": False}})
        outage = poll_interval_seconds({"polling": {"interval_seconds": 10}, "outage": {"enabled": True, "interval_seconds": 3}})
        self.assertEqual(normal, 10)
        self.assertEqual(outage, 3)

    def test_should_notify_requires_webhook(self):
        cfg = {
            "outage": {
                "enabled": True,
                "notify_on": ["reply_posted"],
            }
        }
        self.assertFalse(should_notify(cfg, "reply_posted"))


if __name__ == "__main__":
    unittest.main()
