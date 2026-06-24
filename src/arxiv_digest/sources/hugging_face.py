"""系統B: Hugging Face Daily Papers トレンド取得モジュール。

GET https://huggingface.co/api/daily_papers から当日のトレンド論文を取得する。
arXiv ID が取得できた論文のみ返す。エラー時は空リストを返す（系統B全体スキップ）。
"""

from __future__ import annotations

import logging
import re

import requests

from arxiv_digest import config
from arxiv_digest.models import Paper

logger = logging.getLogger(__name__)

# HF API レスポンスタイムアウト（秒）
_TIMEOUT = 30


def fetch_hf_trending() -> list[Paper]:
    """HF Daily Papers API から当日のトレンド論文を取得して返す。

    arXiv ID が含まれないエントリは除外する。
    取得エラー時は空リストを返す（呼び出し元で系統B全体スキップ扱い）。
    """
    try:
        resp = requests.get(config.HF_API_URL, timeout=_TIMEOUT)
        resp.raise_for_status()
        items: list[dict] = resp.json()
    except requests.RequestException as e:
        logger.error("HF Daily Papers API の取得に失敗しました: %s", e)
        return []
    except ValueError as e:
        logger.error("HF Daily Papers API のレスポンスが JSON ではありません: %s", e)
        return []

    papers: list[Paper] = []
    for item in items:
        arxiv_id = _extract_arxiv_id(item)
        if not arxiv_id:
            continue

        title = item.get("paper", {}).get("title") or item.get("title") or ""
        abstract = item.get("paper", {}).get("summary") or item.get("abstract") or ""
        authors_raw = item.get("paper", {}).get("authors") or []
        if isinstance(authors_raw, list):
            authors = [
                a.get("name", "") if isinstance(a, dict) else str(a)
                for a in authors_raw
            ]
        else:
            authors = []

        paper = Paper(
            arxiv_id=arxiv_id,
            title=title,
            abstract=abstract,
            authors=authors,
            arxiv_url=f"https://arxiv.org/abs/{arxiv_id}",
            source="system_b",
            star_delta=None,
        )
        papers.append(paper)

    logger.info("HF Daily Papers 取得完了: %d 件", len(papers))
    return papers


def get_github_url(arxiv_id: str) -> str | None:
    """arXiv ID に紐付く GitHub リポジトリ URL を HF Papers API から返す。

    GET https://huggingface.co/api/papers/{arxiv_id} の ``githubRepo`` を採用する。
    取得失敗（404・タイムアウト・非JSON・リポジトリ未登録）は None を返す（スキップ扱い）。
    Papers With Code 終了に伴う後継経路。
    """
    # バージョン接尾辞（例: "2406.12345v2"）は HF が受け付けないため除去する
    clean_id = re.sub(r"v\d+$", "", arxiv_id.strip())
    url = f"{config.HF_PAPER_API_URL}{clean_id}"
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        if resp.status_code == 404:
            logger.debug("HF Papers: arxiv_id=%s が見つかりませんでした", arxiv_id)
            return None
        resp.raise_for_status()
        data: dict = resp.json()
    except requests.RequestException as e:
        logger.warning("HF Papers API エラー (arxiv_id=%s): %s", arxiv_id, e)
        return None
    except ValueError as e:
        logger.warning(
            "HF Papers API レスポンスが JSON ではありません (arxiv_id=%s): %s", arxiv_id, e
        )
        return None

    github_url = data.get("githubRepo")
    if github_url and isinstance(github_url, str):
        return github_url.strip()
    return None


def _extract_arxiv_id(item: dict) -> str | None:
    """HF API レスポンスの1エントリから arxiv_id を抽出する。

    HF API のレスポンス構造:
      - item["paper"]["id"] が arXiv ID（例: "2406.12345"）
      - item["id"] に URL 形式で含まれることもある
    """
    # パターン1: item["paper"]["id"]
    paper_obj = item.get("paper", {})
    if isinstance(paper_obj, dict):
        paper_id = paper_obj.get("id")
        if paper_id and isinstance(paper_id, str):
            return paper_id.strip()

    # パターン2: item["id"] が arXiv ID 形式
    item_id = item.get("id")
    if item_id and isinstance(item_id, str):
        # "2406.12345" のような形式かチェック
        stripped = item_id.strip()
        if _looks_like_arxiv_id(stripped):
            return stripped

    return None


def _looks_like_arxiv_id(s: str) -> bool:
    """文字列が arXiv ID 形式（YYMM.NNNNN）かどうかを簡易チェックする。"""
    import re
    return bool(re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", s))
