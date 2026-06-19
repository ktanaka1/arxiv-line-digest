# 系統B 機能仕様：生き残り系（HF Daily Papers / GitHub Stars急伸）→ LINE通知

## 概要

数週間スケールで実際に伸びた論文を通知する。シグナルは2本：
1. **HF Daily Papers トレンド**（当日 Hugging Face でトレンドになっている論文）
2. **GitHub Stars 急伸**（7日間で+50スター以上の repo に紐付く arXiv 論文）

最大5本を系統Aと同じ1メッセージにまとめて通知する。

## MVP スコープ

- HF Daily Papers ✅（優先実装）
- GitHub Stars 急伸 ✅（中優先）
- 良質サーベイ検出 ❌（後回し・MVP外）

## パイプライン

```
HF Daily Papers 取得 ┐
GitHub Stars 急伸取得 ┘ → マージ・arXiv ID で dedup
  → 重複排除（通知済みIDを除外、再掲フラグ付与）
  → スコア降順（スター増加数）→ 上位5本
  → LINE通知（系統Aと同じメッセージに追記）
  → notified.json に記録
```

## sources/hugging_face.py

### API

```
GET https://huggingface.co/api/daily_papers
```

- 非公式 API だが安定して使われている
- レスポンスに arXiv ID が含まれる

### 入力
- なし（当日のトレンドを全取得）

### 出力
- `list[Paper]`（`source="system_b"`, `star_delta=None`）

### 注意
- arXiv ID が取れた論文のみ対象。repo リンクは別途 Papers With Code で補完（後述）

## sources/papers_with_code.py

### API

```
GET https://paperswithcode.com/api/v1/papers/?arxiv_id={arxiv_id}
```

- 非公式 API。公式サポートなし。壊れた場合は系統B のスター急伸シグナルのみ無効化して続行する。

### 処理
- arXiv ID を受け取り、紐付く GitHub repo URL を返す
- 取得失敗（404・タイムアウト等）は `None` を返す（スキップ・エラーにしない）

### 出力
- `github_url: str | None`

## sources/github_stars.py

### スナップショット差分方式

- `notified.json` に前回確認時のスター数を記録
- 今回取得したスター数との差分で「7日間の増加量」を近似する
- 正確な7日間ではなく「前回実行からの増加量」だが、1日1回実行で実用上十分

### notified.json への追記フィールド

```json
{
  "arxiv_id": "2406.12345",
  "github_url": "https://github.com/xxx/yyy",
  "stars_last_checked": 1234,
  "stars_checked_at": "2026-06-19"
}
```

### 急伸判定ロジック

```python
STAR_DELTA_THRESHOLD = 50   # 7日間で+50スター以上（config.py）
STAR_WATCH_DAYS = 7         # 監視期間

# 実装上の近似：前回記録からの増加量が閾値以上なら通知
star_delta = current_stars - stars_last_checked
if star_delta >= STAR_DELTA_THRESHOLD:
    # 通知対象
```

### GitHub API

- `GET /repos/{owner}/{repo}` で `stargazers_count` を取得（1回のAPI コールで済む）
- `GITHUB_TOKEN`（Actions 自動付与）でレート制限を緩和（5000 req/h）

### 監視対象の管理

- 系統A で通知済みの論文のうち、GitHub repo が紐付いているものを自動的に監視対象に追加
- `notified.json` の `github_url` が `null` でないレコードが監視対象

## notify/line.py（系統B 追記分）

### 通知フォーマット（系統B・通常）

```
🟡🌟 [+73⭐/7d] Efficient Fine-Tuning of LLaMA...
LoRAの亜種でメモリ使用量を半減させるファインチューニング手法。個人GPUで再現可能。
📄 https://arxiv.org/abs/2405.XXXXX
🐙 https://github.com/xxx/yyy
```

### 通知フォーマット（系統B・再掲）

```
🟡🌟 [再掲][+73⭐/7d] Efficient Fine-Tuning of LLaMA...
```

- `star_delta` が `None`（HF トレンド由来）の場合は `[HFトレンド]` と表示

```
🟡🌟 [HFトレンド] Paper Title...
```

### メッセージ結合順

1. 系統A（スコア降順、最大5本）
2. 系統B（スター増加数降順、最大5本）
3. ブランク行区切りで1メッセージに結合

## エラーハンドリング

| エラー | 対応 |
|--------|------|
| HF API 取得失敗 | 系統B 全体をスキップ（系統A は通知） |
| Papers With Code 取得失敗（1件） | その論文の `github_url=None` で続行 |
| GitHub API 取得失敗（1件） | その論文のスター判定をスキップ |
| GitHub API レート超過 | ログ出力して系統B スター急伸をスキップ |

## 設定値一覧（config.py）

```python
STAR_DELTA_THRESHOLD = 50   # 7日間で+50スター以上
STAR_WATCH_DAYS = 7         # 監視期間（近似）
SYSTEM_B_MAX = 5            # 系統B最大5本
HF_API_URL = "https://huggingface.co/api/daily_papers"
PWC_API_URL = "https://paperswithcode.com/api/v1/papers/"
```
