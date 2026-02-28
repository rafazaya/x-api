"""X API v2 client for tweet lookup."""

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
                "tweet.fields": "created_at,public_metrics,author_id,text",
                "expansions": "author_id",
                "user.fields": "name,username",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if "errors" in data and "data" not in data:
        error = data["errors"][0]
        raise ValueError(f"X API error: {error.get('detail', error.get('message', str(error)))}")

    if "data" not in data:
        return []

    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    tweets = []
    for tweet_data in data["data"]:
        author = users.get(tweet_data["author_id"], {})
        metrics = tweet_data.get("public_metrics", {})
        tweets.append(Tweet(
            id=tweet_data["id"],
            author_name=author.get("name", "Unknown"),
            author_handle=author.get("username", "unknown"),
            text=tweet_data["text"],
            created_at=tweet_data["created_at"],
            likes=metrics.get("like_count", 0),
            retweets=metrics.get("retweet_count", 0),
            replies=metrics.get("reply_count", 0),
            quotes=metrics.get("quote_count", 0),
            url=f"https://x.com/{author.get('username', '_')}/status/{tweet_data['id']}",
        ))
    return tweets


async def read_tweet(url_or_id: str, bearer_token: str) -> Tweet:
    """Fetch a tweet by URL or ID using X API v2."""
    tweet_id = extract_tweet_id(url_or_id)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.x.com/2/tweets/{tweet_id}",
            headers={"Authorization": f"Bearer {bearer_token}"},
            params={
                "tweet.fields": "created_at,public_metrics,author_id,text",
                "expansions": "author_id",
                "user.fields": "name,username",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if "errors" in data and "data" not in data:
        error = data["errors"][0]
        raise ValueError(f"X API error: {error.get('detail', error.get('message', str(error)))}")

    tweet_data = data["data"]
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    author = users.get(tweet_data["author_id"], {})
    metrics = tweet_data.get("public_metrics", {})

    return Tweet(
        id=tweet_data["id"],
        author_name=author.get("name", "Unknown"),
        author_handle=author.get("username", "unknown"),
        text=tweet_data["text"],
        created_at=tweet_data["created_at"],
        likes=metrics.get("like_count", 0),
        retweets=metrics.get("retweet_count", 0),
        replies=metrics.get("reply_count", 0),
        quotes=metrics.get("quote_count", 0),
        url=f"https://x.com/{author.get('username', '_')}/status/{tweet_data['id']}",
    )
