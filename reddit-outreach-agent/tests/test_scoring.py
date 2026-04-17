import pytest
from agent import parse_score_response, should_skip_post, ScoredPost


def test_parse_valid_score_response():
    raw = '{"relevance_score": 8, "reasoning": "User describes chronic insomnia.", "suggested_angle": "Mention CBT-I tracking."}'
    result = parse_score_response("abc123", raw)
    assert isinstance(result, ScoredPost)
    assert result.post_id == "abc123"
    assert result.relevance_score == 8
    assert "insomnia" in result.reasoning
    assert result.suggested_angle != ""


def test_parse_score_below_threshold_returns_none():
    raw = '{"relevance_score": 3, "reasoning": "Tangentially related.", "suggested_angle": ""}'
    result = parse_score_response("abc124", raw)
    assert result is None


def test_parse_score_at_threshold_included():
    raw = '{"relevance_score": 5, "reasoning": "Moderate fit.", "suggested_angle": "Soft mention."}'
    result = parse_score_response("abc125", raw)
    assert result is not None
    assert result.relevance_score == 5


def test_parse_malformed_json_returns_none():
    result = parse_score_response("abc126", "not json at all")
    assert result is None


def test_parse_missing_fields_returns_none():
    result = parse_score_response("abc127", '{"relevance_score": 7}')
    assert result is None


def test_nsfw_post_skipped():
    post = {"id": "xyz", "over_18": True, "title": "anything"}
    assert should_skip_post(post) is True


def test_non_nsfw_post_not_skipped():
    post = {"id": "xyz", "over_18": False, "title": "I can't sleep"}
    assert should_skip_post(post) is False


def test_nsfw_flag_missing_treated_as_safe():
    post = {"id": "xyz", "title": "I can't sleep"}
    assert should_skip_post(post) is False
