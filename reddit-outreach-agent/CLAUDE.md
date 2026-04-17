# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Reddit outreach agent for an AI-powered sleep coaching app. The agent autonomously browses Reddit, identifies posts where the service is a natural fit, and surfaces them for human engagement.

## Setup

```bash
source .venv/bin/activate   # venv already created
pip install -r requirements.txt
```

Required `.env` variables:
- `ANTHROPIC_API_KEY`
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
- Reddit API credentials (or configure via MCP server)

## Running

```bash
streamlit run main.py
```

## Architecture

Per `docs/planning.md`, the agent follows this flow:

1. **Self-directed planning** — Claude decides which subreddits and search queries to use; no hardcoded lists
2. **Reddit MCP server** — all Reddit API interactions go through the `mcp` package, not direct API calls
3. **Relevance scoring** — each post is scored with reasoning before being surfaced
4. **Streaming output** — results stream to a simple UI as they're found
5. **Langfuse tracing** — all agent decisions traced from the start for observability and evaluation

## Gotchas

- Always use the local `.venv` when running Python — the project dependencies are installed there, not globally. Activate with `source .venv/bin/activate` or invoke directly via `.venv/bin/python main.py`.
- `uvx` must be installed (`brew install uv`) for the Reddit MCP server to launch. The agent hardcodes the path to `/usr/local/bin/uvx` (Homebrew default on Intel Mac). Override with `UVX_PATH=/path/to/uvx` in `.env` if needed.
- We are using Langfuse v4 SDK, which has had many breaking changes from previous versions. Always check most up-to-date documentation before writing Langfuse code
- ALWAYS check the actual function names and implementation for SDKs and integrations, like MCP servers. 
NEVER assume you know what the usage looks like in the code.

## MCP Servers

`.mcp.json` configures the Langfuse docs MCP server (HTTP) for looking up Langfuse tracing APIs during development. The Reddit MCP server (`mcp-server-reddit`) is launched as a subprocess via `uvx` inside `agent.py` — it is not configured in `.mcp.json`.
