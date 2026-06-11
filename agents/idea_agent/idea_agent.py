import json
from datetime import datetime
from typing import List, Dict, Any

from core.schemas.state import Trend, KnowledgeGraphData, IdeaOutput
from core.logging.logger import logger
from core.settings import settings
from core.utils.llm import get_llm
from knowledge_graph.db import db_manager
from langchain_core.prompts import ChatPromptTemplate

class IdeaAgent:
    def __init__(self):
        self.output_dir = settings.BASE_DIR / "outputs" / "ideas"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_ideas(self, trend: Trend, kg_data: KnowledgeGraphData) -> IdeaOutput:
        """
        Generates 10-20 attention-grabbing content angles/ideas from the given trend
        and KG context pack.
        """
        logger.info(f"Agent 4: Starting Idea Generation for trend: '{trend.title}'...")

        raw_ideas = await self._query_ideas_llm(trend, kg_data)
        
        # Ensure we have a reasonable list
        if not raw_ideas:
            raw_ideas = self._get_fallback_ideas(trend)

        # Slice to ensure we respect the 10-20 limit
        ideas = raw_ideas[:20]
        if len(ideas) < 10:
            # Pad if less than 10
            ideas.extend(self._get_fallback_ideas(trend)[:10 - len(ideas)])

        idea_output = IdeaOutput(
            trend_id=trend.trend_id,
            ideas=ideas
        )

        # 1. Save to Relational DB
        await db_manager.save_ideas(idea_output.model_dump())

        # 2. Save to file system
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"ideas_{trend.trend_id}_{timestamp}.json"
        with open(filepath, "w") as f:
            json.dump(idea_output.model_dump(), f, indent=2)

        logger.info(f"Generated {len(ideas)} ideas for trend '{trend.title}'. Saved to {filepath}")
        return idea_output

    async def _query_ideas_llm(self, trend: Trend, kg_data: KnowledgeGraphData) -> List[str]:
        """Queries LLM for content angles."""
        if not settings.GEMINI_API_KEY and not settings.USE_LOCAL_LLM:
            logger.warning("No LLM configured. Skipping idea generation.")
            return []

        prompt_template = ChatPromptTemplate.from_template(
            "You are a viral social media strategist specializing in developer content and tech/AI Instagram Reels.\n"
            "Your target audience is software developers, tech founders, and AI enthusiasts.\n"
            "Generate 10 to 20 attention-grabbing, highly viral hooks or content angles for a 60-second video about the following trend.\n\n"
            "Trend: {title}\n"
            "Summary: {description}\n"
            "Related Entities: {entities}\n"
            "Related Topics: {topics}\n\n"
            "Format Guidelines:\n"
            "- Short, punchy, click-worthy titles (not full scripts yet)\n"
            "- Keep them founder-focused or developer-centric (e.g., 'Nobody noticed this launch', 'Why OpenAI should be worried')\n"
            "- Avoid clickbait that sounds like cheap marketing; keep it intelligent and insider-focused\n\n"
            "Respond ONLY with a JSON object containing a list of strings under the key \"ideas\", like this:\n"
            "{{\n"
            "  \"ideas\": [\n"
            "    \"Angle 1\",\n"
            "    \"Angle 2\"\n"
            "  ]\n"
            "}}\n"
            "Do not output markdown fences or additional text."
        )

        entities_str = ", ".join([e.name for e in kg_data.related_entities])
        topics_str = ", ".join(kg_data.related_topics)

        try:
            llm = get_llm(temperature=0.7, json_mode=True)
            prompt = prompt_template.format_messages(
                title=trend.title,
                description=trend.description,
                entities=entities_str,
                topics=topics_str
            )
            response = await llm.ainvoke(prompt)
            
            text = response.content
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
                
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict) and "ideas" in parsed:
                return [str(item) for item in parsed["ideas"]]
        except Exception as e:
            logger.warning(f"LLM Idea generation failed ({e}). Returning empty list to trigger fallback ideas.")
            return []

    def _get_fallback_ideas(self, trend: Trend) -> List[str]:
        """Returns default fallback ideas if LLM fails."""
        name = trend.title
        return [
            f"This repo exploded overnight: {name}",
            f"Why developers are talking about {name} right now",
            f"Nobody noticed this massive launch: {name}",
            f"The future of agents: How {name} changes everything",
            f"Why OpenAI should be worried about {name}",
            f"Every tech founder needs to see this: {name}",
            f"Is {name} the ultimate developer tool?",
            f"Build AI applications in minutes using {name}",
            f"A secret AI repository you need to clone today",
            f"The open-source alternative to expensive APIs: {name}"
        ]

    async def save_finalized_context(self, trend: Trend, kg_data: KnowledgeGraphData, ideas_output: IdeaOutput, idea_slug: str):
        """
        Saves trend.json, kg_enrichment.json, and ideas.json under outputs/<idea_slug>/
        """
        logger.info(f"Saving context documents for idea '{idea_slug}'...")
        dest_dir = settings.BASE_DIR / "outputs" / idea_slug
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Save trend.json
        with open(dest_dir / "trend.json", "w") as f:
            json.dump(trend.model_dump(), f, indent=2)
            
        # Save kg_enrichment.json
        with open(dest_dir / "kg_enrichment.json", "w") as f:
            json.dump(kg_data.model_dump(), f, indent=2)
            
        # Save ideas.json
        with open(dest_dir / "ideas.json", "w") as f:
            json.dump(ideas_output.model_dump(), f, indent=2)
            
        logger.info(f"Finalized context saved to {dest_dir}")

idea_agent = IdeaAgent()

