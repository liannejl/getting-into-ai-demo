import asyncio
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent import RedditOutreachAgent

st.set_page_config(page_title="Somnia Reddit Outreach", layout="wide")
st.title("Somnia — Reddit Outreach Agent")
st.write(
    "Autonomously finds Reddit posts where Somnia (an AI-powered sleep coaching app) "
    "could genuinely help."
)

if "results" not in st.session_state:
    st.session_state.results = None
    st.session_state.trace_id = None

if st.button("Run Search", type="primary"):
    st.session_state.results = None
    st.session_state.trace_id = None

    agent = RedditOutreachAgent()

    events_placeholder = st.empty()
    result_placeholder = st.empty()

    event_log: list[str] = []
    text_buffer = [""]

    def on_event(event: dict) -> None:
        if event["type"] == "text_delta":
            text_buffer[0] += event["text"]
            result_placeholder.markdown(text_buffer[0])
        elif event["type"] == "tool_call":
            event_log.append(f"🔍 `{event['name']}`")
            events_placeholder.markdown(
                "**Agent activity:**\n" + "\n".join(event_log)
            )
        elif event["type"] == "tool_result":
            event_log.append(f"  ↳ results received")
            events_placeholder.markdown(
                "**Agent activity:**\n" + "\n".join(event_log)
            )

    with st.spinner("Agent is searching Reddit…"):
        final_text, trace_id = asyncio.run(agent.run(on_event=on_event))

    events_placeholder.empty()
    st.session_state.results = final_text
    st.session_state.trace_id = trace_id
    st.rerun()

if st.session_state.results:
    st.markdown("---")
    st.markdown(st.session_state.results)

if st.session_state.trace_id:
    host = os.environ.get("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    project_id = os.environ.get("LANGFUSE_PROJECT_ID", "")
    if project_id:
        trace_url = f"{host}/project/{project_id}/traces/{st.session_state.trace_id}"
        st.sidebar.markdown("## Observability")
        st.sidebar.markdown(f"[View Langfuse Trace →]({trace_url})")
