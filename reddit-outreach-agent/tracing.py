import os
from langfuse import Langfuse, get_client

Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)


def start_run_trace(run_id: str):
    lf = get_client()
    return lf.start_observation(name="reddit-outreach-run", metadata={"run_id": run_id})


def start_span(parent, name: str, input: dict):
    return parent.start_observation(name=name, input=input)


def end_span(span, output: dict, metadata: dict = None):
    span.update(output=output, metadata=metadata)
    span.end()
