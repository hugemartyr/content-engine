#!/usr/bin/env python3
"""
AI Reel Generator
Stitches collected assets (videos, images) together according to the timeline JSON,
overlays captions dynamically using Pillow, and outputs a 9:16 vertical MP4 video.
"""

import os
import sys
import json
import argparse
import tempfile
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Attempt to import moviepy
try:
    from moviepy import (
        VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip
    )
    from moviepy.video.fx import Loop
    from moviepy.audio.fx import AudioLoop
except ImportError as e:
    print("Warning: 'moviepy' or 'pillow' is not installed in the active environment or there was an error importing them:")
    print(e)
    print("Run: venv/bin/pip install moviepy pillow")
    print("Or install them globally. MoviePy is required to render the video.")
    sys.exit(1)

def create_caption_image(text, width=720, height=1280, font_name="Arial", font_size=32):
    """
    Renders transparent PNG with rounded semi-transparent caption background 
    and word-wrapped white text centered at the lower-third safe area.
    This avoids MoviePy's ImageMagick dependency.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Locate a standard system font
    font = None
    macos_fonts = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Verdana.ttf",
        "/System/Library/Fonts/SFPro.ttf",
        "/System/Library/Fonts/Keyboard.ttf"
    ]
    for path in macos_fonts:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except Exception:
                continue
                
    if font is None:
        font = ImageFont.load_default()
        
    # Wrap text to fit nicely (margin of ~60px on each side)
    max_char_width = 30  # fits nicely on 720px width at font size 32
    lines = textwrap.wrap(text, width=max_char_width)
    
    # Calculate dimensions
    line_widths = []
    line_heights = []
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
        except AttributeError:
            # Fallback for older Pillow versions
            w, h = draw.textsize(line, font=font)
        line_widths.append(w)
        line_heights.append(h)
        
    if not line_widths:
        return img
        
    box_width = max(line_widths) + 50
    box_height = sum(line_heights) + (len(lines) - 1) * 12 + 36
    
    # Position the box at the lower third (approx y = 960 on 1280 height)
    box_y_start = int(height * 0.72) - int(box_height / 2)
    box_x_start = int(width / 2) - int(box_width / 2)
    
    # Draw rounded dark background card
    draw.rounded_rectangle(
        [box_x_start, box_y_start, box_x_start + box_width, box_y_start + box_height],
        radius=18,
        fill=(0, 0, 0, 185)  # Dark semi-transparent
    )
    
    # Draw text
    current_y = box_y_start + 18
    for i, line in enumerate(lines):
        line_w = line_widths[i]
        line_x = int(width / 2) - int(line_w / 2)
        # Draw text with anti-aliasing
        draw.text((line_x, current_y), line, font=font, fill=(255, 255, 255, 255))
        current_y += line_heights[i] + 12
        
    return img

def parse_args():
    parser = argparse.ArgumentParser(description="Stitches collected assets into a 9:16 vertical Reel.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--package", 
        type=str, 
        help="Path to unified JSON package (e.g. outputs/final_reel_package_ai_agents.json)"
    )
    group.add_argument(
        "--topic-dir", 
        type=str, 
        help="Path to topic output directory (e.g. outputs/this_repo_exploded_overnight_openclawopenclaw)"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default="outputs/rendered_reel.mp4", 
        help="Path for saving rendered output video"
    )
    parser.add_argument(
        "--assets-dir", 
        type=str, 
        help="Directory override where media assets are stored"
    )
    parser.add_argument(
        "--resolution",
        type=str,
        default="720x1280",
        help="Output resolution widthxheight (default: 720x1280)"
    )
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Parse width and height
    try:
        width, height = map(int, args.resolution.split("x"))
    except ValueError:
        print("Invalid resolution. Use format WxH (e.g., 720x1280)")
        sys.exit(1)
        
    # Load timeline data
    timeline_data = None
    resolved_assets_dir = None
    bgm_file = None
    
    if args.package:
        package_path = Path(args.package)
        if not package_path.exists():
            print(f"Error: Unified package file not found at {package_path}")
            sys.exit(1)
        with open(package_path, "r") as f:
            package_data = json.load(f)
            timeline_data = package_data.get("timeline", {})
        # For unified package, assets are typically inside outputs/assets
        resolved_assets_dir = Path("outputs/assets")
    else:
        topic_path = Path(args.topic_dir)
        if not topic_path.exists():
            print(f"Error: Topic directory not found at {topic_path}")
            sys.exit(1)
            
        timeline_file = topic_path / "timeline.json"
        if not timeline_file.exists():
            print(f"Error: timeline.json not found in {topic_path}")
            sys.exit(1)
            
        with open(timeline_file, "r") as f:
            timeline_data = json.load(f)
            
        # For topic dir, assets are usually inside outputs/assets or outputs/topic_dir/assets
        # Let's search topic_dir/assets first, then outputs/assets
        if (topic_path / "assets").is_dir():
            resolved_assets_dir = topic_path / "assets"
        else:
            resolved_assets_dir = Path("outputs/assets")
            
    # Override assets directory if supplied
    if args.assets_dir:
        resolved_assets_dir = Path(args.assets_dir)
        
    if not timeline_data or "timeline" not in timeline_data:
        print("Error: No timeline events found in JSON.")
        sys.exit(1)
        
    events = timeline_data["timeline"]
    bgm_file = timeline_data.get("bgm")
    
    print(f"--- Preparing Reel ---")
    print(f"Title: {timeline_data.get('title', 'Untitled Reel')}")
    print(f"Assets Directory: {resolved_assets_dir.absolute()}")
    print(f"BGM Option: {bgm_file}")
    print(f"Resolution: {width}x{height}")
    print(f"Total Segments: {len(events)}")
    
    # We will create a temporary directory for text overlay PNGs
    temp_dir_obj = tempfile.TemporaryDirectory()
    temp_dir = Path(temp_dir_obj.name)
    
    clips = []
    
    for idx, event in enumerate(events):
        start = event.get("start", 0.0)
        end = event.get("end", 3.0)
        duration = max(0.1, end - start)
        asset_name = event.get("asset")
        caption = event.get("caption", "")
        
        if not asset_name:
            print(f"Warning: Segment {idx+1} does not have an asset name. Skipping.")
            continue
            
        asset_path = resolved_assets_dir / asset_name
        # If it doesn't exist, search directly in the current workspace outputs/assets
        if not asset_path.exists():
            asset_path = Path("outputs/assets") / asset_name
            
        if not asset_path.exists():
            print(f"Warning: Asset file not found at {asset_path}. Skipping segment {idx+1}.")
            continue
            
        print(f"Processing segment {idx+1}/{len(events)}: {asset_name} ({duration}s)")
        
        suffix = asset_path.suffix.lower()
        clip = None
        
        try:
            if suffix in [".png", ".jpg", ".jpeg", ".webp"]:
                # Load static image
                clip = ImageClip(str(asset_path)).with_duration(duration)
                clip = clip.resized(new_size=(width, height))
            elif suffix in [".mp4", ".mov", ".mkv"]:
                # Load video clip
                video_clip = VideoFileClip(str(asset_path))
                
                # Check video duration. If shorter than requested, loop it.
                if video_clip.duration < duration:
                    try:
                        clip = video_clip.with_effects([Loop(duration=duration)])
                    except Exception:
                        # Fallback simple repeat
                        clip = video_clip.subclipped(0, min(video_clip.duration, duration)).with_duration(duration)
                else:
                    clip = video_clip.subclipped(0, duration)
                    
                # Mute b-roll sound so BGM stands out
                clip = clip.without_audio()
                clip = clip.resized(new_size=(width, height))
            else:
                print(f"Warning: Unsupported file format {suffix}. Skipping.")
                continue
                
            # Add dynamic captions if present
            if caption:
                cap_img = create_caption_image(caption, width=width, height=height)
                cap_png_path = temp_dir / f"caption_{idx}.png"
                cap_img.save(cap_png_path)
                
                cap_clip = ImageClip(str(cap_png_path)).with_duration(duration)
                clip = CompositeVideoClip([clip, cap_clip])
                
            clips.append(clip)
            
        except Exception as e:
            print(f"Error loading/processing asset {asset_name}: {e}")
            continue
            
    if not clips:
        print("Error: No valid clips were loaded. Video cannot be generated.")
        sys.exit(1)
        
    print(f"Stitching {len(clips)} video segments...")
    try:
        final_video = concatenate_videoclips(clips, method="compose")
    except Exception as e:
        print(f"Error concatenating clips: {e}")
        sys.exit(1)
        
    # Process BGM
    if bgm_file:
        bgm_path = resolved_assets_dir / bgm_file
        if not bgm_path.exists():
            bgm_path = Path("outputs/assets") / bgm_file
            
        is_mock_audio = False
        if bgm_path.exists():
            # Check size to avoid loading mock string files
            if bgm_path.stat().st_size < 1000:
                is_mock_audio = True
                
        if bgm_path.exists() and not is_mock_audio:
            try:
                print(f"Adding BGM: {bgm_path.name}")
                audio_clip = AudioFileClip(str(bgm_path))
                
                # Loop or trim BGM to fit video duration
                if audio_clip.duration < final_video.duration:
                    try:
                        audio_clip = audio_clip.with_effects([AudioLoop(duration=final_video.duration)])
                    except Exception:
                        pass
                else:
                    audio_clip = audio_clip.subclipped(0, final_video.duration)
                    
                final_video = final_video.with_audio(audio_clip)
            except Exception as e:
                print(f"Warning: Could not process BGM audio: {e}. Output will have no music.")
        else:
            if is_mock_audio:
                print("Note: Background music file is a simulation mock. Proceeding with silent video.")
            else:
                print(f"Note: Background music file {bgm_file} not found. Proceeding with silent video.")
                
    # Ensure parent output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Writing final video to {output_path}...")
    try:
        # standard reel parameters: libx264 codec, high quality, 24fps
        final_video.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True
        )
        print(f"Successfully rendered video! File saved at: {output_path.absolute()}")
    except Exception as e:
        print(f"Error rendering final video: {e}")
    finally:
        # Close all clips
        final_video.close()
        for c in clips:
            c.close()
        temp_dir_obj.cleanup()

if __name__ == "__main__":
    main()
