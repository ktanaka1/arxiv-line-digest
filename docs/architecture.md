# アーキテクチャ

> 本ドキュメントは技術スタックとディレクトリ構成の正本。意図・要件の正本は `docs/service-overview.md`。

## 全体像

1日1回 GitHub Actions の cron で起動するバッチ型 bot。実行環境は毎回まっさらなので、
通知済み記録は repo 内の JSON ファイルに書き戻して永続化する。Web サーバー・常駐プロセスは持たない。

```
[GitHub Actions cron (毎朝)]
        │
        ▼
  main.py (オーケストレーション)
   ├─ 系統A: arXiv新着 → LLM採点(Gemini) → 高評価のみ
   ├─ 系統B: GitHubスター急伸 / HFトレンド / 良質サーベイ
   ├─ store/dedup.py で notified.json と突き合わせ（重複排除）
   └─ notify/line.py で LINE Messaging API へ配信
        │
        ▼
  data/notified.json を更新 → git commit & push ([skip ci])
```

## 技術スタック

- **言語**: Python
- **依存管理**: uv（`pyproject.toml` + `uv.lock`）
- **実行基盤**: GitHub Actions（`schedule:` cron、1日1回・朝）
- **データストア**: repo 内 JSON（`data/notified.json`）を実行後にコミットして永続化
- **LLM**: Gemini Flash（無料枠）/ `google-generativeai`
- **通知**: LINE Messaging API（既存動線に相乗り）/ `line-bot-sdk`
- **データソース**:
  - arXiv（`arxiv` ライブラリ）— 系統A
  - Papers With Code（arXiv→repo 紐付け）/ GitHub API — 系統B（スター急伸）
  - Hugging Face Papers / Daily Papers — 系統B（トレンド）
- **設計パターン**: 単一フィルタリングパイプライン（系統A・系統Bが1チャンネルに合流）。
  役割ごとにモジュール分割（sources / scoring / notify / store）。

## 選定理由

- **Python**: arXiv・Gemini まわりのエコシステムが最も厚く、論文スコアリングのデータ処理と相性が良い。
- **GitHub Actions**: 1日1回バッチに最適。無料・cron が簡単・シークレットもコードも repo 内で完結し、
  個人運用の管理コストが最小。詳細は [ADR-001](architecture-decisions/ADR-001-execution-platform.md)。
- **repo 内 JSON**: データが軽量（年間数千行規模）。追加サービスゼロで、通知履歴が git ログに自然に残り
  後から振り返れる。詳細は [ADR-002](architecture-decisions/ADR-002-datastore.md)。
- **uv**: 高速かつ lock による再現性管理が容易で、CI でのインストールも速い。

## ディレクトリ構成

```
arxiv-line-digest/
├── .github/workflows/
│   └── daily.yml              # 1日1回 cron（朝）
├── src/arxiv_digest/
│   ├── main.py               # エントリポイント（全体オーケストレーション）
│   ├── config.py             # カテゴリ・閾値(7点)・上限(5+5)等の設定
│   ├── models.py             # Paper 等のデータクラス
│   ├── sources/              # データ取得
│   │   ├── arxiv.py          #   系統A: 新着取得
│   │   ├── papers_with_code.py #   arXiv→repo 紐付け
│   │   ├── github_stars.py   #   系統B: スター急伸判定
│   │   └── hugging_face.py   #   系統B: HFトレンド
│   ├── scoring/
│   │   └── llm_scorer.py     # Gemini採点（興味プロファイル）
│   ├── notify/
│   │   └── line.py           # LINE配信＋文面フォーマット
│   └── store/
│       └── dedup.py          # notified.json 読み書き・重複排除
├── data/
│   └── notified.json         # 通知済み記録（botがコミット）
├── tests/
├── docs/                     # service-overview.md / architecture.md / specs / architecture-decisions
├── pyproject.toml            # 依存管理（uv）
├── .env.example              # 必要なキー一覧（GEMINI_API_KEY, LINE_* 等）
└── CLAUDE.md
```

## シークレット（GitHub Repo Secrets で管理）

- `GEMINI_API_KEY`
- `LINE_CHANNEL_ACCESS_TOKEN`（既存プロジェクトのものを相乗り）
- `LINE_TO`（送信先ユーザー/グループID）
- `GITHUB_TOKEN`（Actions が自動付与。スター取得のレート制限緩和に利用可）

> ローカル実行時は `.env`（gitignore 済み）に格納。`.env.example` に必要キー一覧を記載する。
