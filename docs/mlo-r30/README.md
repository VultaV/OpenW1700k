# W1700K r30/r31: bridge acceleration and wireless results

Status, 2026-09-24: r30 is installed with bridge-flow-offload 1.0-r2. iPhone Air completed earlier five-minute MLO and single-6GHz downloads at about 2 Gbps without reported stalls. The subsequent sleep/wake and awake comparisons averaged 1.78/1.74 Gbps, with no interior zero-byte router interval; a late wake-test dip remains unexplained. MLO and scoped IPv4 TCP acceleration are saved on the test router. **r31 integrates those packages but is not installed or boot-tested.** Long-term reliability remains unproven.

## Results

Air tests used the same 2.5 GbE server, four reverse TCP streams, five minutes, a fixed position and no iPhone Mirroring. The 18 Pro is excluded.

| Client/configuration | Mean / minimum / maximum Mbps | Assessment |
|---|---:|---|
| Air, first single6 | 1480 / 0 / 2023 | Zero timing unknown; not cleared retroactively |
| Air, 5+6GHz MLO | **1963 / 1806 / 2020** | No reported stall in 300 seconds |
| Air, single6 repeat | **1993 / 1761 / 2047** | No reported stall in 300 seconds |
| Air, MLO after two-minute screen lock | 1783 / 468 / 2029 | User reported a slowdown without a stall |
| Air, MLO awake comparison | 1744 / 1271 / 2017 | No interior zero-byte router interval; user supplied rates only |
| Air, MLO with PS event capture | 1905 / 1505 / 2027 | No interior zero-byte router interval; user supplied rates only |
| Mac, earlier settled MLO | 1877 / 1802 / 1952 | No zero/below-1Gbps one-second interval in 300 seconds |
| Mac, after permanent activation | 561 / 69 / 1682 | 20-second performance check failed; overlaps client scanning |

Air application results and router port counters are distinct evidence. MLO and repeated single6 router recordings had no zero/below-500Mbps interior one-second interval. Port byte rates include overhead and are not application goodput. MLO had both links (0x6), with traffic predominantly on 6GHz; these results do not demonstrate simultaneous bandwidth aggregation. The comparable Air means differ by about 1.5%.

Evidence: [Air MLO](AIR_MLO_20260924.json), [first single6](AIR_SINGLE6_20260924.json), [single6 repeat](AIR_SINGLE6_REPEAT_20260924.json), [settled Mac MLO](SETTLED_MLO_LONG.json), [permanent activation](PERMANENT_MLO.json).

## Confirmed bottleneck and changes

Same-association Mac single6 acceleration ON/OFF/ON delivered **1854 / 1392 / 1956 Mbps**. Central loaded samples averaged **6.76% / 63.36% / 6.89% CPU** across four cores. Both ON phases had four HW_OFFLOAD data connections and eight PPE BND directions. This supports the CPU-mediated bridge path as a major throughput constraint, not the cause of every historical stall. See [comparison](THROUGHPUT_VERIFICATION.json).

Acceleration also exposed a correctness defect: bridge transit decremented IPv4 TTL. This snapshot:

- Marks bridge-origin flowtable entries and preserves TTL/hop limit in the software path.
- Passes a private KEEP_TTL action to Airoha PPE and clears its TTL-decrement bit.
- Fixes bridge conntrack reference ownership and a double-free on the NF_DROP path.
- Uses a distinct kernel release/ABI with module vermagic checking; mixed modules are unsupported.
- Keeps board-scoped mt76 TX/RPS placement and inherited r29 driver fixes.
- Replaces broad port discovery with a disabled-by-default package for two explicitly selected trusted bridge ports, IPv4 TCP only. Policy/topology validation fails closed; only its owned table is removed.

Endpoint no-flowtable/software/hardware TTL comparison passed 42 checks: 208,638 packet headers retained TTL64, with zero capture drops or IPv4 checksum errors. This was an 8-second, 100Mbps IPv4 reverse-TCP test per mode, **not** IPv6, TTL-1, routed forwarding or full-rate packet validation. See [TTL evidence](TTL_VERIFICATION.json).

## Driver and NPU scope

The actual NPU RV32 binary was disassembled and compared with the public reverse-engineered FDK. Unbounded descriptor waiting and buffer-allocation-before-token-return paths were found, but neither was linked to a captured Air stall. The NPU binary was not replaced. See [firmware findings](NPU_AUDIT.md).

The repeated Air single6 test had three hardware data flows and one software-only flow, with CPU mean 19.61% versus 6.38% for fully offloaded Air MLO. It still achieved about 2 Gbps. The registration callback failure reason was not captured. A short Mac follow-up registered 20/20 connections; that does not exclude an Air/load-dependent issue. See [coverage](OFFLOAD_COVERAGE.json).

## Current installation and remaining work

OpenWrt_5G now provides 5+6GHz MLO, with LAN2-to-ap-mld0 acceleration. Both APs are enabled, the acceptance guard/watchdog exited, and Air re-associated. No reboot or wired interruption was observed during activation (8/8 probes) or the extra Mac check (59/59). Standalone OpenWrt-6G-Fast is disabled while its radio participates in MLO. Credentials/backups remain private.

The extra Mac check retained four hardware flows but was slow during an airportd BEST CONNECTED SCAN. Scanning began immediately before traffic and continued through about 16 seconds; throughput then recovered. Earlier Mac dips also overlapped scans, while settled 60/300-second tests passed. This supports a scan contribution, not a guarantee that a fixed settling delay or all clients will avoid dips.

Remaining: Air upload and changed-WCID reconnect coverage, full reboot/firewall persistence, the one software-only Air flow, and unexplained wireless dips with matching driver/firmware evidence. IPv6/UDP acceleration is outside the enabled scope. Do not describe all historical stalls as fixed.

A [reconnect cleanup source candidate](reconnect-candidate/README.md) passed isolated host checks and four target-object compiles. It is not part of the active build or installed firmware; PPE ownership/relearning and kernel lifecycle validation remain outstanding.

## Image and reproducibility

r31 SHA256: `14d671fc06bff30acb15c4a6fa3cfd6250453cbeda3194b79be3f578cb2c67e0`.

Nine build stages passed. Extracted-image verification confirms all 74 modules, the kernel payload, 11 firmware files and 338 wpad/LuCI files match r30. It includes bridge-flow-offload 1.0-r2 and ip-bridge 6.18.0-r2, defaults acceleration disabled, and embeds no personal Wi-Fi/Tailscale identity. Kernel release remains `6.18.44-w1700k-mlo-r30`; **r31 has not been boot-tested**.

See [build instructions](BUILD.md), [build result](R31_BUILD_RESULT.json), [image verification](R31_IMAGE_VERIFICATION.json), and [historical ledger](HISTORY.md). This is the preserved Linux 6.18.44/r29 source plus selected fixes, not a rebase onto newer upstream releases.


## Additional sustained and reconnect coverage (2026-09-24)

Mac MLO, same association: upload 300 seconds averaged 1698.33 Mbps (CPU 4.73%); download 300 seconds averaged 1916.83 Mbps (minimum 1374.35; CPU 5.96%). Both had four HW data connections/eight BND directions and no zero-byte interval. Upload's 17 below-1Gbps intervals occurred only at 13–30 seconds, overlapping 33 live channel scans. The subsequent download had no below-1Gbps interval or matching live scan request. CPU percentages include pre/post observation.

A separate intentional radio cycle during an existing 180-second download preserved the same four TCP data ports. Same-IP/MAC reassociation took 16.98 seconds including radio startup; the first full >=1Gbps interval ended within 1.20 seconds afterward, with no later zero interval. Later 98–115s nonzero dips again overlapped a client scan. Both WCIDs were reused, so stale-PPE behavior with changed WCIDs is **not verified**. The four planned-outage zero intervals are not unexplained router stalls.

All 844 wired HTTP checks passed (682 sustained, 162 reconnect). Router configuration/boot remained unchanged and Mac original Wi-Fi was restored. One NPU fast-descriptor-wait sample occurred during ongoing upload without a persistent hang; a PC range hit alone is not deadlock evidence.

See [test evidence](SUSTAINED_RECONNECT_20260924.json) and [candidate reconnect patch review](RECONNECT_REVIEW.md). Candidate patches remain uninstalled; direct application has a hash-linkage mismatch against the current driver and broader dependencies. The Air sleep/wake follow-up is recorded below. These results do not mark the overall investigation complete.


A further [disconnect-window test](DISCONNECT_WINDOW_20260924.json) found four HW connections/eight matching PPE BND directions still present 15.62 seconds after the Mac station disappeared, retaining the old download WCID. MCU teardown returned success. Reconnection reused both WCIDs and recovered without later zero-byte intervals; 105/105 wired probes plus one final check passed. The source trace and limits are in [RECONNECT_REVIEW.md](RECONNECT_REVIEW.md). Retention is confirmed; changed-WCID failure and a causal link to historical Air stalls remain unproven. No speculative cleanup patch was installed.


[Full-rate registration follow-up](LOAD_REGISTRATION_20260924.json): eight new 8-second Mac MLO sessions alternating download/upload registered all 32/32 data connections, with both PPE directions and TTL bit24 clear. All later samples retained registration; no zero-byte interval occurred. Mean downloads ranged 1606.51–1963.10 Mbps and uploads 1794.35–1816.32 Mbps. All 81/81 wired checks passed; router boot/configuration and original Mac Wi-Fi were preserved. This is short full-load registration coverage, not an Air reproduction or long-duration acceptance. The original Air callback failure remains unknown; current kernel tracing facilities are disabled, and no diagnostic firmware was installed.

## Air sleep/wake follow-up (2026-09-24)

After the user locked the screen, a 136.10-second observation retained both links and WCIDs. Both driver PS flags were set in 24/25 samples. The wake download returned **1783 / 468 / 2029 Mbps**, with a user-reported slowdown and no stall. A subsequent same-association awake download returned **1744 / 1271 / 2017 Mbps**; the user did not separately answer the stall question. Both router recordings had 292 interior one-second intervals with no zero interval. The wake run had one below-500Mbps port interval; the awake run had none.

All 52/53 respective interior slow samples retained four HW_OFFLOAD data connections, eight matching PPE BND directions and TTL bit24 clear. Active CPU means were **8.01% / 7.24%** across four cores. Both MLO links and WCIDs remained unchanged. All **972/972** wired checks across the lock observation and both recordings passed. No router configuration, firmware, diagnostic setting or reboot was changed. Recorders exited normally.

The wake run stayed near 2Gbps port RX for about 232 seconds before slowing. The later dip overlapped increased 6GHz TXFREE nonzero status/retry counters and four sampled PS=1 observations. The awake comparison had no active 6GHz PS=1 sample. These are correlated observations, not proof that PS caused the dip. `txfree_failed_attempts` includes retries and nonzero header status, so it is not a lost-packet count. Each run also sampled one NPU descriptor-wait PC during ongoing traffic; this does not establish a hang.

A 75.50-second awake channel-counter comparison reported 6GHz busy 94.30%, transmit 90.95% and receive 2.99%; 5GHz transmit was 0.88%. Traffic remained predominantly on 6GHz. This does not establish concurrent link aggregation or exclude external interference. Sequential runs with means differing by about 2.2% do not establish a causal sleep effect. The evidence does not support CPU saturation or loss of hardware registration as the explanation for these dips; client, wireless-driver and firmware behavior remain to distinguish.

See [sanitized sleep/wake evidence](AIR_WAKE_20260924.json). Raw identities, addresses, router logs and backups remain private. No new firmware patch was justified by this comparison.

## PS event capture follow-up

A further same-association Air run returned **1905 / 1505 / 2027 Mbps**, with no interior zero/below-500Mbps port interval, CPU mean **7.64%**, four HW data flows/eight BND directions throughout 53 interior snapshots, and **418/418** successful wired checks. The PS diagnostic and console logging level were temporarily changed and restored; router boot, network configuration and acceleration remained unchanged.

The transferred kernel stream had 3,247 continuous emitted records. Excluding two seconds at each traffic boundary, Air had four emitted PS transitions and eight detailed TXFREE status1 reports. A brief 6GHz host-PS transition pair was about 4.55ms apart while its one-second port interval was 2081Mbps. The status1 burst occurred with the primary host flag awake, secondary asleep and TXQ gate open; its port interval was 1881Mbps. Host event timing is not an over-the-air sleep-duration measurement. These observations do not reproduce the prior large dip or justify treating PS/status1 presence alone as its cause.

The matched status1 counter increased **36**, but only **8** detailed records were emitted. At least 28 details are absent, consistent with the diagnostic's eight-per-five-second limit. A missing tail can leave no internal sequence gap or suppression notice; counters and log sequences must be checked together. Header counts are not lost-packet counts.

Source inspection separates `mt76_sta_ps_transition()`/host TXQ scheduling from the primary-WCID path registered by `mt7996_net_fill_forward_path()` and Airoha PPE. Bulk accelerated packets bypass per-packet host TX preparation. Changing the host awake selector alone is therefore not a demonstrated repair for this path; the earlier r23 experiment also regressed performance. Firmware may still perform internal MLO decisions, so static PPE route selection does not prove a firmware defect. See [sanitized PS event evidence](AIR_PS_EVENTS_20260924.json). No new driver or NPU workaround was installed.
