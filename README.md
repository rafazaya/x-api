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

Both tools return the tweet's author, text, date, and engagement stats (likes, retweets, replies, quotes).
