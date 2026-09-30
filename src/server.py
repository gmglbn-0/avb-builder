import asyncio
import os
import mimetypes
import logging
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from src.config import Config
from src.manager import BuildManager

logger = logging.getLogger("avb-builder.server")

def range_stream(file_path: Path, start: int, end: int, chunk_size: int = 1024 * 1024):
    """Generator yielding bytes for an HTTP byte-range request."""
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            bytes_to_read = min(remaining, chunk_size)
            chunk = f.read(bytes_to_read)
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk

def create_app(config: Config, manager: BuildManager) -> FastAPI:
    app = FastAPI(title="AVB Builder & OTA Server", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Range-Capable Static File Server ──────────────────────────────────
    async def serve_file_with_range(request: Request, file_path: Path) -> Response:
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        file_size = file_path.stat().st_size
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            if file_path.name.endswith(".csig"):
                mime_type = "application/octet-stream"
            elif file_path.name.endswith(".zip"):
                mime_type = "application/zip"
            elif file_path.name.endswith(".json"):
                mime_type = "application/json"
            else:
                mime_type = "application/octet-stream"

        range_header = request.headers.get("range")
        if range_header:
            # Parse Range: bytes=start-end
            try:
                h = range_header.strip()
                if not h.startswith("bytes="):
                    raise ValueError()
                ranges = h[6:].split("-")
                start = int(ranges[0]) if ranges[0] else 0
                end = int(ranges[1]) if len(ranges) > 1 and ranges[1] else file_size - 1

                if start >= file_size or end >= file_size or start > end:
                    return Response(
                        status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                        headers={"Content-Range": f"bytes */{file_size}"},
                    )

                content_length = end - start + 1
                headers = {
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(content_length),
                    "Content-Type": mime_type,
                }
                return StreamingResponse(
                    range_stream(file_path, start, end),
                    status_code=status.HTTP_206_PARTIAL_CONTENT,
                    headers=headers,
                )
            except Exception as e:
                logger.warning(f"Error parsing Range header '{range_header}': {e}")

        # Full file
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": mime_type,
        }
        if request.method == "HEAD":
            return Response(status_code=status.HTTP_200_OK, headers=headers)

        return StreamingResponse(
            range_stream(file_path, 0, file_size - 1),
            status_code=status.HTTP_200_OK,
            headers=headers,
        )

    # ── Custota Update Info Routes: /<device>.json ────────────────────────
    @app.api_route("/{device}.json", methods=["GET", "HEAD"])
    async def get_custota_json(request: Request, device: str):
        file_path = config.www_dir / f"{device}.json"
        return await serve_file_with_range(request, file_path)

    # ── EvolutionX Builds Routes: /builds/<device>.json ───────────────────
    @app.api_route("/builds/{device}.json", methods=["GET", "HEAD"])
    async def get_evolutionx_json(request: Request, device: str):
        file_path = config.builds_dir / f"{device}.json"
        return await serve_file_with_range(request, file_path)

    # ── OTA File Downloads: /ota/{filename} ────────────────────────────────
    @app.api_route("/ota/{filename}", methods=["GET", "HEAD"])
    async def get_ota_file(request: Request, filename: str):
        file_path = config.ota_dir / filename
        return await serve_file_with_range(request, file_path)

    # ── REST API ─────────────────────────────────────────────────────────
    @app.get("/api/status")
    async def api_status():
        return manager.get_full_status()

    @app.post("/api/check")
    async def api_check():
        results = manager.check_all()
        return {"success": True, "results": {k: bool(v) for k, v in results.items()}}

    @app.post("/api/build/{device}")
    async def api_build(device: str, force: bool = False):
        if device not in config.devices:
            raise HTTPException(status_code=404, detail="Device not found")
        started = manager.start_build(device, force=force)
        return {"success": started, "device": device}

    @app.get("/api/logs")
    async def api_logs():
        return {"logs": manager.log_history}

    # ── Dashboard UI ──────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def get_dashboard():
        html_file = Path(__file__).parent / "static" / "index.html"
        if html_file.exists():
            return HTMLResponse(content=html_file.read_text())
        return HTMLResponse(content="<h1>AVB Builder & OTA Server Running</h1>")

    # ── Background Scheduler Task ─────────────────────────────────────────
    @app.on_event("startup")
    async def startup_event():
        asyncio.create_task(background_scheduler(config, manager))

    return app

async def background_scheduler(config: Config, manager: BuildManager):
    """Periodically check for new upstream releases and trigger build."""
    interval_seconds = config.check_interval_hours * 3600
    logger.info(f"Background update scheduler running (checks every {config.check_interval_hours} hours)")

    # Initial check after 10 seconds of server startup
    await asyncio.sleep(10)
    while True:
        try:
            logger.info("Scheduler: running periodic check for all devices...")
            manager.check_all()

            # Auto-build any device with update_available
            for codename, dev_cfg in config.devices.items():
                if not dev_cfg.enabled:
                    continue
                dev_state = manager.state.get("devices", {}).get(codename, {})
                if dev_state.get("update_available"):
                    logger.info(f"Scheduler: update available for {codename}! Starting automated build...")
                    manager.start_build(codename)

        except Exception as e:
            logger.error(f"Error in background scheduler: {e}", exc_info=True)

        await asyncio.sleep(interval_seconds)
