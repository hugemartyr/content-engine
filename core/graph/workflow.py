from typing import Dict, Any, List
from langgraph.graph import StateGraph, END

from core.schemas.state import AgentState
from core.logging.logger import logger

# Import all agents
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

# --- LangGraph Node Functions ---

async def discover_trends_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- NODE: Discover Trends ---")
    try:
        # Check if trends already present (resumable step check)
        if state.trends:
            logger.info("Trends already present in state, skipping discovery.")
            return {}
        trends = await trend_discovery_agent.discover_trends(state.topic)
        return {"trends": trends}
    except Exception as e:
        logger.exception(f"Exception in discover_trends_node")
        return {"error": f"Trend discovery failed: {str(e)}"}

async def score_trends_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- NODE: Score Trends ---")
    try:
        if state.scores and state.top_trend:
            logger.info("Trend scores and top trend already present, skipping.")
            return {}
            
        if not state.trends:
            raise ValueError("No trends available to score.")
            
        scores = await scoring_agent.score_trends(state.trends)
        
        # Select top scored trend
        top_trend_id = scores[0].trend_id
        top_trend = next((t for t in state.trends if t.trend_id == top_trend_id), None)
        
        if not top_trend:
            raise ValueError(f"Top scored trend {top_trend_id} not found in raw trends list.")
            
        return {"scores": scores, "top_trend": top_trend}
    except Exception as e:
        logger.exception(f"Exception in score_trends_node")
        return {"error": f"Trend scoring failed: {str(e)}"}

async def enrich_kg_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- NODE: Enrich Knowledge Graph ---")
    try:
        if state.kg_enrichment:
            logger.info("KG enrichment already present, skipping.")
            return {}
            
        if not state.top_trend:
            raise ValueError("No top trend selected for KG enrichment.")
            
        kg_data = await kg_agent.enrich_trend(state.top_trend)
        return {"kg_enrichment": kg_data}
    except Exception as e:
        logger.exception(f"Exception in enrich_kg_node")
        return {"error": f"KG enrichment failed: {str(e)}"}

async def generate_ideas_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- NODE: Generate Ideas ---")
    try:
        if state.ideas:
            logger.info("Ideas already present, skipping.")
            return {}
            
        if not state.top_trend or not state.kg_enrichment:
            raise ValueError("Missing top trend or KG enrichment data for idea generation.")
            
        ideas_output = await idea_agent.generate_ideas(state.top_trend, state.kg_enrichment)
        
        # Select first idea as default for script generation
        selected_idea = ideas_output.ideas[0] if ideas_output.ideas else "Default tech trend angle"
        
        # Generate sanitized idea_slug
        import re
        clean_idea = re.sub(r'[^a-zA-Z0-9\s-]', '', selected_idea).strip().lower()
        idea_slug = re.sub(r'[\s-]+', '_', clean_idea)
        
        # Save context documents in the finalized idea folder
        await idea_agent.save_finalized_context(state.top_trend, state.kg_enrichment, ideas_output, idea_slug)
        
        return {"ideas": ideas_output, "selected_idea": selected_idea, "idea_slug": idea_slug}
    except Exception as e:
        logger.exception(f"Exception in generate_ideas_node")
        return {"error": f"Idea generation failed: {str(e)}"}

async def generate_script_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- NODE: Generate Script ---")
    try:
        if state.script:
            logger.info("Script already present, skipping.")
            return {}
            
        if not state.top_trend or not state.selected_idea:
            raise ValueError("Missing top trend or selected idea for script writing.")
            
        script = await script_agent.generate_script(state.top_trend, state.selected_idea, idea_slug=state.idea_slug)
        return {"script": script}
    except Exception as e:
        logger.exception(f"Exception in generate_script_node")
        return {"error": f"Script generation failed: {str(e)}"}

async def plan_scenes_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- NODE: Plan Scenes ---")
    try:
        if state.scenes:
            logger.info("Scenes already present, skipping.")
            return {}
            
        if not state.top_trend or not state.script:
            raise ValueError("Missing top trend or script for scene planning.")
            
        scenes = await scene_planner_agent.plan_scenes(state.top_trend, state.script, idea_slug=state.idea_slug)
        return {"scenes": scenes}
    except Exception as e:
        logger.exception(f"Exception in plan_scenes_node")
        return {"error": f"Scene planning failed: {str(e)}"}

async def retrieve_assets_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- NODE: Retrieve Assets ---")
    try:
        if state.assets:
            logger.info("Assets already present, skipping.")
            return {}
            
        if not state.top_trend or not state.scenes:
            raise ValueError("Missing top trend or scenes for asset retrieval.")
            
        assets = await asset_retrieval_agent.retrieve_assets(state.top_trend, state.scenes, idea_slug=state.idea_slug)
        return {"assets": assets}
    except Exception as e:
        logger.exception(f"Exception in retrieve_assets_node")
        return {"error": f"Asset retrieval failed: {str(e)}"}

async def rank_assets_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- NODE: Rank Assets ---")
    try:
        if state.ranked_assets:
            logger.info("Ranked assets already present, skipping.")
            return {}
            
        if not state.top_trend or not state.scenes or not state.assets:
            raise ValueError("Missing top trend, scenes, or retrieved assets for ranking.")
            
        ranked_assets = await ranked_assets_agent.rank_assets(state.top_trend, state.scenes, state.assets, idea_slug=state.idea_slug)
        return {"ranked_assets": ranked_assets}
    except Exception as e:
        logger.exception(f"Exception in rank_assets_node")
        return {"error": f"Asset ranking failed: {str(e)}"}

async def build_timeline_node(state: AgentState) -> Dict[str, Any]:
    logger.info("--- NODE: Build Timeline ---")
    try:
        if state.timeline:
            logger.info("Timeline already present, skipping.")
            return {}
            
        if not state.top_trend or not state.script or not state.scenes or not state.ranked_assets:
            raise ValueError("Missing top trend, script, scenes, or ranked assets for timeline builder.")
            
        timeline = await timeline_builder_agent.build_timeline(
            state.top_trend, state.script, state.scenes, state.ranked_assets, idea_slug=state.idea_slug
        )
        return {"timeline": timeline}
    except Exception as e:
        logger.exception(f"Exception in build_timeline_node")
        return {"error": f"Timeline building failed: {str(e)}"}

# --- Conditional Edges ---

def check_for_errors(state: AgentState):
    if state.error:
        logger.error(f"Pipeline halting due to error: {state.error}")
        return END
    return "continue"

# --- Build the Graph ---

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("discover_trends", discover_trends_node)
workflow.add_node("score_trends", score_trends_node)
workflow.add_node("enrich_kg", enrich_kg_node)
workflow.add_node("generate_ideas", generate_ideas_node)
workflow.add_node("generate_script", generate_script_node)
workflow.add_node("plan_scenes", plan_scenes_node)
workflow.add_node("retrieve_assets", retrieve_assets_node)
workflow.add_node("rank_assets", rank_assets_node)
workflow.add_node("build_timeline", build_timeline_node)

# Set entry point
workflow.set_entry_point("discover_trends")

# Add edges with error checks
workflow.add_conditional_edges("discover_trends", check_for_errors, {"continue": "score_trends", END: END})
workflow.add_conditional_edges("score_trends", check_for_errors, {"continue": "enrich_kg", END: END})
workflow.add_conditional_edges("enrich_kg", check_for_errors, {"continue": "generate_ideas", END: END})
workflow.add_conditional_edges("generate_ideas", check_for_errors, {"continue": "generate_script", END: END})
workflow.add_conditional_edges("generate_script", check_for_errors, {"continue": "plan_scenes", END: END})
workflow.add_conditional_edges("plan_scenes", check_for_errors, {"continue": "retrieve_assets", END: END})
workflow.add_conditional_edges("retrieve_assets", check_for_errors, {"continue": "rank_assets", END: END})
workflow.add_conditional_edges("rank_assets", check_for_errors, {"continue": "build_timeline", END: END})
workflow.add_edge("build_timeline", END)

# Compile graph
graph = workflow.compile()
