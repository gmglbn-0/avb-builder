import hashlib
import logging
import os
import requests
from pathlib import Path
from typing import Callable, Optional
from src.upstream import USER_AGENT

logger = logging.getLogger("avb-builder.downloader")

class DownloadError(Exception):
    pass

def download_file(
    url: str,
    destination: Path,
    expected_sha256: Optional[str] = None,
    expected_md5: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    chunk_size: int = 1024 * 1024,  # 1MB chunks
) -> Path:
    """Download a file with streaming chunks, hash computation, and progress updates."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_destination = destination.with_suffix(destination.suffix + ".part")

    headers = {"User-Agent": USER_AGENT}

    logger.info(f"Starting download from {url} to {destination}...")

    try:
        with requests.get(url, headers=headers, stream=True, timeout=(15, 60)) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))

            sha256_hash = hashlib.sha256()
            md5_hash = hashlib.md5()
            downloaded = 0

            with open(temp_destination, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    sha256_hash.update(chunk)
                    md5_hash.update(chunk)
                    downloaded += len(chunk)

                    if progress_callback:
                        progress_callback(downloaded, total_size)

        calc_sha256 = sha256_hash.hexdigest().lower()
        calc_md5 = md5_hash.hexdigest().lower()

        # Verify hashes if provided
        if expected_sha256 and expected_sha256.lower() != calc_sha256:
            if temp_destination.exists():
                temp_destination.unlink()
            raise DownloadError(
                f"SHA256 mismatch! Expected {expected_sha256}, got {calc_sha256}"
            )

        if expected_md5 and expected_md5.lower() != calc_md5:
            if temp_destination.exists():
                temp_destination.unlink()
            raise DownloadError(
                f"MD5 mismatch! Expected {expected_md5}, got {calc_md5}"
            )

        # Atomic move to final destination
        if temp_destination.exists():
            temp_destination.rename(destination)

        logger.info(f"Download complete: {destination} ({downloaded} bytes, SHA256: {calc_sha256})")
        return destination

    except Exception as e:
        if temp_destination.exists():
            temp_destination.unlink()
        raise DownloadError(f"Download failed: {e}") from e
