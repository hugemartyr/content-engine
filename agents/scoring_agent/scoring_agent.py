import json
import math
from datetime import datetime
from typing import List, Tuple, Dict, Any

from core.schemas.state import Trend, TrendScore, ScoreBreakdown
from core.logging.logger import logger
from core.settings import settings
from core.utils.llm import get_llm
from knowledge_graph.db import db_manager
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

class TrendScoringAgent:
    def __init__(self):
        self.output_dir = settings.BASE_DIR / "outputs" / "trends"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Setup JSON parser for structured output from LLM
        self.parser = JsonOutputParser(pydantic_object=ScoreBreakdown)
        
    async def score_trends(self, trends: List[Trend]) -> List[TrendScore]:
        """
        Scores and ranks a list of trends based on freshness, virality, novelty,
        visual potential, and technical depth. Uses a hybrid heuristic + LLM approach.
        """
        logger.info(f"Agent 2: Starting Trend Scoring for {len(trends)} items...")
        
        scored_trends: List[TrendScore] = []
        llm = None
        
        if settings.GEMINI_API_KEY or settings.USE_LOCAL_LLM:
            try:
                llm = get_llm(temperature=0.2, json_mode=True)
            except Exception as e:
                logger.error(f"Failed to initialize LLM for trend scoring: {e}. Baselines will be used.")

        for trend in trends:
            # 1. Heuristic Freshness & Virality
            freshness = self._calculate_freshness(trend)
            virality = self._calculate_virality(trend)
            
            # 2. LLM Qualitative Scores (Novelty, Visual Potential, Technical Depth)
            novelty, visual_potential, technical_depth = await self._evaluate_qualitative_dimensions(
                trend, llm
            )
            
            # 3. Weighted Scoring Formula
            # score = 0.30 freshness + 0.25 virality + 0.20 novelty + 0.15 visual_potential + 0.10 technical_depth
            final_score = round(
                (0.30 * freshness) +
                (0.25 * virality) +
                (0.20 * novelty) +
                (0.15 * visual_potential) +
                (0.10 * technical_depth),
                2
            )

            breakdown = ScoreBreakdown(
                freshness=round(freshness, 2),
                virality=round(virality, 2),
                novelty=round(novelty, 2),
                visual_potential=round(visual_potential, 2),
                technical_depth=round(technical_depth, 2)
            )

            scored_trends.append(TrendScore(
                trend_id=trend.trend_id,
                score=final_score,
                breakdown=breakdown
            ))

        # Sort descending by final score
        scored_trends.sort(key=lambda x: x.score, reverse=True)
        
        logger.info(f"Successfully scored and ranked {len(scored_trends)} trends. Top score: {scored_trends[0].score if scored_trends else 'N/A'}")

        # Save to DB
        for s in scored_trends:
            await db_manager.save_score(s.model_dump())

        # Save to file system
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"scored_trends_{timestamp}.json"
        with open(filepath, "w") as f:
            json.dump([s.model_dump() for s in scored_trends], f, indent=2)

        return scored_trends

    def _calculate_freshness(self, trend: Trend) -> float:
        """Calculates freshness score (0-10) using age metrics."""
        metrics = trend.metrics
        if trend.source == "github":
            # Repositories are generally fresh if discovered, baseline 8.5
            return 8.5
        elif trend.source == "reddit":
            age_hours = metrics.get("post_age_hours", 24.0)
            # 0-12 hours is a 10. Decay linearly up to 72 hours.
            return max(1.0, min(10.0, 10.0 - (age_hours - 12) / 6.0)) if age_hours > 12 else 10.0
        elif trend.source == "youtube":
            age_hours = metrics.get("age_hours", 24.0)
            # YouTube decay is slower
            return max(1.0, min(10.0, 10.0 - (age_hours - 24) / 12.0)) if age_hours > 24 else 10.0
        elif trend.source == "newsletter":
            # Newsletters are curated digests, baseline 8.0
            return 8.0
        return 5.0

    def _calculate_virality(self, trend: Trend) -> float:
        """Calculates virality score (0-10) using engagement metrics."""
        metrics = trend.metrics
        if trend.source == "github":
            stars = metrics.get("stars", 100)
            # Logarithmic mapping of stars (100 -> 2.0, 1000 -> 5.0, 10000 -> 8.0, 50000 -> 10.0)
            if stars <= 0:
                return 1.0
            return min(10.0, round(2.0 + math.log10(stars / 100.0) * 3.0, 1))
        elif trend.source == "reddit":
            upvotes = metrics.get("upvotes", 10)
            comments = metrics.get("comments", 0)
            total_engagement = upvotes + (comments * 2)
            # Scale up to 2000 total engagement
            return min(10.0, round((total_engagement / 200.0), 1))
        elif trend.source == "youtube":
            velocity = metrics.get("velocity", 100)
            # Log scale views per hour (100 -> 2.0, 1000 -> 5.0, 10000 -> 8.0, 50000+ -> 10.0)
            if velocity <= 0:
                return 1.0
            return min(10.0, round(2.0 + math.log10(velocity / 100.0) * 3.0, 1))
        elif trend.source == "newsletter":
            # Newsletters are informational, baseline 6.0
            return 6.0
        return 5.0

    async def _evaluate_qualitative_dimensions(
        self, trend: Trend, llm: Any
    ) -> Tuple[float, float, float]:
        """
        Uses LLM to evaluate Novelty, Visual Potential, and Technical Depth.
        Falls back to baseline heuristics if LLM is offline/disabled.
        """
        if not llm:
            # Safe offline fallback baselines based on sources
            if trend.source == "github":
                return 8.0, 4.0, 9.0  # High novelty/technical, lower visual
            elif trend.source == "reddit":
                return 6.0, 5.0, 5.0
            elif trend.source == "youtube":
                return 6.0, 8.0, 6.0  # High visual potential
            else:
                return 7.0, 5.0, 7.0

        prompt_template = ChatPromptTemplate.from_template(
            "You are a trend analyst scoring a tech trend for Instagram Reels.\n"
            "Assess the following topic on three qualitative dimensions from 0.0 to 10.0:\n"
            "1. Novelty: How new/groundbreaking is this concept (0=highly commoditized, 10=completely new/mind-bending)?\n"
            "2. Visual Potential: How easy is it to show interesting visuals for this (0=dry theoretical math, 10=easy to show screenshots, code running, UI interfaces)?\n"
            "3. Technical Depth: How rich is the technical depth (0=simple wrapper/fluff, 10=complex system/heavy engineering)?\n\n"
            "Topic: {title}\n"
            "Description: {description}\n"
            "Source: {source}\n\n"
            "{format_instructions}\n"
            "Respond ONLY with valid JSON."
        )

        prompt = prompt_template.format_messages(
            title=trend.title,
            description=trend.description,
            source=trend.source,
            format_instructions=self.parser.get_format_instructions()
        )

        try:
            response = await llm.ainvoke(prompt)
            # Parse the response text
            text = response.content
            # Clean response text if LLM returns markdown fences
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            parsed = json.loads(text.strip())
            
            novelty = float(parsed.get("novelty", 5.0))
            visual_potential = float(parsed.get("visual_potential", 5.0))
            technical_depth = float(parsed.get("technical_depth", 5.0))
            
            # Constrain to 0-10 range
            novelty = max(0.0, min(10.0, novelty))
            visual_potential = max(0.0, min(10.0, visual_potential))
            technical_depth = max(0.0, min(10.0, technical_depth))
            
            return novelty, visual_potential, technical_depth
        except Exception as e:
            logger.warning(f"LLM qualitative scoring failed for '{trend.title}' ({e}). Falling back to heuristic baselines.")
            # Safe offline fallback baselines based on sources
            if trend.source == "github":
                return 8.0, 4.0, 9.0  # High novelty/technical, lower visual
            elif trend.source == "reddit":
                return 6.0, 5.0, 5.0
            elif trend.source == "youtube":
                return 6.0, 8.0, 6.0  # High visual potential
            else:
                return 7.0, 5.0, 7.0

scoring_agent = TrendScoringAgent()
