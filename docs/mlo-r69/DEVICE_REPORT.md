# r69 device results — guard withdrawn, stability not solved

r69 installed with preserved configuration/SSH/Tailscale and passed the wired endpoint gate. Source-verified read-only instruction readback matched the4B guarded program, but no runtime branch-hit count exists. Kernel/DTB, five relevant modules and six Wi-Fi firmware files match r67; the functional program delta is4B.

Fresh5+6GHz60s DL/UL were379/453Mbps, already below the target. After interruption the restore guard returned original settings. On resume the Mac had only one active6GHz link on an MLD association:30sDL406Mbps with21 zero intervals; UL1808Mbps with none. Wi-Fi ping survived the stall and RF was strong (RSSI-30dBm, noise-96dBm, PHY2401Mbps). This is not a legacySLO result.

Same-association offload OFF20s1064→ON20s1948→ON60s1953Mbps had no zero intervals. Every phase also opened new TCP connections, so table recreation is not isolated as the recovery action. A prior30sDL with21zero intervals and the later healthy flows are both retained. Wired baseline bound to1Gbps management achieved848/941Mbps and no zero intervals; it rules out a400Mbps server-path ceiling, not the full2.5Gbps limit.

The original r69 matrix was interrupted and is excluded. Its first2.4+5AP startup failed. The harness could reload again during legitimateCAC; the resumed helper removes that mid-wait reload and waits240seconds. Three mock cases cover transientubus timeout, deadline and100incompleteCACpolls without a secondreload. APstartup logging now avoids noisy authentication records.

## Exact stock r67 control (not r69 or r70 results)

The exact published r67 image was installed preserving settings/keys/Tailscale and passed the wired iperf/Proxmox endpoint gate. AllAPs were ready before fresh association and40s settle.60sDL1640/UL1828/repeatDL1637Mbps had no zero intervals.

|Active links|Down Mbps|Up Mbps|Down minimum Mbps|Zero intervals down/up|
|---|---:|---:|---:|---:|
|2.4+5|1681.8|1814.6|1628.7|0/0|
|2.4+6|1022.8|1801.2|63.6|0/0|
|2.4+5+6|9.7|639.8|1.1|0/0|
|5+6|1027.9|1828.8|937.3|0/0|

Each direction60s; expectedactive masks confirmed. The severe triple-link loss and2.4+6dip remain despite stock firmware. Zero zero-throughput intervals does not make those performance results acceptable. Original wireless configuration was SHA-restored; no partial/skipped trial is a pass.

## Decision and next change

Withdraw the4B guard: no benefit was established, original zero-as-unlimited intent is unknown, and static analysis identifies a conditional fairness risk at output-slack7. This does not prove the guard caused the failure or that the original firmware is defective. Original/candidate identities and host instruction checks remain in immutable r69 history.

A separate current-kernel defect was traced: hardware deletes can run after flow-block callbacks were unbound when a table is destroyed. Both Airoha direct and MT76 NPU callbacks matter. This is supported by source and an upstream regression report, not by a hardware orphan-entry count on this device. A bounded pre-unbind drain is prepared for r70 with new kernelABI; do not relabel r67 controls as r70 measurements. Unknowns include concurrency/OOM, exact stall causality, true weak-signal/fullOSsleep/overnight behavior. Private backups/identifiers/raw logs were not published.
