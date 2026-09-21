# Build and check this snapshot

This branch preserves the tested source state; it is not rebased onto current
upstream. Building again is supported by the recorded inputs, but a clean Linux
or Actions build has not been performed for this publication. The tested image
was built on Darwin arm64 with GNU make4.4.1, GNU getopt and the existing toolchain.
Build dependencies and target setup follow the upstream OpenWrt instructions.

1. Checkout this branch. Pin feeds to the commits in `build-manifest-as-built.json`.
   Write a local `feeds.conf` using `src-git packages URL^COMMIT`, and likewise
   luci/routing, retaining the upstream URLs from `feeds.conf.default`.
2. Run `./scripts/feeds update -a`. Copy
   `docs/mlo-r29/feed-patches/0002-use-target-ar-for-bundled-libraries.patch` into
   `feeds/packages/libs/libpfring/patches/`, then `./scripts/feeds install -a`.
3. Copy `docs/mlo-r29/r29.config` to `.config`; copy the contents of
   `docs/mlo-r29/overlay/` into `files/`. This overlay has no router credentials.
   The embedded manifest describes the historical build; host PATH was generalized
   for publication. Regenerate it if changing sources or configuration.
4. Run `make defconfig`, `make download`, then `make -jN V=s` with an appropriate
   parallelism for the build host. Do not replace installed kernel modules with
   modules for a different kernel ABI. Do not flash a different board/UBI layout.

The reference image SHA256 is
`dea228e3b2772098b35afd518a510846a69db58918375eb03077799851c47808`.
Rebuilding in a new path/time/host may change its hash; this is not a bit-for-bit
reproducible-build claim. Verify FIT metadata, packages and board before any install.
No router-specific configuration, SSH keys or Tailscale identity is supplied.

## Host regression checks

Run from the repository root, with Node, Python3, C compiler, patch, GNU make:

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

`PRISTINE_MT76` is the unpacked01367e60 source. `PATCHED_MT76` is the prepared
mt76 source after the recipe patches. `BACKPORTS` is the prepared backports7.2 root; `MAC80211` is its
`net/mac80211` directory. The harnesses use actual extracted functions
with host shims; they do not emulate radio firmware or prove field stability.
The DFS fixtures are snapshots of the actual before/after hostapd dispatcher,
retaining the upstream file copyright/license header.

`PUBLISH_VALIDATION.json` and `check-*.log` record the checks rerun from this
publication checkout. Candidate/image/postinstall JSON are historical evidence;
`installed:false` in the candidate record predates the later postinstall pass.

The existing `VultaV/fastbuild` fork is separate. This upload does not change its
workflow source, trigger a firmware build, or upload anything to upstream.
