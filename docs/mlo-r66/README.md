# r66 — NPU coherent DMA pool and QDMA locking

**FAILED initial LAN2 readiness; recovered r65.** The pool and firmware initialized, but both the iperf server and Proxmox became unreachable even through wired management. Exact r65 recovery restored both. See `DEVICE_TESTS.json`; r66 is not recommended. r67 isolates the coherent pool with the exact r65 QDMA patch.

This build retains r65's tested radio-scoped radar/DFS CSA changes and unchanged NPU0.8 firmware. It adds the complete coherent-pool change from OpenWrt PR25928 at `23d295c6cb760da37e958aec725024bd3f25f527` (unmerged when integrated), plus the smaller community QDMA patch from `e0da9590bbfd937199371b77ab5018d7d2e92fa3`.

The NPU device attaches a16MiB coherent pool inside physical DRAM `0x80000000–0xbfffffff` before allocating the existing924 coherent mailbox buffers. Streaming packet DMA is unchanged; DTS memory-region names/phandles and the binding are updated together. Existing ramoops is retained. The prepared-source tests cover seven optional-pool/error/cleanup cases with ASan/UBSan; they do not emulate DMA hardware.

The QDMA patch keeps the pingpong source-port and RX IRQ corrections but restores upstream BH queue locking and removes unused per-packet counters. Audited users are xmit, TX NAPI and cleanup; the hard IRQ handler schedules NAPI without taking the queue lock. All8 queue lock/unlock calls use BH locking; existing mailbox retry and TRTCM retry behavior are preserved.

Kernel source remains6.18.59. Because the private QDMA structure changes, kernel/module ABI and package vermagic use `6.18.59-w1700k-mlo-r66`; never mix r65/r66 modules. The bridge-offload helper r6 accepts this exact ABI and retains the existing board/topology/policy guards. Hostapd/wpad r9 and mt76 r40 source behavior are unchanged from r65.

Build source: `4091277639369ebd42809d5ea4867dcbf3be28f0`. `BUILD_RESULT.json` records the immutable pre-install publication snapshot; later installation and hardware tests are separate. This combines two driver changes, so any throughput difference cannot be causally attributed to either without a separate controlled build.

The r65 initial5-second TCP pause and385Mbps flow are not proven fixed. Full weak-signal fallback, full OS sleep and overnight behavior require separate evidence. Raw logs/backups/station identifiers remain private.
