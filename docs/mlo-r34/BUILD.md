# r34 build inputs and verification

Use the r34 source tag and the three feed commits in `build-manifest.json`.
This is a reproducible source recipe, not a claim of a clean-room or
bit-for-bit reproducible image.

1. Follow `../mlo-r29/BUILD.md` for the toolchain, pinned feeds and libpfring
   patch. Apply the packages-feed ovpn patch from `../mlo-r30/feed-patches/`.
2. Apply `feed-patches/0003-luci-attendedsysupgrade-github-update.patch` to the
   clean pinned LuCI feed as described in `feed-patches/README.md`. Preserve any
   existing local feed changes before integrating it.
3. Copy `r34.config` to `.config`. Start with the public overlay from
   `../mlo-r30/overlay/`, then replace `files/etc/w1700k-mlo-repair` with this
   directory's `build-manifest.json`. No router credentials or Tailscale identity
   belong in the image.
4. Run the normal OpenWrt make stages in `BUILD_RESULT.json`. Run make on every
   attempt and let its dependency tracking decide what is current. Do not skip
   stages merely because an earlier JSON record says they succeeded.
5. Run `verify-image.py BUILD IMAGE NEW_OUTPUT build-manifest.json --baseline
   R33_ARTIFACT_DIRECTORY`. The baseline contains the verified r33 image's
   extracted files and manifest. A mismatch is a failure to investigate, not an
   instruction to relax the check.

r34 retains the r32 kernel release/ABI. Only the NPU and MT7996 modules may
change; the verifier requires the kernel payload and all other module bytes to
match r33, including the forwarding/TTL implementation. It also checks the
versioned NPU/mt76/UI packages, exact kernel dependencies, shipped UI behavior,
firmware identity, and absence of private Tailscale state.

New regressions, run against prepared sources from this build:

```sh
python3 tests/test_mt7996_link_lifecycle.py "$MT76"
python3 tests/test_airoha_npu_watchdog.py "$KERNEL"
node tests/test_attendedsysupgrade_images.js "$LUCI_VIEW"
```

The lifecycle/watchdog tests execute extracted real functions under ASan/UBSan
with kernel/firmware stubs. The UI test executes the view with inert RPC/DOM
substitutes. They do not prove concurrent radio behavior, full browser flows,
boot, throughput, or resolution of the Air sleep/wake stall. No further
wireless test or firmware installation is part of this build verification.
