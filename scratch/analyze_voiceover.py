import wave
import numpy as np

def main():
    audio_path = "outputs/reel_system_prompt/assets/voiceover.wav"
    print(f"Loading wave file from {audio_path}...")
    
    with wave.open(audio_path, 'rb') as w:
        params = w.getparams()
        nchannels = params.nchannels
        sampwidth = params.sampwidth
        framerate = params.framerate
        nframes = params.nframes
        
        frames = w.readframes(nframes)
        data = np.frombuffer(frames, dtype=np.int16)
        
    # If stereo, take the average of the channels
    if nchannels > 1:
        data = data.reshape(-1, nchannels).mean(axis=1)
        
    print(f"Loaded {len(data)} samples at {framerate}Hz ({len(data)/framerate:.2f}s duration)")
    
    # Calculate absolute amplitude
    amplitude = np.abs(data)
    
    # Smooth amplitude with a rolling window (200ms)
    window_size = int(framerate * 0.2)  # 200ms window
    smoothed = np.convolve(amplitude, np.ones(window_size)/window_size, mode='same')
    
    # Threshold for silence: 2% of the 95th percentile amplitude
    threshold = 0.02 * np.percentile(smoothed, 95)
    print(f"Max smoothed amplitude: {smoothed.max():.4f}, 95th percentile: {np.percentile(smoothed, 95):.4f}, threshold: {threshold:.4f}")
    
    is_silent = smoothed < threshold
    
    # Find silence blocks
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
        
    # Filter for silences that are at least 300ms long
    min_silence_len = int(framerate * 0.3)  # 300ms
    pauses = []
    for start, end in zip(silence_starts, silence_ends):
        if end - start >= min_silence_len:
            pauses.append((start / framerate, end / framerate))
            
    print(f"Found {len(pauses)} pauses of at least 300ms:")
    for idx, (start, end) in enumerate(pauses):
        duration = end - start
        mid = (start + end) / 2
        print(f"  Pause {idx+1}: {start:.2f}s - {end:.2f}s (duration: {duration:.2f}s, midpoint: {mid:.2f}s)")

if __name__ == "__main__":
    main()
