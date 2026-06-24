"""エントリポイント。系統A・系統Bのパイプラインを統括して LINE に通知する。

処理フロー:
  1. 系統A: arXiv取得 → 通知済み除外 → Gemini採点 → 閾値フィルタ → 上位5本
  2. 系統B: HF取得 → 通知済み除外（再掲フラグ付与）→ スター急伸チェック → 上位5本
  3. 合算して LINE 通知
  4. notified.json 更新
  5. git commit & push（[skip ci]）
"""

from __future__ import annotations

import logging
import subprocess
import sys
from datetime import date

from dotenv import load_dotenv

from arxiv_digest import config
from arxiv_digest.models import NotifiedRecord, Paper
from arxiv_digest.notify import line as line_notify
from arxiv_digest.scoring.llm_scorer import score_paper
from arxiv_digest.sources import arxiv as arxiv_source
from arxiv_digest.sources import github_stars, hugging_face
from arxiv_digest.store import dedup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 系統A
# ---------------------------------------------------------------------------


def run_system_a(notified_ids: set[str]) -> list[Paper]:
    """系統A パイプラインを実行し、通知対象論文リストを返す。"""
    logger.info("=== 系統A 開始 ===")

    # 1. arXiv 新着取得
    try:
        all_papers = arxiv_source.fetch_todays_papers()
    except Exception as e:
        logger.error("arXiv 取得エラー: %s", e)
        raise

    logger.info("arXiv 取得: %d 件", len(all_papers))

    # 2. 通知済み除外
    candidates = [p for p in all_papers if p.arxiv_id not in notified_ids]
    logger.info("通知済み除外後: %d 件", len(candidates))

    # 3. Gemini 採点
    scored: list[Paper] = []
    for paper in candidates:
        result = score_paper(paper)
        paper.score = result.score
        paper.title_ja = result.title_ja
        paper.summary = result.summary
        logger.info(
            "採点: %s | %d点 | %s", paper.arxiv_id, paper.score, paper.summary[:40]
        )
        if paper.score >= config.SCORE_THRESHOLD:
            scored.append(paper)

    logger.info("閾値 (%d点) 以上: %d 件", config.SCORE_THRESHOLD, len(scored))

    # 4. スコア降順ソート → 上位5本
    scored.sort(key=lambda p: p.score or 0, reverse=True)
    selected = scored[: config.SYSTEM_A_MAX]

    # 5. GitHub URL 補完（HF Papers API）
    for paper in selected:
        github_url = hugging_face.get_github_url(paper.arxiv_id)
        if github_url:
            paper.github_url = github_url
            logger.info("GitHub URL 補完: %s -> %s", paper.arxiv_id, github_url)

    logger.info("系統A 選出: %d 件", len(selected))
    return selected


# ---------------------------------------------------------------------------
# 系統B
# ---------------------------------------------------------------------------


def run_system_b(notified_ids: set[str]) -> list[Paper]:
    """系統B パイプラインを実行し、通知対象論文リストを返す。"""
    logger.info("=== 系統B 開始 ===")

    # --- HF Daily Papers ---
    try:
        hf_papers = hugging_face.fetch_hf_trending()
    except Exception as e:
        logger.error("HF Daily Papers 取得エラー: %s", e)
        hf_papers = []

    logger.info("HF Daily Papers 取得: %d 件", len(hf_papers))

    # --- GitHub スター急伸 ---
    star_candidates = _collect_star_candidates()
    logger.info("スター急伸候補: %d 件", len(star_candidates))

    # --- マージ・arXiv ID で dedup ---
    all_b: list[Paper] = []
    seen_b_ids: set[str] = set()

    for paper in hf_papers + star_candidates:
        if paper.arxiv_id in seen_b_ids:
            continue
        seen_b_ids.add(paper.arxiv_id)
        all_b.append(paper)

    logger.info("系統B マージ後: %d 件", len(all_b))

    # --- 通知済み除外（再掲フラグ付与）---
    # 既存 notified_ids に含まれるものは renotify=True にして残す
    for paper in all_b:
        if paper.arxiv_id in notified_ids:
            paper.renotify = True

    # --- GitHub URL 補完（HF 由来で未取得のもの）---
    for paper in all_b:
        if paper.github_url is None:
            github_url = hugging_face.get_github_url(paper.arxiv_id)
            if github_url:
                paper.github_url = github_url

    # --- スター急伸でない HF 論文は star_delta=None のまま通知 ---
    # star_candidates は既にフィルタ済みなので all_b にそのまま含まれる

    # --- スター増加数降順ソート（None は末尾）→ 上位5本 ---
    all_b.sort(
        key=lambda p: (p.star_delta is not None, p.star_delta or 0),
        reverse=True,
    )
    selected = all_b[: config.SYSTEM_B_MAX]

    logger.info("系統B 選出: %d 件", len(selected))
    return selected


def _collect_star_candidates() -> list[Paper]:
    """notified.json のスター監視対象を確認し、急伸した論文リストを返す。"""
    watchlist = dedup.get_star_watchlist()
    today_str = date.today().isoformat()
    candidates: list[Paper] = []

    for record in watchlist:
        if record.github_url is None:
            continue

        current_stars = github_stars.get_current_stars(record.github_url)
        if current_stars is None:
            continue

        # スナップショット差分で増加量を計算
        prev_stars, _ = dedup.get_star_snapshot(record.arxiv_id)

        if prev_stars is not None:
            star_delta = current_stars - prev_stars
            if github_stars.is_trending(star_delta):
                logger.info(
                    "スター急伸検出: %s (+%d stars)", record.arxiv_id, star_delta
                )
                paper = Paper(
                    arxiv_id=record.arxiv_id,
                    title="",   # ここでは不明。後で補完は行わない（通知済み論文のため）
                    abstract="",
                    authors=[],
                    arxiv_url=f"https://arxiv.org/abs/{record.arxiv_id}",
                    github_url=record.github_url,
                    source="system_b",
                    star_delta=star_delta,
                )
                candidates.append(paper)

        # スナップショットを更新
        dedup.update_star_snapshot(record.arxiv_id, current_stars, today_str)

    return candidates


# ---------------------------------------------------------------------------
# 通知済み記録の更新
# ---------------------------------------------------------------------------


def _save_results(
    system_a_papers: list[Paper],
    system_b_papers: list[Paper],
) -> None:
    """通知した論文を notified.json に記録する。"""
    today_str = date.today().isoformat()

    for paper in system_a_papers:
        record = NotifiedRecord(
            arxiv_id=paper.arxiv_id,
            notified_at=today_str,
            source="system_a",
            score=paper.score,
            star_delta=None,
            github_url=paper.github_url,
            stars_last_checked=None,
            stars_checked_at=None,
        )
        dedup.add_record(record)

    for paper in system_b_papers:
        if paper.renotify:
            # 再掲は既存レコードを更新しない（最初の通知記録を保持）
            continue
        record = NotifiedRecord(
            arxiv_id=paper.arxiv_id,
            notified_at=today_str,
            source="system_b",
            score=None,
            star_delta=paper.star_delta,
            github_url=paper.github_url,
            stars_last_checked=None,
            stars_checked_at=None,
        )
        dedup.add_record(record)


# ---------------------------------------------------------------------------
# git commit & push
# ---------------------------------------------------------------------------


def _git_commit_and_push() -> None:
    """notified.json の変更を git commit & push する。

    GitHub Actions の bot コミットには [skip ci] を付ける。
    """
    try:
        subprocess.run(
            ["git", "add", "data/notified.json"],
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
        )
        if result.returncode == 0:
            logger.info("notified.json に変更がないためコミットをスキップします")
            return

        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "chore: update notified.json [skip ci]",
            ],
            check=True,
            capture_output=True,
        )
        # GitHub Actions の checkout は detached HEAD のため、明示的に main へ push する
        subprocess.run(
            ["git", "push", "origin", "HEAD:main"],
            check=True,
            capture_output=True,
        )
        logger.info("notified.json をコミット & プッシュしました")
    except subprocess.CalledProcessError as e:
        logger.error(
            "git 操作に失敗しました: %s\nstdout: %s\nstderr: %s",
            e,
            e.stdout.decode(errors="replace") if e.stdout else "",
            e.stderr.decode(errors="replace") if e.stderr else "",
        )
        raise


# ---------------------------------------------------------------------------
# メインエントリポイント
# ---------------------------------------------------------------------------


def main() -> None:
    """arxiv-line-digest のメインエントリポイント。"""
    # ローカル実行時に .env を読み込む（GitHub Actions では不要だが害はない）
    load_dotenv()

    logger.info("arxiv-line-digest 開始 (%s)", date.today().isoformat())

    # 通知済み ID をロード（系統A・系統B 共通）
    notified_ids = dedup.get_notified_ids()
    logger.info("通知済み件数: %d", len(notified_ids))

    # 系統A
    system_a_papers = run_system_a(notified_ids)

    # 系統B
    system_b_papers = run_system_b(notified_ids)

    # LINE 通知
    if system_a_papers or system_b_papers:
        line_notify.send_message(system_a_papers, system_b_papers)
    else:
        logger.info("通知対象がないため LINE 送信をスキップします")

    # notified.json 更新
    _save_results(system_a_papers, system_b_papers)

    # git commit & push
    _git_commit_and_push()

    total = len(system_a_papers) + len(system_b_papers)
    logger.info("arxiv-line-digest 完了: 系統A %d 件 / 系統B %d 件（計 %d 件）",
                len(system_a_papers), len(system_b_papers), total)


if __name__ == "__main__":
    main()
