import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.config.settings import Settings
from src.jules.client import JulesClient


def test_optional_jules_key():
    print("Testing Optional Jules Key...")

    # Ensure JULES_API_KEY is not set
    if "JULES_API_KEY" in os.environ:
        del os.environ["JULES_API_KEY"]

    # Set GITHUB_TOKEN (still required)
    os.environ["GITHUB_TOKEN"] = "dummy_token"

    try:
        settings = Settings.from_env()
        print("Settings loaded successfully.")

        if settings.jules_api_key is None:
            print("PASS: settings.jules_api_key is None")
        else:
            print(f"FAIL: settings.jules_api_key is {settings.jules_api_key}")

    except Exception as e:
        print(f"FAIL: Settings.from_env failed: {e}")
        return

    try:
        client = JulesClient()
        print("JulesClient instantiated successfully.")

        if client.api_key is None:
             print("PASS: client.api_key is None")
        else:
             print(f"FAIL: client.api_key is {client.api_key}")

    except Exception as e:
        print(f"FAIL: JulesClient instantiation failed: {e}")

if __name__ == "__main__":
    test_optional_jules_key()
