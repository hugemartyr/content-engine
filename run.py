import argparse
import asyncio
import json
import sys
from uvicorn import run as run_server

from core.logging.logger import logger
from core.settings import settings
from core.graph.workflow import graph
from core.schemas.state import AgentState
from knowledge_graph.db import db_manager

async def run_pipeline_cli(topic: str):
    """Executes the pipeline synchronously in the terminal and outputs the final timeline."""
    logger.info(f"=== Starting CLI Pipeline Run for Topic: '{topic}' ===")
    
    # 1. Initialize DB
    await db_manager.initialize_db()
    
    # 2. Setup state
    initial_state = AgentState(topic=topic)
    
    # 3. Invoke LangGraph
    try:
        final_state = await graph.ainvoke(initial_state)
        
        if final_state.get("error"):
            logger.error(f"Pipeline run failed: {final_state['error']}")
            sys.exit(1)
            
        logger.info("=== Pipeline Completed Successfully! ===")
        
        # Structure the final output package requested in Core Mission
        # trend, idea, script, scenes, assets, timeline
        output_package = {
            "trend": final_state.get("top_trend").model_dump() if final_state.get("top_trend") else {},
            "idea": final_state.get("selected_idea"),
            "script": final_state.get("script").model_dump() if final_state.get("script") else {},
            "scenes": [s.model_dump() for s in final_state.get("scenes", [])],
            "assets": [a.model_dump() for a in final_state.get("ranked_assets", [])],
            "timeline": final_state.get("timeline").model_dump() if final_state.get("timeline") else {}
        }
        
        # Print timeline JSON nicely
        print("\n=== FINAL TIMELINE JSON ===")
        print(json.dumps(output_package, indent=2))
        print("===========================\n")
        
        # Also save to main output
        idea_slug = final_state.get("idea_slug")
        if idea_slug:
            output_file = settings.BASE_DIR / "outputs" / idea_slug / "final_package.json"
        else:
            output_file = settings.BASE_DIR / "outputs" / f"final_reel_package_{topic.lower().replace(' ', '_')}.json"
            
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(output_package, f, indent=2)
        logger.info(f"Saved complete editor package to: {output_file}")

        
    except Exception as e:
        logger.critical(f"CLI Pipeline run failed with critical exception: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="AI Reel Content Intelligence Engine Runner")
    parser.add_argument(
        "--topic", 
        type=str, 
        help="Run the pipeline for the specified topic and export the editor package."
    )
    parser.add_argument(
        "--serve", 
        action="store_true", 
        help="Start the FastAPI uvicorn server."
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=8000, 
        help="Port to start uvicorn server on (default: 8000)."
    )
    
    args = parser.parse_args()
    
    if args.serve:
        logger.info(f"Starting API Server on port {args.port}...")
        run_server("api.app:app", host="127.0.0.1", port=args.port, reload=True)
    elif args.topic:
        asyncio.run(run_pipeline_cli(args.topic))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
