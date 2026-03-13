# アーキテクチャ設計

## 概要

GitHub issue/PR に画像を添付するための Cloudflare Worker + R2 サービス。
`gh-attach`（ブラウザ依存）の代替として、API 経由で画像アップロード→AVIF変換→R2保存→GitHub コメント投稿を行う。

## システム構成

```
クライアント (curl / エージェント / CLI)
    │
    │ POST /v1/upload  or  POST /v1/github/comment-images
    │   multipart/form-data
    │
    ▼
┌─────────────────────────────────────────────┐
│  Cloudflare Worker (Hono)                   │
│                                             │
│  1. Bearer Token 認証                       │
│  2. リクエストバリデーション                  │
│  3. Cloudflare Image Resizing で AVIF 変換  │
│     → 1,600px 超は WebP フォールバック      │
│  4. R2 に変換済み画像を保存                  │
│  5. (optional) GitHub API でコメント投稿     │
│  6. JSON レスポンス返却                     │
└─────────────────────────────────────────────┘
    │                    │
    ▼                    ▼
  R2 Bucket          GitHub API
  (公開CDN配信)       (issue comments)
```

## 技術スタック

| 要素 | 選定 | 理由 |
|------|------|------|
| ランタイム | Cloudflare Workers | 要件通り、エッジ実行 |
| フレームワーク | Hono | 軽量、Workers 親和性高 |
| 画像変換 | Cloudflare Image Resizing binding | ネイティブ AVIF 対応、Rust製で高速 |
| ストレージ | Cloudflare R2 | S3互換、安価、グローバル配信 |
| 言語 | TypeScript | 型安全 |
| テスト | Vitest | 軽量、Workers 対応 |
| パッケージマネージャ | bun | プロジェクト規約 |

## AVIF 変換の技術判断

### 採用: Cloudflare Image Resizing バインディング

- Rust 製 `rav1e` エンコーダを使用、ネイティブで高速
- `wrangler.toml` の `[images]` セクションで有効化
- Worker コード内で `env.IMAGES.input(buffer).output({ format: 'avif' }).run()` で変換

### 却下した代替案

| 方法 | 却下理由 |
|------|----------|
| WASM AVIF (jSquash/libavif) | Workers の 128MB メモリ制限、単一スレッドで遅い |
| クライアント側変換 | エージェント依存増、一貫性なし |
| 外部変換サービス | 不要な外部依存 |

### 制限事項

- **AVIF 1,600px 上限**: Image Resizing で `format=avif` 指定時、1,600px を超える画像は変換不可→WebP にフォールバック
- **有料プラン必須**: Cloudflare Pro 以上、または Images サブスクリプション
- **SVG 非対応**: XSS リスクのため v1 では受け付けない

## ファイル構成

```
gh-image-uplaoder/
├── src/
│   ├── index.ts                # Hono アプリ + ルーティング
│   ├── routes/
│   │   ├── upload.ts           # POST /v1/upload ハンドラ
│   │   └── health.ts           # GET /health
│   ├── services/
│   │   ├── image-converter.ts  # AVIF 変換 (Image Resizing binding)
│   │   ├── r2-storage.ts       # R2 保存
│   │   └── github-client.ts    # GitHub API (コメント投稿)
│   ├── middleware/
│   │   └── auth.ts             # Bearer Token 認証
│   ├── utils/
│   │   ├── sanitize.ts         # ファイル名サニタイズ
│   │   └── placeholder.ts      # gh-attach placeholder 解決
│   └── types.ts                # 型定義 (Env, Request, Response)
├── test/
│   ├── upload.test.ts
│   ├── image-converter.test.ts
│   ├── placeholder.test.ts
│   └── sanitize.test.ts
├── docs/
│   ├── SKILL.md                # スキル定義 (エージェント向け)
│   └── architecture.md         # 本ドキュメント
├── wrangler.toml
├── package.json
├── tsconfig.json
├── vitest.config.ts
├── .env.example
├── .gitignore
└── CLAUDE.md
```

## 処理フロー詳細

### 1. リクエスト受信 + バリデーション

- Bearer Token 認証
- multipart/form-data パース
- MIME type チェック (PNG, JPEG, WebP, GIF のみ)
- ファイルサイズチェック (10MB/ファイル, 20MB/リクエスト)
- `repo` が `owner/repo` 形式か検証

### 2. AVIF 変換

```typescript
const result = await env.IMAGES
  .input(imageBuffer)
  .output({ format: 'avif', quality: 80 })
  .run();
```

- 変換成功: AVIF として R2 に保存
- 1,600px 超で失敗: WebP で再試行
- 全変換失敗: 元画像をそのまま保存

### 3. R2 保存

- object key: `github/{owner}/{repo}/{target_type}/{number}/{yyyy}/{mm}/{uuid}-{name}.avif`
- `Content-Type`: `image/avif`
- `Cache-Control`: `public, max-age=31536000, immutable`
- append-only（上書きしない）

### 4. GitHub コメント投稿 (optional)

- `repo` + `number` 指定時のみ実行
- placeholder (`<!-- gh-attach:IMAGE -->`) があれば置換
- なければ本文末尾に画像 Markdown を追記
- `comment_id` 指定時は既存コメント更新

### 5. レスポンス

- アップロードされた各画像の URL, markdown, サイズ等
- GitHub コメント URL（投稿した場合）

## 環境変数

| 変数名 | 用途 | 必須 |
|--------|------|------|
| `API_TOKEN` | Worker API の Bearer Token | Yes |
| `GITHUB_TOKEN` | GitHub API アクセストークン | No (コメント投稿時のみ) |
| `PUBLIC_BASE_URL` | R2 公開 URL のベース | Yes |
| `R2_BUCKET` | R2 バケット binding 名 | Yes (wrangler.toml) |

## 参考: 既存プロジェクトから流用するパターン

- `aoi-reader/src/lib/cloudflare-storage.ts` - R2 バインディング経由の保存パターン
- `openclaw` - Hono フレームワークの使い方
