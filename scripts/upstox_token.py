import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Load .env file
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

TOKEN_URL = "https://api-v2.upstox.com/login/authorization/token"


def _get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def exchange_code_for_token(auth_code: str) -> dict:
    payload = {
        "code": auth_code,
        "client_id": _get_env("UPSTOX_API_KEY"),
        "client_secret": _get_env("UPSTOX_API_SECRET"),
        "redirect_uri": _get_env("UPSTOX_REDIRECT_URI"),
        "grant_type": "authorization_code",
    }

    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else str(exc)
        raise RuntimeError(f"Upstox token exchange failed: {raw}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response: {raw}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exchange Upstox auth code for an access token."
    )
    parser.add_argument(
        "--code",
        required=False,
        help="Authorization code from Upstox login redirect",
    )
    args = parser.parse_args()

    auth_code = args.code or os.getenv("UPSTOX_AUTH_CODE")
    if not auth_code:
        raise RuntimeError("Provide --code or set UPSTOX_AUTH_CODE in env")

    token_payload = exchange_code_for_token(auth_code)
    access_token = token_payload.get("access_token")

    print(json.dumps(token_payload, indent=2))
    if access_token:
        print("\nSave this in .env as UPSTOX_ACCESS_TOKEN=<value> for later use.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
