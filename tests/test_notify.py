"""tests/test_notify.py

notify/line.py のユニットテスト。
LINE SDK への実ネットワーク通信は発生させない。
"""

from __future__ import annotations

from arxiv_digest.models import Paper
from arxiv_digest.notify.line import build_message, format_system_a, format_system_b


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


# ---------------------------------------------------------------------------
# format_system_a
# ---------------------------------------------------------------------------


class TestFormatSystemA:
    def test_contains_score_summary_arxiv_url(self):
        """score・summary・arxiv_url が含まれる。"""
        paper = make_paper(
            score=8,
            summary="RAGパイプラインを改善する手法。",
            arxiv_url="https://arxiv.org/abs/2406.00001",
        )
        text = format_system_a(paper)

        assert "[8/10]" in text
        assert "RAGパイプラインを改善する手法。" in text
        assert "https://arxiv.org/abs/2406.00001" in text
        assert "🔵🆕" in text
        assert "📄" in text

    def test_github_url_line_present_when_github_url_set(self):
        """github_url がある場合は🐙行が含まれる。"""
        paper = make_paper(
            score=7,
            summary="要約",
            github_url="https://github.com/org/repo",
        )
        text = format_system_a(paper)

        assert "🐙" in text
        assert "https://github.com/org/repo" in text

    def test_github_url_line_absent_when_github_url_is_none(self):
        """github_url が None の場合は🐙行がない。"""
        paper = make_paper(score=7, summary="要約", github_url=None)
        text = format_system_a(paper)

        assert "🐙" not in text

    def test_score_none_shows_question_mark(self):
        """score=None の場合は [?/10] と表示される。"""
        paper = make_paper(score=None, summary="要約")
        text = format_system_a(paper)
        assert "[?/10]" in text

    def test_summary_none_does_not_produce_empty_line(self):
        """summary=None のとき空行が混入しない。"""
        paper = make_paper(score=8, summary=None)
        text = format_system_a(paper)
        # 空行（連続改行）が含まれないこと
        assert "\n\n" not in text


# ---------------------------------------------------------------------------
# format_system_b
# ---------------------------------------------------------------------------


class TestFormatSystemB:
    def test_star_delta_present_shows_star_tag(self):
        """star_delta あり → [+N⭐/7d] が含まれる。"""
        paper = make_paper(source="system_b", star_delta=73, title="LLaMA Fine-Tuning")
        text = format_system_b(paper)

        assert "[+73⭐/7d]" in text
        assert "🟡🌟" in text

    def test_star_delta_none_shows_hf_trend_tag(self):
        """star_delta=None（HF トレンド）→ [HFトレンド] が含まれる。"""
        paper = make_paper(source="system_b", star_delta=None)
        text = format_system_b(paper)

        assert "[HFトレンド]" in text
        assert "[+" not in text

    def test_renotify_true_shows_renotify_tag(self):
        """renotify=True → [再掲] が含まれる。"""
        paper = make_paper(source="system_b", renotify=True, star_delta=None)
        text = format_system_b(paper)

        assert "[再掲]" in text

    def test_renotify_with_star_delta(self):
        """renotify=True かつ star_delta あり → [再掲][+N⭐/7d] が含まれる。"""
        paper = make_paper(source="system_b", renotify=True, star_delta=73)
        text = format_system_b(paper)

        assert "[再掲]" in text
        assert "[+73⭐/7d]" in text
        # [再掲] が [+N⭐/7d] より先に来る
        assert text.index("[再掲]") < text.index("[+73⭐/7d]")

    def test_renotify_false_no_renotify_tag(self):
        """renotify=False の場合は [再掲] が含まれない。"""
        paper = make_paper(source="system_b", renotify=False, star_delta=50)
        text = format_system_b(paper)

        assert "[再掲]" not in text

    def test_github_url_line_present(self):
        """github_url がある場合は🐙行が含まれる。"""
        paper = make_paper(
            source="system_b",
            star_delta=50,
            github_url="https://github.com/org/repo",
        )
        text = format_system_b(paper)
        assert "🐙" in text

    def test_github_url_line_absent(self):
        """github_url が None の場合は🐙行がない。"""
        paper = make_paper(source="system_b", star_delta=50, github_url=None)
        text = format_system_b(paper)
        assert "🐙" not in text


# ---------------------------------------------------------------------------
# build_message
# ---------------------------------------------------------------------------


class TestBuildMessage:
    def test_system_a_before_system_b(self):
        """系統A・系統B の順で結合される。"""
        paper_a = make_paper(
            arxiv_id="2406.00001",
            source="system_a",
            score=9,
            summary="系統A要約",
        )
        paper_b = make_paper(
            arxiv_id="2406.00002",
            source="system_b",
            star_delta=100,
            summary="系統B要約",
        )
        text = build_message([paper_a], [paper_b])

        pos_a = text.index("🔵🆕")
        pos_b = text.index("🟡🌟")
        assert pos_a < pos_b

    def test_blocks_separated_by_blank_line(self):
        """ブランク行（\\n\\n）で区切られる。"""
        paper_a = make_paper(source="system_a", score=8, summary="系統A")
        paper_b = make_paper(arxiv_id="2406.00002", source="system_b", star_delta=50, summary="系統B")
        text = build_message([paper_a], [paper_b])

        assert "\n\n" in text

    def test_only_system_b_when_system_a_is_empty(self):
        """系統Aが0本でも系統Bだけ正しく結合される。"""
        paper_b = make_paper(source="system_b", star_delta=80, summary="系統Bのみ")
        text = build_message([], [paper_b])

        assert "🟡🌟" in text
        assert "🔵🆕" not in text

    def test_only_system_a_when_system_b_is_empty(self):
        """系統Bが0本でも系統Aだけ正しく結合される。"""
        paper_a = make_paper(source="system_a", score=8, summary="系統Aのみ")
        text = build_message([paper_a], [])

        assert "🔵🆕" in text
        assert "🟡🌟" not in text

    def test_multiple_papers_each_separated(self):
        """複数本がそれぞれブランク行で区切られる。"""
        papers_a = [
            make_paper(arxiv_id=f"2406.{i:05d}", score=8, summary=f"要約{i}")
            for i in range(3)
        ]
        text = build_message(papers_a, [])
        # 3ブロック → 2つのブランク行区切り
        assert text.count("\n\n") == 2

    def test_empty_both_returns_empty_string(self):
        """両方空の場合は空文字列を返す。"""
        text = build_message([], [])
        assert text == ""
