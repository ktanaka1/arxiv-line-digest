"""データクラス定義。docs/specs/system-a.md の Paper と NotifiedRecord を定義する。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Paper:
    """1本の論文を表す。系統A・系統B 共通。"""

    arxiv_id: str          # "2406.12345"
    title: str
    abstract: str
    authors: list[str]
    arxiv_url: str         # "https://arxiv.org/abs/2406.12345"
    github_url: str | None = None  # Papers With Code 経由（系統Bで設定）
    score: int | None = None       # Gemini採点結果（系統Aで採点後に設定）
    summary: str | None = None     # Gemini日本語要約（採点後に設定）
    source: str = "system_a"       # "system_a" or "system_b"
    star_delta: int | None = None  # 系統Bのみ（7日間スター増加数）
    renotify: bool = False         # 再掲フラグ（系統Aで通知済みが系統Bで再浮上）


@dataclass
class NotifiedRecord:
    """notified.json の1レコード分。通知済み論文の永続記録。"""

    arxiv_id: str
    notified_at: str           # "YYYY-MM-DD"
    source: str                # "system_a" or "system_b"
    score: int | None = None
    star_delta: int | None = None
    github_url: str | None = None
    stars_last_checked: int | None = None
    stars_checked_at: str | None = None  # "YYYY-MM-DD"

    def to_dict(self) -> dict:
        return {
            "arxiv_id": self.arxiv_id,
            "notified_at": self.notified_at,
            "source": self.source,
            "score": self.score,
            "star_delta": self.star_delta,
            "github_url": self.github_url,
            "stars_last_checked": self.stars_last_checked,
            "stars_checked_at": self.stars_checked_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NotifiedRecord":
        return cls(
            arxiv_id=data["arxiv_id"],
            notified_at=data["notified_at"],
            source=data.get("source", "system_a"),
            score=data.get("score"),
            star_delta=data.get("star_delta"),
            github_url=data.get("github_url"),
            stars_last_checked=data.get("stars_last_checked"),
            stars_checked_at=data.get("stars_checked_at"),
        )
