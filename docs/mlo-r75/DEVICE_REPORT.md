# r75 installation — November 25, 2026

Installed `ubi2-mlo-fixes-r75-20261125-tailscale` using normal settings-preserving sysupgrade. Native device compatibility and image SHA256 checks passed before flashing. Tailscale SSH returned in **111.4 seconds** with the same node identity. The active kernel ABI is `6.18.64-w1700k-mlo-r75`.

All nine checked configuration files, password/account files, SSH keys, and UniFi adoption/host keys were preserved. All 213 previously installed packages are included in the image. Tailscale 1.104.7 and the UniFi 0.3.0 W1700K port run after boot; UniFi remains `enabled=1, apply=0`.

All 75 installed kernel module hashes, wpad, NPU firmware and the embedded build manifest match the verified image. 2.4/5/6 GHz APs are up (2412/5180/6135 MHz), LAN and WAN are up, five WAN pings had zero loss, local DNS resolved Instagram and DCInside, and verified outbound HTTPS passed. The existing bridge offload table has the hardware offload flag and matching LAN/MLO ports. The selected fresh kernel error filter found zero actual matches. No configuration or firewall policy changes were needed after installation.

## Separate pre-existing UniFi connection failure

The UniFi process runs and retains its adoption identity, but its controller POST reports `no route to host`. The pre-install log already contains 252 entries with that error for the same endpoint. The controller address and raw log are private. This is not counted as a successful controller integration test, and its cause is not established here. No controller, VM or network settings were changed.

## Limits and evidence

No new iPhone application, client throughput, sleep/wake, weak-signal fallback or overnight test was performed. Router DNS/HTTPS checks do not establish iPhone app performance or solve the historical intermittent MLO issue. The sysupgrade SSH session reports a shutdown-time ubus connection failure; new firmware/kernel identity, changed boot ID, preserved settings and successful reconnection establish that installation completed.

Build-time assets retain their original pre-install snapshots. `DEVICE_TESTS.json` and this report add the later installation evidence without changing the immutable tag or original firmware assets. Backups, credentials, runtime states and raw device identifiers remain private.
