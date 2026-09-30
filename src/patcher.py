import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List
from src.config import Config
from src.models import DeviceConfig, UpstreamBuild, LocalBuild

logger = logging.getLogger("avb-builder.patcher")

class PatchError(Exception):
    pass

def compute_hashes_and_size(file_path: Path) -> Dict[str, Any]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    size = 0
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return {
        "sha256": sha256.hexdigest().lower(),
        "md5": md5.hexdigest().lower(),
        "size": size,
    }

def extract_and_patch_boot_with_ksu(
    config: Config,
    device: DeviceConfig,
    raw_ota_path: Path,
    work_dir: Path,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    """Extract boot.img from raw OTA and patch it with KernelSU-Next using ksud and magiskboot."""
    work_dir.mkdir(parents=True, exist_ok=True)

    msg = f"Extracting boot.img from {raw_ota_path.name}..."
    logger.info(msg)
    if log_callback:
        log_callback(msg)

    extract_cmd = [
        str(config.avbroot_path),
        "ota",
        "extract",
        "--input", str(raw_ota_path),
        "--partition", "boot",
        "-d", str(work_dir),
    ]
    res = subprocess.run(extract_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise PatchError(f"Failed to extract boot.img from OTA: {res.stderr}")

    extracted_boot = work_dir / "boot.img"
    if not extracted_boot.exists():
        raise PatchError(f"Extracted boot.img not found at {extracted_boot}")

    msg = f"Patching boot.img with KernelSU-Next (ksud)..."
    logger.info(msg)
    if log_callback:
        log_callback(msg)

    env = os.environ.copy()
    bin_dir = str(config.magiskboot_path.parent)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

    patched_boot_name = "boot_ksu.img"
    ksu_cmd = [
        str(config.ksud_path),
        "boot-patch",
        "-b", str(extracted_boot),
        "-o", str(work_dir),
        "--out-name", patched_boot_name,
    ]
    if device.kmi:
        ksu_cmd.extend(["--kmi", device.kmi])

    ksu_res = subprocess.run(ksu_cmd, capture_output=True, text=True, env=env)
    if ksu_res.returncode != 0:
        raise PatchError(f"ksud boot-patch failed: {ksu_res.stderr or ksu_res.stdout}")

    patched_boot = work_dir / patched_boot_name
    if not patched_boot.exists():
        candidates = list(work_dir.glob("kernelsu_boot*.img"))
        if candidates:
            patched_boot = candidates[0]
        else:
            raise PatchError(f"Patched KernelSU boot image not found in {work_dir}")

    msg = f"Successfully injected KernelSU-Next into {patched_boot.name}"
    logger.info(msg)
    if log_callback:
        log_callback(msg)

    return patched_boot

def patch_ota_with_avbroot(
    config: Config,
    device: DeviceConfig,
    raw_ota_path: Path,
    output_ota_path: Path,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    """Run avbroot ota patch to sign the OTA zip with custom AVB and OTA keys."""
    if not config.avbroot_path.exists():
        raise PatchError(f"avbroot binary not found at {config.avbroot_path}")
    if not config.avb_key.exists():
        raise PatchError(f"AVB key not found at {config.avb_key}")
    if not config.ota_key.exists():
        raise PatchError(f"OTA key not found at {config.ota_key}")
    if not config.ota_cert.exists():
        raise PatchError(f"OTA certificate not found at {config.ota_cert}")

    output_ota_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output_ota_path.with_suffix(output_ota_path.suffix + ".patching")

    cmd = [
        str(config.avbroot_path),
        "ota",
        "patch",
        "--input", str(raw_ota_path),
        "--key-avb", str(config.avb_key),
        "--key-ota", str(config.ota_key),
        "--cert-ota", str(config.ota_cert),
        "--output", str(temp_output),
    ]

    # Passphrase handling (files or env vars)
    env = os.environ.copy()
    pass_file = config.keys_dir / "passphrase.txt"
    avb_pass_file = config.keys_dir / "avb.pass"
    ota_pass_file = config.keys_dir / "ota.pass"

    if avb_pass_file.exists():
        cmd.extend(["--pass-avb-file", str(avb_pass_file)])
    elif pass_file.exists():
        cmd.extend(["--pass-avb-file", str(pass_file)])
    elif os.environ.get(config.avb_passphrase_env):
        cmd.extend(["--pass-avb-env-var", config.avb_passphrase_env])
    elif os.environ.get("PASSPHRASE"):
        env["PASSPHRASE"] = os.environ["PASSPHRASE"]
        cmd.extend(["--pass-avb-env-var", "PASSPHRASE"])

    if ota_pass_file.exists():
        cmd.extend(["--pass-ota-file", str(ota_pass_file)])
    elif pass_file.exists():
        cmd.extend(["--pass-ota-file", str(pass_file)])
    elif os.environ.get(config.ota_passphrase_env):
        cmd.extend(["--pass-ota-env-var", config.ota_passphrase_env])
    elif os.environ.get("PASSPHRASE"):
        env["PASSPHRASE"] = os.environ["PASSPHRASE"]
        cmd.extend(["--pass-ota-env-var", "PASSPHRASE"])

    ksu_work_dir = None
    try:
        # Root / Patch mode
        if device.patch_mode == "ksu-next":
            ksu_work_dir = config.temp_dir / f"ksu_{device.codename}_{int(time.time())}"
            patched_boot = extract_and_patch_boot_with_ksu(
                config=config,
                device=device,
                raw_ota_path=raw_ota_path,
                work_dir=ksu_work_dir,
                log_callback=log_callback,
            )
            cmd.extend(["--prepatched", str(patched_boot)])
        elif device.patch_mode == "prepatched" and device.prepatched_boot:
            cmd.extend(["--prepatched", str(device.prepatched_boot)])
        elif device.patch_mode == "magisk" and device.magisk_apk:
            cmd.extend(["--magisk", str(device.magisk_apk)])
        else:
            # Default to rootless if unspecified or if ROM already has KSU
            cmd.append("--rootless")

        msg = f"Executing avbroot: {' '.join(cmd)}"
        logger.info(msg)
        if log_callback:
            log_callback(msg)

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )

        if process.stdout:
            for line in process.stdout:
                clean_line = line.rstrip()
                logger.info(f"[avbroot] {clean_line}")
                if log_callback:
                    log_callback(f"[avbroot] {clean_line}")

        process.wait()
        if process.returncode != 0:
            if temp_output.exists():
                temp_output.unlink()
            raise PatchError(f"avbroot failed with exit code {process.returncode}")

        if temp_output.exists():
            temp_output.rename(output_ota_path)

        logger.info(f"Successfully generated signed OTA: {output_ota_path}")
        return output_ota_path
    finally:
        if ksu_work_dir and ksu_work_dir.exists():
            shutil.rmtree(ksu_work_dir, ignore_errors=True)

def generate_custota_csig(
    config: Config,
    signed_ota_path: Path,
    output_csig_path: Path,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    """Generate Custota signature (.csig) file using custota-tool gen-csig."""
    if not config.custota_tool_path.exists():
        raise PatchError(f"custota-tool not found at {config.custota_tool_path}")

    cmd = [
        str(config.custota_tool_path),
        "gen-csig",
        "--input", str(signed_ota_path),
        "--key", str(config.ota_key),
        "--cert", str(config.ota_cert),
        "--output", str(output_csig_path),
    ]

    env = os.environ.copy()
    pass_file = config.keys_dir / "passphrase.txt"
    ota_pass_file = config.keys_dir / "ota.pass"

    if ota_pass_file.exists():
        cmd.extend(["--passphrase-file", str(ota_pass_file)])
    elif pass_file.exists():
        cmd.extend(["--passphrase-file", str(pass_file)])
    elif os.environ.get(config.ota_passphrase_env):
        cmd.extend(["--passphrase-env-var", config.ota_passphrase_env])
    elif os.environ.get("PASSPHRASE"):
        env["PASSPHRASE"] = os.environ["PASSPHRASE"]
        cmd.extend(["--passphrase-env-var", "PASSPHRASE"])

    logger.info(f"Executing custota-tool gen-csig: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        logger.error(f"custota-tool gen-csig failed: {result.stderr}")
        raise PatchError(f"custota-tool gen-csig failed: {result.stderr}")

    logger.info(f"Successfully generated csig: {output_csig_path}")
    return output_csig_path

def update_custota_json(
    config: Config,
    device: DeviceConfig,
    relative_ota_location: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    """Generate or update the Custota update info JSON: <device>.json"""
    custota_json_path = config.www_dir / f"{device.codename}.json"

    cmd = [
        str(config.custota_tool_path),
        "gen-update-info",
        "--file", str(custota_json_path),
        "--location", relative_ota_location,
    ]

    logger.info(f"Executing custota-tool gen-update-info: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"custota-tool gen-update-info failed: {result.stderr}")
        raise PatchError(f"custota-tool gen-update-info failed: {result.stderr}")

    logger.info(f"Successfully updated Custota JSON: {custota_json_path}")
    return custota_json_path

def update_evolutionx_json(
    config: Config,
    device: DeviceConfig,
    upstream: UpstreamBuild,
    signed_ota_path: Path,
) -> Path:
    """Generate EvolutionX compatible builds/<device>.json"""
    evox_json_path = config.builds_dir / f"{device.codename}.json"
    evox_json_path.parent.mkdir(parents=True, exist_ok=True)

    hashes = compute_hashes_and_size(signed_ota_path)
    download_url = f"{config.base_url}/ota/{signed_ota_path.name}"

    evox_data = {
        "response": [
            {
                "maintainer": upstream.maintainer or "Self-Hosted avbroot",
                "currently_maintained": True,
                "oem": "Google",
                "device": device.name,
                "filename": signed_ota_path.name,
                "download": download_url,
                "timestamp": upstream.timestamp,
                "md5": hashes["md5"],
                "sha256": hashes["sha256"],
                "size": hashes["size"],
                "version": upstream.version,
                "buildtype": upstream.buildtype,
            }
        ]
    }

    with open(evox_json_path, "w") as f:
        json.dump(evox_data, f, indent=2)

    logger.info(f"Successfully updated EvolutionX JSON: {evox_json_path}")
    return evox_json_path

def prune_old_builds(config: Config, device: DeviceConfig):
    """Keep only the latest N signed builds for this device to prevent filling up the disk."""
    ota_files = sorted(
        config.ota_dir.glob(f"*{device.codename}*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if len(ota_files) > device.keep_builds:
        for old_file in ota_files[device.keep_builds:]:
            logger.info(f"Pruning old signed OTA: {old_file}")
            try:
                old_file.unlink(missing_ok=True)
                csig_file = old_file.with_name(old_file.name + ".csig")
                csig_file.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to delete {old_file}: {e}")
