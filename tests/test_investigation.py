import unittest

from core.investigation import (
    filter_follow_up_actions,
    investigation_settings,
    should_continue_investigation,
)
from core.mcp_action import MCPAction


class InvestigationSettingsTests(unittest.TestCase):
    def test_defaults(self):
        settings = investigation_settings({})
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["max_follow_up_steps"], 2)

    def test_disabled(self):
        settings = investigation_settings({"investigation": {"enabled": False}})
        self.assertFalse(settings["enabled"])


class ShouldContinueInvestigationTests(unittest.TestCase):
    def _state(self, **kwargs):
        base = {
            "action_type": "call_mcp",
            "needs_more_evidence": True,
            "follow_up_mcp_actions": [{"tool": "pods_list", "arguments": {}, "label": "pods"}],
            "investigate_step": 0,
        }
        base.update(kwargs)
        return base

    def test_continues_when_follow_up_available(self):
        self.assertTrue(
            should_continue_investigation(self._state(), {"investigation": {"enabled": True, "max_follow_up_steps": 2}})
        )

    def test_stops_at_max_steps(self):
        self.assertFalse(
            should_continue_investigation(
                self._state(investigate_step=2),
                {"investigation": {"enabled": True, "max_follow_up_steps": 2}},
            )
        )

    def test_stops_when_disabled(self):
        self.assertFalse(
            should_continue_investigation(
                self._state(),
                {"investigation": {"enabled": False}},
            )
        )

    def test_stops_without_follow_up(self):
        self.assertFalse(
            should_continue_investigation(
                self._state(follow_up_mcp_actions=[]),
                {"investigation": {"enabled": True}},
            )
        )


class FilterFollowUpActionsTests(unittest.TestCase):
    def test_filters_unknown_tools(self):
        actions = filter_follow_up_actions(
            [
                {"tool": "pods_list", "arguments": {}, "label": "pods"},
                {"tool": "unknown_tool", "arguments": {}, "label": "bad"},
            ],
            mcp_tool_names=["pods_list"],
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].tool, "pods_list")


if __name__ == "__main__":
    unittest.main()
