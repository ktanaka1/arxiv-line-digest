"""系統B: GitHub Stars 急伸チェックモジュール。

スナップショット差分方式で「前回確認時からのスター増加量」を計算し、
STAR_DELTA_THRESHOLD 以上なら通知対象と判定する。
"""

from __future__ import annotations

import logging
import os
import re

import requests

from arxiv_digest import config

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"
_TIMEOUT = 15

# GitHub リポジトリ URL から owner/repo を抽出する正規表現
_REPO_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/\s?#]+)",
    re.IGNORECASE,
)


def _extract_owner_repo(github_url: str) -> tuple[str, str] | None:
    """GitHub URL から (owner, repo) タプルを抽出する。

    取得失敗時は None を返す。
    """
    m = _REPO_RE.search(github_url)
    if not m:
        logger.warning("GitHub URL から owner/repo を抽出できませんでした: %s", github_url)
        return None
    owner = m.group(1)
    repo = m.group(2).rstrip(".git")
    return owner, repo


def _build_headers() -> dict[str, str]:
    """GitHub API リクエストヘッダを組み立てる。

    GITHUB_TOKEN が設定されている場合は Authorization ヘッダを付与する。
    """
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_current_stars(github_url: str) -> int | None:
    """GitHub API でリポジトリの現在のスター数を取得する。

    取得失敗時は None を返す（1件の失敗は系統B全体に影響させない）。
    """
    parsed = _extract_owner_repo(github_url)
    if parsed is None:
        return None

    owner, repo = parsed
    api_url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}"

    try:
        resp = requests.get(api_url, headers=_build_headers(), timeout=_TIMEOUT)
        if resp.status_code == 403:
            # レート制限超過
            logger.error("GitHub API レート制限超過。スター急伸判定をスキップします。")
            return None
        if resp.status_code == 404:
            logger.warning("GitHub リポジトリが見つかりません: %s/%s", owner, repo)
            return None
        resp.raise_for_status()
        data: dict = resp.json()
    except requests.RequestException as e:
        logger.warning("GitHub API エラー (%s/%s): %s", owner, repo, e)
        return None
    except ValueError as e:
        logger.warning("GitHub API レスポンスが JSON ではありません (%s/%s): %s", owner, repo, e)
        return None

    stars = data.get("stargazers_count")
    if stars is None:
        return None
    return int(stars)


def is_trending(star_delta: int) -> bool:
    """スター増加量が急伸閾値以上かどうかを判定する。"""
    return star_delta >= config.STAR_DELTA_THRESHOLD
