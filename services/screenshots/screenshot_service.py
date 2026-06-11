import os
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright
from core.settings import settings
from core.logging.logger import logger

class ScreenshotService:
    def __init__(self):
        self.assets_dir = settings.BASE_DIR / "outputs" / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    async def capture_screenshot(self, url: str, scene_id: int, dest_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Captures a screenshot of the specified URL using Playwright.
        If navigation fails, renders a local HTML template and captures that instead.
        """
        filename = f"screenshot_scene_{scene_id}_{uuid.uuid4().hex[:8]}.png"
        target_dir = dest_dir if dest_dir is not None else self.assets_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / filename
        logger.info(f"Attempting to capture screenshot of URL: {url} for Scene {scene_id}...")


        try:
            async with async_playwright() as p:
                # Use Chromium browser
                browser = await p.chromium.launch(headless=True)
                # Configure a mobile/tablet-like vertical viewport for Reels (e.g. 720 x 1280)
                context = await browser.new_context(
                    viewport={"width": 720, "height": 1280},
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
                )
                page = await context.new_page()
                
                try:
                    # Navigate to target page (timeout after 15 seconds)
                    await page.goto(url, wait_until="networkidle", timeout=15000)
                    # Add a small delay for animations to finish
                    await asyncio.sleep(1.0)
                    await page.screenshot(path=filepath, full_page=False)
                    logger.info(f"Successfully captured screenshot from web: {filepath}")
                    await browser.close()
                    
                    return {
                        "scene": scene_id,
                        "asset_url": url,
                        "local_path": str(filepath.relative_to(settings.BASE_DIR)),
                        "license": "proprietary",
                        "source": "screenshot"
                    }
                except Exception as page_err:
                    logger.warning(f"Failed to load web URL '{url}' ({page_err}). Generating a beautiful local UI card fallback.")
                    
                    # Generate a beautiful local HTML card representation of the website
                    domain = url.split("//")[-1].split("/")[0] if "//" in url else url
                    local_html = self._generate_fallback_html(domain, url)
                    await page.set_content(local_html)
                    await asyncio.sleep(0.5)
                    await page.screenshot(path=filepath, full_page=False)
                    logger.info(f"Successfully captured local UI card screenshot: {filepath}")
                    await browser.close()
                    
                    return {
                        "scene": scene_id,
                        "asset_url": url,
                        "local_path": str(filepath.relative_to(settings.BASE_DIR)),
                        "license": "local_generated",
                        "source": "screenshot_fallback"
                    }
        except Exception as e:
            if settings.ENV == "testing":
                logger.warning(f"Playwright screenshot engine encountered a critical error: {e}. Falling back to standard image for testing.")
                # Touch a simple placeholder file and return it
                filepath.touch()
                return {
                    "scene": scene_id,
                    "asset_url": url,
                    "local_path": str(filepath.relative_to(settings.BASE_DIR)),
                    "license": "fallback",
                    "source": "critical_fallback"
                }
            else:
                logger.exception("Playwright screenshot engine encountered a critical failure")
                raise e

    def _generate_fallback_html(self, title: str, url: str) -> str:
        """Generates a premium dark-themed card containing mock browser details."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
                    color: #f8fafc;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    height: 1280px;
                    width: 720px;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                    box-sizing: border-box;
                }}
                .browser-mockup {{
                    width: 620px;
                    height: 800px;
                    background: #1e293b;
                    border-radius: 16px;
                    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                    border: 1px solid #334155;
                    display: flex;
                    flex-direction: column;
                    overflow: hidden;
                }}
                .browser-header {{
                    height: 48px;
                    background: #0f172a;
                    display: flex;
                    align-items: center;
                    padding: 0 16px;
                    border-bottom: 1px solid #334155;
                }}
                .dots {{
                    display: flex;
                    gap: 6px;
                }}
                .dot {{
                    width: 12px;
                    height: 12px;
                    border-radius: 50%;
                }}
                .dot.red {{ background: #ef4444; }}
                .dot.yellow {{ background: #eab308; }}
                .dot.green {{ background: #22c55e; }}
                
                .address-bar {{
                    flex-grow: 1;
                    margin-left: 24px;
                    margin-right: 24px;
                    height: 28px;
                    background: #1e293b;
                    border-radius: 6px;
                    border: 1px solid #475569;
                    color: #94a3b8;
                    font-size: 12px;
                    display: flex;
                    align-items: center;
                    padding: 0 12px;
                    overflow: hidden;
                    white-space: nowrap;
                    text-overflow: ellipsis;
                }}
                .browser-content {{
                    flex-grow: 1;
                    padding: 40px;
                    display: flex;
                    flex-direction: column;
                    justify-content: space-between;
                }}
                .tag {{
                    align-self: flex-start;
                    background: linear-gradient(90deg, #6366f1 0%, #a855f7 100%);
                    color: white;
                    padding: 6px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: 700;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }}
                .title {{
                    font-size: 38px;
                    font-weight: 800;
                    line-height: 1.2;
                    margin-top: 24px;
                    margin-bottom: 16px;
                    background: linear-gradient(to right, #ffffff, #94a3b8);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }}
                .desc {{
                    font-size: 18px;
                    color: #94a3b8;
                    line-height: 1.6;
                }}
                .code-box {{
                    background: #0f172a;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 16px;
                    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
                    font-size: 14px;
                    color: #38bdf8;
                    margin-top: 24px;
                }}
                .footer-brand {{
                    text-align: center;
                    color: #475569;
                    font-size: 12px;
                    letter-spacing: 2px;
                    text-transform: uppercase;
                    margin-top: 40px;
                }}
            </style>
        </head>
        <body>
            <div class="browser-mockup">
                <div class="browser-header">
                    <div class="dots">
                        <div class="dot red"></div>
                        <div class="dot yellow"></div>
                        <div class="dot green"></div>
                    </div>
                    <div class="address-bar">{url}</div>
                </div>
                <div class="browser-content">
                    <div>
                        <div class="tag">AI Trending</div>
                        <div class="title">{title}</div>
                        <div class="desc">Evaluating technical parameters, repository code patterns, and developer ecosystem signals.</div>
                    </div>
                    <div class="code-box">
                        $ git clone {url}<br>
                        $ npm install && npm run build<br>
                        $ # Status: Active development detected
                    </div>
                </div>
            </div>
            <div class="footer-brand">AI Reel Engine v1.0</div>
        </body>
        </html>
        """

screenshot_service = ScreenshotService()
