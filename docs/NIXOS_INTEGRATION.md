# Indulgence NixOS Configuration Integration

To declaratively run **AVB Builder & OTA Server** on your NixOS node `indulgence`, add the following snippet to:

`/home/gmglbn_0/git/gmglbn-0/nixos-config/nodes/indulgence/configuration.nix`

---

### 1. Update Firewall Allowed Ports

Add port `8085` to `allowedTCPPorts`:

```nix
  networking.firewall.allowedTCPPorts = [ 3000 3001 3005 8080 8085 ];
```

---

### 2. Add OCI Container Definition

In the container section (alongside `kaas-bot`, `once-tagger`, `firefly-iii`):

```nix
  # ── AVB Builder & OTA Server (EvolutionX + Custota) ──────────────────────
  virtualisation.oci-containers.containers.avb-builder = {
    image = "avb-builder:latest";
    ports = [ "8085:8085" ];
    volumes = [
      "/data/avb-builder:/data"
    ];
    environment = {
      AVB_DATA_DIR = "/data";
      AVB_PORT = "8085";
      AVB_HOST = "0.0.0.0";
      AVB_BASE_URL = "http://100.64.0.131:8085";
      # If your keys have a passphrase, uncomment and specify:
      # PASSPHRASE_AVB = "your_avb_passphrase";
      # PASSPHRASE_OTA = "your_ota_passphrase";
    };
  };
```

---

### 3. Add Directory Rules (systemd.tmpfiles.rules)

In the `systemd.tmpfiles.rules` list, add:

```nix
    "d /data/avb-builder 0755 gmglbn_0 users -"
    "d /data/avb-builder/keys 0700 gmglbn_0 users -"
    "d /data/avb-builder/storage 0755 gmglbn_0 users -"
    "d /data/avb-builder/www 0755 gmglbn_0 users -"
    "d /data/avb-builder/www/ota 0755 gmglbn_0 users -"
    "d /data/avb-builder/www/builds 0755 gmglbn_0 users -"
```

---

### 4. Build or Pull the Image on Indulgence

Once you've run `./scripts/deploy_indulgence.sh`, the image `avb-builder:latest` will be built on `indulgence`. Then you can rebuild the NixOS configuration:

```bash
nixos-rebuild switch --flake .#indulgence
```
