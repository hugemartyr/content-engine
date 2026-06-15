import os
import sys
import json
import httpx
import asyncio
import subprocess
import wave
import argparse
import textwrap
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import numpy as np
from pydantic import BaseModel, Field
from typing import List, Optional

# Load environment variables
load_dotenv()

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

# Import moviepy
try:
    from moviepy import (
        VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip, ColorClip, CompositeAudioClip
    )
    from moviepy.video.fx import Loop
    from moviepy.audio.fx import MultiplyVolume, AudioFadeIn, AudioFadeOut
except ImportError as e:
    print("Error: 'moviepy' is not installed in the active environment.")
    print(e)
    sys.exit(1)

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

# Default prompt for the "System Prompt" Reel
DEFAULT_PROMPT = """
Topic: Most people using AI are making themselves slower - here's why
Format: Voiceover + text overlays + stock footage. No face shown.
Length: 38 - 42 seconds
Platform: Instagram Reels (9:16, 1080×1920px)
Voice: ElevenLabs - Callum, calm, confident, slightly dry. Not hype. Not breathless.
Goal: Maximum saves. People save this to come back and build their system prompt.
CTA in video: None. Zero. The pinned comment handles it.
THE HOOK - WHY THIS SPECIFIC LINE
Hook line (voiceover + on screen simultaneously):
 "Most people using AI are making themselves slower."

On screen treatment for the hook:
 — Black screen. White text only. Large. Bold. Centered.
 — Text appears word by word in sync with voiceover -not all at once.
 — "Most people" appears → 0.2 second pause → "using AI" → 0.2 second pause → "are making themselves slower" lands all at once.
 — No music at this exact moment. Silence makes the statement land harder.
 — Music fades in at second 1.8 after the hook has landed.
FULL SCRIPT - WORD FOR WORD
0:00–0:03 — Most people using AI... are making themselves slower.
0:03–0:06 — They type a vague prompt. Get a mediocre answer. Edit it for twenty minutes. And call that productivity.
0:06–0:09 — Here is the actual problem.
0:09–0:15 — ChatGPT, Claude, Gemini — none of them know anything about you. Your job. Your writing style. What you actually need.
0:15–0:17 — So every single conversation starts from zero.
0:17–0:22 — The people getting real output from AI? They have built what is called a system prompt. A permanent set of instructions the AI reads before you type anything.
0:22–0:28 — Your role. Your tone. What to avoid. What format you want answers in. Your writing style. All of it. Written once.
0:28–0:31 — I built mine six months ago. I have not edited a single AI output since.
0:31–0:34 — Most people never build one.
0:34–0:40 — Which means they do the same setup work. Every. Single. Session. That is not AI saving you time. That is AI costing you time.
0:40–0:42 — Build the prompt once.
"""

# Helper to create bold centered text slides on solid black background
def create_text_slide(text, filename, width=1080, height=1920, font_size=72, wrap_width=20):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    
    font = None
    macos_bold_fonts = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFProBold.ttf"
    ]
    for path in macos_bold_fonts:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except Exception:
                continue
                
    if font is None:
        font = ImageFont.load_default()
        
    lines = textwrap.wrap(text, width=wrap_width)
    line_spacing = 20
    line_heights = []
    line_widths = []
    
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
        except AttributeError:
            w, h = draw.textsize(line, font=font)
        line_widths.append(w)
        line_heights.append(h)
        
    total_height = sum(line_heights) + line_spacing * (len(lines) - 1)
    current_y = (height - total_height) // 2
    
    for i, line in enumerate(lines):
        line_w = line_widths[i]
        x = (width - line_w) // 2
        draw.text((x, current_y), line, font=font, fill=(255, 255, 255, 255))
        current_y += line_heights[i] + line_spacing
        
    img.save(filename)
    print(f"Generated text slide image: {filename}")

# Programmatically search and download a vertical video from Pexels
async def download_pexels_video(api_key, query, fallback_queries, filename, target_dir):
    headers = {"Authorization": api_key}
    url = "https://api.pexels.com/videos/search"
    queries = [query] + (fallback_queries or [])
    
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / filename
    
    # Check if the file exists and is valid
    if filepath.exists():
        if filepath.stat().st_size < 100000:  # < 100KB is likely corrupted/mock
            print(f"File {filename} is too small or incomplete. Deleting for redownload.")
            filepath.unlink()
        else:
            print(f"Asset already downloaded: {filename}")
            return str(filepath)
        
    for q in queries:
        print(f"Searching Pexels for: '{q}'...")
        params = {
            "query": q,
            "per_page": 5,
            "orientation": "portrait"
        }
        
        try:
            async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    videos = data.get("videos", [])
                    
                    if videos:
                        for video in videos:
                            video_files = video.get("video_files", [])
                            target_url = None
                            
                            # Preference 1: HD vertical video
                            for vf in video_files:
                                w = vf.get("width", 0)
                                h = vf.get("height", 0)
                                if w < h and h >= 720:
                                    target_url = vf.get("link")
                                    print(f"  Found vertical HD video ({w}x{h}) for query: '{q}'")
                                    break
                                    
                            # Preference 2: Any vertical video
                            if not target_url:
                                for vf in video_files:
                                    w = vf.get("width", 0)
                                    h = vf.get("height", 0)
                                    if w < h:
                                        target_url = vf.get("link")
                                        print(f"  Found vertical video ({w}x{h}) for query: '{q}'")
                                        break
                                        
                            # Preference 3: HD horizontal video (we will crop to vertical)
                            if not target_url:
                                for vf in video_files:
                                    w = vf.get("width", 0)
                                    h = vf.get("height", 0)
                                    if h >= 720:
                                        target_url = vf.get("link")
                                        print(f"  Found horizontal HD video ({w}x{h}) to crop for query: '{q}'")
                                        break
                                        
                            if target_url:
                                print(f"  Downloading video asset to {filepath}...")
                                dl_response = await client.get(target_url, follow_redirects=True, timeout=60.0)
                                if dl_response.status_code == 200:
                                    with open(filepath, "wb") as f:
                                        f.write(dl_response.content)
                                    print(f"  Successfully saved {filename} ({len(dl_response.content)} bytes)")
                                    return str(filepath)
                                else:
                                    print(f"  Failed to download from link, status: {dl_response.status_code}")
        except Exception as e:
            print(f"  Error searching/downloading for query '{q}': {e}")
            
    print(f"Warning: Could not download video for query '{query}'")
    return None

# Download royalty-free lofi background music
async def download_lofi_bgm(target_dir):
    bgm_url = "https://raw.githubusercontent.com/jungcookgf/valentines-day/main/cute-lofi.mp3"
    filepath = target_dir / "bgm.mp3"
    if filepath.exists() and filepath.stat().st_size > 10000:
        print("BGM already exists.")
        return str(filepath)
        
    print(f"Downloading royalty-free background music from {bgm_url}...")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(bgm_url, follow_redirects=True)
            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                print(f"Successfully saved background music to {filepath}")
                return str(filepath)
            else:
                print(f"Failed to download BGM, status: {response.status_code}")
    except Exception as e:
        print(f"Error downloading background music: {e}")
    return None

# Call ElevenLabs API for Voiceover Synthesis
async def generate_voiceover_tts(text, speed_multiplier, output_path):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("Error: ELEVENLABS_API_KEY not found in environment.")
        return False
        
    voice_id = "N2lVS1w4EtoT3dr4eOWO"  # Callum
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.75,
            "similarity_boost": 0.80,
            "style": 0.20,
            "speed": speed_multiplier
        }
    }
    
    print(f"Synthesizing voiceover with ElevenLabs (speed={speed_multiplier})...")
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                print(f"Voiceover successfully saved to {output_path}")
                return True
            else:
                print(f"ElevenLabs API error: {response.status_code}")
                print(response.text)
                return False
    except Exception as e:
        print(f"Error communicating with ElevenLabs: {e}")
        return False

# Convert MP3 to WAV using FFmpeg
def convert_mp3_to_wav(mp3_path, wav_path):
    print(f"Converting {mp3_path} to {wav_path} using FFmpeg...")
    try:
        cmd = ["ffmpeg", "-y", "-i", str(mp3_path), "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1", str(wav_path)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        print("Conversion completed successfully.")
        return True
    except Exception as e:
        print(f"Error converting audio to WAV: {e}")
        return False

# Analyze WAV file to detect pause midpoints
def detect_pause_midpoints(wav_path):
    print(f"Analyzing pause midpoints in WAV file {wav_path}...")
    try:
        with wave.open(str(wav_path), 'rb') as w:
            params = w.getparams()
            nchannels = params.nchannels
            framerate = params.framerate
            nframes = params.nframes
            
            frames = w.readframes(nframes)
            data = np.frombuffer(frames, dtype=np.int16)
            
        if nchannels > 1:
            data = data.reshape(-1, nchannels).mean(axis=1)
            
        duration = len(data) / framerate
        print(f"Loaded audio: {len(data)} samples at {framerate}Hz ({duration:.2f}s duration)")
        
        amplitude = np.abs(data)
        window_size = int(framerate * 0.2)  # 200ms window
        smoothed = np.convolve(amplitude, np.ones(window_size)/window_size, mode='same')
        
        # 2% of the 95th percentile amplitude as silence threshold
        threshold = 0.02 * np.percentile(smoothed, 95)
        is_silent = smoothed < threshold
        
        silence_starts = []
        silence_ends = []
        in_silence = False
        
        for i, val in enumerate(is_silent):
            if val and not in_silence:
                silence_starts.append(i)
                in_silence = True
            elif not val and in_silence:
                silence_ends.append(i)
                in_silence = False
                
        if in_silence:
            silence_ends.append(len(is_silent))
            
        min_silence_len = int(framerate * 0.3)  # 300ms
        pauses = []
        for start, end in zip(silence_starts, silence_ends):
            if end - start >= min_silence_len:
                pauses.append(((start / framerate) + (end / framerate)) / 2)
                
        print(f"Detected {len(pauses)} raw pauses: {pauses}")
        return pauses, duration
    except Exception as e:
        print(f"Error detecting pause midpoints: {e}")
        return [], 0.0

# Align scene estimated durations to actual pause midpoints
def align_scene_durations(scenes, pause_mids, total_duration):
    print("Aligning scene durations with detected audio pauses...")
    
    # The last scene is the CTA slide (cta_black)
    # We want it to play for a fixed short duration at the end (e.g., 2.0s)
    cta_duration = 2.0
    if len(scenes) > 1 and scenes[-1].type == "cta_black":
        cta_duration = scenes[-1].est_duration if scenes[-1].est_duration > 0.5 else 2.0
        
    # Time available for all preceding scenes
    available_time = total_duration - cta_duration
    
    # Non-CTA scenes
    non_cta_scenes = scenes[:-1] if len(scenes) > 1 else scenes
    est_durations = [s.est_duration for s in non_cta_scenes]
    sum_est = sum(est_durations)
    
    if sum_est > 0:
        # Scale estimated durations to fill available_time
        scale_factor = available_time / sum_est
        scaled_durations = [d * scale_factor for d in est_durations]
        print(f"Original estimates sum: {sum_est:.2f}s, Available time: {available_time:.2f}s, Scale factor: {scale_factor:.3f}")
    else:
        scaled_durations = [available_time / len(est_durations)] * len(est_durations)
        
    # Calculate scaled cuts
    scaled_cuts = []
    current = 0.0
    for dur in scaled_durations:
        current += dur
        scaled_cuts.append(current)
        
    # Snap each cut to the nearest detected pause midpoint
    aligned_cuts = []
    used_pauses = set()
    
    # Snap intermediate cuts
    for est in scaled_cuts[:-1]:
        candidates = [p for p in pause_mids if p not in used_pauses]
        if not candidates:
            aligned_cuts.append(est)
            continue
            
        closest = min(candidates, key=lambda p: abs(p - est))
        # Snap if closest pause is within 4.0s of scaled estimate
        if abs(closest - est) <= 4.0:
            aligned_cuts.append(closest)
            used_pauses.add(closest)
        else:
            aligned_cuts.append(est)
            
    # The final cut before the CTA slide should be exactly the last pause midpoint
    # so that the visual videos run until the speaker stops talking
    last_pause = max(pause_mids) if pause_mids else available_time
    aligned_cuts.append(last_pause)
    
    aligned_cuts = sorted(list(set(aligned_cuts)))
    
    aligned_durations = []
    prev = 0.0
    for cut in aligned_cuts:
        aligned_durations.append(cut - prev)
        prev = cut
    aligned_durations.append(total_duration - prev)
    
    print(f"Aligned scene durations: {aligned_durations}")
    return aligned_durations

# Process video clip: loops or trims, mutes, crops to centered vertical, and applies dynamic zoom
def process_clip_with_zoom(clip_path, duration, target_w=1080, target_h=1920, zoom_ratio=1.10):
    clip = VideoFileClip(clip_path)
    
    if clip.duration < duration:
        clip = clip.with_effects([Loop(duration=duration)])
    else:
        clip = clip.subclipped(0, duration)
        
    clip = clip.without_audio()
    w, h = clip.size
    
    scale_factor = max(target_w / w, target_h / h)
    resize_func = lambda t: scale_factor * (1.0 + (zoom_ratio - 1.0) * (t / duration))
    resized_clip = clip.resized(resize_func)
    
    pos_func = lambda t: (
        int((target_w - w * scale_factor * (1.0 + (zoom_ratio - 1.0) * (t / duration))) / 2),
        int((target_h - h * scale_factor * (1.0 + (zoom_ratio - 1.0) * (t / duration))) / 2)
    )
    
    comp_clip = CompositeVideoClip(
        [resized_clip.with_position(pos_func)],
        size=(target_w, target_h)
    ).with_duration(duration)
    
    return comp_clip

# Query Gemini to generate Reel Storyboard
def extract_storyboard_llm(prompt, force=False):
    import hashlib
    from google import genai
    from google.genai import types
    import time
    
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

async def main():
    parser = argparse.ArgumentParser(description="Unified LLM-driven Video Reel Pipeline")
    parser.add_argument("--prompt", type=str, help="Textual prompt describing the Reel idea, script, and visual layout.")
    parser.add_argument("--prompt-file", type=str, help="Path to a text file containing the prompt.")
    parser.add_argument("--cleanup", action="store_true", default=True, help="Clean up temporary files after rendering.")
    parser.add_argument("--no-cleanup", action="store_false", dest="cleanup", help="Keep temporary files after rendering.")
    parser.add_argument("--force", action="store_true", help="Force a fresh LLM call, ignoring cached storyboard.")
    args = parser.parse_args()
    
    # 1. Determine Prompt
    prompt_text = DEFAULT_PROMPT
    if args.prompt:
        prompt_text = args.prompt
    elif args.prompt_file:
        prompt_path = Path(args.prompt_file)
        if prompt_path.exists():
            prompt_text = prompt_path.read_text()
        else:
            print(f"Error: Prompt file not found at {args.prompt_file}")
            sys.exit(1)
            
    # 2. Extract Storyboard via Gemini
    storyboard = extract_storyboard_llm(prompt_text, force=args.force)
    
    # Create output assets directory
    assets_dir = Path("outputs/reel_system_prompt/assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    # 3. Generate Voiceover TTS
    voiceover_mp3 = assets_dir / "voiceover.mp3"
    voiceover_wav = assets_dir / "voiceover.wav"
    
    # Try ElevenLabs; fallback to using existing files if API fails and file is cached
    tts_success = await generate_voiceover_tts(storyboard.voiceover_text, storyboard.voice_speed, voiceover_mp3)
    if not tts_success:
        if voiceover_mp3.exists() and voiceover_mp3.stat().st_size > 1000:
            print("ElevenLabs API failed. Falling back to cached voiceover.mp3...")
        else:
            print("Error: Failed to synthesize voiceover and no cached voiceover.mp3 found.")
            sys.exit(1)
            
    # 4. Audio Conversion and Pause Analysis
    conv_success = convert_mp3_to_wav(voiceover_mp3, voiceover_wav)
    if not conv_success:
        sys.exit(1)
        
    pause_mids, total_duration = detect_pause_midpoints(voiceover_wav)
    if not pause_mids:
        print("Warning: No pauses detected. Using estimated durations.")
        aligned_durations = [s.est_duration for s in storyboard.scenes]
        total_duration = sum(aligned_durations)
    else:
        aligned_durations = align_scene_durations(storyboard.scenes, pause_mids, total_duration)
        
    # Assign aligned durations back to scenes
    for scene, aligned_dur in zip(storyboard.scenes, aligned_durations):
        scene.est_duration = aligned_dur
        
    # 5. Download BGM and Pexels Videos
    bgm_path = await download_lofi_bgm(assets_dir)
    if not bgm_path:
        print("Error: Could not retrieve BGM.")
        sys.exit(1)
        
    pexels_key = os.getenv("PEXELS_API_KEY")
    if not pexels_key:
        print("Error: PEXELS_API_KEY not found in environment.")
        sys.exit(1)
        
    print("Checking and downloading Pexels stock video assets...")
    dl_tasks = []
    for scene in storyboard.scenes:
        if scene.type == "stock_video":
            filename = f"scene_{scene.id}.mp4"
            dl_tasks.append(download_pexels_video(pexels_key, scene.query, scene.fallbacks, filename, assets_dir))
        elif scene.type == "split_screen":
            filename_l = f"scene_{scene.id}_left.mp4"
            filename_r = f"scene_{scene.id}_right.mp4"
            dl_tasks.append(download_pexels_video(pexels_key, scene.left_query, scene.left_fallbacks, filename_l, assets_dir))
            dl_tasks.append(download_pexels_video(pexels_key, scene.right_query, scene.right_fallbacks, filename_r, assets_dir))
            
    await asyncio.gather(*dl_tasks)
    print("Downloads completed.")
    
    # 6. Generate Slide Images via Pillow
    hook_slides = []
    cta_slide_path = str(assets_dir / "cta_slide.png")
    
    # Generate Hook Slides (if multiple segments, or word-by-word builds)
    # By default, let's create a progressive 3-slide hook for hook_black type
    hook_slide_1 = str(assets_dir / "hook_slide_1.png")
    hook_slide_2 = str(assets_dir / "hook_slide_2.png")
    hook_slide_3 = str(assets_dir / "hook_slide_3.png")
    
    # Look for a scene of type 'hook_black'
    hook_scene = next((s for s in storyboard.scenes if s.type == "hook_black"), None)
    hook_text = hook_scene.text if hook_scene else "Most people using AI are making themselves slower."
    
    # Word by word animation builder
    words = hook_text.split()
    if len(words) >= 4:
        phrase_1 = " ".join(words[:2])
        phrase_2 = " ".join(words[:4])
        phrase_3 = hook_text
    else:
        phrase_1 = words[0] if words else "Most"
        phrase_2 = " ".join(words[:2]) if len(words) > 1 else "Most people"
        phrase_3 = hook_text
        
    create_text_slide(phrase_1, hook_slide_1)
    create_text_slide(phrase_2, hook_slide_2)
    create_text_slide(phrase_3, hook_slide_3)
    
    cta_scene = next((s for s in storyboard.scenes if s.type == "cta_black"), None)
    cta_text = cta_scene.text if cta_scene else "Build the prompt once."
    create_text_slide(cta_text, cta_slide_path)
    
    # 7. Stitch and Composite Video Timeline
    print("\nProcessing video segments with MoviePy...")
    clips = []
    
    for scene in storyboard.scenes:
        sid = scene.id
        dur = scene.est_duration
        stype = scene.type
        
        print(f"Processing Scene {sid} ({stype}, {dur:.2f}s)...")
        
        if stype == "hook_black":
            # Three stage slide transition for the hook
            c1 = ImageClip(hook_slide_1).with_duration(0.8)
            c2 = ImageClip(hook_slide_2).with_duration(0.8)
            c3 = ImageClip(hook_slide_3).with_duration(max(0.1, dur - 1.6))
            clips.append(concatenate_videoclips([c1, c2, c3]))
            
        elif stype == "cta_black":
            clips.append(ImageClip(cta_slide_path).with_duration(dur))
            
        elif stype == "stock_video":
            clip_path = assets_dir / f"scene_{sid}.mp4"
            if clip_path.exists():
                clips.append(process_clip_with_zoom(str(clip_path), dur, target_w=1080, target_h=1920, zoom_ratio=1.10))
            else:
                print(f"Warning: Stock video scene_{sid}.mp4 not found. Creating placeholder.")
                clips.append(ColorClip(size=(1080, 1920), color=(0, 0, 0)).with_duration(dur))
                
        elif stype == "reuse_video":
            clip_path = assets_dir / f"scene_{scene.reuse_scene_id}.mp4"
            if clip_path.exists():
                clips.append(process_clip_with_zoom(str(clip_path), dur, target_w=1080, target_h=1920, zoom_ratio=1.10))
            else:
                print(f"Warning: Reusable stock video scene_{scene.reuse_scene_id}.mp4 not found. Creating placeholder.")
                clips.append(ColorClip(size=(1080, 1920), color=(0, 0, 0)).with_duration(dur))
                
        elif stype == "split_screen":
            left_path = assets_dir / f"scene_{sid}_left.mp4"
            right_path = assets_dir / f"scene_{sid}_right.mp4"
            
            if left_path.exists() and right_path.exists():
                left_clip = process_clip_with_zoom(str(left_path), dur, target_w=540, target_h=1920, zoom_ratio=1.10)
                right_clip = process_clip_with_zoom(str(right_path), dur, target_w=540, target_h=1920, zoom_ratio=1.10)
                
                left_positioned = left_clip.with_position((0, 0))
                right_positioned = right_clip.with_position((540, 0))
                
                split_comp = CompositeVideoClip([left_positioned, right_positioned], size=(1080, 1920))
                clips.append(split_comp)
            else:
                print(f"Warning: Split screen files not found. Creating placeholder.")
                clips.append(ColorClip(size=(1080, 1920), color=(0, 0, 0)).with_duration(dur))
                
    print("Concatenating video clips...")
    final_video = concatenate_videoclips(clips, method="compose")
    
    # 8. Audio Processing and Mixing
    print("\nMixing Audio...")
    voice_track = AudioFileClip(str(voiceover_mp3))
    bgm_raw = AudioFileClip(str(bgm_path))
    
    # Calculate BGM switch times (defaults to 25.16s if not generated by LLM)
    beat_switch = storyboard.bgm_beat_switch_time if storyboard.bgm_beat_switch_time else 25.16
    bgm_vol = storyboard.bgm_volume if storyboard.bgm_volume else 0.08
    
    # BGM 1 (Problem theme): Plays from 1.8s to (beat_switch + 1.3s) for cross-fade
    bgm1_start = 1.8
    bgm1_end = beat_switch + 1.3
    bgm1_dur = bgm1_end - bgm1_start
    bgm1_cut = bgm_raw.subclipped(0, bgm1_dur)
    bgm1_mixed = bgm1_cut.with_effects([
        MultiplyVolume(bgm_vol),
        AudioFadeIn(1.5),
        AudioFadeOut(2.5)
    ]).with_start(bgm1_start)
    
    # BGM 2 (Solution theme): Starts at beat_switch of video (using BGM offset 35.0s)
    bgm2_start = beat_switch
    bgm2_end = total_duration - 1.70  # fade out before the CTA black screen
    bgm2_dur = bgm2_end - bgm2_start
    bgm2_cut = bgm_raw.subclipped(35.0, 35.0 + bgm2_dur)
    bgm2_mixed = bgm2_cut.with_effects([
        MultiplyVolume(bgm_vol),
        AudioFadeIn(2.0),
        AudioFadeOut(2.5)
    ]).with_start(bgm2_start)
    
    final_audio = CompositeAudioClip([voice_track, bgm1_mixed, bgm2_mixed])
    final_video = final_video.with_audio(final_audio)
    
    # 9. Render Video
    date_str = datetime.now().strftime("%Y%m%d")
    output_filename = f"reel-001-ai-system-prompt-{date_str}.mp4"
    output_path = Path("outputs") / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\nRendering final video to {output_path}...")
    try:
        final_video.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile="temp-audio-mixed.m4a",
            remove_temp=True
        )
        print(f"\nSUCCESS! Reel rendered successfully at: {output_path.absolute()}")
    except Exception as e:
        print(f"Error rendering video: {e}")
        sys.exit(1)
    finally:
        final_video.close()
        for c in clips:
            c.close()
            
    # 10. Clean Up Temporary Files
    if args.cleanup:
        print("\nCleaning up intermediate temporary files...")
        temp_files = [
            voiceover_wav,
            assets_dir / "hook_slide_1.png",
            assets_dir / "hook_slide_2.png",
            assets_dir / "hook_slide_3.png",
            assets_dir / "cta_slide.png",
        ]
        for tf in temp_files:
            if tf.exists():
                tf.unlink()
                print(f"  Deleted: {tf.name}")
        print("Cleanup completed.")

if __name__ == "__main__":
    asyncio.run(main())
