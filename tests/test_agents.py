import pytest
import os
import shutil
from pathlib import Path

from core.settings import settings
from core.schemas.state import Trend, Script, Scene, Asset, AgentState
from knowledge_graph.db import db_manager, TrendModel
from knowledge_graph.vector import vector_db
from services.github.github_service import github_service
from services.reddit.reddit_service import reddit_service
from services.youtube.youtube_service import youtube_service
from services.newsletters.newsletter_service import newsletter_service
from core.graph.workflow import graph

# Configure testing environment
@pytest.fixture(scope="module", autouse=True)
def setup_test_env():
    # Force sqlite and in-memory vector store for tests
    settings.DB_PROVIDER = "sqlite"
    settings.SQLITE_PATH = "./data/test_engine.db"
    settings.VECTOR_PROVIDER = "memory"
    settings.QUEUE_PROVIDER = "memory"
    settings.USE_LOCAL_LLM = False  # Disable local Ollama connections during testing
    settings.GEMINI_API_KEY = None  # Isolate tests from remote APIs
    settings.OPENAI_API_KEY = None
    settings.ANTHROPIC_API_KEY = None
    settings.ENV = "testing"  # Trigger test-specific safe mock fallbacks
    
    yield
    
    # Cleanup test DB after test completion
    test_db = Path(settings.SQLITE_PATH)
    if test_db.exists():
        try:
            os.remove(test_db)
        except Exception:
            pass

@pytest.mark.asyncio
async def test_database_initialization_and_crud():
    # Initialize DB
    await db_manager.initialize_db()
    
    # Test saving trends
    mock_trend = {
        "trend_id": "test_trend_123",
        "source": "github",
        "title": "test/repo",
        "description": "a test repository description",
        "url": "https://github.com/test/repo",
        "metrics": {"stars": 100, "forks": 10}
    }
    
    await db_manager.save_trends([mock_trend])
    
    # Load and verify
    state = await db_manager.load_pipeline_state("test_trend_123")
    assert state != {}
    assert state["trend"]["title"] == "test/repo"
    assert state["trend"]["metrics"]["stars"] == 100

@pytest.mark.asyncio
async def test_vector_db_operations():
    await vector_db.initialize_collection()
    
    # Upsert entity
    await vector_db.upsert_entity(
        name="Gemini 3.5 Flash",
        entity_type="Product",
        description="A large language model by Google",
        trend_id="test_trend_123"
    )
    
    # Search
    results = await vector_db.search_entities("Google AI models", limit=2)
    assert len(results) > 0
    assert results[0]["name"] == "Gemini 3.5 Flash"
    assert results[0]["type"] == "Product"

@pytest.mark.asyncio
async def test_external_services():
    # Test GitHub Service
    github_repos = await github_service.fetch_trending_repos("agents")
    assert len(github_repos) > 0
    assert "repo_name" in github_repos[0]
    
    # Test Reddit Service
    reddit_posts = await reddit_service.fetch_trending_posts("agents")
    assert len(reddit_posts) > 0
    assert "title" in reddit_posts[0]
    
    # Test YouTube Service
    youtube_vids = await youtube_service.fetch_trending_videos("agents")
    assert len(youtube_vids) > 0
    
    # Test Newsletter Service
    newsletters = await newsletter_service.fetch_newsletter_trends("agents")
    assert len(newsletters) > 0

@pytest.mark.asyncio
async def test_agents_e2e_workflow():
    """Runs the full compiled LangGraph workflow using mock/heuristic fallbacks."""
    initial_state = AgentState(topic="AI agent frameworks")
    
    # Invoke workflow
    final_state = await graph.ainvoke(initial_state)
    
    # Assert execution completed without halting error
    assert final_state.get("error") is None
    
    # Verify stages
    assert len(final_state["trends"]) > 0
    assert final_state["top_trend"] is not None
    assert final_state["kg_enrichment"] is not None
    assert final_state["ideas"] is not None
    assert len(final_state["ideas"].ideas) >= 10
    assert final_state["script"] is not None
    assert len(final_state["scenes"]) > 0
    assert len(final_state["assets"]) > 0
    assert len(final_state["ranked_assets"]) == len(final_state["scenes"])
    assert final_state["timeline"] is not None
    
    # Verify timeline properties
    timeline = final_state["timeline"]
    assert timeline.bgm in ["ambient_tech_mellow.mp3", "lofi_study_beats.mp3", "tech_documentary.mp3"]
    assert len(timeline.timeline) == len(final_state["scenes"])
    
    # Verify timelines have timing bounds
    for item in timeline.timeline:
        assert item.start >= 0.0
        assert item.end > item.start
        assert item.asset != ""
        assert item.caption != ""
