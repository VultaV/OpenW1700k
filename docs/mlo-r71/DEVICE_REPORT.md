# r71 device report — November 5, 2026

**r71 was built, installed and tested, but intermittent mixed-band throughput failures remain. This is an experimental prerelease, not a complete MLO stability fix.** Later healthy runs do not replace the failed measurements below.

Code commit: `12518d34d71c20770fcaf5fb45a102a11024969d`. Immutable build tag `mlo-r71-20261105` points to `7d57e6cf16f624e4810ae24954f4e6500ddcae62`. Firmware SHA256: `5b256cbc0ba7e325b4f1ba4ae69af42bb1732f188c7638fb096411252fe4a4a7`. The image is 30,593,896 bytes. The full build exited 0 in 472.5 seconds. An inherited ignored U-Boot empty-package cleanup warning was recorded separately; selected-image FIT, metadata and payload checks passed.

## Change and binary boundary

Patch `0048-mt76-npu-return-rx-slots-after-refill.patch` backports the missing RX publication part of [mt76 PR1169](https://github.com/openwrt/mt76/pull/1169), commit `105e1b13a25c874fd7d750d28cd06ab05a778921`. Dequeue now changes software state; refill publishes `(head+1)%ndesc` after posting replacement buffers. Existing chain, descriptor and TX barriers remain. This is a proposed upstream change; no merged status is asserted.

The actual fill/dequeue host observer passed 50 cases, with the old source and a wrong endpoint rejected. Four existing RX/TX groups and missing-barrier controls passed on the prepared build sources. These are host checks under the proposed index contract. The original NPU0.8 native producer checks `(P+2)%512` descriptor DONE and does not read the consumer CSR in the identified software path. Hardware credit/IRQ behavior remains unknown. See [the native contract review](FIRMWARE_CONTRACT_REVIEW.md); these tests do not prove native firmware equivalence, DMA safety under every timing, or the cause of the prior TX stall.

mt76 is package release 43. Common kernel/module ABI remains `6.18.59-w1700k-mlo-r70`. Kernel/DTB, `airoha_npu`, Ethernet and flowtable module hashes match r70. Exact stock NPU0.8/package0.8-r3, the 16MiB coherent pool, original QDMA, wpad9 and all six Wi-Fi firmware files remain unchanged. No firmware byte patch or guessed register write was applied. Do not mix modules from different ABIs.

## Installation and method

A fresh private backup, board, config-drift and image-hash gates passed. SSH returned in 102.6 seconds. Settings, SSH access and Tailscale node identity were retained; module/firmware hashes match the built image. A read-only mailbox address lies within the 16MiB pool. One source-verified stock code word matched; this is not branch-hit or per-ring address proof.

The Linux iperf server's LAN2 port negotiated 2.5Gbps. The Mac's separate LAN4/en10 management path negotiated 1Gbps. Every wireless benchmark bound both `--bind-dev en0` and its actual Wi-Fi IP, with four TCP streams and auto TX power. AP links were checked in both `iw` and hostapd, followed by the expected client link mask. No PPE table dump ran during full-rate performance measurements. The Mac remained at the user's fixed near-AP location.

## Measurements, including failures

Early original 5+6GHz association:

| Trial | Direction | Seconds | Mean Mbps | Minimum interval Mbps | Zero intervals |
|---|---|---:|---:|---:|---:|
| early_down | down | 60 | 1969.7 | 1889.3 | 0 |
| early_up | up | 60 | 1793.2 | 1719.0 | 0 |

The first complete matrix used 40 seconds from Wi-Fi power-on. This does not prove 40 seconds from the last actual association; those real failures remain recorded:

| Trial | Direction | Seconds | Mean Mbps | Minimum interval Mbps | Zero intervals |
|---|---|---:|---:|---:|---:|
| mlo24_5_down | down | 60 | 1596.4 | 126.5 | 0 |
| mlo24_5_up | up | 60 | 1772.9 | 1297.5 | 0 |
| mlo24_6_down | down | 60 | 15.6 | 0.0 | 3 |
| mlo24_6_up | up | 60 | 77.5 | 29.2 | 0 |
| mlo24_5_6_down | down | 60 | 62.8 | 6.3 | 0 |
| mlo24_5_6_up | up | 60 | 229.4 | 73.7 | 0 |
| mlo5_6_down | down | 60 | 1935.5 | 1816.3 | 0 |
| mlo5_6_up | up | 60 | 1780.9 | 1601.1 | 0 |

An additional retake required driver-reported connection age of at least 60 seconds and at least three consecutive identical expected link/peer maps before each profile. Both profiles reported 60 seconds and stable expected links. This does not exclude background scans or establish the last per-link join time:

| Trial | Direction | Seconds | Mean Mbps | Minimum interval Mbps | Zero intervals |
|---|---|---:|---:|---:|---:|
| mlo24_5_6_down | down | 60 | 1903.8 | 1776.9 | 0 |
| mlo24_5_6_up | up | 60 | 1518.8 | 1335.9 | 0 |
| mlo24_6_down | down | 60 | 1695.0 | 6.3 | 0 |
| mlo24_6_up | up | 60 | 106.7 | 13.6 | 0 |

Thus the initial triple-link failure can recover after a new association, while the 2.4+6GHz retake still has low uplink throughput. Neither an intrinsically unsupported band combination nor insufficient join settling alone is established. Sampled peer/link identities stayed stable within these trials; this does not exclude off-channel scanning. The sampled primary remained the faster band. Completion counters are not proof of simultaneous multi-link data aggregation or weak-signal fallback.

On 2.4+6GHz, fresh-association selector Y/N/Y controls (45 seconds each) gave:

| Trial | Direction | Seconds | Mean Mbps | Minimum interval Mbps | Zero intervals |
|---|---|---:|---:|---:|---:|
| y_before | down | 45 | 1919.6 | 1606.7 | 0 |
| n | down | 45 | 510.8 | 0.0 | 22 |
| y_after | down | 45 | 1945.9 | 1751.0 | 0 |

`mlo_best_link=N` is not an isolated selector toggle: it also changes odd-TID software routing and stops periodic selection. It did not provide a safe workaround; default Y was restored. Healthy Y results do not erase the other failures.

Router CPU busy time from approximately 10-second `/proc/stat` deltas remained below 5% per core in the initial severely slow 2.4+6 and triple-link trials and in the low-uplink retake. This argues against sustained router CPU saturation in those captured failures. It does not exclude shorter spikes, client limits or NPU/radio/firmware stalls.

After 300 seconds associated idle on original 5+6GHz, both links remained available:

| Trial | Direction | Seconds | Mean Mbps | Minimum interval Mbps | Zero intervals |
|---|---|---:|---:|---:|---:|
| sustained_down | down | 180 | 1954.6 | 1573.8 | 0 |
| sustained_up | up | 60 | 1826.9 | 1763.7 | 0 |

This was associated idle, not full OS sleep or an overnight test. No zero intervals in these bounded runs does not establish resolution of r70's captured per-peer TX stall.

## Other checks

- One unchanged 100Mbps TCP connection survived hardware offload ON/OFF/ON. Matching PPE bound entries changed 2 → 0 → 2; minimum 99.2Mbps, zero intervals 0. PPE reads occurred only during this capped diagnostic. This verifies that bounded removal/rebind case, not arbitrary concurrency, OOM behavior or old-stall causality.
- A 32MiB authenticated Wi-Fi SSH upload/download round trip had equal local/remote/returned SHA256 values. The remote SSH source matched the Wi-Fi IP. This is data-integrity evidence, not exhaustive DMA validation.
- Bridge-offload-OFF host RX stress ran one 300Mbps upload stream for 45 seconds: mean 300.0Mbps, minimum 298.9Mbps, zero intervals 0. NPU firmware remained active; this was neither a full NPU-disable test nor a maximum-throughput test.
- Final Wi-Fi-bound DNS, certificate-verified HTTPS and WAN ping passed. Critical kernel filters, including invalid-token/NPU RX failure patterns, matched no line; this does not exclude radio or firmware faults without a kernel log.

## Restoration and wired protection

Original wireless, network and bridge-offload config hashes match, UCI pending state is empty, standalone 2.4GHz and 5+6GHz MLD APs are enabled, and the Mac returned to mask 0x6. Parameters are restored: best-link Y, PS gate Y, awake test N, PS trace N, NSTR peer empty. SSH, Tailscale, snapshot service and both wired endpoints passed. All owned test controllers and rollback guards finished; no benchmark or monitor remains running.

Outside the explicitly authorized firmware reboot, 4293 observed wired link/router/server samples had 0 failures; 859 WAN and 859 Proxmox samples also had 0 failures. Firmware installation caused the separately recorded temporary interruption. The monitor stopped and restarted once; the maximum recorded sampling gap is 204.2 seconds. Samples do not prove uninterrupted service during unobserved gaps. Full phase counts are in `DEVICE_TESTS.json`.

## Remaining work

Mixed-band rate collapses and the older per-peer TX stall remain unresolved. The next useful evidence is synchronized endpoint TCP behavior and per-link hardware/firmware progress during a naturally failing association, distinguishing client off-channel/PS activity from AP/NPU TX completion loss. Do not substitute an unproved binary patch or disabling the beneficial selector. Keep the stable original 5+6GHz layout for current use.

Real weak-signal 5→2.4/6→2.4 fallback, full OS sleep, overnight stability, initial total allocation failure progress and arbitrary teardown concurrency were not validated. Matter is resolved and excluded. Raw identifiers, backups, packets, credentials and Tailscale state remain private. `DEVICE_TESTS.json` contains only allowlisted summary metrics; `DEVICE_SHA256SUMS` covers these two device records.
