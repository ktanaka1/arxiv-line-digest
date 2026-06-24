"""設定定数。仕様書 docs/service-overview.md および docs/specs/ の確定値をすべてここに集約する。"""

# arXiv 取得対象カテゴリ
ARXIV_CATEGORIES: list[str] = ["cs.AI", "cs.LG", "cs.CL"]

# 1カテゴリあたりの最大取得件数（3カテゴリ × 100 = 300件上限）
ARXIV_MAX_RESULTS: int = 100

# 取得対象とする投稿日のルックバック日数（UTC基準）。
# arXivは投稿→公開に1日ほどラグがあり、時差・週末も挟むため「当日ちょうど」では
# ほぼ0件になる。直近数日を候補にし、実際の重複排除は notified.json で行う。
ARXIV_LOOKBACK_DAYS: int = 2

# 系統A: Gemini採点
GEMINI_MODEL: str = "gemini-2.5-flash"  # 採点に使うモデル（無料枠あり・安定版）
SCORE_THRESHOLD: int = 7       # 7点以上を通知
SYSTEM_A_MAX: int = 5          # 最大5本
# 採点の並列数。数百本を逐次採点すると約1時間かかるため並列化する。
# Gemini のレート制限(RPM)に当たる場合はこの値を下げる。
GEMINI_CONCURRENCY: int = 6

# 系統B: 生き残り系
SYSTEM_B_MAX: int = 5          # 最大5本
STAR_DELTA_THRESHOLD: int = 50 # 7日間で+50スター以上
STAR_WATCH_DAYS: int = 7       # 監視期間（近似）

# 1日の通知上限（系統A + 系統B）
DAILY_MAX: int = SYSTEM_A_MAX + SYSTEM_B_MAX  # 10

# 外部 API エンドポイント
HF_API_URL: str = "https://huggingface.co/api/daily_papers"
# 単一論文メタデータ（githubRepo 等）。Papers With Code は 2025 年に終了し
# paperswithcode.com は HF へ 302 リダイレクトされるため、後継として HF Papers API を使う。
HF_PAPER_API_URL: str = "https://huggingface.co/api/papers/"

# データストアパス（repo 相対パス。main.py からの実行を想定）
NOTIFIED_JSON_PATH: str = "data/notified.json"
