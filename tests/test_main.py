"""tests/test_main.py

main.py のオーケストレーションロジックのユニットテスト。
外部依存（arXiv/HF/GitHub/LINE/Gemini）はすべてモックする。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest

from arxiv_digest import config
from arxiv_digest.models import NotifiedRecord, Paper
from arxiv_digest.main import run_system_a, run_system_b


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


def make_record(**kwargs) -> NotifiedRecord:
    defaults = dict(
        arxiv_id="2406.00001",
        notified_at="2026-06-19",
        source="system_a",
        score=8,
        star_delta=None,
        github_url=None,
        stars_last_checked=None,
        stars_checked_at=None,
    )
    defaults.update(kwargs)
    return NotifiedRecord(**defaults)


# ---------------------------------------------------------------------------
# 系統A: run_system_a
# ---------------------------------------------------------------------------


class TestRunSystemA:
    @patch("arxiv_digest.main.papers_with_code.get_github_url", return_value=None)
    @patch("arxiv_digest.main.score_paper")
    @patch("arxiv_digest.main.arxiv_source.fetch_todays_papers")
    def test_returns_at_most_system_a_max_papers(
        self, mock_fetch, mock_score, mock_pwc
    ):
        """SYSTEM_A_MAX(=5) を超える候補があっても上位5本だけ返る（スコア降順）。"""
        # 6本の論文を返す（スコアは 10, 9, 8, 7, 7, 7）
        scores = [10, 9, 8, 7, 7, 7]
        papers = [
            make_paper(arxiv_id=f"2406.{i:05d}", title=f"Paper {i}")
            for i in range(6)
        ]
        mock_fetch.return_value = papers

        from arxiv_digest.scoring.llm_scorer import ScoringResult
        mock_score.side_effect = [
            ScoringResult(score=s, summary=f"要約{s}", reason="")
            for s in scores
        ]

        result = run_system_a(notified_ids=set())

        assert len(result) <= config.SYSTEM_A_MAX
        assert len(result) == 5
        # スコア降順になっていることを確認
        result_scores = [p.score for p in result]
        assert result_scores == sorted(result_scores, reverse=True)

    @patch("arxiv_digest.main.papers_with_code.get_github_url", return_value=None)
    @patch("arxiv_digest.main.score_paper")
    @patch("arxiv_digest.main.arxiv_source.fetch_todays_papers")
    def test_papers_below_threshold_are_filtered(
        self, mock_fetch, mock_score, mock_pwc
    ):
        """score < SCORE_THRESHOLD(=7) の論文はフィルタされる。"""
        papers = [
            make_paper(arxiv_id="2406.00001"),
            make_paper(arxiv_id="2406.00002"),
            make_paper(arxiv_id="2406.00003"),
        ]
        mock_fetch.return_value = papers

        from arxiv_digest.scoring.llm_scorer import ScoringResult
        # スコア: 6（閾値未満）、7（閾値ちょうど通過）、8（通過）
        mock_score.side_effect = [
            ScoringResult(score=6, summary="低スコア", reason=""),
            ScoringResult(score=7, summary="ちょうど閾値", reason=""),
            ScoringResult(score=8, summary="高スコア", reason=""),
        ]

        result = run_system_a(notified_ids=set())

        # 6点はフィルタされ、7点以上の2本だけ返る
        assert len(result) == 2
        for p in result:
            assert p.score >= config.SCORE_THRESHOLD

    @patch("arxiv_digest.main.papers_with_code.get_github_url", return_value=None)
    @patch("arxiv_digest.main.score_paper")
    @patch("arxiv_digest.main.arxiv_source.fetch_todays_papers")
    def test_already_notified_papers_are_excluded(
        self, mock_fetch, mock_score, mock_pwc
    ):
        """通知済み arxiv_id の論文は採点前に除外される。"""
        papers = [
            make_paper(arxiv_id="2406.00001"),  # 通知済み
            make_paper(arxiv_id="2406.00002"),  # 未通知
        ]
        mock_fetch.return_value = papers

        from arxiv_digest.scoring.llm_scorer import ScoringResult
        # 採点が呼ばれるのは未通知の1本のみ
        mock_score.return_value = ScoringResult(score=8, summary="新着", reason="")

        result = run_system_a(notified_ids={"2406.00001"})

        # 採点は1回だけ呼ばれる
        assert mock_score.call_count == 1
        assert len(result) == 1
        assert result[0].arxiv_id == "2406.00002"


# ---------------------------------------------------------------------------
# 系統B: run_system_b
# ---------------------------------------------------------------------------


class TestRunSystemB:
    @patch("arxiv_digest.main.papers_with_code.get_github_url", return_value=None)
    @patch("arxiv_digest.main._collect_star_candidates", return_value=[])
    @patch("arxiv_digest.main.hugging_face.fetch_hf_trending")
    def test_notified_papers_get_renotify_flag(
        self, mock_hf, mock_stars, mock_pwc
    ):
        """系統Bで通知済み ID と一致する論文は renotify=True になる。"""
        paper_known = make_paper(arxiv_id="2406.already", source="system_b")
        paper_new = make_paper(arxiv_id="2406.new", source="system_b")
        mock_hf.return_value = [paper_known, paper_new]

        result = run_system_b(notified_ids={"2406.already"})

        result_by_id = {p.arxiv_id: p for p in result}
        assert result_by_id["2406.already"].renotify is True
        assert result_by_id["2406.new"].renotify is False

    @patch("arxiv_digest.main.papers_with_code.get_github_url", return_value=None)
    @patch("arxiv_digest.main._collect_star_candidates", return_value=[])
    @patch("arxiv_digest.main.hugging_face.fetch_hf_trending")
    def test_returns_at_most_system_b_max(
        self, mock_hf, mock_stars, mock_pwc
    ):
        """SYSTEM_B_MAX(=5) を超える候補があっても上位5本だけ返る。"""
        papers = [
            make_paper(arxiv_id=f"2406.{i:05d}", source="system_b")
            for i in range(8)
        ]
        mock_hf.return_value = papers

        result = run_system_b(notified_ids=set())
        assert len(result) <= config.SYSTEM_B_MAX


# ---------------------------------------------------------------------------
# main() のオーケストレーション: LINE 送信の有無
# ---------------------------------------------------------------------------


class TestMainOrchestration:
    @patch("arxiv_digest.main._git_commit_and_push")
    @patch("arxiv_digest.main._save_results")
    @patch("arxiv_digest.main.line_notify.send_message")
    @patch("arxiv_digest.main.run_system_b", return_value=[])
    @patch("arxiv_digest.main.run_system_a", return_value=[])
    @patch("arxiv_digest.main.dedup.get_notified_ids", return_value=set())
    @patch("arxiv_digest.main.load_dotenv")
    def test_send_message_not_called_when_both_empty(
        self,
        mock_dotenv,
        mock_ids,
        mock_a,
        mock_b,
        mock_send,
        mock_save,
        mock_git,
    ):
        """系統A・系統B 両方が空の場合、LINE send_message は呼ばれない。"""
        from arxiv_digest.main import main

        main()
        mock_send.assert_not_called()

    @patch("arxiv_digest.main._git_commit_and_push")
    @patch("arxiv_digest.main._save_results")
    @patch("arxiv_digest.main.line_notify.send_message")
    @patch("arxiv_digest.main.run_system_b", return_value=[])
    @patch("arxiv_digest.main.run_system_a")
    @patch("arxiv_digest.main.dedup.get_notified_ids", return_value=set())
    @patch("arxiv_digest.main.load_dotenv")
    def test_send_message_called_when_system_a_has_papers(
        self,
        mock_dotenv,
        mock_ids,
        mock_a,
        mock_b,
        mock_send,
        mock_save,
        mock_git,
    ):
        """系統Aに論文がある場合は LINE send_message が呼ばれる。"""
        papers = [make_paper(arxiv_id="2406.00001", score=8, summary="要約")]
        mock_a.return_value = papers

        from arxiv_digest.main import main

        main()
        mock_send.assert_called_once_with(papers, [])

    @patch("arxiv_digest.main._git_commit_and_push")
    @patch("arxiv_digest.main._save_results")
    @patch("arxiv_digest.main.line_notify.send_message")
    @patch("arxiv_digest.main.run_system_b")
    @patch("arxiv_digest.main.run_system_a", return_value=[])
    @patch("arxiv_digest.main.dedup.get_notified_ids", return_value=set())
    @patch("arxiv_digest.main.load_dotenv")
    def test_send_message_called_when_system_b_has_papers(
        self,
        mock_dotenv,
        mock_ids,
        mock_a,
        mock_b,
        mock_send,
        mock_save,
        mock_git,
    ):
        """系統Bに論文がある場合は LINE send_message が呼ばれる。"""
        papers = [make_paper(arxiv_id="2406.00002", source="system_b", star_delta=80)]
        mock_b.return_value = papers

        from arxiv_digest.main import main

        main()
        mock_send.assert_called_once_with([], papers)
