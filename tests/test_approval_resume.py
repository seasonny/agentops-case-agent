import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest import mock

from core.approval import (
    RESUME_DONE,
    RESUME_PENDING,
    RESUME_DENIED,
    action_fingerprint,
    actions_covered_by_resume_grant,
    approve_fingerprint,
    approve_latest,
    approve_token,
    deny_latest,
    deny_token,
    build_correlation_id,
    format_approval_required_reply,
    list_resumable_approved,
    load_approvals,
    mark_pending_resumed,
    persist_workflow_context_from_memory,
    register_pending_approvals,
)
from core.audit_trail import AuditTrail, load_audit_records
from core import audit_trail as audit_module
from core import approval as approval_module
from core.mcp_action import MCPAction
from workflow.runner import (
    _build_resume_invoke_state,
    try_resume_approved_workflows,
)


class ApprovalStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.approval_patch = mock.patch.object(
            approval_module, "APPROVAL_ROOT", self.root
        )
        self.approval_patch.start()

    def tearDown(self):
        self.approval_patch.stop()
        self.tmp.cleanup()

    def test_pending_entry_has_resume_metadata(self):
        action = MCPAction(tool="pods_exec", arguments={"command": ["dig", "x"]}, label="dig")
        config = {"approval": {"enabled": True, "ttl_hours": 12}}
        pending = register_pending_approvals("case-1", [action], comment_id=42, config=config)
        entry = pending[0]
        self.assertTrue(entry.get("pending_id", "").startswith("pend-"))
        self.assertEqual(entry.get("workflow_id"), entry.get("pending_id"))
        self.assertEqual(
            entry.get("correlation_id"),
            build_correlation_id("case-1", 42, entry["fingerprint"]),
        )
        self.assertTrue(entry.get("expires_at"))

    def test_approve_moves_to_resumable_queue(self):
        action = MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather")
        config = {"approval": {"enabled": True, "required_tools": ["oc_adm_must_gather"]}}
        pending = register_pending_approvals("case-2", [action], comment_id=7, config=config)
        memory = {
            "case_id": "case-2",
            "latest_msg": "please must-gather",
            "mcp_actions": [
                {"tool": "oc_adm_must_gather", "arguments": {}, "label": "gather"},
            ],
            "request_summary": "must-gather",
            "blocked_commands": [],
            "intent": "diagnose",
            "analysis_source": "test",
            "proposed_commands": [],
            "clarifying_questions": [],
        }
        comment = {"id": 7, "content": "please must-gather"}
        persist_workflow_context_from_memory(
            "case-2",
            memory=memory,
            comment=comment,
            pending=pending,
        )
        fp = pending[0]["fingerprint"]
        ok, approved = approve_fingerprint("case-2", fp, approved_by="sre@corp.com")
        self.assertTrue(ok)
        self.assertEqual(approved.get("resume_status"), RESUME_PENDING)
        self.assertIn("workflow_context", approved)

        resumable = list_resumable_approved("case-2")
        self.assertEqual(len(resumable), 1)
        self.assertEqual(resumable[0]["pending_id"], approved["pending_id"])

        mark_pending_resumed("case-2", approved["pending_id"])
        self.assertEqual(len(list_resumable_approved("case-2")), 0)


class CustomerStatusReplyTests(unittest.TestCase):
    def test_customer_status_hides_fingerprint(self):
        pending = [{"fingerprint": "abc123", "tool": "pods_exec", "label": "dig"}]
        text = format_approval_required_reply(
            pending,
            config={"approval": {"connector_reply": {"mode": "customer_status"}}},
        )
        self.assertIn("dig", text)
        self.assertNotIn("abc123", text)
        self.assertIn("自動接續執行", text)


class WorkflowResumeRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.approval_patch = mock.patch.object(
            approval_module, "APPROVAL_ROOT", self.root
        )
        self.audit_patch = mock.patch.object(audit_module, "AUDIT_ROOT", self.root)
        self.approval_patch.start()
        self.audit_patch.start()

    def tearDown(self):
        self.approval_patch.stop()
        self.audit_patch.stop()
        self.tmp.cleanup()

    def test_try_resume_invokes_workflow_after_grant(self):
        action = MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather")
        config = {
            "approval": {"enabled": True, "required_tools": ["oc_adm_must_gather"]},
            "enterprise": {"audit_trail": True},
        }
        pending = register_pending_approvals("case-3", [action], comment_id=11, config=config)
        memory = {
            "case_id": "case-3",
            "latest_msg": "must-gather please",
            "mcp_actions": [
                {"tool": "oc_adm_must_gather", "arguments": {}, "label": "gather"},
            ],
            "request_summary": "gather",
            "blocked_commands": [],
            "intent": "diagnose",
            "analysis_source": "test",
            "proposed_commands": [],
            "clarifying_questions": [],
            "processed_comment_ids": [],
            "processed_handled_keys": [],
        }
        comment = {"id": 11, "content": "must-gather please", "author": "support"}
        persist_workflow_context_from_memory(
            "case-3",
            memory=memory,
            comment=comment,
            pending=pending,
        )
        approved_item = approve_fingerprint(
            "case-3",
            pending[0]["fingerprint"],
            approved_by="sre",
        )[1]
        self.assertIsNotNone(approved_item)

        app = mock.MagicMock()
        app.invoke.return_value = {
            "action_type": "call_mcp",
            "execution_results": ["ok"],
            "reply_posted": True,
            "policy_passed": True,
            "all_mcp_actions": memory["mcp_actions"],
            "proposed_commands": [],
        }

        executor = mock.MagicMock()
        deps = mock.MagicMock()
        deps.executor = executor
        audit = AuditTrail(config=config, case_id="case-3")

        resumed = try_resume_approved_workflows(
            memory,
            config,
            [comment],
            app,
            deps,
            mock.MagicMock(),
            dry_run=False,
            processed_ids=set(),
            processed_keys=set(),
            case_history="history",
            audit=audit,
        )
        self.assertTrue(resumed)
        app.invoke.assert_called_once()
        invoke_state = app.invoke.call_args[0][0]
        self.assertTrue(invoke_state.get("workflow_resume"))
        self.assertEqual(invoke_state.get("pending_id"), approved_item["pending_id"])

        events = [rec.get("event") for rec in load_audit_records("case-3")]
        self.assertIn("workflow_resumed", events)

        stored = approval_module.load_approvals("case-3")
        resumed_entries = [
            item
            for item in stored.get("approved", [])
            if item.get("resume_status") == RESUME_DONE
        ]
        self.assertEqual(len(resumed_entries), 1)

    def test_build_resume_state_from_approved_item(self):
        approved_item = {
            "pending_id": "pend-abc",
            "correlation_id": "case:1:fp",
            "workflow_context": {
                "comment_id": 1,
                "latest_msg": "run dig",
                "mcp_actions": [{"tool": "pods_exec", "arguments": {}, "label": "dig"}],
                "request_summary": "dns check",
            },
        }
        state = _build_resume_invoke_state(
            {"case_id": "case"},
            approved_item=approved_item,
            case_history="hist",
            dry_run=True,
        )
        self.assertEqual(state["action_type"], "call_mcp")
        self.assertTrue(state["analysis_prefilled"])
        self.assertEqual(state["pending_id"], "pend-abc")

    def test_resume_grant_bypasses_reapproval(self):
        action = MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather")
        config = {"approval": {"enabled": True, "required_tools": ["oc_adm_must_gather"]}}
        pending = register_pending_approvals("case-4", [action], comment_id=3, config=config)
        memory = {
            "case_id": "case-4",
            "latest_msg": "must-gather",
            "mcp_actions": [
                {"tool": "oc_adm_must_gather", "arguments": {}, "label": "gather"},
            ],
            "request_summary": "gather",
            "blocked_commands": [],
            "intent": "diagnose",
            "analysis_source": "test",
            "proposed_commands": [],
            "clarifying_questions": [],
        }
        comment = {"id": 3, "content": "must-gather", "author": "support"}
        persist_workflow_context_from_memory(
            "case-4",
            memory=memory,
            comment=comment,
            pending=pending,
        )
        approved_item = approve_fingerprint("case-4", pending[0]["fingerprint"], approved_by="sre")[1]
        self.assertTrue(
            actions_covered_by_resume_grant(
                "case-4",
                approved_item["pending_id"],
                [action],
            )
        )

        from core.config import load_config
        from core.decision import DecisionContext, DecisionEngine
        from core.mcp_policy import MCPPolicyChecker

        engine = DecisionEngine(MCPPolicyChecker(), config)
        result = engine.evaluate(
            DecisionContext(
                action_type="call_mcp",
                actions=[action],
                latest_msg="must-gather",
                case_id="case-4",
                comment_id=3,
                resume_pending_id=approved_item["pending_id"],
            )
        )
        self.assertTrue(result.allowed)
        self.assertFalse(result.requires_approval)
        self.assertTrue(result.to_workflow_state()["policy_passed"])


class ApprovalDedupAndCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.approval_patch = mock.patch.object(
            approval_module, "APPROVAL_ROOT", self.root
        )
        self.approval_patch.start()

    def tearDown(self):
        self.approval_patch.stop()
        self.tmp.cleanup()

    def _grant_with_context(self, case_id: str, comment_id: int, suffix: str) -> Dict[str, Any]:
        action = MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather")
        config = {"approval": {"enabled": True, "required_tools": ["oc_adm_must_gather"]}}
        pending = register_pending_approvals(
            case_id,
            [action],
            comment_id=comment_id,
            config=config,
        )
        memory = {
            "case_id": case_id,
            "latest_msg": "must-gather",
            "mcp_actions": [
                {"tool": "oc_adm_must_gather", "arguments": {}, "label": "gather"},
            ],
            "request_summary": "gather",
            "blocked_commands": [],
            "intent": "diagnose",
            "analysis_source": "test",
            "proposed_commands": [],
            "clarifying_questions": [],
        }
        persist_workflow_context_from_memory(
            case_id,
            memory=memory,
            comment={"id": comment_id, "content": "must-gather"},
            pending=pending,
        )
        ok, approved = approve_token(case_id, pending[0]["fingerprint"], approved_by=suffix)
        self.assertTrue(ok)
        assert approved is not None
        return approved

    def _inject_duplicate_resumable(self, case_id: str, template: Dict[str, Any]) -> Dict[str, Any]:
        store = load_approvals(case_id)
        duplicate = dict(template)
        duplicate["pending_id"] = "pend-dup000000001"
        duplicate["workflow_id"] = duplicate["pending_id"]
        duplicate["approved_at"] = "2099-01-01T00:00:00+00:00"
        store.setdefault("approved", []).append(duplicate)
        approval_module.save_approvals(case_id, store)
        return duplicate

    def test_list_resumable_dedupes_by_correlation_id(self):
        first = self._grant_with_context("dedup-1", 1, "sre1")
        duplicate = self._inject_duplicate_resumable("dedup-1", first)

        resumable = list_resumable_approved("dedup-1")
        self.assertEqual(len(resumable), 1)
        self.assertEqual(resumable[0]["pending_id"], first["pending_id"])
        self.assertNotEqual(resumable[0]["pending_id"], duplicate["pending_id"])

    def test_mark_pending_resumed_supersedes_duplicate_grants(self):
        first = self._grant_with_context("dedup-2", 2, "sre1")
        duplicate = self._inject_duplicate_resumable("dedup-2", first)
        mark_pending_resumed("dedup-2", first["pending_id"])

        store = load_approvals("dedup-2")
        statuses = {
            item["pending_id"]: item.get("resume_status")
            for item in store.get("approved", [])
            if isinstance(item, dict)
        }
        self.assertEqual(statuses[first["pending_id"]], RESUME_DONE)
        self.assertEqual(statuses[duplicate["pending_id"]], RESUME_DONE)
        self.assertEqual(len(list_resumable_approved("dedup-2")), 0)

    def test_register_skips_when_resumable_grant_exists(self):
        approved = self._grant_with_context("dedup-3", 3, "sre")
        action = MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather")
        again = register_pending_approvals("dedup-3", [action], comment_id=3)
        self.assertEqual(again[0]["pending_id"], approved["pending_id"])
        store = load_approvals("dedup-3")
        self.assertEqual(len(store.get("pending", [])), 0)

    def test_approve_by_pending_id_and_latest(self):
        action = MCPAction(tool="pods_exec", arguments={"command": ["dig", "x"]}, label="dig")
        pending = register_pending_approvals("dedup-4", [action], comment_id=4)
        pid = pending[0]["pending_id"]
        ok, entry = approve_token("dedup-4", pid, approved_by="sre")
        self.assertTrue(ok)
        self.assertEqual(entry.get("pending_id"), pid)

        action2 = MCPAction(tool="pods_exec", arguments={"command": ["dig", "y"]}, label="dig2")
        pending2 = register_pending_approvals("dedup-4", [action2], comment_id=5)
        ok_latest, latest = approve_latest("dedup-4", approved_by="lead")
        self.assertTrue(ok_latest)
        self.assertEqual(latest.get("pending_id"), pending2[0]["pending_id"])

    def test_deny_removes_pending_and_blocks_resume(self):
        action = MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather")
        config = {"approval": {"enabled": True, "required_tools": ["oc_adm_must_gather"]}}
        pending = register_pending_approvals("deny-1", [action], comment_id=9, config=config)
        pid = pending[0]["pending_id"]
        ok, denied = deny_token(
            "deny-1",
            pid,
            denied_by="sre@corp.com",
            reason="cluster offline",
        )
        self.assertTrue(ok)
        self.assertEqual(denied.get("resume_status"), RESUME_DENIED)
        self.assertEqual(denied.get("deny_reason"), "cluster offline")

        store = load_approvals("deny-1")
        self.assertEqual(len(store.get("pending", [])), 0)
        self.assertEqual(len(store.get("denied", [])), 1)
        self.assertEqual(len(list_resumable_approved("deny-1")), 0)

    def test_deny_resumable_grant_cancels_resume(self):
        approved = self._grant_with_context("deny-2", 10, "sre")
        self.assertEqual(len(list_resumable_approved("deny-2")), 1)

        ok, denied = deny_token(
            "deny-2",
            approved["pending_id"],
            denied_by="lead",
            reason="not needed",
        )
        self.assertTrue(ok)
        self.assertIsNotNone(denied)
        self.assertEqual(len(list_resumable_approved("deny-2")), 0)

        store = load_approvals("deny-2")
        grant = next(
            item
            for item in store.get("approved", [])
            if item.get("pending_id") == approved["pending_id"]
        )
        self.assertEqual(grant.get("resume_status"), RESUME_DENIED)

    def test_deny_writes_audit_event(self):
        action = MCPAction(tool="pods_exec", arguments={"command": ["dig", "x"]}, label="dig")
        pending = register_pending_approvals("deny-3", [action], comment_id=11)
        config = {"enterprise": {"audit_trail": True}}
        audit = AuditTrail(config=config, case_id="deny-3")
        ok, denied = deny_token("deny-3", pending[0]["fingerprint"], denied_by="sre", reason="no")
        self.assertTrue(ok)
        audit.record_approval_denied(denied_item=denied, denied_by="sre", reason="no")
        events = [rec.get("event") for rec in load_audit_records("deny-3")]
        self.assertIn("approval_denied", events)


if __name__ == "__main__":
    unittest.main()
