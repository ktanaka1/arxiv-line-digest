---
name: commit
description: プロジェクトルールに従ったgitコミットを実行する
disable-model-invocation: true
---

# /commit - arxiv-line-digest 専用コミットスキル

## ルール

1. **修正内容ごとに分けてコミット**: 1コミット = 1論理的変更
2. **Conventional Commits形式**: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:` 等
3. **Co-Authored-By 追加**: 必ず以下を付与
   ```
   Co-Authored-By: Claude <noreply@anthropic.com>
   ```
4. **bot コミット（data/notified.json 更新）には `[skip ci]` を付ける**

## 手順

### 1. 変更状況の確認
```bash
git status
git diff --stat
git log --oneline -5
```

### 2. グループごとにコミット
```bash
git add <関連ファイル>
git commit -m "$(cat <<'EOF'
<type>: <簡潔な説明>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

## 注意事項

- `git add -A` や `git add .` は避け、ファイルを明示的に指定する
- `.env` や認証情報を含むファイルはコミットしない
- `data/notified.json` を更新するコミットには必ず `[skip ci]` を付ける
- push はユーザーの明示的な指示がある場合のみ実行
