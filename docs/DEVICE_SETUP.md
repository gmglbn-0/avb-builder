# Device Setup & Bootloader Locking Guide

This guide covers setting up your **Pixel 4 (`flame`)** and **Pixel 6a (`bluejay`)** with custom AVB keys to keep bootloaders locked with EvolutionX ROM.

---

## Critical Safety Warning

> [!CAUTION]
> **ALWAYS KEEP "OEM UNLOCKING" ENABLED IN DEVELOPER OPTIONS.**  
> If you have a custom ROM or root with a locked bootloader and an update or module ever fails to boot, leaving `OEM Unlocking` ON allows you to run `fastboot flashing unlock` from fastboot to recover your phone. If you disable OEM unlocking and verified boot fails, the device will be permanently hard-bricked.

---

## 1. Key Formats

You should have:
- `avb.key`: Private key for signing AVB metadata (`vbmeta`, partition descriptors).
- `ota.key` & `ota.crt`: Private key and certificate for signing OTA packages.
- `avb_pkmd.bin`: The binary digest of `avb.key` that the hardware bootloader checks against.

If you don't have `avb_pkmd.bin`, generate it from `avb.key`:
```bash
./bin/avbroot pkmd generate -k path/to/avb.key -o avb_pkmd.bin
```

---

## 2. Flashing the Custom AVB Key

### Pixel 4 (`flame`)
1. Reboot phone into fastboot mode (`adb reboot bootloader` or Hold `Power` + `Volume Down`).
2. Verify connection:
   ```bash
   fastboot devices
   ```
3. Flash your custom AVB public key digest into hardware trust storage:
   ```bash
   fastboot flash avb_custom_key avb_pkmd.bin
   ```

### Pixel 6a (`bluejay`)
1. Reboot into fastboot mode:
   ```bash
   adb reboot bootloader
   ```
2. Flash custom key:
   ```bash
   fastboot flash avb_custom_key avb_pkmd.bin
   ```
   *(Note: Pixel 6a also accepts `fastboot flashing set-active-user-key avb_pkmd.bin`)*

---

## 3. Initial ROM Installation (First Time)

Before locking the bootloader, the system partitions on the device must be signed with your `avb.key`:

1. Build your first signed OTA package using `avb-builder`:
   ```bash
   # In avb-builder:
   python3 -m src.main build flame
   python3 -m src.main build bluejay
   ```
   The output zip will be placed in `data/www/ota/<filename>-signed.zip`.

2. Reboot the phone into Recovery mode:
   ```bash
   adb reboot recovery
   ```
   *(If you see "No command", hold `Power` and tap `Volume Up` once).*

3. Sideload the signed OTA:
   ```bash
   adb sideload data/www/ota/EvolutionX-...-signed.zip
   ```

4. Reboot to bootloader:
   ```bash
   fastboot reboot bootloader
   ```

5. **Lock the bootloader**:
   ```bash
   fastboot flashing lock
   ```
   On your phone screen, use the volume buttons to select **"LOCK THE BOOTLOADER"** and press the power button to confirm. (Note: Locking or unlocking triggers a factory wipe on first lock).

6. Boot the device!
   - On boot, you will see a yellow warning screen indicating that the device is running a custom operating system with your custom key.
   - The bootloader verifies the signature against your hardware-flashed `avb_custom_key`.
   - Android will boot up normally!

---

## 4. Reverting to Stock (If Ever Needed)

To return the phone to full factory stock:
1. `fastboot flashing unlock`
2. Erase custom key:
   ```bash
   fastboot erase avb_custom_key
   ```
3. Flash the official Google factory image.
