import unittest
from unittest.mock import patch, MagicMock

import flash_cli
from flash_aws_brain import FlashAWSBrain

class FlashVoiceIntegrationTests(unittest.TestCase):
    @patch("builtins.input")
    @patch("builtins.print")
    @patch("flash_executor.subprocess.run")
    @patch.object(FlashAWSBrain, "ask")
    @patch.object(FlashAWSBrain, "inject_context")
    @patch("flash_cli.classify")
    @patch("flash_ai_planner.plan_request")
    @patch("flash_plan_bridge.execute_validated_plan")
    @patch("sys.argv", ["flash_cli.py", "--voice"])
    @patch("flash_voice_continuous.listen_for_speech")
    def test_voice_mode_integration(
        self,
        mock_listen,
        mock_execute_plan,
        mock_plan_request,
        mock_classify,
        mock_inject_context,
        mock_brain_ask,
        mock_run,
        mock_print,
        mock_input,
    ):
        # Provide a sequence of voice inputs
        voice_inputs = [
            "  ", # Empty transcript
            "open Calculator", # Direct command
            "delete all files", # Blocked safety command
            "launch unsafe_website", # Planner fallback -> rejected by validator
            "open my success project", # Planner fallback -> successful execution
            "open my fail project", # Planner fallback -> failed execution
            "What is the capital of France?", # Q&A fallback
        ]
        
        def mock_listen_func():
            for utterance in voice_inputs:
                yield utterance
            # Clean shutdown simulation via natural generator exhaustion
            
        mock_listen.return_value = mock_listen_func()
        
        mock_classify.return_value = None
        mock_run.return_value = MagicMock(returncode=0)
        mock_brain_ask.return_value = "Paris is the capital of France."
        
        def mock_plan_req(brain, text, context=None):
            if "unsafe_website" in text:
                return {"steps": [{"action": "web_search", "target": "evil.example", "details": "", "requires_confirmation": False}], "needs_clarification": False}
            if "success" in text:
                return {"steps": [{"action": "create_text_file", "target": "success.txt", "details": "ok", "requires_confirmation": False}], "needs_clarification": False}
            if "fail" in text:
                return {"steps": [{"action": "create_text_file", "target": "fail.txt", "details": "bad", "requires_confirmation": False}], "needs_clarification": False}
            return {"steps": [], "needs_clarification": False}
        mock_plan_request.side_effect = mock_plan_req
        
        def mock_exec_plan(plan):
            if not plan.get("steps"):
                return True, [], []
            target = plan["steps"][0]["target"]
            if target == "evil.example":
                raise ValueError("Step 1 website target 'evil.example' is invalid or unsafe.")
            elif target == "success.txt":
                return (True, ["Created success.txt"], ["/mock/success.txt"])
            elif target == "fail.txt":
                return (False, ["Permission denied"], [])
            return (True, [], [])
        mock_execute_plan.side_effect = mock_exec_plan

        # Run CLI main loop in voice mode
        flash_cli.main()
        
        # Verify text input was never called
        mock_input.assert_not_called()
        
        # Verify direct command executed
        self.assertEqual(mock_run.call_count, 1)
        args, _ = mock_run.call_args
        self.assertEqual(args[0], ["open", "-a", "Calculator"])
        
        # Explicitly assert execute_validated_plan was called for both planned actions with expected plans
        mock_execute_plan.assert_any_call({
            "steps": [{"action": "create_text_file", "target": "success.txt", "details": "ok", "requires_confirmation": False}],
            "needs_clarification": False
        })
        mock_execute_plan.assert_any_call({
            "steps": [{"action": "create_text_file", "target": "fail.txt", "details": "bad", "requires_confirmation": False}],
            "needs_clarification": False
        })

        # Verify execution context injection for direct actions and planner successes/failures
        mock_inject_context.assert_any_call("open Calculator", "Action completed: Done: open_calculator")
        mock_inject_context.assert_any_call("open my success project", "Plan succeeded: Created success.txt")
        mock_inject_context.assert_any_call("open my fail project", "Plan failed: Permission denied")
        
        # Verify Q&A went to conversational brain
        mock_brain_ask.assert_called_once_with("What is the capital of France?")
        
        printed_lines = [" ".join(str(arg) for arg in call[0]) for call in mock_print.call_args_list]
        
        # Verify blocked command
        self.assertTrue(any("blocked by the current safety policy" in line for line in printed_lines))
        
        # Verify unsafe planner action rejected by validator
        self.assertTrue(any("PLAN REJECTED: Step 1 website target" in line for line in printed_lines))
        
        # Assert execution failure message is reported in CLI output
        self.assertTrue(any("Permission denied" in line for line in printed_lines))

        # Verify clean shutdown
        self.assertTrue(any("FLASH stopped" in line for line in printed_lines))

if __name__ == "__main__":
    unittest.main(verbosity=2)
