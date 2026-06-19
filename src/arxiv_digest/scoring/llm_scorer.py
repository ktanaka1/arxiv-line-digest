"""系統A: Gemini Flash による論文採点モジュール。

docs/specs/system-a.md のプロンプト仕様に従い、1本ずつ採点する。
API エラー・JSON パース失敗時は score=0 を返してスキップ扱いにする。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from google import genai
from google.genai import types

from arxiv_digest import config
from arxiv_digest.models import Paper

logger = logging.getLogger(__name__)

# docs/specs/system-a.md の「プロンプト」セクションそのまま
_PROMPT_TEMPLATE = """\
あなたは以下の興味プロファイルを持つエンジニアです。
論文を10点満点で採点し、日本語タイトル・スコア・日本語概要・採点根拠を返してください。
日本語タイトルは原題を自然な日本語に訳したものにしてください。

日本語概要は、リンク先を開かなくても内容が分かるように、以下を必ず含めて
3〜4文の日本語でまとめてください：
  - 何の課題に取り組んだか
  - どんな手法・アプローチか
  - 結果・結論（何がどれだけ良くなったか、何が分かったか）
箇条書きにせず、自然な文章にしてください。

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
{{"title_ja": "〇〇を△△で実現する手法", "score": 8, "summary": "従来手法では〜という課題があった。本研究では〜というアプローチでこれに取り組む。実験の結果〜が示され、〜だと結論づけている。", "reason": "コード公開あり、個人再現可"}}
"""


@dataclass
class ScoringResult:
    score: int
    title_ja: str
    summary: str
    reason: str


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY 環境変数が設定されていません")
    return genai.Client(api_key=api_key)


def score_paper(paper: Paper) -> ScoringResult:
    """1本の論文を Gemini Flash で採点して ScoringResult を返す。

    API エラーや JSON パース失敗の場合は score=0, summary="", reason="" を返す。
    """
    prompt = _PROMPT_TEMPLATE.format(
        title=paper.title,
        abstract=paper.abstract,
    )

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        raw = response.text
    except Exception as e:
        logger.error("Gemini API エラー (arxiv_id=%s): %s", paper.arxiv_id, e)
        return ScoringResult(score=0, title_ja="", summary="", reason="")

    try:
        data = json.loads(raw)
        score = int(data.get("score", 0))
        title_ja = str(data.get("title_ja", ""))
        summary = str(data.get("summary", ""))
        reason = str(data.get("reason", ""))
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.error(
            "JSON パース失敗 (arxiv_id=%s): %s / レスポンス: %s",
            paper.arxiv_id,
            e,
            raw[:200],
        )
        return ScoringResult(score=0, title_ja="", summary="", reason="")

    return ScoringResult(score=score, title_ja=title_ja, summary=summary, reason=reason)
