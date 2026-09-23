# Investigation chronology through 2026-09-24

Historical entries below describe their state at each test. Later entries supersede earlier pending/disabled statements. See [current status](README.md). Private raw logs and router backups are intentionally not published.

# r30: bridge offload correctness candidate

Status: full kernel, package and image builds passed; extracted image verified.
Installed on the test router. **Bounded IPv4 TTL tests and five-minute MLO throughput tests on Mac and iPhone Air passed. Permanent MLO configuration and final-image boot validation remain pending.**
Based on the preserved r29 / Linux 6.18.44 source, with selected fixes backported.
It is not a rebase onto the September 23 upstream release.

## Measured problem

Same-association Mac 6 GHz downlink over a 2.5 GbE server path:
bridge hardware offload ON/OFF/ON gave 1798.5 / 1331.5 / 1794.6 Mbps.
Mean host CPU usage in the central loaded window was approximately 7% / 61% / 7%.
These were short 20-second tests, not iPhone MLO acceptance tests.

A separate receiving-end capture then exposed a correctness defect:
69,523 baseline data packets had IPv4 TTL64; all 69,522 offload-enabled data
packets had TTL63. The latter flow was observed in HW_OFFLOAD/PPE BND state.
This establishes a bridge TTL change, not the semantics of any particular
hardware control bit or a solution to historical MLO stalls.

## Changes

- Keep the board-scoped r29 CPU steering candidate: mt76 TX uses the existing
  RPS CPU when it differs from Wi-Fi NAPI.
- Fix bridge conntrack ownership: reset a previous conntrack reference before
  assigning UNTRACKED; let the NF_DROP caller free the packet exactly once.
- Mark only flows originating in the nftables bridge family. Preserve TTL and
  IPv6 hop limit in their software fast path, with the existing low-TTL fallback.
- Carry a private KEEP_TTL action to Airoha PPE and clear its BIND_TTL bit.
  The bounded IPv4 endpoint test below passed; IPv6 remains untested.
- Use kernel release `6.18.44-w1700k-mlo-r30`, a distinct package ABI hash,
  and enable module vermagic checking (`MODULE_STRIPPED=n`, `FORCE_LOAD=n`).
  Rebuild every module; do not install these modules into r29 or mix old modules.

The two TTL patches run after the existing Airoha flowtable patches, as `9998`
and `9999`. Their ordering was checked by a full fresh kernel patch preparation.
All eight affected prepared files match the separately compiled candidates.

## Checks

```sh
python3 tests/test_bridge_conntrack_ownership.py "$KERNEL/net/bridge/netfilter/nf_conntrack_bridge.c"
python3 tests/test_bridge_ttl.py "$KERNEL"
```

The ownership harness reproduces 3 failures in 7 cases on the original source
and 0 on the corrected source. The TTL check passes 12 structural checks and
2,091 extracted-C assertions; the original source fails because the guard is
absent. These are host shims, not kernel packet execution or silicon simulation.
Five affected AArch64 objects compiled before the full build.
The complete kernel build passed; all 1,145 in-tree modules contain the new
vermagic and the linked kernel contains the module-version rejection code.

The final image contains 205 packages and 74 modules. All modules have the new
release, and all 64 kmod packages require the new ABI. The 11 firmware files and
338 wpad/LuCI files are byte-identical to r29. The image SHA256 is
`1e701010549c1d23779ed3137d9cafa60320f90152e7550df0717ade3a57e0e3`.
Postinstall validation passed 21 checks (0 fail/warn/skip): all 74 module hashes,
33 preserved UCI settings, Tailscale continuity, both wired links and three APs.
The 1,443 existing root-directory files were separately hash-verified after
restoration. Wired HTTP recovered within a 214.56-second successful-probe gap
around reboot. The bounded IPv4 endpoint TTL and throughput tests below passed.
No private router configuration or Tailscale identity belongs in this source tree.

## IPv4 endpoint TTL verification

The no-flowtable / software / hardware comparison passed 42 checks with no
failures. Respectively 69,524 / 69,524 / 69,536 data packets all retained TTL64.
The complete 208,638-record capture had zero kernel drops and zero IPv4 header
checksum errors; no TCP payload was retained. The matched HW data flow was
HW_OFFLOAD, with both PPE BND directions showing IB1 `200001fc` (bit 24 clear).
All wired probes passed; temporary tables were removed, recovery was disarmed,
and the boot ID remained unchanged.

This is an 8-second, 100Mbps reverse TCP test for each mode. It validates the
observed IPv4 bridge behavior under those conditions, not IPv6, ordinary routed
TTL, sustained maximum throughput, MLO stalls, or per-packet hardware attribution.

## r30 same-association 6 GHz throughput

| Mode, 20s / 4 reverse TCP streams | Receiver Mbps | Whole-observation CPU | Middle-sample CPU |
|---|---:|---:|---:|
| Hardware ON 1 | 1854.34 | 5.64% | 6.76% |
| OFF | 1392.03 | 38.65% | 63.36% |
| Hardware ON 2 | 1956.28 | 5.71% | 6.89% |

ON mean is 1905.31Mbps, 36.87% above OFF. CPU is averaged across four cores;
whole-observation values include equal pre/post sampling intervals. Middle
samples 1-to-4 cover respectively 16.72/17.18/16.77 seconds during traffic.
Both ON snapshots verify all four actual data connections as HW_OFFLOAD with
both PPE BND directions and TTL bit24 clear. There were no zero-byte iperf
intervals, and wired HTTP passed 72/72. Boot/config remained unchanged; temporary
tables were removed and recovery was disarmed after each ON phase.

This establishes the acceleration effect in this bounded Mac single-link test.
It does not establish sustained upload/download, MLO or Air stability. Persistent
hardware acceleration is still disabled; no broad firewall policy was enabled.

## Recovery launcher correction

A later inspection found that the test router has no `nohup`. All three r30
recovery-launch logs report that missing command, so the independent reboot
processes never started. The recorded arm-file removals do not prove otherwise.
The measured traffic, wired probes and rule cleanup remain valid, but recovery
readiness was unverified. Subsequent HW trials require a corrected `setsid`
launcher with actual child identity/readiness/survival checks. A real automatic
recovery reboot has not been tested.

The corrected shared launcher uses `setsid`; a second SSH command checks the
child PID, start time and separate session. A real-device harmless two-second
marker probe passed after the launching SSH command had returned. Failure gates
also passed locally. Further trials use this verified launcher.

## Remaining acceptance

Hardware offload remains disabled persistently. Before enabling it: verify TTL
and hop-limit preservation with receiving-end captures, ordinary routed behavior,
the PPE entry, long downloads/uploads, reconnects, and iPhone Air MLO. The 18 Pro
is excluded as requested. Then validate a scoped bridge activation mechanism and
its cleanup across interface/firewall changes. A successful build alone does not
complete these acceptance steps.

## Build overlay

Use the r29 feed pins/config/overlay as the baseline. Before building r30, apply
`feed-patches/0001-ovpn-backports-set-module-version.patch` at the packages feed
root. Its direct Kbuild call previously omitted the version macro, hidden by
MODULE_STRIPPED; it now supplies the package version and uses package release 2.
An isolated real main.c cross-compile reproduced the error before the change
and passed afterward, with the expected version in ELF module metadata. The
complete OpenWrt ovpn-dco package subsequently built successfully.

## Sustained Mac MLO result

The first 300-second hardware-accelerated MLO downlink averaged 1781.55Mbps,
with one-second min/max 35.64/2057.98Mbps and no zero-byte intervals. Significant
dips occurred around 14–30s and 152–163s, so MLO stability acceptance is **not
passed**. All four starting data tuples had HW_OFFLOAD and bidirectional PPE
entries with TTL bit24 clear. The snapshot does not prove hardware use during
the later dips. CPU averaged 8.04% over 63 observation samples; the maximum
per-core sampled interval was 36.85%, which does not exclude shorter bursts.
Wired monitoring passed 386/386. Temporary rules were removed, the corrected
recovery timer disarmed, both single-link APs restored and boot unchanged.
Evidence: `MLO_LONG_VERIFICATION.json` and its linked private raw logs.
A sustained single-6GHz comparison and iPhone Air acceptance remain pending.

## Sustained 6GHz comparison

The following single-6GHz 300-second hardware-offloaded run averaged
1892.43Mbps (one-second min/max 97.56/2024.54Mbps), with no zero-byte intervals.
All intervals below 1Gbps were confined to the first approximately nine seconds;
there was no later MLO-like dip in this one run. Sender retransmits: 8,603
versus MLO's 24,875. CPU observation mean: 6.68%.
Wired checks: 346/346; owned bridge tables removed and recovery disarmed.
This supports a separate MLO mid-run instability investigation, but one
sequential comparison cannot establish its cause or clear the startup dip.
The installed NPU firmware has not been replaced. Persistent offload remains
disabled. See SINGLE6_LONG_VERIFICATION.json and MLO_LONG_VERIFICATION.json.

## MLO dip-triggered repeat

Repeated 300-second run: 1713.68Mbps mean, 59.83/2025.41Mbps one-second
min/max, no zero-byte intervals, 20,560 sender retransmits. At 15.45s the
467.6Mbps en0 receive-rate trigger captured both link PS bits set, link2
status2 count 5,053 and failed attempts 5,463; all four TCP connections
remained HW_OFFLOAD with both PPE directions bound. A later recovery sample
near 2.05Gbps showed link2 PS clear. This narrows the next investigation to
PS-transition timing and firmware completion errors without proving causation
or the meaning of status2. CPU/flow snapshots are not per-packet tracing.
Wired checks 375/375; single-link AP configuration restored, owned flowtable
removed and recovery disarmed. Evidence: MLO_DIP_VERIFICATION.json.

## Bounded PS trace run

MLO reverse/P4/300s with existing diagnostic PS logging: 1868.97Mbps mean,
99.66/1989.94Mbps min/max, no zero-byte intervals, 15,112 sender retransmits.
Sub-1Gbps intervals were confined to approximately 13–25s. Retained PS host
notifications overlap that period; 141 global PS IDs are missing between emitted
records because of diagnostic rate limiting. Exact air-state duration or cause
is not proven. The prior r27 AWDL experiment already demonstrated similar
short losses; do not substitute this Mac symptom for the original Air stall.
Wired 376/376, single APs/Mac 6GHz restored, PS trace N, temporary acceleration
removed, recovery disarmed. Evidence: MLO_PS_VERIFICATION.json.
Next: preserve the demonstrated acceleration improvement with the reviewed
disabled-by-default package and validate its real lifecycle; obtain Air
acceptance when available. Do not keep repeating the same Mac PS experiment
without a new discriminating intervention or stronger packet evidence.
- PS comparison: 198 and 125 retained target notifications fall in the
  10–20s and 20–30s low-throughput windows. Four notifications also occur
  at 190–200s while receiver intervals stay above 1.905Gbps. A PS transition
  by itself is therefore not a sufficient explanation; burst frequency,
  omitted records and TCP recovery must be distinguished.

## Installed bridge package validation (2026-09-23)

`bridge-flow-offload` 1.0-r2 and `ip-bridge` 6.18.0-r2 are installed. The actual final APK generator matches the reviewed source. `.config` remained byte-identical; no replacement firmware image was produced or installed in this step. The sandbox build failure and earlier pre-hairpin APK are retained as failed/superseded artifacts, not successful deliverables.

Legacy hook moved, hash-verified, to `/etc/hotplug.disabled/00-disable-bridge-flow-offload.pre-r30`; new iface hook installed. Existing global routed hardware offload remains 0. The independent config is now **enabled for LAN2 <-> phy0.2-ap0, IPv4 TCP only**. Wireless/network config hashes and boot ID are unchanged. Diagnostic ps_trace is N; no recovery reboot arm remains. Before/after private backups are preserved.

| Check | Result | Limits |
|---|---|---|
| Offline generator | 20 pass, 0 fail; 100% | Stubbed platform calls |
| Initial 20 s after association | 1,049.55 Mbps; 103.74–1,785.84 | Functional pass, throughput acceptance withheld; first 9 seconds slow |
| Same-connection 60 s | 1,938.87 Mbps; 1,834.93–1,971.92 | One warm 6 GHz reverse TCP run, 4 streams |
| Hardware registration | 4/4 data connections, 8/8 BND directions, TTL bit 24 clear | During-traffic snapshot |
| CPU during warm trial | 5.70% overall | Includes pre/post samples |
| Wired observation | 36/36 first, 79/79 warm, 7/7 lifecycle, 5/5 activation | Sampled HTTP checks, not proof against sub-second loss |
| Actual 6 GHz AP down/up | Owned table removed and recreated automatically | No full firewall reload/reboot in this step |
| Rollback | Both traffic trials and lifecycle returned to OFF and removed table | Then separately enabled and committed after validation |
| Backup listing | New config, firewall, revised iface hook and archived legacy hook included | Future firmware must include compatible package/dependencies |

APK installations returned success, but each reported six missing offline repository-cache warnings. Unsupported macOS xattr preservation warnings: 2 for ip-bridge and 7 for bridge-flow-offload. These were not classified as warning-free installs; package content/functionality checks passed.

Pending: Air acceptance, MLO-specific long-stall resolution, routed/TTL-1 and IPv6 validation, full boot/firewall persistence. IPv6/UDP and MLO port `ap-mld0` are not enabled by this production config. No new GitHub push in this step.

## Mac MLO installed-package follow-up

A separate 60-second test used the installed generator with explicit LAN2 <-> ap-mld0 selection and Mac valid_links 0x6. Mean 1437.09 Mbps; minimum 82.09, maximum 1983.13. All below-1Gbps intervals occurred at 13–28 seconds; last 20 seconds averaged 1913.52 Mbps. CPU aggregate 6.40%; 4 HW_OFFLOAD connections/8 BND directions were recorded early in traffic. This snapshot is not proof that every flow stayed bound at every dip. No zero interval, but **MLO performance/stability acceptance failed**. Functional controller success does not override that assessment.

125/125 wired checks passed. Both AP configuration and saved LAN2-to-6GHz enabled configuration were restored; no new firmware/reboot. Updated the test guard firewall hash only after confirming the sole firewall diff was the new bridge script include. Mac sudo authentication is unavailable, so a controlled AWDL-disable comparison needs user-side authentication; no AWDL setting was changed. The existing Air request remains pending. See LIVE_MLO.json and ../mlo-driver-followup-r30-2026-09-23/RESULT.md.

## AWDL attempt and client-scan finding

The user ran the prepared AWDL guard. macOS reenabled awdl0 after 5.059 seconds; the guard logged invalid_os_reenabled and restored UP. No throughput test ran during that OFF interval. This is an invalid comparison, not evidence that AWDL cannot affect performance. No repeated force-down loop or service termination was used.

A retrospective airportd inspection found BEST CONNECTED SCAN with 33 live scan requests over about 14 seconds. In the initial installed-package MLO run these occurred at client-launch+9.67 to +23.54 seconds; throughput dipped at +13 to +29. In earlier long MLO, scans at +11.83–25.44 align with the first dip and further scans at +151.27–154.47 align with a later dip. A low sample at +140 seconds is not explained by these captured scan-start events. Earlier single6 and PS-traced MLO runs also had 33-request bursts overlapping their low-rate windows.

Following the same MLO setup with 45 seconds of settling, the installed-generator 60-second test delivered mean 1945.66 Mbps, minimum 1804.43, maximum 1977.06; no below-1Gbps interval. Retained airportd logs had no matching scan-start event in this test window. Wired checks 158/158 passed and production 6GHz settings were restored. This is stronger evidence for a client scan contribution to Mac dips, not proof that every dip or the original Air stall has the same cause. AWDL REALTIME inactive log messages do not mean all AWDL radio activity was absent.

A 300-second settled Mac MLO test is now running, using unchanged production driver/firmware and the same bounded cleanup mechanisms. Air acceptance remains pending.

## Settled 300-second MLO result

Mac two-link MLO, installed bridge generator, 45-second post-association settling: **1877.39 Mbps mean / 1801.80 minimum / 1952.24 maximum**, zero 1-second intervals below 1 Gbps, zero zero-throughput intervals. CPU aggregate 6.51%; 4/4 HW_OFFLOAD data connections and 8/8 BND directions were captured. All 425 wired checks passed. Retained airportd log query for the traffic window had no live-scan-start or BEST CONNECTED SCAN matches. Both AP configuration and enabled LAN2-to-6GHz production configuration were restored. See SETTLED_MLO_LONG.json.

This refines the earlier Mac MLO failure interpretation: post-association/background channel scanning is a strong contributor to the observed Mac dips, supported by repeated temporal alignment and two settled tests (60/300 seconds) without a dip. Waiting for the scan to finish changes test timing; it is not a driver repair for scanning itself. Do not claim every observed dip is explained, or that absence of matching retained logs proves no radio scanning at all. The isolated earlier +140-second low sample remains unassigned. The r30 offload throughput/CPU improvement is separately supported by OFF/ON tests; no speculative firmware/PS patch was added for these Mac scan-related symptoms. Air post-r30 verification remains required before declaring the original device problem solved.


## iPhone Air physical acceptance (2026-09-24)

| Configuration | App mean / minimum / maximum Mbps | Stalls |
|---|---|---|
| 6 GHz single, hardware offload | 1480 / 0 / 2023 | Zero timing unknown to user |
| 5+6 GHz MLO, hardware offload | **1963 / 1806 / 2020** | **None during five minutes** |

Both trials used the same 2.5 GbE server, four reverse TCP streams, five minutes and no iPhone Mirroring. User maintained position and screen-on. The 32.6% higher MLO mean is a result of these two runs, not a general aggregation gain. Driver counters show MLO 0x6 with transmission predominantly on 6 GHz.

The MLO router record contains 292 interior approximately-one-second intervals covering 298.92 seconds: aggregate LAN RX mean/min/max 2058.33/1812.69/2136.77 Mbps, zero intervals below 500 Mbps. These port counts include protocol overhead and are not application goodput. Host CPU mean 6.38%; all four data flows had HW_OFFLOAD and eight PPE directions with bridge TTL bit24 clear. Wired checks 397/397; single-link APs and prior enabled LAN2-to-6GHz package configuration restored afterward. See AIR_MLO_20260924.json and AIR_SINGLE6_20260924.json.

The initial Air MLO attempt was invalidated by a test-controller bug: iperf's small control connection was counted as a fifth data stream. The controller restored safely (122/122 wired checks), was corrected and checked against that recorded failure before the successful trial. Do not classify this controller abort as a driver failure or throughput pass.

r31 has been built and extracted-image verified (not installed) to integrate the installed bridge-flow-offload 1.0-r2 package and ip-bridge dependency. It retains the r30 kernel ABI, driver and firmware; this build has not yet been installed. Long-term reliability, full boot persistence, and IPv6/UDP acceleration are not established by the five-minute IPv4 TCP result.


### Air single-6 GHz repeat

A subsequent five-minute physical Air test reported **1993/1761/2047 Mbps**, no stalls. The approximately-one-second LAN2 series has 291 interior intervals, 298.88 seconds, minimum 1881.89 Mbps and no zero/below-500Mbps interval. The prior single6 zero was not reproduced; its original timing remains unknown.

Three data streams had hardware offload; the first data stream stayed in software OFFLOAD, with both matching PPE entries UNB. CPU mean 19.61% (MLO's fully hardware-offloaded run: 6.38%). This mixed-path run still delivered approximately 2 Gbps. The callback failure reason was not captured and remains a separate acceleration-coverage issue; UNB entry rewrite fields must not be interpreted as valid corrupted forwarding state. MLO and this repeat have similar mean throughput (1963 vs1993), not evidence of a general 33% MLO gain. See AIR_SINGLE6_REPEAT_20260924.json.

The r31 image passed all nine build stages and extracted-content verification: identical kernel payload, 74 modules and 11 firmware files to r30, with bridge-flow-offload 1.0-r2 and ip-bridge 6.18.0-r2 integrated. Image SHA256: `14d671fc06bff30acb15c4a6fa3cfd6250453cbeda3194b79be3f578cb2c67e0`. It has not been installed/boot-tested; permanent MLO selection and restart persistence remain separate deployment checks.
