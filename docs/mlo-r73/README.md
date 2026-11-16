# W1700K r73 wireless backports

r73 uses the r72 Linux 6.18.59 base and the new kernel/module ABI `6.18.59-w1700k-mlo-r73`. The checked-in config changes the build label. The CPU profile, NPU firmware and wireless firmware are inherited from r72.

- mt76 r44 limits TXFREE parsing to the complete header and whole words, including the optional version 7 pair word. Existing partial-batch completion and non-linear skb handling are retained. The bounds follow [the community TXFREE change](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/aa332819f707311fd99e945d1bb6e293211812c4). Timeout-based token reclamation is deferred pending DMA ownership and late-completion validation.
- mac80211 7.2-r14 imports subsystem patches 485–490 for channel reservation, station and BA teardown, receive defragmentation and the single-radio RTS threshold. [OpenWrt backports](https://github.com/openwrt/openwrt/commit/24c13d794c810e14b52bd6e9720a1f512b5e5f23)
- wpad r10 and wifi-scripts 1.0-r5 add `mlo_emlsr` and `mlo_emlmr` as AP MLD UCI options. Apply the same value on every affiliated AP in an MLD. An unset option retains the driver's mode support. The Basic Multi-Link element omits the EML capability field when no supported mode is advertised. [hostapd](https://github.com/openwrt/openwrt/commit/cfae1f57f8cc73675db76d50c91da9509c8dfbd7) · [wifi-scripts](https://github.com/openwrt/openwrt/commit/8e3f6ad698203479e7f678c9b71b07f59e413d34)
- bridge-flow-offload 1.0-r10 accepts the new kernel ABI.

See `BUILD_RESULT.json`, `HOST_CHECKS.json` and `IMAGE_CHECKS.json` for verification. Hardware boot, migration and iPhone stall testing have not been performed on r73. The prior per-peer TX stall remains unconfirmed as resolved.
