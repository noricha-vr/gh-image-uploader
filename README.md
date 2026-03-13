# gh-image-uploader

Claude Code 用スキル。エージェントが GitHub issue / PR にスクリーンショットや画像を Markdown で貼り付けるための手順を定義する。

スキル定義: [SKILL.md](SKILL.md)

## 仕組み

1. エージェントが SKILL.md の手順に従ってスクリプトを呼び出す
2. 画像を AVIF に変換して Cloudflare R2 にアップロード
3. 公開 URL / Markdown リンクを返す

## セットアップ

### 前提条件

- [uv](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/)（`bunx wrangler` 実行用）

### 手順

```bash
# 1. 環境変数設定
cp .env.example .env
# R2_BUCKET と R2_PUBLIC_BASE_URL を設定

# 2. wrangler 認証
bunx wrangler login

# 3. 動作確認
uv run scripts/upload_image.py --format markdown test-image.png
```

R2 バケットは Cloudflare ダッシュボードまたは `bunx wrangler r2 bucket create <name>` で作成し、公開アクセスを有効にする。
