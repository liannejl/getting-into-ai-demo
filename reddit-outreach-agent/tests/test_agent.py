import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent import parse_plan_response, deduplicate_posts, AgentPlan


def test_parse_plan_response_valid():
    raw = '{"subreddits": ["r/insomnia", "r/sleep"], "keywords": ["can\'t fall asleep", "wake up 3am"]}'
    plan = parse_plan_response(raw)
    assert isinstance(plan, AgentPlan)
    assert len(plan.subreddits) >= 1
    assert len(plan.keywords) >= 1


def test_parse_plan_response_malformed_returns_none():
    plan = parse_plan_response("not json")
    assert plan is None


def test_parse_plan_response_missing_fields_returns_none():
    plan = parse_plan_response('{"subreddits": ["r/insomnia"]}')
    assert plan is None


def test_deduplicate_posts_removes_duplicates():
    posts = [
        {"id": "1", "title": "Can't sleep"},
        {"id": "2", "title": "Insomnia help"},
        {"id": "1", "title": "Can't sleep"},
    ]
    result = deduplicate_posts(posts)
    assert len(result) == 2
    ids = [p["id"] for p in result]
    assert ids.count("1") == 1


def test_deduplicate_posts_empty():
    assert deduplicate_posts([]) == []


def test_deduplicate_posts_no_duplicates_unchanged():
    posts = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    assert len(deduplicate_posts(posts)) == 3
