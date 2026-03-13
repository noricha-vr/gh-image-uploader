---
name: github-r2-attach
description: GitHub issue / pull request の会話コメントに、Cloudflare Worker 経由で Cloudflare R2 に保存した画像 URL を差し込む仕組みを実装・変更・修正するスキル。gh-attach 代替、スクリーンショット添付、issue comment、PR comment、Cloudflare Worker、R2、GitHub comment API、placeholder、画像アップロード、コメント更新などの依頼で使う。diff 行への inline review comment や review thread には、明示された場合だけ使う。
compatibility: Codex などのコーディングエージェント向け。リポジトリ読み書き、shell、git、curl、jq、必要に応じて gh が使える前提。
---

# 目的

`gh-attach` のブラウザ依存をやめ、Cloudflare Worker + R2 + GitHub API で issue / PR コメントに画像を付ける仕組みを作る。

このスキルは、次のような依頼で使う。

- GitHub issue / PR にスクリーンショットを貼りたい
- `gh-attach` を置き換えたい
- R2 + Worker ベースで画像アップロード API を作りたい
- issue comment / PR comment に画像 URL を差し込みたい
- コメント本文の placeholder を維持したい
- 画像付きコメントの create / update フローを実装したい

このスキルは、次のときは**使わない**。

- PR の diff 行に対する inline review comment / review thread が主目的のとき
- GitHub のネイティブ添付 UI を Playwright で操作する方針が明示されているとき
- 画像ではなく動画、PDF、任意バイナリ添付が主目的のとき

# このスキルで優先する判断

1. 既存リポジトリの命名・認証・ルーティング規約を最優先で再利用する。
2. 既存規約がなければ、このファイルのデフォルト設計を採用する。
3. ブラウザ自動操作や GitHub の内部 API には寄らない。
4. 通常の PR コメントは issue comments API を使う。PR review comment API は、diff 上の行コメントが明示されたときだけ使う。
5. 秘密情報は env / Wrangler secret に置く。コード、fixture、README に平文で埋め込まない。
6. まず小さく動く最短実装を作り、そのあと拡張する。

# 実装前に最初に確認すること

実装前に、必ず現在のリポジトリから次を確認する。

- `wrangler.toml` / `wrangler.jsonc` の有無
- Worker エントリポイント、ルーティング、ミドルウェア構成
- 既存の R2 binding 名
- 既存の認証方式（Bearer token / HMAC / Cloudflare Access / GitHub App など）
- GitHub API 呼び出し基盤の有無
- コメント本文の既存テンプレートや placeholder 記法の有無
- テスト基盤（Vitest, Jest, Miniflare, integration tests など）
- API 命名規則（`/api/...`、`/v1/...` など）

既存規約がある場合は、それに寄せる。新規で始める場合だけ、以下のデフォルトを使う。

# デフォルト設計

## 推奨アーキテクチャ

新規実装では、次の順で考える。

### 第一候補: Worker が upload も GitHub comment 更新も行う

- クライアントは Worker API に画像と本文を送る
- Worker が画像を AVIF に変換して R2 に保存する
- Worker が GitHub API で issue / PR conversation comment を create / update する
- クライアントは 1 回の API 呼び出しで完了する

この構成は、コーディングエージェント側に `gh` や GitHub token を要求しないので、最初のプロダクトとして扱いやすい。

### 第二候補: Worker は upload のみ、comment 更新は client / agent 側で行う

- Worker は画像 URL / Markdown / HTML を返す
- client / agent が `gh api` か REST で comment を作成・更新する

既存で `gh` 認証や GitHub App 呼び出し基盤が client 側にあるなら、この構成でもよい。

**迷ったら第一候補を採用する。**

## AVIF 変換方針

- Cloudflare Image Resizing バインディング（`images`）を使用してネイティブ AVIF 変換
- quality: 80（ファイルサイズと品質のバランス）
- 1,600px 超の画像は WebP にフォールバック（Image Resizing の AVIF 上限）
- 変換失敗時は元画像をそのまま保存（Fail gracefully）
- SVG 入力は v1 では非対応

## GitHub コメント種別の扱い

- issue comment: issue comments API を使う
- PR conversation comment: issue comments API を使う
- PR diff line comment / review thread: 別 API。依頼で明示された場合のみ実装対象にする

通常の「PR に画像付きコメントを付ける」は review comment ではなく、conversation comment として扱う。

## 画像レンダリング方針

デフォルトは Markdown を使う。

```md
![alt text](https://img.example.com/path/to/file.avif)
```

HTML は、既存仕様で width 固定が必要なときだけ使う。

```html
<img src="https://img.example.com/path/to/file.avif" alt="alt text" width="800">
```

ルール:

- デフォルト render mode は `markdown`
- `width` は HTML mode のときだけ使う
- alt text が未指定なら、拡張子を除いたファイル名を使う
- 本文中の改行や前後文脈はできるだけそのまま保つ

## placeholder 方針

`gh-attach` 互換を優先し、次をサポートする。

- `<!-- gh-attach:IMAGE -->`
- `<!-- gh-attach:IMAGE:1 -->`
- `<!-- gh-attach:IMAGE:2 -->`
- `<!-- gh-attach:IMAGE:N -->`

ルール:

- `<!-- gh-attach:IMAGE -->` は 1 枚目として扱う
- `N` は 1 始まり
- placeholder がなければ、画像を本文末尾へ空行区切りで append する
- 同じ placeholder が複数回出たら、同じ画像をその位置すべてに差し込む
- 範囲外の番号が指定されたら 422 を返す
- placeholder を置換したあと、残った未解決 placeholder があれば 422 を返す

# 新規実装時の API 契約（デフォルト）

既存 API 契約がない場合は、まず次のどちらかで実装する。

## 推奨: comment まで 1 回で完了する endpoint

### `POST /v1/github/comment-images`

Content-Type: `multipart/form-data`

必須フィールド:

- `repo`: `owner/repo`
- `number`: issue または PR 番号
- `files`: 画像ファイル（複数可）

任意フィールド:

- `target_type`: `issue` | `pr`（未指定時は `issue` 扱い。`pr` でも conversation comment として issue comments API を使う）
- `body`: コメント本文
- `comment_id`: 既存 comment を更新する場合に指定
- `render_mode`: `markdown` | `html`（default: `markdown`）
- `width`: HTML mode 用の幅
- `meta`: JSON 文字列。将来 alt text や file ごとのオプションを増やすときはここに集約する

返却 JSON の例:

```json
{
  "repo": "owner/repo",
  "number": 123,
  "target_type": "pr",
  "comment_id": 987654321,
  "comment_url": "https://github.com/owner/repo/pull/123#issuecomment-987654321",
  "body": "E2E result\n\n![before](https://img.example.com/.../before.avif)",
  "images": [
    {
      "filename": "before.avif",
      "original_filename": "before.png",
      "content_type": "image/avif",
      "size": 12345,
      "key": "github/owner/repo/pr/123/2026/03/uuid-before.avif",
      "url": "https://img.example.com/github/owner/repo/pr/123/2026/03/uuid-before.avif",
      "markdown": "![before](https://img.example.com/github/owner/repo/pr/123/2026/03/uuid-before.avif)"
    }
  ]
}
```

## 代替: upload だけ行う endpoint

既存設計が client-side の GitHub 認証を前提にしているなら、次でもよい。

### `POST /v1/uploads/images`

- 画像を受け取って AVIF に変換し R2 に保存する
- `url`, `markdown`, `html`, `key`, `content_type`, `size` を返す
- comment の create / update は別 endpoint または `gh api` で行う

この場合、コメント更新ロジックは client / agent 側に置く。

# GitHub API の使い分け

## conversation comment を create するとき

- issue / PR どちらでも `repos/{owner}/{repo}/issues/{number}/comments` を使う
- body には最終レンダリング済み文字列を入れる

## conversation comment を update するとき

- `repos/{owner}/{repo}/issues/comments/{comment_id}` を使う
- body は全文差し替えで扱う

## review comment を使うのは次のときだけ

- ユーザーが「PR のこの diff 行にコメントしたい」と明示した
- `path`, `line`, `side`, `commit_id` など review comment に必要な情報が与えられている

それ以外は review comment API に進まない。

# Worker 側の責務

Worker 実装では、次を分離して考える。

## 1. Request validation

- `repo` は `owner/repo` 形式か
- `number` と `comment_id` は整数か
- `target_type` は想定値か
- 画像が 1 枚以上あるか
- 拡張子と MIME type が想定範囲か
- サイズ制限を超えていないか
- 認証ヘッダや caller 権限が有効か

## 2. Image normalization + AVIF conversion

- ファイル名を sanitize する
- alt text のデフォルト値を決める
- content type を決定する
- Cloudflare Image Resizing で AVIF に変換する
- 1,600px 超の場合は WebP にフォールバックする
- object key を生成する

## 3. R2 persistence

- `Content-Type` を正しく保存する
- 可能なら `Cache-Control: public, max-age=31536000, immutable` を付ける
- 必要なら `Content-Disposition: inline` を付ける
- 上書きより append-only を優先する

## 4. Comment rendering

- placeholder を解決する
- placeholder がなければ本文末尾へ追記する
- `render_mode` に応じて Markdown / HTML を組み立てる
- 改行の扱いを壊さない

## 5. GitHub write

- `comment_id` がなければ create
- `comment_id` があれば update
- GitHub の失敗は machine-readable なエラーに変換する

# R2 object key のデフォルト規則

既存規約がない場合、次の形を推奨する。

```text
github/{owner}/{repo}/{target_type}/{number}/{yyyy}/{mm}/{uuid}-{sanitized-filename}.avif
```

例:

```text
github/acme/widgets/pr/123/2026/03/550e8400-e29b-41d4-a716-446655440000-before.avif
```

repo/number なしの場合:

```text
uploads/{yyyy}/{mm}/{uuid}-{sanitized-filename}.avif
```

ルール:

- object key には `repo`, `target_type`, `number` を含める
- ファイル名は sanitize する
- 衝突回避のため UUID を付ける
- v1 では dedupe を必須にしない
- comment 更新時も原則として既存 object を上書きしない

# 推奨する env / secret の考え方

名前は repo の規約に合わせる。新規なら、たとえば次を使う。

- `R2_BUCKET` または Worker binding
- `PUBLIC_BASE_URL`
- `API_TOKEN`
- `GITHUB_TOKEN` または GitHub App 用 secret 群
- `MAX_IMAGE_BYTES`
- `ALLOWED_IMAGE_MIME_TYPES`

GitHub App を使う場合は、installation token 取得ロジックをサービス層に閉じ込める。

# エラー設計

エラーは、HTTP status と JSON の両方で判別しやすくする。

例:

```json
{
  "error": {
    "code": "IMAGE_INDEX_OUT_OF_RANGE",
    "message": "placeholder <!-- gh-attach:IMAGE:2 --> cannot be resolved because only 1 image was uploaded"
  }
}
```

推奨ステータス:

- `400`: リクエスト形式不正
- `401`: 未認証
- `403`: 権限不足
- `404`: repo / issue / comment が見つからない
- `413`: サイズ超過
- `415`: 非対応 MIME type
- `422`: placeholder 解決失敗、GitHub validation failed、spam 判定など
- `502` / `503`: GitHub や upstream 障害

# セキュリティ指針

- client が送った `repo` / `number` をそのまま信頼しない
- 認証された caller がその repo へ書いてよいかを確認する
- SVG は XSS や取り扱い差異が面倒なので、明示要求がない限り v1 では受け付けない
- MIME type はヘッダだけでなく、可能なら実ファイル内容とも整合を取る
- ファイル名は path traversal を起こさないよう sanitize する
- GitHub token / app secret をログに出さない
- エラーログに request body を丸ごと出さない

# テスト方針

最低限、次は自動化する。

## Unit tests

- placeholder 置換
- placeholder 範囲外エラー
- append fallback
- Markdown / HTML renderer
- object key 生成
- file 名 sanitize
- MIME / size validation
- create / update 分岐

## Integration tests

- multipart upload -> AVIF 変換 -> R2 保存 -> レスポンス JSON
- comment create の GitHub API mock
- comment update の GitHub API mock
- GitHub error の変換

## 手動 smoke test

最低 1 回は curl 例を README や PR 説明に残す。

```bash
curl -X POST "$API_BASE/v1/github/comment-images" \
  -H "Authorization: Bearer $API_TOKEN" \
  -F repo=owner/repo \
  -F number=123 \
  -F target_type=pr \
  -F body='Result: <!-- gh-attach:IMAGE -->' \
  -F files=@./result.png
```

# 実装時のチェックリスト

作業の最後に、次を確認する。

- issue と PR conversation comment の両方で同じフローが使える
- review comment API を誤って使っていない
- placeholder が仕様どおり動く
- placeholder がない本文でも自然に append される
- 画像が AVIF に変換されている
- 1,600px 超の画像が WebP にフォールバックされる
- 画像 URL が外部から到達できる
- 画像の `Content-Type` が正しい
- 認証情報がコードに埋め込まれていない
- README / API 例が更新されている
- エラーが JSON で読める

# やらないこと

明示要求がない限り、次は scope 外にする。

- PR diff line review comment の完全対応
- 画像削除に連動した R2 garbage collection
- 動画 / PDF / 任意バイナリ対応
- ブラウザ自動操作による GitHub ネイティブ添付
- 画像変換やサムネイル生成（AVIF 変換以外）
- SVG 入力対応
