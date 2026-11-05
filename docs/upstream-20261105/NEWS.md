# W1700K upstream review — November 5, 2026

Public sources checked November 5 around 10:30 KST. Compared against the current local r65 source at `422905a0ccc0f1440be0546c1c419258a889e176`, including its immutable build manifest. This is an information/source comparison: no production patch, build, installation, router query/configuration, or performance experiment was performed in this review.

## Result

A new normal UBI2 image is available. The highest-priority newly reviewed item is the reworked **NPU coherent DMA window PR**, followed by a review of the **QDMA hard-IRQ locking/counter differences**. The new community image's NPU firmware bytes are identical to r65. Several newly dated community commits contain fixes already present in r65. None of these findings establishes the cause of r65's initial 5-second TCP pause or its one slow TCP flow.

## Latest normal UBI2 release

- Tag: `ubi2_2026.11.05_r38160-5224315c8a`.
- Published: **2026-11-05 09:36:55 KST** (00:36:55 UTC).
- Pinned source: `OpenWRT-fanboy/OpenW1700k@5224315c8a25bb2558834924b7958354d7aae55a`.
- Sysupgrade image: `openwrt-airoha-an7581-gemtek_w1700k-ubi-squashfs-sysupgrade.itb`, 22,475,583 bytes.
- GitHub API image digest: `3ba811cb783c5ea8bde4b6cb22d02cad3b8b9e1acea2f80e60e8e3bfa5a32eab`. This is release metadata; the full image was not downloaded or verified.
- New source kernel: **6.18.60**, versus r65 **6.18.59**. New mt76 pin: **0936617dc529ff9da0385221d3fa6de732231177** (October 28), versus r65 **639e128702780b398c1c36782b77899ce6bcb1fa** plus local backports. The October 28 pin is the same target inspected November 3, not a new mt76 release today.
- Separate kernel73/overclock variants were listed; they were not selected for integration or tested.

Sources: [release](https://github.com/w1700k/builds/releases/tag/ubi2_2026.11.05_r38160-5224315c8a), [kernel recipe](https://github.com/OpenWRT-fanboy/OpenW1700k/blob/5224315c8a25bb2558834924b7958354d7aae55a/target/linux/generic/kernel-6.18), [mt76 recipe](https://github.com/OpenWRT-fanboy/OpenW1700k/blob/5224315c8a25bb2558834924b7958354d7aae55a/package/kernel/mt76/Makefile).

## 1. Reworked NPU DMA PR — high-priority integration review

[OpenWrt PR #25928](https://github.com/openwrt/openwrt/pull/25928) is **open and unmerged**, with head `23d295c6cb760da37e958aec725024bd3f25f527`, committed **November 4 00:34:38 KST**. This is a change from the older October watch checkpoint; it is not a change authored November 5.

The current version confines **coherent** NPU allocations to physical DRAM `0x80000000–0xbfffffff`. It adds a `shared-dma-pool`/`no-map` region, 1 MiB normally and **16 MiB for WLAN**, and attaches it to the NPU device. The author describes NPU aliasing above that address window on 2 GiB boards and reports roughly 10.7 MiB of coherent allocations with MT7996.

Important distinction from the old hold note: this version **retains and depends on the coherent-mailbox patch**. It attaches the reserved pool before mailbox allocation and also covers mt76 NPU rings/RRO/TXD buffers because mt76 uses the NPU device for DMA. It leaves streaming packet mappings alone; the author's reported penalty for a restricted/bounce pool is not a performance gain measured in our setup.

Local r65 comparison:

- Existing `924-net-airoha-npu-use-coherent-mailbox-dma.patch` is retained in our tree.
- The prepared driver uses `dma_set_mask_and_coherent(..., DMA_BIT_MASK(32))` and `dmam_alloc_coherent()` for mailbox buffers, but does not attach this optional NPU coherent pool.
- `an7581.dtsi` / `an7581-npu-wlan.dtsi` have no `npu_dma` pool or `"dma"` memory region. The PR changes all of these together, including memory-region naming (`binary` to `firmware`), so applying only its driver file is incomplete.
- The prepared r65 kernel has `CONFIG_OF_RESERVED_MEM`, `CONFIG_DMA_DECLARE_COHERENT`, and `CONFIG_DMA_COHERENT_POOL` enabled. That is a prerequisite check, not runtime validation of the PR.

Review the complete DTS/driver change and reserved-memory layout before an experimental build. It is a credible address-correctness candidate, **not a confirmed explanation for our two TCP outliers**. Actual board memory layout and allocation addresses would need separate verification.

Sources: [current PR diff](https://github.com/openwrt/openwrt/pull/25928/files), [current commit](https://github.com/openwrt/openwrt/commit/23d295c6cb760da37e958aec725024bd3f25f527), [Airoha confirmation linked by the author](https://lore.kernel.org/r/atCRsquzA1UxSpCc@mediatek.com).

## 2. QDMA/NPU stability refresh — core fixes already present, smaller fork patch differs

Community commit [e0da9590bb](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/e0da9590bbfd937199371b77ab5018d7d2e92fa3), dated November 5 06:59:30 KST, contains source-port routing, RX IRQ mask and mailbox retry changes. These core fixes are **already in r65's build manifest and prepared source**:

- Pingpong/NPU source ports map to GDM1 instead of being rejected.
- `RX_IRQ0_BANK_PIN_MASK` is `0xbb9f`, enabling the additional queue IRQ bits.
- WLAN mailbox setup uses retries with the shorter per-attempt polling limit.

The material difference is what the refreshed community patch **omits**:

- r65's `992-20-net-airoha-stability.patch` changes `spin_lock_bh()` to `spin_lock_irq()` and adds per-packet queue counters. The community adaptation leaves upstream BH locking and removes those counters, explicitly citing the per-packet hard-IRQ cost and lack of a reproduced W1700K race.
- r65 retries the optional BA-node setup too; the community adaptation leaves that command single-shot.
- The TRTCM retry mechanism is already supplied locally by patch187; adding an older duplicate workaround is unnecessary.

Review whether the extra r65 hard-IRQ masking is required for any actual caller before removing it. This is a driver latency/CPU candidate, not a measured improvement or a proven fix for the 385Mbps flow.

Local files: `target/linux/airoha/patches-6.18/992-20-net-airoha-stability.patch`, `992-21-net-airoha-npu-init-stability.patch`, and `187-v7.3-net-airoha-Add-retry-mechanism-to-airoha_qdma_set_tr.patch`.

## 3. TXFREE truncation cleanup — already included

[Community commit a644370737](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/a644370737dde845f24544b60975a96e7eb3e00a) changes a malformed/truncated TXFREE event's descriptor-loop overrun from an early `return` to `break`, allowing accumulated buffers/tokens and the TX worker tail to be handled normally. It also removes the WARN splat.

r65 already has the same functional change in `package/kernel/mt76/patches/0005-wifi-mt76-mt7996-guard-txfree-overrun.patch`; the prepared `mt7996/mac.c` also contains the `break`. A new community commit date does not make this a newly missing repair in r65.

## 4. NPU firmware — no new bytes in the inspected supply/build

The latest inspected UBI2 source still embeds the **v0.8 test pair** from `zhengping-zhang/airoha-npu@1df6a36f849ea52cadfc326ec5b583d658be630e` (October 21). Both files were actually downloaded from the new release's pinned source and compared byte-for-byte with the r65 source files:

| File | Bytes | SHA256 | Compared with r65 |
|---|---:|---|---|
| `en7581_MT7996_npu_rv32.bin` | 125832 | `7068a987bb95e89129a69de10d598f234a4400023eb23aacc8eb377e5f0fe0ea` | identical |
| `en7581_MT7996_npu_data.bin` | 3092 | `6fd9506e399ebb309801ac2ecc74d3e10fa66731afc828c76fde8a67b2153f49` | identical |

The supplier repository's default branch still has the same October21 commit. The FDK repository's default branch still has its August9 initialization commit. This review does not establish the state of every vendor branch or the official linux-firmware repository. The old identity-specific budget guard is still not applicable to this v0.8 pair.

Sources: [binary supplier](https://github.com/zhengping-zhang/airoha-npu/commit/1df6a36f849ea52cadfc326ec5b583d658be630e), [files in the pinned new build source](https://github.com/OpenWRT-fanboy/OpenW1700k/tree/5224315c8a25bb2558834924b7958354d7aae55a/package/firmware/linux-firmware/files/airoha), [FDK](https://github.com/hurryman2212/airoha-npu-fdk).

## 5. MLO/6GHz changes and preservation of our DFS fixes

[Commit12745c130b](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/12745c130bf03b385722ac72677c157ffd98967b) adds EHT beamforming defaults to the legacy shell configuration path and an explicit 6GHz exemption to `hostapd_is_dfs_required()`.

- r65 uses `CONFIG_WIFI_SCRIPTS_UCODE=y`. Its schema already defaults all three EHT beamforming flags to true and its ucode generator filters them by advertised capabilities. Applying the shell patch alone does not change that active r65 path.
- r65's `hostapd_handle_dfs()` already exempts6GHz, but its separate `hostapd_is_dfs_required()` helper lacks the new explicit check. This is a small defensive candidate for review/testing; it is a different path from the driver's cross-radio radar bug.
- The new build's pinned mt76 source still calls `ieee80211_radar_detected(mphy->hw, NULL)`. The checked community mt76 patch list does not contain r64's radio-context scoping patch, and its hostapd patch list lacks r65's narrower-channel fallback patch. Do not assume the new image preserves our tested DFS behavior. The new image was not boot-tested here.
- `openwrt/mt76` and the firmware fork still expose October28 `0936617dc5` as their latest inspected default head; no newer default-head MLO commit was found today. r65 already backports the four major October28 correctness changes documented in its manifest. A full bump still needs the coupled mac80211/flow-offload API review.

Sources: [pinned upstream radar handler](https://github.com/openwrt/mt76/blob/0936617dc529ff9da0385221d3fa6de732231177/mt7996/mcu.c), [community mt76 patches](https://github.com/OpenWRT-fanboy/OpenW1700k/tree/5224315c8a25bb2558834924b7958354d7aae55a/package/kernel/mt76/patches), [community hostapd patches](https://github.com/OpenWRT-fanboy/OpenW1700k/tree/5224315c8a25bb2558834924b7958354d7aae55a/package/network/services/hostapd/patches).

## 6. "iperf3 performance" and receive-buffer changes — limited relevance to our test path

[Commitcf17f0c8e0](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/cf17f0c8e06ef435803dbafe676fe6a1bb0e98fc) raises the **loopback** GSO limit and TCP's RAM-derived maximum send-buffer share from4MiB to32MiB. The commit's cited gains are localhost tests. These are not changes to the WLAN/NPU bridge forwarding engine. Our recorded test has TCP endpoints on the Mac and the Linux server, not on the router; a direct fix for that path is not established by these localhost numbers.

[Commitf167b4f4d4](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/f167b4f4d4f8c0a9e12a0edf9d820cb4268c0224) raises the router kernel's default socket receive buffer to1MiB, describing locally received UDP burst loss with GRO/LRO. It is not proof of an external-endpoint TCP forwarding improvement. Neither new patch is present in r65.

## 7. KASLR and older-kernel NPU backport

[PR25290](https://github.com/openwrt/openwrt/pull/25290) merged **November5 06:33:10KST**. It enables KASLR/relocation on AN7581/AN7583 and adds U-Boot RNG support/seed plumbing. The reported board tests are Nokia devices, not our W1700K. The prepared r65 kernel has relocation enabled but KASLR disabled. This is a security/boot-chain change, not a demonstrated repair for the TCP outliers. No U-Boot update was performed or proposed as an automatic Wi-Fi repair.

[PR25348](https://github.com/openwrt/openwrt/pull/25348) remains open and specifically backports EN7581 NPU support to **Linux6.12**. Its description states that the relevant upstream support is already in6.18. Do not treat it as a newly missing6.18 driver feature.

## 8. Forum verification

The web search tool was blocked by forum robots rules. The normal public Discourse JSON API worked, and the latest post bodies were retrieved directly:

- Community Builds topic249319: highest post **529**, last posted **October31 21:21KST**. No new post beyond that checkpoint. Post529 shares a personal Linux7.3.1 dumb-AP image; it is not a new measured repair for our residual TCP symptoms.
- Support topic222776: highest post **4047**, latest **November4 05:47KST**. Posts4046/4047 discuss V1/V2 hardware, user base and general expectations. Post4046's stability statement is one user's opinion, not controlled MLO/NPU evidence. No new driver patch or reproducible fix was supplied in these two posts.

Sources: [community529](https://forum.openwrt.org/t/gemtek-w1700k-community-builds/249319/529), [support4046](https://forum.openwrt.org/t/quantum-fiber-w1700k-support/222776/4046), [support4047](https://forum.openwrt.org/t/quantum-fiber-w1700k-support/222776/4047).

## Suggested order for subsequent implementation work

1. Review/adapt the complete revised NPU coherent-pool PR against our924 mailbox implementation and reserved-memory layout; preserve streaming DMA semantics. Keep its unmerged status explicit.
2. Audit the extra hard-IRQ locking/counters in our992-20 against actual callers, then compare a minimal cleanup experimentally.
3. Review the small6GHz DFS helper exemption while preserving r64/r65's separately tested radar/CSA changes.
4. Review a6.18.60/whole-wireless-stack rebase as a coupled change. Do not replace r65 with the new image solely on its release date or an iperf-related title.

Evidence is under `/Users/volta/Documents/ChatGPT/openwrt/artifacts/news-20261105/`: pinned API responses, fetched NPU pair, raw primary commit/PR diffs, forum posts and comparisons against r65. No private router logs, settings or credentials were queried or published in this review. The archive watch-state file was not advanced; its November1 on-hold entry for NPU0.8 is historical and was superseded by the r63 integration.
