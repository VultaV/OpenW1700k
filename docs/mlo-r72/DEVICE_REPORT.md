# r72 device installation and restoration checks — November 8, 2026

The exact published r72 image was installed with settings retained. SSH returned in 102.6 seconds. Live wpad, modules and the stock NPU 0.8 pair match the image hashes. All five preinstall configuration hashes match, pending UCI changes are empty, SSH key and Tailscale node identity are retained, and Tailscale is online.

The requested layout is restored: `OpenWrt_5G` has the 5+6 GHz MLD links; `OpenWrt_2G` remains an independent 2.4 GHz AP. The temporary iPhone compatibility AP is removed. The earlier LAN/Tailscale DNS interface fix is preserved. Both production APs are enabled and the Mac is back on the MLD with client mask 0x6. This does not rename or merge the 2.4 GHz SSID.

The Linux test-server path negotiated 2.5 Gbps; separate wired management negotiated 1 Gbps. Measurements bind both the actual Mac Wi-Fi address and en0, after confirmed AP/client readiness and at least 60 seconds of associated age.

| Mac MLO test | Duration | Average Mbps | Lowest interval Mbps | Zero intervals |
|---|---:|---:|---:|---:|
| Download | 30 s | 1971.0 | 1883.1 | 0 |
| Upload | 30 s | 1828.0 | 1792.0 | 0 |

A 32 MiB authenticated SSH upload/remote/download over Wi-Fi retained the same SHA256 throughout (4.21 seconds total). This is an integrity check, not an exhaustive DMA test or throughput benchmark. Wi-Fi-bound DNS queries, certificate-verified HTTPS and WAN ICMP 20/20 passed on both the main MLO AP and the standalone 2.4 GHz AP.

The first automatic 2.4 GHz join was not independently verified, so its network check did not run. That setup failure remains in private evidence. Retrying only this phase with the current router credentials verified association and passed the checks; the final Mac MLO mask is again 0x6. No firmware fault or stale-password cause was established from the first attempt.

Outside the authorized installation reboot, wired probes recorded 3578 active-link/router/server samples and 716 WAN/Proxmox samples with zero failures. The observation spans 3771.28 seconds including r71 build-time and r72 postinstall phases; maximum sampling gap was 5.08 seconds. The installation reboot is counted separately, and discrete probes cannot prove service between samples. The owned monitor has stopped.

Final CPU temperature was 61.8 C. The selected critical kernel-error filter matched no lines; watchdog/snapshot service, bridge hardware-offload table, wired endpoints and Tailscale were healthy. Experimental awake/PS trace parameters are off, NSTR peer empty, best-link and PS-gate corrections enabled. Private raw logs, backup and device identities are excluded from public assets.

This is a bounded Mac regression check. No new iPhone throughput test, full band-combination matrix, full OS sleep, weak-signal fallback or overnight run was performed. The thermal patch does not establish a fix for intermittent per-peer MLO transmission stalls. IRQ injection, driver unbind and probe-failure execution were not tested. GPIO PR26508 remains deferred for board-specific validation. Build warnings are recorded in README.md and BUILD_RESULT.json.

Source commit: `8e4d25a332`; immutable build tag: `mlo-r72-20261108` at `6ad7da164f04fd92c54ba67153197b96f3a2f023`. The original release assets describe the build-time snapshot; these DEVICE files are subsequent installation/test evidence. Full sanitized values are in DEVICE_TESTS.json.
