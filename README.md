# AVB Builder & OTA Server

Automated EvolutionX custom ROM rebuild & signing pipeline with [avbroot](https://github.com/chenxiaolong/avbroot) and [Custota](https://github.com/chenxiaolong/Custota) OTA server. Keeps Google Pixel devices running custom ROMs with **hardware-backed locked bootloaders** and seamless over-the-air updates.

---

## Supported Devices

| Device | Codename | Upstream Source | Patch Mode |
|---|---|---|---|
| **Google Pixel 4** | `flame` | [0xsoul24/OTA (cnb)](https://github.com/0xsoul24/OTA) | KernelSU-Next / ReSukiSU (Kernel-integrated) |
| **Google Pixel 6a** | `bluejay` | [Evolution-X/OTA (vic)](https://github.com/Evolution-X/OTA) | Rootless / Custom boot |

---

## Architecture

```
 Upstream Repos (GitHub / CDN)
   ├── 0xsoul24/OTA (Pixel 4 flame)
   └── Evolution-X/OTA (Pixel 6a bluejay)
             │
             ▼
   [ AVB Builder Daemon ]  (Hosted on Proxmox node `indulgence`)
   ┌─────────────────────────────────────────────────────────────┐
   │ 1. Polls upstream JSON endpoints every 6 hours              │
   │ 2. Downloads upstream release ZIP with SHA256 verification  │
   │ 3. Patches & signs OTA package using `avbroot` & custom key │
   │ 4. Generates Custota `.csig` & `<device>.json` metadata     │
   │ 5. Generates EvolutionX `/builds/<device>.json` metadata    │
   │ 6. Automatically cleans raw ZIPs & prunes old builds        │
   │ 7. Exposes HTTP Range-capable streaming server & Web UI     │
   └─────────────────────────────────────────────────────────────┘
             │  (HTTP Range Streaming via Tailscale / LAN)
             ▼
   [ Custota on Phone ] ──> Android update_engine ──> Reboot into Locked Slot
```

---

## Quick Start

### 1. Place Your Signing Keys
Copy your `avbroot` keys into `data/keys/`:
```bash
data/keys/
├── avb.key         # AVB private signing key
├── ota.key         # OTA private signing key
├── ota.crt         # OTA certificate
└── avb_pkmd.bin    # AVB public key digest (for fastboot)
```
*(Or run `./scripts/setup_keys.sh` to generate or verify keys)*

### 2. Local Run (via Nix Flake)
```bash
# Check upstream for new updates
nix develop --command python3 -m src.main check

# View server, keys, tools, and disk status
nix develop --command python3 -m src.main status

# Run the OTA Server & Web UI (defaults to http://0.0.0.0:8085)
nix develop --command python3 -m src.main serve
```

### 3. Deploy to `indulgence` (Proxmox LXC)

Make sure you've expanded `indulgence` LXC disk in Proxmox (50GB+ recommended).

```bash
# Automated deployment script
./scripts/deploy_indulgence.sh indulgence
```

Or add the container declaratively to `nixos-config/nodes/indulgence/configuration.nix` (see [docs/NIXOS_INTEGRATION.md](docs/NIXOS_INTEGRATION.md)).

---

## Web Dashboard

Visit `http://100.64.0.131:8085` (Tailscale) or `http://192.168.106.242:8085` (LAN) in your browser:
- Real-time device build cards for Pixel 4 and Pixel 6a
- One-click **"Check Upstream Now"** and **"Build Update"** buttons
- Storage gauge and keys status
- Live build activity log terminal

---

## Guides & Documentation

- [Device Setup & Bootloader Locking Guide](docs/DEVICE_SETUP.md)
- [Custota Phone Setup Guide](docs/CUSTOTA_SETUP.md)
- [NixOS Integration for Indulgence](docs/NIXOS_INTEGRATION.md)

---

## Configuration Reference (`config.yaml`)

```yaml
server:
  host: "0.0.0.0"
  port: 8085
  base_url: "http://100.64.0.131:8085"
  data_dir: "./data"
  check_interval_hours: 6

tools:
  avbroot_path: "./bin/avbroot"
  custota_tool_path: "./bin/custota-tool"

keys:
  avb_key: "./data/keys/avb.key"
  ota_key: "./data/keys/ota.key"
  ota_cert: "./data/keys/ota.crt"

devices:
  flame:
    name: "Pixel 4"
    codename: "flame"
    upstream_url: "https://raw.githubusercontent.com/0xsoul24/OTA/cnb/builds/flame.json"
    branch: "cnb"
    patch_mode: "rootless"
    keep_builds: 2
    enabled: true

  bluejay:
    name: "Pixel 6a"
    codename: "bluejay"
    upstream_url: "https://raw.githubusercontent.com/Evolution-X/OTA/vic/builds/bluejay.json"
    branch: "vic"
    patch_mode: "rootless"
    keep_builds: 2
    enabled: true
```
