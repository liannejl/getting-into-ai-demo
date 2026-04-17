import asyncio
import os
from typing import Callable, Optional

import anthropic
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tracer import langfuse

SYSTEM_PROMPT = """You are a Reddit outreach researcher for Somnia, an AI-powered sleep \
coaching app. Target user: someone struggling with sleep who wants tools to help manage it.

Instructions:
1. PLAN — decide which subreddits (r/sleep, r/insomnia, r/anxiety, r/BipolarReddit, \
r/SleepApnea) and queries to use. Think out loud.
2. SEARCH — use tools to search those subreddits.
3. SCORE — rate each post 1-10 with reasoning.
4. RETURN — a ranked markdown list with: title, URL, subreddit, relevance score, \
why it fits, suggested engagement angle.

Rules:
- Skip any post marked NSFW or over_18. Do not include it in results regardless of relevance score."""

TASK_PROMPT = (
    "Find top Reddit posts where Somnia could genuinely help. "
    "Start by planning your search strategy."
)


def _filter_nsfw(result_text: str) -> str:
    """Remove NSFW entries from a Reddit tool result (JSON list or plain text)."""
    import json

    try:
        data = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        # Plain text — drop any line that mentions nsfw/over_18 being true
        lines = result_text.splitlines()
        filtered = [
            l for l in lines
            if not ("over_18: true" in l.lower() or "nsfw: true" in l.lower() or '"nsfw": true' in l.lower())
        ]
        return "\n".join(filtered)

    if isinstance(data, list):
        data = [
            item for item in data
            if not (item.get("over_18") or item.get("nsfw"))
        ]
    elif isinstance(data, dict) and "posts" in data:
        data["posts"] = [
            item for item in data["posts"]
            if not (item.get("over_18") or item.get("nsfw"))
        ]

    return json.dumps(data)


class RedditOutreachAgent:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(max_retries=6)
        self.model = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")

    async def run(
        self, on_event: Optional[Callable] = None
    ) -> tuple[str, str]:
        root = langfuse.start_observation(
            name="reddit-outreach-search",
            as_type="span",
            input={"task": TASK_PROMPT},
        )

        reddit_env = {
            "REDDIT_CLIENT_ID": os.environ["REDDIT_CLIENT_ID"],
            "REDDIT_CLIENT_SECRET": os.environ["REDDIT_CLIENT_SECRET"],
            "REDDIT_USERNAME": os.environ["REDDIT_USERNAME"],
            "REDDIT_PASSWORD": os.environ["REDDIT_PASSWORD"],
            "REDDIT_USER_AGENT": os.environ.get(
                "REDDIT_USER_AGENT", "somnia-outreach-agent/1.0"
            ),
        }

        uvx = os.environ.get("UVX_PATH", "/usr/local/bin/uvx")
        server_params = StdioServerParameters(
            command=uvx,
            args=["mcp-server-reddit"],
            env={**os.environ, **reddit_env},
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    tools_result = await session.list_tools()
                    anthropic_tools = [
                        {
                            "name": t.name,
                            "description": t.description or "",
                            "input_schema": t.inputSchema,
                        }
                        for t in tools_result.tools
                    ]

                    messages = [{"role": "user", "content": TASK_PROMPT}]
                    final_text = ""

                    while True:
                        async with self.client.messages.stream(
                            model=self.model,
                            max_tokens=4096,
                            system=SYSTEM_PROMPT,
                            tools=anthropic_tools,
                            messages=messages,
                        ) as stream:
                            async for event in stream:
                                if (
                                    event.type == "content_block_delta"
                                    and event.delta.type == "text_delta"
                                ):
                                    if on_event:
                                        on_event(
                                            {
                                                "type": "text_delta",
                                                "text": event.delta.text,
                                            }
                                        )
                            response = await stream.get_final_message()

                        messages.append(
                            {"role": "assistant", "content": response.content}
                        )

                        if response.stop_reason == "end_turn":
                            final_text = "".join(
                                b.text
                                for b in response.content
                                if b.type == "text"
                            )
                            break

                        tool_use_blocks = [
                            b for b in response.content if b.type == "tool_use"
                        ]
                        if not tool_use_blocks:
                            break

                        tool_results = []
                        for block in tool_use_blocks:
                            if on_event:
                                on_event(
                                    {
                                        "type": "tool_call",
                                        "name": block.name,
                                        "input": block.input,
                                    }
                                )

                            tool_span = root.start_observation(
                                name=f"tool:{block.name}",
                                as_type="span",
                                input=block.input,
                            )

                            mcp_result = await session.call_tool(
                                block.name, dict(block.input)
                            )
                            result_text = "\n".join(
                                c.text
                                for c in mcp_result.content
                                if hasattr(c, "text")
                            ) or str(mcp_result.content)

                            # Strip NSFW posts from results before Claude sees them
                            result_text = _filter_nsfw(result_text)

                            # Truncate large results to stay under token rate limits
                            max_chars = int(os.environ.get("TOOL_RESULT_MAX_CHARS", "3000"))
                            if len(result_text) > max_chars:
                                result_text = result_text[:max_chars] + "\n...[truncated]"

                            tool_span.update(output=result_text)
                            tool_span.end()

                            if on_event:
                                on_event(
                                    {"type": "tool_result", "name": block.name}
                                )

                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": result_text,
                                    "is_error": bool(mcp_result.isError),
                                }
                            )

                        messages.append(
                            {"role": "user", "content": tool_results}
                        )
                        await asyncio.sleep(2)

        finally:
            root.update(output=final_text if "final_text" in dir() else "")
            root.end()
            langfuse.flush()

        trace_id = getattr(root, "trace_id", None) or root.id
        return final_text, trace_id
