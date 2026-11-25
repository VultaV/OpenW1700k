# r75 — missing wireless fixes, Linux 6.18.64

This release starts from the installed r74 source and adds only the applicable missing fixes identified in the November 25 comparison. It is an experimental prerelease; the historical intermittent MLO problem is not proven resolved.

## Changes from r74

- Fix the inherited backports socket-type guard: Linux 6.18.57–60 define `sockaddr_unsized`, while 6.18.61–64 removed it. The retained size-check macro cannot detect this. Eleven version conditions pass.
- Linux 6.18.59 → 6.18.64, with ABI `6.18.64-w1700k-mlo-r75`. Refresh the existing generic patch stack, remove three patches already included by stable Linux, and rebuild every module. Preserve the NPU pool, QDMA isolation, thermal IRQ ordering and RX ownership protections.
- mt76 package r45: restore WCID association flags on reassociation; allow station key programming without a channel context; synchronize primary/secondary link selection with the MLD setup command; set QoS TID before the hardware-reorder return; support RX PN validation for CCMP-256/GCMP variants; retain GTK PN checking when an IGTK/BIGTK is installed; validate software-reordered frames before releasing the reorder lock.
- mac80211 package r15: keep AP VLANs out of driver restart callbacks, correct MLD station lookup on RX, and report airtime from the MLO station owner.
- hostapd package r11: reject a released BSS resource before dereferencing it, initialize the start configuration before the no-frequency path, avoid restarting an ongoing CAC, and release an MLD link ID through the shared reference helper.
- wifi-scripts package r6: correct the cell-density upper bound from 3 to 2.
- Include the already installed W1700K UniFi v0.3.0 port and its hostapd-utils/veth dependencies in the image, with explicit state preservation. This packages existing functionality so it survives this upgrade. New images default to disabled; the existing device's `enabled=1, apply=0` configuration must be preserved.

## Scope decisions

The user's current request is to apply missing fixes. General feed refreshes and unrelated package changes are excluded; feed commits and overrides remain pinned to r74. Tailscale 1.104.7 and UniFi 0.3.0 were still the latest stable releases checked on November 25.

The NPU program/data and six MT7996 firmware files are byte-identical to the latest public versions checked. Keep their exact verified r74 contents. The overlapping NPU RX reassembly proposal does not replace the local whole-chain/barrier/refill protections. Timeout-based token reclamation remains deferred pending DMA ownership evidence. Deferred-airtime opt-in (mac80211 508) and the newer PEER_MLD/fw_mld_idx command series are not imported. The secondary-link backport is adapted to this baseline's existing STA_REC_MLD primary-WCID encoding and preserves the local data-link selector.

## Reproduction and verification

Use `r75.config` and `build-manifest.json`, the pinned feeds and inherited feed patches, then the normal OpenWrt build documented in `docs/host-fixes-20261003/README.md`. The native host is Darwin arm64 with GNU make 4.4.1 and Go 1.27.4. Place the manifest at `files/etc/w1700k-mlo-repair` before generating the root filesystem. All source hashes, new backport commits and package releases are pinned in the manifest.

`HOST_CHECKS.json` describes host fixtures and limits. It includes 63 PN/control-path checks, 36 link-pair/TLV combinations with primary/removal cases, negative r74 controls, 22 bridge tests, RX/NPU regressions and DFS/EML/TXFREE checks. Host fixtures do not execute firmware, radio, concurrent locks or RCU. The older lifecycle fixture no longer matches the r74 API and is explicitly not counted as a pass; current link-pair/TLV functions are extracted directly instead.

`BUILD_RESULT.json`, `IMAGE_CHECKS.json` and `SHA256SUMS` describe the finished image. Installation and service checks, when performed, are documented separately in `DEVICE_REPORT.md` and `DEVICE_TESTS.json`. A successful remote boot and basic network checks do not establish iPhone app performance, weak-signal fallback, sleep/wake or overnight stability.

Only the `gemtek,w1700k-ubi` UBI2 profile is supported. Use a normal settings-preserving sysupgrade and verify its device check. Never mix r74 and r75 kernel modules. Backups, keys, Tailscale node state, UniFi adoption state and raw device identifiers are private and are not release assets.
