import json
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional

from core.schemas.state import Scene, Asset, Trend
from core.logging.logger import logger
from core.settings import settings
from services.stock.stock_service import stock_service
from services.screenshots.screenshot_service import screenshot_service
from knowledge_graph.db import db_manager

class AssetRetrievalAgent:
    def __init__(self):
        self.output_dir = settings.BASE_DIR / "outputs" / "assets"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def retrieve_assets(self, trend: Trend, scenes: List[Scene], idea_slug: Optional[str] = None) -> List[Asset]:
        """
        Asynchronously retrieves asset candidates (screenshots or stocks) for each scene
        in the storyboard. Downloads them locally.
        """
        logger.info(f"Agent 7: Starting Asset Retrieval for {len(scenes)} scenes...")

        dest_dir = None
        if idea_slug:
            dest_dir = settings.BASE_DIR / "outputs" / idea_slug / "assets"
            dest_dir.mkdir(parents=True, exist_ok=True)

        tasks = []
        for scene in scenes:
            tasks.append(self._retrieve_for_scene(scene, dest_dir=dest_dir))

        # Fetch all assets concurrently
        retrieved_results = await asyncio.gather(*tasks)

        # Flatten list (since each scene can return multiple candidates)
        candidates: List[Asset] = []
        for result in retrieved_results:
            if isinstance(result, list):
                candidates.extend(result)
            elif result:
                candidates.append(result)

        logger.info(f"Retrieved {len(candidates)} candidate assets in total.")

        # 1. Save to relational DB
        await db_manager.save_assets(trend.trend_id, [c.model_dump() for c in candidates])

        # 2. Save to file system
        if idea_slug:
            filepath = settings.BASE_DIR / "outputs" / idea_slug / "candidate_assets.json"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.output_dir / f"retrieved_assets_{trend.trend_id}_{timestamp}.json"
            
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump([c.model_dump() for c in candidates], f, indent=2)

        return candidates

    async def _retrieve_for_scene(self, scene: Scene, dest_dir: Optional[Any] = None) -> List[Asset]:
        """Retrieves asset candidates for a specific scene."""
        candidates = []
        
        # 1. Screenshot scene (GitHub/Docs URLs)
        if scene.asset_type in ["SCREENSHOT", "UI_CAPTURE"]:
            url = scene.retrieval_hints
            # Enforce absolute URL fallback if simple string is given
            if not url.startswith("http"):
                url = f"https://github.com/search?q={url}"
            try:
                res = await screenshot_service.capture_screenshot(url, scene.scene, dest_dir=dest_dir)
                domain = url.split("//")[-1].split("/")[0] if "//" in url else "webpage"
                tags = ["screenshot", "web", domain]
                candidates.append(Asset(
                    scene=scene.scene,
                    asset_url=res["asset_url"],
                    local_path=res["local_path"],
                    license=res["license"],
                    source=res["source"],
                    tags=tags
                ))
            except Exception as e:
                logger.error(f"Error capturing screenshot for Scene {scene.scene}: {e}")

        # 2. Stock / B-Roll / Logo scene (Keywords)
        else:
            # Clean and sanitize search query
            clean_hint = scene.retrieval_hints.strip().strip("'\"").strip()
            # Remove redundant commas and brackets
            clean_hint = clean_hint.replace(",", "").replace("[", "").replace("]", "").strip()
            
            # Split the hints if the LLM outputted quotes around multiple strings (just in case)
            if "'" in clean_hint or '"' in clean_hint:
                import re
                phrases = re.findall(r'[\'"](.*?)[\'"]', scene.retrieval_hints)
                if phrases:
                    clean_hint = phrases[0].strip()
            
            # Now build queries
            queries = [clean_hint]
            if " " in clean_hint:
                queries.append(clean_hint.split(" ")[0] + " technology")
            else:
                queries.append(f"abstract {clean_hint}")
                
            for i, q in enumerate(queries[:2]):
                try:
                    res = await stock_service.search_and_download_stock(
                        query=q,
                        scene_id=scene.scene,
                        asset_type=scene.asset_type,
                        dest_dir=dest_dir
                    )
                    candidates.append(Asset(
                        scene=scene.scene,
                        asset_url=res["asset_url"],
                        local_path=res["local_path"],
                        license=res["license"],
                        source=res["source"],
                        tags=res.get("tags", [])
                    ))
                except Exception as e:
                    logger.error(f"Error retrieving stock asset '{q}' for Scene {scene.scene}: {e}")

        # Fallback safeguard in case no candidates were downloaded
        if not candidates:
            logger.warning(f"No assets retrieved for Scene {scene.scene}. Writing critical local mockup fallback.")
            # Touch a simple blank file
            fallback_filename = f"scene_{scene.scene}_critical_fallback.jpg"
            target_dir = dest_dir if dest_dir is not None else self.output_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            fallback_path = target_dir / fallback_filename
            fallback_path.touch()
            candidates.append(Asset(
                scene=scene.scene,
                asset_url="local_fallback",
                local_path=str(fallback_path.relative_to(settings.BASE_DIR)),
                license="fallback",
                source="local_mock",
                tags=["fallback", "local_mock", "placeholder"]
            ))

        return candidates

asset_retrieval_agent = AssetRetrievalAgent()

