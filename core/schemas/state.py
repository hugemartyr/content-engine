from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# --- Stage 1: Trend Discovery ---
class Trend(BaseModel):
    trend_id: str = Field(..., description="Unique ID for the trend")
    source: str = Field(..., description="Source of trend: github, reddit, youtube, newsletter")
    title: str = Field(..., description="Title of the trending item")
    description: str = Field(..., description="Brief summary or description")
    url: str = Field(..., description="Link to the source")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Source specific metrics like stars, views, upvotes")

class TrendDiscoveryOutput(BaseModel):
    trends: List[Trend] = Field(default_factory=list, description="List of discovered trends")

# --- Stage 2: Trend Scoring ---
class ScoreBreakdown(BaseModel):
    freshness: float = Field(..., description="Freshness score (0-10)")
    virality: float = Field(..., description="Virality score (0-10)")
    novelty: float = Field(..., description="Novelty score (0-10)")
    visual_potential: float = Field(..., description="Visual potential score (0-10)")
    technical_depth: float = Field(..., description="Technical depth score (0-10)")

class TrendScore(BaseModel):
    trend_id: str = Field(..., description="Unique ID for the trend")
    score: float = Field(..., description="Overall calculated score (0-10)")
    breakdown: ScoreBreakdown = Field(..., description="Breakdown of individual scoring weights")

# --- Stage 3: Knowledge Graph Agent ---
class KGEntity(BaseModel):
    name: str = Field(..., description="Name of entity, e.g. Google, Gemini")
    type: str = Field(..., description="Type of entity: Company, Framework, Research Paper, Founder, Product")
    description: Optional[str] = Field(None, description="Brief context about the entity")

class KGRelation(BaseModel):
    source: str = Field(..., description="Source entity name")
    target: str = Field(..., description="Target entity name")
    type: str = Field(..., description="Relation type: created_by, competes_with, inspired_by, integrates_with")

class KnowledgeGraphData(BaseModel):
    trend_id: str = Field(..., description="Unique ID for the trend")
    related_entities: List[KGEntity] = Field(default_factory=list, description="Entities found in this trend")
    relations: List[KGRelation] = Field(default_factory=list, description="Relations between entities")
    related_topics: List[str] = Field(default_factory=list, description="General semantic tags/topics")

# --- Stage 4: Idea Agent ---
class IdeaOutput(BaseModel):
    trend_id: str = Field(..., description="Unique ID for the trend")
    ideas: List[str] = Field(..., description="10 to 20 content angles/ideas generated from the trend")

# --- Stage 5: Script Agent ---
class Script(BaseModel):
    hook: str = Field(..., description="0-3s hook to grab attention")
    body: str = Field(..., description="3-50s explanation containing context, detail, and why it matters")
    cta: str = Field(..., description="50-60s call to action")

# --- Stage 6: Scene Planner Agent ---
class Scene(BaseModel):
    scene: int = Field(..., description="Scene index (1-indexed)")
    duration: float = Field(..., description="Duration in seconds")
    visual: str = Field(..., description="Visual description of what to show on screen")
    asset_type: str = Field(..., description="Allowed types: SCREENSHOT, STOCK, AI_BROLL, LOGO, CHART, UI_CAPTURE")
    retrieval_hints: str = Field(..., description="Keywords or instructions for retrieval")

# --- Stage 7 & 8: Asset Retrieval & Ranking ---
class Asset(BaseModel):
    scene: int = Field(..., description="Scene index this asset matches")
    asset_url: str = Field(..., description="URL of the asset")
    local_path: Optional[str] = Field(None, description="Local path to the downloaded asset")
    license: str = Field(default="free", description="License of the asset")
    source: str = Field(..., description="Source of asset: pexels, pixabay, github, local_fallback")
    score: Optional[float] = Field(None, description="Visual relevance rank score (0.0 to 1.0)")
    tags: List[str] = Field(default_factory=list, description="Associated semantic tags/description for the asset")

class RankedAssetsOutput(BaseModel):
    assets: List[Asset] = Field(..., description="Selected assets per scene after ranking")

# --- Stage 9: Timeline Builder Agent ---
class TimelineItem(BaseModel):
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    asset: str = Field(..., description="Filename/local path to the asset")
    caption: str = Field(..., description="Overlay caption to display")

class Timeline(BaseModel):
    title: str = Field(..., description="Title of the reel")
    bgm: str = Field(..., description="Filename of BGM music track, e.g. ambient_tech_mellow.mp3")
    timeline: List[TimelineItem] = Field(..., description="Chronological timeline of scenes")

# --- LangGraph Global State ---
class AgentState(BaseModel):
    topic: str = Field(..., description="Topic of the run")
    trends: List[Trend] = Field(default_factory=list, description="Raw trends discovered")
    scores: List[TrendScore] = Field(default_factory=list, description="Scoring breakdown of trends")
    top_trend: Optional[Trend] = Field(None, description="Selected top trend")
    kg_enrichment: Optional[KnowledgeGraphData] = Field(None, description="Enriched knowledge graph entities & relationships")
    ideas: Optional[IdeaOutput] = Field(None, description="Generated ideas/angles")
    selected_idea: Optional[str] = Field(None, description="Selected angle for script")
    idea_slug: Optional[str] = Field(None, description="Sanitized folder name slug for the selected idea")
    script: Optional[Script] = Field(None, description="Generated script")
    scenes: List[Scene] = Field(default_factory=list, description="Generated scene plans")
    assets: List[Asset] = Field(default_factory=list, description="All retrieved assets (candidates)")
    ranked_assets: List[Asset] = Field(default_factory=list, description="Ranked and selected assets (one per scene)")
    timeline: Optional[Timeline] = Field(None, description="Final timeline JSON")
    error: Optional[str] = Field(None, description="Error trace if execution failed")
