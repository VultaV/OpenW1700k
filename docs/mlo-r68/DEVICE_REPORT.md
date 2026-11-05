# r68 hardware result — rejected

The full upstream PEER_MLD backport compiled and passed99 new +20 existing host checks. It booted, retained settings/SSH/Tailscale, and the Mac associated on both links. NPU0.8 and all6 Wi-Fi firmware files matched r67. Runtime forwarding performance nevertheless failed.

|Completed case|Down Mbps|Up Mbps|Zero intervals down/up|
|---|---:|---:|---:|
|Initial5+6,30s each|796.0|735.4|0/0|
|2.4+5,30s each|1.3|24.1|7/0|
|2.4+6,30s each|184.9|38.6|6/0|

The test was interrupted during tri-band setup. Its independent finally/guard restored original config hashes. Exact r65 imagef96a2516 was then installed preserving current settings; SSH returned108.6s later and both internal TCP endpoints responded via wired en10. No critical MCU/kernel error was observed, and wired checks stayed healthy outside authorized reboots. Remaining profiles and long tests are untested, not passes.

This rejects the backport in this integration; it does not prove an upstream-wide defect or identify the low-level cause. In particular, PEER_MLD/MLD_SKIP, local data-link switching and separate NPU metadata have not been demonstrated compatible. r69 withdraws this candidate and tests a separate exact-identity NPU0.8 budget guard against the previous r67 driver semantics. Firmware guard bytes were not present in r68. Raw identifiers/backups/logs remain private.
