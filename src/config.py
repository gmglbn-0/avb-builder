import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from src.models import DeviceConfig

class Config:
    def __init__(self, config_path: Optional[str] = None):
        self.root_dir = Path(__file__).resolve().parent.parent
        self.config_file = self._find_config_file(config_path)
        self.data: Dict[str, Any] = self._load_yaml()

        # Server settings
        server_cfg = self.data.get("server", {})
        self.host = os.environ.get("AVB_HOST", server_cfg.get("host", "0.0.0.0"))
        self.port = int(os.environ.get("AVB_PORT", server_cfg.get("port", 8085)))
        self.base_url = os.environ.get("AVB_BASE_URL", server_cfg.get("base_url", f"http://127.0.0.1:{self.port}")).rstrip("/")
        
        # Base Data Directory
        raw_data_dir = os.environ.get("AVB_DATA_DIR", server_cfg.get("data_dir", "./data"))
        self.data_dir = Path(raw_data_dir).expanduser()
        if not self.data_dir.is_absolute():
            self.data_dir = (self.root_dir / self.data_dir).resolve()

        self.check_interval_hours = int(server_cfg.get("check_interval_hours", 6))

        # Directories
        self.keys_dir = self.data_dir / "keys"
        self.downloads_dir = self.data_dir / "storage" / "downloads"
        self.temp_dir = self.data_dir / "storage" / "temp"
        self.www_dir = self.data_dir / "www"
        self.ota_dir = self.www_dir / "ota"
        self.builds_dir = self.www_dir / "builds"
        self.logs_dir = self.data_dir / "logs"
        self.state_file = self.data_dir / "state.json"

        # Tool paths
        tools_cfg = self.data.get("tools", {})
        self.avbroot_path = self._resolve_tool_path(tools_cfg.get("avbroot_path", "avbroot"))
        self.custota_tool_path = self._resolve_tool_path(tools_cfg.get("custota_tool_path", "custota-tool"))
        self.ksud_path = self._resolve_tool_path(tools_cfg.get("ksud_path", "ksud"))
        self.magiskboot_path = self._resolve_tool_path(tools_cfg.get("magiskboot_path", "magiskboot"))

        # Keys
        keys_cfg = self.data.get("keys", {})
        self.avb_key = self._resolve_key_path(keys_cfg.get("avb_key", "avb.key"))
        self.ota_key = self._resolve_key_path(keys_cfg.get("ota_key", "ota.key"))
        self.ota_cert = self._resolve_key_path(keys_cfg.get("ota_cert", "ota.crt"))
        self.avb_passphrase_env = keys_cfg.get("avb_passphrase_env", "PASSPHRASE_AVB")
        self.ota_passphrase_env = keys_cfg.get("ota_passphrase_env", "PASSPHRASE_OTA")

        # Devices
        self.devices: Dict[str, DeviceConfig] = {}
        for codename, dev_cfg in self.data.get("devices", {}).items():
            self.devices[codename] = DeviceConfig(
                codename=codename,
                name=dev_cfg.get("name", codename),
                upstream_url=dev_cfg.get("upstream_url", ""),
                branch=dev_cfg.get("branch", "main"),
                patch_mode=dev_cfg.get("patch_mode", "rootless"),
                prepatched_boot=dev_cfg.get("prepatched_boot"),
                magisk_apk=dev_cfg.get("magisk_apk"),
                kmi=dev_cfg.get("kmi"),
                keep_builds=int(dev_cfg.get("keep_builds", 2)),
                enabled=dev_cfg.get("enabled", True),
            )

        self._ensure_directories()

    def _find_config_file(self, config_path: Optional[str]) -> Path:
        if config_path and Path(config_path).exists():
            return Path(config_path)
        if (self.root_dir / "config.yaml").exists():
            return self.root_dir / "config.yaml"
        if (self.root_dir / "config.example.yaml").exists():
            return self.root_dir / "config.example.yaml"
        return self.root_dir / "config.yaml"

    def _load_yaml(self) -> Dict[str, Any]:
        if self.config_file.exists():
            with open(self.config_file, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _resolve_tool_path(self, path_str: Any) -> Path:
        import shutil
        name = Path(path_str).name
        # 1. Check if name is in system PATH (e.g. /usr/local/bin in Docker)
        which_path = shutil.which(name) or shutil.which(str(path_str))
        if which_path:
            return Path(which_path)
        # 2. Check in local bin/ directory
        local_bin = self.root_dir / "bin" / name
        if local_bin.exists():
            return local_bin
        # 3. Fallback to path resolution
        return self._resolve_path(path_str)

    def _resolve_key_path(self, path_str: Any) -> Path:
        p = Path(path_str).expanduser()
        if p.is_absolute() and p.exists():
            return p
        # Check inside keys_dir
        if (self.keys_dir / p.name).exists():
            return self.keys_dir / p.name
        # Check inside data_dir
        if (self.data_dir / p).exists():
            return self.data_dir / p
        return self.keys_dir / p.name

    def _resolve_path(self, path_str: Any) -> Path:
        p = Path(path_str).expanduser()
        if not p.is_absolute():
            p = (self.root_dir / p).resolve()
        return p

    def _ensure_directories(self):
        for d in [
            self.data_dir,
            self.keys_dir,
            self.downloads_dir,
            self.temp_dir,
            self.www_dir,
            self.ota_dir,
            self.builds_dir,
            self.logs_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def check_tools(self) -> Dict[str, bool]:
        return {
            "avbroot": self.avbroot_path.exists() and os.access(self.avbroot_path, os.X_OK),
            "custota-tool": self.custota_tool_path.exists() and os.access(self.custota_tool_path, os.X_OK),
            "ksud": self.ksud_path.exists() and os.access(self.ksud_path, os.X_OK),
            "magiskboot": self.magiskboot_path.exists() and os.access(self.magiskboot_path, os.X_OK),
        }

    def check_keys(self) -> Dict[str, bool]:
        return {
            "avb_key": self.avb_key.exists(),
            "ota_key": self.ota_key.exists(),
            "ota_cert": self.ota_cert.exists(),
        }
