"""Financial News MCP Server."""

import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from .scrapers import (
    get_latest_news,
    search_news,
    RSS_FEEDS,
    SOURCE_NAMES,
    NewsArticle,
)

app = Server("financial-news-mcp")

ALL_SOURCES = list(RSS_FEEDS.keys())

CATEGORY_SOURCES = {
    "markets": ["reuters_markets", "marketwatch_markets", "cnbc_markets", "investing_com", "bloomberg_markets"],
    "finance": ["reuters_finance", "cnbc_finance", "yahoo_finance"],
    "investing": ["seeking_alpha", "yahoo_finance", "investing_com"],
    "top": ["reuters_markets", "marketwatch_top", "cnbc_finance", "cnbc_business"],
    "all": ALL_SOURCES,
}


def _format_articles(articles: list[NewsArticle], max_articles: int = 20) -> str:
    if not articles:
        return "No articles found."
    lines = []
    for i, a in enumerate(articles[:max_articles], 1):
        lines.append(f"{i}. **{a.title}**")
        lines.append(f"   Source: {a.source}" + (f" | Category: {a.category}" if a.category else ""))
        if a.published:
            lines.append(f"   Published: {a.published}")
        if a.summary:
            lines.append(f"   {a.summary}")
        lines.append(f"   URL: {a.url}")
        lines.append("")
    return "\n".join(lines)


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_latest_news",
            description=(
                "Fetch the latest financial news headlines from major sources including "
                "Reuters, MarketWatch, CNBC, Yahoo Finance, Financial Times, Seeking Alpha, "
                "and Investing.com."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "News category: 'markets', 'finance', 'investing', 'business', 'top', 'all'. Defaults to 'top'.",
                        "enum": ["markets", "finance", "investing", "top", "all"],
                        "default": "top",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max articles per source (1-20). Defaults to 5.",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 5,
                    },
                },
            },
        ),
        types.Tool(
            name="search_financial_news",
            description=(
                "Search for financial news articles matching a keyword or phrase across "
                "multiple news sources."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword or phrase (e.g. 'Apple', 'Fed interest rates').",
                    },
                    "category": {
                        "type": "string",
                        "description": "Limit to source category. Options: 'markets', 'finance', 'investing', 'top', 'all'.",
                        "enum": ["markets", "finance", "investing", "top", "all"],
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (1-50). Defaults to 10.",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="list_news_sources",
            description="List all available financial news sources and their categories.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="get_news_by_source",
            description="Fetch the latest news from a specific financial news source.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Source key. Use list_news_sources to see options.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max articles (1-20). Defaults to 10.",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 10,
                    },
                },
                "required": ["source"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_latest_news":
        category = arguments.get("category", "top")
        limit = arguments.get("limit", 5)
        sources = CATEGORY_SOURCES.get(category, CATEGORY_SOURCES["top"])
        articles = await get_latest_news(sources, limit_per_source=limit)
        text = f"## Latest Financial News — {category.title()}\n\n"
        text += _format_articles(articles, max_articles=limit * len(sources))
        return [types.TextContent(type="text", text=text)]

    elif name == "search_financial_news":
        query = arguments.get("query", "")
        category = arguments.get("category", "all")
        limit = arguments.get("limit", 10)
        if not query:
            return [types.TextContent(type="text", text="Please provide a search query.")]
        sources = CATEGORY_SOURCES.get(category, ALL_SOURCES)
        articles = await search_news(query, sources, limit=limit)
        text = f"## Financial News Search: '{query}'\n\n"
        if not articles:
            text += f"No articles found matching '{query}'."
        else:
            text += f"Found {len(articles)} article(s):\n\n"
            text += _format_articles(articles, max_articles=limit)
        return [types.TextContent(type="text", text=text)]

    elif name == "list_news_sources":
        lines = ["## Available Financial News Sources\n"]
        for key, name_str in SOURCE_NAMES.items():
            from .scrapers import SOURCE_CATEGORIES
            cat = SOURCE_CATEGORIES.get(key, "General")
            lines.append(f"- **{key}** — {name_str} ({cat})")
        lines.append("\n### Category Groups")
        for cat, srcs in CATEGORY_SOURCES.items():
            lines.append(f"- **{cat}**: {', '.join(srcs)}")
        return [types.TextContent(type="text", text="\n".join(lines))]

    elif name == "get_news_by_source":
        source = arguments.get("source", "")
        limit = arguments.get("limit", 10)
        if source not in RSS_FEEDS:
            available = ", ".join(RSS_FEEDS.keys())
            return [types.TextContent(type="text", text=f"Unknown source '{source}'. Available: {available}")]
        from .scrapers import fetch_rss_feed
        articles = await fetch_rss_feed(source, limit=limit)
        source_name = SOURCE_NAMES.get(source, source)
        text = f"## Latest News from {source_name}\n\n"
        text += _format_articles(articles, max_articles=limit)
        return [types.TextContent(type="text", text=text)]

    else:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )

def main():
    asyncio.run(run())

if __name__ == "__main__":
    main()
