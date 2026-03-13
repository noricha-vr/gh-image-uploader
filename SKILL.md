---
name: gh-image-uploader
description: 画像を AVIF 変換して Cloudflare R2 にアップロードし、公開 URL / Markdown を返す。GitHub issue・PR への画像添付に使用。
---

# gh-image-uploader

画像を AVIF に変換して Cloudflare R2 にアップロードするスクリプト。

## セットアップ確認

実行前に `.env` の存在を確認する。

```bash
test -f .env || echo "SETUP_REQUIRED"
```

`.env` が存在しない場合は `README.md` を読み、ユーザーにセットアップ手順を案内する。

## 前提条件

- `uv` インストール済み
- `.env` 設定済み（`.env.example` を参考に）
- `wrangler` 認証済み（`bunx wrangler login`）

## 実行コマンド

スクリプトパス: `scripts/upload_image.py`

### 基本（URL 出力）

```bash
uv run scripts/upload_image.py image.png
```

### Markdown 出力

```bash
uv run scripts/upload_image.py --format markdown screenshot.png
```

### GitHub issue / PR 向け（キー名にリポジトリ情報を含める）

```bash
uv run scripts/upload_image.py --repo owner/repo --number 123 --format markdown result.png
```

### 複数ファイル

```bash
uv run scripts/upload_image.py --format markdown before.png after.png
```

### JSON 出力

```bash
uv run scripts/upload_image.py --format json screenshot.png
```

## 引数一覧

| 引数 | 必須 | デフォルト | 説明 |
|------|------|-----------|------|
| `files` | Yes | - | アップロードする画像ファイル（複数可） |
| `--quality` | No | `.env` or 80 | AVIF 品質（1-100） |
| `--repo` | No | - | GitHub リポジトリ（`owner/repo`）。R2 キーに含まれる |
| `--number` | No | - | Issue / PR 番号。R2 キーに含まれる |
| `--bucket` | No | `.env` | R2 バケット名（`.env` を上書き） |
| `--base-url` | No | `.env` | 公開ベース URL（`.env` を上書き） |
| `--format` | No | `url` | 出力形式: `url` / `markdown` / `json` |

## .env 設定項目

| キー | 必須 | デフォルト | 説明 |
|------|------|-----------|------|
| `R2_BUCKET` | Yes | - | R2 バケット名 |
| `R2_PUBLIC_BASE_URL` | Yes | - | R2 公開 URL（例: `https://pub-xxxxx.r2.dev`） |
| `AVIF_QUALITY` | No | `80` | AVIF 変換品質 |
| `MAX_FILE_BYTES` | No | `10485760` | 最大ファイルサイズ（バイト） |
| `MAX_WIDTH` | No | `0`（無制限） | 最大幅（超えたらリサイズ） |
| `MAX_HEIGHT` | No | `0`（無制限） | 最大高さ（超えたらリサイズ） |
| `ALLOWED_EXTENSIONS` | No | `.png,.jpg,.jpeg,.webp,.gif` | 許可する拡張子 |
