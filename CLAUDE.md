# CLAUDE.md

作業言語は **日本語**（ドキュメント・通知文面・コメント・コミットメッセージすべて）。

## プロジェクト概要

個人用 arXiv 論文通知 bot。1日1回 GitHub Actions で起動し、興味に合う論文を LINE に最大10本通知する。
設計の意図の正本は `docs/service-overview.md`、技術判断の正本は `docs/architecture.md`。

## 技術スタック

- **言語**: Python / **依存管理**: uv（`pyproject.toml` + `uv.lock`）
- **実行基盤**: GitHub Actions（`schedule:` cron、1日1回・朝）
- **LLM**: Gemini Flash（`google-generativeai`）
- **通知**: LINE Messaging API（`line-bot-sdk`、既存動線に相乗り）
- **データストア**: `data/notified.json`（実行後に `[skip ci]` コミットで永続化）

## コマンド

```bash
# 依存インストール
uv sync

# ローカル実行（要 .env）
uv run python -m arxiv_digest.main

# テスト
uv run pytest

# Lint / Format
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

> `.env.example` に必要なキー一覧あり。ローカルでは `.env` にコピーして埋める。

## ディレクトリ構成

```
arxiv-line-digest/
├── .github/workflows/daily.yml    # cron 定義
├── src/arxiv_digest/
│   ├── main.py                    # オーケストレーション
│   ├── config.py                  # 閾値・カテゴリ等の設定
│   ├── models.py                  # データクラス
│   ├── sources/                   # arXiv / PWC / GitHub / HF
│   ├── scoring/llm_scorer.py      # Gemini採点
│   ├── notify/line.py             # LINE配信
│   └── store/dedup.py             # notified.json 重複排除
├── data/notified.json             # 通知済み記録（botが更新）
├── tests/
├── docs/
│   ├── service-overview.md
│   ├── architecture.md
│   ├── architecture-decisions/    # ADR-001, ADR-002
│   └── specs/                     # 機能仕様書（実装時に追加）
├── pyproject.toml
└── .env.example
```

## セキュリティルール

- `.env` は **絶対にコミットしない**（.gitignore 済み）
- API キーをコードにハードコードしない。環境変数 or Repo Secrets 経由のみ
- GitHub Actions での bot コミットには必ず `[skip ci]` を付ける

## テストポリシー

- `tests/` 配下に pytest で書く。外部 API は `unittest.mock` でモックする
- CI で `pytest` が通ることをマージの条件にする（実装開始後に workflow に追加）

## 設計制約（覆さないこと。いずれも意図的な判断）

- **通知先**: 専用 LINE 公式アカウント「ArXiv Digest」（プロバイダー AI活用Pjt 配下）。当初は既存
  Stock Signal 動線に相乗り予定だったが、通知混在を避けるため分離。1チャンネルで完結する点は維持
- **ソース**: `cs.AI` `cs.LG` `cs.CL` のみ。全量は絶対に流さない
- **上限**: 系統A最大5本 + 系統B最大5本（1日合計10本）
- **被引用数急伸は系統Bのシグナルにしない**（引用反応は半年〜1年スケールで数週間では動かない）
