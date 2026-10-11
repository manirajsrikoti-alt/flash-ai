"""FLASH task planner — creates safe plans; performs no actions."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class PlannedStep:
    action: str
    description: str
    requires_confirmation: bool = False


@dataclass(frozen=True)
class TaskPlan:
    original_request: str
    steps: tuple[PlannedStep, ...]
    needs_clarification: bool = False
    clarification: str = ""


def plan_task(request: str) -> TaskPlan:
    """Convert a small set of requests into a dry-run plan."""
    text = re.sub(r"\s+", " ", (request or "").strip())
    lower = text.lower()

    if not text:
        return TaskPlan(text, (), True, "What would you like FLASH to do?")

    # Messaging is planned, never sent by this module.
    if "whatsapp" in lower and re.search(r"\b(send|message|text)\b", lower):
        return TaskPlan(
            text,
            (
                PlannedStep("open_whatsapp", "Open WhatsApp"),
                PlannedStep(
                    "identify_recipients",
                    "Identify the requested recipients and show their names",
                    True,
                ),
                PlannedStep(
                    "prepare_messages",
                    "Prepare the requested message for each confirmed recipient",
                    True,
                ),
                PlannedStep(
                    "send_messages",
                    "Send messages only after explicit user approval",
                    True,
                ),
            ),
            True,
            "The recipient-selection rule is not defined yet. "
            "Should 'first four people' mean the first four visible chats?",
        )

    if re.fullmatch(r"(?:hey flash[, ]*)?(?:open|launch|start) whatsapp", lower):
        return TaskPlan(
            text,
            (PlannedStep("open_whatsapp", "Open WhatsApp"),),
        )

    if re.search(r"\b(create|make|write)\b", lower) and "note" in lower:
        return TaskPlan(
            text,
            (
                PlannedStep(
                    "create_note",
                    "Prepare a note; its title and content need to be extracted",
                    True,
                ),
            ),
            True,
            "What title and content should the note contain?",
        )

    if re.search(r"\b(search|google)\b", lower):
        return TaskPlan(
            text,
            (
                PlannedStep(
                    "web_search",
                    "Prepare a web search; the search query needs to be extracted",
                    True,
                ),
            ),
            True,
            "What exactly should FLASH search for?",
        )

    return TaskPlan(
        text,
        (),
        True,
        "This request is not yet supported by the dry-run planner.",
    )


def main():
    examples = [
        "Open WhatsApp",
        "Open WhatsApp and send Hi to the first 4 people",
        "Create a note about today's project meeting",
        "Google the latest Python release",
        "Do something unsupported",
    ]

    for example in examples:
        result = plan_task(example)
        print(f"\nREQUEST: {result.original_request}")
        for index, step in enumerate(result.steps, start=1):
            approval = " [confirmation required]" if step.requires_confirmation else ""
            print(f"  {index}. {step.action}: {step.description}{approval}")
        if result.needs_clarification:
            print(f"  CLARIFY: {result.clarification}")
        if not result.steps:
            print("  No action proposed.")


if __name__ == "__main__":
    main()
