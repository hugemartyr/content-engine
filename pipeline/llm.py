import os
import json
import hashlib
import time
import sys
from pathlib import Path
from google import genai
from google.genai import types
from .schemas import ReelStoryboard

# Query Gemini to generate Reel Storyboard
def extract_storyboard_llm(prompt, force=False):
    cache_path = Path("outputs/reel_system_prompt/assets/storyboard.json")
    prompt_hash = hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()
    
    if not force and cache_path.exists():
        try:
            with open(cache_path, "r") as f:
                cached_data = json.load(f)
            if cached_data.get("prompt_hash") == prompt_hash:
                print("Loading storyboard from local cache...")
                storyboard_fields = cached_data.get("storyboard")
                if storyboard_fields:
                    return ReelStoryboard(**storyboard_fields)
        except Exception as e:
            print(f"Error loading cached storyboard: {e}")
            
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("Error: GEMINI_API_KEY not found in environment.")
        sys.exit(1)
        
    client = genai.Client()
    
    print("Asking Gemini to generate structured Reel storyboard...")
    system_instruction = """
    You are an expert short-form video editor and content producer.
    Your job is to analyze a raw video concept text/prompt and output a structured JSON storyboard optimized for dynamic pacing and high retention.
    
    Rules:
    1. Video cuts must happen every 2 to 6 seconds. No stock clip should play for longer than 7 seconds. Split long narration blocks into sub-segments.
    2. Write voiceover script with ellipses (...) and sentence structures to direct ElevenLabs pauses.
    3. Specify layout types: 'hook_black' (start), 'cta_black' (end), 'stock_video', 'split_screen', 'reuse_video'.
    4. Provide clear Pexels search queries and fallbacks.
    5. Specify BGM mood and beat-switch cross-fade point.
    """
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"Analyze this prompt and generate a ReelStoryboard:\n\n{prompt}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=ReelStoryboard,
                    temperature=0.2
                )
            )
            storyboard_data = json.loads(response.text)
            storyboard = ReelStoryboard(**storyboard_data)
            print("Successfully generated storyboard with Gemini.")
            
            # Save to cache
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump({
                    "prompt_hash": prompt_hash,
                    "storyboard": storyboard.model_dump()
                }, f, indent=2)
            print(f"Storyboard saved to cache at {cache_path}")
            
            return storyboard
        except Exception as e:
            print(f"Error generating storyboard with Gemini (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                sleep_time = 2 ** attempt
                print(f"Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
            else:
                sys.exit(1)
