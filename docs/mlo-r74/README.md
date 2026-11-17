# W1700K r74 Tailscale update

r74 embeds Tailscale 1.104.7-r1 with Go 1.27.4 in the r73 firmware. The kernel and wireless packages use the r73 ABI. The OpenWrt startup service and `/etc/tailscale/` upgrade preservation list are inherited from r73.

Apply the two `feed-patches/` to the packages feed at the commit pinned in `build-manifest.json`, after the inherited r73 feed patches and before compilation. The Tailscale recipe follows the OpenWrt package build tags for client self-updating and flash appliances. Firmware builds and package management provide the update path. The source archive checksums and the exact upstream tag commit are recorded in the manifest.

See `BUILD_RESULT.json` and `IMAGE_CHECKS.json` for build and package verification. Device boot, identity migration, reconnect and subnet route forwarding have not been exercised on r74.
