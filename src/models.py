from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any
import time

@dataclass
class UpstreamBuild:
    device: str
    filename: str
    download_url: str
    timestamp: int
    md5: str
    sha256: str
    size: int
    version: str
    buildtype: str = "user"
    maintainer: str = ""

@dataclass
class LocalBuild:
    device: str
    filename: str
    relative_path: str
    csig_path: str
    timestamp: int
    md5: str
    sha256: str
    size: int
    version: str
    built_at: float = field(default_factory=time.time)

@dataclass
class DeviceConfig:
    codename: str
    name: str
    upstream_url: str
    branch: str = "main"
    patch_mode: str = "rootless"  # "rootless", "ksu-next", "prepatched", "magisk"
    prepatched_boot: Optional[str] = None
    magisk_apk: Optional[str] = None
    kmi: Optional[str] = None  # e.g. "android13-5.10" or None for auto-detect
    keep_builds: int = 2
    enabled: bool = True

@dataclass
class JobProgress:
    device: str
    status: str  # idle, checking, downloading, patching, generating_metadata, completed, failed
    step: str = ""
    percent: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    message: str = ""
    error: Optional[str] = None
    started_at: float = 0.0
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
