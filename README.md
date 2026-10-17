# x-api

An MCP server that lets Claude read public tweets from X.com by URL or tweet ID. Designed for occasional research use with X's pay-as-you-go billing — no monthly subscription required.

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- An X API Bearer Token (see below)

## X API Setup

### 1. Create an X Developer Account

1. Go to https://developer.x.com and sign in with your X account
2. Accept the Developer Agreement and Policy
3. You should see a default app already available on your dashboard

### 2. Generate a Bearer Token

1. Go to your app's **Keys and Tokens** section
2. Generate a **Bearer Token** (App-only token) — this is all you need for reading public tweets
3. Copy it — you'll only see it once

### 3. Set Up Pay-As-You-Go Billing

1. In the Developer Console (https://console.x.com/), go to **Billing**
2. Add a payment method and purchase initial credits ($5 is plenty)
3. Set a spending cap of $1–2/month to prevent surprises

Each tweet read costs roughly $0.005, so $5 in credits lasts a very long time at casual usage.

### 4. Store the Bearer Token

```bash
mkdir -p ~/.config/x-api
echo "X_BEARER_TOKEN=your-bearer-token-here" > ~/.config/x-api/.env
chmod 600 ~/.config/x-api/.env
```

Replace `your-bearer-token-here` with your actual token.

## Installation

```bash
git clone https://github.com/rafazaya/x-api.git
cd x-api
uv sync
```

## MCP Configuration

Add the following to your `.mcp.json` (in your project root or `~/.claude/.mcp.json` for global access):

```json
{
  "mcpServers": {
    "x-api": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/x-api",
        "python",
        "-m",
        "x_api.server"
      ]
    }
  }
}
```

Replace `/path/to/x-api` with the absolute path to your cloned repo.

## Usage

Once configured, Claude can:

**Read tweets** by URL or ID:
- `https://x.com/user/status/123456789`
- `123456789`

**Search recent tweets** (last 7 days) by topic or keyword:
- `"Python asyncio"`
- `"from:karpathy -is:retweet"`

**Search the full tweet archive** by topic or keyword:
- `"from:kepano Obsidian -is:retweet"`
- Use optional `start_time` and `end_time` ISO 8601 bounds for narrower searches
- Use sparingly; this calls X's full-archive search endpoint and may be more expensive than recent search

These tools return the tweet's author, text, date, and engagement stats (likes, retweets, replies, quotes).

**List bookmarks** for an authorized account (see below):
- `list_bookmarks_tool(account="<username>", max_results=20)`
- `account` can be omitted when only one account is authorized

## Bookmarks (OAuth 2.0 user context)

The bearer token can't read bookmarks; X requires a token issued for the account itself. Any number of accounts can authorize the same app.

### Console setup (one-time)

In the developer console, open your app → **User authentication settings** → **Set up**:

- App permissions: **Read**
- Type of App: **Native App** (public client, PKCE, no client secret)
- Callback URI: `http://127.0.0.1:8723/callback`
- Website URL: anything, e.g. this repo

Save, then add the **Client ID** to the env file:

```bash
echo "X_CLIENT_ID=your-client-id" >> ~/.config/x-api/.env
```

### Authorize an account

```bash
uv run python -m x_api.auth login   # prints a URL; open it signed into the account
uv run python -m x_api.auth list    # show authorized accounts
```

The browser must be signed into the account you want to authorize. Repeat per account, switching accounts (or using a private window) in between. Tokens are saved to `~/.config/x-api/tokens/<username>.json` (mode 600).

The callback goes to `127.0.0.1` on the machine running the browser, so if the browser is on another machine, tunnel the port first:

```bash
ssh -L 8723:127.0.0.1:8723 user@server
```

Access tokens last 2 hours and are refreshed automatically. X rotates the refresh token on every refresh; refreshes hold a per-account lock and save the new token atomically, so the MCP server and the sync job can run side by side. If a refresh ever fails, run `login` again for that account.

### Sync bookmarks to a markdown file

`x_api.sync_bookmarks` appends new bookmarks from every authorized account to a markdown file, one entry per bookmark with the author, date, link, and full text. It only fetches and dedupes, with no classification, so it is safe to run unattended.

```bash
echo "X_BOOKMARKS_FILE=/path/to/Social bookmarks.md" >> ~/.config/x-api/.env
uv run python -m x_api.sync_bookmarks            # or --dry-run to only count new items
```

Seen IDs are kept in `~/.local/state/x-api/bookmarks.json`. Each run reads 10 bookmarks per account and pages further only when all of them are new, up to `X_BOOKMARKS_MAX_PAGES` pages (default 3). X only exposes an account's 800 most recent bookmarks.

Example systemd user units for a daily run:

```ini
# ~/.config/systemd/user/x-bookmarks-sync.service
[Unit]
Description=Sync X bookmarks
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=%h/.local/bin/uv run --directory /path/to/x-api python -m x_api.sync_bookmarks

# ~/.config/systemd/user/x-bookmarks-sync.timer
[Timer]
OnCalendar=*-*-* 07:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user enable --now x-bookmarks-sync.timer
```
