# r65 device validation — November 5, 2026 (KST)

The confirmed DFS outage paths were fixed, built, installed and tested. **Overall stability is not declared solved:** one initial TCP download had five zero-throughput seconds and one reconnect flow was slow; their causes remain unresolved.

## Root cause and changes

- The installed r62 MT7996 driver passed a NULL channel context to radar reporting on a shared `ieee80211_hw`. mac80211 therefore marked unrelated radio contexts. The incident had 5GHz radar followed by false 6GHz/2.4GHz radar reports, beacon errors, deauths and persistent transmit stalls.
- r64 scoped reporting to the current radio context under RCU and resumed firmware TX after successful operational-channel setup (excluding CAC/offchannel/error paths). DFS80 passed. DFS160 still restarted the MLD for CAC and produced 27 consecutive zero-throughput seconds (r64 result retained).
- r65 hostapd first looks for a legal available narrower channel for MLO, before the original CAC-required restart fallback. ETSI uniform spreading and legacy AP selection remain unchanged. It uses the existing regulatory/DFS availability filter.
- Source: `447f3823006507b792e518764230ce931a4e6381`; immutable build tag: `mlo-r65-20261105`. hostapd/wpad r9, mt76 r40, ABI `6.18.59-w1700k-mlo-r32`. Kernel/DTB/mt76 bytes and NPU 0.8 pair match r64.
- Firmware SHA256: `f96a2516380a983e63646a3d0c05d76209d27299b20ba360817a858d9debcdff`. Native board/image preflight passed. Settings, SSH and Tailscale were retained; installed bytes match the image. The unsigned FIT hash checks are not trusted-key signature validation.

## Mac wireless measurements

All traffic was bound to `en0` and its Wi-Fi address. Management remained on wired `en10` (1Gbps); the Linux iperf server path is LAN2 at 2.5Gbps. Fixed near-AP position, automatic TX power, four TCP streams.

Each matrix direction ran 90 seconds. All 8 tests had zero packet loss in 3,517 Wi-Fi pings; one duplicate reply occurred in the 2.4+5 downlink. Link masks show active links, not simultaneous data aggregation.

| Configuration | Link mask | Down Mbps | Up Mbps | Zero intervals down/up |
|---|---|---:|---:|---:|
| mlo24_5 | 0x3 | 1918.0 | 1814.0 | 0/0 |
| mlo24_6 | 0x5 | 1953.4 | 1834.6 | 0/0 |
| mlo24_5_6 | 0x7 | 1895.4 | 1828.6 | 0/0 |
| mlo5_6 | 0x6 | 1958.3 | 1833.3 | 0/0 |

Two-minute associated idle had PS=1 on both links at every 20-second sample; subsequent 120-second downlink was 1957.5Mbps and 60-second uplink 1793.5Mbps, with no zero intervals. This was not full macOS sleep.

Original standalone 2.4GHz AP (20MHz) delivered 143.4Mbps for 30 seconds with no zero intervals. DNS (three domains), certificate-verified HTTPS and WAN ping 20/20 passed on that Wi-Fi path.

## DFS160 validation

The first attempt is **excluded from traffic-continuity claims**: an unsolicited radar event occurred before the scheduled trigger and before iperf began. Hostapd did select 80MHz without AP restart, and subsequent traffic worked, but that cannot establish continuity across the event. Its original logs and result are retained.

The valid repeat respected the 30-minute NOP. After real CAC, both client links and channel100/160MHz were verified, then traffic began immediately. Five complete nonzero data intervals preceded the actual event. A firmware emulation request was sent; a new 5500MHz radar event and completed CSA to channel36/80MHz were observed.

- No unrelated-band radar, AP-DISABLED, beacon error or CAC restart.
- Zero 0Mbps intervals; Wi-Fi ping 441/441.
- Average 1636.2Mbps, minimum 124.6Mbps; 12 intervals below 500Mbps. Final 30 seconds recovered to 1954.4Mbps. **Throughput recovery is not instantaneous.**
- Original wireless configuration restored byte-for-byte; the temporary DFS policy was not saved as the user's configuration.

The analyzer was checked against actual r64 DFS80 (accept), r64 DFS160 outage (reject) and r65 pre-traffic-event attempt (reject).

## Initial TCP pause and repeated connections

The first 300-second sustained downlink after returning from the 2.4GHz SSID had five zero intervals at 4–9 seconds; mean 1878.0Mbps. All 1,472 concurrent Wi-Fi pings replied. The queue sampler started later, so no queue evidence exists for those first seconds. No new DFS event explains it; Mac wireless system logging yielded no relevant records. **Do not label this pause fixed or attribute it to the client or NPU without evidence.**

Without changing that connection, repeated 300-second downlink was 1953.3Mbps (minimum1825.3) and uplink1724.3Mbps (minimum934.3), both zero zero-throughput intervals and no ping loss. Additional reconnect trials had the recorder active before traffic:

| Round | Reconnection | Down Mbps (45s) | Zero intervals |
|---|---|---:|---:|
| 1 | same-SSID radio cycle | 1934.9 | 0 |
| 2 | 2.4GHz profile return | 1906.4 | 0 |
| 3 | same-SSID radio cycle | 385.1 | 0 |

The third reconnect flow averaged385.1Mbps (minimum33.5), with zero sender retransmissions, PHY2401Mbps, and the6GHz primary. A new TCP flow on the same unchanged association then delivered1933.8Mbps, minimum1828.8, with no zero intervals. The exact cause of that slow flow remains unresolved; no speculative firmware change was made for it. Additional fresh-flow results and server-output availability are recorded in `DEVICE_TESTS.json`.

## Final state and limits

Original configuration hashes match, UCI has no pending changes, standalone2.4GHz and MLO5+6GHz are enabled, Mac is back on both MLO links, expected bridge hardware-offload table is present, SSH/Tailscale are online, and no owned Wi-Fi rollback guard remains. The wired monitor separates the explicitly allowed installation/reboot from all other periods; exact counts are in `DEVICE_TESTS.json`.

No overnight test, full OS sleep, or genuine weak-signal fallback was performed. NPU0.8 is a vendor test pair; the old exact-identity TX-budget guard does not apply. Raw logs, station identifiers, credentials and configuration backups remain private in the local artifact directory. `BUILD_RESULT.json` is the immutable pre-install publication snapshot; this report and `DEVICE_TESTS.json` are subsequent device records.
