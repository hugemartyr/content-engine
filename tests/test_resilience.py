import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from core.settings import settings
from core.schemas.state import Trend, Script, Scene, Asset, AgentState
from core.graph.workflow import graph
from knowledge_graph.db import db_manager

@pytest.fixture(scope="module", autouse=True)
def setup_test_env():
    # Force sqlite and in-memory vector/queue store for tests
    settings.DB_PROVIDER = "sqlite"
    settings.SQLITE_PATH = "./data/test_resilience_engine.db"
    settings.VECTOR_PROVIDER = "memory"
    settings.QUEUE_PROVIDER = "memory"
    
    yield
    
    # Cleanup test DB after test completion
    test_db = Path(settings.SQLITE_PATH)
    if test_db.exists():
        try:
            os.remove(test_db)
        except Exception:
            pass

@pytest.mark.asyncio
async def test_workflow_llm_failure_resilience():
    """
    Simulates a complete outage of LLMs (e.g. connection error/API offline) 
    and checks that all agents recover gracefully and use baseline fallbacks.
    """
    # 1. Setup mock LLM that always throws an error
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("Mock LLM offline / Connection error"))
    
    # 2. Force settings to trigger LLM invocation and simulate development env
    settings.USE_LOCAL_LLM = True
    settings.ENV = "development"  # This ensures that non-testing code paths are hit
    
    # Initialize DB
    await db_manager.initialize_db()
    
    initial_state = AgentState(topic="AI Agents")
    
    # Patch get_llm in all agents and core.utils.llm to guarantee it's mocked
    patches = [
        patch("core.utils.llm.get_llm", return_value=mock_llm),
        patch("agents.scoring_agent.scoring_agent.get_llm", return_value=mock_llm),
        patch("agents.kg_agent.kg_agent.get_llm", return_value=mock_llm),
        patch("agents.idea_agent.idea_agent.get_llm", return_value=mock_llm),
        patch("agents.script_agent.script_agent.get_llm", return_value=mock_llm),
        patch("agents.scene_agent.scene_agent.get_llm", return_value=mock_llm),
        patch("agents.ranking_agent.ranking_agent.get_llm", return_value=mock_llm),
        patch("agents.timeline_agent.timeline_agent.get_llm", return_value=mock_llm),
    ]
    
    # Start all patches
    for p in patches:
        p.start()
        
    try:
        # 3. Execute workflow. It should run till completion using fallbacks!
        final_state = await graph.ainvoke(initial_state)
    finally:
        # Stop all patches
        for p in patches:
            p.stop()
    
    # 4. Verify no error trace halted the pipeline
    assert final_state.get("error") is None
    
    # 5. Verify individual agent fallbacks worked:
    # Trend scoring qualitative dimensions fallback check
    assert final_state["top_trend"] is not None
    assert final_state["scores"] is not None
    top_score = final_state["scores"][0]
    assert top_score.breakdown.novelty in [6.0, 7.0, 8.0]  # baseline heuristic values
    
    # KG extraction fallback check
    assert final_state["kg_enrichment"] is not None
    assert len(final_state["kg_enrichment"].related_entities) > 0
    assert final_state["kg_enrichment"].related_topics == ["Artificial Intelligence", "Tech Trends"]
    
    # Idea generation fallback check
    assert final_state["ideas"] is not None
    assert len(final_state["ideas"].ideas) >= 10
    
    # Script generation fallback check
    assert final_state["script"] is not None
    assert "exploded overnight" in final_state["script"].hook
    
    # Scene planning fallback check
    assert len(final_state["scenes"]) > 0
    assert final_state["scenes"][0].duration == 3.0
    
    # Asset retrieval fallback check (verifies it worked and retrieved assets)
    assert len(final_state["assets"]) > 0
    
    # Asset ranking fallback check
    assert len(final_state["ranked_assets"]) == len(final_state["scenes"])
    
    # Timeline builder fallback check
    assert final_state["timeline"] is not None
    assert len(final_state["timeline"].timeline) == len(final_state["scenes"])
    assert final_state["timeline"].timeline[0].caption == final_state["script"].hook


@pytest.mark.asyncio
@patch("services.screenshots.screenshot_service.screenshot_service.capture_screenshot")
@patch("services.stock.stock_service.stock_service.search_and_download_stock")
async def test_workflow_asset_failure_resilience(mock_search_stock, mock_capture_screenshot):
    """
    Simulates failure of all asset retrieval APIs (Playwright, Stock APIs, fallbacks)
    and checks that retrieval agent falls back to generating local mock placeholders 
    instead of crashing the pipeline.
    """
    # 1. Setup mock LLM that always throws an error
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("Mock LLM offline / Connection error"))
    
    # 2. Setup asset retrieval failures
    mock_capture_screenshot.side_effect = Exception("Screenshot service failure")
    mock_search_stock.side_effect = Exception("Stock service failure")
    
    # 3. Force settings to trigger LLM invocation and simulate development env
    settings.USE_LOCAL_LLM = True
    settings.ENV = "development"
    
    # Initialize DB
    await db_manager.initialize_db()
    
    initial_state = AgentState(topic="AI Agents")
    
    # Patch get_llm in all agents and core.utils.llm to guarantee it's mocked
    patches = [
        patch("core.utils.llm.get_llm", return_value=mock_llm),
        patch("agents.scoring_agent.scoring_agent.get_llm", return_value=mock_llm),
        patch("agents.kg_agent.kg_agent.get_llm", return_value=mock_llm),
        patch("agents.idea_agent.idea_agent.get_llm", return_value=mock_llm),
        patch("agents.script_agent.script_agent.get_llm", return_value=mock_llm),
        patch("agents.scene_agent.scene_agent.get_llm", return_value=mock_llm),
        patch("agents.ranking_agent.ranking_agent.get_llm", return_value=mock_llm),
        patch("agents.timeline_agent.timeline_agent.get_llm", return_value=mock_llm),
    ]
    
    # Start all patches
    for p in patches:
        p.start()
        
    try:
        # Execute workflow
        final_state = await graph.ainvoke(initial_state)
    finally:
        # Stop all patches
        for p in patches:
            p.stop()
    
    # Verify no error trace halted the pipeline
    assert final_state.get("error") is None
    
    # Verify fallback local_mock assets were created and used
    assert len(final_state["assets"]) > 0
    assert all(a.source == "local_mock" for a in final_state["assets"])
    
    # Verify timeline is built using these mock assets
    assert final_state["timeline"] is not None
    for item in final_state["timeline"].timeline:
        assert "critical_fallback" in item.asset

