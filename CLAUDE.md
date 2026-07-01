# レシピ検索API - CLAUDE.md

## プロジェクト概要

日本の主要レシピサイト10サイトからレシピを横断検索するWebスクレイピングAPI。
レシピ提案アプリ（Expo GO）のバックエンドとして動作し、ユーザーの「レシピを考える手間」「作る手間」を減らすことを目的とする。

### 対応レシピサイト（10サイト）

楽天レシピ / 白ごはん.com / dancyu / クックパッド / Nadia / クラシル / DELISH KITCHEN / みんなのきょうの料理（NHK） / レタスクラブ / 味の素パーク

## ディレクトリ構成

```
recipe-search-api/
├── app.py                  # メインアプリケーション（全ロジックを含む単一ファイル）
├── requirements.txt        # Pythonパッケージ依存関係
├── recipe-api-reference.md # アプリ連携用APIリファレンス
├── deploy-files.txt        # デプロイ対象ファイル一覧
├── CLAUDE.md               # 本ファイル
└── .claude/
    └── settings.json       # Claude Code プロジェクト固有設定
```

### app.py の構成（約1376行）

| セクション | 行範囲 | 内容 |
|---|---|---|
| データモデル | ~50-113 | Recipe, SearchResult, RecipeDetail, AppSearchRequest/Response |
| build_search_query | ~115-155 | freeText/category/season → 検索キーワード変換 |
| HTTPユーティリティ | ~158-210 | fetch_page, parse_iso_duration, extract_jsonld_recipe |
| シンプルモード関連 | ~211-275 | _relevance_score, _simplicity_score, _sort_by_simplicity |
| 各サイトスクレイパー | ~280-1080 | 10サイト分のスクレイピング関数（各50-80行程度） |
| レシピ詳細取得 | ~1080-1118 | get_recipe_detail_from_url（JSON-LD + HTMLフォールバック） |
| APIエンドポイント | ~1120-1363 | /, POST /api/recipes/search, GET /search, GET /detail, GET /sources |
| 起動 | ~1365-1376 | uvicorn起動（port 8002） |

## 使用技術・ライブラリ

| パッケージ | バージョン | 用途 |
|---|---|---|
| Python | 3.x | 実行環境 |
| fastapi | 0.115.6 | Webフレームワーク |
| uvicorn[standard] | 0.34.0 | ASGIサーバー |
| httpx | 0.28.1 | 非同期HTTPクライアント（スクレイピング用） |
| beautifulsoup4 | 4.12.3 | HTMLパーサー |
| pydantic | 2.10.4 | データバリデーション |

## サーバー構成・ポート番号

### ローカル開発

- **ポート**: 8002
- **URL**: http://localhost:8002
- **Swagger UI**: http://localhost:8002/docs

### さくらVPS（本番）

> 詳細は server-config.md を参照（.gitignore対象・リポジトリ非公開）

## APIエンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| POST | `/api/recipes/search` | アプリ連携用レシピ検索（メイン） |
| GET | `/search?q=カレー` | キーワード直指定の検索 |
| GET | `/detail?url=...` | レシピ詳細取得（材料・手順） |
| GET | `/sources` | 対応サイト一覧 |
| GET | `/docs` | Swagger UI |

### POST /api/recipes/search の主要パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| freeText | string | null | 自由入力テキスト |
| category | string | null | 料理カテゴリ |
| season | string | null | 季節 |
| offset | int | 0 | ページング開始位置 |
| limit | int | 3 | 取得件数 |
| simple_mode | bool | false | シンプルレシピ優先モード（詳細ページ取得で判定、追加5-6秒） |

## ビルド・デプロイ手順

### ローカル起動

```bash
cd recipe-search-api/
pip install -r requirements.txt
python app.py
# → http://localhost:8002 で起動
```

### VPSデプロイ

1. deploy-files.txt に記載のファイル（app.py, requirements.txt）をVPSへ転送
2. VPS上で pip install -r requirements.txt
3. systemd サービスを再起動

## 開発時の注意事項

- **単一ファイル構成**: すべてのロジックが app.py に集約されている。分割は行っていない
- **Windows環境**: 開発はWindows上で行う。cp932エンコーディングの制約があるため、print文に絵文字を使わないこと
- **スクレイピング上限**: 各サイトのスクレイパーは最大50件を取得（`unique[:50]`）
- **並行処理**: 全10サイトを asyncio.gather で並行検索。シンプルモード時は詳細ページも最大60件を並列取得（Semaphore=10で同時接続制限）
- **.envファイル**: 現状は使用していない。APIキー等の秘密情報はなし
- **サーバープロセス管理（Windows）**: uvicornプロセスが残る場合は `netstat -ano | grep 8002` でPIDを確認し `taskkill //PID <pid> //F` で停止

## コミットルール

- コミットは「コミットして」と指示があった時のみ行う
- コミットの前に必ず変更内容に以下の機密情報が含まれていないか確認する
  - APIキー・トークン
  - パスワード
  - 個人情報（メールアドレス・電話番号等）
  - サーバーのIPアドレス・接続情報
  - .envファイルの内容
- 機密情報が含まれる場合は作業を中断してその旨を報告する
- 機密情報が含まれない場合のみコミットを実行する
- コミットメッセージは以下の形式で日本語で書く
  - バグ修正：`fix: 内容`
  - 新機能：`feat: 内容`
  - リファクタリング：`refactor: 内容`
  - その他：`chore: 内容`
- コミット後は自動でpushまで行う

## よく使うコマンド

```bash
# ローカルサーバー起動
python app.py

# 動作確認（ルート）
curl -s http://localhost:8002/

# アプリ連携検索テスト
curl -s -X POST http://localhost:8002/api/recipes/search \
  -H "Content-Type: application/json" \
  -d '{"freeText": "鶏肉", "offset": 0, "limit": 3}'

# シンプルモード検索テスト
curl -s -X POST http://localhost:8002/api/recipes/search \
  -H "Content-Type: application/json" \
  -d '{"freeText": "鶏肉", "simple_mode": true, "limit": 3}'

# キーワード検索テスト
curl -s "http://localhost:8002/search?q=カレー"

# レシピ詳細テスト
curl -s "http://localhost:8002/detail?url=<レシピURL>"

# 対応サイト一覧
curl -s http://localhost:8002/sources

# ポート8002を使用中のプロセス確認（Windows）
netstat -ano | grep 8002

# パッケージインストール
pip install -r requirements.txt
```
