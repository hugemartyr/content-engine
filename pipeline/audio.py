import os
import sys
import httpx
import subprocess
import wave
import numpy as np
from typing import List

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
