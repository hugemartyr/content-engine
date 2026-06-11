import pytest
import httpx
from services.reddit.reddit_service import reddit_service
from services.youtube.youtube_service import youtube_service
from services.newsletters.newsletter_service import newsletter_service

def has_internet():
    try:
        httpx.get("https://www.google.com", timeout=2.0)
        return True
    except Exception:
        return False

@pytest.mark.asyncio
@pytest.mark.skipif(not has_internet(), reason="Requires active internet connection")
async def test_real_time_reddit_scraping():
    """Verifies that the Playwright fallback works for Reddit and gets actual posts."""
    # We force standard API to fail or verify Playwright scraper directly
    posts = await reddit_service._scrape_reddit_playwright("AI Agents")
    assert isinstance(posts, list)
    # We should have found some real search result posts on Reddit
    assert len(posts) > 0
    # Verify the structure matches AgentState expectations
    for p in posts[:3]:
        assert "title" in p
        assert "url" in p
        assert "subreddit" in p
        assert p["upvotes"] > 0
        assert p["url"].startswith("http")

@pytest.mark.asyncio
@pytest.mark.skipif(not has_internet(), reason="Requires active internet connection")
async def test_real_time_youtube_scraping():
    """Verifies that the Playwright search fallback works for YouTube and gets actual videos."""
    videos = await youtube_service._scrape_youtube_playwright("AI Agents")
    assert isinstance(videos, list)
    assert len(videos) > 0
    for v in videos[:3]:
        assert "title" in v
        assert "url" in v
        assert "channel" in v
        assert v["views"] > 0
        assert v["url"].startswith("http")

@pytest.mark.asyncio
@pytest.mark.skipif(not has_internet(), reason="Requires active internet connection")
async def test_real_time_newsletter_scraping():
    """Verifies that the Playwright search fallback works for newsletters and gets actual articles."""
    articles = await newsletter_service._scrape_newsletters_playwright("Agent")
    assert isinstance(articles, list)
    assert len(articles) > 0
    for a in articles[:3]:
        assert "title" in a
        assert "summary" in a
        assert "link" in a
        assert "source" in a
        assert a["link"].startswith("http")
