"""Static file serving endpoint for Finance frontend assets."""

from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class FinanceDashboardStaticView(HomeAssistantView):
    """Serve static frontend files.

    R12: file I/O is dispatched to the thread pool via
    ``hass.async_add_executor_job`` so the async event loop is never
    blocked by synchronous ``read_bytes()`` calls.  A small LRU cache
    (16 entries, mtime-aware) avoids redundant disk reads for hot files
    like the main JS bundle.
    """

    url = f"/api/{DOMAIN}/static/{{filename}}"
    name = f"api:{DOMAIN}:static"
    requires_auth = False  # Static JS/CSS files

    # LRU cache: filename -> (mtime_ns, bytes)
    _cache: dict[str, tuple[int, bytes]] = {}  # noqa: RUF012
    _CACHE_MAX = 16

    async def get(self, request: web.Request, filename: str) -> web.Response:
        """Serve a static file from the frontend directory."""
        hass = request.app["hass"]
        frontend_dir = Path(__file__).parent.parent / "frontend"
        file_path = frontend_dir / filename

        if not file_path.exists() or not file_path.is_file():
            return web.Response(status=404)

        try:
            file_path.resolve().relative_to(frontend_dir.resolve())
        except ValueError:
            return web.Response(status=403)

        content_type = "application/javascript"
        if filename.endswith(".css"):
            content_type = "text/css"
        elif filename.endswith(".html"):
            content_type = "text/html"

        # R12: async file read + mtime-aware LRU cache.
        def _read() -> tuple[int, bytes]:
            mtime = file_path.stat().st_mtime_ns
            return mtime, file_path.read_bytes()

        cached = self._cache.get(filename)
        if cached is not None:
            cached_mtime, cached_data = cached
            current_mtime = await hass.async_add_executor_job(lambda: file_path.stat().st_mtime_ns)
            if current_mtime == cached_mtime:
                data = cached_data
            else:
                mtime, data = await hass.async_add_executor_job(_read)
                self._cache[filename] = (mtime, data)
        else:
            mtime, data = await hass.async_add_executor_job(_read)
            # Evict oldest entry if cache is full
            if len(self._cache) >= self._CACHE_MAX:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[filename] = (mtime, data)

        return web.Response(
            body=data,
            content_type=content_type,
            headers={
                "Cache-Control": "public, max-age=3600",
            },
        )
