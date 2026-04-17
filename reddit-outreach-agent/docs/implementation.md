# Implementation Plan: Reddit Outreach Agent

## Goal

Build an agent that autonomously finds Reddit posts where an AI-powered sleep coaching app would be a natural, non-spammy fit — and surfaces them for a human to engage with.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                  Streamlit UI                    │
│  (streams agent status + scored results live)    │
└──────────────────────┬──────────────────────────┘
                       │ runs
┌──────────────────────▼──────────────────────────┐
│                  agent.py                        │
│  Claude (claude-sonnet-4-6) with tool use        │
│  Phase 1: Planning  → decides subreddits/queries │
│  Phase 2: Searching → calls Reddit MCP tools     │
│  Phase 3: Scoring   → scores each post 0–10      │
└──────┬─────────────────────────┬────────────────┘
       │ MCP stdio subprocess    │ Langfuse SDK
┌──────▼──────────┐   ┌──────────▼───────────────┐
│ mcp-server-     │   │  tracing.py               │
│ reddit (uvx)    │   │  Traces each run; spans   │
│                 │   │  per phase; logs scores   │
└─────────────────┘   └───────────────────────────┘
```

---

## File Structure

```
reddit-outreach-agent/
├── main.py               # Streamlit entry point
├── agent.py              # Agent loop + MCP client setup
├── tracing.py            # Langfuse trace/span helpers
├── tests/
│   ├── test_scoring.py   # Unit tests for scoring logic (write first)
│   ├── test_agent.py     # Agent planning + filtering (mock MCP)
│   └── test_tracing.py   # Tracing helper contract tests
├── docs/
│   ├── planning.md
│   └── implementation.md
├── .env.example
├── requirements.txt
└── CLAUDE.md
```

---

## Phase-by-Phase Agent Flow

### Phase 1 — Planning (no tool calls yet)

Claude receives a system prompt describing the product and is asked to output a JSON search plan:

```json
{
  "subreddits": ["r/sleep", "r/insomnia", "r/anxiety", ...],
  "queries": ["can't fall asleep", "wake up at 3am", ...]
}
```

No hardcoded lists. Claude decides based on product context. This plan is logged as a Langfuse span.

### Phase 2 — Searching

Agent iterates the plan and calls the Reddit MCP tool `search_posts` for each (subreddit, query) pair. Each call:
- Skips posts marked NSFW
- Deduplicates by post ID
- Collects raw post data (title, body, score, author, url, subreddit)

### Phase 3 — Scoring

For each collected post, Claude evaluates relevance using a structured prompt and returns:

```json
{
  "post_id": "...",
  "relevance_score": 7,
  "reasoning": "User describes waking at 3am with racing thoughts...",
  "suggested_angle": "Empathize then mention the app's CBT-I tracking feature"
}
```

Posts scoring < 5 are dropped. NSFW posts are always dropped regardless of score.

### Output

Scored results stream to the Streamlit UI as they're produced. Each result card shows: subreddit, title, score badge, reasoning, suggested angle, and a link to the post.

---

## Module Contracts

### `agent.py`

```python
async def run_agent(product_description: str) -> AsyncIterator[AgentEvent]:
    """Yields AgentEvent objects: PlanReady, PostFound, PostScored, Done, Error."""
```

- Sets up the MCP client subprocess (`uvx mcp-server-reddit`)
- Runs all three phases, yielding events for the UI to consume
- Uses `anthropic` SDK with streaming for Phase 1 and Phase 3

### `tracing.py`

```python
def start_run_trace(run_id: str) -> Trace: ...
def start_span(trace: Trace, name: str, input: dict) -> Span: ...
def end_span(span: Span, output: dict, metadata: dict = None): ...
```

Thin wrappers around Langfuse v4 SDK. Agent code calls these; no Langfuse imports leak into `agent.py`.

### `main.py`

Streamlit app with a single "Run Agent" button. Consumes `run_agent()` events and renders them live using `st.empty()` containers. No agent logic lives here.

---

## Test Plan (TDD — write tests before implementation)

### `tests/test_scoring.py` — write first

Tests for the scoring parsing logic. Use mock Claude responses (no real API calls):
- Parses valid JSON score response correctly
- Handles score < 5 (filtered out)
- Handles malformed JSON gracefully
- NSFW posts return score 0 regardless

### `tests/test_agent.py` — write second

Tests for agent planning and search orchestration. Mock the MCP client:
- Planning phase produces a non-empty list of subreddits and queries
- NSFW posts are filtered before scoring
- Duplicate posts (same ID) are deduplicated
- AgentEvent stream ends with `Done` event

### `tests/test_tracing.py` — write third

Tests for `tracing.py` contract:
- `start_run_trace` returns an object with `.id`
- `end_span` can be called without error given valid span
- Uses Langfuse SDK in a way compatible with v4 API

---

## Environment Variables (`.env`)

```
ANTHROPIC_API_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
UVX_PATH=/usr/local/bin/uvx   # override if not on Homebrew Intel path
```

Reddit credentials are handled by the MCP server — configure via `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` if the MCP server requires them.

---

## Dependencies to Add

```
anthropic
langfuse
streamlit
python-dotenv
mcp
pytest
pytest-asyncio
```

---

## Key Decisions & Tradeoffs

| Decision | Choice | Tradeoff |
|---|---|---|
| Agent model | `claude-haiku-4-5-20251001` | Fast and cheap; ideal for high-volume post scoring at a hackathon |
| Reddit access | MCP server via uvx subprocess | No direct PRAW dependency; relies on uvx being installed |
| Scoring | Separate Claude call per post | More accurate than batch; slower but parallelizable |
| UI | Streamlit | Fast to build; not suitable for production but fine for demo |
| Tracing | Langfuse v4 | Requires checking latest docs — v4 has breaking changes from v3 |

---

## Implementation Order

1. Write all tests (stub implementations so tests fail cleanly)
2. Implement `tracing.py` (simplest, no dependencies)
3. Implement `agent.py` phases 1–3
4. Implement `main.py` Streamlit UI
5. Wire `.env.example` and confirm end-to-end run
