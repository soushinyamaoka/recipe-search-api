"""
レシピ検索API v2.1 - 10サイト対応 + アプリ連携エンドポイント
FastAPI + BeautifulSoup によるWebスクレイピングAPI

対応サイト:
  1. 楽天レシピ
  2. 白ごはん.com
  3. dancyu
  4. クックパッド
  5. Nadia（ナディア）
  6. クラシル
  7. DELISH KITCHEN
  8. みんなのきょうの料理（NHK）
  9. レタスクラブ
  10. 味の素パーク

アプリ連携:
  POST /api/recipes/search - レシピ提案アプリからの検索用
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlencode, urljoin
import re
import json

app = FastAPI(
    title="レシピ検索API",
    description="日本の主要レシピサイト10サイトからレシピを横断検索するAPI",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# データモデル
# ============================================================

class Recipe(BaseModel):
    title: str
    url: str
    image_url: Optional[str] = None
    description: Optional[str] = None
    source: str
    cooking_time: Optional[str] = None
    servings: Optional[str] = None
    author: Optional[str] = None

class SearchResult(BaseModel):
    query: str
    total: int
    source: Optional[str] = None
    recipes: list[Recipe]

class RecipeDetail(BaseModel):
    title: str
    url: str
    image_url: Optional[str] = None
    source: str
    description: Optional[str] = None
    cooking_time: Optional[str] = None
    servings: Optional[str] = None
    author: Optional[str] = None
    ingredients: list[dict] = []
    steps: list[dict] = []
    tips: Optional[str] = None
    calories: Optional[str] = None

# ============================================================
# アプリ連携用モデル（POST /api/recipes/search）
# ============================================================

class AppSearchRequest(BaseModel):
    """アプリ側からのリクエスト（AIレシピ生成APIと同じ形式）"""
    season: Optional[str] = None       # 例: "春", "夏", "秋", "冬"
    category: Optional[str] = None     # 例: "日本食", "中華", "イタリアン"
    freeText: Optional[str] = None     # 例: "冷蔵庫に鶏肉がある"
    servings: Optional[int] = None     # 人数（あっても無視するが受け付ける）
    offset: int = 0                    # 取得開始位置（0始まり）
    limit: int = 3                     # 1回に取得する件数（デフォルト3件）
    simple_mode: bool = False          # シンプルレシピ優先モード

class AppRecipeItem(BaseModel):
    """アプリ側へのレスポンス（1件分）"""
    name: str                          # レシピ名
    description: str                   # 概要・説明文（1〜2文）
    url: Optional[str] = None          # レシピページURL（取得できない場合はnull）
    source: str                        # 出典サイト名

class AppSearchResponse(BaseModel):
    """アプリ側へのレスポンス"""
    recipes: list[AppRecipeItem]
    total: int                         # フィルタ後の総件数
    offset: int                        # 今回の取得開始位置
    limit: int                         # 今回の取得件数
    simple_mode: bool = False          # シンプルレシピ優先モードが有効か

class AppErrorResponse(BaseModel):
    """エラーレスポンス（AIレシピAPIと同じ形式）"""
    error: str


def build_search_query(req: AppSearchRequest) -> str:
    """リクエストのseason/category/freeTextから検索キーワードを組み立てる"""
    parts = []

    # freeTextから食材や料理名を抽出（メインのキーワード）
    if req.freeText:
        # 「冷蔵庫に鶏肉がある」→「鶏肉」のように食材を抽出する簡易ロジック
        text = req.freeText
        # よくあるフレーズを除去して食材部分を残す
        noise_phrases = [
            "冷蔵庫に", "冷凍庫に", "家に", "余っている", "余ってる",
            "がある", "があります", "が残っている", "が残ってる",
            "を使いたい", "を使った", "で何か", "で作れる", "で作りたい",
            "を消費したい", "を使い切りたい",
        ]
        cleaned = text
        for phrase in noise_phrases:
            cleaned = cleaned.replace(phrase, " ")
        cleaned = cleaned.strip()
        if cleaned:
            parts.append(cleaned)
        else:
            parts.append(text)  # クリーニングで全部消えたら元のテキストを使う

    # カテゴリ（日本食、中華など）
    if req.category:
        # 「日本食」→「和食」に変換（検索ヒット率向上）
        category_map = {
            "日本食": "和食",
            "日本料理": "和食",
            "西洋料理": "洋食",
            "韓国料理": "韓国",
        }
        parts.append(category_map.get(req.category, req.category))

    # 季節（春→春 旬 のように検索ワードに追加）
    if req.season:
        parts.append(f"{req.season} 旬")

    query = " ".join(parts)
    return query if query.strip() else "おすすめ レシピ"


# ============================================================
# HTTP ユーティリティ
# ============================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

async def fetch_page(url: str, timeout: float = 15.0) -> str:
    """ページのHTMLを取得"""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.text


def parse_iso_duration(duration: str) -> str:
    """ISO 8601の期間（PT30M等）を日本語に変換"""
    if not duration or not duration.startswith("PT"):
        return duration or ""
    parts = []
    time_match = re.findall(r"(\d+)([HMS])", duration)
    for val, unit in time_match:
        label = {"H": "時間", "M": "分", "S": "秒"}.get(unit, unit)
        parts.append(f"{val}{label}")
    return "".join(parts) if parts else duration


def extract_jsonld_recipe(soup: BeautifulSoup) -> dict:
    """JSON-LD (Schema.org/Recipe) からレシピデータを抽出"""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string)
            # リスト形式
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Recipe":
                        return item
            # @graph形式
            if isinstance(data, dict):
                if data.get("@type") == "Recipe":
                    return data
                for item in data.get("@graph", []):
                    if isinstance(item, dict) and item.get("@type") == "Recipe":
                        return item
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


def _parse_duration_to_minutes(duration: str) -> Optional[int]:
    """ISO 8601の期間文字列（PT30M等）を分数に変換。パースできない場合はNone"""
    if not duration or not duration.startswith("PT"):
        return None
    total = 0
    for val, unit in re.findall(r"(\d+)([HMS])", duration):
        if unit == "H":
            total += int(val) * 60
        elif unit == "M":
            total += int(val)
        elif unit == "S":
            total += max(1, int(val) // 60)
    return total if total > 0 else None


def _simplicity_score(ingredient_count: int, step_count: int, cook_minutes: Optional[int]) -> int:
    """レシピのシンプルさスコアを算出（高いほどシンプル）"""
    score = 100
    score -= ingredient_count * 3   # 材料が多いほど減点
    score -= step_count * 5         # 手順が多いほど減点
    if cook_minutes is not None:
        score -= cook_minutes       # 調理時間が長いほど減点
    return score


async def _fetch_simplicity_data(url: str, semaphore: asyncio.Semaphore) -> dict:
    """1件のレシピURLからシンプルさ判定に必要なデータを取得"""
    async with semaphore:
        try:
            html = await fetch_page(url, timeout=10.0)
            soup = BeautifulSoup(html, "html.parser")
            ld = extract_jsonld_recipe(soup)
            ingredient_count = len(ld.get("recipeIngredient", []))
            step_count = len(ld.get("recipeInstructions", []))
            cook_time = ld.get("cookTime") or ld.get("totalTime") or ""
            cook_minutes = _parse_duration_to_minutes(cook_time)
            return {
                "url": url,
                "ingredient_count": ingredient_count,
                "step_count": step_count,
                "cook_minutes": cook_minutes,
                "score": _simplicity_score(ingredient_count, step_count, cook_minutes),
            }
        except Exception:
            return {"url": url, "score": 0}


async def _sort_by_simplicity(recipes: list[Recipe], max_fetch: int = 60) -> list[Recipe]:
    """レシピのシンプルさスコアで並べ替える（詳細ページを並列取得して判定）"""
    targets = recipes[:max_fetch]
    rest = recipes[max_fetch:]

    semaphore = asyncio.Semaphore(10)
    tasks = [_fetch_simplicity_data(r.url, semaphore) for r in targets if r.url]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    score_map: dict[str, int] = {}
    for r in results:
        if isinstance(r, dict) and "url" in r:
            score_map[r["url"]] = r.get("score", 0)

    targets.sort(key=lambda r: score_map.get(r.url, 0), reverse=True)
    return targets + rest


def _relevance_score(title: str, query: str) -> int:
    """レシピタイトルの検索キーワードとの関連度スコアを算出（高いほど関連度が高い）"""
    if not query or not title:
        return 1
    keywords = [k.strip() for k in query.split() if len(k.strip()) >= 1]
    if not keywords:
        return 1
    title_lower = title.lower()
    score = 0
    for k in keywords:
        kl = k.lower()
        if kl in title_lower:
            # 完全一致（例: "鶏肉" がタイトルに含まれる）
            score += 10
        elif len(kl) >= 2 and any(c in title_lower for c in kl):
            # 部分一致（例: "鶏肉" → "鶏" がタイトルに含まれる）
            matched_chars = sum(1 for c in kl if c in title_lower)
            score += matched_chars
    return score


def is_relevant_recipe(title: str, query: str) -> bool:
    """レシピタイトルが検索キーワードと関連しているか簡易チェック"""
    return _relevance_score(title, query) > 0


# ノイズタイトル（UI要素やナビゲーション）を除外するパターン
NOISE_TITLES = {
    "レシピを書く", "レシピを探す", "お気に入り", "RECIPE",
    "検索結果", "新着レシピ", "人気レシピ", "ランキング",
    "もっと見る", "一覧を見る", "トップページ",
}


def is_noise_title(title: str) -> bool:
    """ノイズタイトル（UI要素）かどうか判定"""
    cleaned = title.strip()
    if cleaned in NOISE_TITLES:
        return True
    # 「〜の検索結果」パターン
    if cleaned.endswith("の検索結果") or cleaned.startswith("「") and "検索結果" in cleaned:
        return True
    return False


# ============================================================
# 1. 楽天レシピ
# ============================================================

async def search_rakuten(query: str, page: int = 1) -> list[Recipe]:
    """楽天レシピからレシピを検索"""
    recipes = []
    try:
        page_url = f"https://recipe.rakuten.co.jp/search/{quote_plus(query)}/{page}/"
        html = await fetch_page(page_url)
        soup = BeautifulSoup(html, "html.parser")

        # JSON-LD の ItemList からレシピURLを取得（最も正確）
        recipe_urls_from_ld = set()
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("@type") == "ItemList":
                    for item in data.get("itemListElement", []):
                        item_url = item.get("url", "")
                        if item_url:
                            recipe_urls_from_ld.add(item_url)
            except (json.JSONDecodeError, TypeError):
                continue

        # JSON-LDがあればそれを使う
        if recipe_urls_from_ld:
            for card in soup.select("a[href]"):
                try:
                    link = card.get("href", "")
                    if not link.startswith("http"):
                        link = urljoin(page_url, link)
                    if link not in recipe_urls_from_ld:
                        continue
                    title = card.get_text(strip=True)
                    if len(title) < 3:
                        continue
                    # タイトルからランキングノイズを除去
                    title = re.sub(r'^\d+位\s*', '', title)
                    title = re.sub(r'^PICK\s*UP\s*', '', title)
                    img_el = card.select_one("img")
                    img_url = img_el.get("src") if img_el else None
                    recipes.append(Recipe(
                        title=title[:100],
                        url=link,
                        image_url=img_url,
                        source="楽天レシピ",
                    ))
                except Exception:
                    continue
        else:
            # フォールバック: URLパターンで厳密にフィルタ
            for card in soup.select("a[href]"):
                try:
                    link = card.get("href", "")
                    if not link.startswith("http"):
                        link = urljoin(page_url, link)
                    # /recipe/数字/ パターンのみ許可
                    if not re.search(r'/recipe/\d+/', link):
                        continue
                    title = card.get_text(strip=True)
                    if len(title) < 3:
                        continue
                    title = re.sub(r'^\d+位\s*', '', title)
                    title = re.sub(r'^PICK\s*UP\s*', '', title)
                    img_el = card.select_one("img")
                    img_url = img_el.get("src") if img_el else None
                    recipes.append(Recipe(
                        title=title[:100],
                        url=link,
                        image_url=img_url,
                        source="楽天レシピ",
                    ))
                except Exception:
                    continue

        # 重複除去
        seen = set()
        unique = []
        for r in recipes:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        recipes = unique[:50]
    except Exception as e:
        print(f"[楽天レシピ] エラー: {e}")
    return recipes


# ============================================================
# 2. 白ごはん.com
# ============================================================

async def search_sirogohan(query: str) -> list[Recipe]:
    """白ごはん.comからレシピを検索"""
    recipes = []
    try:
        page_url = f"https://www.sirogohan.com/?s={quote_plus(query)}"
        html = await fetch_page(page_url)
        soup = BeautifulSoup(html, "html.parser")

        # 白ごはん.comはレシピリンクが /recipe/ パスを持つ <a> タグ
        for a_el in soup.select("a[href*='/recipe/']"):
            try:
                link = a_el.get("href", "")
                if not link.startswith("http"):
                    link = urljoin(page_url, link)
                # カテゴリページ(/recipe/index/)を除外、個別レシピのみ
                if "/recipe/index/" in link:
                    continue
                title_el = a_el.select_one("h2, h3")
                title = title_el.get_text(strip=True) if title_el else a_el.get_text(strip=True)
                if len(title) < 3:
                    continue
                img_el = a_el.select_one("img")
                img_url = img_el.get("src") if img_el else None
                desc_el = a_el.select_one("p")
                desc = desc_el.get_text(strip=True)[:120] if desc_el else None
                recipes.append(Recipe(
                    title=title[:100],
                    url=link,
                    image_url=img_url,
                    description=desc,
                    source="白ごはん.com",
                ))
            except Exception:
                continue

        # 重複除去
        seen = set()
        unique = []
        for r in recipes:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        recipes = unique
    except Exception as e:
        print(f"[白ごはん.com] エラー: {e}")
    return recipes[:50]


# ============================================================
# 3. dancyu
# ============================================================

async def search_dancyu(query: str) -> list[Recipe]:
    """dancyu Webからレシピを検索"""
    recipes = []
    try:
        page_url = f"https://dancyu.jp/?s={quote_plus(query)}&post_type=recipe"
        html = await fetch_page(page_url)
        soup = BeautifulSoup(html, "html.parser")

        # dancyuはrecipeパスを含むリンクを直接探す
        for a_el in soup.select("a[href*='recipe/']"):
            try:
                link = a_el.get("href", "")
                # urljoinで相対パス (../../recipe/...) を正しく解決
                if not link.startswith("http"):
                    link = urljoin(page_url, link)
                # /recipe/ パスを含むもののみ（/read/ 記事を除外）
                if "/recipe/" not in link:
                    continue
                # ナビゲーションリンク（/recipe/ のみ）を除外
                if re.match(r'^https://dancyu\.jp/recipe/?$', link):
                    continue

                title_el = a_el.select_one("h2, h3, p")
                title = title_el.get_text(strip=True) if title_el else a_el.get_text(strip=True)
                # 日付のみのタイトルを除外
                if len(title) < 3 or re.match(r'^\d{4}[\.\-/]\d{2}[\.\-/]\d{2}$', title):
                    continue
                img_el = a_el.select_one("img")
                img_url = img_el.get("src") if img_el else None
                recipes.append(Recipe(
                    title=title[:100],
                    url=link,
                    image_url=img_url,
                    source="dancyu",
                ))
            except Exception:
                continue

        # 重複除去
        seen = set()
        unique = []
        for r in recipes:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        recipes = unique
    except Exception as e:
        print(f"[dancyu] エラー: {e}")
    return recipes[:50]


# ============================================================
# 4. クックパッド
# ============================================================

async def search_cookpad(query: str, page: int = 1) -> list[Recipe]:
    """クックパッドからレシピを検索"""
    recipes = []
    try:
        url = f"https://cookpad.com/jp/search/{quote_plus(query)}?page={page}"
        html = await fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")

        # レシピカードを検索
        for card in soup.select("[class*='recipe'], li[class*='Recipe'], a[href*='/recipes/']"):
            try:
                a_el = card if card.name == "a" else card.select_one("a[href*='/recipes/']")
                if not a_el:
                    continue
                link = a_el.get("href", "")
                if not link.startswith("http"):
                    link = "https://cookpad.com" + link
                if "/recipes/" not in link:
                    continue

                title_el = card.select_one("h2, h3, [class*='title'], [class*='name']")
                title = title_el.get_text(strip=True) if title_el else a_el.get_text(strip=True)
                if len(title) < 3:
                    continue

                img_el = card.select_one("img")
                img_url = img_el.get("src") or img_el.get("data-src") if img_el else None

                author_el = card.select_one("[class*='author'], [class*='user']")
                author = author_el.get_text(strip=True) if author_el else None

                recipes.append(Recipe(
                    title=title[:100],
                    url=link,
                    image_url=img_url,
                    source="クックパッド",
                    author=author,
                ))
            except Exception:
                continue

        seen = set()
        unique = []
        for r in recipes:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        recipes = unique[:50]
    except Exception as e:
        print(f"[クックパッド] エラー: {e}")
    return recipes


# ============================================================
# 5. Nadia（ナディア）
# ============================================================

async def search_nadia(query: str) -> list[Recipe]:
    """Nadia（ナディア）からレシピを検索"""
    recipes = []
    try:
        page_url = f"https://oceans-nadia.com/search?keyword={quote_plus(query)}"
        html = await fetch_page(page_url)
        soup = BeautifulSoup(html, "html.parser")

        # Nadiaは SPA のため、__NEXT_DATA__ や埋め込みJSONからデータを抽出
        for script in soup.select("script"):
            try:
                text = script.string or ""
                # __NEXT_DATA__ からレシピデータを抽出
                if script.get("id") == "__NEXT_DATA__":
                    data = json.loads(text)
                    # pageProps内のレシピデータを探索
                    page_props = data.get("props", {}).get("pageProps", {})
                    # data.publishedRecipes.data のネスト構造を探索
                    pr = page_props.get("data", {}).get("publishedRecipes", {})
                    if isinstance(pr, dict):
                        recipe_list = pr.get("data", [])
                    elif isinstance(pr, list):
                        recipe_list = pr
                    else:
                        recipe_list = (
                            page_props.get("publishedRecipes")
                            or page_props.get("recipes")
                            or []
                        )
                    for item in recipe_list:
                        if not isinstance(item, dict):
                            continue
                        title = item.get("title", "")
                        recipe_id = item.get("id", "")
                        user_id = item.get("userId", "") or item.get("user_id", "")
                        if not title or not recipe_id:
                            continue
                        # ユーザー情報
                        user_data = item.get("user", {})
                        author = (user_data.get("nickname") or user_data.get("name")) if isinstance(user_data, dict) else None
                        # URL構築
                        if user_id:
                            link = f"https://oceans-nadia.com/user/{user_id}/recipe/{recipe_id}"
                        else:
                            link = f"https://oceans-nadia.com/recipe/{recipe_id}"
                        # 画像
                        img_url = None
                        image_set = item.get("imageSet") or item.get("image")
                        if isinstance(image_set, dict):
                            img_url = image_set.get("t", {}).get("url") or image_set.get("url")
                        elif isinstance(image_set, str):
                            img_url = image_set
                        recipes.append(Recipe(
                            title=title[:100],
                            url=link,
                            image_url=img_url,
                            source="Nadia",
                            author=author,
                            cooking_time=str(item.get("cookTime", "")) or None,
                        ))
                    if recipes:
                        break

                # publishedRecipes が直接埋め込まれている場合
                if "publishedRecipes" in text:
                    match = re.search(r'"publishedRecipes"\s*:\s*(\[.*?\])\s*[,}]', text)
                    if match:
                        recipe_list = json.loads(match.group(1))
                        for item in recipe_list:
                            if not isinstance(item, dict):
                                continue
                            title = item.get("title", "")
                            recipe_id = item.get("id", "")
                            user_id = item.get("userId", "")
                            if not title or not recipe_id:
                                continue
                            user_data = item.get("user", {})
                            author = user_data.get("name") if isinstance(user_data, dict) else None
                            if user_id:
                                link = f"https://oceans-nadia.com/user/{user_id}/recipe/{recipe_id}"
                            else:
                                link = f"https://oceans-nadia.com/recipe/{recipe_id}"
                            recipes.append(Recipe(
                                title=title[:100],
                                url=link,
                                source="Nadia",
                                author=author,
                            ))
                        if recipes:
                            break
            except (json.JSONDecodeError, TypeError):
                continue

        # HTMLフォールバック（上記で取得できなかった場合）
        if not recipes:
            for a_el in soup.select("a[href*='/recipe/']"):
                try:
                    link = a_el.get("href", "")
                    if not link.startswith("http"):
                        link = urljoin(page_url, link)
                    title = a_el.get_text(strip=True)
                    if len(title) < 3:
                        continue
                    recipes.append(Recipe(
                        title=title[:100],
                        url=link,
                        source="Nadia",
                    ))
                except Exception:
                    continue

        # 重複除去
        seen = set()
        unique = []
        for r in recipes:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        recipes = unique[:50]
    except Exception as e:
        print(f"[Nadia] エラー: {e}")
    return recipes


# ============================================================
# 6. クラシル
# ============================================================

async def search_kurashiru(query: str) -> list[Recipe]:
    """クラシルからレシピを検索"""
    recipes = []
    try:
        url = f"https://www.kurashiru.com/search?query={quote_plus(query)}"
        html = await fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")

        for card in soup.select("[class*='recipe'], article, a[href*='/recipes/']"):
            try:
                a_el = card if card.name == "a" else card.select_one("a[href*='/recipes/']")
                if not a_el:
                    continue
                link = a_el.get("href", "")
                if not link.startswith("http"):
                    link = "https://www.kurashiru.com" + link
                if "/recipes/" not in link:
                    continue

                title_el = card.select_one("h2, h3, [class*='title'], [class*='name']")
                title = title_el.get_text(strip=True) if title_el else a_el.get_text(strip=True)
                if len(title) < 3:
                    continue

                img_el = card.select_one("img")
                img_url = img_el.get("src") or img_el.get("data-src") if img_el else None

                desc_el = card.select_one("p, [class*='description']")
                desc = desc_el.get_text(strip=True)[:120] if desc_el else None

                recipes.append(Recipe(
                    title=title[:100],
                    url=link,
                    image_url=img_url,
                    description=desc,
                    source="クラシル",
                ))
            except Exception:
                continue

        seen = set()
        unique = []
        for r in recipes:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        recipes = unique[:50]
    except Exception as e:
        print(f"[クラシル] エラー: {e}")
    return recipes


# ============================================================
# 7. DELISH KITCHEN
# ============================================================

async def search_delish_kitchen(query: str) -> list[Recipe]:
    """DELISH KITCHENからレシピを検索"""
    recipes = []
    try:
        url = f"https://delishkitchen.tv/search?q={quote_plus(query)}"
        html = await fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")

        for card in soup.select("[class*='recipe'], article, a[href*='/recipes/']"):
            try:
                a_el = card if card.name == "a" else card.select_one("a[href*='/recipes/']")
                if not a_el:
                    continue
                link = a_el.get("href", "")
                if not link.startswith("http"):
                    link = "https://delishkitchen.tv" + link
                if "/recipes/" not in link:
                    continue

                title_el = card.select_one("h2, h3, [class*='title'], [class*='name']")
                title = title_el.get_text(strip=True) if title_el else a_el.get_text(strip=True)
                if len(title) < 3:
                    continue

                img_el = card.select_one("img")
                img_url = img_el.get("src") or img_el.get("data-src") if img_el else None

                recipes.append(Recipe(
                    title=title[:100],
                    url=link,
                    image_url=img_url,
                    source="DELISH KITCHEN",
                ))
            except Exception:
                continue

        seen = set()
        unique = []
        for r in recipes:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        recipes = unique[:50]
    except Exception as e:
        print(f"[DELISH KITCHEN] エラー: {e}")
    return recipes


# ============================================================
# 8. みんなのきょうの料理（NHK）
# ============================================================

async def search_kyounoryouri(query: str) -> list[Recipe]:
    """みんなのきょうの料理からレシピを検索"""
    recipes = []
    try:
        url = f"https://www.kyounoryouri.jp/search/recipe?keyword={quote_plus(query)}"
        html = await fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")

        for card in soup.select("[class*='recipe'], article, .card, li"):
            try:
                a_el = card.select_one("a[href*='/recipe/']")
                if not a_el:
                    if card.name == "a" and "/recipe/" in card.get("href", ""):
                        a_el = card
                    else:
                        continue
                link = a_el.get("href", "")
                if not link.startswith("http"):
                    link = "https://www.kyounoryouri.jp" + link

                title_el = card.select_one("h2, h3, [class*='title'], [class*='name']")
                title = title_el.get_text(strip=True) if title_el else a_el.get_text(strip=True)
                if len(title) < 3:
                    continue

                img_el = card.select_one("img")
                img_url = img_el.get("src") or img_el.get("data-src") if img_el else None

                author_el = card.select_one("[class*='chef'], [class*='author'], [class*='teacher']")
                author = author_el.get_text(strip=True) if author_el else None

                recipes.append(Recipe(
                    title=title[:100],
                    url=link,
                    image_url=img_url,
                    source="みんなのきょうの料理",
                    author=author,
                ))
            except Exception:
                continue

        seen = set()
        unique = []
        for r in recipes:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        recipes = unique[:50]
    except Exception as e:
        print(f"[みんなのきょうの料理] エラー: {e}")
    return recipes


# ============================================================
# 9. レタスクラブ
# ============================================================

async def search_lettuceclub(query: str) -> list[Recipe]:
    """レタスクラブからレシピを検索"""
    recipes = []
    try:
        url = f"https://www.lettuceclub.net/recipe/search/{quote_plus(query)}/"
        html = await fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")

        for card in soup.select("[class*='recipe'], article, .card, a[href*='/recipe/dish/']"):
            try:
                a_el = card if card.name == "a" else card.select_one("a[href*='/recipe/']")
                if not a_el:
                    continue
                link = a_el.get("href", "")
                if not link.startswith("http"):
                    link = "https://www.lettuceclub.net" + link
                if "/recipe/" not in link:
                    continue

                title_el = card.select_one("h2, h3, [class*='title'], [class*='name']")
                title = title_el.get_text(strip=True) if title_el else a_el.get_text(strip=True)
                if len(title) < 3:
                    continue

                img_el = card.select_one("img")
                img_url = img_el.get("src") or img_el.get("data-src") if img_el else None

                cal_el = card.select_one("[class*='calorie'], [class*='cal']")
                cal = cal_el.get_text(strip=True) if cal_el else None

                recipes.append(Recipe(
                    title=title[:100],
                    url=link,
                    image_url=img_url,
                    source="レタスクラブ",
                    cooking_time=cal,  # カロリー情報を仮でここに
                ))
            except Exception:
                continue

        seen = set()
        unique = []
        for r in recipes:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        recipes = unique[:50]
    except Exception as e:
        print(f"[レタスクラブ] エラー: {e}")
    return recipes


# ============================================================
# 10. 味の素パーク
# ============================================================

async def search_ajinomoto(query: str) -> list[Recipe]:
    """味の素パークからレシピを検索"""
    recipes = []
    try:
        url = f"https://park.ajinomoto.co.jp/recipe/search/?search_word={quote_plus(query)}"
        html = await fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")

        for card in soup.select("[class*='recipe'], article, .card, a[href*='/recipe/card/']"):
            try:
                a_el = card if card.name == "a" else card.select_one("a[href*='/recipe/']")
                if not a_el:
                    continue
                link = a_el.get("href", "")
                if not link.startswith("http"):
                    link = "https://park.ajinomoto.co.jp" + link
                if "/recipe/" not in link:
                    continue

                title_el = card.select_one("h2, h3, [class*='title'], [class*='name']")
                title = title_el.get_text(strip=True) if title_el else a_el.get_text(strip=True)
                if len(title) < 3:
                    continue

                img_el = card.select_one("img")
                img_url = img_el.get("src") or img_el.get("data-src") if img_el else None

                time_el = card.select_one("[class*='time']")
                cooking_time = time_el.get_text(strip=True) if time_el else None

                recipes.append(Recipe(
                    title=title[:100],
                    url=link,
                    image_url=img_url,
                    source="味の素パーク",
                    cooking_time=cooking_time,
                ))
            except Exception:
                continue

        seen = set()
        unique = []
        for r in recipes:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        recipes = unique[:50]
    except Exception as e:
        print(f"[味の素パーク] エラー: {e}")
    return recipes


# ============================================================
# スクレイパー登録マップ
# ============================================================

SCRAPERS = {
    "rakuten":     {"name": "楽天レシピ",            "fn": search_rakuten,        "paginated": True},
    "sirogohan":   {"name": "白ごはん.com",          "fn": search_sirogohan,      "paginated": False},
    "dancyu":      {"name": "dancyu",                "fn": search_dancyu,         "paginated": False},
    "cookpad":     {"name": "クックパッド",           "fn": search_cookpad,        "paginated": True},
    "nadia":       {"name": "Nadia",                 "fn": search_nadia,          "paginated": False},
    "kurashiru":   {"name": "クラシル",               "fn": search_kurashiru,      "paginated": False},
    "delish":      {"name": "DELISH KITCHEN",        "fn": search_delish_kitchen, "paginated": False},
    "kyounoryouri":{"name": "みんなのきょうの料理",    "fn": search_kyounoryouri,   "paginated": False},
    "lettuceclub": {"name": "レタスクラブ",           "fn": search_lettuceclub,    "paginated": False},
    "ajinomoto":   {"name": "味の素パーク",           "fn": search_ajinomoto,      "paginated": False},
}

VALID_SOURCES = list(SCRAPERS.keys())


# ============================================================
# レシピ詳細の取得（汎用 JSON-LD + HTML フォールバック）
# ============================================================

async def get_recipe_detail_from_url(url: str) -> RecipeDetail:
    """URLからレシピの詳細情報を取得"""
    html = await fetch_page(url)
    soup = BeautifulSoup(html, "html.parser")

    # ソース判定
    source = "不明"
    domain_map = {
        "rakuten": "楽天レシピ", "sirogohan": "白ごはん.com", "dancyu": "dancyu",
        "cookpad": "クックパッド", "nadia": "Nadia", "kurashiru": "クラシル",
        "delishkitchen": "DELISH KITCHEN", "kyounoryouri": "みんなのきょうの料理",
        "lettuceclub": "レタスクラブ", "ajinomoto": "味の素パーク",
    }
    for key, name in domain_map.items():
        if key in url:
            source = name
            break

    # JSON-LD からデータ抽出
    ld = extract_jsonld_recipe(soup)

    title = ld.get("name", "")
    if not title:
        title_el = soup.select_one("h1, [class*='title']")
        title = title_el.get_text(strip=True) if title_el else "タイトル不明"

    # 画像
    img_url = ld.get("image")
    if isinstance(img_url, list):
        img_url = img_url[0] if img_url else None
    elif isinstance(img_url, dict):
        img_url = img_url.get("url")
    if not img_url:
        og_img = soup.select_one('meta[property="og:image"]')
        img_url = og_img.get("content") if og_img else None

    description = ld.get("description")
    cooking_time = parse_iso_duration(ld.get("cookTime") or ld.get("totalTime") or "")
    servings = str(ld.get("recipeYield", "")) or None

    # 著者
    author_data = ld.get("author")
    author = None
    if isinstance(author_data, dict):
        author = author_data.get("name")
    elif isinstance(author_data, str):
        author = author_data

    # カロリー
    calories = None
    nutrition = ld.get("nutrition")
    if isinstance(nutrition, dict):
        calories = nutrition.get("calories")

    # 材料
    ingredients = []
    for ing in ld.get("recipeIngredient", []):
        ingredients.append({"name": str(ing), "amount": ""})

    # 手順
    steps = []
    for i, step in enumerate(ld.get("recipeInstructions", []), 1):
        if isinstance(step, str):
            steps.append({"step": i, "text": step})
        elif isinstance(step, dict):
            steps.append({
                "step": i,
                "text": step.get("text", ""),
                "image_url": step.get("image"),
            })

    # JSON-LDがなかった場合のHTMLフォールバック
    if not ingredients:
        for el in soup.select(
            "[itemprop='recipeIngredient'], [class*='ingredient'] li, "
            "[class*='material'] li, [class*='zairyo'] li"
        ):
            text = el.get_text(strip=True)
            if text:
                ingredients.append({"name": text, "amount": ""})

    if not steps:
        for i, el in enumerate(soup.select(
            "[itemprop='recipeInstructions'] li, [class*='step'] li, "
            "[class*='howto'] li, [class*='instruction'] li"
        ), 1):
            text = el.get_text(strip=True)
            if text:
                step_img = el.select_one("img")
                steps.append({
                    "step": i,
                    "text": text,
                    "image_url": step_img.get("src") if step_img else None,
                })

    # tips
    tips = None
    tips_el = soup.select_one("[class*='advice'], [class*='tips'], [class*='point'], [class*='memo']")
    if tips_el:
        tips = tips_el.get_text(strip=True)[:300]

    return RecipeDetail(
        title=title or "タイトル不明",
        url=url,
        image_url=img_url,
        source=source,
        description=description,
        cooking_time=cooking_time or None,
        servings=servings,
        author=author,
        ingredients=ingredients,
        steps=steps,
        tips=tips,
        calories=calories,
    )


# ============================================================
# APIエンドポイント
# ============================================================

@app.get("/")
async def root():
    """APIの概要"""
    return {
        "name": "レシピ検索API",
        "version": "2.1.0",
        "total_sources": len(SCRAPERS),
        "endpoints": {
            "POST /api/recipes/search": "アプリ連携用レシピ検索（season/category/freeText）",
            "GET /search": "レシピをキーワード検索（全サイトまたは指定サイト）",
            "GET /detail": "レシピの詳細を取得（材料・手順など）",
            "GET /sources": "対応レシピサイト一覧",
            "GET /docs": "Swagger UI（インタラクティブドキュメント）",
        },
    }


# ============================================================
# アプリ連携用エンドポイント
# ============================================================

@app.post("/api/recipes/search", response_model=AppSearchResponse)
async def app_search_recipes(req: AppSearchRequest):
    """
    アプリ連携用レシピ検索（AIレシピ生成APIの /generate と対になるエンドポイント）

    - season, category, freeText から検索キーワードを組み立てて横断検索
    - 異なるサイトからバランスよく3件を返す
    - エラー時は { "error": "メッセージ" } を返す
    """
    # バリデーション: 最低1つはパラメータが必要
    if not req.season and not req.category and not req.freeText:
        return JSONResponse(
            status_code=400,
            content={"error": "season, category, freeText のいずれか1つ以上を指定してください"},
        )

    try:
        # 検索キーワードを組み立て
        query = build_search_query(req)

        # 全サイト並行検索
        tasks = []
        for key, scraper in SCRAPERS.items():
            if scraper["paginated"]:
                tasks.append(scraper["fn"](query, 1))
            else:
                tasks.append(scraper["fn"](query))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_recipes: list[Recipe] = []
        for result in results:
            if isinstance(result, list):
                all_recipes.extend(result)

        # ノイズ除去 + 関連度スコア順に並べ替え（フィルタではなくソート）
        all_recipes = [r for r in all_recipes if not is_noise_title(r.title)]
        all_recipes.sort(key=lambda r: _relevance_score(r.title, query), reverse=True)

        if not all_recipes:
            return JSONResponse(
                status_code=404,
                content={"error": f"「{query}」に一致するレシピが見つかりませんでした。別のキーワードでお試しください。"},
            )

        # シンプルモード: 詳細ページを取得してシンプルさ順にソート（ラウンドロビンは適用しない）
        if req.simple_mode:
            all_recipes = await _sort_by_simplicity(all_recipes)
            sorted_recipes = all_recipes
        else:
            # 異なるサイトからバランスよく並べ替え
            sorted_recipes = _sort_diverse_recipes(all_recipes)

        # ページング: offset/limitでスライス
        total = len(sorted_recipes)
        offset = req.offset
        limit = req.limit
        page_recipes = sorted_recipes[offset:offset + limit]

        # アプリ側のレスポンス形式に変換
        app_recipes = []
        for r in page_recipes:
            description = r.description or f"{r.source}で見つけた「{r.title}」のレシピです。"
            # descriptionが長すぎる場合は切り詰め
            if len(description) > 100:
                description = description[:97] + "..."

            app_recipes.append(AppRecipeItem(
                name=r.title,
                description=description,
                url=r.url if r.url else None,
                source=r.source,
            ))

        return AppSearchResponse(
            recipes=app_recipes,
            total=total,
            offset=offset,
            limit=limit,
            simple_mode=req.simple_mode,
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"レシピ検索中にエラーが発生しました: {str(e)}"},
        )


def _sort_diverse_recipes(recipes: list[Recipe]) -> list[Recipe]:
    """異なるサイトからバランスよく交互に並べ替える（ページング用）"""
    from collections import defaultdict, deque

    # サイトごとにグループ化（出現順を維持）
    groups: dict[str, deque] = defaultdict(deque)
    source_order: list[str] = []
    for r in recipes:
        if r.source not in groups:
            source_order.append(r.source)
        groups[r.source].append(r)

    # ラウンドロビンで各サイトから1件ずつ取り出す
    sorted_list: list[Recipe] = []
    while any(groups[s] for s in source_order):
        for s in source_order:
            if groups[s]:
                sorted_list.append(groups[s].popleft())

    return sorted_list


@app.get("/search", response_model=SearchResult)
async def search_recipes(
    q: str = Query(..., description="検索キーワード（例: カレー、唐揚げ、パスタ）"),
    source: Optional[str] = Query(
        None,
        description=f"レシピサイトを指定。有効値: {', '.join(VALID_SOURCES)}。省略で全サイト横断検索",
    ),
    page: int = Query(1, ge=1, description="ページ番号（楽天レシピ・クックパッドのみ対応）"),
):
    """
    レシピをキーワードで検索します。

    - 全サイトを同時並行で検索し、結果をまとめて返します
    - `source` パラメータで特定サイトに絞れます
    """
    if source and source not in SCRAPERS:
        raise HTTPException(
            status_code=400,
            detail=f"無効なsource: '{source}'。有効値: {', '.join(VALID_SOURCES)}",
        )

    tasks = []
    if source:
        # 特定サイトのみ
        scraper = SCRAPERS[source]
        if scraper["paginated"]:
            tasks.append(scraper["fn"](q, page))
        else:
            tasks.append(scraper["fn"](q))
    else:
        # 全サイト並行検索
        for key, scraper in SCRAPERS.items():
            if scraper["paginated"]:
                tasks.append(scraper["fn"](q, page))
            else:
                tasks.append(scraper["fn"](q))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_recipes = []
    for result in results:
        if isinstance(result, list):
            all_recipes.extend(result)

    # ノイズ除去: UI要素やナビゲーションリンクを除外
    all_recipes = [r for r in all_recipes if not is_noise_title(r.title)]

    # キーワード関連性フィルタ: タイトルにキーワードが含まれるものを優先
    relevant = [r for r in all_recipes if is_relevant_recipe(r.title, q)]
    others = [r for r in all_recipes if not is_relevant_recipe(r.title, q)]
    all_recipes = relevant + others

    return SearchResult(
        query=q,
        total=len(all_recipes),
        source=source,
        recipes=all_recipes,
    )


@app.get("/detail", response_model=RecipeDetail)
async def get_recipe_detail(
    url: str = Query(..., description="レシピページのURL（検索結果から取得）"),
):
    """
    レシピの詳細情報（材料・手順・調理時間等）を取得します。

    - JSON-LD（構造化データ）を優先的に使用するため、多くのサイトで正確なデータが取れます
    - JSON-LDがない場合はHTMLからフォールバック抽出します
    """
    try:
        return await get_recipe_detail_from_url(url)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"レシピページの取得に失敗: {e}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"レシピの解析に失敗: {str(e)}")


@app.get("/sources")
async def list_sources():
    """対応しているレシピサイトの一覧を返します"""
    sources = []
    site_info = {
        "rakuten":     {"url": "https://recipe.rakuten.co.jp",  "desc": "ユーザー投稿型の大規模レシピサイト。人気順検索が無料", "features": ["ページネーション", "人気順無料"]},
        "sirogohan":   {"url": "https://www.sirogohan.com",     "desc": "和食専門の丁寧なレシピサイト", "features": ["和食特化"]},
        "dancyu":      {"url": "https://dancyu.jp",             "desc": "食のプロによるレシピ", "features": ["プロ監修"]},
        "cookpad":     {"url": "https://cookpad.com/jp",        "desc": "日本最大のレシピ投稿サイト。395万品以上", "features": ["ページネーション", "最大レシピ数"]},
        "nadia":       {"url": "https://oceans-nadia.com",      "desc": "料理家・フードコーディネーターのプロレシピ", "features": ["プロのみ投稿", "コラム充実"]},
        "kurashiru":   {"url": "https://www.kurashiru.com",     "desc": "動画付きレシピサービス。3万本以上のレシピ動画", "features": ["動画レシピ"]},
        "delish":      {"url": "https://delishkitchen.tv",      "desc": "動画付きレシピ。満足度No.1", "features": ["動画レシピ", "高満足度"]},
        "kyounoryouri":{"url": "https://www.kyounoryouri.jp",   "desc": "NHK『きょうの料理』のレシピサイト。50年以上の歴史", "features": ["NHK公式", "プロ監修", "定番〜上級"]},
        "lettuceclub": {"url": "https://www.lettuceclub.net",   "desc": "料理雑誌「レタスクラブ」のWebレシピ。3.5万件以上", "features": ["雑誌連携", "献立提案"]},
        "ajinomoto":   {"url": "https://park.ajinomoto.co.jp",  "desc": "味の素公式レシピサイト。管理栄養士監修", "features": ["栄養士監修", "カロリー表示"]},
    }
    for key, scraper in SCRAPERS.items():
        info = site_info.get(key, {})
        sources.append({
            "id": key,
            "name": scraper["name"],
            "url": info.get("url", ""),
            "description": info.get("desc", ""),
            "features": info.get("features", []),
            "paginated": scraper["paginated"],
        })
    return {"total": len(sources), "sources": sources}


# ============================================================
# 起動
# ============================================================

if __name__ == "__main__":
    import uvicorn
    print("レシピ検索API v2.1 起動中...")
    print(f"   対応サイト: {len(SCRAPERS)}サイト")
    print("   アプリ連携: POST /api/recipes/search")
    print("   ドキュメント: http://localhost:8002/docs")
    uvicorn.run(app, host="0.0.0.0", port=8002)
