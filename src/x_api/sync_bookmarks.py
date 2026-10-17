"""Append new X bookmarks from every authorized account to a markdown inbox note.

Deliberately dumb: fetch, dedupe, append. No classification happens here; an
agent routes the entries later. Safe to run unattended on a timer.

Config (in ~/.config/x-api/.env):
    X_BOOKMARKS_FILE       markdown file to append to (required)
    X_BOOKMARKS_MAX_PAGES  pages to read per account per run (default 3; the
                           first page is 10 posts, later ones 100)

Usage:
    uv run python -m x_api.sync_bookmarks [--dry-run]
"""

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

from x_api import auth
from x_api.client import Tweet, list_bookmarks

STATE_FILE = Path.home() / ".local" / "state" / "x-api" / "bookmarks.json"
# Seen IDs kept per account. X only exposes the newest 800 bookmarks, so this
# comfortably covers everything the API can ever return.
SEEN_LIMIT = 2000
FIRST_PAGE_SIZE = 10

NOTE_HEADER = """# Social Bookmarks

Raw bookmarks pulled automatically from social accounts (currently X) by the
x-api sync timer. New entries are appended at the bottom.

Don't sort here by hand. Ask an agent to route each entry to the relevant inbox
or knowledge note (AI, Linux, ...), then delete it from this list. Entries with
no durable value go to `Rafa/90 Rejected/` or are just deleted.

"""


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, STATE_FILE)


async def _fetch_new(username: str, seen: set[str], max_pages: int) -> list[Tweet]:
    """Page newest-first until hitting an already-seen bookmark or the page cap.

    Reads are billed per post returned, so the first page is small: on a
    typical day the few new bookmarks plus one already-seen one fit in it.
    """
    access_token, user_id = auth.get_access_token(username)
    new: list[Tweet] = []
    pagination_token = None
    for page in range(max_pages):
        page_size = FIRST_PAGE_SIZE if page == 0 else 100
        tweets, pagination_token = await list_bookmarks(user_id, access_token, page_size, pagination_token)
        for tweet in tweets:
            if tweet.id in seen:
                return new
            new.append(tweet)
        if not pagination_token:
            break
    return new


def _format_entry(tweet: Tweet, account: str, today: str) -> str:
    quoted = "\n".join(f"> {line}" if line else ">" for line in tweet.text.splitlines())
    return (
        f"### @{tweet.author_handle} ({tweet.author_name}): {tweet.created_at[:10]}\n"
        f"via @{account} · pulled {today} · {tweet.url}\n\n"
        f"{quoted}\n"
    )


async def sync(dry_run: bool = False) -> int:
    out_path = os.environ.get("X_BOOKMARKS_FILE", "")
    if not out_path:
        raise RuntimeError("X_BOOKMARKS_FILE not set. Add it to ~/.config/x-api/.env")
    out_file = Path(out_path).expanduser()
    max_pages = int(os.environ.get("X_BOOKMARKS_MAX_PAGES", "3"))

    accounts = auth.list_accounts()
    if not accounts:
        raise RuntimeError("No authorized accounts. Run: python -m x_api.auth login")

    state = _load_state()
    today = date.today().isoformat()
    total = 0
    failures = 0

    for account in accounts:
        seen_list = state.get(account, [])
        try:
            new = await _fetch_new(account, set(seen_list), max_pages)
        except Exception as e:
            print(f"@{account}: failed: {e}", file=sys.stderr)
            failures += 1
            continue

        print(f"@{account}: {len(new)} new bookmark(s)")
        if not new or dry_run:
            continue

        # Oldest first, so the note reads chronologically top to bottom.
        entries = [_format_entry(t, account, today) for t in reversed(new)]
        if not out_file.exists():
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(NOTE_HEADER)
        with open(out_file, "a") as f:
            f.write("\n" + "\n".join(entries))

        # Save state only after the note is written: a crash duplicates, never drops.
        state[account] = ([t.id for t in new] + seen_list)[:SEEN_LIMIT]
        _save_state(state)
        total += len(new)

    print(f"Appended {total} bookmark(s) to {out_file}" + (" (dry run)" if dry_run else ""))
    return 1 if failures else 0


def main() -> None:
    sys.exit(asyncio.run(sync(dry_run="--dry-run" in sys.argv)))


if __name__ == "__main__":
    main()
