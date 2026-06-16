import os
import httpx
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

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
