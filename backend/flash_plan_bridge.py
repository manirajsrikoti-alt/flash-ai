"""FLASH AI planner bridge with safe, explicit execution mode."""

import argparse
import json

from flash_ai_planner import plan_request
from flash_plan_executor import (
    execute_step,
    normalize_website_url,
    normalize_search_url,
    resolve_app,
)

EXECUTABLE_ACTIONS = {"open_app", "web_search", "search_web", "read_chrome_tabs", "create_text_file", "create_note"}


def validate_plan_for_dry_run(plan: dict) -> list[str]:
    """Validate every step before returning any preview."""
    if not isinstance(plan, dict):
        raise ValueError("Plan must be a JSON object.")

    if plan.get("needs_clarification") is True:
        clarification = plan.get("clarification", "")
        raise ValueError(
            "Planner needs clarification: "
            + (clarification if isinstance(clarification, str) else "")
        )

    if plan.get("needs_clarification") is not False:
        raise ValueError("Plan must explicitly set needs_clarification to false.")

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("Plan must contain a non-empty steps list.")

    preview = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"Step {index} must be an object.")

        action = step.get("action")
        target = step.get("target")
        details = step.get("details")
        confirmation = step.get("requires_confirmation")

        if action not in EXECUTABLE_ACTIONS:
            raise ValueError(
                f"Step {index} uses unsupported action {action!r}; "
                "the entire plan is rejected."
            )

        if action != "read_chrome_tabs":
            if not isinstance(target, str) or not target.strip():
                raise ValueError(f"Step {index} needs a non-empty target.")

        if not isinstance(details, str):
            raise ValueError(f"Step {index} details must be text.")

        if confirmation is not False:
            raise ValueError(
                f"Step {index} requires confirmation or lacks an explicit "
                "safe flag; the entire plan is rejected."
            )

        if action == "open_app" and resolve_app(target) is None:
            raise ValueError(
                f"Step {index} app {target!r} is not allowlisted."
            )

        if action == "web_search" and normalize_website_url(target) is None:
            raise ValueError(
                f"Step {index} website target {target!r} is invalid or unsafe."
            )

        if action == "search_web" and normalize_search_url(target, details) is None:
            raise ValueError(
                f"Step {index} search provider/query is invalid or unsupported."
            )

        if action == "create_note":
            if not isinstance(target, str) or not target.strip():
                raise ValueError(
                    f"Step {index} create_note requires a non-empty title (target)."
                )

        preview.append(
            f"{index}. search_web -> {target.strip()}: {details.strip()}"
            if action == "search_web"
            else f"{index}. create_note -> title={target.strip()!r}"
            if action == "create_note"
            else f"{index}. {action} -> {target.strip()}"
        )

    return preview


def execute_validated_plan(plan: dict) -> tuple[bool, list[str], list[str]]:
    """Execute only after validating the entire plan."""
    validate_plan_for_dry_run(plan)

    results = []
    extracted_targets = []
    success = True
    for step in plan["steps"]:
        result = execute_step(step, dry_run=False)
        results.append(result.message)
        if getattr(result, "extracted_targets", None):
            extracted_targets.extend(result.extracted_targets)
        if not result.ok:
            success = False
            break

    return success, results, extracted_targets


def main():
    parser = argparse.ArgumentParser(description="FLASH planner bridge")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Allow validated app/website actions to run directly.",
    )
    args = parser.parse_args()

    if args.execute:
        print("FLASH ⚡ EXECUTION MODE — supported app/website actions only")
    else:
        print("FLASH ⚡ PLAN BRIDGE — DRY RUN ONLY")

    print("Messaging, note creation, deletion, shell commands, and payments are disabled.")

    request = input("\nWhat should FLASH plan? ").strip()
    if not request:
        print("No request entered.")
        return

    try:
        from flash_aws_brain import FlashAWSBrain
        plan = plan_request(FlashAWSBrain(), request)
        preview = validate_plan_for_dry_run(plan)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"PLAN REJECTED: {exc}")
        print("No actions were performed.")
        return
    except Exception as exc:
        print(f"Planning failed safely: {type(exc).__name__}: {exc}")
        print("No actions were performed.")
        return

    print("\nVALIDATED PLAN:")
    for item in preview:
        print(item)

    if not args.execute:
        print("\nDry run complete. No actions were performed.")
        return


    try:
        success, messages, extracted_targets = execute_validated_plan(plan)
    except Exception as exc:
        print(f"Execution stopped safely: {type(exc).__name__}: {exc}")
        return

    print("\nExecution results:")
    for message in messages:
        print(f"- {message}")


if __name__ == "__main__":
    main()
