import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from core.schemas.state import Trend, Script, Scene
from core.logging.logger import logger
from core.settings import settings
from core.utils.llm import get_llm
from knowledge_graph.db import db_manager
from langchain_core.prompts import ChatPromptTemplate

class ScenePlannerAgent:
    def __init__(self):
        self.output_dir = settings.BASE_DIR / "outputs" / "scripts"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def plan_scenes(self, trend: Trend, script: Script, idea_slug: Optional[str] = None) -> List[Scene]:
        """
        Translates script text into a structured list of scenes.
        Enforces a total duration of around 50-60s.
        """
        logger.info(f"Agent 6: Planning scenes for script of trend '{trend.trend_id}'...")

        raw_scenes = await self._query_scene_planner_llm(trend, script)
        
        if not raw_scenes:
            raw_scenes = self._generate_fallback_scenes(trend, script)

        scenes: List[Scene] = []
        for s in raw_scenes:
            scenes.append(Scene(
                scene=int(s.get("scene", len(scenes) + 1)),
                duration=float(s.get("duration", 5.0)),
                visual=s.get("visual", "Abstract tech visualization"),
                asset_type=s.get("asset_type", "STOCK").upper(),
                retrieval_hints=s.get("retrieval_hints", "technology abstract")
            ))

        # 1. Save to Relational DB
        scenes_dicts = [s.model_dump() for s in scenes]
        await db_manager.save_scenes(trend.trend_id, scenes_dicts)

        # 2. Save to file system
        if idea_slug:
            filepath = settings.BASE_DIR / "outputs" / idea_slug / "scenes.json"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.output_dir / f"scenes_{trend.trend_id}_{timestamp}.json"
            
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(scenes_dicts, f, indent=2)

        logger.info(f"Generated {len(scenes)} scenes for trend {trend.trend_id} and saved to {filepath}")
        return scenes


    async def _query_scene_planner_llm(self, trend: Trend, script: Script) -> List[Dict[str, Any]]:
        """Queries LLM to segment the script and define visuals/duration per scene."""
        if not settings.GEMINI_API_KEY and not settings.USE_LOCAL_LLM:
            logger.warning("No LLM configured. Skipping scene planning.")
            return []

        prompt_template = ChatPromptTemplate.from_template(
            "You are a video editor and storyboard artist for tech reels.\n"
            "Given this script, break it down into a list of scenes. The total duration must be around 55-60 seconds.\n"
            "Assign each scene an asset type from: SCREENSHOT, STOCK, AI_BROLL, LOGO, CHART, UI_CAPTURE.\n\n"
            "Full Script:\n"
            "Hook: {hook}\n"
            "Body: {body}\n"
            "CTA: {cta}\n\n"
            "Trend Context:\n"
            "Title: {title}\n"
            "Url: {url}\n\n"
            "Guidelines:\n"
            "- First scene is the Hook, duration should be exactly 3 seconds.\n"
            "- Middle scenes represent the Body (~40-50s), split into 4-6 distinct segments (e.g. 5 to 8s each).\n"
            "- Final scene is the CTA, duration should be ~5-7 seconds.\n"
            "- For SCREENSHOT or UI_CAPTURE, specify the retrieval hint as a single URL string (e.g. {url} or related documentation URLs).\n"
            "- For STOCK or AI_BROLL, specify 2-3 clean, unquoted, lowercase search keywords optimized for stock databases (e.g. 'coding laptop keyboard', 'abstract database server', 'robot hand technology'). Do NOT include quotes, commas, or punctuation.\n\n"
            "Respond ONLY with a JSON object containing a list of scenes under the key \"scenes\", matching this schema:\n"
            "{{\n"
            "  \"scenes\": [\n"
            "    {{\n"
            "      \"scene\": 1,\n"
            "      \"duration\": 3.0,\n"
            "      \"visual\": \"visual description of what is shown\",\n"
            "      \"asset_type\": \"SCREENSHOT|STOCK|AI_BROLL|LOGO|CHART|UI_CAPTURE\",\n"
            "      \"retrieval_hints\": \"search keywords or URL to screenshot\"\n"
            "    }}\n"
            "  ]\n"
            "}}\n"
            "Do not output markdown fences or comments."
        )

        try:
            llm = get_llm(temperature=0.4, json_mode=True)
            prompt = prompt_template.format_messages(
                hook=script.hook,
                body=script.body,
                cta=script.cta,
                title=trend.title,
                url=trend.url
            )
            response = await llm.ainvoke(prompt)
            
            text = response.content
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
                
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict) and "scenes" in parsed:
                return parsed["scenes"]
        except Exception as e:
            logger.warning(f"LLM scene planning failed ({e}). Returning empty list to trigger fallback scenes.")
            return []

    def _generate_fallback_scenes(self, trend: Trend, script: Script) -> List[Dict[str, Any]]:
        """Returns standard visual scene transitions if LLM fails."""
        return [
            {
                "scene": 1,
                "duration": 3.0,
                "visual": f"Trending GitHub repository page for {trend.title}",
                "asset_type": "SCREENSHOT",
                "retrieval_hints": trend.url or "https://github.com"
            },
            {
                "scene": 2,
                "duration": 12.0,
                "visual": "A software engineer typing code intensely on a mechanical keyboard, dark background, neon lighting",
                "asset_type": "STOCK",
                "retrieval_hints": "software engineer coding dark neon"
            },
            {
                "scene": 3,
                "duration": 20.0,
                "visual": "An abstract visualization of a neural network with glowing connections and nodes, slow movement",
                "asset_type": "AI_BROLL",
                "retrieval_hints": "neural network abstract glowing nodes"
            },
            {
                "scene": 4,
                "duration": 15.0,
                "visual": "A server rack with flashing green and blue LED lights, showing local compute hardware",
                "asset_type": "STOCK",
                "retrieval_hints": "data center server rack blinking lights"
            },
            {
                "scene": 5,
                "duration": 6.0,
                "visual": f"The official logo of {trend.title} or developer profile page",
                "asset_type": "LOGO",
                "retrieval_hints": trend.url or "https://github.com"
            }
        ]

scene_planner_agent = ScenePlannerAgent()
