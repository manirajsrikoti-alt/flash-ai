"""FLASH: allowlisted macOS application and website executor."""

import subprocess

ALLOWED_APPS = {
    "open_calculator": "Calculator",
    "open_chrome": "Google Chrome",
}

ALLOWED_WEBSITES = {
    "open_youtube": "https://www.youtube.com",
}


def execute_action(action: str, confidence: float) -> str:
    if confidence < 0.85:
        return "Action blocked: confidence is too low."

    try:
        if action in ALLOWED_APPS:
            app_name = ALLOWED_APPS[action]
            subprocess.run(
                ["open", "-a", app_name],
                check=True,
                timeout=10,
            )
            return f"Opened {app_name} successfully."

        if action in ALLOWED_WEBSITES:
            url = ALLOWED_WEBSITES[action]
            subprocess.run(
                ["open", "-a", "Google Chrome", url],
                check=True,
                timeout=10,
            )
            return f"Opened {url} in Google Chrome."

        return f"No executable action allowed for: {action}"

    except subprocess.CalledProcessError:
        return "Could not open the requested app or website."
    except subprocess.TimeoutExpired:
        return "Timed out while opening the requested app or website."


if __name__ == "__main__":
    print(execute_action("open_youtube", 0.99))
