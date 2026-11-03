# r63 — NPU v0.8 and focused MLO backports

This experimental candidate preserves the r62 kernel, wireless source pin and local MLO/PS/offload protections. It does not establish that the intermittent MLO stall, the 2.4 GHz-inclusive downlink stalls or the all-band association outage are fixed. Installation and hardware boot testing are pending.

## Changes from r62

- Replace only the EN7581 + MT7996 NPU firmware pair with the vendor-published **v0.8 test version**. The package is versioned `0.8-r1`; other linux-firmware packages retain their versions.
- Backport mt76 `451f47376280`: an 802.3-encapsulated non-MLO frame uses the station's actual link rather than an unset mac80211 MLO-link field.
- Backport `d8d24d7cbf5d`: removing links alone does not send a fresh MLD setup to firmware.
- Backport `46b67e5b7c49`: management frames for an MLD station retain their selected link.
- Backport `59b149d24e27`: all links of an MLD peer share CCMP replay counters; seed the counters once per key install rather than resetting them on each link. Both affected mt7996 and mt7925 callers are updated.
- mt76 package release **39**. Kernel **6.18.59-w1700k-mlo-r32** and mt76 source **639e128702780b398c1c36782b77899ce6bcb1fa** remain pinned. Existing r62 `mlo_best_link`, PS, DMA/descriptor, mailbox, TTL and offload patches remain.

The original NPU TX-budget guard applies only to its exact old firmware pair. The new pair does **not** match that identity, so it is copied unchanged and the guard logs **not applicable**. Applying the old instruction offset to the new binary would be invalid. No claim is made that the new firmware contains an equivalent budget fix or that its runtime behavior has been verified.

## Source provenance

- Firmware source: https://github.com/zhengping-zhang/airoha-npu/commit/1df6a36f849ea52cadfc326ec5b583d658be630e (v0.8 test version).
- Upstream firmware selection: https://github.com/OpenWRT-fanboy/OpenW1700k/commit/15ff304cb43c2ae4aef9d426e615336f28cd8970 .
- MLO patch origin: https://github.com/OpenWRT-fanboy/mt76-firmware/commit/451f4737628000d9f5ab910b56b8c86114ffc441 , https://github.com/OpenWRT-fanboy/mt76-firmware/commit/d8d24d7cbf5dc30d52077ddbeccbeac5fdb569e8 , https://github.com/OpenWRT-fanboy/mt76-firmware/commit/46b67e5b7c49313d11b2b2d83df3c8025406d63e , https://github.com/OpenWRT-fanboy/mt76-firmware/commit/59b149d24e2752dfc6ff076cbe92ebe1dd94256f .
- This release also records previously uncommitted r60–r62 sources and sanitized test reports. It does not retroactively identify the installed r62 module as reproduced: the older installed manifest had a differing 0042 patch hash. r63 records its own exact source and firmware identities.

## Host checks and limits

- Actual prepared MLO source: 20 checks pass with ASan/UBSan. Before the four fixes, the same 20-check suite reproduced five failures (802.3 link selection, management-frame link, remove-only setup, cross-link replay and peer PN preservation).
- Best-link selector: 10 checks pass.
- PS/AQL: pristine baseline 19/29 failures, patched 0/29; existing MLO PS suite 29 + 99 checks pass; existing active-link suite passes.
- Actual NPU loader/probe extracted C: 24 old-pair identity/error/readback boundary cases pass and 2 new-pair DT/default cases pass with ASan/UBSan. The two new cases verify exact byte copying and immutable input buffers, not NPU execution.
- Legacy `test_mt7996_link_transition.py` cannot extract `mt7996_sta_update_link_ids` from the current pin (removed before r63). Its result is **not a pass**; this historical harness was not rewritten for this release.
- Host fixtures do not verify radio timing, concurrency, NPU instruction execution, DMA hardware visibility or cold boot. No throughput, fallback or overnight stability result is attributed to r63.

Use the build manifest and BUILD_RESULT.json for the final source commit, packaged identities and image verification. Do not mix the mt76 package with a different kernel/module ABI.
