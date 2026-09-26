# r35 build inputs and verification

Follow the pinned toolchain/feed/overlay procedure in `../mlo-r34/BUILD.md`,
using the r35 source tag, `r35.config`, and this directory's
`build-manifest.json`. The existing LuCI feed patch remains in
`../mlo-r34/feed-patches/`; its source and package version do not change.

Run all nine make commands recorded in `BUILD_RESULT.json`. Do not skip a
command based on an earlier successful JSON entry. Then run:

```sh
python3 docs/mlo-r35/verify-image.py BUILD IMAGE NEW_OUTPUT \
  docs/mlo-r35/build-manifest.json --baseline R34_ARTIFACT_DIRECTORY
```

The verified r34 baseline must include its manifest and extracted image.
Its layout is `build-manifest.json` and
`verified-image/{rootfs/,metadata.json,dtb,kernel.gz}`. Keep the verified
baseline's metadata and manifest together with its extracted payloads.
The kernel release remains `6.18.44-w1700k-mlo-r32`, and its exact APK ABI
dependency must match r34. Only `mt7996e.ko`
may change; the compressed kernel, other modules, firmware and all wpad/LuCI
files must remain byte-identical to r34. Exact package dependencies and the
new module's identity against the built package payload are also checked.

Run the new checks against this build's prepared sources:

```sh
python3 tests/test_mt7996_link_transition.py --source-dir "$MT76" \
  --mac80211-dir "$BACKPORTS/net/mac80211"
python3 tests/test_mt7996_forward_path.py "$MT76"
python3 tests/test_mt7996_link_lifecycle.py "$MT76" all
```

The transition and forward-path host tests execute real extracted functions
with kernel/firmware substitutes and controlled interleavings. They do not
prove hardware concurrency, existing PPE binding invalidation, failed-link
rollback recovery, bootability or Air sleep/wake stability. No additional
wireless test or device installation is part of this verification.
