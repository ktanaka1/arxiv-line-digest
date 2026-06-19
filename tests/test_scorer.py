"""tests/test_scorer.py

scoring/llm_scorer.py のユニットテスト。
Gemini API は unittest.mock.patch で完全にモックする。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from arxiv_digest import config
from arxiv_digest.models import Paper
from arxiv_digest.scoring.llm_scorer import ScoringResult, score_paper


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def make_paper(**kwargs) -> Paper:
    defaults = dict(
        arxiv_id="2406.00001",
        title="Test Paper",
        abstract="Abstract text.",
        authors=["Author A"],
        arxiv_url="https://arxiv.org/abs/2406.00001",
        github_url=None,
        score=None,
        summary=None,
        source="system_a",
        star_delta=None,
        renotify=False,
    )
    defaults.update(kwargs)
    return Paper(**defaults)


def _make_response(payload: dict) -> MagicMock:
    """generate_content の戻り値モックを作る。"""
    mock_response = MagicMock()
    mock_response.text = json.dumps(payload)
    return mock_response


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------


class TestScorePaper:
    @patch("arxiv_digest.scoring.llm_scorer._get_client")
    def test_normal_case_returns_scoring_result(self, mock_get_client):
        """Gemini API が正常なレスポンスを返す場合、ScoringResult が返る。"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_response(
            {"score": 8, "summary": "要約テキスト", "reason": "根拠テキスト"}
        )
        mock_get_client.return_value = mock_client

        paper = make_paper()
        result = score_paper(paper)

        assert isinstance(result, ScoringResult)
        assert result.score == 8
        assert result.summary == "要約テキスト"
        assert result.reason == "根拠テキスト"

    @patch("arxiv_digest.scoring.llm_scorer._get_client")
    def test_score_below_threshold_is_returned_as_is(self, mock_get_client):
        """score=6（閾値未満）の場合でも scorer 自体は値をそのまま返す。

        閾値フィルタは main.py で行うため、scorer はフィルタしない。
        """
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_response(
            {"score": 6, "summary": "閾値未満の要約", "reason": "弱い根拠"}
        )
        mock_get_client.return_value = mock_client

        paper = make_paper()
        result = score_paper(paper)

        assert result.score == 6
        # 閾値チェックは呼び出し元の責務であり、score < SCORE_THRESHOLD になること
        assert result.score < config.SCORE_THRESHOLD

    @patch("arxiv_digest.scoring.llm_scorer._get_client")
    def test_api_error_returns_score_zero(self, mock_get_client):
        """generate_content が例外を投げた場合は score=0 の ScoringResult を返す。"""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("API Unavailable")
        mock_get_client.return_value = mock_client

        paper = make_paper(arxiv_id="2406.error")
        result = score_paper(paper)

        assert result.score == 0
        assert result.summary == ""
        assert result.reason == ""

    @patch("arxiv_digest.scoring.llm_scorer._get_client")
    def test_invalid_json_response_returns_score_zero(self, mock_get_client):
        """API が JSON として不完全なレスポンスを返した場合は score=0 を返す。"""
        mock_response = MagicMock()
        mock_response.text = "not json at all"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        paper = make_paper(arxiv_id="2406.badjson")
        result = score_paper(paper)

        assert result.score == 0
        assert result.summary == ""

    @patch("arxiv_digest.scoring.llm_scorer._get_client")
    def test_json_missing_score_key_returns_score_zero(self, mock_get_client):
        """APIが `{"invalid": true}` のように score キーを欠いたJSONを返した場合は score=0 になる。"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_response({"invalid": True})
        mock_get_client.return_value = mock_client

        paper = make_paper(arxiv_id="2406.nokey")
        result = score_paper(paper)

        # score キーがないので data.get("score", 0) → 0
        assert result.score == 0

    @patch("arxiv_digest.scoring.llm_scorer._get_client")
    def test_get_client_raises_returns_score_zero(self, mock_get_client):
        """_get_client 自体が例外を投げた場合（API KEY なし等）も score=0 を返す。"""
        mock_get_client.side_effect = EnvironmentError("GEMINI_API_KEY が設定されていません")

        paper = make_paper()
        result = score_paper(paper)

        assert result.score == 0
