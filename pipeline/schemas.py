from pydantic import BaseModel, Field
from typing import List, Optional

# Define Structured Storyboard Pydantic Schema
class SceneItem(BaseModel):
    id: str = Field(description="Unique scene ID (e.g., '1', '2a', '2b', '3')")
    type: str = Field(description="Scene type: 'hook_black', 'cta_black', 'stock_video', 'split_screen', 'reuse_video'")
    query: Optional[str] = Field(None, description="Pexels query for stock video (e.g., 'frustrated typing laptop')")
    fallbacks: Optional[List[str]] = Field(None, description="Fallback queries for Pexels search")
    left_query: Optional[str] = Field(None, description="Left side query for split_screen type")
    left_fallbacks: Optional[List[str]] = Field(None, description="Left side fallbacks for split_screen type")
    right_query: Optional[str] = Field(None, description="Right side query for split_screen type")
    right_fallbacks: Optional[List[str]] = Field(None, description="Right side fallbacks for split_screen type")
    reuse_scene_id: Optional[str] = Field(None, description="Scene ID to reuse (for reuse_video type)")
    text: Optional[str] = Field(None, description="Text overlays to put on slides (for hook_black, cta_black)")
    est_duration: float = Field(description="Estimated duration of this scene in seconds based on reading speed")

class ReelStoryboard(BaseModel):
    voiceover_text: str = Field(description="Exact script text for ElevenLabs speech generation, containing punctuation, commas, ellipses to shape pacing.")
    voice_speed: float = Field(1.15, description="ElevenLabs speed multiplier (default 1.15)")
    bgm_query: str = Field(description="Desired BGM mood/style (e.g., 'lofi focus', 'ambient tech')")
    bgm_volume: float = Field(0.08, description="BGM volume level (default 0.08)")
    bgm_beat_switch_time: Optional[float] = Field(None, description="Timestamp (seconds) where BGM 2 (Solution theme) cross-fades in")
    scenes: List[SceneItem] = Field(description="List of scenes in chronological order")
