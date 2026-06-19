"""系統A: Gemini Flash による論文採点モジュール。

docs/specs/system-a.md のプロンプト仕様に従い、1本ずつ採点する。
API エラー・JSON パース失敗時は score=0 を返してスキップ扱いにする。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

import google.generativeai as genai

from arxiv_digest.models import Paper

logger = logging.getLogger(__name__)

# docs/specs/system-a.md の「プロンプト」セクションそのまま
_PROMPT_TEMPLATE = """\
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
"""


@dataclass
class ScoringResult:
    score: int
    summary: str
    reason: str


def _get_model() -> genai.GenerativeModel:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY 環境変数が設定されていません")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
        ),
    )


def score_paper(paper: Paper) -> ScoringResult:
    """1本の論文を Gemini Flash で採点して ScoringResult を返す。

    API エラーや JSON パース失敗の場合は score=0, summary="", reason="" を返す。
    """
    prompt = _PROMPT_TEMPLATE.format(
        title=paper.title,
        abstract=paper.abstract,
    )

    try:
        model = _get_model()
        response = model.generate_content(prompt)
        raw = response.text
    except Exception as e:
        logger.error("Gemini API エラー (arxiv_id=%s): %s", paper.arxiv_id, e)
        return ScoringResult(score=0, summary="", reason="")

    try:
        data = json.loads(raw)
        score = int(data.get("score", 0))
        summary = str(data.get("summary", ""))
        reason = str(data.get("reason", ""))
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.error(
            "JSON パース失敗 (arxiv_id=%s): %s / レスポンス: %s",
            paper.arxiv_id,
            e,
            raw[:200],
        )
        return ScoringResult(score=0, summary="", reason="")

    return ScoringResult(score=score, summary=summary, reason=reason)
