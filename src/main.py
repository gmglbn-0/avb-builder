import argparse
import logging
import os
import sys
# pyrefly: ignore [missing-import]
import uvicorn
from pathlib import Path
from src.config import Config
from src.manager import BuildManager
from src.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("avb-builder")

def cmd_check(config: Config, manager: BuildManager):
    print("\nChecking upstream updates for configured devices...\n")
    results = manager.check_all()
    for codename, build in results.items():
        dev = config.devices[codename]
        state = manager.state.get("devices", {}).get(codename, {})
        has_update = state.get("update_available", False)
        if build:
            status_symbol = "UPDATE AVAILABLE" if has_update else "UP TO DATE"
            print(f"[{status_symbol}] {dev.name} ({codename}):")
            print(f"  - Upstream file: {build.filename}")
            print(f"  - Version:       v{build.version} ({build.buildtype})")
            print(f"  - Timestamp:     {build.timestamp}")
            print(f"  - Size:          {round(build.size / (1024**2), 1)} MB")
            print(f"  - Download URL:  {build.download_url}\n")
        else:
            print(f"[FAILED] Could not fetch upstream info for {dev.name} ({codename})\n")

def cmd_status(config: Config, manager: BuildManager):
    status = manager.get_full_status()
    print("\n" + "=" * 60)
    print("AVB BUILDER & OTA SERVER STATUS")
    print("=" * 60)
    print(f"Server Base URL: {status['server']['base_url']}")
    print(f"Data Directory:  {status['disk']['path']}")
    print(f"Storage Free:    {status['disk']['free_gb']} GB / {status['disk']['total_gb']} GB total")

    print("\n[Tools]")
    for tool, ok in status["tools"].items():
        print(f"  [{'OK' if ok else 'MISSING'}] {tool}")

    print("\n[Signing Keys]")
    for key, ok in status["keys"].items():
        print(f"  [{'OK' if ok else 'MISSING'}] {key}")

    print("\n[Devices]")
    for codename, dev in status["devices"].items():
        up = dev.get("upstream") or {}
        loc = dev.get("local") or {}
        print(f"  - {dev['name']} ({codename}):")
        print(f"      Status:   {'Update available' if dev['update_available'] else 'Current'}")
        print(f"      Local:    {loc.get('filename', 'None built yet')}")
        print(f"      Upstream: {up.get('filename', 'Not checked')}")
    print("=" * 60 + "\n")

def cmd_build(config: Config, manager: BuildManager, device: str, force: bool):
    if device not in config.devices:
        print(f"Error: Unknown device '{device}'. Configured: {list(config.devices.keys())}")
        sys.exit(1)

    print(f"\nStarting build workflow for {device} (force={force})...\n")
    manager.start_build(device, force=force)

    # Monitor job from CLI
    while True:
        job = manager.get_job(device)
        if not job:
            break
        print(f"\r[{job.status.upper()}] {job.percent}% - {job.message[:80]}", end="", flush=True)
        if job.status in ["completed", "failed"]:
            print("\n")
            if job.status == "completed":
                print(f"Build finished successfully for {device}.")
            else:
                print(f"Build failed for {device}: {job.error}")
            break
        import time
        time.sleep(1)

def cmd_serve(config: Config, manager: BuildManager):
    app = create_app(config, manager)
    print(f"\nStarting AVB Builder & OTA Server on http://{config.host}:{config.port}")
    print(f"Base URL for Custota: {config.base_url}")
    print(f"Data directory: {config.data_dir}\n")
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")

def main():
    parser = argparse.ArgumentParser(description="AVB Builder & OTA Server for EvolutionX")
    parser.add_argument("--config", "-c", help="Path to config.yaml", default=None)
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("check", help="Check upstream for new EvolutionX releases")
    subparsers.add_parser("status", help="Show system, tools, keys, and device status")
    subparsers.add_parser("serve", help="Run the HTTP OTA server, web dashboard, and scheduler")

    build_parser = subparsers.add_parser("build", help="Build and sign an OTA package for a device")
    build_parser.add_argument("device", help="Device codename (e.g. flame, bluejay)")
    build_parser.add_argument("--force", "-f", action="store_true", help="Force build even if already up to date")

    args = parser.parse_args()

    config = Config(args.config)
    manager = BuildManager(config)

    if args.command == "check":
        cmd_check(config, manager)
    elif args.command == "status":
        cmd_status(config, manager)
    elif args.command == "build":
        cmd_build(config, manager, args.device, args.force)
    elif args.command == "serve":
        cmd_serve(config, manager)
    else:
        # Default to serve
        cmd_serve(config, manager)

if __name__ == "__main__":
    main()
