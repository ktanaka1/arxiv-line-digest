"""tests/test_dedup.py

store/dedup.py のユニットテスト。
data/notified.json には一切触れず、tmp_path + 環境変数差し替えで完結させる。
"""

from __future__ import annotations

import json
import os

import pytest

from arxiv_digest import config
from arxiv_digest.models import NotifiedRecord
from arxiv_digest.store import dedup


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


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
# load_notified
# ---------------------------------------------------------------------------


class TestLoadNotified:
    def test_file_not_exist_returns_empty(self, tmp_path, monkeypatch):
        """ファイルが存在しない場合は空リストを返す。"""
        missing = str(tmp_path / "notified.json")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", missing)
        result = dedup.load_notified()
        assert result == []

    def test_empty_array_returns_empty(self, tmp_path, monkeypatch):
        """空の JSON 配列 `[]` を読んだ場合は空リストを返す。"""
        path = tmp_path / "notified.json"
        path.write_text("[]", encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))
        result = dedup.load_notified()
        assert result == []

    def test_normal_records(self, tmp_path, monkeypatch):
        """正常なレコードが含まれる場合は NotifiedRecord のリストを返す。"""
        records = [
            {
                "arxiv_id": "2406.00001",
                "notified_at": "2026-06-19",
                "source": "system_a",
                "score": 8,
                "star_delta": None,
                "github_url": None,
                "stars_last_checked": None,
                "stars_checked_at": None,
            },
            {
                "arxiv_id": "2406.00002",
                "notified_at": "2026-06-18",
                "source": "system_b",
                "score": None,
                "star_delta": 73,
                "github_url": "https://github.com/org/repo",
                "stars_last_checked": 1234,
                "stars_checked_at": "2026-06-18",
            },
        ]
        path = tmp_path / "notified.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        result = dedup.load_notified()
        assert len(result) == 2
        assert result[0].arxiv_id == "2406.00001"
        assert result[0].score == 8
        assert result[1].arxiv_id == "2406.00002"
        assert result[1].github_url == "https://github.com/org/repo"

    def test_invalid_json_returns_empty(self, tmp_path, monkeypatch):
        """不正 JSON の場合は空リストを返し、例外を上げない。"""
        path = tmp_path / "notified.json"
        path.write_text("{broken json!!!}", encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))
        result = dedup.load_notified()
        assert result == []

    def test_missing_required_key_returns_empty(self, tmp_path, monkeypatch):
        """必須キーが欠けているレコードがある場合は空リストを返す。"""
        path = tmp_path / "notified.json"
        # arxiv_id が欠けている
        path.write_text('[{"notified_at": "2026-06-19"}]', encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))
        result = dedup.load_notified()
        assert result == []


# ---------------------------------------------------------------------------
# get_notified_ids
# ---------------------------------------------------------------------------


class TestGetNotifiedIds:
    def test_returns_set_of_arxiv_ids(self, tmp_path, monkeypatch):
        """通知済み arxiv_id のセットが正しく返る。"""
        records = [
            make_record(arxiv_id="2406.00001").to_dict(),
            make_record(arxiv_id="2406.00002").to_dict(),
        ]
        path = tmp_path / "notified.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        ids = dedup.get_notified_ids()
        assert ids == {"2406.00001", "2406.00002"}

    def test_empty_file_returns_empty_set(self, tmp_path, monkeypatch):
        """ファイルが存在しない場合は空セットを返す。"""
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(tmp_path / "notified.json"))
        ids = dedup.get_notified_ids()
        assert ids == set()


# ---------------------------------------------------------------------------
# add_record
# ---------------------------------------------------------------------------


class TestAddRecord:
    def test_adds_record_to_empty_file(self, tmp_path, monkeypatch):
        """空ファイル（存在しない）にレコードを追記できる。"""
        path = tmp_path / "notified.json"
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        rec = make_record(arxiv_id="2406.99999")
        dedup.add_record(rec)

        result = dedup.load_notified()
        assert len(result) == 1
        assert result[0].arxiv_id == "2406.99999"

    def test_appends_to_existing_records(self, tmp_path, monkeypatch):
        """既存レコードがある場合に1件追記される。"""
        existing = [make_record(arxiv_id="2406.00001").to_dict()]
        path = tmp_path / "notified.json"
        path.write_text(json.dumps(existing), encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        dedup.add_record(make_record(arxiv_id="2406.00002"))
        result = dedup.load_notified()
        assert len(result) == 2
        assert {r.arxiv_id for r in result} == {"2406.00001", "2406.00002"}

    def test_duplicate_arxiv_id_is_not_added(self, tmp_path, monkeypatch):
        """同一 arxiv_id が既に存在する場合は上書き・追記しない。"""
        existing = [make_record(arxiv_id="2406.00001", score=8).to_dict()]
        path = tmp_path / "notified.json"
        path.write_text(json.dumps(existing), encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        dedup.add_record(make_record(arxiv_id="2406.00001", score=9))
        result = dedup.load_notified()
        assert len(result) == 1
        assert result[0].score == 8  # 元の値が保持される


# ---------------------------------------------------------------------------
# get_star_snapshot
# ---------------------------------------------------------------------------


class TestGetStarSnapshot:
    def test_returns_snapshot_for_existing_arxiv_id(self, tmp_path, monkeypatch):
        """github_url ありのレコードからスナップショットが取れる。"""
        rec = make_record(
            arxiv_id="2406.00001",
            github_url="https://github.com/org/repo",
            stars_last_checked=500,
            stars_checked_at="2026-06-19",
        )
        path = tmp_path / "notified.json"
        path.write_text(json.dumps([rec.to_dict()]), encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        stars, checked_at = dedup.get_star_snapshot("2406.00001")
        assert stars == 500
        assert checked_at == "2026-06-19"

    def test_returns_none_none_for_missing_arxiv_id(self, tmp_path, monkeypatch):
        """存在しない arxiv_id を指定した場合は (None, None) を返す。"""
        path = tmp_path / "notified.json"
        path.write_text("[]", encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        stars, checked_at = dedup.get_star_snapshot("9999.99999")
        assert stars is None
        assert checked_at is None

    def test_returns_none_none_when_stars_not_set(self, tmp_path, monkeypatch):
        """stars_last_checked が未設定のレコードは (None, None) を返す。"""
        rec = make_record(arxiv_id="2406.00001", stars_last_checked=None, stars_checked_at=None)
        path = tmp_path / "notified.json"
        path.write_text(json.dumps([rec.to_dict()]), encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        stars, checked_at = dedup.get_star_snapshot("2406.00001")
        assert stars is None
        assert checked_at is None


# ---------------------------------------------------------------------------
# update_star_snapshot
# ---------------------------------------------------------------------------


class TestUpdateStarSnapshot:
    def test_updates_existing_record(self, tmp_path, monkeypatch):
        """stars_last_checked と stars_checked_at が更新される。"""
        rec = make_record(
            arxiv_id="2406.00001",
            github_url="https://github.com/org/repo",
            stars_last_checked=100,
            stars_checked_at="2026-06-18",
        )
        path = tmp_path / "notified.json"
        path.write_text(json.dumps([rec.to_dict()]), encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        dedup.update_star_snapshot("2406.00001", stars=200, checked_at="2026-06-19")

        stars, checked_at = dedup.get_star_snapshot("2406.00001")
        assert stars == 200
        assert checked_at == "2026-06-19"

    def test_noop_for_missing_arxiv_id(self, tmp_path, monkeypatch):
        """存在しない arxiv_id を指定しても例外にならない。"""
        path = tmp_path / "notified.json"
        path.write_text("[]", encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        # 例外が上がらないことだけ確認
        dedup.update_star_snapshot("9999.99999", stars=100, checked_at="2026-06-19")
        assert dedup.load_notified() == []


# ---------------------------------------------------------------------------
# get_star_watchlist
# ---------------------------------------------------------------------------


class TestGetStarWatchlist:
    def test_returns_only_records_with_github_url(self, tmp_path, monkeypatch):
        """github_url が None でないレコードだけ返る。"""
        records = [
            make_record(arxiv_id="2406.00001", github_url="https://github.com/org/repo1").to_dict(),
            make_record(arxiv_id="2406.00002", github_url=None).to_dict(),
            make_record(arxiv_id="2406.00003", github_url="https://github.com/org/repo3").to_dict(),
        ]
        path = tmp_path / "notified.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        watchlist = dedup.get_star_watchlist()
        assert len(watchlist) == 2
        ids = {r.arxiv_id for r in watchlist}
        assert ids == {"2406.00001", "2406.00003"}

    def test_empty_when_no_github_urls(self, tmp_path, monkeypatch):
        """全レコードの github_url が None の場合は空リストを返す。"""
        records = [
            make_record(arxiv_id="2406.00001", github_url=None).to_dict(),
        ]
        path = tmp_path / "notified.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        monkeypatch.setenv("NOTIFIED_JSON_PATH", str(path))

        watchlist = dedup.get_star_watchlist()
        assert watchlist == []
