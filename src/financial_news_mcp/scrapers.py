"""Financial news scrapers for various sources."""

import asyncio
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass
from lxml import etree
from typing import Optional


@dataclass
class NewsArticle:
    title: str
    url: str
    source: str
    summary: str
    published: Optional[str]
    category: Optional[str] = None


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

RSS_FEEDS = {
    "reuters_markets": "https://feeds.reuters.com/reuters/businessNews",
    "reuters_finance": "https://feeds.reuters.com/news/wealth",
    "yahoo_finance": "https://finance.yahoo.com/rss/",
    "marketwatch_top": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "marketwatch_markets": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
    "cnbc_finance": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "cnbc_business": "https://www.cnbc.com/id/10001147/device/rss/rss.html",
    "cnbc_markets": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "ft_markets": "https://www.ft.com/rss/home/uk",
    "ft_international": "https://www.ft.com/rss/home/international",
    "seeking_alpha": "https://seekingalpha.com/feed.xml",
    "investing_com": "https://www.investing.com/rss/news.rss",
    "bloomberg_markets": "https://feeds.bloomberg.com/markets/news.rss",
    "wsj_business": "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness",
    "wsj_markets": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
    "wsj_economy": "https://feeds.content.dowjones.io/public/rss/socialeconomyfeed",
    "fox_business_economy": "https://moxie.foxbusiness.com/google-publisher/economy.xml",
    "fox_business_markets": "https://moxie.foxbusiness.com/google-publisher/markets.xml",
    "fox_business_latest": "https://moxie.foxbusiness.com/google-publisher/latest.xml",
}

SOURCE_CATEGORIES = {
    "reuters_markets": "Business",
    "reuters_finance": "Finance",
    "yahoo_finance": "Markets",
    "marketwatch_top": "Top Stories",
    "marketwatch_markets": "Markets",
    "cnbc_finance": "Finance",
    "cnbc_business": "Finance",
    "cnbc_markets": "Markets",
    "ft_markets": "Markets",
    "ft_international": "International",
    "seeking_alpha": "Investing",
    "investing_com": "Markets",
    "bloomberg_markets": "Markets",
    "wsj_business": "Business",
    "wsj_markets": "Markets",
    "wsj_economy": "Economy",
    "fox_business_economy": "Economy",
    "fox_business_markets": "Markets",
    "fox_business_latest": "Top Stories",
}

SOURCE_NAMES = {
    "reuters_markets": "Reuters",
    "reuters_finance": "Reuters",
    "yahoo_finance": "Yahoo Finance",
    "marketwatch_top": "MarketWatch",
    "marketwatch_markets": "MarketWatch",
    "cnbc_finance": "CNBC",
    "cnbc_markets": "CNBC",
    "ft_markets": "Financial Times",
    "ft_international": "Financial Times",
    "seeking_alpha": "Seeking Alpha",
    "investing_com": "Investing.com",
    "bloomberg_markets": "Bloomberg",
    "wsj_business": "Wall Street Journal",
    "wsj_markets": "Wall Street Journal",
    "wsj_economy": "Wall Street Journal",
    "fox_business_economy": "Fox Business",
    "fox_business_markets": "Fox Business",
    "fox_business_latest": "Fox Business",
}

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def _text(el: etree._Element, tag: str, ns: Optional[str] = None) -> str:
    found = el.find(tag)
    if found is not None and found.text:
        return found.text.strip()
    if ns:
        found = el.find(f"{{{NS[ns]}}}{tag}")
        if found is not None and found.text:
            return found.text.strip()
    return ""


def _strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator=" ", strip=True)[:500]


def _parse_rss_xml(xml_bytes: bytes, source_key: str, limit: int) -> list[NewsArticle]:
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        text = xml_bytes.decode("utf-8", errors="replace")
        text = "\n".join(line for line in text.splitlines() if "<?xml" not in line)
        try:
            root = etree.fromstring(text.encode("utf-8"))
        except etree.XMLSyntaxError:
            return []

    articles = []
    source_name = SOURCE_NAMES.get(source_key, source_key)
    category = SOURCE_CATEGORIES.get(source_key)

    items = root.findall(".//item")
    if not items:
        items = root.findall(f".//{{{NS['atom']}}}entry")

    for item in items[:limit]:
        title = (
            _text(item, "title")
            or _text(item, "title", "atom")
            or "No title"
        )
        title = _strip_html(title) or title

        link = _text(item, "link")
        if not link:
            link_el = item.find(f"{{{NS['atom']}}}link")
            if link_el is not None:
                link = link_el.get("href", "")

        summary = (
            _text(item, "description")
            or _text(item, "summary", "atom")
            or _text(item, "content", "content")
            or ""
        )
        summary = _strip_html(summary)

        published = (
            _text(item, "pubDate")
            or _text(item, "published", "atom")
            or _text(item, "updated", "atom")
            or _text(item, "date", "dc")
        )

        articles.append(NewsArticle(
            title=title,
            url=link,
            source=source_name,
            summary=summary,
            published=published or None,
            category=category,
        ))

    return articles


async def fetch_rss_feed(feed_key: str, limit: int = 10) -> list[NewsArticle]:
    url = RSS_FEEDS[feed_key]
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return _parse_rss_xml(response.content, feed_key, limit)
    except Exception:
        return []


async def get_latest_news(sources: list[str], limit_per_source: int = 5) -> list[NewsArticle]:
    tasks = [fetch_rss_feed(src, limit_per_source) for src in sources if src in RSS_FEEDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    articles = []
    for result in results:
        if isinstance(result, list):
            articles.extend(result)
    return articles


async def search_news(query: str, sources: list[str], limit: int = 20) -> list[NewsArticle]:
    all_articles = await get_latest_news(sources, limit_per_source=25)
    query_lower = query.lower()
    matched = [
        a for a in all_articles
        if query_lower in a.title.lower() or query_lower in a.summary.lower()
    ]
    return matched[:limit]