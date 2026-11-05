# r70 device results — offload cleanup observed; residual TXstall

The exact image installed with settings/SSH/Tailscale node identity preserved. Both wired endpoints passed the readiness gate. NewABI6.18.59-w1700k-mlo-r70 modules and stockNPU0.8 hashes matched. Pool/mailbox were observed in the16MiB window; the original source-verified codeword matched. First60s5+6GHz DL1938/UL1806Mbps had no zero intervals.

One100Mbps100-second TCP connection stayed open while offload was turned OFF/ON. Its matching PPEBND entries changed2→0→2, minimum80.8Mbps, zero intervals0. This verifies removal/rebind in that bounded case. PPEstats were read only during the capped diagnostic, not full-rate benchmarks. It does not prove arbitrary concurrency/OOM safety or the cause of previous stalls.

## Real failure retained

Immediately before the planned integrity test, WiFiSSHbanner exchange and router/server/WAN pings failed while wired management remained healthy. The logical station still had5+6 links. A temporary count-only nftprobe recorded10received echo requests and10generated replies, but Mac received0. The probe table was removed. Host prepare/PS transitions and PLEqueued frames increased; TXS/TXFREE remained fixed. Of276logged MacPStransition events,207showed the host gate open; non-AQL count stayed6 and no matchingTXFREEtrace event appeared. Tracing was restoredOFF. These are host diagnostics, not atomic WTBL or air captures.

Mac-only reassociation recovered connectivity. A new32MiB authenticated WiFi upload/download had matchingSHA256. The first failure is not replaced by that retry. Its precise cause remains unproved; a lower WiFi/sharedTX completion path is implicated more directly than DNS/WAN or a saturated CPU. NPU involvement cannot be excluded because disabling bridgeoffload is not disablingNPU.

## Subsequent controlled matrix

|Links|Down Mbps|Up Mbps|Down minimum|Zero intervals down/up|
|---|---:|---:|---:|---:|
|2.4+5|1911.7|1789.3|1601.8|0/0|
|2.4+6|1950.6|903.1|1879.3|0/0|
|2.4+5+6|1865.2|1758.6|1497.1|0/0|
|5+6|1899.3|1738.3|1712.0|0/0|

Each direction60s, allAP/clientlink masks checked beforetraffic,40s postjoinsettle, no mid-CACreload. No zero intervals occurred, but2.4+6uplink903Mbps remains belowtheotheruplinks. This good active-traffic run does not establish idle/overnight stability or simultaneousmulti-linkaggregation.

Originalwireless/network/bridgeconfig hashes match andUCIis empty. Originalstandalone2.4GHz and5+6MLD are restored, Maclinks0x6, boundWiFiDNS/TLS/WAN tests passed afterfreshreassociation, SSH/Tailscaleonline, no critical kernel warnings. Wiredmanagement1Gbps/server2.5Gbps; monitor perphase counts are inJSON, with authorized installation outages separated. Raw logs/backups/identifiers remain private.

## Missing RX fix and firmware review

A separate missingpart ofPR1169was found: dequeue still published theNPU RXDMAindex before buffers were refilled. Existing whole-chain and ownership-store barriers do not fix that earlier doorbell. r71 movespublication torefill afterreplacementbuffers, with50host cases andold/newnegativecontrols. It is not yet proved asthiscapturedstall'scause.

The current sixWiFifirmwarefiles matchbothofficialandforklatesthead0936617; the newerf349872commitdate refers to thealready-packaged20260721bytes. No newbinary or PS/TXstallfixnote was found inthoseheads. No differentfirmwarewasblindly installed. Trueweak-signal/fullOSsleep/overnight, arbitraryconcurrency/OOM andexactfirmwareschedulerfault remain unverified.
