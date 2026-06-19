"""Papers With Code API: arXiv ID から GitHub リポジトリ URL を取得するモジュール。

GET https://paperswithcode.com/api/v1/papers/?arxiv_id={arxiv_id}

非公式 API のため壊れた場合は None を返してスキップする（エラーにしない）。
"""

from __future__ import annotations

import logging

import requests

from arxiv_digest import config

logger = logging.getLogger(__name__)

_TIMEOUT = 15


def get_github_url(arxiv_id: str) -> str | None:
    """arXiv ID に紐付く GitHub リポジトリ URL を返す。

    取得失敗（404・タイムアウト等）は None を返す（スキップ扱い）。
    """
    url = f"{config.PWC_API_URL}?arxiv_id={arxiv_id}"
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        if resp.status_code == 404:
            logger.debug("PWC: arxiv_id=%s が見つかりませんでした", arxiv_id)
            return None
        resp.raise_for_status()
        data: dict = resp.json()
    except requests.RequestException as e:
        logger.warning("PWC API エラー (arxiv_id=%s): %s", arxiv_id, e)
        return None
    except ValueError as e:
        logger.warning("PWC API レスポンスが JSON ではありません (arxiv_id=%s): %s", arxiv_id, e)
        return None

    # レスポンス構造: {"count": N, "results": [{"repository": {"url": "..."}, ...}]}
    results = data.get("results", [])
    if not results:
        return None

    # 最初のリポジトリリンクを採用
    repo = results[0].get("repository") or {}
    if isinstance(repo, dict):
        github_url = repo.get("url")
        if github_url:
            return str(github_url)

    return None
