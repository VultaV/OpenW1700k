# r72 — Register the EN7581 thermal IRQ after the thermal zone

r72 backports upstream commit `7efceedd23678cd58e98b2c64d4b2b7be03f6cf9` onto the existing Linux 6.18.59 tree. The IRQ handler uses the thermal-zone pointer. Requesting the IRQ in post_probe, after zone registration and drvdata setup, closes the early interrupt window and releases the IRQ before the zone during managed teardown. ADC and monitor setup retain their original position.

The kernel/module identity is `6.18.59-w1700k-mlo-r72`. Bridge-flow-offload 1.0-r9 admits this identity. The r71 mt76 r43, NPU RX publication fix, stock NPU 0.8 pair and six wireless firmware files are retained. This thermal fix does not establish resolution of the existing per-peer MLO transmission stalls.

The source-order check rejects the old driver and accepts the patched driver. The bridge-offload suite passed 22 tests. Full native build completed in 594.5 seconds with exit 0. FIT payload hashes, W1700K UBI2 layout, module identity, reserved NPU pool, firmware identity and private-state exclusion passed. The DTB matches r71. The generated source manifest precedes the build, with actual outcomes in BUILD_RESULT.json and IMAGE_CHECKS.json.

Three inherited feed recursive-dependency messages and the inherited ignored U-Boot empty-package cleanup error remain recorded. GPIO PR26508 is deferred pending board-specific pin and boot validation. Hardware interrupt injection and driver unbind were not exercised.

Device installation and bounded checks subsequently passed: see [DEVICE_REPORT.md](DEVICE_REPORT.md), [DEVICE_TESTS.json](DEVICE_TESTS.json) and DEVICE_SHA256SUMS. The requested 5+6 GHz MLO and separate 2.4 GHz layout is restored, with the temporary compatibility AP removed. Mac Wi-Fi download/upload averaged 1971/1828 Mbps for 30 seconds each without zero intervals. Both APs passed DNS/TLS/WAN checks. The intermittent MLO fault remains unresolved. Initial release build assets remain unchanged and describe the build-time snapshot.
