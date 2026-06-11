import json
from datetime import datetime
from typing import Dict, Any, Optional

from core.schemas.state import Trend, Script
from core.logging.logger import logger
from core.settings import settings
from core.utils.llm import get_llm
from knowledge_graph.db import db_manager
from langchain_core.prompts import ChatPromptTemplate

class ScriptAgent:
    def __init__(self):
        self.output_dir = settings.BASE_DIR / "outputs" / "scripts"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_script(self, trend: Trend, selected_idea: str, idea_slug: Optional[str] = None) -> Script:
        """
        Generates a 50-60s script from a selected idea and trend data.
        Conforms to a specific timing breakdown: Hook (0-3s), Body (3-50s), CTA (50-60s).
        """
        logger.info(f"Agent 5: Generating script for idea: '{selected_idea}'...")

        script = await self._query_script_llm(trend, selected_idea)
        
        # Save to relational DB
        db_payload = {
            "trend_id": trend.trend_id,
            "hook": script.hook,
            "body": script.body,
            "cta": script.cta
        }
        await db_manager.save_script(db_payload)

        # Save to file system
        if idea_slug:
            filepath = settings.BASE_DIR / "outputs" / idea_slug / "script.json"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.output_dir / f"script_{trend.trend_id}_{timestamp}.json"
            
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(db_payload, f, indent=2)

        logger.info(f"Successfully generated script for trend {trend.trend_id} and saved to {filepath}")
        return script


    async def _query_script_llm(self, trend: Trend, selected_idea: str) -> Script:
        """Queries the LLM for a structured, tone-aware video script."""
        fallback_script = Script(
            hook=f"This repository exploded overnight, and you need to clone it right now.",
            body=f"It's called {trend.title}. {trend.description or 'A new open-source project.'} In just a few days, it's gained thousands of stars. Here is why this matters: it lets you build autonomous pipelines without complex setup. Unlike previous systems, it runs completely local.",
            cta="If you want to stay ahead of the curve, hit follow. Link is in the description!"
        )

        if not settings.GEMINI_API_KEY and not settings.USE_LOCAL_LLM:
            logger.warning("No LLM configured. Returning fallback script.")
            return fallback_script

        prompt_template = ChatPromptTemplate.from_template(
            "You are a master scriptwriter for highly technical, viral Instagram Reels.\n"
            "Your writing style is:\n"
            "- Direct, smart, clean, and founder-focused.\n"
            "- Absolutely NO cheesy marketing phrases (e.g. 'Are you tired of...', 'Say hello to...', 'Game changer!', 'Mind-blowing').\n"
            "- Short, punchy sentences. High information density.\n\n"
            "Create a 60-second video script based on this idea:\n"
            "Angle: '{selected_idea}'\n"
            "Repository/Trend: '{title}'\n"
            "Details: '{description}'\n\n"
            "Structure the output exactly in three parts:\n"
            "1. Hook (0-3s): The first sentence, extremely engaging, sets the stakes.\n"
            "2. Body (3-50s): Context (3-15s), Explanation (15-35s), Why It Matters (35-50s). Integrate facts seamlessly.\n"
            "3. CTA (50-60s): Call to action, clear and professional.\n\n"
            "Respond ONLY with a JSON object matching this schema:\n"
            "{{\n"
            "  \"hook\": \"Punchy attention grabbing first sentence.\",\n"
            "  \"body\": \"The narrative explanation, context, and why it matters. Keep it conversational but technical and concise (~100-120 words total).\",\n"
            "  \"cta\": \"Clear final sentence directing them to clone the repo or follow.\"\n"
            "}}\n"
            "Do not output markdown fences or additional text."
        )

        try:
            llm = get_llm(temperature=0.5, json_mode=True)
            prompt = prompt_template.format_messages(
                selected_idea=selected_idea,
                title=trend.title,
                description=trend.description
            )
            response = await llm.ainvoke(prompt)
            
            text = response.content
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
                
            parsed = json.loads(text.strip())
            
            return Script(
                hook=parsed.get("hook", fallback_script.hook),
                body=parsed.get("body", fallback_script.body),
                cta=parsed.get("cta", fallback_script.cta)
            )
        except Exception as e:
            logger.warning(f"LLM script generation failed ({e}). Returning fallback script.")
            return fallback_script

script_agent = ScriptAgent()
