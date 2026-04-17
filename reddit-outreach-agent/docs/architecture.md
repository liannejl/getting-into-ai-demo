# Reddit Outreach Agent — Architecture & Implementation Plan

## Problem
Manually finding Reddit conversations to promote Somnia (an AI-powered sleep coaching app) is slow and inconsistent. This agent autonomously plans a search strategy, browses Reddit, scores posts for relevance with reasoning, and surfaces them in a Streamlit UI — ready for a human to engage.

---

## Architecture Overview

```
main.py       — Streamlit app: UI, triggers agent, streams output
agent.py      — Agent class: MCP wiring, Claude loop, tool proxying
tracer.py     — Langfuse setup helpers
requirements.txt — add: streamlit
.env.example  — already complete (Reddit + Anthropic + Langfuse keys)
```

The Reddit MCP server (`mcp-server-reddit` via `uvx`) runs as a subprocess. The Python `mcp` package (already in requirements) connects to it via `stdio_client` + `ClientSession`, lists its tools, and proxies Claude's `tool_use` blocks through it.

---

## File-by-File Plan

### `tracer.py`
- Initialize `Langfuse()` (reads `LANGFUSE_*` env vars automatically)
- Export a `make_trace(name)` helper used by the agent

### `agent.py`
**MCP wiring:**
- Use `StdioServerParameters(command="uvx", args=["mcp-server-reddit"], env={...Reddit creds...})`
- Inside `stdio_client` + `ClientSession`, call `session.list_tools()` and convert each to Anthropic tool format (`name`, `description`, `input_schema`)

**Agent loop (async):**
1. Send initial message with `TASK_PROMPT` to Claude with tools attached
2. On each response:
   - Emit text deltas to Streamlit via `on_event` callback
   - If `stop_reason == "end_turn"` → break
   - For each `tool_use` block: open a Langfuse span, call `session.call_tool(name, input)`, append `tool_result` to messages
3. Continue until `end_turn`

**Prompts:**
```
SYSTEM: You are a Reddit outreach researcher for Somnia, an AI-powered sleep
coaching app. Target user: someone struggling with sleep who wants tools to
help manage it.

Instructions:
1. PLAN — decide which subreddits (r/sleep, r/insomnia, r/anxiety,
   r/BipolarReddit, r/SleepApnea) and queries to use. Think out loud.
2. SEARCH — use tools to search those subreddits.
3. SCORE — rate each post 1-10 with reasoning.
4. RETURN — a ranked markdown list with: title, URL, subreddit,
   relevance score, why it fits, suggested engagement angle.

TASK: Find top Reddit posts where Somnia could genuinely help.
Start by planning your search strategy.
```

**Langfuse tracing:**
- One `trace` per agent run
- One `generation` wrapping the full Claude loop
- One `span` per tool call (name = `tool:<tool_name>`, input/output recorded)

### `main.py` — Streamlit UI
- Header + **[Run Search]** button
- On click: `asyncio.run(agent.run(on_event=...))` with a callback that writes to:
  - `st.status("Agent thinking...", expanded=True)` for tool calls and intermediate steps
  - `st.empty()` updated progressively for Claude's text output
- After loop ends: render final ranked results as `st.markdown()`
- Sidebar: Langfuse trace URL for easy observability

---

## Requirements Changes

Add to `requirements.txt`:
```
streamlit
```

`mcp-server-reddit` is **not** a pip package — installed via `uvx` (part of `uv`).
Users need `uv` installed: `brew install uv` or `pip install uv`.

---

## Setup & Verification

```bash
# 1. Install Python deps
pip install -r requirements.txt

# 2. Confirm Reddit MCP server works (auto-installs on first run)
uvx mcp-server-reddit --help

# 3. Fill in credentials
cp .env.example .env
# edit .env with real keys

# 4. Run
streamlit run main.py
```

Then click "Run Search" — you should see:
- Agent planning which subreddits/queries to use
- Tool calls firing for each search
- Scored, ranked results rendered in the browser
- A Langfuse trace with tool call spans in the dashboard

---

## Model
`claude-sonnet-4-6` — good balance of speed and reasoning for multi-turn tool use loops.
