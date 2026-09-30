import logging
import requests
from typing import Optional
from src.models import UpstreamBuild, DeviceConfig

logger = logging.getLogger("avb-builder.upstream")

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def fetch_upstream_build(device: DeviceConfig) -> Optional[UpstreamBuild]:
    """Fetch the latest upstream build information from the device's upstream JSON URL."""
    if not device.upstream_url:
        logger.warning(f"Device {device.codename} has no upstream_url configured.")
        return None

    try:
        headers = {"User-Agent": USER_AGENT}
        logger.info(f"Querying upstream for {device.codename} ({device.name}) from {device.upstream_url}...")
        resp = requests.get(device.upstream_url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        response_list = data.get("response", [])
        if not response_list:
            logger.warning(f"Empty response array in upstream JSON for {device.codename}")
            return None

        # Take the newest build (first item in response list)
        item = response_list[0]

        return UpstreamBuild(
            device=device.codename,
            filename=item.get("filename", ""),
            download_url=item.get("download", ""),
            timestamp=int(item.get("timestamp", 0)),
            md5=item.get("md5", ""),
            sha256=item.get("sha256", ""),
            size=int(item.get("size", 0)),
            version=str(item.get("version", "")),
            buildtype=item.get("buildtype", "user"),
            maintainer=item.get("maintainer", ""),
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch upstream build for {device.codename}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing upstream for {device.codename}: {e}", exc_info=True)
        return None
