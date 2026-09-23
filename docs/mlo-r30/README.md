# W1700K r30/r31: bridge acceleration and wireless results

Status, 2026-09-24: r30 is installed with bridge-flow-offload 1.0-r2. iPhone Air completed five-minute MLO and single-6GHz downloads at about 2 Gbps without reported stalls. MLO and scoped IPv4 TCP acceleration are saved on the test router. **r31 integrates those packages but is not installed or boot-tested.** Long-term reliability remains unproven.

## Results

Air tests used the same 2.5 GbE server, four reverse TCP streams, five minutes, a fixed position and no iPhone Mirroring. The 18 Pro is excluded.

| Client/configuration | Mean / minimum / maximum Mbps | Assessment |
|---|---:|---|
| Air, first single6 | 1480 / 0 / 2023 | Zero timing unknown; not cleared retroactively |
| Air, 5+6GHz MLO | **1963 / 1806 / 2020** | No reported stall in 300 seconds |
| Air, single6 repeat | **1993 / 1761 / 2047** | No reported stall in 300 seconds |
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

Remaining: long-duration/reconnect/upload coverage, full reboot/firewall persistence, the one software-only Air flow, and any new stall with matching driver/NPU evidence. IPv6/UDP acceleration is outside the enabled scope. Do not describe all historical stalls as fixed.

## Image and reproducibility

r31 SHA256: `14d671fc06bff30acb15c4a6fa3cfd6250453cbeda3194b79be3f578cb2c67e0`.

Nine build stages passed. Extracted-image verification confirms all 74 modules, the kernel payload, 11 firmware files and 338 wpad/LuCI files match r30. It includes bridge-flow-offload 1.0-r2 and ip-bridge 6.18.0-r2, defaults acceleration disabled, and embeds no personal Wi-Fi/Tailscale identity. Kernel release remains `6.18.44-w1700k-mlo-r30`; **r31 has not been boot-tested**.

See [build instructions](BUILD.md), [build result](R31_BUILD_RESULT.json), [image verification](R31_IMAGE_VERIFICATION.json), and [historical ledger](HISTORY.md). This is the preserved Linux 6.18.44/r29 source plus selected fixes, not a rebase onto newer upstream releases.
