# Build the r31 integration snapshot

Use this branch and the feed commits in [R31_build-manifest.json](R31_build-manifest.json). The manifest records the built artifact, not later live acceptance. No clean-room or bit-for-bit reproducibility claim is made.

1. Follow the feed pinning/toolchain setup in [r29 BUILD.md](../mlo-r29/BUILD.md), including the libpfring feed patch.
2. Apply [the ovpn module-version feed patch](feed-patches/README.md).
3. Copy `docs/mlo-r30/r31.config` to `.config`. Use `docs/mlo-r30/overlay/` as `files/`. It contains public diagnostics/update helpers and the as-built manifest, not device configuration. Start with a clean overlay so old disable hooks are not carried over.
4. Run `make defconfig`, download sources, then the normal full OpenWrt build. [R31_BUILD_RESULT.json](R31_BUILD_RESULT.json) lists the nine successful stages. Darwin toolchain and host adjustments are recorded in the manifest.
5. Verify FIT board/UBI metadata, checksum, matching kernel/module ABI, package contents and preserved settings before deployment. Build verification does not prove successful boot.

Do not reuse modules from another kernel release or ABI. KEEP_TTL requires the complete matching kernel/module set. r31 retains the r30 ABI because their kernel/module bytes match.

Run from the repository root against the fully prepared kernel source:

```sh
python3 tests/test_bridge_conntrack_ownership.py "$KERNEL/net/bridge/netfilter/nf_conntrack_bridge.c"
python3 tests/test_bridge_ttl.py "$KERNEL"
python3 tests/test_bridge_flow_offload.py
```

Publication checks: ownership 7 cases/0 failures; TTL 12 structural checks and 2,091 extracted-C assertions/0 failures; generator 20 tests/0 failures or skips. Host harnesses stub platform/kernel calls and do not simulate hardware. Existing r29 driver/UI checks retain their documented limits.

The package enables nothing automatically. Its pair must refer to trusted, untagged bridge members; unsupported kernel/board, isolation/VLAN/ingress policy or legacy hooks prevent activation. The tested installation uses LAN2 and ap-mld0. Do not infer routed hardware-offload acceptance from these bridge-only results.

Public overlay shell files have trailing whitespace and extra EOF blank lines removed from their as-built copies. Shell syntax checks pass; this formatting difference is not a reproducible-image claim.
