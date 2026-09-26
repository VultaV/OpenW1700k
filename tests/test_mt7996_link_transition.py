#!/usr/bin/env python3
"""Check the PS-gated TXQ/link-change boundary using extracted driver functions.

The lifecycle and PS/AQL fixtures are reused, while the real link-change callback,
selector/remove/add functions, mt7996 PS predicate, mt76 scheduler/completion and
mac80211 AQL functions come from --source-dir/--mac80211-dir. --patch applies a
candidate to a temporary main.c only; supplied source trees are never modified.

Mask publication and worker ordering are injected deterministically. The active
list, locks, RCU, MCU and allocation remain host fixtures: this checks conditional
control flow, not concurrent kernel execution or the observed Air sleep/wake stall.
The host fixture represents FQ backlog and fragment presence separately and frees
the attempted core link immediately; it does not test RCU grace periods or DMA.
The separate core rollback cases extract the actual activation/removal functions,
active-mask driver wrapper and schedule/wake helpers. --core-patch is applied only
to a temporary sta_info.c. Baseline mode requires the exact stranded-backlog result,
not an arbitrary failure; fixed mode requires the backlog to be rearmed after cleanup.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import runpy
import subprocess
import tempfile


def replace_once(source, before, after):
    assert source.count(before) == 1, before
    return source.replace(before, after, 1)


LIFECYCLE_TYPES = r'''
#include <errno.h>
#define BIT(n) (1ul << (n))
#define IEEE80211_LINK_UNSPECIFIED 255
#define IEEE80211_MLD_MAX_NUM_LINKS 16
#define MT7996_WTBL_STA 32
#define MT_WCID_FLAG_TDLS_PEER 3
#define MT_WTBL_UPDATE_ADM_COUNT_CLEAR 0
#define CONN_STATE_DISCONNECT 0
#define GFP_KERNEL 0
#define __ffs(v) __builtin_ctzl(v)
#define module_param_named(...)
#define MODULE_PARM_DESC(...)
#define mt76_dereference(p, d) (p)
#define rcu_assign_pointer(p, v) ((p) = (v))
#define kfree_rcu(p, member) free(p)
#define set_bit(i, p) (*(p) |= BIT(i))
#define for_each_set_bit(i, p, max) for ((i) = 0; (i) < (max); (i)++) if (*(p) & BIT(i))
#define INIT_LIST_HEAD(p) ((p)->present = false)
#define list_empty(p) (!(p)->present)
#define list_del_init(p) ((p)->present = false)
#define ewma_avg_signal_init(p) (*(p) = 0)
#define ewma_signal_init(p) (*(p) = 0)
static int mutex_depth;
#define mutex_lock(p) do { assert(mutex_depth == 0); mutex_depth++; } while (0)
#define mutex_unlock(p) do { assert(mutex_depth == 1); mutex_depth--; } while (0)
struct mt7996_sta;
struct mt7996_sta_link {
    struct mt7996_sta *sta;
    struct mt76_wcid wcid;
    struct list_head rc_list;
    int avg_ack_signal;
};
struct mt7996_sta {
    struct mt7996_sta_link deflink, *link[16];
    u8 deflink_id, seclink_id;
};
struct ieee80211_link_sta { struct ieee80211_sta *sta; };
struct ieee80211_bss_conf { int unused; };
struct mt7996_phy { struct mt76_phy *mt76; };
struct mt76_vif_link { struct mt76_phy *phy; };
struct mt7996_vif_link { struct mt76_vif_link mt76; struct mt7996_phy *phy; };
struct mt7996_dev { struct mt76_dev mt76; };
'''

LIFECYCLE_SHIMS = r'''
static struct {
    struct mt7996_sta msta;
    struct ieee80211_vif vif;
    struct mt7996_phy phy[3];
    struct mt7996_vif_link links[16];
    struct ieee80211_link_sta link_sta[16];
    struct ieee80211_bss_conf conf[16];
} life;
static int missing_conf = -1;
static struct ieee80211_sta *wcid_to_sta(struct mt76_wcid *wcid) {
    return wcid && mt76_wcid_primary(wcid)->sta ? &f.peer.sta : NULL;
}
static void *kzalloc(size_t size, int flags) { return calloc(1, size); }
static int mt76_wcid_alloc(unsigned long *mask, unsigned max) {
    assert(mutex_depth == 1);
    for (unsigned i = 0; i < max; i++)
        if (!(*mask & BIT(i))) { *mask |= BIT(i); return i; }
    return -1;
}
static void mt76_wcid_mask_clear(unsigned long *mask, unsigned idx) {
    assert(*mask & BIT(idx)); *mask &= ~BIT(idx);
}
static struct mt7996_dev *mt7996_hw_dev(struct ieee80211_hw *hw) { return &f.router; }
static struct mt7996_phy *mt7996_vif_link_phy(struct mt7996_vif_link *link) { return link->phy; }
static struct mt76_phy *mt76_vif_link_phy(struct mt76_vif_link *link) { return link->phy; }
static struct mt7996_phy *__mt7996_phy(struct mt7996_dev *dev, unsigned id) { return &life.phy[id]; }
static struct ieee80211_bss_conf *link_conf_dereference_protected(struct ieee80211_vif *v, unsigned id) {
    return (int)id == missing_conf ? NULL : &life.conf[id];
}
static struct ieee80211_link_sta *link_sta_dereference_protected(struct ieee80211_sta *s, unsigned id) {
    return &life.link_sta[id];
}
static struct mt7996_vif_link *mt7996_vif_link(struct mt7996_dev *d, struct ieee80211_vif *v, unsigned id) {
    return &life.links[id];
}
static struct mt7996_sta_link *mt7996_sta_link(struct mt7996_sta *s, u8 id) {
    return id < ARRAY_SIZE(s->link) ? s->link[id] : NULL;
}
static void mt7996_mac_wtbl_update(struct mt7996_dev *d, int idx, int mask) {}
static void mt7996_mcu_add_sta(struct mt7996_dev *d, struct ieee80211_bss_conf *c,
    struct ieee80211_link_sta *s, struct mt7996_vif_link *v, struct mt7996_sta_link *l, int state, bool add) {}
static void mt76_wcid_init(struct mt76_wcid *w, unsigned band) { w->phy_idx = band; }
/* In the reproduced interleaving only the surviving secondary has pending TX.
 * Thus old-primary cleanup has no completed frames that could rearm a TXQ. */
static void mt76_wcid_cleanup(void *d, struct mt76_wcid *w) { assert(mutex_depth == 1); }
'''

CASES = r'''
static struct mt76_wcid *link_wcid(unsigned link_id) {
    return &life.msta.link[link_id]->wcid;
}
static void setup(void) {
    reset(); memset(&life, 0, sizeof(life));
    memset(f.dev.wcid, 0, sizeof(f.dev.wcid));
    missing_conf = -1; mutex_depth = 0; mlo_ps_gate_fix = true;
    f.peer.sta.mlo = true; f.peer.sta.valid_links = 6;
    f.peer.sta.drv_priv = &life.msta; f.drv.txq_ps = mt7996_txq_ps;
    life.msta.deflink_id = life.msta.seclink_id = IEEE80211_LINK_UNSPECIFIED;
    for (unsigned i = 0; i < 3; i++) {
        f.phys[i].band_idx = i; life.phy[i].mt76 = &f.phys[i];
    }
    for (unsigned i = 0; i < 16; i++) {
        life.links[i].phy = &life.phy[i % 3];
        life.links[i].mt76.phy = &f.phys[i % 3];
        life.link_sta[i].sta = &f.peer.sta;
    }
    mutex_lock(NULL);
    assert(mt7996_mac_sta_add_links(&f.router, &life.vif, &f.peer.sta, 6) == 0);
    mutex_unlock(NULL);
    link_wcid(1)->flags = BIT(MT_WCID_FLAG_PS); link_wcid(2)->flags = 0;
    assert(life.msta.deflink_id == 1 && life.msta.seclink_id == 2);
}
static int change(unsigned old, unsigned next) {
    return mt7996_mac_sta_change_links(f.dev.hw, &life.vif, &f.peer.sta, old, next);
}
static void cleanup(void) {
    mutex_lock(NULL);
    mt7996_mac_sta_remove_links(&f.router, &life.vif, &f.peer.sta, 0xffff, true);
    mutex_unlock(NULL);
    assert(f.dev.wcid_mask[0] == 0);
}
static void block_after_mask_change(unsigned mask) {
    f.peer.sta.valid_links = mask; f.txq[3].scheduled = true;
    check("published mask mismatch gates the old primary", mt7996_txq_ps(link_wcid(1)));
    check("actual scheduler removes gated TXQ with secondary AQL pending",
          mt76_txq_schedule_list(&f.phys[1], MT_TXQ_BE) == 0 &&
          !f.txq[3].scheduled && f.txq[3].backlog == 10);
}
int main(void) {
    struct sk_buff *skb;
    unsigned secondary;
    setup();
    check("normal two-link awake secondary opens the effective PS gate", !mt7996_txq_ps(link_wcid(1)));
    f.txq[3].scheduled = true;
    check("normal two-link scheduler drains backlog", mt76_txq_schedule_list(&f.phys[1], 0) == 10);
    cleanup();

    /* mac80211 sta_info.c publishes valid_links before the callback. */
    setup(); secondary = link_wcid(2)->idx; skb = packet(secondary, false, 0, 100);
    block_after_mask_change(4);
    check("primary removal callback succeeds", change(6, 4) == 0);
    check("callback selects surviving primary and TXQ WCID",
          life.msta.deflink_id == 2 && f.mtxq[3].wcid == secondary && link_wcid(2)->link_valid);
    check("successful MLO callback rearms stopped backlog once",
          f.txq[3].scheduled && f.txq[3].rearms == 1 && workers == 1 && bad_hw == 0);
    __mt76_tx_complete_skb(&f.dev, secondary, skb, NULL);
    check("awake completion returns AQL without supplying a PS wake",
          reports == 1 && f.peer.airtime[0].aql_tx_pending == 0 &&
          f.txq[3].rearms == 1 && workers == 1);
    check("callback rearm lets the worker drain surviving-link backlog",
          mt76_txq_schedule_list(&f.phys[2], 0) == 10 && !f.txq[3].backlog);
    cleanup();

    /* A primary that remains asleep must still obey AQL gating after rearm. */
    setup(); secondary = link_wcid(2)->idx; skb = packet(secondary, false, 0, 100);
    block_after_mask_change(2);
    check("secondary removal succeeds", change(6, 2) == 0);
    check("rearm preserves raw and effective PS state",
          mt7996_txq_ps(link_wcid(1)) && test_bit(MT_WCID_FLAG_PS, &link_wcid(1)->flags));
    check("rearmed sleeping primary still cannot drain with AQL pending",
          mt76_txq_schedule_list(&f.phys[1], 0) == 0 && !f.txq[3].scheduled);
    __mt76_tx_complete_skb(&f.dev, secondary, skb, NULL);
    check("ordinary PS completion can rearm after AQL returns", f.txq[3].scheduled);
    cleanup();

    setup(); f.peer.sta.valid_links = 0;
    check("zero-active removal succeeds without rearm", change(6, 0) == 0 && workers == 0 && f.txq[3].rearms == 0);
    cleanup();
    setup(); f.peer.sta.mlo = false; f.peer.sta.valid_links = 4;
    check("non-MLO callback retains prior wake behavior", change(6, 4) == 0 && workers == 0 && f.txq[3].rearms == 0);
    cleanup();

    /* All existing station queues get one rearm, but only one worker kick. */
    setup(); f.peer.sta.txq[5] = &f.txq[5]; f.mtxq[5].wcid = link_wcid(1)->idx;
    f.txq[5].ac = 1; f.txq[5].backlog = 3; f.peer.sta.valid_links = 4;
    check("multiple TXQs follow the new primary", change(6, 4) == 0 &&
          f.mtxq[3].wcid == link_wcid(2)->idx && f.mtxq[5].wcid == link_wcid(2)->idx);
    check("each present TXQ is rearmed once with one worker kick",
          f.txq[3].rearms == 1 && f.txq[5].rearms == 1 && workers == 1 && bad_hw == 0);
    cleanup();

    /* A failed third-link addition temporarily changes valid_links from 6 to 7.
     * The caller's rollback happens AFTER callback return. This patch deliberately
     * leaves that separate boundary unfixed rather than claiming an early rearm
     * cannot be consumed while the temporary mask still closes the PS gate. */
    setup(); secondary = link_wcid(2)->idx; skb = packet(secondary, false, 0, 100);
    block_after_mask_change(7); missing_conf = 0;
    check("failed addition propagates error without premature rearm",
          change(6, 7) == -EINVAL && workers == 0 && f.txq[3].rearms == 0);
    f.peer.sta.valid_links = 6; /* ieee80211_sta_activate_link rollback */
    __mt76_tx_complete_skb(&f.dev, secondary, skb, NULL);
    check("LIMITATION: failed activation rollback can still leave a TXQ unscheduled",
          !mt7996_txq_ps(link_wcid(1)) && !f.txq[3].scheduled && f.txq[3].backlog == 10);
    ieee80211_schedule_txq(f.dev.hw, &f.txq[3]); /* next host skb enqueue */
    check("new enqueue rescues the documented failed-activation limitation",
          mt76_txq_schedule_list(&f.phys[1], 0) == 10);
    cleanup();
    printf("link transition: %d checks, %d failed\n", checked, failed);
    puts("Limitation retained: failed activation rollback; no Air hardware claim.");
    return failed ? 1 : 0;
}
'''



CORE_SHIMS = r"""
#define WLAN_STA_INSERTED 1
#define IEEE80211_TXQ_DIRTY 0
#define WARN_ON(v) (!!(v))
#define might_sleep() assert(!bh_depth && !rcu_depth)
#define lockdep_assert_wiphy(p) assert(wiphy_depth == 1)
#define lockdep_is_held(p) (wiphy_depth == 1)
#define rcu_dereference_protected(p, c) (assert(c), (p))
#define rcu_access_pointer(p) (p)
#define RCU_INIT_POINTER(p, v) ((p) = (v))
#define local_bh_disable() (++bh_depth)
#define local_bh_enable() do { assert(bh_depth == 1); --bh_depth; } while (0)
static struct ieee80211_sub_if_data core_sdata;
static struct link_sta_info core_old_links[2];
static int core_changes, core_wakes, core_frees, core_hash_adds;
static bool core_duplicate, core_interleave, core_blocked;
static struct txq_info *to_txq_info(struct ieee80211_txq *q) {
    return container_of(q, struct txq_info, txq);
}
static bool skb_queue_empty(const unsigned *count) { return !*count; }
static struct ieee80211_sub_if_data *vif_to_sdata(struct ieee80211_vif *v) {
    return container_of(v, struct ieee80211_sub_if_data, vif);
}
static bool check_sdata_in_driver(struct ieee80211_sub_if_data *s) { return s->in_driver; }
static bool test_sta_flag(struct sta_info *s, int flag) { return s->inserted; }
static bool link_sta_info_hash_lookup(struct ieee80211_local *l, const u8 *addr) { return core_duplicate; }
static int link_sta_info_hash_add(struct ieee80211_local *l, struct link_sta_info *link) { ++core_hash_adds; return 0; }
static void link_sta_info_hash_del(struct ieee80211_local *l, struct link_sta_info *link) { assert(false); }
static void ieee80211_link_sta_debugfs_remove(struct link_sta_info *link) { assert(link); }
static void ieee80211_link_sta_debugfs_drv_remove(struct link_sta_info *link) { assert(link); }
static void ieee80211_link_sta_debugfs_drv_add(struct link_sta_info *link) { assert(link); }
static void ieee80211_recalc_min_chandef(struct ieee80211_sub_if_data *s, unsigned id) {}
static void ieee80211_sta_recalc_aggregates(struct ieee80211_sta *s) {}
static void sta_accumulate_removed_link_stats(struct sta_info *s, unsigned id) { assert(s->link[id]); }
static void sta_link_free_rcu(struct rcu_head *h) { free(container_of(h, struct sta_link_alloc, rcu_head)); }
static void call_rcu(struct rcu_head *h, void (*fn)(struct rcu_head *)) { ++core_frees; fn(h); }
static void trace_drv_return_int(struct ieee80211_local *l, int ret) {}
static void trace_drv_change_sta_links(struct ieee80211_local *l,
    struct ieee80211_sub_if_data *s, struct ieee80211_sta *sta, u16 old, u16 next) {
    ++core_changes;
    if (!core_interleave) return;
    assert(sta->valid_links == 7 && old == 6 && next == 7);
    assert(mt7996_txq_ps(&life.msta.link[1]->wcid));
    f.txq[3].scheduled = true;
    assert(mt76_txq_schedule_list(&f.phys[1], 0) == 0);
    assert(!f.txq[3].scheduled && f.txq[3].backlog == 10);
    core_blocked = true;
}
static void trace_drv_wake_tx_queue(struct ieee80211_local *l,
    struct ieee80211_sub_if_data *s, struct txq_info *q) {
    assert(wiphy_depth == 1 && bh_depth == 1 && rcu_depth == 1 && mutex_depth == 0);
    assert(f.peer.sta.valid_links == 6 && !f.peer.link[0] && !f.peer.sta.link[0]);
    assert(core_frees == 1); /* cleanup must precede driver wake */
    ++core_wakes;
}
"""

CORE_CASES = r"""
static const struct ieee80211_ops core_ops = {
    .change_sta_links = mt7996_mac_sta_change_links,
    .wake_tx_queue = mt76_wake_tx_queue,
};
static void core_setup(void) {
    setup();
    memset(&core_sdata, 0, sizeof(core_sdata));
    core_changes = core_wakes = core_frees = core_hash_adds = 0;
    core_duplicate = core_interleave = core_blocked = false;
    wiphy_depth = 1; assert(!rcu_depth && !bh_depth);
    core_sdata.local = &f.local[0]; core_sdata.in_driver = true;
    core_sdata.vif.active_links = 7;
    f.local[0].ops = &core_ops; f.local[0].hw.priv = &f.phys[0];
    f.peer.local = &f.local[0]; f.peer.sdata = &core_sdata; f.peer.inserted = true;
    for (unsigned i = 0; i < 17; i++) f.txq[i].vif = &core_sdata.vif;
    for (unsigned i = 1; i <= 2; i++) {
        f.peer.link[i] = &core_old_links[i - 1]; f.peer.sta.link[i] = &life.link_sta[i];
    }
    struct sta_link_alloc *alloc = calloc(1, sizeof(*alloc)); assert(alloc);
    f.peer.link[0] = &alloc->info; f.peer.sta.link[0] = &life.link_sta[0];
    to_txq_info(&f.txq[3])->tin.backlog_packets = 10;
}
static void core_cleanup(void) {
    if (f.peer.link[0]) {
        free(container_of(f.peer.link[0], struct sta_link_alloc, info));
        f.peer.link[0] = NULL;
    }
    assert(wiphy_depth == 1 && !bh_depth && !rcu_depth && !mutex_depth);
    wiphy_depth = 0; cleanup();
}
static void core_cases(void) {
    unsigned secondary;
    struct sk_buff *skb;
    (void)schedule_and_wake_txq; (void)txq_has_queue; /* unused on baseline */
    core_setup(); secondary = link_wcid(2)->idx; skb = packet(secondary, false, 0, 100);
    core_interleave = true; missing_conf = 0;
    check("core activation preserves the actual driver error", ieee80211_sta_activate_link(&f.peer, 0) == -EINVAL);
    check("actual wrapper exposed temporary mask before failing add", core_changes == 1 && core_blocked);
    check("rollback preserves old links, selectors and PS bits and frees attempted link",
          f.peer.sta.valid_links == 6 && !f.peer.link[0] && !f.peer.sta.link[0] && core_frees == 1 &&
          f.peer.link[1] == &core_old_links[0] && f.peer.link[2] == &core_old_links[1] &&
          life.msta.deflink_id == 1 && life.msta.seclink_id == 2 &&
          link_wcid(1)->link_valid && link_wcid(2)->link_valid &&
          f.mtxq[3].wcid == link_wcid(1)->idx &&
          test_bit(MT_WCID_FLAG_PS, &link_wcid(1)->flags) && !mt7996_txq_ps(link_wcid(1)));
    check("core queues rearm only after complete rollback", f.txq[3].rearms == CORE_FIXED &&
          core_wakes == CORE_FIXED && workers == CORE_FIXED && core_hash_adds == 0);
    __mt76_tx_complete_skb(&f.dev, secondary, skb, NULL);
    check("awake completion returns AQL without additional PS rearm",
          f.peer.airtime[0].aql_tx_pending == 0 && f.txq[3].rearms == CORE_FIXED && workers == CORE_FIXED);
    if (CORE_FIXED) {
        check("fixed core lets actual scheduler drain restored-link backlog",
              f.txq[3].scheduled && mt76_txq_schedule_list(&f.phys[1], 0) == 10 && !f.txq[3].backlog);
    } else {
        check("EXACT BASELINE FAILURE: postrollback backlog remains unscheduled",
              !mt7996_txq_ps(link_wcid(1)) && !f.txq[3].scheduled && f.txq[3].backlog == 10 &&
              mt76_txq_schedule_list(&f.phys[1], 0) == 0);
    }
    puts(CORE_FIXED ? "CORE fixed: restored-link backlog drained" :
         "CORE baseline: exact postrollback stalled-backlog negative control reproduced");
    core_cleanup();

    core_setup(); missing_conf = 0;
    f.peer.sta.txq[5] = &f.txq[5]; /* present but empty */
    f.peer.sta.txq[7] = &f.txq[7]; f.mtxq[7].wcid = link_wcid(1)->idx;
    f.txq[7].backlog = 1; to_txq_info(&f.txq[7])->frags = 1; /* fragment-only queue */
    check("null and empty TXQs skipped, fragment and FQ backlog each rearmed once",
          ieee80211_sta_activate_link(&f.peer, 0) == -EINVAL &&
          f.txq[3].rearms == CORE_FIXED && f.txq[5].rearms == 0 &&
          f.txq[7].rearms == CORE_FIXED && core_wakes == 2 * CORE_FIXED);
    core_cleanup();

    core_setup(); missing_conf = 0; f.local[0].in_reconfig = true;
    check("reconfig rollback queues are marked dirty without driver wake",
          ieee80211_sta_activate_link(&f.peer, 0) == -EINVAL &&
          f.txq[3].rearms == CORE_FIXED && core_wakes == 0 && workers == 0 &&
          test_bit(IEEE80211_TXQ_DIRTY, &to_txq_info(&f.txq[3])->flags) == CORE_FIXED);
    core_cleanup();

    core_setup(); core_sdata.in_driver = false;
    check("interface-outside-driver error preserved without calling driver wake",
          ieee80211_sta_activate_link(&f.peer, 0) == -EIO && core_changes == 0 &&
          f.peer.sta.valid_links == 6 && core_wakes == 0 && workers == 0);
    core_cleanup();

    core_setup();
    check("successful activation uses existing driver rearm only",
          ieee80211_sta_activate_link(&f.peer, 0) == 0 && f.peer.sta.valid_links == 7 &&
          core_changes == 1 && core_hash_adds == 1 && core_frees == 0 &&
          core_wakes == 0 && f.txq[3].rearms == 1 && workers == 1);
    core_cleanup();

    core_setup(); core_sdata.vif.active_links = 6; missing_conf = 0;
    check("actual wrapper filters inactive added link and does not call driver",
          ieee80211_sta_activate_link(&f.peer, 0) == 0 && f.peer.sta.valid_links == 7 &&
          core_changes == 0 && core_hash_adds == 1 && core_frees == 0 && workers == 0);
    core_cleanup();

    core_setup();
    check("already-valid activation exits before mask publication or wake",
          ieee80211_sta_activate_link(&f.peer, 1) == -EINVAL && f.peer.sta.valid_links == 6 &&
          core_changes == 0 && core_frees == 0 && workers == 0);
    check("missing link exits before mask publication or wake",
          ieee80211_sta_activate_link(&f.peer, 3) == -EINVAL && f.peer.sta.valid_links == 6 &&
          core_changes == 0 && core_frees == 0 && workers == 0);
    core_duplicate = true;
    check("existing hash entry returns exact EALREADY without wake",
          ieee80211_sta_activate_link(&f.peer, 0) == -EALREADY && f.peer.sta.valid_links == 6 &&
          core_changes == 0 && core_frees == 0 && workers == 0);
    core_cleanup();

    core_setup(); f.peer.inserted = false;
    check("not-yet-inserted station follows hash-only path without driver wake",
          ieee80211_sta_activate_link(&f.peer, 0) == 0 && f.peer.sta.valid_links == 7 &&
          core_changes == 0 && core_hash_adds == 1 && core_frees == 0 && workers == 0);
    core_cleanup();
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--mac80211-dir', type=Path, required=True)
    parser.add_argument('--patch', type=Path, help='Apply to a temporary main.c before extraction')
    parser.add_argument('--core-patch', type=Path, help='Apply to temporary net/mac80211/sta_info.c')
    parser.add_argument('--expect-core-rollback', choices=['auto', 'baseline', 'fixed'], default='auto',
                        help='Auto detects the core rollback rearm; explicit modes pin negative/positive input')
    args = parser.parse_args()
    old = runpy.run_path(str(Path(__file__).with_name('test_mt76_ps_wake.py')))
    lifecycle = runpy.run_path(str(Path(__file__).with_name('test_mt7996_link_lifecycle.py')))
    extract = old['extract']
    source = (args.source_dir / 'tx.c').read_text()
    driver = (args.source_dir / 'mt7996/main.c').read_text()
    core = (args.mac80211_dir / 'sta_info.c').read_text()
    with tempfile.TemporaryDirectory(prefix='mt7996-link-transition-') as temporary:
        work = Path(temporary)
        if args.patch:
            (work / 'mt7996').mkdir()
            (work / 'mt7996/main.c').write_text(driver)
            subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(args.patch.resolve())], cwd=work, check=True)
            driver = (work / 'mt7996/main.c').read_text()
        if args.core_patch:
            (work / 'net/mac80211').mkdir(parents=True)
            (work / 'net/mac80211/sta_info.c').write_text(core)
            subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(args.core_patch.resolve())], cwd=work, check=True)
            core = (work / 'net/mac80211/sta_info.c').read_text()
        activate = lifecycle['function'](core, 'ieee80211_sta_activate_link')
        fixed = 'schedule_and_wake_txq(' in activate
        if args.expect_core_rollback != 'auto':
            assert fixed == (args.expect_core_rollback == 'fixed'), 'core mode/input mismatch'
        aql = extract((args.mac80211_dir / 'tx.c').read_text(), 'u32 ieee80211_txq_aql_pending(', '\nEXPORT_SYMBOL(ieee80211_txq_aql_pending)')
        aql += extract((args.mac80211_dir / 'sta_info.c').read_text(), 'void ieee80211_sta_update_pending_airtime(', '\nstatic struct ieee80211_sta_rx_stats *')
        functions = ''.join(extract(source, start, end) for start, end in [
            ('static int\nmt76_txq_get_qid(', '\nvoid\nmt76_tx_check_agg_ssn('),
            ('void\nmt76_tx_status_lock(', '\nvoid\nmt76_tx_status_skb_done('),
            ('static void\nmt76_tx_check_non_aql(', '\nstatic int\n__mt76_tx_queue_skb('),
            ('static bool\nmt76_txq_stopped(', '\nvoid mt76_txq_schedule('),
        ])
        stubs = old['STUBS']
        for before, after in [
            ('unsigned char addr[6];', 'unsigned char addr[6]; bool mlo, tdls; u16 valid_links; void *drv_priv;'),
            ('struct list_head {};', 'struct list_head { bool present; };'),
            ('int phy_idx, tx_info;', 'int phy_idx, tx_info, rssi; unsigned idx; bool link_valid; u8 link_id; struct list_head poll_list;'),
            ('struct ieee80211_sta *sta;\n    struct rate_info rate;', 'unsigned sta;\n    struct rate_info rate;'),
            ('bool offchannel;', 'bool offchannel; unsigned band_idx; int num_sta;'),
            ('unsigned int drv_flags; };', 'unsigned int drv_flags; bool (*txq_ps)(struct mt76_wcid *); };'),
            ('struct mt76_wcid *wcids[3];', 'struct mt76_wcid *wcid[32]; unsigned long wcid_mask[1];'),
            ('return idx >= 0 && idx < 3 ? dev->wcids[idx] : NULL;', 'return idx >= 0 && idx < 32 ? dev->wcid[idx] : NULL;'),
            ('static struct ieee80211_sta *wcid_to_sta(struct mt76_wcid *wcid) {\n    return wcid ? mt76_wcid_primary(wcid)->sta : NULL;\n}', 'static struct ieee80211_sta *wcid_to_sta(struct mt76_wcid *wcid);'),
            ('static struct {\n    struct mt76_dev dev;', LIFECYCLE_TYPES + '\nstatic struct {\n    union { struct mt76_dev dev; struct mt7996_dev router; };'),
        ]:
            stubs = replace_once(stubs, before, after)
        for before, after in [
            ('#define rcu_read_lock() ((void)0)', 'static int rcu_depth, bh_depth, wiphy_depth;\n#define rcu_read_lock() (++rcu_depth)'),
            ('#define rcu_read_unlock() ((void)0)', '#define rcu_read_unlock() do { assert(rcu_depth > 0); --rcu_depth; } while (0)'),
            ('struct ieee80211_vif {};', 'struct ieee80211_vif { u16 active_links; };'),
            ('u16 valid_links; void *drv_priv;', 'u16 valid_links; void *drv_priv; struct ieee80211_link_sta *link[16];'),
            ('struct sta_info {', '''struct link_sta_info { u8 addr[6]; };
struct rcu_head { int unused; };
struct sta_link_alloc { struct link_sta_info info; struct rcu_head rcu_head; };
struct ieee80211_sub_if_data;
struct ieee80211_local;
struct ieee80211_ops;
struct sta_info {
    struct ieee80211_sub_if_data *sdata;
    struct ieee80211_local *local;
    struct link_sta_info *link[16], deflink;
    bool inserted;'''),
            ('struct ieee80211_hw { void *wiphy; };', 'struct ieee80211_hw { void *wiphy, *priv; };'),
            ('struct ieee80211_local {', 'struct ieee80211_local {\n    const struct ieee80211_ops *ops; bool in_reconfig, resuming;'),
            ('struct rate_info {', '''struct txq_info {
    struct ieee80211_txq txq;
    unsigned long flags;
    unsigned frags;
    struct { unsigned backlog_packets; } tin;
};
struct ieee80211_sub_if_data {
    struct ieee80211_local *local;
    struct ieee80211_vif vif;
    bool in_driver;
};
struct ieee80211_ops {
    int (*change_sta_links)(struct ieee80211_hw *, struct ieee80211_vif *, struct ieee80211_sta *, u16, u16);
    void (*wake_tx_queue)(struct ieee80211_hw *, struct ieee80211_txq *);
};
struct rate_info {'''),
            ('struct ieee80211_txq txq[17];', 'struct txq_info txqi[17];'),
        ]:
            stubs = replace_once(stubs, before, after)
        callback = extract(driver, 'static bool mlo_ps_gate_fix = true;', '\nint mt7996_run(')
        names = ['mt7996_sta_init_txq_wcid', 'mt7996_sta_update_link_ids',
                 'mt7996_mac_sta_init_link', 'mt7996_mac_sta_remove_link',
                 'mt7996_mac_sta_remove_links', 'mt7996_mac_sta_add_links',
                 'mt7996_mac_sta_change_links']
        links = ''.join(lifecycle['function'](driver, name) for name in names)
        reset_cases = old['CASES'].split('static void stall(void)')[0]
        reset_cases = reset_cases.replace('f.dev.wcids[i]', 'f.dev.wcid[i]').replace('f.wcids[i].sta = &f.peer.sta;', 'f.wcids[i].sta = 1;')
        helpers = extract((args.mac80211_dir / 'driver-ops.h').read_text(),
                          'static inline void drv_wake_tx_queue(', '\nstatic inline int drv_can_aggregate')
        helpers += extract((args.mac80211_dir / 'ieee80211_i.h').read_text(),
                           'static inline bool txq_has_queue(', '\n}\n') + '\n}\n'
        helpers += lifecycle['function']((args.mac80211_dir / 'driver-ops.c').read_text(), 'drv_change_sta_links')
        helpers += lifecycle['function'](core, 'sta_remove_link') + activate
        helpers += lifecycle['function'](source, 'mt76_wake_tx_queue')
        cases = CASES.replace('int main(void) {', 'static void core_cases(void);\nint main(void) {')
        cases = cases.replace('    printf("link transition:', '    assert(checked == 24);\n    core_cases();\n    printf("link transition:')
        cases = cases.replace('Limitation retained: failed activation rollback; no Air hardware claim.',
                              'Driver-only rollback limitation reproduced; actual core rollback checked separately. No Air hardware claim.')
        program = (stubs + LIFECYCLE_SHIMS + callback + aql + old['STATUS_SHIM'] + functions + links +
                   CORE_SHIMS + helpers + reset_cases + cases + f'\n#define CORE_FIXED {int(fixed)}\n' + CORE_CASES)
        program = re.sub(r'f\.txq\[([^\]]+)\]', r'f.txqi[\1].txq', program)
        c = work / 'transition.c'
        c.write_text(program)
        inputs = [args.source_dir / 'tx.c', args.source_dir / 'mt7996/main.c']
        inputs += [args.mac80211_dir / name for name in ['sta_info.c', 'tx.c', 'driver-ops.c', 'driver-ops.h', 'ieee80211_i.h']]
        inputs += [Path(__file__).with_name(name) for name in ['test_mt76_ps_wake.py', 'test_mt7996_link_lifecycle.py']]
        print('INPUT ' + json.dumps({'core_mode': 'fixed' if fixed else 'baseline',
              'sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
              'extracted_core_sha256': hashlib.sha256(core.encode()).hexdigest(),
              'core_patch_sha256': hashlib.sha256(args.core_patch.read_bytes()).hexdigest() if args.core_patch else None}), flush=True)
        subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-parameter', '-Wno-sign-compare', '-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', str(c), '-o', str(work / 'transition')], check=True)
        return subprocess.run([str(work / 'transition')]).returncode


if __name__ == '__main__':
    raise SystemExit(main())
