import unittest
from unittest.mock import patch, MagicMock

import flash_cli
from flash_aws_brain import FlashAWSBrain
from flash_context import TaskContext

class FlashCLIIntegrationTests(unittest.TestCase):
    @patch("builtins.print")
    @patch("flash_executor.subprocess.run")
    @patch.object(FlashAWSBrain, "ask")
    @patch.object(FlashAWSBrain, "inject_context")
    @patch("flash_cli.classify")
    @patch("flash_ai_planner.plan_request")
    @patch("flash_plan_bridge.execute_validated_plan")
    @patch("sys.argv", ["flash_cli.py", "--voice"])
    def test_cli_integration(
        self,
        mock_execute_plan,
        mock_plan_request,
        mock_classify,
        mock_inject_context,
        mock_brain_ask,
        mock_run,
        mock_print,
    ):
        inputs = [
            # A missing target remains unresolved
            {"type": "final", "text": "open it"}, # should fail to missing_target
            # A unique recent target resolves correctly
            {"type": "final", "text": "open Calculator"},
            {"type": "final", "text": "open it again"},
            # Multiple candidate targets produce an ambiguous result
            {"type": "final", "text": "open two apps"}, # fake multi-target plan
            {"type": "final", "text": "open it"}, # should fail to ambiguous
            # Ordered references work
            {"type": "final", "text": "close the first one"}, # resolves to "wikipedia.org" -> conversational fallback
            # Different intents using the same reference remain distinct
            {"type": "final", "text": "open the second one"}, # resolves to "github.com" -> opens
            {"type": "final", "text": "tell me about it"}, # resolves to "github.com" -> conversational
            {"type": "final", "text": "quit"}
        ]
        
        def mock_listen():
            for item in inputs:
                yield item
            while True:
                yield {"type": "final", "text": "quit"}
        
        mock_classify.return_value = None
        mock_run.return_value = MagicMock(returncode=0)
        mock_brain_ask.return_value = "I am conversational fallback."
        
        def mock_plan_req(brain, text, context=None):
            if "two apps" in text:
                return {"steps": [
                    {"action": "web_search", "target": "wikipedia.org", "details": "test", "requires_confirmation": False},
                    {"action": "web_search", "target": "github.com", "details": "test", "requires_confirmation": False}
                ], "needs_clarification": False}
            elif "close" in text:
                raise ValueError("Closing apps is not supported by the planner.")
            elif "github.com" in text and "open" in text:
                return {"steps": [{"action": "web_search", "target": "github.com", "details": "test", "requires_confirmation": False}], "needs_clarification": False}
            return {"steps": [], "needs_clarification": False}
            
        mock_plan_request.side_effect = mock_plan_req
        
        def mock_exec_plan(plan):
            return (True, ["Executed plan."], [])
            
        mock_execute_plan.side_effect = mock_exec_plan

        # Mock sys.modules to avoid numba crash
        mock_voice_module = MagicMock()
        mock_voice_module.listen_for_speech = mock_listen
        
        with patch.dict("sys.modules", {"flash_voice_continuous": mock_voice_module}):
            flash_cli.main()
        
        # Verify
        printed_lines = [" ".join(str(arg) for arg in call[0]) for call in mock_print.call_args_list]
        
        # Verify missing target:
        self.assertTrue(any("I'm not sure what you're referring to." in line for line in printed_lines))
        
        # Verify ambiguous:
        self.assertTrue(any("Please clarify which one you mean." in line for line in printed_lines))
        
        # Verify ordered references:
        # "close the first one" -> hits conversational fallback (because "close" is not imperative_verbs)
        mock_brain_ask.assert_any_call("close wikipedia.org")
        
        # Verify "tell me about it" -> "tell me about github.com" -> conversational
        # It should trigger brain.ask("tell me about github.com")
        mock_brain_ask.assert_any_call("tell me about github.com")

if __name__ == "__main__":
    unittest.main(verbosity=2)
