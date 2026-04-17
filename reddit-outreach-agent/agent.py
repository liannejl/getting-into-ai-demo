import json
import os
import uuid
from dataclasses import dataclass, asdict
from typing import AsyncIterator

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tracing import start_run_trace, start_span, end_span

MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
RELEVANCE_THRESHOLD = 5

PRODUCT_DESCRIPTION = """
AI-powered sleep coaching app. Helps people struggling with sleep: insomnia,
waking at night, trouble falling asleep, sleep anxiety, irregular schedules.
Features: CBT-I techniques, sleep tracking, personalized coaching, habit building.
Ideal customers: people who want to improve their sleep quality naturally.
"""

PLAN_SYSTEM_PROMPT = """You are a Reddit research strategist. Given a product description, output a JSON
plan identifying the best subreddits where the target customer would post about their problems.

Output ONLY valid JSON in this exact format:
{"subreddits": ["r/insomnia", ...], "keywords": ["can't fall asleep", ...]}

Include 8-12 subreddits and 6-10 keywords. Focus on communities where someone struggling with
sleep would seek help. Keywords are used to filter posts for relevance."""

SCORE_SYSTEM_PROMPT = """You are evaluating Reddit posts to determine if a sleep coaching app could
genuinely help the poster. Score the post for relevance (0-10) where:
- 8-10: Person is clearly struggling with sleep and seeking solutions
- 5-7: Person mentions sleep issues but engagement may feel forced
- 0-4: Not a genuine fit (venting, already solved, unrelated)

Output ONLY valid JSON in this exact format:
{"relevance_score": 7, "reasoning": "...", "suggested_angle": "..."}

Be honest - only score >=5 if a helpful, non-spammy response mentioning the app would genuinely add value."""


@dataclass
class AgentPlan:
    subreddits: list[str]
    keywords: list[str]


@dataclass
class ScoredPost:
    post_id: str
    title: str
    subreddit: str
    url: str
    relevance_score: int
    reasoning: str
    suggested_angle: str


@dataclass
class PlanReady:
    plan: AgentPlan


@dataclass
class PostFound:
    post: dict


@dataclass
class PostScored:
    scored_post: ScoredPost


@dataclass
class Done:
    total_scored: int


@dataclass
class AgentError:
    message: str


AgentEvent = PlanReady | PostFound | PostScored | Done | AgentError


def parse_plan_response(raw: str) -> AgentPlan | None:
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
        if "subreddits" not in data or "keywords" not in data:
            return None
        return AgentPlan(subreddits=data["subreddits"], keywords=data["keywords"])
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


def parse_score_response(post_id: str, raw: str) -> ScoredPost | None:
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
        required = {"relevance_score", "reasoning", "suggested_angle"}
        if not required.issubset(data.keys()):
            return None
        score = int(data["relevance_score"])
        if score < RELEVANCE_THRESHOLD:
            return None
        return ScoredPost(
            post_id=post_id,
            title=data.get("title", ""),
            subreddit=data.get("subreddit", ""),
            url=data.get("url", ""),
            relevance_score=score,
            reasoning=data["reasoning"],
            suggested_angle=data["suggested_angle"],
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def should_skip_post(post: dict) -> bool:
    return bool(post.get("over_18", False))


def deduplicate_posts(posts: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result = []
    for post in posts:
        pid = post.get("id", "")
        if pid and pid not in seen:
            seen.add(pid)
            result.append(post)
    return result


async def _plan_search(client: anthropic.AsyncAnthropic, product_description: str) -> AgentPlan:
    response = await client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=PLAN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Product:\n{product_description}"}],
    )
    raw = response.content[0].text
    plan = parse_plan_response(raw)
    if not plan:
        return AgentPlan(
            subreddits=["r/insomnia", "r/sleep", "r/anxiety", "r/sleepapnea"],
            keywords=["can't sleep", "insomnia", "waking up", "trouble falling asleep"],
        )
    return plan


def _parse_mcp_posts(result) -> list[dict]:
    """Parse posts from an MCP tool result."""
    if not result.content:
        return []
    raw = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "posts" in data:
        return data["posts"]
    return []


async def _browse_subreddit(session: ClientSession, subreddit: str, limit: int = 15) -> list[dict]:
    """Fetch hot and top posts from a subreddit."""
    sub = subreddit.lstrip("r/")
    posts: list[dict] = []
    for tool in ("get_subreddit_hot_posts", "get_subreddit_top_posts"):
        try:
            result = await session.call_tool(tool, {"subreddit_name": sub, "limit": limit})
            posts.extend(_parse_mcp_posts(result))
        except Exception:
            pass
    return posts


async def _score_post(
    client: anthropic.AsyncAnthropic,
    post: dict,
    product_description: str,
    keywords: list[str] | None = None,
) -> ScoredPost | None:
    title = post.get("title", "")
    body = post.get("selftext", post.get("body", ""))[:1000]
    subreddit = post.get("subreddit", post.get("subreddit_name_prefixed", ""))
    post_id = post.get("id", "")
    url = post.get("url", post.get("permalink", ""))

    keyword_hint = ""
    if keywords:
        keyword_hint = f"Relevance keywords: {', '.join(keywords)}\n"

    response = await client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=SCORE_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Product: {product_description}\n"
                    f"{keyword_hint}"
                    f"Post title: {title}\n"
                    f"Subreddit: {subreddit}\n"
                    f"Post body: {body}\n\n"
                    "Score this post."
                ),
            }
        ],
    )
    raw = response.content[0].text
    scored = parse_score_response(post_id, raw)
    if scored:
        scored.title = title
        scored.subreddit = subreddit
        scored.url = url
    return scored


async def run_agent(product_description: str = PRODUCT_DESCRIPTION) -> AsyncIterator[AgentEvent]:
    run_id = str(uuid.uuid4())
    trace = start_run_trace(run_id)

    uvx_path = os.environ.get("UVX_PATH", "/usr/local/bin/uvx")
    server_params = StdioServerParameters(
        command=uvx_path,
        args=["mcp-server-reddit"],
        env={
            "REDDIT_CLIENT_ID": os.environ.get("REDDIT_CLIENT_ID", ""),
            "REDDIT_CLIENT_SECRET": os.environ.get("REDDIT_CLIENT_SECRET", ""),
            "REDDIT_USERNAME": os.environ.get("REDDIT_USERNAME", ""),
            "REDDIT_PASSWORD": os.environ.get("REDDIT_PASSWORD", ""),
            "REDDIT_USER_AGENT": os.environ.get("REDDIT_USER_AGENT", "somnia-agent/1.0"),
        },
    )

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Phase 1: Planning
                plan_span = start_span(trace, "planning", {"product": product_description})
                plan = await _plan_search(client, product_description)
                end_span(plan_span, {"subreddits": plan.subreddits, "queries": plan.queries})
                yield PlanReady(plan=plan)

                # Phase 2: Browsing
                search_span = start_span(trace, "browsing", asdict(plan))
                all_posts: list[dict] = []
                for subreddit in plan.subreddits:
                    posts = await _browse_subreddit(session, subreddit)
                    all_posts.extend(posts)

                unique_posts = deduplicate_posts(
                    [p for p in all_posts if not should_skip_post(p)]
                )
                end_span(search_span, {"post_count": len(unique_posts)})

                for post in unique_posts:
                    yield PostFound(post=post)

                # Phase 3: Scoring
                score_span = start_span(trace, "scoring", {"post_count": len(unique_posts)})
                scored_posts: list[ScoredPost] = []
                for post in unique_posts:
                    scored = await _score_post(client, post, product_description, plan.keywords)
                    if scored:
                        scored_posts.append(scored)
                        yield PostScored(scored_post=scored)
                end_span(score_span, {"scored_count": len(scored_posts)})

                trace.end()
                yield Done(total_scored=len(scored_posts))

    except Exception as e:
        trace.end()
        yield AgentError(message=str(e))
