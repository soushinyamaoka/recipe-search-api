# レシピ検索API リファレンス v2.1

レシピ提案アプリからこのAPIを呼び出すためのリファレンスです。

---

## サーバー起動

```bash
cd recipe-search-api/
pip install -r requirements.txt
python app.py
# → http://localhost:8000 で起動
```

> Expo Goからアクセスする場合は `localhost` ではなくPCのローカルIP（例: `192.168.x.x`）を使用してください。

---

## アプリ連携用エンドポイント

### `POST /api/recipes/search`

AIレシピ生成APIの `/generate` と対になるエンドポイントです。

#### リクエスト

```json
{
  "season": "春",
  "category": "日本食",
  "freeText": "冷蔵庫に鶏肉がある"
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `season` | string | - | 季節（"春", "夏", "秋", "冬"） |
| `category` | string | - | 料理カテゴリ（"日本食", "中華", "イタリアン" 等） |
| `freeText` | string | - | 自由入力テキスト（食材や要望など） |
| `servings` | number | - | 人数（受け付けるが検索には使用しない） |

※ `season`, `category`, `freeText` のうち最低1つが必要です。

#### レスポンス（成功時）

3件のレシピを返します。異なるサイトからバランスよく選出されます。

```json
{
  "recipes": [
    {
      "name": "鶏もも肉の照り焼き",
      "description": "定番の照り焼きレシピ。甘辛いタレで白ご飯にぴったりです。",
      "url": "https://cookpad.com/recipe/12345",
      "source": "クックパッド"
    },
    {
      "name": "春野菜と鶏肉の塩麹炒め",
      "description": "旬の春野菜と鶏肉を塩麹で炒めた、やさしい味わいの一品。",
      "url": "https://oceans-nadia.com/user/.../recipe/...",
      "source": "Nadia"
    },
    {
      "name": "鶏むね肉のさっぱり南蛮漬け",
      "description": "揚げ焼きにした鶏むね肉を甘酢に漬けた南蛮漬け。",
      "url": "https://www.sirogohan.com/recipe/...",
      "source": "白ごはん.com"
    }
  ]
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `name` | string | 必須 | レシピ名 |
| `description` | string | 必須 | レシピの概要・説明文（1〜2文程度） |
| `url` | string \| null | 必須 | レシピページのURL（取得できない場合は `null`） |
| `source` | string | 必須 | 出典サイト名（例: "クックパッド", "クラシル"） |

#### レスポンス（エラー時）

AIレシピAPIと同じ形式です。

```json
{
  "error": "「鶏肉 和食 春 旬」に一致するレシピが見つかりませんでした。別のキーワードでお試しください。"
}
```

| HTTPステータス | 内容 |
|---|---|
| 400 | パラメータ不足（season/category/freeTextがすべて空） |
| 404 | レシピが見つからない |
| 500 | サーバーエラー |

#### 検索キーワードの組み立てロジック

APIは `freeText`, `category`, `season` を組み合わせて検索キーワードを自動生成します。

| リクエスト例 | 生成される検索キーワード |
|---|---|
| `freeText: "冷蔵庫に鶏肉がある"` | `鶏肉` |
| `category: "日本食"` | `和食` |
| `season: "春"` | `春 旬` |
| `freeText: "鶏肉", category: "中華", season: "夏"` | `鶏肉 中華 夏 旬` |

`freeText` は「冷蔵庫に〜がある」「〜を使いたい」などの自然文から食材部分を自動抽出します。

---

## TypeScript 型定義（アプリ連携用）

```typescript
/** POST /api/recipes/search のリクエスト */
interface WebRecipeSearchRequest {
  season?: string;
  category?: string;
  freeText?: string;
  servings?: number;  // 受け付けるが検索には不使用
}

/** レスポンスの1件分 */
interface WebRecipeItem {
  name: string;
  description: string;
  url: string | null;
  source: string;
}

/** 成功レスポンス */
interface WebRecipeSearchResponse {
  recipes: WebRecipeItem[];
}

/** エラーレスポンス */
interface WebRecipeErrorResponse {
  error: string;
}
```

---

## APIクライアントコード（コピペ用）

```typescript
const API_BASE_URL =
  process.env.EXPO_PUBLIC_RECIPE_API_URL || "http://localhost:8000";

/**
 * Webレシピ検索（POST /api/recipes/search）
 */
export async function searchWebRecipes(params: {
  season?: string;
  category?: string;
  freeText?: string;
}): Promise<WebRecipeSearchResponse> {
  const res = await fetch(`${API_BASE_URL}/api/recipes/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data.error || `API Error: ${res.status}`);
  }

  return data;
}
```

---

## アプリ内での使い方（例）

```typescript
// 例1: 食材 + 季節 + カテゴリで検索
const result = await searchWebRecipes({
  season: "春",
  category: "日本食",
  freeText: "冷蔵庫に鶏肉がある",
});
// → result.recipes に3件のレシピ

// 例2: 食材だけで検索
const result2 = await searchWebRecipes({
  freeText: "豚肉とキャベツ",
});

// 例3: カテゴリだけで検索
const result3 = await searchWebRecipes({
  category: "イタリアン",
});

// 例4: エラーハンドリング
try {
  const result = await searchWebRecipes({ freeText: "鶏肉" });
  console.log(result.recipes);
} catch (e) {
  console.error(e.message); // "レシピが見つかりませんでした..."
}
```

---

## その他のエンドポイント（汎用）

アプリ連携用以外に、以下の汎用エンドポイントも引き続き利用できます。

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/search?q=カレー` | キーワード直指定の検索 |
| GET | `/detail?url=...` | レシピ詳細取得（材料・手順） |
| GET | `/sources` | 対応サイト一覧 |
| GET | `/docs` | Swagger UI |

---

## 補足

- **レスポンス速度**: 全10サイト並行検索で3〜8秒程度
- **Swagger UI**: `http://localhost:8000/docs` で全エンドポイントを試せます
- **対応サイト**: 楽天レシピ, 白ごはん.com, dancyu, クックパッド, Nadia, クラシル, DELISH KITCHEN, みんなのきょうの料理, レタスクラブ, 味の素パーク
