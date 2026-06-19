"""通知済み記録の読み書きモジュール。

data/notified.json の操作はすべてこのモジュール経由で行う。
他のモジュールが直接 JSON を読み書きすることを禁止する。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from arxiv_digest import config
from arxiv_digest.models import NotifiedRecord

logger = logging.getLogger(__name__)


def _get_path() -> Path:
    """notified.json の絶対パスを返す。

    環境変数 NOTIFIED_JSON_PATH が設定されている場合はそちらを優先する。
    未設定の場合は config.NOTIFIED_JSON_PATH を使う（repo ルートからの相対パス）。
    """
    override = os.environ.get("NOTIFIED_JSON_PATH")
    if override:
        return Path(override)
    return Path(config.NOTIFIED_JSON_PATH)


def load_notified() -> list[NotifiedRecord]:
    """notified.json を読み込んで NotifiedRecord のリストを返す。

    ファイルが存在しない場合は空リストを返す。
    """
    path = _get_path()
    if not path.exists():
        logger.info("notified.json が見つかりません。空リストを返します: %s", path)
        return []

    try:
        with path.open("r", encoding="utf-8") as f:
            raw: list[dict] = json.load(f)
        return [NotifiedRecord.from_dict(item) for item in raw]
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("notified.json の読み込みに失敗しました: %s", e)
        return []


def save_notified(records: list[NotifiedRecord]) -> None:
    """NotifiedRecord のリストを notified.json に書き込む（全上書き）。"""
    path = _get_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = [r.to_dict() for r in records]
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("notified.json を更新しました (%d 件)", len(records))


def get_notified_ids() -> set[str]:
    """通知済み arxiv_id のセットを返す。重複排除に使う。"""
    return {r.arxiv_id for r in load_notified()}


def add_record(record: NotifiedRecord) -> None:
    """1件追記する。load → append → save で完結する。"""
    records = load_notified()
    # 同一 arxiv_id が既に存在する場合は上書きしない（最初の通知記録を保持）
    existing_ids = {r.arxiv_id for r in records}
    if record.arxiv_id in existing_ids:
        logger.debug("add_record: %s は既に記録済みのためスキップ", record.arxiv_id)
        return
    records.append(record)
    save_notified(records)


def update_star_snapshot(arxiv_id: str, stars: int, checked_at: str) -> None:
    """指定 arxiv_id のスター数スナップショットを更新する。

    stars_last_checked と stars_checked_at を上書きする。
    レコードが存在しない場合は何もしない。
    """
    records = load_notified()
    updated = False
    for r in records:
        if r.arxiv_id == arxiv_id:
            r.stars_last_checked = stars
            r.stars_checked_at = checked_at
            updated = True
            break
    if updated:
        save_notified(records)
    else:
        logger.debug("update_star_snapshot: %s のレコードが見つかりません", arxiv_id)


def get_star_snapshot(arxiv_id: str) -> tuple[int | None, str | None]:
    """指定 arxiv_id の (stars_last_checked, stars_checked_at) を返す。

    レコードが存在しない場合は (None, None) を返す。
    """
    for r in load_notified():
        if r.arxiv_id == arxiv_id:
            return r.stars_last_checked, r.stars_checked_at
    return None, None


def get_star_watchlist() -> list[NotifiedRecord]:
    """github_url が設定されているレコードをすべて返す（スター監視対象）。

    docs/specs/system-b.md: 「系統Aで通知済みの論文のうち、
    GitHub repo が紐付いているものを自動的に監視対象に追加」
    """
    return [r for r in load_notified() if r.github_url is not None]
