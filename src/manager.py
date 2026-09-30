import asyncio
import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from src.config import Config
from src.models import UpstreamBuild, LocalBuild, DeviceConfig, JobProgress
from src.upstream import fetch_upstream_build
from src.downloader import download_file
from src.patcher import (
    patch_ota_with_avbroot,
    generate_custota_csig,
    update_custota_json,
    update_evolutionx_json,
    compute_hashes_and_size,
    prune_old_builds,
)

logger = logging.getLogger("avb-builder.manager")

class BuildManager:
    def __init__(self, config: Config):
        self.config = config
        self.jobs: Dict[str, JobProgress] = {}
        self.log_history: List[str] = []
        self.lock = threading.Lock()
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if self.config.state_file.exists():
            try:
                with open(self.config.state_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load state file: {e}")
        return {"devices": {}}

    def _save_state(self):
        with self.lock:
            try:
                with open(self.config.state_file, "w") as f:
                    json.dump(self.state, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save state: {e}")

    def append_log(self, message: str):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}"
        with self.lock:
            self.log_history.append(entry)
            if len(self.log_history) > 200:
                self.log_history.pop(0)

    def get_job(self, codename: str) -> Optional[JobProgress]:
        return self.jobs.get(codename)

    def check_device(self, codename: str) -> Optional[UpstreamBuild]:
        device = self.config.devices.get(codename)
        if not device or not device.enabled:
            return None

        self.append_log(f"Checking upstream updates for {device.name} ({codename})...")
        upstream = fetch_upstream_build(device)
        if not upstream:
            return None

        dev_state = self.state["devices"].setdefault(codename, {})
        dev_state["upstream"] = {
            "filename": upstream.filename,
            "download_url": upstream.download_url,
            "timestamp": upstream.timestamp,
            "version": upstream.version,
            "size": upstream.size,
            "sha256": upstream.sha256,
            "checked_at": time.time(),
        }

        # Compare with local signed build
        local_ts = dev_state.get("local", {}).get("timestamp", 0)
        has_update = upstream.timestamp > local_ts
        dev_state["update_available"] = has_update

        self._save_state()
        if has_update:
            self.append_log(f"Update available for {codename}: {upstream.filename} (v{upstream.version})")
        else:
            self.append_log(f"{codename} is up to date (current timestamp: {local_ts})")

        return upstream

    def check_all(self) -> Dict[str, Optional[UpstreamBuild]]:
        results = {}
        for codename in self.config.devices:
            results[codename] = self.check_device(codename)
        return results

    def start_build(self, codename: str, force: bool = False) -> bool:
        device = self.config.devices.get(codename)
        if not device:
            raise ValueError(f"Unknown device: {codename}")

        # Check if already running
        current_job = self.jobs.get(codename)
        if current_job and current_job.status in ["downloading", "patching", "generating_metadata"]:
            return False

        job = JobProgress(
            device=codename,
            status="starting",
            started_at=time.time(),
            message=f"Starting build for {device.name}...",
        )
        self.jobs[codename] = job

        thread = threading.Thread(
            target=self._run_build_thread,
            args=(device, job, force),
            daemon=True,
        )
        thread.start()
        return True

    def _run_build_thread(self, device: DeviceConfig, job: JobProgress, force: bool):
        codename = device.codename
        try:
            self.append_log(f"Starting build workflow for {device.name} ({codename})...")
            job.status = "checking"
            job.message = "Checking upstream build..."

            upstream = fetch_upstream_build(device)
            if not upstream:
                raise Exception(f"Failed to fetch upstream build info for {codename}")

            dev_state = self.state["devices"].setdefault(codename, {})
            local_ts = dev_state.get("local", {}).get("timestamp", 0)
            if not force and upstream.timestamp <= local_ts:
                job.status = "completed"
                job.message = f"{device.name} is already up to date."
                self.append_log(f"Skipping build for {codename}: already at latest version.")
                return

            # Destination paths
            raw_filename = upstream.filename
            raw_path = self.config.downloads_dir / raw_filename

            # Output signed filename: e.g. EvolutionX-17.0-...-flame-12.2-signed.zip
            signed_filename = raw_filename.replace(".zip", "-signed.zip")
            if "-signed.zip" not in signed_filename:
                signed_filename = f"{raw_filename}-signed.zip"
            signed_path = self.config.ota_dir / signed_filename
            csig_path = signed_path.with_name(signed_path.name + ".csig")

            # 1. Download
            job.status = "downloading"
            job.message = f"Downloading upstream zip: {raw_filename}..."
            self.append_log(f"Downloading {upstream.download_url}...")

            def download_progress(downloaded: int, total: int):
                job.downloaded_bytes = downloaded
                job.total_bytes = total
                if total > 0:
                    job.percent = round((downloaded / total) * 100, 1)

            download_file(
                url=upstream.download_url,
                destination=raw_path,
                expected_sha256=upstream.sha256 or None,
                expected_md5=upstream.md5 or None,
                progress_callback=download_progress,
            )

            # 2. Patch with avbroot
            job.status = "patching"
            job.percent = 0.0
            job.message = "Signing and patching OTA with avbroot..."
            self.append_log(f"Patching {raw_filename} with avbroot...")

            def log_callback(msg: str):
                self.append_log(msg)
                job.message = msg

            patch_ota_with_avbroot(
                config=self.config,
                device=device,
                raw_ota_path=raw_path,
                output_ota_path=signed_path,
                log_callback=log_callback,
            )

            # 3. Custota metadata (csig and update-info)
            job.status = "generating_metadata"
            job.message = "Generating Custota csig signature..."
            self.append_log(f"Generating Custota signature for {signed_filename}...")

            generate_custota_csig(
                config=self.config,
                signed_ota_path=signed_path,
                output_csig_path=csig_path,
                log_callback=log_callback,
            )

            # Relative path from root www/ to ota/
            relative_ota_loc = f"ota/{signed_filename}"
            update_custota_json(
                config=self.config,
                device=device,
                relative_ota_location=relative_ota_loc,
                log_callback=log_callback,
            )

            # 4. EvolutionX JSON metadata
            update_evolutionx_json(
                config=self.config,
                device=device,
                upstream=upstream,
                signed_ota_path=signed_path,
            )

            # 5. Clean up downloaded raw file to save disk space
            self.append_log(f"Cleaning temporary raw zip: {raw_path}...")
            try:
                if raw_path.exists():
                    raw_path.unlink()
            except Exception as e:
                logger.warning(f"Could not remove {raw_path}: {e}")

            # 6. Prune older builds
            prune_old_builds(self.config, device)

            # 7. Update state
            hashes = compute_hashes_and_size(signed_path)
            dev_state["local"] = {
                "filename": signed_filename,
                "relative_path": relative_ota_loc,
                "csig_filename": csig_path.name,
                "timestamp": upstream.timestamp,
                "version": upstream.version,
                "size": hashes["size"],
                "sha256": hashes["sha256"],
                "md5": hashes["md5"],
                "built_at": time.time(),
            }
            dev_state["update_available"] = False
            self._save_state()

            job.status = "completed"
            job.percent = 100.0
            job.message = f"Build completed successfully! Ready for OTA updates."
            self.append_log(f"Build completed for {device.name}: {signed_filename}")

        except Exception as e:
            logger.error(f"Build error for {codename}: {e}", exc_info=True)
            job.status = "failed"
            job.error = str(e)
            job.message = f"Build failed: {e}"
            self.append_log(f"Build FAILED for {codename}: {e}")

    def get_full_status(self) -> Dict[str, Any]:
        tools_status = self.config.check_tools()
        keys_status = self.config.check_keys()

        # Disk space in data dir
        disk_stats = shutil.disk_usage(self.config.data_dir)
        free_gb = round(disk_stats.free / (1024 ** 3), 2)
        total_gb = round(disk_stats.total / (1024 ** 3), 2)
        used_gb = round(disk_stats.used / (1024 ** 3), 2)

        devices_status = {}
        for codename, dev_cfg in self.config.devices.items():
            state_dev = self.state.get("devices", {}).get(codename, {})
            current_job = self.jobs.get(codename)
            devices_status[codename] = {
                "codename": codename,
                "name": dev_cfg.name,
                "enabled": dev_cfg.enabled,
                "upstream": state_dev.get("upstream"),
                "local": state_dev.get("local"),
                "update_available": state_dev.get("update_available", False),
                "job": current_job.to_dict() if current_job else None,
            }

        return {
            "server": {
                "base_url": self.config.base_url,
                "port": self.config.port,
                "check_interval_hours": self.config.check_interval_hours,
            },
            "disk": {
                "total_gb": total_gb,
                "used_gb": used_gb,
                "free_gb": free_gb,
                "path": str(self.config.data_dir),
            },
            "tools": tools_status,
            "keys": keys_status,
            "devices": devices_status,
            "recent_logs": self.log_history[-50:],
        }
