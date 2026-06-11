import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from core.schemas.state import Trend, Script, Scene, Asset, Timeline, TimelineItem
from core.logging.logger import logger
from core.settings import settings
from core.utils.llm import get_llm
from knowledge_graph.db import db_manager
from langchain_core.prompts import ChatPromptTemplate

class TimelineBuilderAgent:
    def __init__(self):
        self.output_dir = settings.BASE_DIR / "outputs" / "timelines"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Low energy, mellow ambient bgms
        self.bgm_tracks = [
            "ambient_tech_mellow.mp3",
            "lofi_study_beats.mp3",
            "tech_documentary.mp3"
        ]

    async def build_timeline(
        self, trend: Trend, script: Script, scenes: List[Scene], assets: List[Asset], idea_slug: Optional[str] = None
    ) -> Timeline:
        """
        Assembles the final editor-ready timeline JSON.
        Aligns assets, calculates timing, overlays captions, and selects BGM.
        """
        logger.info(f"Agent 9: Building timeline for trend: '{trend.trend_id}'...")

        # Map assets by scene number
        assets_map = {a.scene: a for a in assets}

        # Select BGM (default to ambient_tech_mellow)
        bgm = "ambient_tech_mellow.mp3"
        if "lofi" in trend.title.lower() or "reddit" in trend.trend_id:
            bgm = "lofi_study_beats.mp3"
        elif "youtube" in trend.trend_id:
            bgm = "tech_documentary.mp3"

        # Generate scene captions
        captions = await self._generate_scene_captions(trend, script, scenes)

        timeline_items: List[TimelineItem] = []
        current_time = 0.0

        # Sort scenes to ensure chronological order
        sorted_scenes = sorted(scenes, key=lambda x: x.scene)

        for scene in sorted_scenes:
            asset_obj = assets_map.get(scene.scene)
            # Find filename (relative to outputs/assets or base path)
            asset_file = "placeholder.png"
            if asset_obj and asset_obj.local_path:
                filename = asset_obj.local_path.split("/")[-1]
                if idea_slug:
                    asset_file = f"assets/{filename}"
                else:
                    asset_file = filename
            
            duration = scene.duration
            start = round(current_time, 2)
            end = round(current_time + duration, 2)
            current_time = end

            caption_text = captions.get(scene.scene, scene.visual)

            timeline_items.append(TimelineItem(
                start=start,
                end=end,
                asset=asset_file,
                caption=caption_text
            ))

        timeline = Timeline(
            title=f"Reel: {trend.title}",
            bgm=bgm,
            timeline=timeline_items
        )

        # 1. Save to relational DB
        db_payload = {
            "trend_id": trend.trend_id,
            "title": timeline.title,
            "bgm": timeline.bgm,
            "timeline": [item.model_dump() for item in timeline.timeline]
        }
        await db_manager.save_timeline(db_payload)

        # 2. Save to file system
        if idea_slug:
            filepath = settings.BASE_DIR / "outputs" / idea_slug / "timeline.json"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.output_dir / f"timeline_{trend.trend_id}_{timestamp}.json"
            
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(db_payload, f, indent=2)

        logger.info(f"Timeline successfully assembled and saved to {filepath}")
        return timeline


    async def _generate_scene_captions(
        self, trend: Trend, script: Script, scenes: List[Scene]
    ) -> Dict[int, str]:
        """Queries LLM to segment the script narration into captions matching each scene."""
        captions = {}
        
        # 1. Default heuristics fallback
        captions[1] = script.hook
        
        # Distribute body and cta
        body_sentences = [s.strip() for s in script.body.split(".") if s.strip()]
        for scene in scenes[1:-1]:
            if body_sentences:
                captions[scene.scene] = body_sentences.pop(0)
            else:
                captions[scene.scene] = scene.visual

        captions[scenes[-1].scene] = script.cta

        # 2. LLM alignment if key is present
        if settings.GEMINI_API_KEY or settings.USE_LOCAL_LLM:
            prompt_template = ChatPromptTemplate.from_template(
                "You are an editor preparing on-screen text overlays (captions) for a short video.\n"
                "Align the narration script parts with the planned storyboard scenes.\n\n"
                "Narration:\n"
                "Hook: {hook}\n"
                "Body: {body}\n"
                "CTA: {cta}\n\n"
                "Storyboard Scenes:\n"
                "{scenes_list}\n\n"
                "Respond ONLY with a JSON object mapping scene index to a concise overlay caption (under 10 words):\n"
                "{{\n"
                "  \"1\": \"caption for scene 1\",\n"
                "  \"2\": \"caption for scene 2\"\n"
                "}}\n"
                "Do not output markdown fences or comments."
            )

            scenes_list = "\n".join([f"Scene {s.scene} ({s.duration}s): {s.visual}" for s in scenes])
            try:
                llm = get_llm(temperature=0.3, json_mode=True)
                prompt = prompt_template.format_messages(
                    hook=script.hook,
                    body=script.body,
                    cta=script.cta,
                    scenes_list=scenes_list
                )
                response = await llm.ainvoke(prompt)
                
                text = response.content
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                    
                parsed = json.loads(text.strip())
                for k, v in parsed.items():
                    captions[int(k)] = str(v)
            except Exception as e:
                logger.warning(f"LLM caption generation failed ({e}). Using heuristic default captions instead.")

        return captions

timeline_builder_agent = TimelineBuilderAgent()
