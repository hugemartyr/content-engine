import json
from typing import List, Dict, Any, Optional
from sqlalchemy import Column, String, Float, Integer, ForeignKey, JSON
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.future import select

from core.settings import settings
from core.logging.logger import logger

Base = declarative_base()

# --- SQLAlchemy Models ---

class TrendModel(Base):
    __tablename__ = "trends"
    trend_id = Column(String, primary_key=True)
    source = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    url = Column(String, nullable=True)
    metrics = Column(JSON, default=dict)

    # Relationships
    score = relationship("TrendScoreModel", back_populates="trend", uselist=False, cascade="all, delete-orphan")
    entities = relationship("KGEntityModel", back_populates="trend", cascade="all, delete-orphan")
    relations = relationship("KGRelationModel", back_populates="trend", cascade="all, delete-orphan")
    idea = relationship("IdeaModel", back_populates="trend", uselist=False, cascade="all, delete-orphan")
    script = relationship("ScriptModel", back_populates="trend", uselist=False, cascade="all, delete-orphan")
    scenes = relationship("SceneModel", back_populates="trend", cascade="all, delete-orphan")
    assets = relationship("AssetModel", back_populates="trend", cascade="all, delete-orphan")
    timeline = relationship("TimelineModel", back_populates="trend", uselist=False, cascade="all, delete-orphan")


class TrendScoreModel(Base):
    __tablename__ = "trend_scores"
    trend_id = Column(String, ForeignKey("trends.trend_id"), primary_key=True)
    score = Column(Float, nullable=False)
    breakdown = Column(JSON, nullable=False)

    trend = relationship("TrendModel", back_populates="score")


class KGEntityModel(Base):
    __tablename__ = "kg_entities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trend_id = Column(String, ForeignKey("trends.trend_id"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # Company, Framework, Research Paper, Founder, Product
    description = Column(String, nullable=True)

    trend = relationship("TrendModel", back_populates="entities")


class KGRelationModel(Base):
    __tablename__ = "kg_relations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trend_id = Column(String, ForeignKey("trends.trend_id"), nullable=False)
    source = Column(String, nullable=False)
    target = Column(String, nullable=False)
    type = Column(String, nullable=False)  # created_by, competes_with, inspired_by, integrates_with

    trend = relationship("TrendModel", back_populates="relations")


class IdeaModel(Base):
    __tablename__ = "ideas"
    trend_id = Column(String, ForeignKey("trends.trend_id"), primary_key=True)
    ideas = Column(JSON, nullable=False)  # List of strings

    trend = relationship("TrendModel", back_populates="idea")


class ScriptModel(Base):
    __tablename__ = "scripts"
    trend_id = Column(String, ForeignKey("trends.trend_id"), primary_key=True)
    hook = Column(String, nullable=False)
    body = Column(String, nullable=False)
    cta = Column(String, nullable=False)

    trend = relationship("TrendModel", back_populates="script")


class SceneModel(Base):
    __tablename__ = "scenes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trend_id = Column(String, ForeignKey("trends.trend_id"), nullable=False)
    scene = Column(Integer, nullable=False)
    duration = Column(Float, nullable=False)
    visual = Column(String, nullable=False)
    asset_type = Column(String, nullable=False)
    retrieval_hints = Column(String, nullable=False)

    trend = relationship("TrendModel", back_populates="scenes")


class AssetModel(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trend_id = Column(String, ForeignKey("trends.trend_id"), nullable=False)
    scene = Column(Integer, nullable=False)
    asset_url = Column(String, nullable=False)
    local_path = Column(String, nullable=True)
    license = Column(String, default="free")
    source = Column(String, nullable=False)
    score = Column(Float, nullable=True)

    trend = relationship("TrendModel", back_populates="assets")


class TimelineModel(Base):
    __tablename__ = "timelines"
    trend_id = Column(String, ForeignKey("trends.trend_id"), primary_key=True)
    title = Column(String, nullable=False)
    bgm = Column(String, nullable=False)
    timeline = Column(JSON, nullable=False)  # List of timeline items

    trend = relationship("TrendModel", back_populates="timeline")


# --- Database Connection and Manager ---

class DatabaseManager:
    def __init__(self):
        self.db_url = settings.get_db_url()
        self.engine = create_async_engine(self.db_url, echo=False)
        self.async_session = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        logger.info(f"DatabaseManager initialized for URL: {self.db_url}")

    async def initialize_db(self):
        """Creates tables if they do not exist."""
        logger.info("Initializing relational database schema...")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema initialized successfully.")

    async def save_trends(self, trends: List[Dict[str, Any]]):
        async with self.async_session() as session:
            async with session.begin():
                for trend_data in trends:
                    # Update or insert
                    stmt = select(TrendModel).where(TrendModel.trend_id == trend_data["trend_id"])
                    result = await session.execute(stmt)
                    existing = result.scalar_one_or_none()
                    if existing:
                        existing.source = trend_data["source"]
                        existing.title = trend_data["title"]
                        existing.description = trend_data["description"]
                        existing.url = trend_data["url"]
                        existing.metrics = trend_data["metrics"]
                    else:
                        new_trend = TrendModel(**trend_data)
                        session.add(new_trend)
            await session.commit()

    async def save_score(self, score_data: Dict[str, Any]):
        async with self.async_session() as session:
            async with session.begin():
                stmt = select(TrendScoreModel).where(TrendScoreModel.trend_id == score_data["trend_id"])
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    existing.score = score_data["score"]
                    existing.breakdown = score_data["breakdown"]
                else:
                    new_score = TrendScoreModel(**score_data)
                    session.add(new_score)
            await session.commit()

    async def save_kg_data(self, kg_data: Dict[str, Any]):
        trend_id = kg_data["trend_id"]
        async with self.async_session() as session:
            async with session.begin():
                # Delete existing entities/relations for this trend
                del_entities_stmt = select(KGEntityModel).where(KGEntityModel.trend_id == trend_id)
                entities_result = await session.execute(del_entities_stmt)
                for ent in entities_result.scalars():
                    await session.delete(ent)

                del_relations_stmt = select(KGRelationModel).where(KGRelationModel.trend_id == trend_id)
                relations_result = await session.execute(del_relations_stmt)
                for rel in relations_result.scalars():
                    await session.delete(rel)

                # Add new
                for ent in kg_data.get("related_entities", []):
                    session.add(KGEntityModel(trend_id=trend_id, name=ent["name"], type=ent["type"], description=ent.get("description")))
                for rel in kg_data.get("relations", []):
                    session.add(KGRelationModel(trend_id=trend_id, source=rel["source"], target=rel["target"], type=rel["type"]))
            await session.commit()

    async def save_ideas(self, ideas_data: Dict[str, Any]):
        async with self.async_session() as session:
            async with session.begin():
                stmt = select(IdeaModel).where(IdeaModel.trend_id == ideas_data["trend_id"])
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    existing.ideas = ideas_data["ideas"]
                else:
                    new_idea = IdeaModel(**ideas_data)
                    session.add(new_idea)
            await session.commit()

    async def save_script(self, script_data: Dict[str, Any]):
        async with self.async_session() as session:
            async with session.begin():
                stmt = select(ScriptModel).where(ScriptModel.trend_id == script_data["trend_id"])
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    existing.hook = script_data["hook"]
                    existing.body = script_data["body"]
                    existing.cta = script_data["cta"]
                else:
                    new_script = ScriptModel(**script_data)
                    session.add(new_script)
            await session.commit()

    async def save_scenes(self, trend_id: str, scenes: List[Dict[str, Any]]):
        async with self.async_session() as session:
            async with session.begin():
                # Delete existing scenes
                stmt = select(SceneModel).where(SceneModel.trend_id == trend_id)
                result = await session.execute(stmt)
                for scene_obj in result.scalars():
                    await session.delete(scene_obj)

                # Add new scenes
                for s in scenes:
                    session.add(SceneModel(
                        trend_id=trend_id,
                        scene=s["scene"],
                        duration=s["duration"],
                        visual=s["visual"],
                        asset_type=s["asset_type"],
                        retrieval_hints=s["retrieval_hints"]
                    ))
            await session.commit()

    async def save_assets(self, trend_id: str, assets: List[Dict[str, Any]]):
        async with self.async_session() as session:
            async with session.begin():
                # Delete existing assets
                stmt = select(AssetModel).where(AssetModel.trend_id == trend_id)
                result = await session.execute(stmt)
                for asset_obj in result.scalars():
                    await session.delete(asset_obj)

                # Add new assets
                for a in assets:
                    session.add(AssetModel(
                        trend_id=trend_id,
                        scene=a["scene"],
                        asset_url=a["asset_url"],
                        local_path=a.get("local_path"),
                        license=a.get("license", "free"),
                        source=a["source"],
                        score=a.get("score")
                    ))
            await session.commit()

    async def save_timeline(self, timeline_data: Dict[str, Any]):
        async with self.async_session() as session:
            async with session.begin():
                stmt = select(TimelineModel).where(TimelineModel.trend_id == timeline_data["trend_id"])
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    existing.title = timeline_data["title"]
                    existing.bgm = timeline_data["bgm"]
                    existing.timeline = timeline_data["timeline"]
                else:
                    new_timeline = TimelineModel(**timeline_data)
                    session.add(new_timeline)
            await session.commit()

    async def load_pipeline_state(self, trend_id: str) -> Dict[str, Any]:
        """Loads all persisted components of a pipeline run for resumability."""
        state = {"trend_id": trend_id}
        async with self.async_session() as session:
            # 1. Trend
            trend_stmt = select(TrendModel).where(TrendModel.trend_id == trend_id)
            trend_res = await session.execute(trend_stmt)
            trend = trend_res.scalar_one_or_none()
            if not trend:
                return {}
            state["trend"] = {
                "trend_id": trend.trend_id,
                "source": trend.source,
                "title": trend.title,
                "description": trend.description,
                "url": trend.url,
                "metrics": trend.metrics
            }

            # 2. Score
            score_stmt = select(TrendScoreModel).where(TrendScoreModel.trend_id == trend_id)
            score_res = await session.execute(score_stmt)
            score = score_res.scalar_one_or_none()
            if score:
                state["score"] = {"trend_id": score.trend_id, "score": score.score, "breakdown": score.breakdown}

            # 3. Knowledge Graph
            ent_stmt = select(KGEntityModel).where(KGEntityModel.trend_id == trend_id)
            rel_stmt = select(KGRelationModel).where(KGRelationModel.trend_id == trend_id)
            ents = (await session.execute(ent_stmt)).scalars().all()
            rels = (await session.execute(rel_stmt)).scalars().all()
            state["kg"] = {
                "trend_id": trend_id,
                "related_entities": [{"name": e.name, "type": e.type, "description": e.description} for e in ents],
                "relations": [{"source": r.source, "target": r.target, "type": r.type} for r in rels]
            }

            # 4. Ideas
            idea_stmt = select(IdeaModel).where(IdeaModel.trend_id == trend_id)
            idea = (await session.execute(idea_stmt)).scalar_one_or_none()
            if idea:
                state["ideas"] = {"trend_id": trend_id, "ideas": idea.ideas}

            # 5. Script
            script_stmt = select(ScriptModel).where(ScriptModel.trend_id == trend_id)
            script = (await session.execute(script_stmt)).scalar_one_or_none()
            if script:
                state["script"] = {"hook": script.hook, "body": script.body, "cta": script.cta}

            # 6. Scenes
            scene_stmt = select(SceneModel).where(SceneModel.trend_id == trend_id).order_by(SceneModel.scene)
            scenes = (await session.execute(scene_stmt)).scalars().all()
            state["scenes"] = [{
                "scene": s.scene,
                "duration": s.duration,
                "visual": s.visual,
                "asset_type": s.asset_type,
                "retrieval_hints": s.retrieval_hints
            } for s in scenes]

            # 7. Assets
            asset_stmt = select(AssetModel).where(AssetModel.trend_id == trend_id)
            assets = (await session.execute(asset_stmt)).scalars().all()
            state["assets"] = [{
                "scene": a.scene,
                "asset_url": a.asset_url,
                "local_path": a.local_path,
                "license": a.license,
                "source": a.source,
                "score": a.score
            } for a in assets]

            # 8. Timeline
            timeline_stmt = select(TimelineModel).where(TimelineModel.trend_id == trend_id)
            timeline = (await session.execute(timeline_stmt)).scalar_one_or_none()
            if timeline:
                state["timeline"] = {
                    "title": timeline.title,
                    "bgm": timeline.bgm,
                    "timeline": timeline.timeline
                }

        return state

db_manager = DatabaseManager()
