"""MCP server exposing X API tweet reading."""

import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from x_api.client import read_tweet, search_all_tweets, search_tweets

# Load bearer token from env file
load_dotenv(os.path.expanduser("~/.config/x-api/.env"))

BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "")

mcp = FastMCP("x-api", instructions="Read tweets from X.com by URL or ID.")


@mcp.tool()
async def read_tweet_tool(url_or_id: str) -> str:
    """Read a tweet from X.com given a URL or tweet ID.

    Returns the tweet's author, text, date, and engagement stats.

    Args:
        url_or_id: A full X.com/Twitter URL (e.g. https://x.com/user/status/123)
                   or a raw tweet ID (e.g. 123456789)
    """
    if not BEARER_TOKEN:
        return "Error: X_BEARER_TOKEN not set. Check ~/.config/x-api/.env"

    try:
        tweet = await read_tweet(url_or_id, BEARER_TOKEN)
    except Exception as e:
        return f"Error reading tweet: {e}"

    return (
        f"@{tweet.author_handle} ({tweet.author_name})\n"
        f"{tweet.created_at}\n\n"
        f"{tweet.text}\n\n"
        f"Likes: {tweet.likes} | Retweets: {tweet.retweets} | "
        f"Replies: {tweet.replies} | Quotes: {tweet.quotes}\n"
        f"{tweet.url}"
    )


@mcp.tool()
async def search_tweets_tool(query: str, max_results: int = 10) -> str:
    """Search recent tweets (last 7 days) on X.com by topic or keyword.

    Uses the X API v2 recent search endpoint. Supports the full query syntax
    including operators like `from:`, `has:media`, `-is:retweet`, etc.

    Args:
        query: Search query (e.g. "Python asyncio", "from:karpathy -is:retweet")
        max_results: Number of results to return (10-100, default 10)
    """
    if not BEARER_TOKEN:
        return "Error: X_BEARER_TOKEN not set. Check ~/.config/x-api/.env"

    try:
        tweets = await search_tweets(query, BEARER_TOKEN, max_results)
    except Exception as e:
        return f"Error searching tweets: {e}"

    if not tweets:
        return "No tweets found for that query."

    parts = []
    for tweet in tweets:
        parts.append(
            f"@{tweet.author_handle} ({tweet.author_name})\n"
            f"{tweet.created_at}\n\n"
            f"{tweet.text}\n\n"
            f"Likes: {tweet.likes} | Retweets: {tweet.retweets} | "
            f"Replies: {tweet.replies} | Quotes: {tweet.quotes}\n"
            f"{tweet.url}"
        )
    return "\n\n---\n\n".join(parts)


@mcp.tool()
async def search_all_tweets_tool(
    query: str,
    max_results: int = 10,
    start_time: str | None = None,
    end_time: str | None = None,
) -> str:
    """Search the full X.com tweet archive by topic or keyword.

    Uses the X API v2 full-archive search endpoint. This may cost more than
    recent search, so use it sparingly and prefer narrow queries with date
    bounds when possible. Supports the full query syntax including operators
    like `from:`, `has:media`, `-is:retweet`, etc.

    Args:
        query: Search query (e.g. "from:kepano Obsidian -is:retweet")
        max_results: Number of results to return (10-100, default 10)
        start_time: Optional ISO 8601 start time, e.g. "2026-01-01T00:00:00Z"
        end_time: Optional ISO 8601 end time, e.g. "2026-06-01T00:00:00Z"
    """
    if not BEARER_TOKEN:
        return "Error: X_BEARER_TOKEN not set. Check ~/.config/x-api/.env"

    try:
        tweets = await search_all_tweets(query, BEARER_TOKEN, max_results, start_time, end_time)
    except Exception as e:
        return f"Error searching full archive: {e}"

    if not tweets:
        return "No tweets found for that query."

    parts = []
    for tweet in tweets:
        parts.append(
            f"@{tweet.author_handle} ({tweet.author_name})\n"
            f"{tweet.created_at}\n\n"
            f"{tweet.text}\n\n"
            f"Likes: {tweet.likes} | Retweets: {tweet.retweets} | "
            f"Replies: {tweet.replies} | Quotes: {tweet.quotes}\n"
            f"{tweet.url}"
        )
    return "\n\n---\n\n".join(parts)


if __name__ == "__main__":
    mcp.run()
