import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from core.schemas.state import Scene, Asset, Trend, RankedAssetsOutput
from core.logging.logger import logger
from core.settings import settings
from core.utils.llm import get_llm
from knowledge_graph.db import db_manager
from langchain_core.prompts import ChatPromptTemplate

class AssetRankingAgent:
    def __init__(self):
        self.output_dir = settings.BASE_DIR / "outputs" / "assets"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def rank_assets(self, trend: Trend, scenes: List[Scene], assets: List[Asset], idea_slug: Optional[str] = None) -> List[Asset]:
        """
        Scores candidate assets and selects the highest scoring asset for each scene.
        Scoring dimensions: Relevance, Visual Quality, Motion Potential.
        """
        logger.info(f"Agent 8: Ranking candidate assets for trend: '{trend.trend_id}'...")

        # Group assets by scene
        scene_candidates: Dict[int, List[Asset]] = {}
        for a in assets:
            scene_candidates.setdefault(a.scene, []).append(a)

        selected_assets: List[Asset] = []

        # Find corresponding scene info
        scenes_map = {s.scene: s for s in scenes}

        for scene_id, candidates in scene_candidates.items():
            scene_info = scenes_map.get(scene_id)
            if not scene_info:
                # If no scene matching, default to first candidate
                selected_assets.append(candidates[0])
                continue

            # Rank candidates
            ranked_candidates = []
            for candidate in candidates:
                score = await self._calculate_asset_score(scene_info, candidate)
                candidate.score = score
                ranked_candidates.append(candidate)

            # Sort descending by score
            ranked_candidates.sort(key=lambda x: x.score or 0.0, reverse=True)
            
            # Select the top candidate
            best_asset = ranked_candidates[0]
            logger.info(f"Scene {scene_id}: Selected {best_asset.source} asset (local: {best_asset.local_path}) with score {best_asset.score}")
            selected_assets.append(best_asset)

        # 1. Save to relational DB
        await db_manager.save_assets(trend.trend_id, [a.model_dump() for a in selected_assets])

        # 2. Save to file system
        if idea_slug:
            filepath = settings.BASE_DIR / "outputs" / idea_slug / "selected_assets.json"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.output_dir / f"selected_assets_{trend.trend_id}_{timestamp}.json"
            
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump([a.model_dump() for a in selected_assets], f, indent=2)

        return selected_assets


    async def _calculate_asset_score(self, scene: Scene, asset: Asset) -> float:
        """Calculates a quality score (0.0 to 1.0) using LLM / heuristics."""
        
        # 1. Simple heuristic scoring baseline
        relevance = 0.5
        visual_quality = 0.5
        motion_potential = 0.5
        
        # Adjust relevance based on source type compatibility
        if scene.asset_type in ["SCREENSHOT", "UI_CAPTURE"] and asset.source in ["screenshot", "screenshot_fallback"]:
            relevance = 0.95
        elif scene.asset_type in ["STOCK", "AI_BROLL"] and asset.source in ["pexels", "pixabay"]:
            relevance = 0.85
            motion_potential = 0.8  # video assets have motion
        elif asset.source == "unsplash":
            relevance = 0.75
            visual_quality = 0.85   # unsplash images are high quality
            motion_potential = 0.3  # static image
        elif asset.source == "picsum":
            relevance = 0.5
            visual_quality = 0.6
            motion_potential = 0.3
        elif asset.source == "local_mock":
            relevance = 0.3
            visual_quality = 0.3
            motion_potential = 0.1

        # 2. Refine scores using LLM if available
        if settings.GEMINI_API_KEY or settings.USE_LOCAL_LLM:
            prompt_template = ChatPromptTemplate.from_template(
                "You are an AI video editor quality inspector.\n"
                "Evaluate the visual relevance of this asset for a scene in an Instagram Reel.\n\n"
                "Scene Visual Description: {scene_visual}\n"
                "Scene Asset Type Required: {scene_type}\n"
                "Asset Source: {asset_source}\n"
                "Asset URL: {asset_url}\n"
                "Asset Semantic Tags/Description: {asset_tags}\n\n"
                "Score the asset on three dimensions from 0.0 to 1.0:\n"
                "1. Relevance: How well does this asset match the visual description? Base this primarily on the semantic tags/description of the asset and how they align with the scene visual description.\n"
                "2. Visual Quality: Estimate quality based on source (e.g. pexels/unsplash is high, local_mock is low).\n"
                "3. Motion Potential: (1.0 for videos, 0.3 for static images, 0.1 for fallbacks).\n\n"
                "Respond ONLY with a JSON object, like this:\n"
                "{{\n"
                "  \"relevance\": 0.9,\n"
                "  \"visual_quality\": 0.8,\n"
                "  \"motion_potential\": 0.3\n"
                "}}\n"
                "Do not output markdown fences or comments."
            )

            try:
                llm = get_llm(temperature=0.1, json_mode=True)
                prompt = prompt_template.format_messages(
                    scene_visual=scene.visual,
                    scene_type=scene.asset_type,
                    asset_source=asset.source,
                    asset_url=asset.asset_url,
                    asset_tags=", ".join(asset.tags) if asset.tags else "None"
                )
                response = await llm.ainvoke(prompt)
                
                text = response.content
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                    
                parsed = json.loads(text.strip())
                relevance = float(parsed.get("relevance", relevance))
                visual_quality = float(parsed.get("visual_quality", visual_quality))
                motion_potential = float(parsed.get("motion_potential", motion_potential))
            except Exception as e:
                logger.warning(f"LLM asset evaluation failed ({e}). Using heuristic scoring baseline instead.")

        # Combined weight: 0.5 relevance + 0.3 quality + 0.2 motion
        final_score = round((0.5 * relevance) + (0.3 * visual_quality) + (0.2 * motion_potential), 2)
        return final_score

ranked_assets_agent = AssetRankingAgent()
