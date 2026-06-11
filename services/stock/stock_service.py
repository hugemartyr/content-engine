import httpx
import os
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from core.settings import settings
from core.logging.logger import logger

class StockService:
    def __init__(self):
        self.pexels_key = settings.PEXELS_API_KEY
        self.pixabay_key = settings.PIXABAY_API_KEY
        self.assets_dir = settings.BASE_DIR / "outputs" / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    async def search_and_download_stock(self, query: str, scene_id: int, asset_type: str, dest_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Searches for stock video/image on Pexels/Pixabay and downloads it locally.
        If no API keys are present, falls back to public royalty-free placeholders.
        """
        local_filename = f"scene_{scene_id}_{uuid.uuid4().hex[:8]}"
        logger.info(f"Retrieving stock asset for Scene {scene_id} with query: '{query}'...")
        
        # 1. Try Pexels (if API key is present)
        if self.pexels_key:
            asset = await self._search_pexels(query, local_filename, asset_type, dest_dir)
            if asset:
                return asset
                
        # 2. Try Pixabay (if API key is present)
        if self.pixabay_key:
            asset = await self._search_pixabay(query, local_filename, asset_type, dest_dir)
            if asset:
                return asset
                
        # 3. Fallback to public royalty-free image download (using Unsplash/Picsum placeholder)
        logger.warning(f"No Stock API keys configured or search failed. Using public Unsplash/Picsum fallback.")
        return await self._download_fallback_image(query, scene_id, local_filename, dest_dir)

    async def _search_pexels(self, query: str, filename: str, asset_type: str, dest_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
        headers = {"Authorization": self.pexels_key}
        # Pexels supports both videos and images
        is_video = asset_type.upper() in ["STOCK", "AI_BROLL"]
        url = "https://api.pexels.com/v1/search" if not is_video else "https://api.pexels.com/videos/search"
        
        params = {"query": query, "per_page": 3, "orientation": "portrait"} # reels orientation!
        
        target_dir = dest_dir if dest_dir is not None else self.assets_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if is_video:
                        videos = data.get("videos", [])
                        if videos:
                            video = videos[0]
                            # Find a medium quality mobile/portrait video file
                            video_files = video.get("video_files", [])
                            # Find vertical/portrait file or fallback to first file
                            target_url = None
                            for vf in video_files:
                                if vf.get("width", 0) < vf.get("height", 0):  # Portrait
                                    target_url = vf.get("link")
                                    break
                            if not target_url and video_files:
                                target_url = video_files[0].get("link")
                                
                            if target_url:
                                filepath = target_dir / f"{filename}.mp4"
                                await self._download_file(target_url, filepath)
                                
                                # Extract tags from video URL slug
                                tags = []
                                video_page_url = video.get("url")
                                if video_page_url and "/video/" in video_page_url:
                                    slug = video_page_url.split("/video/")[1].split("/")[0]
                                    tags = [w for w in slug.split("-") if not w.isdigit() and len(w) > 2]
                                if not tags:
                                    tags = [w.strip().lower() for w in query.split(" ") if len(w.strip()) > 2]
                                    
                                return {
                                    "scene": 0,  # to be updated by caller
                                    "asset_url": target_url,
                                    "local_path": str(filepath.relative_to(settings.BASE_DIR)),
                                    "license": "pexels",
                                    "source": "pexels",
                                    "tags": tags
                                }
                    else:
                        photos = data.get("photos", [])
                        if photos:
                            photo_url = photos[0].get("src", {}).get("portrait") or photos[0].get("src", {}).get("large")
                            if photo_url:
                                filepath = target_dir / f"{filename}.jpg"
                                await self._download_file(photo_url, filepath)
                                
                                # Extract tags from photo alt or URL slug
                                alt_text = photos[0].get("alt", "")
                                tags = [w.strip().lower() for w in alt_text.split(" ") if len(w.strip()) > 2] if alt_text else []
                                if not tags and photos[0].get("url"):
                                    photo_page_url = photos[0].get("url")
                                    if "/photo/" in photo_page_url:
                                        slug = photo_page_url.split("/photo/")[1].split("/")[0]
                                        tags = [w for w in slug.split("-") if not w.isdigit() and len(w) > 2]
                                if not tags:
                                    tags = [w.strip().lower() for w in query.split(" ") if len(w.strip()) > 2]
                                    
                                return {
                                    "scene": 0,  # to be updated by caller
                                    "asset_url": photo_url,
                                    "local_path": str(filepath.relative_to(settings.BASE_DIR)),
                                    "license": "pexels",
                                    "source": "pexels",
                                    "tags": tags
                                }
        except Exception as e:
            logger.error(f"Pexels stock retrieval failed: {e}")
        return None

    async def _search_pixabay(self, query: str, filename: str, asset_type: str, dest_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
        is_video = asset_type.upper() in ["STOCK", "AI_BROLL"]
        url = "https://pixabay.com/api/" if not is_video else "https://pixabay.com/api/videos/"
        params = {
            "key": self.pixabay_key,
            "q": query,
            "per_page": 3,
            "safesearch": "true"
        }
        
        target_dir = dest_dir if dest_dir is not None else self.assets_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    hits = data.get("hits", [])
                    if hits:
                        hit = hits[0]
                        
                        # Extract tags
                        tags_str = hit.get("tags", "")
                        tags = [t.strip().lower() for t in tags_str.split(",") if t.strip()]
                        if not tags:
                            tags = [w.strip().lower() for w in query.split(" ") if len(w.strip()) > 2]
                            
                        if is_video:
                            # Extract video urls
                            videos = hit.get("videos", {})
                            video_url = videos.get("medium", {}).get("url") or videos.get("small", {}).get("url")
                            if video_url:
                                filepath = target_dir / f"{filename}.mp4"
                                await self._download_file(video_url, filepath)
                                return {
                                    "scene": 0,
                                    "asset_url": video_url,
                                    "local_path": str(filepath.relative_to(settings.BASE_DIR)),
                                    "license": "pixabay",
                                    "source": "pixabay",
                                    "tags": tags
                                }
                        else:
                            image_url = hit.get("largeImageURL") or hit.get("webformatURL")
                            if image_url:
                                filepath = target_dir / f"{filename}.jpg"
                                await self._download_file(image_url, filepath)
                                return {
                                    "scene": 0,
                                    "asset_url": image_url,
                                    "local_path": str(filepath.relative_to(settings.BASE_DIR)),
                                    "license": "pixabay",
                                    "source": "pixabay",
                                    "tags": tags
                                }
        except Exception as e:
            logger.error(f"Pixabay stock retrieval failed: {e}")
        return None

    async def _download_fallback_image(self, query: str, scene_id: int, filename: str, dest_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Downloads a beautiful tech-themed vertical placeholder image from Unsplash Source."""
        # Curated list of tech/AI themed Unsplash photo IDs to rotate based on query hash
        tech_photo_ids = [
            "photo-1618005182384-a83a8bd57fbe", # Abstract tech wave
            "photo-1620712943543-bcc4688e7485", # Robot hand / AI
            "photo-1518770660439-4636190af475", # Circuit board
            "photo-1639762681485-074b7f938ba0", # Abstract network
            "photo-1526374965328-7f61d4dc18c5", # Digital matrix / code
            "photo-1451187580459-43490279c0fa"  # Earth network
        ]
        # Select one deterministically based on query text
        idx = hash(query) % len(tech_photo_ids)
        photo_id = tech_photo_ids[idx]
        
        # We query Unsplash with sizing for a vertical reel (1080 x 1920 or scaled to 720 x 1280)
        unsplash_url = f"https://images.unsplash.com/{photo_id}?auto=format&fit=crop&w=720&h=1280&q=80"
        
        target_dir = dest_dir if dest_dir is not None else self.assets_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine fallback tags
        tags = [w.strip().lower() for w in query.split(" ") if len(w.strip()) > 2] + ["fallback", "unsplash", "technology"]
        
        filepath = target_dir / f"{filename}.jpg"
        try:
            await self._download_file(unsplash_url, filepath)
            return {
                "scene": scene_id,
                "asset_url": unsplash_url,
                "local_path": str(filepath.relative_to(settings.BASE_DIR)),
                "license": "unsplash_free",
                "source": "unsplash",
                "tags": tags
            }
        except Exception as e:
            logger.error(f"Failed to download Unsplash fallback image: {e}")
            
        # Hard fallback to simple Picsum portrait image
        picsum_url = f"https://picsum.photos/720/1280?random={scene_id}"
        try:
            filepath = target_dir / f"{filename}.jpg"
            await self._download_file(picsum_url, filepath)
            return {
                "scene": scene_id,
                "asset_url": picsum_url,
                "local_path": str(filepath.relative_to(settings.BASE_DIR)),
                "license": "picsum_free",
                "source": "picsum",
                "tags": tags
            }
        except Exception as pe:
            if settings.ENV == "testing":
                logger.critical(f"Critical fallback to Picsum failed: {pe}")
                # If network completely fails, touch empty file so code doesn't break
                filepath.touch()
                return {
                    "scene": scene_id,
                    "asset_url": "local_fallback",
                    "local_path": str(filepath.relative_to(settings.BASE_DIR)),
                    "license": "local",
                    "source": "local_mock",
                    "tags": tags + ["picsum", "local"]
                }
            else:
                logger.exception("Picsum stock fallback download critically failed")
                raise pe

    async def _download_file(self, url: str, dest_path: Path):
        """Asynchronously downloads a file from url and saves to dest_path."""
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"Successfully downloaded asset to {dest_path}")
            else:
                raise Exception(f"Failed to download file. Status: {response.status_code}")

stock_service = StockService()
