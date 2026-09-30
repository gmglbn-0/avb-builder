# Custota Setup & Seamless A/B Updates

**Custota** is an open-source Android app designed specifically by the author of `avbroot` to perform seamless A/B OTA updates from custom OTA servers while keeping bootloaders locked.

---

## Why Custota?

- Runs as a system app via Magisk or KernelSU/KernelSU-Next.
- Never contacts unauthorized external servers.
- Uses Android's internal `update_engine` streaming API (writes updates in the background to the inactive A/B slot without needing full zip pre-download).
- Monitors the Virtual A/B snapshot merge process and alerts when safe to reboot.
- Supports custom server URLs directly via app settings!

---

## 1. Installation

1. Download the latest `Custota-vX.X.zip` Magisk/KernelSU module from:  
   [https://github.com/chenxiaolong/Custota/releases](https://github.com/chenxiaolong/Custota/releases)
2. Open your root manager app (**KernelSU**, **KernelSU-Next**, or **Magisk**).
3. Go to the **Modules** tab -> **Install from storage**.
4. Select the Custota zip file and reboot the phone.

---

## 2. Configuration

1. After rebooting, open the **Custota** app from your app drawer.
2. Grant any necessary root or notification permissions.
3. Tap the **Settings** gear icon in the top right.
4. In **OTA Server URL**, enter your server's endpoint:
   ```
   http://100.64.0.131:8085
   ```
   *(Or your custom domain / local IP, e.g. `http://192.168.106.242:8085`)*
5. Configure update preferences:
   - **Check interval**: Every 6, 12, or 24 hours (or manual only).
   - **Auto-install**: Optional (installs overnight in the background).
   - **Skip post-install scripts**: Recommended ON (speeds up update process).

---

## 3. How Updates Work Under the Hood

1. Custota fetches `http://100.64.0.131:8085/{device}.json` (e.g. `flame.json` or `bluejay.json`).
2. It detects the signed OTA zip URL and verifies the accompanying `.csig` digital signature using your `ota.crt`.
3. Custota connects to the OTA server and streams the update via HTTP `Range` requests directly to Android's `update_engine`.
4. `update_engine` writes the partitions into the inactive slot (Slot A -> Slot B or vice-versa).
5. Once complete, Custota prompts you to reboot.
6. The phone reboots into the new slot. Verified Boot checks the new slot with your `avb_custom_key`, succeeds, and boots into the updated EvolutionX ROM!
