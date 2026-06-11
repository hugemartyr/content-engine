#!/usr/bin/env python3
"""
Professional Generic Reel Compilation Script
Optimized for 9:16 vertical (1080x1920), 30fps, H264 MP4.
Features:
- Generic CLI execution on any topic output directory.
- No static frame longer than 2 seconds (dynamic sub-segmenting).
- Cycles visual motions (zoom-ins, pans, translations) on every segment.
- Cumulative word-by-word kinetic text highlights (Pillow) with spring scale burst.
- Mutes stock clips to keep audio clean.
- Auto-handles mock/missing BGM tracks.
- Generates final_reel.mp4 and edit_decisions.json in the target folder.
"""

import os
import sys
import json
import argparse
import tempfile
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Import moviepy
try:
    from moviepy import (
        VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip
    )
    from moviepy.video.fx import Loop
    from moviepy.audio.fx import AudioLoop
except ImportError as e:
    print("Error: 'moviepy' or 'pillow' is not installed in the active environment.")
    print(e)
    sys.exit(1)

# Highlight terms list
HIGHLIGHT_WORDS = {
    "AI", "PHYSICAL", "MACHINES", "AUTOMATION", "REVOLUTION", "BREAKTHROUGH",
    "GMAIL", "GOOGLE", "EMAIL", "OUTLOOK", "HOTMAIL", "APPLIED", "INTUITION",
    "QASAR", "PETER", "FUTURE", "$1T", "REPO", "CLONE", "SHAPE", "PIONEERS",
    "MARKET", "TRANSFORMING", "EFFICIENCY", "TECHNOLOGY", "COPILOT", "VISIONPLUS",
    "SUPERHERO", "MEMORY", "COMPANION", "DOWNLOADS", "PRODUCTIVITY", "MICROSOFT",
    "INFINITE", "COMPANIONS", "AGENTS"
}

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
    """
    Looks for the best available fallback asset in the topic assets folder 
    or the shared outputs/assets directory.
    """
    shared_assets = Path("outputs/assets")
    
    # Try 1: check if original_filename exists in shared folder
    if (shared_assets / original_filename).exists():
        return shared_assets / original_filename
        
    # Try 2: check if scene_{scene_id}_critical_fallback.jpg exists in outputs/assets or topic/assets
    fallback_name = f"scene_{scene_id}_critical_fallback.jpg"
    if (shared_assets / fallback_name).exists():
        return shared_assets / fallback_name
    if (assets_dir / fallback_name).exists():
        return assets_dir / fallback_name
        
    # Try 3: check if there is any file in assets_dir matching scene_{scene_id}
    for p in assets_dir.glob(f"*scene_{scene_id}*"):
        if p.is_file():
            return p
            
    # Try 4: check if there is any file in shared_assets matching scene_{scene_id}
    for p in shared_assets.glob(f"*scene_{scene_id}*"):
        if p.is_file():
            return p
            
    # Try 5: fallback to any file from the same directory as a last resort
    for ext in ["*.jpg", "*.png", "*.mp4"]:
        for p in assets_dir.glob(ext):
            if p.is_file():
                return p
                
    return None

def clean_word(word):
    """Strip punctuation from word for highlighting check."""
    return "".join(c for c in word if c.isalnum() or c in ['$', '%']).upper()

def should_highlight(word):
    """Determine if a word should be highlighted (capital, numeric, or in highlight list)."""
    cleaned = clean_word(word)
    if not cleaned:
        return False
    # Check if in highlight list
    if cleaned in HIGHLIGHT_WORDS:
        return True
    # Check if contains numbers (e.g. 2004, $1T, 100%, 24)
    if any(c.isdigit() for c in cleaned):
        return True
    # Check if capitalized and length > 2
    if len(cleaned) > 2 and cleaned.isupper():
        return True
    return False

def draw_word_highlighted_text(draw, text, x_center, y_start, font, font_bold, width, highlight_color=(255, 204, 0, 255), default_color=(255, 255, 255, 255)):
    """Renders word-wrapped lines with specific highlighted words colorized."""
    # Wrap text to fit nicely on 1080px width at font size 48
    max_char_width = 24
    lines = textwrap.wrap(text, width=max_char_width)
    
    # Measure spacing
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
    
    measured_lines = []
    for line in lines:
        words = line.split(" ")
        word_widths = []
        for word in words:
            use_font = font_bold if should_highlight(word) else font
            try:
                bbox = draw.textbbox((0, 0), word, font=use_font)
                w = bbox[2] - bbox[0]
            except AttributeError:
                w, _ = draw.textsize(word, font=use_font)
            word_widths.append(w)
            
        line_w = sum(word_widths) + space_w * (len(words) - 1)
        max_line_width = max(max_line_width, line_w)
        measured_lines.append((words, word_widths, line_w))
        
    # Draw background box (dark semi-transparent rounded rectangle)
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
            is_hl = should_highlight(word)
            use_font = font_bold if is_hl else font
            color = highlight_color if is_hl else default_color
            
            draw.text((current_x, current_y), word, font=use_font, fill=color)
            current_x += word_widths[i] + space_w
            
        current_y += line_h

def create_caption_image(text, width=1080, height=1920, font_size=46):
    """Creates a transparent PNG frame with centered dynamic keyword-highlighted captions."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Fonts loading
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
        width=width
    )
    return img

def main():
    parser = argparse.ArgumentParser(description="Professional automated video compilation tool.")
    parser.add_argument(
        "--topic-dir", 
        type=str, 
        required=True, 
        help="Path to the generated topic output directory (e.g. outputs/microsofts_copilot_visionplus_your_ai_superhero)"
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
    
    print("====== PROFESSIONAL GENERIC REEL COMPILER ======")
    print(f"Topic: {package_data.get('topic')}")
    print(f"Directory: {topic_dir.absolute()}")
    print(f"Assets Path: {assets_dir.absolute()}")
    
    temp_dir_obj = tempfile.TemporaryDirectory()
    temp_dir = Path(temp_dir_obj.name)
    
    clips = []
    decisions_log = {}
    total_rendered_duration = 0.0
    width, height = 1080, 1920
    global_sub_segment_index = 0
    
    for idx, event in enumerate(events):
        scene_id = idx + 1
        asset_name = event.get("asset")
        
        # Clean prefix
        asset_filename = asset_name.replace("assets/", "")
        asset_path = assets_dir / asset_filename
        
        if not asset_path.exists():
            # Run fallback resolution
            fallback = find_fallback_asset(assets_dir, scene_id, asset_filename)
            if fallback:
                print(f"Asset {asset_filename} not found. Using fallback: {fallback.name}")
                asset_path = fallback
            else:
                print(f"Warning: Asset {asset_filename} not found and no fallback available. Skipping scene {scene_id}.")
                continue
            
        scene_start = event.get("start", 0.0)
        scene_end = event.get("end", 3.0)
        scene_dur = max(0.1, scene_end - scene_start)
        
        caption_text = event.get("caption", "").strip()
        words = caption_text.split()
        
        # Determine how many sub-segments are needed (maximum 2.0s duration per segment)
        # To avoid static screens:
        num_sub_segments = max(1, int(scene_dur / 2.0 + 0.99))
        sub_dur = scene_dur / num_sub_segments
        
        print(f"Processing Scene {scene_id}: {asset_filename} ({scene_dur}s) -> Split into {num_sub_segments} clips of {sub_dur:.2f}s")
        suffix = asset_path.suffix.lower()
        decisions_log[f"scene_{scene_id}"] = []
        current_time_in_scene = 0.0
        
        for sub_idx in range(num_sub_segments):
            # Dynamic cumulative word selection (type-writer animation build up)
            if words:
                num_words_to_show = min(len(words), int((sub_idx + 1) * len(words) / num_sub_segments + 0.5))
                num_words_to_show = max(1, num_words_to_show)
                sub_text = " ".join(words[:num_words_to_show]).upper()
            else:
                sub_text = ""
                
            # Get visual preset
            preset = VISUAL_PRESETS[global_sub_segment_index % len(VISUAL_PRESETS)]
            zoom_val = preset["zoom"]
            pan_val = preset["pan"]
            global_sub_segment_index += 1
            
            # Save logs
            decisions_log[f"scene_{scene_id}"].append({
                "sub_segment": sub_idx + 1,
                "asset_used": asset_filename,
                "duration": sub_dur,
                "overlay_text": sub_text,
                "animation": f"zoom_{zoom_val}_{pan_val}",
                "transition": "whip_pan" if sub_idx > 0 else "push"
            })
            
            # Check if file is mock/empty
            is_mock = False
            if asset_path.exists() and asset_path.stat().st_size < 100:
                is_mock = True
                
            base_clip = None
            try:
                if is_mock:
                    from moviepy import ColorClip
                    base_clip = ColorClip(size=(width, height), color=(18, 18, 18), duration=sub_dur)
                else:
                    if suffix in [".png", ".jpg", ".jpeg", ".webp"]:
                        base_clip = ImageClip(str(asset_path)).with_duration(sub_dur)
                    else:
                        full_video = VideoFileClip(str(asset_path))
                        start_cut = current_time_in_scene
                        end_cut = current_time_in_scene + sub_dur
                        
                        if full_video.duration < end_cut:
                            try:
                                base_clip = full_video.with_effects([Loop(duration=end_cut)])
                            except Exception:
                                base_clip = full_video
                        else:
                            base_clip = full_video.subclipped(start_cut, end_cut)
                            
                        base_clip = base_clip.without_audio()
                        current_time_in_scene += sub_dur
            except Exception as e:
                print(f"Error loading {asset_path.name}: {e}. Falling back to ColorClip.")
                from moviepy import ColorClip
                base_clip = ColorClip(size=(width, height), color=(18, 18, 18), duration=sub_dur)
                
            # Resize base clip to be slightly larger (1.25x) to allow translation pans
            scale_w = int(width * 1.25)
            scale_h = int(height * 1.25)
            base_clip = base_clip.resized(new_size=(scale_w, scale_h))
            
            # Translation coordinates
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
                base_clip = base_clip.resized(lambda t: min(zoom_val, 1.0 + (zoom_val - 1.0) * (t / sub_dur)))
                
            # Composite translation frame
            scene_comp = CompositeVideoClip([base_clip], size=(width, height)).with_duration(sub_dur)
            
            # Add dynamic pop captions
            if sub_text:
                cap_img = create_caption_image(sub_text, width=width, height=height)
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
                        
                cap_clip = ImageClip(str(cap_png_path)).with_duration(sub_dur)
                cap_clip = cap_clip.resized(text_scale)
                scene_comp = CompositeVideoClip([scene_comp, cap_clip])
                
            clips.append(scene_comp)
            total_rendered_duration += sub_dur
            
    if not clips:
        print("Error: No valid clips were compiled.")
        sys.exit(1)
        
    print(f"Stitching {len(clips)} dynamic segments (Total Duration: {total_rendered_duration:.2f}s)...")
    final_video = concatenate_videoclips(clips, method="compose")
    
    # Mix BGM
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
                print(f"Mixing background music: {bgm_file}")
                audio_clip = AudioFileClip(str(bgm_path))
                if audio_clip.duration < final_video.duration:
                    audio_clip = audio_clip.with_effects([AudioLoop(duration=final_video.duration)])
                else:
                    audio_clip = audio_clip.subclipped(0, final_video.duration)
                final_video = final_video.with_audio(audio_clip)
            except Exception as e:
                print(f"Warning BGM load failed: {e}. Output will be silent.")
        else:
            print("Note: BGM is missing or a mock placeholder. Generating silent audio.")
            
    # Save outputs
    output_video_path = topic_dir / "final_reel.mp4"
    output_decisions_path = topic_dir / "edit_decisions.json"
    
    print(f"Writing final video to {output_video_path}...")
    try:
        final_video.write_videofile(
            str(output_video_path),
            fps=30,
            codec="libx264",
            audio_codec="aac" if final_video.audio is not None else None,
            temp_audiofile="temp-audio.m4a",
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
