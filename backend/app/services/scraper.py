"""热点抓取器 — 微博热搜 / 抖音热点 / B站热门."""
import re
import httpx
from bs4 import BeautifulSoup
from typing import Dict, List, Optional

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def _safe_get(url: str, timeout: float = 15.0) -> Optional[str]:
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None


# ---- 微博热搜 (公开 API) ----
def get_weibo_hot(limit: int = 20) -> List[Dict]:
    """微博热搜榜，使用公开 JSON API."""
    try:
        resp = httpx.get(
            "https://weibo.com/ajax/side/hotSearch", headers=_HEADERS, timeout=15.0
        )
        resp.raise_for_status()
        data = resp.json()
        items = []
        for rank, item in enumerate(data.get("data", {}).get("realtime", [])[:limit], 1):
            word = item.get("word", "")
            items.append({
                "title": word,
                "url": f"https://s.weibo.com/weibo?q={word}",
                "hot_score": item.get("num", 0),
                "rank": rank,
                "platform": "weibo",
            })
        return items
    except Exception:
        return []


# ---- 抖音热点 (公开 API) ----
def get_douyin_hot(limit: int = 20) -> List[Dict]:
    """抖音热点榜."""
    try:
        resp = httpx.get(
            "https://www.douyin.com/aweme/v1/web/hot/search/list/",
            headers={**_HEADERS, "Referer": "https://www.douyin.com/"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        items = []
        for rank, word_data in enumerate(
            data.get("data", {}).get("word_list", [])[:limit], 1
        ):
            word = word_data.get("word", "")
            items.append({
                "title": word,
                "url": f"https://www.douyin.com/search/{word}",
                "hot_score": word_data.get("hot_value", 0),
                "rank": rank,
                "platform": "douyin",
            })
        return items
    except Exception:
        return []


# ---- B站热门 (RSS/页面解析) ----
def get_bilibili_hot(limit: int = 20) -> List[Dict]:
    """B站热门排行."""
    try:
        resp = httpx.get(
            "https://api.bilibili.com/x/web-interface/popular?ps=50",
            headers=_HEADERS,
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        items = []
        for rank, video in enumerate(
            data.get("data", {}).get("list", [])[:limit], 1
        ):
            items.append({
                "title": video.get("title", ""),
                "url": f"https://www.bilibili.com/video/{video.get('bvid', '')}",
                "hot_score": video.get("stat", {}).get("view", 0),
                "rank": rank,
                "platform": "bilibili",
            })
        return items
    except Exception:
        return []


def get_all_trending(limit_per_platform: int = 10) -> List[Dict]:
    """聚合多个平台的热搜."""
    results = []
    results.extend(get_weibo_hot(limit_per_platform))
    results.extend(get_douyin_hot(limit_per_platform))
    results.extend(get_bilibili_hot(limit_per_platform))
    return results


def get_trending_topics(platform: str = "all", limit: int = 10) -> List[Dict]:
    """统一入口."""
    platforms = {
        "weibo": get_weibo_hot,
        "douyin": get_douyin_hot,
        "bilibili": get_bilibili_hot,
    }
    if platform in platforms:
        return platforms[platform](limit)
    return get_all_trending(limit)
