import pytest
from unittest.mock import patch, MagicMock
from tracing import start_run_trace, start_span, end_span


def test_start_run_trace_returns_observation():
    with patch("tracing.get_client") as mock_get_client:
        mock_lf = MagicMock()
        mock_obs = MagicMock()
        mock_obs.id = "obs-123"
        mock_get_client.return_value = mock_lf
        mock_lf.start_observation.return_value = mock_obs

        trace = start_run_trace("run-abc")
        assert trace.id == "obs-123"
        mock_lf.start_observation.assert_called_once()


def test_start_span_creates_child_observation():
    mock_parent = MagicMock()
    mock_child = MagicMock()
    mock_parent.start_observation.return_value = mock_child

    span = start_span(mock_parent, "planning", {"input": "test"})
    assert span is mock_child
    mock_parent.start_observation.assert_called_once_with(name="planning", input={"input": "test"})


def test_end_span_updates_and_ends():
    mock_span = MagicMock()
    end_span(mock_span, {"output": "done"}, {"score": 8})
    mock_span.update.assert_called_once_with(output={"output": "done"}, metadata={"score": 8})
    mock_span.end.assert_called_once()


def test_end_span_no_metadata():
    mock_span = MagicMock()
    end_span(mock_span, {"output": "done"})
    mock_span.update.assert_called_once_with(output={"output": "done"}, metadata=None)
    mock_span.end.assert_called_once()
