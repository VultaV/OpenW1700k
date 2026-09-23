# Reconnect/offload source review, 2026-09-24

No production code changed. Scope is the current prepared r30/r31 source versus three public candidate patches from hurryman2212/OpenW1700k-test offload-oc, commit 73c3ab3081432f02d90b0084f63ea8ca4ea8589b (2026-08-05). Public candidate links are pinned below; local downloaded Git blob hashes were verified.

## Confirmed current behavior

- nf_flow_table_core.c flow_offload_refresh retries hardware work for active software flows; a persistent software-only flow cannot be explained merely by saying there is no retry.
- nf_flow_table_offload.c discards callback errors while counting successes; rule allocation also reduces failure to NULL. No exact runtime errno was captured for the Air stream.
- HW_OFFLOAD can be set when at least one callback/direction succeeds. Therefore the acceptance checks separately verify BOTH matching PPE BND directions; the flag alone is insufficient.
- The current prepared mac80211 sta_info.c lacks the candidate switchdev FDB deletion notification. Airoha/netfilter likewise lack this candidate MAC-based teardown path. Missing code is not proof that the observed Air single-flow issue used that path.

## Candidate applicability concerns

- 930-net-airoha-ppe-flush-stale-PPE-flows-on-FDB-and-STA-events.patch removes an L2-table entry using &e->node. In the current prepared driver, airoha_l2_flow_table_params.head_offset selects l2_node, and existing removal uses &e->l2_node. Applying the candidate directly would use the wrong hash linkage before freeing e. This must be resolved before use; the patch was not installed.
- The same patch extends airoha_ppe_dev operations, requiring matching consumers/modules and ABI review. Its advertised mt76 caller is outside this patch.
- 990-01 also changes global bridge FDB ageing from 300 to 30 seconds and depends on additional PPE/NPU changes. That is broader than a demonstrated per-station stale-flow repair and is not included blindly.
- Generation handling, MAC/network scope, object lifetime and teardown ordering require review before any backport. The controlled reconnect trial recovered but reused both WCIDs. A changed-WCID trial is still needed to discriminate this candidate failure mode.

The historical July report describes upload offload disappearing after iPhone reconnect; later replies report that a standalone mac80211 notification patch was not universally sufficient. These reports are different builds/topologies, not confirmation on this router:
https://github.com/orgs/w1700k/discussions/25

No candidate patch or speculative firmware/PPE flush was applied to the live router. The candidate bundle is not included in this source snapshot.

## Pinned candidate sources

- [mac80211 STA notification](https://github.com/hurryman2212/OpenW1700k-test/blob/73c3ab3081432f02d90b0084f63ea8ca4ea8589b/package/kernel/mac80211/patches/subsys/990-mac80211-emit-switchdev-fdb-del-on-sta-disconnect.patch)
- [Airoha PPE cleanup](https://github.com/hurryman2212/OpenW1700k-test/blob/73c3ab3081432f02d90b0084f63ea8ca4ea8589b/target/linux/airoha/patches-6.18/930-net-airoha-ppe-flush-stale-PPE-flows-on-FDB-and-STA-events.patch)
- [Netfilter FDB cleanup](https://github.com/hurryman2212/OpenW1700k-test/blob/73c3ab3081432f02d90b0084f63ea8ca4ea8589b/target/linux/airoha/patches-6.18/990-01-netfilter-nf_flow_table-invalidate-flows-on-bridge-FDB-roaming.patch)
