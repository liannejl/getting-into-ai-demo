import asyncio
import queue
import threading
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent import (
    AgentError,
    Done,
    PlanReady,
    PostScored,
    run_agent,
)


def iter_agent_events():
    """Run the async agent in a background thread and yield events synchronously."""
    event_queue: queue.Queue = queue.Queue()

    async def collect():
        try:
            async for event in run_agent():
                event_queue.put(event)
        except Exception as e:
            event_queue.put(AgentError(message=str(e)))
        finally:
            event_queue.put(None)  # sentinel

    def run_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(collect())
        finally:
            loop.close()

    thread = threading.Thread(target=run_thread, daemon=True)
    thread.start()

    while True:
        event = event_queue.get()
        if event is None:
            break
        yield event

    thread.join()


st.set_page_config(page_title="Reddit Outreach Agent", layout="wide")
st.title("Reddit Outreach Agent")
st.caption("Finds Reddit posts where our sleep coaching app is a natural fit.")

if st.button("Find Opportunities", type="primary"):
    status = st.empty()
    plan_container = st.container()
    results_container = st.container()

    status.info("Planning search strategy...")

    for event in iter_agent_events():
        if isinstance(event, PlanReady):
            with plan_container:
                st.subheader("Search Plan")
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**Subreddits**")
                    for sub in event.plan.subreddits:
                        st.write(f"- {sub}")
                with col2:
                    st.write("**Keywords**")
                    for kw in event.plan.keywords:
                        st.write(f"- {kw}")
            status.info("Browsing Reddit...")

        elif isinstance(event, PostScored):
            post = event.scored_post
            score = post.relevance_score
            color = "🟢" if score >= 8 else "🟡"
            with results_container:
                with st.expander(
                    f"{color} [{score}/10] {post.title} — {post.subreddit}",
                    expanded=score >= 8,
                ):
                    st.write(f"**Reasoning:** {post.reasoning}")
                    st.write(f"**Suggested angle:** {post.suggested_angle}")
                    if post.url:
                        st.write(f"[View post]({post.url})")

        elif isinstance(event, Done):
            status.success(f"Done — found {event.total_scored} relevant posts.")

        elif isinstance(event, AgentError):
            status.error(f"Error: {event.message}")
