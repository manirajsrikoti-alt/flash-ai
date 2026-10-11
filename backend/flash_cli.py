
"""FLASH CLI — conversational AI with a safety-gated action router."""

import json
import re

from flash_router import route
from flash_executor import execute
from flash_laya_classifier import classify
from flash_aws_brain import FlashAWSBrain


# Conservative safety gate: these requests must not reach an action executor
# or be treated as ordinary requests by the conversational fallback.
BLOCKED_PATTERN = re.compile(
    r"\b(delete|remove|erase|format|wipe|rm|sudo|send|message|email|"
    r"text|pay|buy|purchase|transfer|password|token|credential|"
    r"shutdown|install)\b",
    re.IGNORECASE,
)


def parse_whatsapp_request(text: str) -> dict | None:
    """Parse WhatsApp messaging request into recipient and message content.
    Returns None if text is not a WhatsApp messaging request.
    """
    if not isinstance(text, str):
        return None
    t = text.strip()
    norm = re.sub(r"^(?:hey flash|flash|please|can you|could you)[,\s]+", "", t, flags=re.IGNORECASE).strip()
    norm = norm.rstrip(".!?").strip()
    lower = norm.lower()

    if not lower or "whatsapp" not in lower:
        return None

    # Plain open app is NOT a messaging request
    if re.fullmatch(r"^(?:open|launch|start|run) (?:the )?whatsapp(?: app)?$", lower):
        return None

    recipient = None
    message = None

    # Pattern 1: ... to <recipient> (saying|that says|with text|with body|:) <message>
    m = re.search(
        r"(?:to|contact)\s+([A-Za-z0-9_+ -]+?)\s+(?:saying|that says|with text|with body|say|telling them|telling her|telling him)\s+(.+)$",
        norm,
        re.IGNORECASE,
    )
    if m:
        recipient = m.group(1).strip()
        message = m.group(2).strip()

    # Pattern 2: ... to <recipient>:\s*<message>
    if not recipient:
        m = re.search(r"(?:to|contact)\s+([A-Za-z0-9_+ -]+?)\s*[:]\s*(.+)$", norm, re.IGNORECASE)
        if m:
            recipient = m.group(1).strip()
            message = m.group(2).strip()

    # Pattern 3: (message|whatsapp|text) <recipient> (saying|that says|with text|:) <message>
    if not recipient:
        m = re.search(
            r"^(?:send\s+(?:a\s+)?)?(?:whatsapp\s+)?(?:message|whatsapp|text)\s+(?!saying\b|that\s+says\b|with\s+text\b)(.+?)\s+(?:on whatsapp\s+)?(?:saying|that says|with text|:)\s*(.+)$",
            norm,
            re.IGNORECASE,
        )
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in {"message", "whatsapp", "text", "a message", "a text"}:
                recipient = candidate
                message = m.group(2).strip()

    # Pattern 4: (message|whatsapp) <recipient> on whatsapp ...
    if not recipient:
        m = re.search(
            r"^(?:send\s+(?:a\s+)?)?(?:message|text)\s+([A-Za-z0-9_+ -]+?)\s+on whatsapp\s*(?:saying|that says|:)?\s*(.*)$",
            norm,
            re.IGNORECASE,
        )
        if m:
            recipient = m.group(1).strip()
            msg = m.group(2).strip()
            if msg:
                message = msg

    # Pattern 5: ... to <recipient> on whatsapp
    if not recipient:
        m = re.search(
            r"(?:to|contact)\s+([A-Za-z0-9_+ -]+?)\s+on whatsapp\s*(.*)$",
            norm,
            re.IGNORECASE,
        )
        if m:
            recipient = m.group(1).strip()
            msg = m.group(2).strip()
            if msg:
                message = msg

    # Pattern 6: only recipient specified: e.g. "send a whatsapp message to Alice"
    if not recipient:
        m = re.search(r"(?:to|contact)\s+([A-Za-z0-9_+ -]+?)(?:\s+on whatsapp)?$", norm, re.IGNORECASE)
        if m:
            recipient = m.group(1).strip()

    # Clean up recipient if it captured "on whatsapp" or reserved phrases
    if recipient:
        recipient = re.sub(r"\s+on whatsapp$", "", recipient, flags=re.IGNORECASE).strip()
        recipient = re.sub(r"^the\s+", "", recipient, flags=re.IGNORECASE).strip()
        if recipient.lower() in {"message", "whatsapp", "text", "a message", "a text", "chat", "someone"}:
            recipient = None

    # If message still None, see if there's text after "saying"
    if not message:
        m = re.search(r"(?:saying|that says|with text|:)\s*(.+)$", norm, re.IGNORECASE)
        if m:
            message = m.group(1).strip()

    return {
        "is_whatsapp": True,
        "recipient": recipient if recipient else None,
        "message": message if message else None,
    }


def _run_loop(args, voice_iterator, brain, task_context, popup=None, stop_event=None):
    while True:
        if stop_event and stop_event.is_set():
            print("FLASH stopped.")
            break
        if popup and popup.is_dismissed():
            print("FLASH stopped.")
            break

        # Check and apply context expiry at start of turn
        task_context.check_and_apply_expiry()

        try:
            if args.voice:
                if popup:
                    popup.set_state("listening")
                utterance = next(voice_iterator)
                if isinstance(utterance, dict):
                    ut_type = utterance.get("type", "final")
                    text = utterance.get("text", "").strip()
                    if ut_type == "preview":
                        # A partial transcript is provisional and must not independently trigger an action.
                        print(f"you (preview)> {text}")
                        if popup:
                            popup.set_transcript(text)
                        continue
                else:
                    text = utterance.strip()
                print(f"you> {text}")
                if popup:
                    popup.set_state("processing")
                    popup.set_transcript(text)
            else:
                text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt, StopIteration):
            print("\nFLASH stopped.")
            break
        except Exception as e:
            print(f"\nFLASH stopped due to error: {e}")
            break

        if not text:
            continue

        # Prevent duplicate actions from repeated or overlapping transcript segments
        import time
        now = time.monotonic()
        if hasattr(task_context, "last_text") and text == task_context.last_text:
            if now - getattr(task_context, "last_text_time", 0.0) < 2.0:
                continue

        task_context.last_text = text
        task_context.last_text_time = now
        task_context.add_turn("user", text)

        command = text.lower().strip().rstrip(".!?").strip()

        if command in {"quit", "exit"}:
            print("FLASH stopped.")
            if popup:
                popup.request_close()
            break

        if command == "reset":
            brain.reset()
            task_context.reset()
            print("FLASH> Conversation history and context cleared.")
            if popup:
                popup.set_state("speaking")
                popup.set_response("Conversation history cleared.")
            continue

        # Check for active confirmation requirement
        if task_context.active_task and task_context.active_task.phase == "awaiting_confirmation":
            if command in {"yes", "confirm", "proceed", "sure", "do it", "ok", "okay"}:
                task_context.active_task.phase = "executing"
                # Advance or retry the confirmed step
                pending_info = task_context.advance_to_next_step()
                if pending_info:
                    idx, step = pending_info
                    task_context.mark_step_running(idx)
                    if step.action in {"prepare_whatsapp_message", "send_whatsapp_message", "capture_photo", "create_note"}:
                        result = execute(step.action, step.target)
                    else:
                        from flash_plan_executor import execute_step
                        result = execute_step({
                            "action": step.action,
                            "target": step.target,
                            "details": step.details,
                            "requires_confirmation": False
                        }, dry_run=False)
                    task_context.record_step_result(idx, result.ok, result.message, getattr(result, "extracted_targets", None))
                    print("FLASH>", result.message)
                    if popup:
                        popup.set_state("completed" if result.ok else "failed")
                        popup.set_response(result.message)
                continue
            elif command in {"no", "cancel", "stop", "abort", "nevermind", "dont"}:
                task_context.set_task_phase("idle", result="Action cancelled.")
                print("FLASH> Action cancelled.")
                if popup:
                    popup.set_state("speaking")
                    popup.set_response("Action cancelled.")
                continue

        # Check for active clarification requirement for WhatsApp
        if (
            task_context.active_task
            and task_context.active_task.phase == "awaiting_clarification"
            and getattr(task_context, "pending_whatsapp", None)
        ):
            p_wa = task_context.pending_whatsapp
            if not p_wa.get("recipient"):
                p_wa["recipient"] = text.strip()
            elif not p_wa.get("message"):
                p_wa["message"] = text.strip()

            if p_wa.get("recipient") and p_wa.get("message"):
                recipient = p_wa["recipient"]
                msg_content = p_wa["message"]
                task_context.pending_whatsapp = None
                task_context.create_task(
                    f"Send WhatsApp message to {recipient}",
                    [{
                        "action": "prepare_whatsapp_message",
                        "target": json.dumps({"recipient": recipient, "message": msg_content}),
                        "details": msg_content,
                        "requires_confirmation": True
                    }]
                )
                task_context.active_task.phase = "awaiting_confirmation"
                confirm_prompt = (
                    f"I have prepared a WhatsApp message for {recipient}: \"{msg_content}\". "
                    "Would you like to proceed? Say 'yes' to confirm or 'no' to cancel."
                )
                print("FLASH>", confirm_prompt)
                if popup:
                    popup.set_state("speaking")
                    popup.set_response(confirm_prompt)
                continue
            elif not p_wa.get("message"):
                ask_msg = f"What message would you like to send to {p_wa['recipient']} on WhatsApp?"
                print("FLASH>", ask_msg)
                if popup:
                    popup.set_state("speaking")
                    popup.set_response(ask_msg)
                continue

        # Check for new WhatsApp messaging request
        wa_req = parse_whatsapp_request(text)
        if wa_req:
            if not wa_req.get("recipient"):
                task_context.pending_whatsapp = wa_req
                task_context.create_task("Send WhatsApp message", [{"action": "prepare_whatsapp_message", "target": "", "details": "", "requires_confirmation": True}])
                task_context.set_task_phase("awaiting_clarification", error="Missing recipient.")
                clarify_q = "Who would you like to message on WhatsApp?"
                print("FLASH>", clarify_q)
                if popup:
                    popup.set_state("speaking")
                    popup.set_response(clarify_q)
                continue
            elif not wa_req.get("message"):
                task_context.pending_whatsapp = wa_req
                task_context.create_task(f"Send WhatsApp message to {wa_req['recipient']}", [{"action": "prepare_whatsapp_message", "target": "", "details": "", "requires_confirmation": True}])
                task_context.set_task_phase("awaiting_clarification", error="Missing message content.")
                clarify_q = f"What message would you like to send to {wa_req['recipient']} on WhatsApp?"
                print("FLASH>", clarify_q)
                if popup:
                    popup.set_state("speaking")
                    popup.set_response(clarify_q)
                continue
            else:
                recipient = wa_req["recipient"]
                msg_content = wa_req["message"]
                task_context.pending_whatsapp = None
                task_context.create_task(
                    f"Send WhatsApp message to {recipient}",
                    [{
                        "action": "prepare_whatsapp_message",
                        "target": json.dumps({"recipient": recipient, "message": msg_content}),
                        "details": msg_content,
                        "requires_confirmation": True
                    }]
                )
                task_context.active_task.phase = "awaiting_confirmation"
                confirm_prompt = (
                    f"I have prepared a WhatsApp message for {recipient}: \"{msg_content}\". "
                    "Would you like to proceed? Say 'yes' to confirm or 'no' to cancel."
                )
                print("FLASH>", confirm_prompt)
                if popup:
                    popup.set_state("speaking")
                    popup.set_response(confirm_prompt)
                continue

        # Check for safe Apple Notes creation request
        early_decision = route(text, classifier=classify)
        if early_decision.intent == "create_note":
            final_target = early_decision.target
            record = task_context.add_action(text, early_decision.intent, final_target)
            task_context.update_action(record, "running")
            task_context.create_task(
                text,
                [{"action": early_decision.intent, "target": str(final_target or ""), "requires_confirmation": False}]
            )
            task_context.mark_step_running(0)
            if popup:
                popup.set_state("executing")

            result = execute(early_decision.intent, final_target)
            print("FLASH>", result.message)
            if popup:
                popup.set_state("speaking")
                popup.set_response(result.message)

            status = "succeeded" if result.ok else "failed"
            task_context.update_action(record, status, result.message)
            task_context.record_step_result(0, result.ok, result.message)
            task_context.add_turn("assistant", result.message, intent=early_decision.intent, phase=status)
            if result.ok:
                brain.inject_context(text, f"Action completed: {result.message}")
            continue

        # Apply the conservative safety gate before routing, follow-ups or cloud fallback.
        if BLOCKED_PATTERN.search(text):
            print("FLASH> This request is blocked by the current safety policy.")
            if popup:
                popup.set_state("speaking")
                popup.set_response("Blocked by safety policy.")
            continue

        # Resolve ambiguous references (e.g. "it", "the first one", "retry", "continue")
        resolved_text, ref_error = task_context.resolve_reference(text)

        if ref_error == "followup_retry":
            retry_info = task_context.prepare_retry_step()
            if retry_info:
                idx, step = retry_info
                if popup:
                    popup.set_state("executing")
                print(f"FLASH> Retrying step {idx+1}: {step.action} -> {step.target}")
                from flash_plan_executor import execute_step
                task_context.mark_step_running(idx)
                result = execute_step({
                    "action": step.action,
                    "target": step.target,
                    "details": step.details,
                    "requires_confirmation": False
                }, dry_run=False)
                task_context.record_step_result(idx, result.ok, result.message, getattr(result, "extracted_targets", None))
                print("FLASH>", result.message)
                if popup:
                    popup.set_state("completed" if result.ok else "failed")
                    popup.set_response(result.message)
            continue
        elif ref_error == "followup_continue":
            next_info = task_context.advance_to_next_step()
            if next_info:
                idx, step = next_info
                if popup:
                    popup.set_state("executing")
                print(f"FLASH> Executing step {idx+1}: {step.action} -> {step.target}")
                from flash_plan_executor import execute_step
                task_context.mark_step_running(idx)
                result = execute_step({
                    "action": step.action,
                    "target": step.target,
                    "details": step.details,
                    "requires_confirmation": False
                }, dry_run=False)
                task_context.record_step_result(idx, result.ok, result.message, getattr(result, "extracted_targets", None))
                print("FLASH>", result.message)
                if popup:
                    popup.set_state("completed" if result.ok else "failed")
                    popup.set_response(result.message)
            continue
        elif ref_error == "ambiguous":
            print("FLASH> Please clarify which one you mean.")
            task_context.set_task_phase("awaiting_clarification", error="Ambiguous target reference.")
            if popup:
                popup.set_state("speaking")
                popup.set_response("Please clarify which one you mean.")
            continue
        elif ref_error == "missing_target":
            print("FLASH> I'm not sure what you're referring to.")
            if popup:
                popup.set_state("speaking")
                popup.set_response("I'm not sure what you're referring to.")
            continue

        text_for_routing = resolved_text

        # Approved, recognized intents use the existing local executor (Laya fast path)
        t_route_start = time.perf_counter()
        decision = route(text_for_routing, classifier=classify)
        t_route_ms = (time.perf_counter() - t_route_start) * 1000.0
        print(f"[{decision.source}] {decision.intent}: {decision.reason}")

        if decision.intent != "unknown":
            final_target = decision.target
            record = task_context.add_action(text_for_routing, decision.intent, final_target)
            task_context.update_action(record, "running")
            task_context.create_task(
                text_for_routing,
                [{"action": decision.intent, "target": str(final_target or ""), "requires_confirmation": False}]
            )
            task_context.mark_step_running(0)

            if popup:
                popup.set_state("executing")

            t_exec_start = time.perf_counter()
            result = execute(decision.intent, final_target)
            t_exec_ms = (time.perf_counter() - t_exec_start) * 1000.0

            print("FLASH>", result.message)
            if popup:
                popup.set_state("speaking")
                popup.set_response(result.message)

            status = "succeeded" if result.ok else "failed"
            task_context.update_action(record, status, result.message)
            task_context.record_step_result(0, result.ok, result.message)
            task_context.add_turn("assistant", result.message, intent=decision.intent, phase=status)

            if result.ok:
                brain.inject_context(text_for_routing, f"Action completed: {result.message}")
            continue

        # Try AI planning for unrecognized actionable commands
        from flash_router import normalize
        normalized = normalize(text_for_routing)
        words = normalized.split()

        imperative_verbs = {
            "open", "launch", "start", "run", "search", "find",
            "google", "create", "make", "write", "visit", "browse", "go"
        }
        correction_words = {
            "actually", "instead", "no", "wait", "scratch", "cancel", "nevermind"
        }

        is_imperative = False
        if words:
            if words[0] in imperative_verbs:
                is_imperative = True
            elif words[0] in correction_words:
                for word in words[1:5]:
                    if word in imperative_verbs:
                        is_imperative = True
                        break

        if is_imperative:
            try:
                from flash_ai_planner import plan_request
                from flash_plan_bridge import validate_plan_for_dry_run, execute_validated_plan

                if popup:
                    popup.set_state("planning")

                plan = plan_request(brain, text_for_routing, task_context)

                # Handle planner output with needs_clarification: true
                if plan.get("needs_clarification") is True:
                    clarification_q = plan.get("clarification", "Could you please clarify your request?")
                    task_context.set_task_phase("awaiting_clarification", result=clarification_q)
                    print("FLASH>", clarification_q)
                    if popup:
                        popup.set_state("speaking")
                        popup.set_response(clarification_q)
                    continue

                validate_plan_for_dry_run(plan)

                targets = []
                for step in plan.get("steps", []):
                    t = step.get("target")
                    if t:
                        targets.append(t)

                final_plan_target = None
                if len(targets) == 1:
                    final_plan_target = targets[0]
                elif len(targets) > 1:
                    final_plan_target = targets

                record = task_context.add_action(text_for_routing, "ai_plan", final_plan_target)
                task_context.create_task(text_for_routing, plan.get("steps", []))

                print("FLASH> Executing planned task:")
                task_context.update_action(record, "running")

                if popup:
                    popup.set_state("executing")

                success, messages, plan_extracted = execute_validated_plan(plan)

                # Update step outcomes in task_context
                for idx, msg in enumerate(messages):
                    step_ok = success or (idx < len(messages) - 1)
                    task_context.record_step_result(
                        idx,
                        step_ok,
                        msg,
                        plan_extracted if idx == 0 else None,
                    )

                overall_message = " | ".join(messages)
                status_str = "succeeded" if success else "failed"

                new_target = None
                if plan_extracted:
                    all_targets = record.target or []
                    if isinstance(all_targets, str):
                        all_targets = [all_targets]
                    all_targets.extend(plan_extracted)
                    new_target = all_targets if len(all_targets) > 1 else all_targets[0]

                task_context.update_action(record, status_str, overall_message, new_target)
                brain.inject_context(text_for_routing, f"Plan {status_str}: {overall_message}")

                if popup:
                    popup.set_state("speaking")
                    popup.set_response(overall_message if overall_message else status_str)

                for msg in messages:
                    print("FLASH> -", msg)
                continue
            except ValueError as exc:
                if 'record' in locals():
                    task_context.update_action(record, "failed", str(exc))
                task_context.set_task_phase("failed", error=str(exc))
                print(f"FLASH> PLAN REJECTED: {exc}")
                if popup:
                    popup.set_state("speaking")
                    popup.set_response(f"Plan rejected: {exc}")
                continue
            except Exception as exc:
                if 'record' in locals():
                    task_context.update_action(record, "failed", str(exc))
                task_context.set_task_phase("failed", error=str(exc))
                print(f"FLASH> Planning failed safely: {type(exc).__name__}: {exc}")
                if popup:
                    popup.set_state("speaking")
                    popup.set_response(f"Planning failed: {exc}")
                continue

        # Unknown, non-blocked, non-imperative requests go to conversational AI.
        answer = brain.ask(text_for_routing)
        print("FLASH>", answer)
        task_context.add_turn("assistant", answer, phase="speaking")
        if popup:
            popup.set_state("speaking")
            popup.set_response(answer)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="FLASH CLI")
    parser.add_argument("--voice", action="store_true", help="Enable continuous voice listening mode")
    args = parser.parse_args()

    print("FLASH ⚡ FAST INTELLIGENCE. INSTANT ACTION.")
    print("AWS conversational brain + Laya classifier + safety router enabled.")

    voice_iterator = None
    if args.voice:
        print("Voice mode activated. Ensure your microphone is accessible.")
        try:
            from flash_voice_continuous import listen_for_speech
            voice_iterator = listen_for_speech()
        except ImportError as e:
            print("Error loading voice modules:", e)
            return

        # Start one-time background model warmup in voice mode
        import os, sys, threading
        is_test = "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules
        if not is_test:
            def _bg_warmup():
                try:
                    from flash_laya_classifier import warmup as warmup_laya
                    warmup_laya()
                except Exception:
                    pass
                try:
                    from flash_voice_continuous import warmup_whisper
                    warmup_whisper()
                except Exception:
                    pass

            threading.Thread(target=_bg_warmup, daemon=True).start()
    else:
        print("Type 'reset' to clear conversation history, or 'quit' to exit.")

    from flash_context import TaskContext
    brain = FlashAWSBrain()
    task_context = TaskContext()

    if args.voice:
        import os, sys, threading
        is_test = "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules
        from flash_voice_popup import FlashVoicePopup
        popup = FlashVoicePopup(headless=is_test)

        if not popup.headless:
            stop_event = threading.Event()
            popup.on_dismiss = lambda: stop_event.set()

            def worker():
                _run_loop(args, voice_iterator, brain, task_context, popup, stop_event)
                popup.request_close()

            t = threading.Thread(target=worker, daemon=True)
            t.start()
            popup.run_mainloop()
            stop_event.set()
            t.join(timeout=1.0)
            return
        else:
            _run_loop(args, voice_iterator, brain, task_context, popup)
            return
    else:
        _run_loop(args, None, brain, task_context)


if __name__ == "__main__":
    main()
