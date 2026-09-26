# r36 build and verification

Reuse the pinned toolchain/feed/overlay instructions in `../mlo-r34/BUILD.md`,
with the r36 source tag, `r36.config` and `build-manifest.json` here. The
existing fixed LuCI feed patch and overrides remain unchanged. Do not copy
private router backups or state into the image.

Run all nine make commands recorded in `BUILD_RESULT.json`. Existing successful
stage records are not a reason to skip make dependency checks. Verify with:

```sh
python3 docs/mlo-r36/verify-image.py BUILD IMAGE NEW_OUTPUT \
  docs/mlo-r36/build-manifest.json --baseline R35_ARTIFACT_DIRECTORY
python3 tests/test_mt76_npu_rx.py --source-dir "$MT76" --applied
```

The verified r35 baseline needs `build-manifest.json` and
`verified-image/{rootfs/,metadata.json,dtb,kernel.gz}`. Only `mt76.ko` may change;
kernel payload, other 73 modules, NPU/Wi-Fi firmware and wpad/LuCI must match
r35. The verifier also requires exact package ABI and the newly built package
payload. mt76 packages advance from r28 to r29 without changing the kernel
release `6.18.44-w1700k-mlo-r32` or ABI.

`--applied` extracts the functions from the actual prepared tree. Without that
option the test expects pristine mt76 `01367e60` and applies 0006/0029/0034 in a
temporary directory after demonstrating the original failures. The host fixture
is not a kernel ABI model, and its ordering checks are not real weak-memory
execution. Proposal logs explicitly distinguish intended contract failures
from sanitizer diagnostics; the build result finalizer rejects ASan/UBSan
errors in those logs. The generic test helper itself only checks exit codes
for negative controls, so read the diagnostic text when reusing it separately.

The two firmware evidence checks take explicit paths and only use Python's
standard library:

```sh
python3 docs/mlo-r36/check-tx-budget.py \
  --blob "$NPU_PROGRAM" --instructions "$DECODER_JSON"
python3 docs/mlo-r36/check-completion-pools.py \
  --blob "$NPU_PROGRAM" --instructions "$DECODER_JSON"
```

Use the unchanged image file `lib/firmware/airoha/en7581_MT7996_npu_rv32.bin`.
The expected SHA is recorded in each checker. The saved linear decoder JSON
contains `address`, `size`, `bytes`, `mnemonic`, `operands`; the decoder recipe
and version limits are in `../mlo-r34/FIRMWARE_FOLLOWUP_20260926.md`.
The public evidence includes raw selected anchors, byte/branch checks and
bounded arithmetic model results. It does not ship private captures, prove
full firmware control flow or execute a replacement firmware.

The unchanged r35 lifecycle/PS, NPU watchdog, TTL, conntrack, PPE, FDB and updater
UI checks are rerun against the built sources/image. These host/static checks
are distinct from boot, hardware, wireless and Air sleep/wake acceptance.
