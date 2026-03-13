# AVIF 変換の技術調査

## 調査日: 2026-03-13

## 目的

Cloudflare Worker 内で画像を AVIF に変換してから R2 に保存する方法を調査。

## 調査結果

### 方法1: Cloudflare Image Resizing バインディング (推奨)

**実現性: 推奨**

Cloudflare Image Resizing はネイティブで AVIF をサポート。Rust 製 `rav1e` エンコーダを使用。

- `format=auto`: Accept ヘッダに基づいて WebP/AVIF/JPEG を自動選択
- `format=avif`: 明示的に AVIF を指定
- quality: 1-100（推奨 50-90、デフォルト 85）

#### Worker での使用方法

```typescript
// wrangler.toml
// [images]
// binding = "IMAGES"

const response = await env.IMAGES
  .input(imageBuffer)
  .output({ format: 'avif', quality: 80 })
  .run();
```

#### 制限事項

| 制限項目 | 詳細 |
|---------|------|
| 最大解像度 | 1,600px（`format=avif` 明示時の上限） |
| 処理速度 | 他フォーマットより「1桁遅い」 |
| フォールバック | サイズ超過時は自動的に WebP/JPEG に降格 |
| 料金 | Pro 以上、または Images サブスクリプション必須 |

#### 参考リンク

- https://blog.cloudflare.com/generate-avif-images-with-image-resizing/
- https://developers.cloudflare.com/images/transform-images/
- https://developers.cloudflare.com/images/transform-images/bindings/

### 方法2: WebAssembly ベース AVIF エンコーダ (非推奨)

**実現性: 非推奨**

利用可能なパッケージ:
- `@jsquash/avif` - libavif ベース
- `@saschazar/wasm-avif` - AOMediaCodec/libavif 使用

#### 制約

- Cloudflare Workers は動的インポート不可（WASM バイナリを事前バンドル必須）
- 処理が非常に遅い（単一スレッド環境で 10 秒以内推奨）
- WASM での AVIF エンコーディングは「遅く、エラーが起きやすい」
- WebP や MozJPEG の方が Workers では現実的

#### 参考リンク

- https://github.com/jamsinclair/jSquash

### 方法3: クライアント側変換 (不採用)

クライアント（エージェント）側で AVIF に変換してから Worker にアップロードする方式。
一貫性が保てず、エージェント側に変換ツールのインストールが必要になるため不採用。

## Cloudflare Workers のリソース制限

| リソース | 制限値 |
|---------|--------|
| CPU 時間 | デフォルト 30 秒、最大 5 分 |
| メモリ | 128 MB |
| ネットワーク待機時間 | CPU 時間にカウントされない |

## 結論

| 方法 | 実現性 | 理由 |
|------|--------|------|
| Cloudflare Image Resizing + R2 | 推奨 | ネイティブ対応、実績豊富、性能安定 |
| WASM AVIF in Workers | 非推奨 | 遅い、複雑、メモリ制約大 |
| クライアント側変換 | 不採用 | 一貫性なし、依存増 |

### 採用するアプローチ

**Cloudflare Image Resizing バインディング** を使用。
1,600px 超の画像は WebP にフォールバックし、変換完全失敗時は元画像をそのまま保存する。
