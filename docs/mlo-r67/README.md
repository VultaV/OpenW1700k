# r67 — NPU coherent-pool-only isolation

r66 booted with the reserved pool but initial traffic could not reach the LAN2 server/Proxmox, including from wired management. Exact r65 recovery restored reachability. This does not isolate the cause. r67 restores the exact r65 QDMA patch and retains only the PR25928 coherent-pool addition. NPU0.8, mt76r40 and hostapdr9/DFS fixes stay unchanged.

Kernel/module ABI is `6.18.59-w1700k-mlo-r67`; bridge-offloadr7 accepts only the intended ABI. Do not mix modules. Host pool7/7 and bridge22/22 passed. Full build, image and hardware results are recorded separately. Before wireless testing, the installer must verify both LAN2 endpoints and recover r65 promptly if readiness fails. The r65 pauses/slow flows are not proven fixed. Weak-signal fallback, overnight and full OS sleep remain untested.
