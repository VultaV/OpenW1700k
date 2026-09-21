#!/usr/bin/env python3
"""Exercise pinned mt76 PS scheduling and both TX status paths, before/after 0008.

Usage: python3 tests/test_mt76_ps_wake.py --source-dir PATH_TO_MT76_01367e60
The default mac80211 source is ../mac80211-regular/backports-7.2; override it
with --mac80211-dir. Requires cc and patch, and never changes either source tree.
The compiled functions are extracted verbatim, including mac80211's actual AQL
accounting/accessor. Firmware, RCU and concurrent kernel execution are fixtures;
this establishes conditional host behavior, not hardware incidence or throughput.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile


def extract(source, start, end):
    offset = source.index(start)
    return source[offset:source.index(end, offset)]


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef int atomic_t;
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define READ_ONCE(v) (*(volatile __typeof__(v) *)&(v))
#define unlikely(v) (v)
#define EXPORT_SYMBOL_GPL(...)
#define EXPORT_SYMBOL(...)
#define __acquires(...)
#define __releases(...)
#define rcu_read_lock() ((void)0)
#define rcu_read_unlock() ((void)0)
#define spin_lock_bh(...) ((void)0)
#define spin_unlock_bh(...) ((void)0)
#define spin_lock(...) ((void)0)
#define spin_unlock(...) ((void)0)
#define WARN_ONCE(condition, ...) (condition)
#define IEEE80211_NUM_TIDS 16
#define NL80211_EXT_FEATURE_AQL 1
#define MT_WCID_FLAG_PS 0
#define MT76_RESET 1
#define MT_DRV_HW_PS_BUFFERING 1
#define MT_DRV_IGNORE_TXS_FAILED 2
#define MT_WCID_TX_INFO_SET 1
#define MT_MAX_NON_AQL_PKT 16
#define MT_TXQ_FREE_THR 2
#define MT_PACKET_ID_FIRST 3
#define MT_TX_CB_DMA_DONE 1
#define MT_TX_CB_TXS_DONE 2
#define MT_TX_CB_TXS_FAILED 4
#define IEEE80211_TX_STAT_ACK 1
enum mt76_txq_id { MT_TXQ_BE, MT_TXQ_BK, MT_TXQ_VI, MT_TXQ_VO };
static const unsigned long jiffies = 123;
static int atomic_read(const atomic_t *v) { return *v; }
static void atomic_add(int n, atomic_t *v) { *v += n; }
static void atomic_sub(int n, atomic_t *v) { *v -= n; }
static int atomic_sub_return(int n, atomic_t *v) { return *v -= n; }
static int atomic_dec_return(atomic_t *v) { return --*v; }
static int atomic_cmpxchg(atomic_t *v, int old, int value) {
    int prev = *v;
    if (prev == old) *v = value;
    return prev;
}
static bool test_bit(int bit, const unsigned long *flags) {
    return !!(*flags & (1ul << bit));
}
struct ieee80211_txq;
struct ieee80211_vif {};
struct ieee80211_sta {
    struct ieee80211_txq *txq[17];
    unsigned char addr[6];
};
struct sta_info {
    struct ieee80211_sta sta;
    struct { atomic_t aql_tx_pending; } airtime[4];
};
struct ieee80211_hw { void *wiphy; };
struct ieee80211_local {
    struct ieee80211_hw hw;
    atomic_t aql_bc_pending_airtime, aql_total_pending_airtime;
    atomic_t aql_ac_pending_airtime[4];
};
static struct ieee80211_local *hw_to_local(struct ieee80211_hw *hw) {
    return container_of(hw, struct ieee80211_local, hw);
}
static bool wiphy_ext_feature_isset(void *wiphy, int feature) { return true; }
struct mt76_txq {
    u16 wcid, agg_ssn;
    bool send_bar, aggr;
    struct ieee80211_txq *owner;
};
struct ieee80211_txq {
    void *drv_priv;
    struct ieee80211_sta *sta;
    struct ieee80211_vif *vif;
    int ac, tid;
    bool scheduled;
    int backlog, rearms;
    struct ieee80211_hw *last_hw;
};
struct rate_info { int flags, legacy; };
struct ieee80211_rate_status { struct rate_info rate_idx; };
struct ieee80211_tx_info {
    int tx_time_est, flags;
    struct { int rates[4]; } control;
    struct { struct { int count, idx; } rates[4]; } status;
};
struct mt76_tx_cb { int pktid, wcid, flags; unsigned long jiffies; };
struct sk_buff {
    struct ieee80211_tx_info info;
    struct mt76_tx_cb cb;
    struct sk_buff *next;
    struct ieee80211_hw *hw;
    int ac;
};
struct sk_buff_head { struct sk_buff *first, *last; };
struct list_head {};
struct ieee80211_tx_status {
    struct sk_buff *skb;
    struct list_head *free_list;
    struct ieee80211_tx_info *info;
    struct ieee80211_sta *sta;
    struct ieee80211_rate_status *rates;
    int n_rates;
};
struct mt76_wcid {
    unsigned long flags;
    int phy_idx, tx_info;
    atomic_t non_aql_packets;
    struct mt76_wcid *def_wcid;
    struct ieee80211_sta *sta;
    struct rate_info rate;
};
struct mt76_queue { bool stopped, blocked; int queued, ndesc, lock; };
struct mt76_dev;
struct mt76_phy {
    struct mt76_dev *dev;
    struct ieee80211_hw *hw;
    unsigned long state;
    bool offchannel;
    struct mt76_queue *q_tx[4];
};
struct mt76_driver_ops { unsigned int drv_flags; };
struct mt76_queue_ops {
    void (*kick)(struct mt76_dev *, struct mt76_queue *);
    void (*tx_cleanup)(struct mt76_dev *, struct mt76_queue *, bool);
};
struct mt76_dev {
    struct ieee80211_hw *hw;
    struct mt76_phy *phys[3];
    struct mt76_wcid *wcids[3];
    struct mt76_driver_ops *drv;
    struct mt76_queue_ops *queue_ops;
    int status_lock, rx_lock, tx_worker;
};
#define IEEE80211_SKB_CB(skb) (&(skb)->info)
static struct mt76_tx_cb *mt76_tx_skb_cb(struct sk_buff *skb) { return &skb->cb; }
static struct mt76_wcid *__mt76_wcid_ptr(struct mt76_dev *dev, int idx) {
    return idx >= 0 && idx < 3 ? dev->wcids[idx] : NULL;
}
static struct mt76_wcid *mt76_wcid_primary(struct mt76_wcid *wcid) {
    return wcid->def_wcid ? wcid->def_wcid : wcid;
}
static struct ieee80211_sta *wcid_to_sta(struct mt76_wcid *wcid) {
    return wcid ? mt76_wcid_primary(wcid)->sta : NULL;
}
static struct mt76_phy *mt76_dev_phy(struct mt76_dev *dev, int idx) {
    return dev->phys[idx];
}
static struct ieee80211_hw *mt76_phy_hw(struct mt76_dev *dev, int idx) {
    return mt76_dev_phy(dev, idx)->hw;
}
static struct ieee80211_hw *mt76_tx_status_get_hw(struct mt76_dev *dev,
                                                struct sk_buff *skb) {
    return skb->hw;
}
static struct ieee80211_txq *mtxq_to_txq(struct mt76_txq *mtxq) { return mtxq->owner; }
static void __skb_queue_head_init(struct sk_buff_head *list) {
    list->first = list->last = NULL;
}
static void __skb_queue_tail(struct sk_buff_head *list, struct sk_buff *skb) {
    skb->next = NULL;
    if (list->last) list->last->next = skb;
    else list->first = skb;
    list->last = skb;
}
static struct sk_buff *__skb_dequeue(struct sk_buff_head *list) {
    struct sk_buff *skb = list->first;
    if (skb) {
        list->first = skb->next;
        if (!list->first) list->last = NULL;
    }
    return skb;
}
static struct {
    struct mt76_dev dev;
    struct mt76_driver_ops drv;
    struct mt76_queue_ops ops;
    struct mt76_phy phys[3];
    struct ieee80211_local local[3];
    struct sta_info peer;
    struct mt76_wcid wcids[3];
    struct mt76_queue queues[3][4];
    struct ieee80211_txq txq[17];
    struct mt76_txq mtxq[17];
} f;
static int workers, reports, premature_rearms, bad_hw, transmitted;
static bool interleave_worker;
static int mt76_txq_schedule_list(struct mt76_phy *phy, enum mt76_txq_id qid);
u32 ieee80211_txq_aql_pending(struct ieee80211_hw *hw, struct ieee80211_txq *txq);
void ieee80211_sta_update_pending_airtime(struct ieee80211_local *local,
                                         struct sta_info *sta, u8 ac,
                                         u16 airtime, bool completed, bool mcast);
static void ieee80211_schedule_txq(struct ieee80211_hw *hw,
                                  struct ieee80211_txq *txq) {
    struct mt76_txq *mtxq = txq->drv_priv;
    struct mt76_wcid *wcid = __mt76_wcid_ptr(&f.dev, mtxq->wcid);
    txq->rearms++;
    txq->last_hw = hw;
    if (wcid && hw != mt76_phy_hw(&f.dev, wcid->phy_idx)) bad_hw++;
    if (wcid && test_bit(MT_WCID_FLAG_PS, &wcid->flags) &&
        ieee80211_txq_aql_pending(hw, txq)) premature_rearms++;
    if (txq->backlog) txq->scheduled = true;
}
static void mt76_worker_schedule(int *worker) {
    workers++;
    if (!interleave_worker) return;
    /* A worker can run before tx_status_ext returns the pending airtime. */
    for (int ac = 0; ac < 4; ac++) mt76_txq_schedule_list(&f.phys[0], ac);
}
static struct ieee80211_txq *ieee80211_next_txq(struct ieee80211_hw *hw, int ac) {
    for (int i = 0; i < 17; i++) {
        if (f.txq[i].scheduled && f.txq[i].ac == ac) {
            f.txq[i].scheduled = false;
            return &f.txq[i];
        }
    }
    return NULL;
}
static void ieee80211_return_txq(struct ieee80211_hw *hw,
                                struct ieee80211_txq *txq, bool force) {
    txq->scheduled = !!txq->backlog;
}
static struct sk_buff *mt76_txq_dequeue(struct mt76_phy *phy, struct mt76_txq *mtxq) {
    struct ieee80211_txq *txq = mtxq_to_txq(mtxq);
    if (!txq->backlog) return NULL;
    txq->backlog--;
    return calloc(1, sizeof(struct sk_buff));
}
static int __mt76_tx_queue_skb(struct mt76_phy *phy, int qid, struct sk_buff *skb,
                              struct mt76_wcid *wcid, struct ieee80211_sta *sta,
                              bool *stop) {
    transmitted++;
    /* Model the next frame becoming in flight. A PS burst must then stop
     * again until that frame's completion, rather than draining all backlog. */
    ieee80211_sta_update_pending_airtime(hw_to_local(phy->hw),
        container_of(sta, struct sta_info, sta), qid, 100, false, false);
    free(skb);
    return 0;
}
static void ieee80211_get_tx_rates(struct ieee80211_vif *vif,
                                  struct ieee80211_sta *sta, struct sk_buff *skb,
                                  int *rates, int count) {}
static void ieee80211_send_bar(struct ieee80211_vif *vif, unsigned char *addr,
                              int tid, int ssn) {}
static void kick(struct mt76_dev *dev, struct mt76_queue *q) {}
'''

# This shim implements only status_ext's AQL return and skb consumption. Both
# AQL helpers below are extracted from the supplied mac80211 source, not copied.
STATUS_SHIM = r'''
static void ieee80211_tx_status_ext(struct ieee80211_hw *hw,
                                   struct ieee80211_tx_status *status) {
    struct sk_buff *skb = status->skb;
    struct sta_info *sta = status->sta ?
        container_of(status->sta, struct sta_info, sta) : NULL;
    if (skb->info.tx_time_est > 0) {
        ieee80211_sta_update_pending_airtime(hw_to_local(hw), sta, skb->ac,
                                             skb->info.tx_time_est, true, false);
        skb->info.tx_time_est = 0;
    }
    reports++;
    /* ASan catches any subsequent dereference of skb, info or cb by the fix. */
    free(skb);
}
'''

CASES = r'''
static int failed, checked;
static void check(const char *name, bool ok) {
    checked++;
    if (!ok) { failed++; printf("FAIL: %s\n", name); }
}
static void reset(void) {
    memset(&f, 0, sizeof(f));
    workers = reports = premature_rearms = bad_hw = transmitted = 0;
    interleave_worker = false;
    f.drv.drv_flags = MT_DRV_HW_PS_BUFFERING;
    f.ops.kick = kick;
    f.dev.drv = &f.drv; f.dev.queue_ops = &f.ops;
    f.dev.hw = &f.local[0].hw;
    for (int i = 0; i < 3; i++) {
        f.dev.phys[i] = &f.phys[i]; f.dev.wcids[i] = &f.wcids[i];
        /* MT7996 MLO links share one mac80211 hardware instance. */
        f.phys[i].dev = &f.dev; f.phys[i].hw = &f.local[0].hw;
        f.wcids[i].phy_idx = i; f.wcids[i].sta = &f.peer.sta;
        f.wcids[i].def_wcid = i ? &f.wcids[0] : NULL;
        for (int ac = 0; ac < 4; ac++) {
            f.phys[i].q_tx[ac] = &f.queues[i][ac];
            f.queues[i][ac].ndesc = 256;
        }
    }
    for (int i = 0; i < 17; i++) {
        f.txq[i].drv_priv = &f.mtxq[i]; f.mtxq[i].owner = &f.txq[i];
        f.txq[i].sta = &f.peer.sta; f.txq[i].tid = i;
    }
    f.peer.sta.txq[3] = &f.txq[3];
    f.txq[3].backlog = 10;
    f.wcids[0].flags = 1ul << MT_WCID_FLAG_PS;
}
static struct sk_buff *packet(int completion, int tracked, int ac, int airtime) {
    struct sk_buff *skb = calloc(1, sizeof(*skb));
    assert(skb);
    skb->hw = f.dev.hw;
    skb->ac = ac; skb->info.tx_time_est = airtime;
    skb->cb.wcid = completion;
    skb->cb.pktid = tracked ? MT_PACKET_ID_FIRST : 0;
    if (airtime) ieee80211_sta_update_pending_airtime(hw_to_local(skb->hw), &f.peer,
                                                      ac, airtime, false, false);
    return skb;
}
static void stall(void) {
    f.txq[3].scheduled = true;
    assert(mt76_txq_schedule_list(&f.phys[0], MT_TXQ_BE) == 0);
    assert(!f.txq[3].scheduled && f.txq[3].backlog == 10);
}
static void txs(struct sk_buff *skb, bool timeout) {
    struct sk_buff_head list;
    mt76_tx_status_lock(&f.dev, &list);
    __mt76_tx_status_skb_done(&f.dev, skb, MT_TX_CB_TXS_DONE |
                             (timeout ? MT_TX_CB_TXS_FAILED : 0), &list);
    mt76_tx_status_unlock(&f.dev, &list);
}
static bool ready(void) {
    return f.txq[3].scheduled && f.txq[3].rearms == 1 && workers == 1 &&
           reports == 1 && f.peer.airtime[0].aql_tx_pending == 0 &&
           premature_rearms == 0 && bad_hw == 0;
}
int main(void) {
    struct sk_buff *skb, *second;
    reset(); skb = packet(1, false, 0, 100); stall();
    __mt76_tx_complete_skb(&f.dev, 1, skb, NULL);
    check("awake secondary completion rearms sleeping primary TXQ", ready());
    mt76_txq_schedule_list(&f.phys[0], MT_TXQ_BE);
    check("backlog progresses without another enqueue or PS transition",
          f.txq[3].backlog == 9 && transmitted == 1);

    reset(); skb = packet(0, false, 0, 100); stall();
    __mt76_tx_complete_skb(&f.dev, 0, skb, NULL);
    check("single-link PS wake occurs after AQL return", ready());

    reset(); skb = packet(0, false, 0, 100); stall(); interleave_worker = true;
    __mt76_tx_complete_skb(&f.dev, 0, skb, NULL);
    check("worker interleaving cannot consume the wake before AQL return",
          reports == 1 && premature_rearms == 0 && transmitted == 1);

    for (int completion = 0; completion < 2; completion++) {
        for (int timeout = 0; timeout < 2; timeout++) {
            reset(); skb = packet(completion, true, 0, 100); stall();
            __mt76_tx_complete_skb(&f.dev, completion, skb, NULL);
            check("DMA alone retains AQL and does not prematurely wake",
                  reports == 0 && workers == 0 && f.txq[3].rearms == 0 &&
                  f.peer.airtime[0].aql_tx_pending == 100);
            txs(skb, timeout);
            check("later TXS or timeout returns airtime and rearms", ready());
        }
    }
    reset(); skb = packet(1, true, 0, 100); stall(); txs(skb, false);
    check("TXS before DMA retains AQL without waking", reports == 0 && workers == 0);
    __mt76_tx_complete_skb(&f.dev, 1, skb, NULL);
    check("DMA after TXS rearms through status_unlock", ready());

    reset(); skb = packet(1, false, 0, 60); second = packet(1, false, 0, 40); stall();
    __mt76_tx_complete_skb(&f.dev, 1, skb, NULL);
    check("remaining AC airtime prevents rearm",
          workers == 0 && f.txq[3].rearms == 0 && f.peer.airtime[0].aql_tx_pending == 40);
    __mt76_tx_complete_skb(&f.dev, 1, second, NULL);
    check("last completion with outstanding AC airtime rearms",
          reports == 2 && f.txq[3].scheduled && workers == 1 && premature_rearms == 0);

    reset(); skb = packet(1, false, 0, 100); stall();
    f.mtxq[3].wcid = 2; f.wcids[2].flags = 1ul << MT_WCID_FLAG_PS;
    /* Also exercise the generic helper's choice of current TXQ PHY. */
    f.phys[2].hw = &f.local[2].hw;
    f.wcids[0].flags = 0;
    __mt76_tx_complete_skb(&f.dev, 1, skb, NULL);
    check("changed primary uses current TXQ WCID and its PHY", ready());

    reset(); skb = packet(0, false, 0, 100); stall(); f.mtxq[3].wcid = 2;
    __mt76_tx_complete_skb(&f.dev, 0, skb, NULL);
    check("old sleeping primary completion still wakes new awake TXQ", ready());

    reset(); skb = packet(0, false, 0, 60); second = packet(1, false, 0, 40); stall();
    f.mtxq[3].wcid = 2;
    __mt76_tx_complete_skb(&f.dev, 0, skb, NULL);
    check("new awake TXQ need not wait for all remaining AC airtime",
          f.txq[3].rearms == 1 && workers == 1 && f.txq[3].scheduled &&
          f.peer.airtime[0].aql_tx_pending == 40 && premature_rearms == 0 && bad_hw == 0);
    __mt76_tx_complete_skb(&f.dev, 1, second, NULL);

    reset(); skb = packet(0, true, 0, 100); stall();
    __mt76_tx_complete_skb(&f.dev, 0, skb, NULL); f.mtxq[3].wcid = 2;
    txs(skb, false);
    check("delayed sleeping-link status wakes replacement awake primary", ready());

    reset(); skb = packet(1, true, 0, 100); stall();
    __mt76_tx_complete_skb(&f.dev, 1, skb, NULL);
    f.mtxq[3].wcid = 2; f.wcids[0].flags = 0;
    f.wcids[2].flags = 1ul << MT_WCID_FLAG_PS;
    txs(skb, false);
    check("primary changed between DMA and TXS is checked at airtime return", ready());

    reset(); f.peer.sta.txq[7] = &f.txq[7]; f.txq[7].ac = MT_TXQ_VO;
    f.txq[7].backlog = 10;
    skb = packet(1, false, 0, 100); second = packet(1, false, MT_TXQ_VO, 100); stall();
    __mt76_tx_complete_skb(&f.dev, 1, skb, NULL);
    check("a different AC's pending airtime does not block ready AC",
          f.txq[3].rearms == 1 && f.txq[7].rearms == 0 && premature_rearms == 0);
    __mt76_tx_complete_skb(&f.dev, 1, second, NULL);
    check("other AC is rearmed when its airtime is returned", f.txq[7].rearms == 1);

    reset(); skb = packet(0, false, 0, 100); f.wcids[0].flags = 0;
    __mt76_tx_complete_skb(&f.dev, 0, skb, NULL);
    check("awake non-MLO station gains no PS wake", reports == 1 && workers == 0 &&
          f.txq[3].rearms == 0);

    reset(); f.mtxq[3].wcid = 1; f.wcids[1].def_wcid = NULL;
    f.wcids[1].flags = 1ul << MT_WCID_FLAG_PS;
    f.phys[1].hw = f.dev.hw = &f.local[1].hw;
    skb = packet(1, false, 0, 100); stall();
    __mt76_tx_complete_skb(&f.dev, 1, skb, NULL);
    check("single-link station on another hardware PHY keeps its wake", ready());

    /* Existing lifecycle limitation, deliberately not asserted as fixed:
     * after a primary replacement, both the completing and current WCIDs
     * may be awake even though the queue was blocked by the old primary. */
    reset(); skb = packet(1, false, 0, 100); stall(); f.mtxq[3].wcid = 2;
    __mt76_tx_complete_skb(&f.dev, 1, skb, NULL);
    assert(!f.txq[3].scheduled && workers == 0);
    reset(); skb = packet(0, true, 0, 100); f.drv.drv_flags = 0;
    __mt76_tx_complete_skb(&f.dev, 0, skb, NULL); txs(skb, false);
    check("non-HW-PS driver gains no PS wake", reports == 1 && workers == 0 &&
          f.txq[3].rearms == 0);
    reset(); skb = packet(0, false, 0, 100); f.mtxq[3].wcid = 99;
    __mt76_tx_complete_skb(&f.dev, 0, skb, NULL);
    check("missing current WCID is ignored", reports == 1 && workers == 0 &&
          f.txq[3].rearms == 0);
    reset(); skb = packet(0, false, 0, 100); f.wcids[0].sta = NULL;
    __mt76_tx_complete_skb(&f.dev, 0, skb, NULL);
    check("missing station is safe", reports == 1 && workers == 0);

    reset(); skb = packet(0, false, 0, 0); f.wcids[0].flags = 0;
    f.wcids[0].non_aql_packets = MT_MAX_NON_AQL_PKT;
    __mt76_tx_complete_skb(&f.dev, 0, skb, NULL);
    check("non-AQL threshold wake remains intact", f.wcids[0].non_aql_packets ==
          MT_MAX_NON_AQL_PKT - 1 && f.txq[3].rearms == 1 && workers == 0);
    printf("%d checks, %d failed\n", checked, failed);
    return failed ? 1 : 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--mac80211-dir', type=Path)
    args = parser.parse_args()
    source = (args.source_dir / 'tx.c').read_text()
    if hashlib.sha256(source.encode()).hexdigest() != (
            'c80cde5856b25008e04c5d91046fe8d2a46dcd55456e0ebf09d68fd2fbb8ce3b'):
        raise SystemExit('Expected unmodified tx.c from pinned mt76 01367e60.')
    mac_dir = args.mac80211_dir or args.source_dir.parent / 'mac80211-regular/backports-7.2'
    mac_tx = (mac_dir / 'net/mac80211/tx.c').read_text()
    mac_sta = (mac_dir / 'net/mac80211/sta_info.c').read_text()
    aql = extract(mac_tx, 'u32 ieee80211_txq_aql_pending(',
                  '\nEXPORT_SYMBOL(ieee80211_txq_aql_pending)')
    aql += extract(mac_sta, 'void ieee80211_sta_update_pending_airtime(',
                   '\nstatic struct ieee80211_sta_rx_stats *')
    patch = (Path(__file__).resolve().parents[1] / 'package/kernel/mt76/patches/'
             '0008-mt76-wake-ps-txqs-after-aql-return.patch')
    with tempfile.TemporaryDirectory(prefix='mt76-ps-wake-') as temporary:
        work = Path(temporary)
        (work / 'tx.c').write_text(source)
        for patched in (False, True):
            if patched:
                subprocess.run(['patch', '-s', '--fuzz=0', '-p1', '-i', str(patch)],
                               cwd=work, check=True)
            current = (work / 'tx.c').read_text()
            functions = extract(current, 'static int\nmt76_txq_get_qid(',
                                '\nvoid\nmt76_tx_check_agg_ssn(')
            functions += extract(current, 'void\nmt76_tx_status_lock(',
                                 '\nvoid\nmt76_tx_status_skb_done(')
            functions += extract(current, 'static void\nmt76_tx_check_non_aql(',
                                 '\nstatic int\n__mt76_tx_queue_skb(')
            functions += extract(current, 'static bool\nmt76_txq_stopped(',
                                 '\nvoid mt76_txq_schedule(')
            label = 'patched' if patched else 'baseline'
            c_file, binary = work / (label + '.c'), work / label
            c_file.write_text(STUBS + aql + STATUS_SHIM + functions + CASES)
            subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra',
                            '-Werror', '-Wno-unused-parameter', '-Wno-sign-compare',
                            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                            str(c_file), '-o', str(binary)], check=True)
            print(label + ':', flush=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            print(result.stdout, end='')
            if result.stderr:
                raise SystemExit(result.stderr)
            expected = 0 if patched else 1
            if result.returncode != expected or ' checks, ' not in result.stdout:
                raise SystemExit(f'{label}: unexpected return code {result.returncode}')
    print('Pinned-source regression reproduced before 0008; all checks pass after it (ASan/UBSan).')


if __name__ == '__main__':
    main()
