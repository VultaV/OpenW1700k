# r67 device results — failed2.4+6 criteria

The image installed, retained settings/SSH/Tailscale, and passed the new wired LAN2 readiness gate. The16MiB pool and one mailbox address were observed at0xbf000000. Original QDMA source was restored exactly to r65. Authenticated32MiB Wi-Fi upload/download hashes matched.

|Active MLO links|Down Mbps|Up Mbps|Zero-throughput intervals|
|---|---:|---:|---:|
|2.4+5|1969.1|1794.2|0/0|
|2.4+6|14.4|852.8|0/1|
|2.4+5+6|1926.3|1803.2|0/0|
|5+6|1934.2|1761.8|0/0|

All four configurations associated with the expected active-link sets. The2.4+6 result fails stability/performance: down14.4Mbps with mean ping246.9ms and up852.8Mbps with one zero second. Host CPU peaked around3.4% during that downlink; it was not saturated in10-second samples. Other three configurations had down1926–1969Mbps and no zero intervals.

Same-association hardware-offload ON/OFF/ON measured1163/1031/345Mbps, with0/0/3 zero intervals. PPE debugfs reads occurred at17/32s of the last trial, after its zero intervals13–16s. Reads perform SRAM request/ACK polling and may perturb later throughput; the14Mbps matrix trial had no such manual reads. This does not establish the firmware as the cause.

The first interrupted run had real LAN4/Mac en10 link failures. macOS logged interface detach/reattach, user does not recall physical changes. That run is preserved and excluded from the primary comparison. All wired/router/server/Proxmox/WAN samples during the full matrix retest and offload isolation passed; exact per-phase counts are in DEVICE_TESTS.json. Do not generalize this to uninterrupted LAN throughout the session.

Original wireless/network/bridge hashes match, UCI pending is empty, standalone2.4 and5+6MLO are restored, SSH/Tailscale and diagnostics are online, and final critical kernel-error checks were empty. r67 is not a completed stability fix. Long reconnect/DFS/sustained follow-ups were deferred for cause isolation and r68's new upstream PEER_MLD fix. True weak-signal fallback, full OS sleep and overnight operation remain untested. Raw device identifiers/backups/logs stay private.
