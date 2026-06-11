import json
import uuid
import asyncio
from datetime import datetime
from typing import List, Dict, Any

from core.schemas.state import Trend
from core.logging.logger import logger
from core.settings import settings
from services.github.github_service import github_service
from services.reddit.reddit_service import reddit_service
from services.youtube.youtube_service import youtube_service
from services.newsletters.newsletter_service import newsletter_service
from knowledge_graph.db import db_manager

class TrendDiscoveryAgent:
    def __init__(self):
        self.output_dir = settings.BASE_DIR / "outputs" / "trends"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def discover_trends(self, topic: str) -> List[Trend]:
        """
        Discovers emerging trends from GitHub, Reddit, YouTube, and Newsletters
        concurrently, normalizes the data, saves it locally, and updates the database.
        """
        logger.info(f"Agent 1: Starting Trend Discovery for topic: '{topic}'...")

        # Execute all scraping concurrently
        github_task = github_service.fetch_trending_repos(topic)
        reddit_task = reddit_service.fetch_trending_posts(topic)
        youtube_task = youtube_service.fetch_trending_videos(topic)
        newsletter_task = newsletter_service.fetch_newsletter_trends(topic)

        github_repos, reddit_posts, youtube_vids, newsletter_items = await asyncio.gather(
            github_task, reddit_task, youtube_task, newsletter_task
        )

        trends: List[Trend] = []

        # 1. Normalize GitHub trends
        for repo in github_repos:
            trend_id = f"github_{repo['owner']}_{repo['repo_name']}"
            trends.append(Trend(
                trend_id=trend_id,
                source="github",
                title=f"{repo['owner']}/{repo['repo_name']}",
                description=repo["description"],
                url=repo["url"],
                metrics={
                    "stars": repo["stars"],
                    "forks": repo["forks"],
                    "readme_summary": repo["readme_summary"]
                }
            ))

        # 2. Normalize Reddit trends
        for post in reddit_posts:
            # Hash title for id
            import hashlib
            title_hash = hashlib.md5(post["title"].encode('utf-8')).hexdigest()[:8]
            trend_id = f"reddit_{post['subreddit']}_{title_hash}"
            trends.append(Trend(
                trend_id=trend_id,
                source="reddit",
                title=post["title"],
                description=f"Trending discussion in r/{post['subreddit']}.",
                url=post["url"],
                metrics={
                    "upvotes": post["upvotes"],
                    "comments": post["comments"],
                    "post_age_hours": post["post_age_hours"]
                }
            ))

        # 3. Normalize YouTube trends
        for vid in youtube_vids:
            import hashlib
            title_hash = hashlib.md5(vid["title"].encode('utf-8')).hexdigest()[:8]
            trend_id = f"youtube_{vid['channel']}_{title_hash}"
            trends.append(Trend(
                trend_id=trend_id,
                source="youtube",
                title=vid["title"],
                description=f"Video by {vid['channel']}.",
                url=vid["url"],
                metrics={
                    "views": vid["views"],
                    "age_hours": vid["age_hours"],
                    "velocity": vid["velocity_views_per_hour"]
                }
            ))

        # 4. Normalize Newsletter trends
        for item in newsletter_items:
            import hashlib
            title_hash = hashlib.md5(item["title"].encode('utf-8')).hexdigest()[:8]
            trend_id = f"newsletter_{item['source'].lower().replace(' ', '_')}_{title_hash}"
            trends.append(Trend(
                trend_id=trend_id,
                source="newsletter",
                title=item["title"],
                description=item["summary"],
                url=item["link"],
                metrics={
                    "newsletter_source": item["source"]
                }
            ))

        logger.info(f"Discovered {len(trends)} total raw trends for topic '{topic}'.")

        # Save to DB
        trends_dicts = [t.model_dump() for t in trends]
        await db_manager.save_trends(trends_dicts)

        # Save to file system
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"discovered_trends_{timestamp}.json"
        with open(filepath, "w") as f:
            json.dump(trends_dicts, f, indent=2)
            
        logger.info(f"Saved discovered trends to database and file: {filepath}")
        return trends

trend_discovery_agent = TrendDiscoveryAgent()
