#!/usr/bin/env python3
"""
LLM-in-the-Loop Reel Compilation Script
Optimized for 9:16 vertical (1080x1920), 30fps, H264 MP4.

Features:
- Interfaces with the configured local LLM (Ollama Qwen2.5-VL).
- Local LLM dynamically determines:
  * Semantic splitting of scenes.
  * Word-level kinetic overlays and highlights.
  * Visual zooms/pans based on asset characteristics.
  * Trigger timings for sound effects (whoosh, pop, ding).
- Mixed multi-track audio compiler (combines BGM and SFX).
- Handles empty/mock assets gracefully via ColorClips.
"""

import os
import sys
import json
import argparse
import tempfile
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Add project root to path so we can import core modules
sys.path.append(str(Path(__file__).resolve().parent))

# Import settings and LLM utils
from core.settings import settings
from core.utils.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

# Import moviepy
try:
    from moviepy import (
        VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip
    )
    from moviepy.video.fx import Loop
    from moviepy.audio.fx import AudioLoop
except ImportError as e:
    print("Error: 'moviepy' or 'pillow' is not installed in the active environment.")
    print(e)
    sys.exit(1)

# Visual presets cycle
VISUAL_PRESETS = [
    {"zoom": 1.0, "pan": "right"},
    {"zoom": 1.25, "pan": "center"},
    {"zoom": 1.15, "pan": "left"},
    {"zoom": 1.2, "pan": "bottom_up"},
    {"zoom": 1.1, "pan": "slow_zoom"},
    {"zoom": 1.25, "pan": "top_down"}
]

def find_fallback_asset(assets_dir, scene_id, original_filename):
    """Finds fallback image or video assets if the primary is missing."""
    shared_assets = Path("outputs/assets")
    if (shared_assets / original_filename).exists():
        return shared_assets / original_filename
        
    fallback_name = f"scene_{scene_id}_critical_fallback.jpg"
    if (shared_assets / fallback_name).exists():
        return shared_assets / fallback_name
    if (assets_dir / fallback_name).exists():
        return assets_dir / fallback_name
        
    for p in assets_dir.glob(f"*scene_{scene_id}*"):
        if p.is_file():
            return p
            
    for p in shared_assets.glob(f"*scene_{scene_id}*"):
        if p.is_file():
            return p
            
    for ext in ["*.jpg", "*.png", "*.mp4"]:
        for p in assets_dir.glob(ext):
            if p.is_file():
                return p
    return None

def load_sfx_clip(sfx_name, assets_dir):
    """Attempts to load a WAV or MP3 sound effect clip from asset directories."""
    shared_assets = Path("outputs/assets")
    for ext in [".wav", ".mp3"]:
        filename = f"{sfx_name}{ext}"
        if (assets_dir / filename).exists():
            try:
                return AudioFileClip(str(assets_dir / filename))
            except Exception:
                pass
        if (shared_assets / filename).exists():
            try:
                return AudioFileClip(str(shared_assets / filename))
            except Exception:
                pass
    return None

def clean_json_string(text):
    """Strips markdown code blocks from LLM string output."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def draw_word_highlighted_text(draw, text, x_center, y_start, font, font_bold, width, highlight_words, highlight_color=(255, 204, 0, 255), default_color=(255, 255, 255, 255)):
    """Draws multi-colored text on transparent canvas, highlighting target words."""
    max_char_width = 24
    lines = textwrap.wrap(text, width=max_char_width)
    
    try:
        space_bbox = draw.textbbox((0, 0), " ", font=font)
        space_w = space_bbox[2] - space_bbox[0]
        line_h = (space_bbox[3] - space_bbox[1]) + 20
    except AttributeError:
        space_w, _ = draw.textsize(" ", font=font)
        line_h = 60
        
    current_y = y_start
    total_text_height = len(lines) * line_h
    max_line_width = 0
    
    # Normalize highlight words
    hl_set = {w.upper().strip(".,!?\"'") for w in highlight_words}
    
    measured_lines = []
    for line in lines:
        words = line.split(" ")
        word_widths = []
        for word in words:
            cleaned = word.upper().strip(".,!?\"'")
            is_hl = cleaned in hl_set
            use_font = font_bold if is_hl else font
            try:
                bbox = draw.textbbox((0, 0), word, font=use_font)
                w = bbox[2] - bbox[0]
            except AttributeError:
                w, _ = draw.textsize(word, font=use_font)
            word_widths.append(w)
            
        line_w = sum(word_widths) + space_w * (len(words) - 1)
        max_line_width = max(max_line_width, line_w)
        measured_lines.append((words, word_widths, line_w))
        
    # Draw background box
    box_width = max_line_width + 60
    box_height = total_text_height + 40
    box_x_start = int(width / 2) - int(box_width / 2)
    box_y_start = y_start - 20
    
    draw.rounded_rectangle(
        [box_x_start, box_y_start, box_x_start + box_width, box_y_start + box_height],
        radius=25,
        fill=(0, 0, 0, 195)
    )
    
    # Draw text
    for words, word_widths, line_w in measured_lines:
        line_x_start = int(width / 2) - int(line_w / 2)
        current_x = line_x_start
        
        for i, word in enumerate(words):
            cleaned = word.upper().strip(".,!?\"'")
            is_hl = cleaned in hl_set
            use_font = font_bold if is_hl else font
            color = highlight_color if is_hl else default_color
            
            draw.text((current_x, current_y), word, font=use_font, fill=color)
            current_x += word_widths[i] + space_w
            
        current_y += line_h

def create_caption_image(text, highlight_words, width=1080, height=1920, font_size=46):
    """Generates transparent PNG overlay for kinetic captions."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    macos_bold_fonts = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/SFProBold.ttf"
    ]
    macos_reg_fonts = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFPro.ttf"
    ]
    
    font_bold = None
    for path in macos_bold_fonts:
        if os.path.exists(path):
            try:
                font_bold = ImageFont.truetype(path, font_size)
                break
            except Exception:
                continue
                
    font_reg = None
    for path in macos_reg_fonts:
        if os.path.exists(path):
            try:
                font_reg = ImageFont.truetype(path, font_size)
                break
            except Exception:
                continue
                
    if font_bold is None:
        font_bold = ImageFont.load_default()
    if font_reg is None:
        font_reg = ImageFont.load_default()
        
    draw_word_highlighted_text(
        draw, text, 
        x_center=int(width / 2), 
        y_start=1320, 
        font=font_reg, 
        font_bold=font_bold, 
        width=width,
        highlight_words=highlight_words
    )
    return img

def main():
    parser = argparse.ArgumentParser(description="LLM-in-the-Loop professional Reel compiler.")
    parser.add_argument(
        "--topic-dir", 
        type=str, 
        required=True, 
        help="Path to topic output directory (e.g. outputs/the_future_of_physical_ai_qasar_peters_breakthrough)"
    )
    args = parser.parse_args()
    
    topic_dir = Path(args.topic_dir)
    if not topic_dir.exists():
        print(f"Error: Topic directory not found at {topic_dir.absolute()}")
        sys.exit(1)
        
    final_package_file = topic_dir / "final_package.json"
    if not final_package_file.exists():
        print(f"Error: final_package.json not found in {topic_dir}")
        sys.exit(1)
        
    with open(final_package_file, "r") as f:
        package_data = json.load(f)
        
    timeline_data = package_data.get("timeline", {})
    if not timeline_data or "timeline" not in timeline_data:
        print("Error: Timeline not defined in final_package.json.")
        sys.exit(1)
        
    events = timeline_data["timeline"]
    bgm_file = timeline_data.get("bgm")
    assets_dir = topic_dir / "assets"
    
    # ------------------ LLM DIRECTING STAGE ------------------
    directives_file = topic_dir / "edit_directives.json"
    directives = {"scenes": {}}
    
    if directives_file.exists():
        print(f"Found existing directing sheet at: {directives_file.name}. Loading...")
        with open(directives_file, "r") as f:
            directives = json.load(f)
    else:
        print("Initializing local LLM Director Agent to generate editing directives in a loop...")
        try:
            llm = get_llm(temperature=0.2, json_mode=True)
        except Exception as e:
            print(f"Error instantiating local LLM: {e}. Falling back to default editor maps.")
            sys.exit(1)
        
        # System prompt for a single scene
        system_prompt = """You are an elite short-form video editor specializing in viral Instagram Reels.
You will receive details for a single scene: duration, original caption/narration, and asset info.
You must break this single scene into sub-segments of 1.0 to 2.0 seconds each (so a 3.0s scene gets 2 sub-segments, an 8.0s scene gets 4 sub-segments, etc.).

For each sub-segment, you MUST decide:
1. "text": A very short, uppercase caption (3-7 words max) that acts as a kinetic pop-up. Convert the narration clause into punchy keywords.
2. "highlight_words": List of words in "text" to paint in yellow.
3. "zoom": Zoom level (float between 1.0 and 1.3). Alternate zooms to create dynamic motion.
4. "pan": Panning direction ("left", "right", "bottom_up", "top_down", "slow_zoom", "center").
5. "sfx": Sound effect cue ("whoosh", "impact", "ding", "none"). Use "whoosh" for cuts, "ding" for metrics/numbers, "impact" for hook entrances.

Output EXACTLY this JSON array structure:
[
  {
    "sub_segment_id": 1,
    "duration": 1.5,
    "text": "PHYSICAL AI IS HERE",
    "highlight_words": ["PHYSICAL", "AI"],
    "zoom": 1.0,
    "pan": "right",
    "sfx": "impact"
  },
  {
    "sub_segment_id": 2,
    "duration": 1.5,
    "text": "MEET THE PIONEERS",
    "highlight_words": ["PIONEERS"],
    "zoom": 1.25,
    "pan": "center",
    "sfx": "none"
  }
]
"""
        
        for idx, event in enumerate(events):
            scene_id = idx + 1
            asset_name = event.get("asset", "")
            asset_filename = asset_name.replace("assets/", "")
            caption = event.get("caption", "")
            duration = event.get("end", 3.0) - event.get("start", 0.0)
            
            print(f"Querying LLM for Scene {scene_id}/{len(events)} ({duration}s)...")
            
            human_prompt = f"""
Scene details:
- Scene ID: {scene_id}
- Duration: {duration} seconds
- Original Caption/Narration: "{caption}"
- Asset Filename: {asset_filename}

Generate a JSON array of sub-segments (total duration must sum to exactly {duration} seconds).
"""
            try:
                response = llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_prompt)
                ])
                cleaned_response = clean_json_string(response.content)
                sub_segs = json.loads(cleaned_response)
                
                # If it returned a dictionary instead of a list, extract the list
                if isinstance(sub_segs, dict):
                    found_list = False
                    for val in sub_segs.values():
                        if isinstance(val, list):
                            sub_segs = val
                            found_list = True
                            break
                    if not found_list:
                        sub_segs = [sub_segs]
                        
                directives["scenes"][str(scene_id)] = sub_segs
                
            except Exception as e:
                print(f"Error querying LLM for Scene {scene_id}: {e}. Generating default segments.")
                # fallback default splits
                num_splits = max(1, int(duration / 2.0 + 0.99))
                split_dur = duration / num_splits
                fallback_segs = []
                words = caption.split()
                for i in range(num_splits):
                    sub_text = " ".join(words[i*3:(i+1)*3]).upper() if words else ""
                    fallback_segs.append({
                        "sub_segment_id": i + 1,
                        "duration": split_dur,
                        "text": sub_text,
                        "highlight_words": [],
                        "zoom": 1.0 + 0.1 * (i % 2),
                        "pan": "center",
                        "sfx": "none"
                    })
                directives["scenes"][str(scene_id)] = fallback_segs
                
        # Save directives
        with open(directives_file, "w") as f:
            json.dump(directives, f, indent=2)
        print(f"All editing directives generated and saved at: {directives_file.absolute()}")
            
    # ------------------ VIDEO COMPILATION STAGE ------------------
    print("====== COMPILING VIDEO FROM LLM DIRECTIVES ======")
    temp_dir_obj = tempfile.TemporaryDirectory()
    temp_dir = Path(temp_dir_obj.name)
    
    clips = []
    decisions_log = {}
    total_rendered_duration = 0.0
    width, height = 1080, 1920
    global_sub_segment_index = 0
    
    audio_tracks = []
    
    scene_directives = directives.get("scenes", {})
    
    for idx, event in enumerate(events):
        scene_id = idx + 1
        asset_name = event.get("asset")
        asset_filename = asset_name.replace("assets/", "")
        asset_path = assets_dir / asset_filename
        
        if not asset_path.exists():
            fallback = find_fallback_asset(assets_dir, scene_id, asset_filename)
            if fallback:
                print(f"Asset {asset_filename} not found. Using fallback: {fallback.name}")
                asset_path = fallback
            else:
                print(f"Warning: Asset {asset_filename} not found and no fallback available. Skipping scene {scene_id}.")
                continue
                
        sub_segments = scene_directives.get(str(scene_id), scene_directives.get(scene_id, []))
        if not sub_segments:
            print(f"Warning: No LLM directives found for scene {scene_id}. Skipping.")
            continue
            
        scene_dur = event.get("end", 3.0) - event.get("start", 0.0)
        print(f"Rendering Scene {scene_id}: {asset_filename} ({len(sub_segments)} LLM segments)")
        suffix = asset_path.suffix.lower()
        decisions_log[f"scene_{scene_id}"] = []
        current_time_in_scene = 0.0
        
        # Normalize sub-segments list (handles list of strings or dictionary objects)
        normalized_segs = []
        num_segs = len(sub_segments) if sub_segments else 1
        sub_dur = scene_dur / num_segs
        
        for sub_idx, seg in enumerate(sub_segments):
            if isinstance(seg, str):
                text_val = seg.upper()
                normalized_segs.append({
                    "sub_segment_id": sub_idx + 1,
                    "duration": sub_dur,
                    "text": text_val,
                    "highlight_words": [text_val],
                    "zoom": 1.0 + 0.15 * (sub_idx % 2),
                    "pan": VISUAL_PRESETS[global_sub_segment_index % len(VISUAL_PRESETS)]["pan"],
                    "sfx": "whoosh" if sub_idx > 0 else "none"
                })
            elif isinstance(seg, dict):
                normalized_segs.append({
                    "sub_segment_id": seg.get("sub_segment_id", sub_idx + 1),
                    "duration": seg.get("duration", sub_dur),
                    "text": seg.get("text", "").upper(),
                    "highlight_words": seg.get("highlight_words", []),
                    "zoom": seg.get("zoom", 1.0),
                    "pan": seg.get("pan", "center"),
                    "sfx": seg.get("sfx", "none")
                })
                
        if not normalized_segs:
            normalized_segs.append({
                "sub_segment_id": 1,
                "duration": scene_dur,
                "text": caption.upper(),
                "highlight_words": [],
                "zoom": 1.0,
                "pan": "center",
                "sfx": "none"
            })
            
        for sub_idx, seg in enumerate(normalized_segs):
            dur = seg["duration"]
            overlay_text = seg["text"]
            highlight_words = seg["highlight_words"]
            zoom_val = seg["zoom"]
            pan_val = seg["pan"]
            sfx_name = seg["sfx"]
            
            # Save logs
            decisions_log[f"scene_{scene_id}"].append({
                "sub_segment": sub_idx + 1,
                "asset_used": asset_path.name,
                "duration": dur,
                "overlay_text": overlay_text,
                "animation": f"zoom_{zoom_val}_{pan_val}",
                "sfx_triggered": sfx_name,
                "transition": "whip_pan" if sub_idx > 0 else "push"
            })
            
            # Mix SFX if triggered
            if sfx_name != "none":
                sfx_clip = load_sfx_clip(sfx_name, assets_dir)
                if sfx_clip:
                    sfx_clip = sfx_clip.with_start(total_rendered_duration)
                    audio_tracks.append(sfx_clip)
                    print(f"  Mixed Sound Effect: '{sfx_name}' at {total_rendered_duration:.2f}s")
                    
            # Check if file is mock/empty
            is_mock = False
            if asset_path.exists() and asset_path.stat().st_size < 100:
                is_mock = True
                
            base_clip = None
            try:
                if is_mock:
                    from moviepy import ColorClip
                    base_clip = ColorClip(size=(width, height), color=(18, 18, 18), duration=dur)
                else:
                    if suffix in [".png", ".jpg", ".jpeg", ".webp"]:
                        base_clip = ImageClip(str(asset_path)).with_duration(dur)
                    else:
                        full_video = VideoFileClip(str(asset_path))
                        start_cut = current_time_in_scene
                        end_cut = current_time_in_scene + dur
                        
                        if full_video.duration < end_cut:
                            try:
                                base_clip = full_video.with_effects([Loop(duration=end_cut)])
                            except Exception:
                                base_clip = full_video
                        else:
                            base_clip = full_video.subclipped(start_cut, end_cut)
                            
                        base_clip = base_clip.without_audio()
                        current_time_in_scene += dur
            except Exception as e:
                print(f"Error loading {asset_path.name}: {e}. Falling back to ColorClip.")
                from moviepy import ColorClip
                base_clip = ColorClip(size=(width, height), color=(18, 18, 18), duration=dur)
                
            # Resize base clip slightly larger (1.25x) to allow translations
            scale_w = int(width * 1.25)
            scale_h = int(height * 1.25)
            base_clip = base_clip.resized(new_size=(scale_w, scale_h))
            
            # Panning offset coordinates
            center_x = (width - scale_w) // 2
            center_y = (height - scale_h) // 2
            
            pos_func = lambda t: (center_x, center_y)
            if pan_val == "right":
                pos_func = lambda t: (int(center_x + 60 * t), center_y)
            elif pan_val == "left":
                pos_func = lambda t: (int(center_x - 60 * t), center_y)
            elif pan_val == "bottom_up":
                pos_func = lambda t: (center_x, int(center_y - 80 * t))
            elif pan_val == "top_down":
                pos_func = lambda t: (center_x, int(center_y + 80 * t))
            elif pan_val == "slow_zoom":
                pos_func = lambda t: (int(center_x + 20 * t), int(center_y + 20 * t))
                
            base_clip = base_clip.with_position(pos_func)
            
            # Zoom effect
            if zoom_val > 1.0:
                base_clip = base_clip.resized(lambda t: min(zoom_val, 1.0 + (zoom_val - 1.0) * (t / dur)))
                
            # Composite visual canvas
            scene_comp = CompositeVideoClip([base_clip], size=(width, height)).with_duration(dur)
            
            # Add dynamic captions with pop-in spring burst
            if overlay_text:
                cap_img = create_caption_image(overlay_text, highlight_words, width=width, height=height)
                cap_png_path = temp_dir / f"caption_s{scene_id}_g{sub_idx}.png"
                cap_img.save(cap_png_path)
                
                # Spring pop formula
                def text_scale(t):
                    if t < 0.15:
                        return 0.8 + 2.33 * t
                    elif t < 0.3:
                        return 1.15 - 1.0 * (t - 0.15)
                    else:
                        return 1.0
                        
                cap_clip = ImageClip(str(cap_png_path)).with_duration(dur)
                cap_clip = cap_clip.resized(text_scale)
                scene_comp = CompositeVideoClip([scene_comp, cap_clip])
                
            clips.append(scene_comp)
            total_rendered_duration += dur
            global_sub_segment_index += 1
            
    if not clips:
        print("Error: No clips compiled.")
        sys.exit(1)
        
    print(f"Stitching {len(clips)} LLM segments (Total Duration: {total_rendered_duration:.2f}s)...")
    final_video = concatenate_videoclips(clips, method="compose")
    
    # Process BGM
    if bgm_file:
        bgm_path = assets_dir / bgm_file
        if not bgm_path.exists():
            bgm_path = Path("outputs/assets") / bgm_file
            
        is_mock_audio = False
        if bgm_path.exists():
            if bgm_path.stat().st_size < 1000:
                is_mock_audio = True
                
        if bgm_path.exists() and not is_mock_audio:
            try:
                print(f"Loading background music: {bgm_file}")
                bgm_track = AudioFileClip(str(bgm_path))
                if bgm_track.duration < final_video.duration:
                    bgm_track = bgm_track.with_effects([AudioLoop(duration=final_video.duration)])
                else:
                    bgm_track = bgm_track.subclipped(0, final_video.duration)
                audio_tracks.append(bgm_track)
            except Exception as e:
                print(f"Warning BGM load failed: {e}")
        else:
            print("Note: BGM is a mock placeholder. Skipping BGM track.")
            
    # Combine BGM and SFX tracks
    if audio_tracks:
        print(f"Combining {len(audio_tracks)} audio tracks (BGM + SFX)...")
        final_audio = CompositeAudioClip(audio_tracks)
        final_video = final_video.with_audio(final_audio)
    else:
        print("Note: No audio tracks to mix. Video will be silent.")
        
    # Save outputs
    output_video_path = topic_dir / "final_reel_llm.mp4"
    output_decisions_path = topic_dir / "edit_decisions.json"
    
    print(f"Writing final video to {output_video_path}...")
    try:
        final_video.write_videofile(
            str(output_video_path),
            fps=30,
            codec="libx264",
            audio_codec="aac" if final_video.audio is not None else None,
            temp_audiofile="temp-audio-llm.m4a",
            remove_temp=True
        )
        print("Success! Reel rendered.")
        
        # Save decisions log
        with open(output_decisions_path, "w") as f:
            json.dump(decisions_log, f, indent=2)
        print(f"Decisions log saved at: {output_decisions_path}")
        
    except Exception as e:
        print(f"Error compiling/writing final reel: {e}")
        sys.exit(1)
    finally:
        final_video.close()
        for c in clips:
            c.close()
        temp_dir_obj.cleanup()

if __name__ == "__main__":
    main()
