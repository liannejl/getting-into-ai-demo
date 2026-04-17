
## problem statement
Manually finding relevant Reddit conversations to promote your product is slow, inconsistent,
and easy to miss. We need an agent that autonomously browses Reddit, identifies posts where our
service is a natural fit, and surfaces them — ready for a human to engage.

## context
our product is an AI powered sleep coaching app. our ideal customer is someone who is struggling 
with sleep and would like some tools to help them manage their sleep. 

## proposed solution direction
I think this should be built as an AI agent using Claude with tool use. Here is my
  rough thinking on the architecture:

  - Use an existing Reddit MCP server to handle all Reddit API interactions
  - The agent should plan its own search strategy (which subreddits, which queries)
    before making any tool calls
  - Each post should be scored for relevance with reasoning, not just returned raw
  - Add tracing from the start so we can observe and evaluate agent decisions

a proposed tech stack:
  - Python
  - Anthropic SDK (Claude) for the agent
  - Langfuse for tracing and evaluation
  - simple UI to see streaming

some basic requirements: 
- make sure to skip NSFW Reddit content

help me come up with an architecture & implementation plan for my approval before starting to code