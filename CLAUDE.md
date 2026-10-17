# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

Think in English, but answer the user in Korean (영어로 생각하고 답변만 한글로 해).

## What this is

An OpenWrt build tree forked for the **Gemtek W1700K** (Airoha AN7581, MT7996 Wi-Fi 7) that investigates Wi-Fi 7 **MLO** (Multi-Link Operation) stalls. It is experimental, and the MLO problem is **not proven solved**. The current state, test results and failed hypotheses live in `docs/mlo-r29/README.md`, which is written in Korean. Read it before you change MLO-related code, and don't describe a fix as a confirmed solution.

The default and working branch is `codex/mlo-r30-bridge-offload` (r30 bridge offload through the r53 release, kernel 6.18.55). Per-release records are in `docs/mlo-r*/` and `docs/releases/`. `codex/mlo-r29-progress-20260921` keeps the exact tested r29 source state and is deliberately **not rebased** onto newer upstream.

## Build (standard OpenWrt, pinned inputs)

The current procedure is `docs/host-fixes-20261003/README.md` section 7, with the config and manifest of the release being built (r53 at the time of writing: `docs/mlo-r53/`). `docs/mlo-r29/BUILD.md` describes the historical r29 build. In short:

1. `cp feeds.conf.release feeds.conf` (the pinned feed commits; they must match `feeds` in `docs/mlo-r53/build-manifest.json`).
2. Run `./scripts/feeds update -a`, apply the feed patches listed in that README (libpfring AR patch, `docs/mlo-r34/feed-patches/`, `docs/host-fixes-20261003/feed-patches/`), then `./scripts/feeds install -a`.
3. `cp docs/mlo-r53/r53.config .config`, then `rm -rf files && mkdir files && cp -R docs/mlo-r30/overlay/* files/ && cp docs/mlo-r53/build-manifest.json files/etc/w1700k-mlo-repair`. Do not use `docs/mlo-r29/overlay`: its `github_fetch` needs jq regex support the image's jq lacks.
4. Run `make defconfig && make download && make -jN V=s`.

To rebuild a single package, use `make package/kernel/mt76/{clean,compile} V=s`, and the same form for `package/network/services/hostapd`.

The tested image was built on **Darwin arm64** with GNU make 4.4.1 and GNU getopt. Some patches exist only so the macOS host can build: `package/boot/arm-trusted-firmware-airoha/patches/0002-use-portable-host-headers.patch` and the libpfring AR patch. Never flash an image built for a different board or UBI layout. Never mix kernel modules across kernel ABIs.

## Host regression tests (`tests/`)

These tests don't use a framework. Each script extracts real functions from the patched sources, compiles them with host shims and runs the cases. Run them from the repo root:

```sh
node tests/test_mlo_ui.js
python3 tests/test_image_metadata.py
python3 tests/test_hostapd_mld_reassoc.py
python3 tests/test_hostapd_dfs_pending_link.py
python3 tests/test_mt76_npu_rx.py --source-dir "$PRISTINE_MT76"
python3 tests/test_mt76_ps_wake.py --source-dir "$PRISTINE_MT76" --mac80211-dir "$BACKPORTS"
python3 tests/test_mt7996_mlo_ps.py --source-dir "$PATCHED_MT76" --mac80211-dir "$MAC80211"
python3 tests/test_mt7996_active_link.py "$PATCHED_MT76/mt7996" --tx-errors
```

What the variables point to:

- `PRISTINE_MT76`: the unpacked mt76 source at the pinned `PKG_SOURCE_VERSION` (`639e1287` since r51). These tests apply the recipe patches themselves, show the baseline failing, then show it passing once patched.
- `PATCHED_MT76`: the prepared mt76 build dir after patches.
- `BACKPORTS`: the prepared backports 7.2 root.
- `MAC80211`: the `net/mac80211` directory inside `BACKPORTS`.

All of these come from a build tree (`build_dir/...`).

`test_mt7996_mlo_ps.py` reuses helpers from `test_mt76_ps_wake.py` through `runpy`. It also extracts code between literal source markers, such as `static bool mlo_ps_gate_fix = true;`, so renaming or reflowing those anchors in a patch breaks the test. The hostapd DFS test uses the before and after snapshots in `tests/fixtures/hostapd-dfs/`. The expected output of each test is recorded in `docs/mlo-r29/check-*.log`.

These harnesses don't emulate radio firmware, and passing them doesn't prove field stability.

## Device testing

`.device/mac-wifi-check.sh` runs the Mac Wi-Fi regression check (optional reconnects, MLO link state, iperf3 4-stream 30 s down/up, offloaded flows, kernel warnings). It refuses to run when the route to the iperf3 server does not leave through Wi-Fi: a wired adapter ranked first or a Tailscale subnet route for the LAN silently takes the test elsewhere. Close System Settings' Wi-Fi pane while measuring, because its scans stall the link. macOS runs a background roam scan about 17 s after joining that stalls the link for about 16 s (`docs/mlo-r53/JOIN_DIP_20261017.md`), so the script waits 40 s after reconnects.

## Where the fork's changes live

- **mt76 driver**: `package/kernel/mt76/Makefile` pins `OpenWRT-fanboy/mt76-firmware@639e1287` (2026-10-08) with `PKG_RELEASE=36` (r29 shipped `01367e60` release 26). The patches are in `package/kernel/mt76/patches/`, and the numbering has gaps. Patches that change behaviour:
  - 0006 and 0029: NPU RX chain and DMA ownership ordering
  - 0008: wake PS TXQs after AQL return
  - 0012: rate-control PHY from the active link
  - 0015: shared-TXQ PS gate (`mlo_ps_gate_fix`)

  Most of the rest are diagnostics (per-link PS/TX/BA/MCU tracing and counters). The experiments 0020 (`nstr_test_peer`) and 0023 (`mlo_tx_awake_test`) are module params that default to empty or OFF and must stay OFF. Forcing the awake-link choice measurably hurt throughput.
- **hostapd**: these three patches in `package/network/services/hostapd/patches/` are the fork's:
  - `999-preserve-link-id-for-unknown-station.patch`
  - `9999-reset-expired-mld-before-link-setup.patch`
  - `9999-deliver-dfs-state-to-unconfigured-links.patch`

  The `mtk-*` patches there come from MediaTek's SDK.
- **LuCI apps**: `package/luci-app-mlo` and `package/luci-app-wifi7`, tested by `test_mlo_ui.js`. The `luci-app-airoha-*`, `luci-app-w1700k-fancontrol` and `luci-app-netspeedtest` apps were added for this board.
- **Target**: `target/linux/airoha` (kernel 6.18, `patches-6.18/`). The device is `Device/gemtek_w1700k-ubi` in `target/linux/airoha/image/an7581.mk`, and the DTS is `an7581-w1700k-ubi.dts`.
- **Build-system fix**: `scripts/json_overview_image_info.py` handles image metadata under parallel make and is tested by `test_image_metadata.py`.
- **Rootfs overlay**: `docs/mlo-r30/overlay/` holds debug scripts and the CGI scripts for firmware fetch and check (`docs/mlo-r29/overlay/` is the historical r29 copy). It is shipped through `files/`. It deliberately contains no router credentials, keys or Tailscale state, so keep it that way.

## Conventions

- Upstream OpenWrt style applies. Commits need a sign-off (`git.alwaysSignOff`). Files use LF line endings, with no trailing whitespace except in `.diff` files.
- If you change sources or the config, regenerate the manifests and verification JSON in `docs/mlo-r29/`. Otherwise they keep describing the historical build.
- `VultaV/fastbuild`, the CI build fork, is separate. Nothing in this repo triggers it.
