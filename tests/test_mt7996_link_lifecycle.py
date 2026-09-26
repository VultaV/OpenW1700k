#!/usr/bin/env python3
"""Extract real station-link lifecycle functions and check selectors/failed allocation.

Usage: test_mt7996_link_lifecycle.py /path/to/mt76 [all|selectors|allocation]
ASan/UBSan cover host control flow; MCU, RCU, locks and hardware are stubs.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def function(source, name):
    match = re.search(r'^(?:static )?(?:int|void)\s+' + name + r'\(', source, re.M)
    assert match, name
    opening = source.index('{', match.start())
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end] + '\n'


STUBS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint16_t u16;
#define ARRAY_SIZE(v) (sizeof(v) / sizeof((v)[0]))
#define BIT(i) (1UL << (i))
#define IEEE80211_LINK_UNSPECIFIED 255
#define IEEE80211_MLD_MAX_NUM_LINKS 16
#define MT7996_WTBL_STA 32
#define MT_WCID_FLAG_TDLS_PEER 0
#define MT_WTBL_UPDATE_ADM_COUNT_CLEAR 0
#define CONN_STATE_DISCONNECT 0
#define GFP_KERNEL 0
#define __ffs(v) __builtin_ctzl(v)
#define mt76_dereference(p, d) (p)
#define rcu_assign_pointer(p, v) ((p) = (v))
#define kfree_rcu(p, member) free(p)
#define set_bit(i, p) (*(p) |= BIT(i))
#define for_each_set_bit(i, p, max) for ((i) = 0; (i) < (max); (i)++) if (*(p) & BIT(i))
struct list_head { bool present; };
#define INIT_LIST_HEAD(p) ((p)->present = false)
#define list_empty(p) (!(p)->present)
#define list_del_init(p) ((p)->present = false)
static int mutex_depth;
#define mutex_lock(p) do { assert(mutex_depth == 0); mutex_depth++; } while (0)
#define mutex_unlock(p) do { assert(mutex_depth == 1); mutex_depth--; } while (0)
#define spin_lock_bh(p) ((void)0)
#define spin_unlock_bh(p) ((void)0)
#define ewma_avg_signal_init(p) (*(p) = 0)
#define ewma_signal_init(p) (*(p) = 0)
struct mt76_wcid {
    unsigned idx, link_id, phy_idx, sta;
    bool link_valid;
    unsigned long flags;
    struct mt76_wcid *def_wcid;
    struct list_head poll_list;
    int rssi;
};
struct mt7996_sta;
struct mt7996_sta_link {
    struct mt7996_sta *sta;
    struct mt76_wcid wcid;
    struct list_head rc_list;
    int avg_ack_signal;
};
struct mt76_txq { unsigned wcid; };
struct ieee80211_txq { struct mt76_txq drv_priv[1]; };
struct ieee80211_sta {
    void *drv_priv;
    unsigned valid_links;
    bool mlo, tdls;
    struct ieee80211_txq *txq[17];
};
struct mt7996_sta {
    struct mt7996_sta_link deflink, *link[16];
    unsigned deflink_id, seclink_id;
};
struct ieee80211_link_sta { struct ieee80211_sta *sta; };
struct ieee80211_bss_conf { int unused; };
struct mt76_phy { unsigned band_idx; int num_sta; };
struct mt7996_phy { struct mt76_phy *mt76; };
struct mt76_vif_link { struct mt76_phy *phy; };
struct mt7996_vif_link { struct mt76_vif_link mt76; struct mt7996_phy *phy; };
struct ieee80211_vif { int unused; };
struct mt7996_dev {
    struct { unsigned long wcid_mask[1]; struct mt76_wcid *wcid[32]; } mt76;
};
struct ieee80211_hw { struct mt7996_dev *dev; };
static struct {
    struct mt7996_dev dev;
    struct ieee80211_hw hw;
    struct ieee80211_vif vif;
    struct ieee80211_sta sta;
    struct mt7996_sta msta;
    struct ieee80211_txq txq[17];
    struct mt76_phy mphy[16];
    struct mt7996_phy phy[16];
    struct mt7996_vif_link link[16];
    struct ieee80211_link_sta link_sta[16];
    struct ieee80211_bss_conf conf[16];
} f;
static int fail_alloc, allocations, missing_conf = -1;
static void *kzalloc(size_t size, int flags) {
    return ++allocations == fail_alloc ? NULL : calloc(1, size);
}
static int mt76_wcid_alloc(unsigned long *mask, unsigned max) {
    assert(mutex_depth == 1);
    for (unsigned i = 0; i < max; i++)
        if (!(*mask & BIT(i))) { *mask |= BIT(i); return i; }
    return -1;
}
static void mt76_wcid_mask_clear(unsigned long *mask, unsigned idx) {
    assert(*mask & BIT(idx)); *mask &= ~BIT(idx);
}
static struct mt7996_dev *mt7996_hw_dev(struct ieee80211_hw *hw) { return hw->dev; }
static struct mt7996_phy *mt7996_vif_link_phy(struct mt7996_vif_link *link) { return link->phy; }
static struct mt76_phy *mt76_vif_link_phy(struct mt76_vif_link *link) { return link->phy; }
static struct mt7996_phy *__mt7996_phy(struct mt7996_dev *dev, unsigned id) { return &f.phy[id]; }
static struct ieee80211_bss_conf *link_conf_dereference_protected(struct ieee80211_vif *v, unsigned id) {
    return (int)id == missing_conf ? NULL : &f.conf[id];
}
static struct ieee80211_link_sta *link_sta_dereference_protected(struct ieee80211_sta *s, unsigned id) {
    return &f.link_sta[id];
}
static struct mt7996_vif_link *mt7996_vif_link(struct mt7996_dev *d, struct ieee80211_vif *v, unsigned id) {
    return &f.link[id];
}
static void mt7996_mac_wtbl_update(struct mt7996_dev *d, int idx, int mask) {}
static void mt7996_mcu_add_sta(struct mt7996_dev *d, struct ieee80211_bss_conf *c,
    struct ieee80211_link_sta *s, struct mt7996_vif_link *v, struct mt7996_sta_link *l, int state, bool add) {}
static void mt76_wcid_init(struct mt76_wcid *w, unsigned band) { w->phy_idx = band; }
static void mt76_wcid_cleanup(void *d, struct mt76_wcid *w) { assert(mutex_depth == 1); }
'''

CASES = r'''
static int checked, failed;
static void check(const char *name, bool ok) {
    checked++;
    if (!ok) { failed++; printf("FAIL: %s\n", name); }
}
static void setup(bool mlo) {
    memset(&f, 0, sizeof(f));
    f.hw.dev = &f.dev; f.sta.drv_priv = &f.msta; f.sta.mlo = mlo;
    f.msta.deflink_id = f.msta.seclink_id = IEEE80211_LINK_UNSPECIFIED;
    for (unsigned i = 0; i < 16; i++) {
        f.mphy[i].band_idx = i; f.phy[i].mt76 = &f.mphy[i];
        f.link[i].phy = &f.phy[i]; f.link[i].mt76.phy = &f.mphy[i];
        f.link_sta[i].sta = &f.sta;
    }
    for (unsigned i = 0; i < ARRAY_SIZE(f.txq); i++) f.sta.txq[i] = &f.txq[i];
    allocations = fail_alloc = mutex_depth = 0; missing_conf = -1;
}
static int add(unsigned links) {
    mutex_lock(NULL);
    int ret = mt7996_mac_sta_add_links(&f.dev, &f.vif, &f.sta, links);
    mutex_unlock(NULL);
    return ret;
}
static void cleanup(void) {
    mutex_lock(NULL);
    mt7996_mac_sta_remove_links(&f.dev, &f.vif, &f.sta, 0xffff, true);
    mutex_unlock(NULL);
}
static bool selectors(unsigned mask) {
    if (!mask) return f.msta.deflink_id == 255 && f.msta.seclink_id == 255;
    unsigned p = f.msta.deflink_id, s = f.msta.seclink_id;
    if (p >= 16 || s >= 16 || !(mask & BIT(p)) || !(mask & BIT(s))) return false;
    if (__builtin_popcount(mask) > 1 && p == s) return false;
    if (!f.msta.link[p] || !f.msta.link[s]) return false;
    for (unsigned i = 0; i < ARRAY_SIZE(f.txq); i++)
        if (f.txq[i].drv_priv->wcid != f.msta.link[p]->wcid.idx) return false;
    return true;
}
static void transition(unsigned old, unsigned next) {
    unsigned primary = f.msta.deflink_id;
    f.sta.valid_links = next;
    check("link change returns success", mt7996_mac_sta_change_links(&f.hw, &f.vif, &f.sta, old, next) == 0);
    check("selectors and all shared TXQs refer to active links", selectors(next));
    if (primary < 16 && (next & BIT(primary)))
        check("surviving primary is preserved", f.msta.deflink_id == primary);
}
static void selector_cases(void) {
    /* Every directed transition among retained three-link subsets; includes zero
     * and remove-only changes, and each case starts with distinct allocated links. */
    for (unsigned first = 0; first < 8; first++) for (unsigned next = 0; next < 8; next++) {
        setup(true); f.sta.valid_links = 7; check("initial three-link add", add(7) == 0);
        transition(7, first); transition(first, next); cleanup();
        check("all WCID reservations returned", f.dev.mt76.wcid_mask[0] == 0);
    }
    setup(true); f.sta.valid_links = 6; check("two-link add", add(6) == 0);
    transition(6, 2); transition(2, 6); transition(6, 4); transition(4, 6);
    cleanup(); check("two-link cleanup", f.dev.mt76.wcid_mask[0] == 0);

    /* Client MLO can change active links without changing negotiated valid_links. */
    setup(true); f.sta.valid_links = 7; check("client MLO initial add", add(7) == 0);
    check("client MLO selects initial active subset",
          mt7996_mac_sta_change_links(&f.hw, &f.vif, &f.sta, 7, 3) == 0 && selectors(3));
    check("fixed valid_links permits active 0x3 to 0x6 transition",
          mt7996_mac_sta_change_links(&f.hw, &f.vif, &f.sta, 3, 6) == 0 &&
          f.sta.valid_links == 7 && f.msta.deflink_id == 1 && selectors(6));
    cleanup(); check("client MLO cleanup", f.dev.mt76.wcid_mask[0] == 0);

    setup(true); f.sta.valid_links = 2; check("existing primary add", add(2) == 0);
    unsigned primary = f.msta.deflink_id;
    f.sta.valid_links = 14; missing_conf = 3;
    check("partial add propagates configuration failure", add(12) == -EINVAL);
    check("failed addition retains old primary and repairs secondary", selectors(2) && f.msta.deflink_id == primary);
    check("failed new WCID removed", f.dev.mt76.wcid_mask[0] == 1);
    cleanup(); check("failure cleanup returns remaining WCID", f.dev.mt76.wcid_mask[0] == 0);

    setup(false); check("non-MLO add", add(1) == 0);
    check("non-MLO primary and TXQ unchanged", selectors(1));
    cleanup(); check("non-MLO cleanup", f.dev.mt76.wcid_mask[0] == 0);
}
static void allocation_cases(void) {
    for (int nth = 1; nth <= 2; nth++) {
        setup(true); f.sta.valid_links = 7; fail_alloc = nth;
        check("allocation failure propagates", add(7) == -ENOMEM);
        check("allocation failure returns every reserved WCID", f.dev.mt76.wcid_mask[0] == 0);
        check("failed initial add leaves no selectors", selectors(0));
        for (unsigned i = 0; i < 16; i++) check("failed initial add leaves no links", !f.msta.link[i]);
    }
    setup(true); f.sta.valid_links = 2; check("existing station add", add(2) == 0);
    unsigned long before = f.dev.mt76.wcid_mask[0];
    f.sta.valid_links = 6;
    for (int n = 0; n < 40; n++) {
        fail_alloc = allocations + 1;
        check("repeated allocation failure stays ENOMEM", add(4) == -ENOMEM);
        check("repeated failure preserves original reservation", f.dev.mt76.wcid_mask[0] == before);
        check("repeated failure preserves primary", selectors(2));
    }
    fail_alloc = 0;
    check("later allocation still succeeds", add(4) == 0);
    check("successful retry restores selectors", selectors(6));
    cleanup(); check("retry cleanup returns all WCIDs", f.dev.mt76.wcid_mask[0] == 0);
}
int main(int argc, char **argv) {
    const char *which = argc > 1 ? argv[1] : "all";
    if (!strcmp(which, "all") || !strcmp(which, "selectors")) selector_cases();
    if (!strcmp(which, "all") || !strcmp(which, "allocation")) allocation_cases();
    printf("link lifecycle: %d checks, %d failed\n", checked, failed);
    return failed ? 1 : 0;
}
'''


if __name__ == '__main__':
    source = (Path(sys.argv[1]) / 'mt7996/main.c').read_text()
    names = ['mt7996_sta_init_txq_wcid']
    if 'mt7996_sta_update_link_ids(' in source:
        names.append('mt7996_sta_update_link_ids')
    names += ['mt7996_mac_sta_init_link', 'mt7996_mac_sta_remove_link',
              'mt7996_mac_sta_remove_links', 'mt7996_mac_sta_add_links',
              'mt7996_mac_sta_change_links']
    case = sys.argv[2] if len(sys.argv) > 2 else 'all'
    assert case in ('all', 'selectors', 'allocation'), case
    with tempfile.TemporaryDirectory(prefix='mt7996-lifecycle-') as directory:
        work = Path(directory)
        c = work / 'check.c'
        c.write_text(STUBS + ''.join(function(source, name) for name in names) + CASES)
        subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-parameter', '-Wno-sign-compare', '-fsanitize=address,undefined',
                        '-fno-omit-frame-pointer', str(c), '-o', str(work / 'check')], check=True)
        raise SystemExit(subprocess.run([str(work / 'check'), case]).returncode)
