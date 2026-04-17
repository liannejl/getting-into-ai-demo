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
python main.py
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

## MCP Servers

`.mcp.json` configures the Langfuse docs MCP server (HTTP) for looking up Langfuse tracing APIs during development. A Reddit MCP server needs to be added here for Reddit interactions.
