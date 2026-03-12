# mcp-server-insta-analytics

Instagram の投稿をリードオンリーで分析する MCP サーバー。エンゲージメント指標・センチメント分析・ハッシュタグ追跡などを提供します。

## Tools

| Tool | Description |
|------|-------------|
| `get_post_metrics` | 投稿のエンゲージメント率・いいね/コメント比率を取得 |
| `compare_post_performance` | 複数投稿のパフォーマンスを比較・ランキング |
| `search_posts_by_hashtag` | ハッシュタグで投稿を検索 |
| `track_hashtag_trend` | ハッシュタグのボリューム・エンゲージメント・トレンド方向 |
| `get_user_profile_analytics` | ユーザープロフィールのフォロワー指標・投稿頻度を分析 |
| `get_user_timeline_metrics` | ユーザーの直近投稿のエンゲージメント統計 |
| `get_engagement_timeseries` | ユーザーのエンゲージメント推移を時系列で表示 |
| `analyze_best_posting_times` | 過去データから最適な投稿時間帯を分析 |
| `get_post_comments` | 投稿のコメントを取得 |
| `analyze_comment_sentiment` | コメントのセンチメント分析（ポジティブ/ネガティブ分布） |

## Setup

### 1. 認証情報を取得（オプション）

公開プロフィールはログインなしでアクセスできます。ハッシュタグ検索やコメント取得にはセッション Cookie が必要です。

ブラウザで [instagram.com](https://www.instagram.com) にログインし、DevTools (F12) > Application > Cookies から `sessionid` を取得:

- `sessionid` → `INSTA_ANALYTICS_SESSION_COOKIE`

### 2. `.env` を作成

```bash
cp .env.example .env
```

`INSTA_ANALYTICS_SESSION_COOKIE` を記入します（オプション）。

## Local (Docker)

Docker だけで動きます。

```bash
docker compose up -d
```

`http://localhost:8001/mcp` で MCP サーバーが起動します。

### MCP クライアント設定

```json
{
  "mcpServers": {
    "insta-analytics": {
      "type": "streamable-http",
      "url": "http://localhost:8001/mcp/"
    }
  }
}
```

## AWS Lambda (常時無料枠)

Lambda Function URL + DynamoDB で運用。**S3 を含む期限付き無料枠は一切使用しません。**

### 使用する AWS リソース (すべて常時無料)

| リソース | 無料枠 |
|---------|--------|
| Lambda | 100万リクエスト + 40万GB秒/月 |
| DynamoDB | 25 RCU + 25 WCU + 25GB |
| Lambda Function URL | 無料 |
| CloudWatch Logs | 5GB/月 (保持期間1週間) |
| データ転送 | 100GB/月 |

### コスト保護

- **同時実行数制限** (10) — Lambda 無料枠超過を防止
- **Bearer トークン認証** — 不正アクセスを遮断 (トークンなしは即 403)
- **ログ保持期間 1 週間** — ストレージ蓄積を防止
- **アプリ内レート制限** — 15 req/min, 500 req/day

### 前提条件

- AWS CLI 設定済み (`aws configure` or `aws sso login`)
- [uv](https://docs.astral.sh/uv/) インストール済み

### デプロイ

```bash
# 環境変数を設定
export SESSION_COOKIE=xxx   # ブラウザ Cookies > sessionid (オプション)
export API_KEY=zzz          # 任意の文字列 (アクセス保護用)

# デプロイ
./deploy.sh
```

デプロイ後に表示される Function URL と API Key を MCP クライアントに設定:

```json
{
  "mcpServers": {
    "insta-analytics": {
      "type": "streamable-http",
      "url": "https://xxxxxxxxxx.lambda-url.ap-northeast-1.on.aws/mcp/",
      "headers": {
        "Authorization": "Bearer zzz"
      }
    }
  }
}
```

### 運用コマンド

```bash
# コード更新のみ (スタック変更なし)
./deploy.sh --update

# Session Cookie だけ差し替え (再デプロイ不要)
export SESSION_COOKIE=new_cookie
./deploy.sh --rotate-cookie

# 無料枠の使用状況を表示
./deploy.sh --status

# 全リソース一括削除
./deploy.sh --destroy
```

## Development

```bash
uv sync --all-extras
uv run pytest tests/ -q
uv run pyright src/
uv run ruff check src/
```
