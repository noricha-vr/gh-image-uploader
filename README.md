# gh-image-uploader

画像を AVIF に変換して Cloudflare R2 にアップロードし、公開 URL を返す CLI ツール。

## 前提条件

- [uv](https://docs.astral.sh/uv/) がインストール済み
- [Bun](https://bun.sh/)（`bunx wrangler` 実行用）

## セットアップ

### 1. R2 バケット作成

Cloudflare ダッシュボードまたは wrangler CLI で R2 バケットを作成する。

```bash
# wrangler CLI の場合
bunx wrangler r2 bucket create your-bucket-name
```

バケットの公開アクセスを有効にし、公開 URL（例: `https://pub-xxxxx.r2.dev`）を控える。

### 2. 環境変数設定

`.env.example` をコピーして値を設定する。

```bash
cp .env.example .env
```

最低限 `R2_BUCKET` と `R2_PUBLIC_BASE_URL` を設定する。

```bash
# .env
R2_BUCKET=your-bucket-name
R2_PUBLIC_BASE_URL=https://pub-xxxxx.r2.dev
```

### 3. wrangler 認証

```bash
bunx wrangler login
```

ブラウザが開くので Cloudflare アカウントで認証する。

## 動作確認

```bash
uv run scripts/upload_image.py --format markdown test-image.png
```

成功すると Markdown 形式の画像リンクが出力される:

```
![test-image](https://pub-xxxxx.r2.dev/uploads/2026/03/abcd1234-test-image.avif)
```
