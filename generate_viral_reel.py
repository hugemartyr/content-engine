import os
import sys
import json
import httpx
import asyncio
import zipfile
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import textwrap
from datetime import datetime

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
    from moviepy.audio.fx import AudioLoop, MultiplyVolume, AudioFadeIn, AudioFadeOut
except ImportError as e:
    print("Error: 'moviepy' is not installed in the active environment.")
    print(e)
    sys.exit(1)

# Storyboard configuration with exact pause midpoints from 1.15x speed voiceover analysis
# Total voiceover duration is 57.26 seconds
SCENES = [
    {
        "id": 1,
        "type": "hook_black",
        "start": 0.0,
        "end": 3.38,
        "duration": 3.38,
        "text": "Most people using AI are making themselves slower."
    },
    {
        "id": "2a",
        "type": "stock_video",
        "start": 3.38,
        "end": 10.32,
        "duration": 6.94,
        "query": "frustrated person laptop",
        "fallbacks": ["stressed typing computer", "frustrated typing laptop"]
    },
    {
        "id": "2b",
        "type": "stock_video",
        "start": 10.32,
        "end": 12.17,
        "duration": 1.85,
        "query": "keyboard typing close up",
        "fallbacks": ["frustrated typing laptop close up", "stressed keyboard close up"]
    },
    {
        "id": "2c",
        "type": "stock_video",
        "start": 12.17,
        "end": 16.48,
        "duration": 4.31,
        "query": "stressed face computer",
        "fallbacks": ["stressed man laptop face", "frustrated face screen"]
    },
    {
        "id": "3a",
        "type": "stock_video",
        "start": 16.48,
        "end": 20.09,
        "duration": 3.61,
        "query": "phone screen chat app",
        "fallbacks": ["smartphone screen close up", "phone screen chat"]
    },
    {
        "id": "3b",
        "type": "stock_video",
        "start": 20.09,
        "end": 22.77,
        "duration": 2.68,
        "query": "hand scrolling phone",
        "fallbacks": ["phone screen typing close up", "smartphone screen close up"]
    },
    {
        "id": 4,
        "type": "stock_video",
        "start": 22.77,
        "end": 25.16,
        "duration": 2.39,
        "query": "person waiting screen",
        "fallbacks": ["person waiting laptop", "impatient face screen"]
    },
    # Solutions phase begins here (25.16s) - BGM switches to bright theme
    {
        "id": "5a",
        "type": "split_screen",
        "start": 25.16,
        "end": 31.26,
        "duration": 6.10,
        "left_query": "messy handwritten notes",
        "left_fallbacks": ["messy desk papers", "handwritten notes"],
        "right_query": "organized desk documents",
        "right_fallbacks": ["neat desk documents", "clean document desk"]
    },
    {
        "id": "5b",
        "type": "stock_video",
        "start": 31.26,
        "end": 37.43,
        "duration": 6.17,
        "query": "writing code laptop",
        "fallbacks": ["typing instructions laptop", "coding screen close up"]
    },
    {
        "id": "5c",
        "type": "stock_video",
        "start": 37.43,
        "end": 39.66,
        "duration": 2.23,
        "query": "writing on notepad close up",
        "fallbacks": ["handwriting notebook close up", "writing list notebook"]
    },
    {
        "id": "5d",
        "type": "stock_video",
        "start": 39.66,
        "end": 44.63,
        "duration": 4.97,
        "query": "using tablet close up",
        "fallbacks": ["reviewing document tablet", "looking at graph tablet"]
    },
    {
        "id": "5e",
        "type": "stock_video",
        "start": 44.63,
        "end": 48.24,
        "duration": 3.61,
        "query": "pressing enter key",
        "fallbacks": ["clicking keyboard enter button", "hand pressing enter key"]
    },
    {
        "id": 6,
        "type": "stock_video",
        "start": 48.24,
        "end": 50.73,
        "duration": 2.49,
        "query": "person relaxed laptop coffee",
        "fallbacks": ["relaxed typing coffee shop", "happy person laptop"]
    },
    {
        "id": "7a",
        "type": "reuse_video",
        "start": 50.73,
        "end": 53.30,
        "duration": 2.57,
        "reuse_scene_id": "2a"
    },
    {
        "id": "7b",
        "type": "stock_video",
        "start": 53.30,
        "end": 55.56,
        "duration": 2.26,
        "query": "tired face screen",
        "fallbacks": ["sleepy office worker", "stressed person screen"]
    },
    {
        "id": 8,
        "type": "cta_black",
        "start": 55.56,
        "end": 57.26,
        "duration": 1.70,
        "text": "Build the prompt once."
    }
]

# Helper to create bold centered text slides on solid black background
def create_text_slide(text, filename, width=1080, height=1920, font_size=72, wrap_width=20):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    
    # Locate a bold modern sans-serif system font
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
    
    # If the file exists but is corrupted/too small, delete it
    if filepath.exists():
        if filepath.stat().st_size < 100000: # < 100KB is likely corrupted/mock
            print(f"File {filename} is too small or incomplete ({filepath.stat().st_size} bytes). Deleting for redownload.")
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

# Process video clip: loops or trims, mutes, crops to centered vertical, and applies dynamic zoom
def process_clip_with_zoom(clip_path, duration, target_w=1080, target_h=1920, zoom_ratio=1.10):
    clip = VideoFileClip(clip_path)
    
    # Trim or loop
    if clip.duration < duration:
        clip = clip.with_effects([Loop(duration=duration)])
    else:
        clip = clip.subclipped(0, duration)
        
    # Mute audio
    clip = clip.without_audio()
    
    # Get original dimensions
    w, h = clip.size
    
    # Calculate scale factor so the video covers target dimensions
    scale_factor = max(target_w / w, target_h / h)
    
    # Apply dynamic resize function (scales from scale_factor to scale_factor * zoom_ratio)
    resize_func = lambda t: scale_factor * (1.0 + (zoom_ratio - 1.0) * (t / duration))
    resized_clip = clip.resized(resize_func)
    
    # Position function to keep the expanding clip perfectly centered in the container
    pos_func = lambda t: (
        int((target_w - w * scale_factor * (1.0 + (zoom_ratio - 1.0) * (t / duration))) / 2),
        int((target_h - h * scale_factor * (1.0 + (zoom_ratio - 1.0) * (t / duration))) / 2)
    )
    
    # Composite the zooming clip inside a solid container matching the target resolution
    comp_clip = CompositeVideoClip(
        [resized_clip.with_position(pos_func)],
        size=(target_w, target_h)
    ).with_duration(duration)
    
    return comp_clip

async def main():
    print("====== VIRAL REEL ORCHESTRATION PIPELINE (UPGRADED) ======")
    assets_dir = Path("outputs/reel_system_prompt/assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Verify Voiceover
    voiceover_path = assets_dir / "voiceover.mp3"
    if not voiceover_path.exists() or voiceover_path.stat().st_size < 1000:
        print("Voiceover file not found! Please run generate_elevenlabs_voiceover.py first.")
        sys.exit(1)
    print(f"Voiceover verified at: {voiceover_path.absolute()}")
    
    # 2. Download BGM (with transition decision support using single track offsets)
    bgm_path = await download_lofi_bgm(assets_dir)
    if not bgm_path:
        print("Failed to secure background music asset.")
        sys.exit(1)
        
    # 3. Download Pexels videos
    pexels_key = os.getenv("PEXELS_API_KEY")
    if not pexels_key:
        print("Error: PEXELS_API_KEY not found in environment.")
        sys.exit(1)
        
    print("Checking and downloading Pexels stock video assets...")
    tasks = []
    for scene in SCENES:
        if scene["type"] == "stock_video":
            filename = f"scene_{scene['id']}.mp4"
            tasks.append(download_pexels_video(pexels_key, scene["query"], scene["fallbacks"], filename, assets_dir))
        elif scene["type"] == "split_screen":
            filename_l = f"scene_{scene['id']}_left.mp4"
            filename_r = f"scene_{scene['id']}_right.mp4"
            tasks.append(download_pexels_video(pexels_key, scene["left_query"], scene["left_fallbacks"], filename_l, assets_dir))
            tasks.append(download_pexels_video(pexels_key, scene["right_query"], scene["right_fallbacks"], filename_r, assets_dir))
            
    await asyncio.gather(*tasks)
    print("Asset check and downloads completed.")
    
    # 4. Generate PIL text slides for Hook & CTA
    hook_slide_1 = str(assets_dir / "hook_slide_1.png")
    hook_slide_2 = str(assets_dir / "hook_slide_2.png")
    hook_slide_3 = str(assets_dir / "hook_slide_3.png")
    cta_slide = str(assets_dir / "cta_slide.png")
    
    create_text_slide("Most people", hook_slide_1)
    create_text_slide("Most people\nusing AI", hook_slide_2)
    create_text_slide("Most people using AI\nare making themselves slower.", hook_slide_3)
    create_text_slide("Build the prompt\nonce.", cta_slide)
    
    # 5. Stitches and compiles clips with dynamic zoom-in
    print("\nProcessing video segments with dynamic zooms...")
    clips = []
    
    for scene in SCENES:
        sid = scene["id"]
        dur = scene["duration"]
        stype = scene["type"]
        
        print(f"Processing Scene {sid} ({stype}, {dur:.2f}s)...")
        
        if stype == "hook_black":
            c1 = ImageClip(hook_slide_1).with_duration(0.8)
            c2 = ImageClip(hook_slide_2).with_duration(0.8)
            c3 = ImageClip(hook_slide_3).with_duration(dur - 1.6)
            clips.append(concatenate_videoclips([c1, c2, c3]))
            
        elif stype == "cta_black":
            clips.append(ImageClip(cta_slide).with_duration(dur))
            
        elif stype == "stock_video":
            clip_path = assets_dir / f"scene_{sid}.mp4"
            clips.append(process_clip_with_zoom(str(clip_path), dur, target_w=1080, target_h=1920, zoom_ratio=1.10))
            
        elif stype == "reuse_video":
            clip_path = assets_dir / f"scene_{scene['reuse_scene_id']}.mp4"
            clips.append(process_clip_with_zoom(str(clip_path), dur, target_w=1080, target_h=1920, zoom_ratio=1.10))
            
        elif stype == "split_screen":
            left_path = assets_dir / f"scene_{sid}_left.mp4"
            right_path = assets_dir / f"scene_{sid}_right.mp4"
            
            # Crop to width 540 (half of 1080) and apply dynamic zoom centered on each half
            left_clip = process_clip_with_zoom(str(left_path), dur, target_w=540, target_h=1920, zoom_ratio=1.10)
            right_clip = process_clip_with_zoom(str(right_path), dur, target_w=540, target_h=1920, zoom_ratio=1.10)
            
            left_positioned = left_clip.with_position((0, 0))
            right_positioned = right_clip.with_position((540, 0))
            
            split_comp = CompositeVideoClip([left_positioned, right_positioned], size=(1080, 1920))
            clips.append(split_comp)
            
    print("Concatenating video timeline...")
    final_video = concatenate_videoclips(clips, method="compose")
    
    # 6. Audio Processing and Mixing with BGM mood switch at 25.16s
    print("\nMixing audio tracks (Voiceover + Dual-BGM Mood transition)...")
    voice_track = AudioFileClip(str(voiceover_path))
    
    bgm_raw = AudioFileClip(str(bgm_path))
    
    # BGM 1 (Problem theme): Plays from 1.8s to 26.5s of the video (using 0.0s to 24.7s of BGM)
    bgm1_dur = 26.5 - 1.8
    bgm1_cut = bgm_raw.subclipped(0, bgm1_dur)
    bgm1_mixed = bgm1_cut.with_effects([
        MultiplyVolume(0.08),
        AudioFadeIn(1.5),
        AudioFadeOut(2.5)
    ]).with_start(1.8)
    
    # BGM 2 (Solution theme): Starts at 24.0s of the video (using 35.0s onwards of BGM)
    bgm2_dur = 55.56 - 24.0
    bgm2_cut = bgm_raw.subclipped(35.0, 35.0 + bgm2_dur)
    bgm2_mixed = bgm2_cut.with_effects([
        MultiplyVolume(0.08),
        AudioFadeIn(2.0),
        AudioFadeOut(2.5)
    ]).with_start(24.0)
    
    print("  Adding voiceover track...")
    print("  Mixing BGM 1: Problem theme (1.8s start, ends at 26.5s)...")
    print("  Mixing BGM 2: Solution theme (24.0s start, cross-fades, ends at 55.56s)...")
    
    final_audio = CompositeAudioClip([voice_track, bgm1_mixed, bgm2_mixed])
    final_video = final_video.with_audio(final_audio)
    
    # 7. Render and Write Final Output
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
        print(f"\nSUCCESS! Upgraded high-quality Reel rendered successfully.")
        print(f"Final file saved at: {output_path.absolute()}")
    except Exception as e:
        print(f"Error rendering final video: {e}")
        sys.exit(1)
    finally:
        final_video.close()
        for c in clips:
            c.close()
            
if __name__ == "__main__":
    asyncio.run(main())
