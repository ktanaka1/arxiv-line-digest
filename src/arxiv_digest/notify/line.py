"""LINE Messaging API 通知モジュール。

docs/specs/system-a.md / system-b.md の通知フォーマット仕様に従って
メッセージを組み立て、line-bot-sdk で Push Message を送信する。
"""

from __future__ import annotations

import logging
import os

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)

from arxiv_digest.models import Paper

logger = logging.getLogger(__name__)


def format_system_a(paper: Paper) -> str:
    """系統A 通知フォーマットを生成する。

    例:
        🔵🆕 [8/10] Retrieval-Augmented Generation with...
        RAGパイプラインにキャッシュ層を追加し推論コストを40%削減する手法。
        📄 https://arxiv.org/abs/2406.XXXXX
        🐙 https://github.com/xxx/yyy
    """
    score_str = f"[{paper.score}/10]" if paper.score is not None else "[?/10]"
    title = paper.title_ja or paper.title
    lines = [
        f"🔵🆕 {score_str} {title}",
        paper.summary or "",
        f"📄 {paper.arxiv_url}",
    ]
    if paper.github_url:
        lines.append(f"🐙 {paper.github_url}")
    return "\n".join(line for line in lines if line)


def format_system_b(paper: Paper) -> str:
    """系統B 通知フォーマットを生成する。

    再掲フラグ・HF トレンド・スター急伸の3パターンに対応する。

    例（スター急伸）:
        🟡🌟 [+73⭐/7d] Efficient Fine-Tuning of LLaMA...
    例（再掲）:
        🟡🌟 [再掲][+73⭐/7d] Efficient Fine-Tuning of LLaMA...
    例（HFトレンド）:
        🟡🌟 [HFトレンド] Paper Title...
    """
    # タグ部分を組み立てる
    tags: list[str] = []
    if paper.renotify:
        tags.append("[再掲]")

    if paper.star_delta is not None:
        tags.append(f"[+{paper.star_delta}⭐/7d]")
    else:
        tags.append("[HFトレンド]")

    tag_str = "".join(tags)
    title = paper.title_ja or paper.title
    lines = [
        f"🟡🌟 {tag_str} {title}",
        paper.summary or "",
        f"📄 {paper.arxiv_url}",
    ]
    if paper.github_url:
        lines.append(f"🐙 {paper.github_url}")
    return "\n".join(line for line in lines if line)


def build_message(system_a_papers: list[Paper], system_b_papers: list[Paper]) -> str:
    """系統A・系統Bの論文リストから1つの通知メッセージ文字列を組み立てる。

    docs/specs/system-b.md 「メッセージ結合順」:
      1. 系統A（スコア降順、最大5本）
      2. 系統B（スター増加数降順、最大5本）
      3. ブランク行区切りで1メッセージに結合
    """
    blocks: list[str] = []

    for paper in system_a_papers:
        blocks.append(format_system_a(paper))

    for paper in system_b_papers:
        blocks.append(format_system_b(paper))

    return "\n\n".join(blocks)


def send_message(system_a_papers: list[Paper], system_b_papers: list[Paper]) -> None:
    """LINE Push Message で通知を送信する。

    環境変数:
        LINE_CHANNEL_ACCESS_TOKEN: LINE Messaging API のチャンネルアクセストークン
        LINE_TO: 送信先ユーザー ID またはグループ ID
    """
    if not system_a_papers and not system_b_papers:
        logger.info("通知対象の論文がないため LINE 送信をスキップします")
        return

    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    to = os.environ.get("LINE_TO")

    if not token:
        raise EnvironmentError("LINE_CHANNEL_ACCESS_TOKEN 環境変数が設定されていません")
    if not to:
        raise EnvironmentError("LINE_TO 環境変数が設定されていません")

    text = build_message(system_a_papers, system_b_papers)
    logger.info("LINE 送信: %d 文字", len(text))

    configuration = Configuration(access_token=token)
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.push_message(
            PushMessageRequest(
                to=to,
                messages=[TextMessage(type="text", text=text)],
            )
        )
    logger.info("LINE 送信完了")
