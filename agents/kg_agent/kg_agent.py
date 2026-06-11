import json
from datetime import datetime
from typing import Dict, Any, List

from core.schemas.state import Trend, KnowledgeGraphData, KGEntity, KGRelation
from core.logging.logger import logger
from core.settings import settings
from core.utils.llm import get_llm
from knowledge_graph.db import db_manager
from knowledge_graph.vector import vector_db
from langchain_core.prompts import ChatPromptTemplate

class KGAgent:
    def __init__(self):
        self.output_dir = settings.BASE_DIR / "outputs" / "trends"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def enrich_trend(self, trend: Trend) -> KnowledgeGraphData:
        """
        Enriches a trend with entities and relationships extracted from it.
        Stores them in the vector database and relational database, then returns the context pack.
        """
        logger.info(f"Agent 3: Starting Knowledge Graph Enrichment for trend: '{trend.title}'...")

        kg_raw_data = await self._extract_entities_and_relations(trend)
        trend_id = trend.trend_id

        # Map to Pydantic objects
        entities = [
            KGEntity(
                name=ent.get("name", ""),
                type=ent.get("type", "Product"),
                description=ent.get("description", "")
            )
            for ent in kg_raw_data.get("related_entities", [])
            if ent.get("name")
        ]

        relations = [
            KGRelation(
                source=rel.get("source", ""),
                target=rel.get("target", ""),
                type=rel.get("type", "integrates_with")
            )
            for rel in kg_raw_data.get("relations", [])
            if rel.get("source") and rel.get("target")
        ]

        related_topics = kg_raw_data.get("related_topics", [])

        kg_data = KnowledgeGraphData(
            trend_id=trend_id,
            related_entities=entities,
            relations=relations,
            related_topics=related_topics
        )

        # 1. Save to relational DB
        await db_manager.save_kg_data(kg_data.model_dump())

        # 2. Save to vector DB (Qdrant)
        await vector_db.initialize_collection()
        for ent in entities:
            await vector_db.upsert_entity(
                name=ent.name,
                entity_type=ent.type,
                description=ent.description or "",
                trend_id=trend_id
            )

        # 3. Save to file system
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"kg_enrichment_{trend_id}_{timestamp}.json"
        with open(filepath, "w") as f:
            json.dump(kg_data.model_dump(), f, indent=2)

        logger.info(f"Enriched trend with {len(entities)} entities and {len(relations)} relations.")
        return kg_data

    async def _extract_entities_and_relations(self, trend: Trend) -> Dict[str, Any]:
        """Queries LLM to parse and extract entities/relations from the trend data."""
        # Baseline fallback
        fallback_data = {
            "related_entities": [
                {"name": trend.title, "type": "Product", "description": trend.description}
            ],
            "relations": [],
            "related_topics": ["Artificial Intelligence", "Tech Trends"]
        }

        if not settings.GEMINI_API_KEY and not settings.USE_LOCAL_LLM:
            logger.warning("No LLM configured. Returning fallback KG data.")
            return fallback_data

        prompt_template = ChatPromptTemplate.from_template(
            "You are a knowledge graph agent specializing in technology networks.\n"
            "Given the following trending topic details, extract key entities, relationships, and general topics.\n\n"
            "Trend Title: {title}\n"
            "Description: {description}\n"
            "Metadata: {metrics}\n\n"
            "Extract entities matching these types: Company, Framework, Research Paper, Founder, Product.\n"
            "Extract relationships matching these types: created_by, competes_with, inspired_by, integrates_with.\n\n"
            "Respond ONLY with a valid JSON matching this schema:\n"
            "{{\n"
            "  \"related_entities\": [\n"
            "    {{\"name\": \"Entity Name\", \"type\": \"Company|Framework|Research Paper|Founder|Product\", \"description\": \"Brief details\"}}\n"
            "  ],\n"
            "  \"relations\": [\n"
            "    {{\"source\": \"Source Entity\", \"target\": \"Target Entity\", \"type\": \"created_by|competes_with|inspired_by|integrates_with\"}}\n"
            "  ],\n"
            "  \"related_topics\": [\"Topic1\", \"Topic2\"]\n"
            "}}\n"
            "Do not output markdown fences or additional explanation."
        )

        try:
            llm = get_llm(temperature=0.1, json_mode=True)
            prompt = prompt_template.format_messages(
                title=trend.title,
                description=trend.description,
                metrics=json.dumps(trend.metrics)
            )
            response = await llm.ainvoke(prompt)
            
            text = response.content
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
                
            return json.loads(text.strip())
        except Exception as e:
            logger.warning(f"LLM KG extraction failed ({e}). Returning fallback KG data.")
            return fallback_data

kg_agent = KGAgent()
