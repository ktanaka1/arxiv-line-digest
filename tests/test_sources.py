"""tests/test_sources.py

sources モジュールのユニットテスト。外部 HTTP は unittest.mock でモックする。
ここでは Papers With Code 終了に伴う後継経路 hugging_face.get_github_url を検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from arxiv_digest.sources import hugging_face


def _mock_resp(*, status_code=200, json_data=None, json_exc=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    if json_exc is not None:
        resp.json.side_effect = json_exc
    else:
        resp.json.return_value = json_data
    return resp


class TestGetGithubUrl:
    @patch("arxiv_digest.sources.hugging_face.requests.get")
    def test_githubRepo_を抽出する(self, mock_get):
        mock_get.return_value = _mock_resp(
            json_data={"id": "2405.09818", "githubRepo": "https://github.com/foo/bar"}
        )
        assert (
            hugging_face.get_github_url("2405.09818")
            == "https://github.com/foo/bar"
        )

    @patch("arxiv_digest.sources.hugging_face.requests.get")
    def test_バージョン接尾辞を除去して問い合わせる(self, mock_get):
        mock_get.return_value = _mock_resp(json_data={"githubRepo": "https://github.com/x/y"})
        hugging_face.get_github_url("2405.09818v2")
        called_url = mock_get.call_args[0][0]
        assert called_url.endswith("/2405.09818")
        assert "v2" not in called_url

    @patch("arxiv_digest.sources.hugging_face.requests.get")
    def test_githubRepo_なしは_None(self, mock_get):
        mock_get.return_value = _mock_resp(json_data={"id": "2405.09818"})
        assert hugging_face.get_github_url("2405.09818") is None

    @patch("arxiv_digest.sources.hugging_face.requests.get")
    def test_404_は_None(self, mock_get):
        mock_get.return_value = _mock_resp(status_code=404)
        assert hugging_face.get_github_url("0000.00000") is None

    @patch("arxiv_digest.sources.hugging_face.requests.get")
    def test_通信エラーは_None(self, mock_get):
        mock_get.side_effect = requests.RequestException("boom")
        assert hugging_face.get_github_url("2405.09818") is None

    @patch("arxiv_digest.sources.hugging_face.requests.get")
    def test_非JSONレスポンスは_None(self, mock_get):
        # PWC 終了後のリダイレクト先 HTML を受け取った状況を模す
        mock_get.return_value = _mock_resp(json_exc=ValueError("Expecting value"))
        assert hugging_face.get_github_url("2405.09818") is None
