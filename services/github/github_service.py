import httpx
from typing import List, Dict, Any
from core.settings import settings
from core.logging.logger import logger

class GitHubService:
    def __init__(self):
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "content-intelligence-engine"
        }
        if settings.GITHUB_TOKEN:
            self.headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"

    async def fetch_trending_repos(self, topic: str) -> List[Dict[str, Any]]:
        """
        Searches GitHub for repositories related to the topic,
        sorting by stars to find trending items.
        """
        url = "https://api.github.com/search/repositories"
        params = {
            "q": f"{topic} OR AI",
            "sort": "stars",
            "order": "desc",
            "per_page": 10
        }
        
        logger.info(f"Querying GitHub Search API for topic: '{topic}'...")
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=10.0) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    repos = []
                    for item in items:
                        repos.append({
                            "repo_name": item.get("name"),
                            "owner": item.get("owner", {}).get("login"),
                            "stars": item.get("stargazers_count", 0),
                            "forks": item.get("forks_count", 0),
                            "description": item.get("description", ""),
                            "url": item.get("html_url", ""),
                            "readme_summary": await self.fetch_readme_summary(item.get("owner", {}).get("login"), item.get("name"))
                        })
                    return repos
                else:
                    logger.warning(f"GitHub Search API returned status {response.status_code}. Response: {response.text}")
        except Exception as e:
            logger.error(f"GitHub Search API request failed: {e}")

        logger.warning("Falling back to mock GitHub trending data.")
        return self._generate_mock_repos(topic)

    async def fetch_readme_summary(self, owner: str, repo: str) -> str:
        """Fetches the raw README.md content from GitHub and creates a short summary."""
        # Try master and main branch
        for branch in ["main", "master"]:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        content = response.text
                        # Simple truncation as summary
                        return content[:500] + "..." if len(content) > 500 else content
            except Exception:
                continue
        return "README content unavailable."

    def _generate_mock_repos(self, topic: str) -> List[Dict[str, Any]]:
        """Generates realistic mock repos for testing/fallback."""
        normalized_topic = topic.lower().replace(" ", "-")
        return [
            {
                "repo_name": f"hyper-{normalized_topic}",
                "owner": "dev-crew-labs",
                "stars": 12450,
                "forks": 1280,
                "description": f"A blazing fast, ultra-scalable agentic framework for running {topic} on edge devices.",
                "url": f"https://github.com/dev-crew-labs/hyper-{normalized_topic}",
                "readme_summary": f"# Hyper-{topic}\n\nFeatures:\n- Zero latency orchestration\n- Local model routing\n- Multi-agent sync protocols."
            },
            {
                "repo_name": f"open-{normalized_topic}-mcp",
                "owner": "mcp-alliance",
                "stars": 8340,
                "forks": 920,
                "description": f"Model Context Protocol server implementation for connecting {topic} tools directly into LLM IDEs.",
                "url": f"https://github.com/mcp-alliance/open-{normalized_topic}-mcp",
                "readme_summary": f"# Open {topic} MCP\n\nAllows Claude, Gemini, or ChatGPT to call internal database tools instantly."
            },
            {
                "repo_name": f"{normalized_topic}-swarm",
                "owner": "swarm-intelligence",
                "stars": 6120,
                "forks": 510,
                "description": f"Hierarchical agent swarm coordination library supporting planning and reflection loops for {topic}.",
                "url": f"https://github.com/swarm-intelligence/{normalized_topic}-swarm",
                "readme_summary": f"# Swarm {topic}\n\nCoordinate hundreds of agents with centralized task dispatchers."
            }
        ]

github_service = GitHubService()
