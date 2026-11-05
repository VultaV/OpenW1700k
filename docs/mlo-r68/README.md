# r68 — Stable firmware MLD identity

This backports the complete five-file upstream1e1ca91 PEER_MLD command. Firmware association identity stays at its original WCID while the host may select another data link. PEER_MLD is sent before the first STA_REC; a failed command aborts association. MLD_SETUP uses SKIP only for the exact link set described at association, preserving later partner-link updates. Local0042 data-link voting,0044 removal-only and0045 management selection stay intact.

The NPU coherent pool, original r65 QDMA, exact vendor NPU0.8 and Wi-Fi WM/DSP/WA20260721 firmware are retained. Kernel/common-module ABI remains6.18.59-w1700k-mlo-r67; only private MT7996 state and serialization change. Ship the matching mt76r41 set. The wider flow-key/mac80211/WED update is not required for this backport.

Prepared-source tests passed99 new checks plus20 existing backport checks with ASan/UBSan; reversing the stable-index change reproduces two expected fixture failures. Hardware transport and stability remain separate. r67 had2.4+6GHz throughput collapse despite other configurations around1.9Gbps. A separately discovered NPU0.8 zero-budget defect is NOT patched here; its effect must be tested independently. Weak-signal fallback/full OS sleep/overnight stability are unverified.
