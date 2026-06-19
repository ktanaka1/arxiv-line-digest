# 系統A 機能仕様：arXiv新着 → Gemini採点 → LINE通知

## 概要

毎朝 arXiv の新着論文（`cs.AI` `cs.LG` `cs.CL`）を全量取得し、興味プロファイルに基づいて
Gemini Flash で採点。7点以上を最大5本、LINE にまとめて1メッセージで通知する。

## パイプライン

```
arXiv新着取得（3カテゴリ）
  → 重複排除（通知済みIDを除外）
  → Gemini採点（1本ずつ、JSON出力）
  → 閾値フィルタ（7点以上）
  → スコア降順ソート → 上位5本
  → LINE通知（まとめて1メッセージ）
  → notified.json に記録
```

## モジュール対応

| 処理 | モジュール |
|------|-----------|
| 新着取得 | `sources/arxiv.py` |
| 採点 | `scoring/llm_scorer.py` |
| 重複排除・記録 | `store/dedup.py` |
| LINE配信 | `notify/line.py` |
| 全体制御 | `main.py` |

## sources/arxiv.py

### 入力
- カテゴリリスト: `["cs.AI", "cs.LG", "cs.CL"]`（`config.py` から）

### 処理
- `arxiv` ライブラリで各カテゴリの当日新着を取得
- 重複論文（複数カテゴリに跨るもの）は arXiv ID で dedup する

### 出力
- `list[Paper]`（`models.py` の `Paper` データクラス）

### Paper データクラス（models.py）

```python
@dataclass
class Paper:
    arxiv_id: str          # "2406.12345"
    title: str
    abstract: str
    authors: list[str]
    arxiv_url: str         # "https://arxiv.org/abs/2406.12345"
    github_url: str | None # Papers With Code 経由（系統Bで設定）
    score: int | None      # Gemini採点結果（採点後に設定）
    summary: str | None    # Gemini日本語要約（採点後に設定）
    source: str            # "system_a" or "system_b"
    star_delta: int | None # 系統Bのみ（7日間スター増加数）
    renotify: bool         # 再掲フラグ
```

## scoring/llm_scorer.py

### 入力
- `Paper` 1件

### 処理
- Gemini Flash に以下のプロンプトを送信
- `response_mime_type="application/json"` で JSON 出力を強制
- 1本ずつ処理（バッチ送信しない）

### プロンプト

```
あなたは以下の興味プロファイルを持つエンジニアです。
論文を10点満点で採点し、スコア・1行日本語要約・採点根拠を返してください。

【興味プロファイル】
実装・ハッカー気質（Pragmatic）。
好むテーマ：RAGの高度化 / AIエージェント / プロンプトエンジニアリング
         / API連携 / OSSモデルのファインチューニング。
判定の核：「読んだ実務者が明日コードを書きたくなるか」

加点要素：手を動かせる（コード/リポジトリ/レシピが具体的）、
         個人〜小規模で再現可能、すぐ効く実務Tips。
減点要素：理論・証明オンリー、ベンチSOTAの僅差更新、
         大手しか再現できない、応用の利かないニッチ特化。

【論文情報】
タイトル: {title}
アブストラクト: {abstract}

【出力形式（JSON）】
{{"score": 8, "summary": "〇〇を△△で実現する手法。コード公開あり。", "reason": "コード公開あり、個人再現可"}}
```

### 出力
- `score: int`（1〜10）
- `summary: str`（日本語1行）
- `reason: str`（採点根拠、通知には含めない・デバッグ用）

### 閾値・上限（config.py）

```python
SCORE_THRESHOLD = 7      # 7点以上を通知
SYSTEM_A_MAX = 5         # 最大5本
```

## store/dedup.py

### notified.json スキーマ

```json
[
  {
    "arxiv_id": "2406.12345",
    "notified_at": "2026-06-19",
    "source": "system_a",
    "score": 8,
    "star_delta": null
  }
]
```

### 処理
- 採点前に notified.json を読み込み、通知済み ID のセットを作成
- 採点後に通知対象を notified.json に追記
- 実行後に `git commit -m "chore: update notified.json [skip ci]"` でコミット

## notify/line.py

### 通知フォーマット（系統A）

```
🔵🆕 [8/10] Retrieval-Augmented Generation with...
RAGパイプラインにキャッシュ層を追加し推論コストを40%削減する手法。コード公開あり。
📄 https://arxiv.org/abs/2406.XXXXX
🐙 https://github.com/xxx/yyy
```

- `github_url` がない場合は🐙行を省略
- 複数本はブランク行区切りで1メッセージに結合
- LINE Messaging API の Push Message（`line-bot-sdk`）で送信

## エラーハンドリング

- Gemini API エラー → その1本をスキップ（他の論文の処理は続行）
- LINE API エラー → GitHub Actions のログに出力して終了（通知失敗は翌日まで待つ）
- arXiv 取得エラー → GitHub Actions のログに出力して終了

## 設定値一覧（config.py）

```python
ARXIV_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL"]
SCORE_THRESHOLD = 7
SYSTEM_A_MAX = 5
SYSTEM_B_MAX = 5
DAILY_MAX = SYSTEM_A_MAX + SYSTEM_B_MAX  # 10
```
