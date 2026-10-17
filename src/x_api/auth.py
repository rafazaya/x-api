"""OAuth 2.0 user-context auth (Authorization Code + PKCE) for X.

Each authorized account gets its own token file under ~/.config/x-api/tokens/.
X rotates the refresh token on every refresh, so a refresh holds an exclusive
lock and saves the new tokens atomically before anything else uses them.

Usage:
    uv run python -m x_api.auth login     # authorize whichever account the browser is signed into
    uv run python -m x_api.auth list      # show authorized accounts
"""

import base64
import fcntl
import hashlib
import http.server
import json
import os
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "x-api"
TOKENS_DIR = CONFIG_DIR / "tokens"

AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 8723
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}/callback"
SCOPES = "tweet.read users.read bookmark.read offline.access"

# Refresh this many seconds before the access token actually expires.
EXPIRY_MARGIN = 120

load_dotenv(CONFIG_DIR / ".env")


def _client_id() -> str:
    client_id = os.environ.get("X_CLIENT_ID", "")
    if not client_id:
        raise RuntimeError(f"X_CLIENT_ID not set. Add it to {CONFIG_DIR / '.env'}")
    return client_id


def _token_path(username: str) -> Path:
    return TOKENS_DIR / f"{username.lower()}.json"


def _save_tokens(username: str, tokens: dict) -> None:
    """Write tokens atomically with 0600 permissions."""
    TOKENS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _token_path(username)
    tmp = path.with_suffix(".json.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(tokens, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _token_record(resp_json: dict, user_id: str, username: str) -> dict:
    return {
        "user_id": user_id,
        "username": username,
        "access_token": resp_json["access_token"],
        "refresh_token": resp_json["refresh_token"],
        "expires_at": int(time.time()) + int(resp_json.get("expires_in", 7200)),
        "scope": resp_json.get("scope", ""),
    }


def list_accounts() -> list[str]:
    """Usernames that have a saved token file."""
    if not TOKENS_DIR.exists():
        return []
    return sorted(p.stem for p in TOKENS_DIR.glob("*.json"))


def load_account(username: str) -> dict:
    path = _token_path(username)
    if not path.exists():
        raise RuntimeError(f"@{username} is not authorized. Run: python -m x_api.auth login")
    return json.loads(path.read_text())


def get_access_token(username: str) -> tuple[str, str]:
    """Return (access_token, user_id) for an account, refreshing if needed."""
    TOKENS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = TOKENS_DIR / f".{username.lower()}.lock"
    with open(lock_path, "w") as lock:
        # Exclusive lock: two concurrent refreshes would burn the rotated refresh token.
        fcntl.flock(lock, fcntl.LOCK_EX)
        tokens = load_account(username)
        if tokens["expires_at"] - EXPIRY_MARGIN > time.time():
            return tokens["access_token"], tokens["user_id"]

        resp = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": _client_id(),
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Token refresh for @{username} failed ({resp.status_code}): {resp.text}. "
                "Re-run: python -m x_api.auth login"
            )
        new = _token_record(resp.json(), tokens["user_id"], tokens["username"])
        _save_tokens(username, new)
        return new["access_token"], new["user_id"]


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _wait_for_callback(expected_state: str, timeout: int) -> str:
    """Serve one request on the loopback redirect URI and return the auth code."""
    result: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            if params.get("state") != expected_state:
                result["error"] = "state mismatch"
            elif "error" in params:
                result["error"] = params["error"]
            else:
                result["code"] = params.get("code", "")
            ok = "code" in result
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            msg = "Authorized. You can close this tab." if ok else f"Authorization failed: {result.get('error')}"
            self.wfile.write(msg.encode())

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer((REDIRECT_HOST, REDIRECT_PORT), Handler)
    server.timeout = 5
    deadline = time.time() + timeout
    try:
        while not result and time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    if "code" not in result:
        raise RuntimeError(f"Authorization failed: {result.get('error', 'timed out waiting for callback')}")
    return result["code"]


def login(timeout: int = 600) -> str:
    """Run the browser consent flow and save tokens. Returns the authorized username."""
    client_id = _client_id()
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)

    url = AUTHORIZE_URL + "?" + urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    print("Open this URL in a browser signed into the X account to authorize:\n", flush=True)
    print(url + "\n", flush=True)
    print(f"Waiting for the callback on {REDIRECT_URI} (up to {timeout // 60} min)...", flush=True)

    code = _wait_for_callback(state, timeout)

    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
            "client_id": client_id,
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    token_json = resp.json()

    me = httpx.get(
        "https://api.x.com/2/users/me",
        headers={"Authorization": f"Bearer {token_json['access_token']}"},
    )
    me.raise_for_status()
    user = me.json()["data"]

    _save_tokens(user["username"], _token_record(token_json, user["id"], user["username"]))
    print(f"Authorized @{user['username']} (id {user['id']}). Saved to {_token_path(user['username'])}")
    return user["username"]


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "login":
        login()
    elif cmd == "list":
        for name in list_accounts():
            tokens = load_account(name)
            left = int(tokens["expires_at"] - time.time())
            print(f"@{tokens['username']}  id={tokens['user_id']}  access token expires in {left // 60} min")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
