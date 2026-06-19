"""系統A: arXiv 新着論文取得モジュール。

arxiv ライブラリで各カテゴリの当日新着を取得し、複数カテゴリ重複を arxiv_id で dedup する。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import arxiv

from arxiv_digest import config
from arxiv_digest.models import Paper

logger = logging.getLogger(__name__)


def _to_arxiv_id(entry_id: str) -> str:
    """arxiv.Result.entry_id（URL形式）から純粋な arxiv_id を抽出する。

    例: "http://arxiv.org/abs/2406.12345v1" -> "2406.12345"
    """
    # entry_id は "http://arxiv.org/abs/XXXX.YYYYYvN" の形式
    base = entry_id.rstrip("/").split("/")[-1]
    # バージョン番号を除去
    return base.split("v")[0]


def fetch_todays_papers() -> list[Paper]:
    """設定カテゴリの直近新着論文を取得して返す。

    投稿日(UTC)が直近 config.ARXIV_LOOKBACK_DAYS 日以内のものを候補とする。
    （「当日ちょうど」だと投稿→公開ラグ・時差・週末でほぼ0件になるため。
      実際の重複排除は notified.json 側で行う。）
    複数カテゴリに跨る論文は arxiv_id で dedup する。
    取得エラーは例外をそのまま上位に伝播させる（呼び出し元で処理）。
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.ARXIV_LOOKBACK_DAYS)).date()
    seen_ids: set[str] = set()
    papers: list[Paper] = []

    client = arxiv.Client(
        page_size=config.ARXIV_MAX_RESULTS,
        delay_seconds=3,
        num_retries=3,
    )

    for category in config.ARXIV_CATEGORIES:
        logger.info("arXiv カテゴリ %s の新着を取得中...", category)

        search = arxiv.Search(
            query=f"cat:{category}",
            max_results=config.ARXIV_MAX_RESULTS,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        try:
            results = list(client.results(search))
        except Exception as e:
            logger.error("カテゴリ %s の取得に失敗しました: %s", category, e)
            raise

        for result in results:
            # 投稿日がルックバック窓より古いものは除外
            submitted_date = result.published
            if submitted_date is not None:
                submitted_day = (
                    submitted_date.date()
                    if hasattr(submitted_date, "date")
                    else submitted_date
                )
                if submitted_day < cutoff:
                    # 投稿日降順ソートなので、窓より古いものが来たら以降は全て古い → 打ち切り
                    logger.debug(
                        "投稿日 %s が窓 (>= %s) より古いため打ち切り", submitted_day, cutoff
                    )
                    break

            arxiv_id = _to_arxiv_id(result.entry_id)

            if arxiv_id in seen_ids:
                logger.debug("重複スキップ: %s", arxiv_id)
                continue
            seen_ids.add(arxiv_id)

            paper = Paper(
                arxiv_id=arxiv_id,
                title=result.title,
                abstract=result.summary,
                authors=[str(a) for a in result.authors],
                arxiv_url=f"https://arxiv.org/abs/{arxiv_id}",
                source="system_a",
            )
            papers.append(paper)

    logger.info("取得完了: %d 件（dedup後）", len(papers))
    return papers
