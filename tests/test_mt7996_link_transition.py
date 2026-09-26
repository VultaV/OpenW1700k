#!/usr/bin/env python3
"""Check the PS-gated TXQ/link-change boundary using extracted driver functions.

The lifecycle and PS/AQL fixtures are reused, while the real link-change callback,
selector/remove/add functions, mt7996 PS predicate, mt76 scheduler/completion and
mac80211 AQL functions come from --source-dir/--mac80211-dir. --patch applies a
candidate to a temporary main.c only; supplied source trees are never modified.

Mask publication and worker ordering are injected deterministically. The active
list, locks, RCU, MCU and allocation remain host fixtures: this checks conditional
control flow, not concurrent kernel execution or the observed Air sleep/wake stall.
Failed link activation is deliberately a tested limitation: mac80211 rolls its
valid_links mask back only after the driver's callback has returned.
"""
import argparse
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--mac80211-dir', type=Path, required=True)
    parser.add_argument('--patch', type=Path, help='Apply to a temporary main.c before extraction')
    args = parser.parse_args()
    old = runpy.run_path(str(Path(__file__).with_name('test_mt76_ps_wake.py')))
    lifecycle = runpy.run_path(str(Path(__file__).with_name('test_mt7996_link_lifecycle.py')))
    extract = old['extract']
    source = (args.source_dir / 'tx.c').read_text()
    driver = (args.source_dir / 'mt7996/main.c').read_text()
    with tempfile.TemporaryDirectory(prefix='mt7996-link-transition-') as temporary:
        work = Path(temporary)
        if args.patch:
            (work / 'mt7996').mkdir()
            (work / 'mt7996/main.c').write_text(driver)
            subprocess.run(['patch', '--batch', '--forward', '-p1', '-i', str(args.patch.resolve())], cwd=work, check=True)
            driver = (work / 'mt7996/main.c').read_text()
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
        callback = extract(driver, 'static bool mlo_ps_gate_fix = true;', '\nint mt7996_run(')
        names = ['mt7996_sta_init_txq_wcid', 'mt7996_sta_update_link_ids',
                 'mt7996_mac_sta_init_link', 'mt7996_mac_sta_remove_link',
                 'mt7996_mac_sta_remove_links', 'mt7996_mac_sta_add_links',
                 'mt7996_mac_sta_change_links']
        links = ''.join(lifecycle['function'](driver, name) for name in names)
        reset_cases = old['CASES'].split('static void stall(void)')[0]
        reset_cases = reset_cases.replace('f.dev.wcids[i]', 'f.dev.wcid[i]').replace('f.wcids[i].sta = &f.peer.sta;', 'f.wcids[i].sta = 1;')
        c = work / 'transition.c'
        c.write_text(stubs + LIFECYCLE_SHIMS + callback + aql + old['STATUS_SHIM'] + functions + links + reset_cases + CASES)
        subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-parameter', '-Wno-sign-compare', '-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', str(c), '-o', str(work / 'transition')], check=True)
        return subprocess.run([str(work / 'transition')]).returncode


if __name__ == '__main__':
    raise SystemExit(main())
