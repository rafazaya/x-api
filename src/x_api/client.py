"""X API v2 client for tweet lookup."""

import html
import re
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel


class Tweet(BaseModel):
    id: str
    author_name: str
    author_handle: str
    text: str
    created_at: str
    likes: int
    retweets: int
    replies: int
    quotes: int
    url: str


def extract_tweet_id(url_or_id: str) -> str:
    """Extract tweet ID from a URL or return as-is if already an ID."""
    if url_or_id.strip().isdigit():
        return url_or_id.strip()

    parsed = urlparse(url_or_id)
    # Match paths like /user/status/1234567890
    match = re.search(r"/status/(\d+)", parsed.path)
    if match:
        return match.group(1)

    raise ValueError(f"Could not extract tweet ID from: {url_or_id}")


TWEET_PARAMS = {
    "tweet.fields": "created_at,public_metrics,author_id,text,note_tweet,entities",
    "expansions": "author_id",
    "user.fields": "name,username",
}


def _parse_tweets(data: dict) -> list[Tweet]:
    """Turn an X API v2 response (single tweet or list) into Tweet models."""
    if "errors" in data and "data" not in data:
        error = data["errors"][0]
        raise ValueError(f"X API error: {error.get('detail', error.get('message', str(error)))}")
    if "data" not in data:
        return []

    items = data["data"] if isinstance(data["data"], list) else [data["data"]]
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    tweets = []
    for tweet_data in items:
        author = users.get(tweet_data["author_id"], {})
        metrics = tweet_data.get("public_metrics", {})
        # Long posts are truncated in `text`; the full body lives in note_tweet.
        note = tweet_data.get("note_tweet", {})
        text = note.get("text", tweet_data["text"])
        entities = note.get("entities") or tweet_data.get("entities", {})
        for link in entities.get("urls", []):
            if link.get("expanded_url"):
                text = text.replace(link["url"], link["expanded_url"])
        tweets.append(Tweet(
            id=tweet_data["id"],
            author_name=author.get("name", "Unknown"),
            author_handle=author.get("username", "unknown"),
            text=html.unescape(text),
            created_at=tweet_data["created_at"],
            likes=metrics.get("like_count", 0),
            retweets=metrics.get("retweet_count", 0),
            replies=metrics.get("reply_count", 0),
            quotes=metrics.get("quote_count", 0),
            url=f"https://x.com/{author.get('username', '_')}/status/{tweet_data['id']}",
        ))
    return tweets


async def search_tweets(query: str, bearer_token: str, max_results: int = 10) -> list[Tweet]:
    """Search recent tweets (last 7 days) using X API v2."""
    max_results = max(10, min(max_results, 100))

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.x.com/2/tweets/search/recent",
            headers={"Authorization": f"Bearer {bearer_token}"},
            params={
                "query": query,
                "max_results": max_results,
                **TWEET_PARAMS,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    return _parse_tweets(data)


async def search_all_tweets(
    query: str,
    bearer_token: str,
    max_results: int = 10,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[Tweet]:
    """Search the full X archive using X API v2."""
    max_results = max(10, min(max_results, 100))

    params = {
        "query": query,
        "max_results": max_results,
        **TWEET_PARAMS,
    }
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.x.com/2/tweets/search/all",
            headers={"Authorization": f"Bearer {bearer_token}"},
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    return _parse_tweets(data)


async def read_tweet(url_or_id: str, bearer_token: str) -> Tweet:
    """Fetch a tweet by URL or ID using X API v2."""
    tweet_id = extract_tweet_id(url_or_id)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.x.com/2/tweets/{tweet_id}",
            headers={"Authorization": f"Bearer {bearer_token}"},
            params=TWEET_PARAMS,
        )
        resp.raise_for_status()
        data = resp.json()

    return _parse_tweets(data)[0]


async def list_bookmarks(
    user_id: str,
    access_token: str,
    max_results: int = 100,
    pagination_token: str | None = None,
) -> tuple[list[Tweet], str | None]:
    """Fetch one page of a user's bookmarks, newest first.

    Requires an OAuth 2.0 user-context token with bookmark.read. Returns the
    tweets and the next pagination token (None on the last page).
    """
    params = {
        "max_results": max(1, min(max_results, 100)),
        **TWEET_PARAMS,
    }
    if pagination_token:
        params["pagination_token"] = pagination_token

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.x.com/2/users/{user_id}/bookmarks",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    return _parse_tweets(data), data.get("meta", {}).get("next_token")
