# Reconnect cleanup candidate, 2026-09-24

**Experimental source candidate only. Not included in the normal patch directories, r30/r31 images, or the running router.** No firmware was linked or installed for this change. The observed retained PPE entries are real; a changed-WCID forwarding failure and a causal link to historical Air stalls are still unproven.

During the earlier controlled disconnect, four hardware connections and eight matching PPE BND directions survived at least 15.62 seconds after the station disappeared. Removing one station does not take down the AP, so the existing NETDEV_DOWN flow cleanup does not run. See [source and runtime evidence](../RECONNECT_REVIEW.md).

## Candidate behavior

- mac80211 emits a station-MAC FDB deletion notification after AP/AP_VLAN station removal. It uses the current backports `cfg80211_del_sta_sinfo(&sdata->wdev, ...)` context; no driver ABI operation is added.
- Netfilter queues the atomic notification to a worker. It matches only older, bridge-origin, untagged direct-transmit flows in the same network namespace, with the same destination MAC and egress interface. Tagged, routed, local and multicast cases are excluded.
- A generation cutoff is captured under the same spinlock used to publish both bridge-flow tuples. A walk cannot miss a half-published old flow, and delayed work cannot delete a flow published after its event. The lock is on flow creation/event handling, not every packet.
- The worker marks matching flows for normal teardown and schedules the existing GC work. Existing FLOW_CLS_DESTROY callbacks retain ownership of driver objects. Pending hardware work is retried by normal GC; this is not synchronous, instantaneous hardware invalidation.
- The shared `flow_offload_teardown()` becomes idempotent: only its first invocation fixes conntrack state and then releases IPS_OFFLOAD. The old function cleared that bit even on repeated teardown. An extracted-C regression demonstrates an old flow clearing the bit after a replacement flow claims the same conntrack. The candidate preserves the replacement's bit. This shared change also affects existing IP, TC and device-cleanup callers, so their runtime coverage is required.
- Network references cover deferred work. Module init failures unwind notifier/workqueue registration; module exit unregisters and drains the new workqueue before offload shutdown. No bridge ageing timer or firmware image is changed.

The matcher deliberately supports the currently enabled untagged bridge topology only. Allocation failure drops that notification and leaves normal expiry as fallback. The unsigned 64-bit generation uses signed-delta comparison, assuming fewer than 2^63 events can remain outstanding.

## Validation

[Validation evidence](VALIDATION.json):

- Extracted-C host harness with AddressSanitizer and UndefinedBehaviorSanitizer: **13 matching cases, 9 rejected-event cases, 1 failed-insertion case, 1,000 publication interleavings and 3 teardown cases passed; 0 failed**. Kernel services are stubbed.
- Four negative controls removing port scope, direct-transmit union guarding, generation guarding or teardown idempotence were rejected by the harness.
- **4/4 ARM64 object compiles passed**, using the prepared r30 target flags: netfilter core and mac80211 station code, each with switchdev enabled/disabled. The disabled case is a compile-time override, not a complete alternate kernel configuration.
- Both patches applied to disposable source copies and reproduced the candidate files byte for byte. Checkpatch reported zero errors/warnings/checks with signoff/path checks excluded.
- Prepared build-source hashes stayed unchanged. Read-only router verification found unchanged boot/configuration, working wired carrier and restored diagnostics.

Run the harness against a disposable patched kernel source:

```sh
python3 tests/test_bridge_fdb_cleanup.py "$CANDIDATE_KERNEL/net/netfilter/nf_flow_table_core.c"
```

These checks do **not** establish kernel locking/GC correctness under load, hardware deletion/relearning, station-removal notifier interactions, or reconnect throughput. `struct flow_offload` changes layout: any eventual firmware needs a distinct matching kernel/module ABI and a complete rebuild. Do not hot-swap these objects into r30/r31.

## Upstream bundle review

The approach was informed by these pinned public inputs, but their full bundle is not applied:

- [mac80211 notification](https://github.com/hurryman2212/OpenW1700k-test/blob/73c3ab3081432f02d90b0084f63ea8ca4ea8589b/package/kernel/mac80211/patches/subsys/990-mac80211-emit-switchdev-fdb-del-on-sta-disconnect.patch)
- [netfilter generation cleanup](https://github.com/hurryman2212/OpenW1700k-test/blob/73c3ab3081432f02d90b0084f63ea8ca4ea8589b/target/linux/airoha/patches-6.18/990-01-netfilter-nf_flow_table-invalidate-flows-on-bridge-FDB-roaming.patch)
- [PPE cleanup 930](https://github.com/hurryman2212/OpenW1700k-test/blob/73c3ab3081432f02d90b0084f63ea8ca4ea8589b/target/linux/airoha/patches-6.18/930-net-airoha-ppe-flush-stale-PPE-flows-on-FDB-and-STA-events.patch)
- [PPE teardown/reinsertion 990-02](https://github.com/hurryman2212/OpenW1700k-test/blob/73c3ab3081432f02d90b0084f63ea8ca4ea8589b/target/linux/airoha/patches-6.18/990-02-airoha-ppe-invalidate-bridge-flows-on-teardown.patch)
- [mt76 NPU RX reasons](https://github.com/hurryman2212/OpenW1700k-test/blob/73c3ab3081432f02d90b0084f63ea8ca4ea8589b/package/kernel/mt76/patches/0012-wifi-mt76-npu-always-call-check_skb-on-rx.patch)

Against the current prepared driver, 930 has two concrete ownership incompatibilities: L2 removal uses `node` where the table requires `l2_node`; and it accesses/frees a subflow after `airoha_ppe_foe_remove_flow()` already freed it. The latter was reproduced with the extracted current helper plus the candidate statements under host ASan (expected heap-use-after-free). This is a rejected-patch compatibility finding, not a claim that this code is installed.

990-02 also invalidates a BND slot computed from a never-committed L4 flow without matching its owner. Its INVALID-slot path skips tuple comparison and commits every L4 entry in a software hash bucket; a hash match is not proof of flow identity or physical-slot ownership. Its L2-subflow deletion exception remains unconditional. These changes require collision/ownership validation rather than blind application. The NPU RX patch broadens eligible CPU reason codes but does not itself solve stale ownership, and it has not been applied.

## Remaining before deployment

Validate current PPE slot ownership across old/new cookies with the same tuple and across collisions. Normal teardown/reinsertion must not invalidate a newer binding. Then complete kernel/module integration, lockdep/KASAN or equivalent lifecycle testing, changed-WCID reconnect testing, unrelated-station isolation and wired continuity checks. The current candidate alone is not claimed to finish those requirements or resolve the overall investigation.
