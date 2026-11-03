# W1700K upstream news — 2026-11-03

Read-only public-source review against the r62 baseline last verified on November 2. No source integration, build, flash, router setting change or new performance test was performed.

## Most important new finding: a different NPU binary is now shipped

The latest inspected normal UBI2 release is `ubi2_2026.11.02_r38036-aa89ec25f3`, published **2026-11-03 07:58:08 KST**. Its pinned source is `aa89ec25f3efaa0a680c92da3b0b1095c0c6f2d6`.

Commit `15ff304cb43c2ae4aef9d426e615336f28cd8970`, dated November 3 05:03:37 KST, changes the EN7581+MT7996 recipe from the linux-firmware archive's files to repository-local files. The commit identifies its source as `zhengping-zhang/airoha-npu`.

That repository's commit `1df6a36f849ea52cadfc326ec5b583d658be630e` is dated October 21 and explicitly describes the files as a **v0.8 test version** for AN7581 Kite/Eagle. Do not describe it as a stable vendor release or infer that its version number makes it a proven improvement over the currently used 0.1111.

The actual two binaries were downloaded from both pinned sources and compared byte-for-byte:

| File | New bytes | New SHA256 |
|---|---:|---|
| `en7581_MT7996_npu_rv32.bin` | 125832 | `7068a987bb95e89129a69de10d598f234a4400023eb23aacc8eb377e5f0fe0ea` |
| `en7581_MT7996_npu_data.bin` | 3092 | `6fd9506e399ebb309801ac2ecc74d3e10fa66731afc828c76fde8a67b2153f49` |

Both match the declared source repository exactly. They differ from the November 2 device baseline:

| Existing file | Bytes | SHA256 |
|---|---:|---|
| RV32 program | 122336 | `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643` |
| Data | 3084 | `61a75afb052feed2ceb2f3023e16f50317c05c78f9c8e564bf01924ce39c7ec1` |

This updates the earlier state of knowledge: the October 6 check concerned identical official linux-firmware files, whereas this community build now deliberately selects different test binaries from another repository. A package date alone was not used to establish this change.

### Interaction with the local budget guard

The local `9999-z6` loader guard accepts only the old program/data size and hash pair. On the new pair, that guard would be **not applicable**: the loader's normal path copies the unmodified files and reports that condition. A hash mismatch alone does not reject loading in this implementation.

Do not transplant the old byte offset/instruction change into v0.8. This review did not disassemble the new firmware, validate its ABI, inspect its zero-budget path, or prove compatibility with the local driver/RED/token settings. No changelog establishing a repair for our measured stalls was obtained.

Sources:

- [Latest inspected UBI2 release](https://github.com/w1700k/builds/releases/tag/ubi2_2026.11.02_r38036-aa89ec25f3)
- [NPU selection change](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/15ff304cb43c2ae4aef9d426e615336f28cd8970)
- [Pinned binary origin](https://github.com/zhengping-zhang/airoha-npu/tree/1df6a36f849ea52cadfc326ec5b583d658be630e)

## New build baseline

| Component | r62 baseline last verified Nov 2 | Inspected released UBI2 source |
|---|---|---|
| Kernel | 6.18.59 | 6.18.60 |
| mt76 | `639e128702780b398c1c36782b77899ce6bcb1fa` + local patches | `0936617dc529ff9da0385221d3fa6de732231177`, recipe now points to `openwrt/mt76` |
| NPU files | Old 0.1111 pair, with the runtime budget guard | Different v0.8 test pair |

The UBI2 source branch had advanced further to `460968f8a5e7cda1fb359d2fdde646583d484840` (November 3 10:36 KST) when queried. The detailed recipe/file comparison above is pinned to the **released** build, not that later moving branch head. The image itself was not downloaded; its release API asset digest is `499e1a912a07567bbb038e534eac87e512c73474b2b7cf8117bb7b37200c73e5`.

The separate kernel73 and kernel73-oc variants also have fresh builds. Their existence is not a recommendation to replace our validated ABI or switch to overclocking.

## Relevant mt76 changes not in the r62 pin

These commits are dated **October 28**, not newly authored since yesterday. They were newly inspected in detail in this review and are included in the newer build baseline. The compare reports a diverged history (83 commits ahead, 1 behind); it is not a simple fast-forward update of the firmware fork.

| Commit | Verified change | Relevance / limitation |
|---|---|---|
| `d8d24d7cbf5d` | Avoid another MLD_SETUP when station links are only removed. The description documents that the remaining links can stop passing traffic even while TX completion looks successful. | Directly relevant to link removal/reconfiguration. Not evidence that our fixed-link attenuation stalls had this cause; the Fixes dependency and surrounding station-link changes must be reviewed. |
| `46b67e5b7c49` | Keep unicast MLO management frames on their selected link, avoiding requests/responses being transmitted on a removed link. | Relevant to Link Reconfiguration failures and disconnects. Requires the matching mac80211/hostapd control path. |
| `451f47376280` | For non-MLO 802.3 frames, do not interpret an unset MLO-link control field as link 0; use the station/WCID link. | A packet-loss fix, not automatic fastest-band selection. The shown MLO branch still retains TID-parity selection. |
| `59b149d24e27` | Share CCMP replay PN state across an MLD peer and seed it once per key installation. | Correctness/security change across links, not a demonstrated performance repair. |
| `7f2f67eebb54`, `eb9e675d4cfc`, `238538d7d1cf` | Flow-offload flush/idle/priority callbacks for WED/SCS/MSCS. | Potentially relevant architecture work, but applicability to our Airoha NPU path must be traced before claiming it fixes our bridge-flowtable behavior. |

The newest mt76 commit returned by the inspected history is still October 28 `0936617dc529`; no later commit appeared in that queried branch. The r61 plan already named this target. The `451f` diff explicitly retains `link_id = (tid % 2) ? seclink_id : deflink_id` for the MLO branch, so merely upgrading mt76 does not establish replacement of the local `0042` policy or successful 5/6→2.4 GHz fallback.

Commit sources:

- [Link removal stall](https://github.com/OpenWRT-fanboy/mt76-firmware/commit/d8d24d7cbf5dc30d52077ddbeccbeac5fdb569e8)
- [Management frame link](https://github.com/OpenWRT-fanboy/mt76-firmware/commit/46b67e5b7c49313d11b2b2d83df3c8025406d63e)
- [802.3 link selection](https://github.com/OpenWRT-fanboy/mt76-firmware/commit/451f4737628000d9f5ab910b56b8c86114ffc441)
- [MLD replay state](https://github.com/OpenWRT-fanboy/mt76-firmware/commit/59b149d24e2752dfc6ff076cbe92ebe1dd94256f)
- [Pinned comparison](https://github.com/OpenWRT-fanboy/mt76-firmware/compare/639e128702780b398c1c36782b77899ce6bcb1fa...0936617dc529ff9da0385221d3fa6de732231177)

## Other checked sources and limits

- `VultaV/OpenW1700k` still lists r59 as its newest public release. No r60–r62 publication was found in that listing.
- `hurryman2212/airoha-npu-fdk` still reports only its August 9 initialization commit. It is not the source of the newly selected v0.8 binaries.
- The inspected default branch of `hurryman2212/OpenW1700k-test` reports August commits; its EHT/beamforming/VLAN commits were already taken into our r60 candidate. This check does not assert that every branch or PR was audited.
- Both requested OpenWrt forum threads returned a non-retryable robots.txt block through web search. Their latest post bodies were not verified. This is not a finding that there is no forum news.
- This review does not establish that the official linux-firmware main branch changed; the confirmed new selection is the community build's alternate pair.

## Next integration boundary

Treat the v0.8 NPU pair and the newer wireless stack as separate experimental variables. Preserve the measured r62 baseline. Before any integration, review the new NPU ABI/guard behavior and the full mac80211/hostapd/wifi-scripts/mt76 dependency set. Then compare one change at a time using the same matrix and bridge-offload controls. Do not use a successful compile or a community commit title as proof that the original stall is repaired.

Local evidence: `artifacts/news-2026-11-03/evidence.json`, `npu-v08-hashes.json`, downloaded binary pair, and selected pinned source recipes. No private router logs or settings were published.
