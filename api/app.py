import uuid
import asyncio
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel

from core.logging.logger import logger
from core.settings import settings
from core.schemas.state import (
    Trend, TrendScore, KnowledgeGraphData, IdeaOutput,
    Script, Scene, Asset, Timeline, AgentState
)
from core.graph.workflow import graph

# Import agents directly for individual endpoints
from agents.trend_agent.trend_agent import trend_discovery_agent
from agents.scoring_agent.scoring_agent import scoring_agent
from agents.kg_agent.kg_agent import kg_agent
from agents.idea_agent.idea_agent import idea_agent
from agents.script_agent.script_agent import script_agent
from agents.scene_agent.scene_agent import scene_planner_agent
from agents.retrieval_agent.retrieval_agent import asset_retrieval_agent
from agents.ranking_agent.ranking_agent import ranked_assets_agent
from agents.timeline_agent.timeline_agent import timeline_builder_agent

from knowledge_graph.db import db_manager

# --- FastAPI Initialization ---

app = FastAPI(
    title="AI Reel Content Intelligence Engine",
    description="Production-grade pipeline to discover trends, write scripts, retrieve assets, and build timelines.",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up FastAPI application...")
    await db_manager.initialize_db()

# --- Request Models ---

class TopicRequest(BaseModel):
    topic: str

class ScoreRequest(BaseModel):
    trends: List[Trend]

class EnrichRequest(BaseModel):
    trend: Trend

class IdeasRequest(BaseModel):
    trend: Trend
    kg_data: KnowledgeGraphData

class ScriptRequest(BaseModel):
    trend: Trend
    selected_idea: str

class ScenesRequest(BaseModel):
    trend: Trend
    script: Script

class AssetsRequest(BaseModel):
    trend: Trend
    scenes: List[Scene]

class RankRequest(BaseModel):
    trend: Trend
    scenes: List[Scene]
    assets: List[Asset]

class TimelineRequest(BaseModel):
    trend: Trend
    script: Script
    scenes: List[Scene]
    ranked_assets: List[Asset]

class PipelineRunRequest(BaseModel):
    topic: str
    selected_idea: Optional[str] = None

# --- Individual Stage Endpoints ---

@app.post("/discover", response_model=List[Trend])
async def discover_trends_endpoint(payload: TopicRequest):
    try:
        trends = await trend_discovery_agent.discover_trends(payload.topic)
        return trends
    except Exception as e:
        logger.error(f"Error in /discover endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/score", response_model=List[TrendScore])
async def score_trends_endpoint(payload: ScoreRequest):
    try:
        scores = await scoring_agent.score_trends(payload.trends)
        return scores
    except Exception as e:
        logger.error(f"Error in /score endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/enrich", response_model=KnowledgeGraphData)
async def enrich_kg_endpoint(payload: EnrichRequest):
    try:
        kg_data = await kg_agent.enrich_trend(payload.trend)
        return kg_data
    except Exception as e:
        logger.error(f"Error in /enrich endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ideas", response_model=IdeaOutput)
async def generate_ideas_endpoint(payload: IdeasRequest):
    try:
        ideas_output = await idea_agent.generate_ideas(payload.trend, payload.kg_data)
        return ideas_output
    except Exception as e:
        logger.error(f"Error in /ideas endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/script", response_model=Script)
async def generate_script_endpoint(payload: ScriptRequest):
    try:
        script = await script_agent.generate_script(payload.trend, payload.selected_idea)
        return script
    except Exception as e:
        logger.error(f"Error in /script endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scenes", response_model=List[Scene])
async def plan_scenes_endpoint(payload: ScenesRequest):
    try:
        scenes = await scene_planner_agent.plan_scenes(payload.trend, payload.script)
        return scenes
    except Exception as e:
        logger.error(f"Error in /scenes endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/assets", response_model=List[Asset])
async def retrieve_assets_endpoint(payload: AssetsRequest):
    try:
        assets = await asset_retrieval_agent.retrieve_assets(payload.trend, payload.scenes)
        return assets
    except Exception as e:
        logger.error(f"Error in /assets endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/rank", response_model=List[Asset])
async def rank_assets_endpoint(payload: RankRequest):
    try:
        ranked = await ranked_assets_agent.rank_assets(payload.trend, payload.scenes, payload.assets)
        return ranked
    except Exception as e:
        logger.error(f"Error in /rank endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/timeline", response_model=Timeline)
async def timeline_builder_endpoint(payload: TimelineRequest):
    try:
        timeline = await timeline_builder_agent.build_timeline(
            payload.trend, payload.script, payload.scenes, payload.ranked_assets
        )
        return timeline
    except Exception as e:
        logger.error(f"Error in /timeline endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Full Pipeline Orchestration Endpoints ---

async def run_pipeline_task(topic: str, selected_idea: Optional[str] = None):
    """Orchestrates the running of the LangGraph workflow in the background."""
    logger.info(f"Background Pipeline Task Started for topic: '{topic}'")
    initial_state = AgentState(topic=topic, selected_idea=selected_idea)
    try:
        # Run state machine
        final_state = await graph.ainvoke(initial_state)
        if final_state.get("error"):
            logger.error(f"Background Pipeline run halted with error: {final_state['error']}")
        else:
            logger.info("Background Pipeline task completed successfully!")
    except Exception as e:
        logger.critical(f"Critical failure in background pipeline execution: {e}")

@app.post("/pipeline/run")
async def trigger_pipeline_run(payload: PipelineRunRequest, background_tasks: BackgroundTasks):
    """
    Triggers the asynchronous LangGraph pipeline run.
    Uses BackgroundTasks to start processing instantly.
    """
    try:
        # Enqueue pipeline run in background
        background_tasks.add_task(run_pipeline_task, payload.topic, payload.selected_idea)
        return {"status": "processing", "message": f"Pipeline run successfully triggered for topic: '{payload.topic}'"}
    except Exception as e:
        logger.error(f"Failed to trigger pipeline run: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/pipeline/{trend_id}")
async def get_pipeline_run_status(trend_id: str):
    """
    Retrieves the execution status and intermediate/final results 
    of a pipeline run by its Trend ID from database persistence.
    """
    try:
        state = await db_manager.load_pipeline_state(trend_id)
        if not state:
            raise HTTPException(status_code=404, detail=f"No pipeline run found for trend ID '{trend_id}'")
        return state
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading pipeline run '{trend_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))
