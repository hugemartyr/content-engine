import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime

# Import modules from current package
from .schemas import ReelStoryboard
from .llm import extract_storyboard_llm
from .assets import download_pexels_video, download_lofi_bgm, create_text_slide
from .audio import generate_voiceover_tts, convert_mp3_to_wav, detect_pause_midpoints, align_scene_durations
from .video import build_video_clips, mix_audio_and_render

async def run_pipeline(prompt_text: str, force: bool = False, cleanup: bool = True):
    # 2. Extract Storyboard via Gemini
    storyboard = extract_storyboard_llm(prompt_text, force=force)
    
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
    hook_slides = [hook_slide_1, hook_slide_2, hook_slide_3]
    clips = build_video_clips(storyboard, assets_dir, hook_slides, cta_slide_path)
    
    # 8 & 9. Render Video
    date_str = datetime.now().strftime("%Y%m%d")
    output_filename = f"reel-001-ai-system-prompt-{date_str}.mp4"
    output_path = Path("outputs") / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    mix_audio_and_render(
        clips=clips,
        voiceover_mp3=voiceover_mp3,
        bgm_path=bgm_path,
        storyboard=storyboard,
        total_duration=total_duration,
        output_path=output_path
    )
    
    # 10. Clean Up Temporary Files
    if cleanup:
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
