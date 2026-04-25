import discord
import logging
import asyncio
import aiohttp
from typing import Optional

from io import BytesIO
from PIL import Image

from discord.ext import commands

logger = logging.getLogger('discord.google_img')

MAX_IMG_COUNT = 5
MAX_IMG_SIZE_MB = 8
SEARCH_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 10


class GoogleImages(commands.Cog):
    def __init__(self, bot, searxng_url: str):
        self.bot = bot
        self.searxng_url = (searxng_url or '').rstrip('/')
        self.api_available = bool(self.searxng_url)
        if self.api_available:
            logger.info(f"Image search initialized against {self.searxng_url}")
        else:
            logger.error("SEARXNG_URL not set; image search disabled")

    @commands.command(name='img', help='Search for an image - optionally add a number at the end for count (e.g., !img cute cats 3)')
    async def img_search(self, ctx, *args):
        try:
            if not self.api_available:
                await ctx.send("❌ Image search is currently unavailable.")
                return

            if not args:
                await ctx.send("❌ Please provide a search term! Example: `!img cute cats` or `!img cute cats 3`")
                return

            count = 1
            query_parts = list(args)
            if len(args) > 1:
                try:
                    potential_count = int(args[-1])
                    if potential_count < 1:
                        await ctx.send("❌ Count must be at least 1!")
                        return
                    if potential_count > MAX_IMG_COUNT:
                        await ctx.send(f"⚠️ Maximum {MAX_IMG_COUNT} images allowed. Setting count to {MAX_IMG_COUNT}.")
                        count = MAX_IMG_COUNT
                    else:
                        count = potential_count
                    query_parts = args[:-1]
                except ValueError:
                    pass

            query = ' '.join(query_parts).strip()
            if not query:
                await ctx.send("❌ Please provide a search term! Example: `!img cute cats` or `!img cute cats 3`")
                return

            logger.info(f'Image search request from {ctx.author} for "{query}" (count: {count})')

            async with ctx.typing():
                await self._search(ctx, query, count)

        except Exception as e:
            logger.error(f"Error in img_search command: {e}", exc_info=True)
            await ctx.send("❌ An error occurred while searching for images. Please try again.")

    async def _search(self, ctx, query: str, count: int):
        try:
            results = await self._searxng_query(query, fetch=count * 4)
            logger.info(f"Found {len(results)} search results for '{query}'")

            if not results:
                await ctx.send(f"😕 No images found for '{query}'. Try a different search term.")
                return

            sent_count = 0
            timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for i, result in enumerate(results):
                    if sent_count >= count:
                        break

                    img_url = result.get('img_src') or result.get('thumbnail_src')
                    if not img_url:
                        continue

                    try:
                        image_data = await self._download_image(session, img_url)
                        if not image_data:
                            continue
                        if not self._validate_image(image_data):
                            continue
                        if await self._send_image(ctx, image_data, query, i):
                            sent_count += 1
                            logger.info(f"Sent image {sent_count}/{count} for '{query}'")
                    except Exception as e:
                        logger.warning(f"Error processing image {i} for '{query}': {e}")
                        continue

            if sent_count == 0:
                await ctx.send(f"😕 Couldn't find any valid images for '{query}'. Try a different search term.")
            elif sent_count < count:
                await ctx.send(f"⚠️ Only found {sent_count} valid images (requested {count}) for '{query}'.")

        except asyncio.TimeoutError:
            logger.error(f"SearXNG query timed out for '{query}'")
            await ctx.send("❌ Image search timed out. Please try again.")
        except aiohttp.ClientError as e:
            logger.error(f"SearXNG query failed for '{query}': {e}")
            await ctx.send("❌ Failed to reach image search. Please try again later.")
        except Exception as e:
            logger.error(f"Error in image search for '{query}': {e}", exc_info=True)
            await ctx.send("❌ An error occurred while processing the image search.")

    async def _searxng_query(self, query: str, fetch: int) -> list:
        params = {
            'q': query,
            'format': 'json',
            'categories': 'images',
            'safesearch': '1',
        }
        timeout = aiohttp.ClientTimeout(total=SEARCH_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.searxng_url}/search", params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()
        return data.get('results', [])[:fetch]

    async def _download_image(self, session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                content_length = resp.headers.get('content-length')
                if content_length and int(content_length) > MAX_IMG_SIZE_MB * 1024 * 1024:
                    return None
                data = bytearray()
                async for chunk in resp.content.iter_chunked(8192):
                    data.extend(chunk)
                    if len(data) > MAX_IMG_SIZE_MB * 1024 * 1024:
                        return None
                return bytes(data)
        except Exception as e:
            logger.debug(f"Download failed for {url}: {e}")
            return None

    def _validate_image(self, image_data: bytes) -> bool:
        if len(image_data) < 1024:
            return False
        try:
            with BytesIO(image_data) as img_io:
                with Image.open(img_io) as img:
                    img.verify()
                    return True
        except Exception:
            return self._has_image_signature(image_data)

    def _has_image_signature(self, data: bytes) -> bool:
        if len(data) < 8:
            return False
        signatures = (
            b'\xFF\xD8\xFF',
            b'\x89PNG\r\n\x1a\n',
            b'GIF87a', b'GIF89a',
            b'\x00\x00\x01\x00',
            b'BM',
        )
        if any(data.startswith(sig) for sig in signatures):
            return True
        return data.startswith(b'RIFF') and b'WEBP' in data[:12]

    async def _send_image(self, ctx, image_data: bytes, query: str, index: int) -> bool:
        try:
            file_ext = self._get_file_extension(image_data)
            filename = f"{query}_{index}.{file_ext}"
            with BytesIO(image_data) as image_io:
                image_io.seek(0)
                discord_file = discord.File(image_io, filename=filename)
                try:
                    await ctx.send(file=discord_file)
                    return True
                except discord.HTTPException as e:
                    if e.status == 413:
                        logger.warning(f"Image too large for Discord: {filename}")
                    else:
                        logger.error(f"Discord error sending image: {e}")
                    return False
        except Exception as e:
            logger.error(f"Error preparing image for sending: {e}")
            return False

    def _get_file_extension(self, image_data: bytes) -> str:
        if image_data.startswith(b'\xFF\xD8\xFF'):
            return 'jpg'
        if image_data.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'png'
        if image_data.startswith((b'GIF87a', b'GIF89a')):
            return 'gif'
        if image_data.startswith(b'RIFF') and b'WEBP' in image_data[:12]:
            return 'webp'
        if image_data.startswith(b'BM'):
            return 'bmp'
        return 'jpg'
