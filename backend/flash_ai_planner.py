"""FLASH AI planner — validates structured plans; executes no actions."""

import json
import re

from flash_aws_brain import FlashAWSBrain

ALLOWED_ACTIONS = {
    "open_app",
    "web_search",
    "search_web",
    "read_chrome_tabs",
    "create_text_file",
    "create_note",
    "prepare_message",
    "identify_recipients",
    "request_confirmation",
}

PLANNER_PROMPT = """
You are FLASH's task-planning engine for macOS.

Convert the user's request into a JSON object with this exact structure:
{
  "steps": [
    {
      "action": "one allowed action",
      "target": "app or destination, or empty string",
      "details": "specific task details",
      "requires_confirmation": true
    }
  ],
  "needs_clarification": false,
  "clarification": ""
}

Allowed actions:
- open_app
- web_search
- search_web
- read_chrome_tabs
- create_text_file
- create_note
- prepare_message
- identify_recipients
- request_confirmation

Rules:
- Output JSON only. No Markdown fences or extra text.
- Never claim any action has already been performed.
- Do not invent recipient names, search results, or note contents.
- For messaging, identify recipients and prepare the message first.
- Require explicit confirmation before sending any message.
- If recipient selection is ambiguous, set needs_clarification to true.
- Do not include an action named send_message. This planner cannot send messages.
- Use the user's exact message wording when preparing a message.
- For web searches, extract the query from the request.
- Use search_web to open actual search results, not just a website homepage.
- For create_text_file, set requires_confirmation to false.
- For create_note, set requires_confirmation to false. Use target for the note title and details for the note body text.
- For search_web, target must be exactly "youtube", "google", or "github"; put the search query in details.
- Example: "Search YouTube for MrBeast" -> action search_web, target "youtube", details "MrBeast".
- Example: "Search GitHub for Python projects" -> action search_web, target "github", details "Python projects".
- If the user only asks to open a website, use web_search with its plain HTTPS URL.
- If a search request can be satisfied directly by search_web, do not add a redundant homepage-opening step.
- Ask a clarification only when information genuinely needed for the plan is missing.

App-versus-website rules:
- "Open Calculator", "Open Notes", or "Open VS Code" means open the installed macOS application: use open_app and the application name.
- Use open_app only for applications, not website domains.
- "Open GitHub", "Open YouTube", or "Open Google" means open the corresponding website: use web_search and target the plain HTTPS URL, such as https://github.com, https://www.youtube.com, or https://www.google.com.
- If the user explicitly gives a website URL, use web_search and normalize a bare domain to HTTPS.
- "Search GitHub for Python projects" or "Search Google for..." means perform a web search. Preserve the search query in details.
- Never return Markdown links such as [GitHub](https://github.com). Use plain URLs.
- Do not treat an unknown app name as a website unless the request or name clearly indicates a website.
- If the intended app or website is genuinely ambiguous, set needs_clarification to true and ask a concise question.
"""


def extract_json(text: str) -> dict:
    """Parse a JSON object, allowing surrounding whitespace."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    result = json.loads(text)

    if not isinstance(result, dict):
        raise ValueError("Planner response must be a JSON object.")
    if not isinstance(result.get("steps"), list):
        raise ValueError("Planner response must contain a steps list.")

    for step in result["steps"]:
        if not isinstance(step, dict):
            raise ValueError("Each step must be an object.")
        if step.get("action") not in ALLOWED_ACTIONS:
            raise ValueError(f"Action not allowlisted: {step.get('action')!r}")
        if not isinstance(step.get("target", ""), str):
            raise ValueError("Step target must be text.")
        if not isinstance(step.get("details", ""), str):
            raise ValueError("Step details must be text.")
        if not isinstance(step.get("requires_confirmation"), bool):
            raise ValueError("Confirmation flag must be true or false.")

        # Enforce safety regardless of the AI-generated flag.
        if step["action"] in {
            "identify_recipients",
            "prepare_message",
            "request_confirmation",
        }:
            step["requires_confirmation"] = True

    if not isinstance(result.get("needs_clarification"), bool):
        raise ValueError("needs_clarification must be true or false.")
    if not isinstance(result.get("clarification", ""), str):
        raise ValueError("clarification must be text.")

    return result


def plan_request(brain: FlashAWSBrain, request: str, context: 'TaskContext' = None) -> dict:
    if not request.strip():
        raise ValueError("Request cannot be empty.")

    context_str = ""
    if context:
        if context.current_goal:
            context_str += f"\nCurrent Goal: {context.current_goal}"
        recent_actions = [a for a in context.actions if a.status in {"succeeded", "failed"}]
        if recent_actions:
            context_str += "\nRecent verified actions:\n"
            for a in recent_actions[-3:]:
                context_str += f"- {a.instruction} -> {a.status}: {a.result_message}\n"
    
    prompt = PLANNER_PROMPT
    if context_str:
        prompt += "\n\nCONTEXT:\n" + context_str

    response = brain.plan(
        system_prompt=prompt,
        user_request=request
    )
    if not response:
        raise ValueError("Empty response from AI planner.")
    return extract_json(response)


def main():
    print("FLASH ⚡ AI PLANNER — DRY RUN ONLY")
    print("No apps will be opened and no messages will be sent.")
    request = input("\nEnter a task for FLASH: ").strip()

    brain = FlashAWSBrain()

    try:
        plan = plan_request(brain, request)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"\nPLAN REJECTED: {exc}")
        print("No actions were performed.")
        return

    print("\nVALIDATED PLAN:")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    print("\nDry run complete. No actions were performed.")


if __name__ == "__main__":
    main()
