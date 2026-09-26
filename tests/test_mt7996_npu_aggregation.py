#!/usr/bin/env python3
"""Check NPU TXS aggregation-timer refresh using extracted host code.

The actual PID/WCID/RCU dispatcher, refresh if-block, mac80211 refresh/timer
functions and negotiated-timeout assignment are compiled with ASan/UBSan.
--patch applies only to a temporary mac.c. --expect-missing-npu-refresh requires
the exact baseline failure: accepted periodic NPU TXS leaves last_tx unchanged
and the real timer callback stops the session. Other failures are not accepted.

Firmware emission/PID selection, complete TXS rate/status processing, timer
concurrency and hardware are not modeled. This proves conditional host behavior,
not the Air's negotiated timeout, fastpath TXS frequency or observed stall cause.
"""
import argparse
import hashlib
from pathlib import Path
import re
import runpy
import subprocess
import tempfile


def block(source, opening):
    """Keep a balanced C block verbatim, as in the existing lifecycle fixture."""
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[opening:end]


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint32_t __le32;
#define GENMASK(h, l) ((UINT32_MAX >> (31 - (h))) & (UINT32_MAX << (l)))
#define FIELD_GET(mask, value) (((value) & (mask)) >> __builtin_ctz(mask))
#define FIELD_PREP(mask, value) (((u32)(value) << __builtin_ctz(mask)) & (mask))
#define le32_get_bits(value, mask) FIELD_GET(mask, value)
#define le16_to_cpu(value) (value)
#define container_of(p, type, member) ((type *)((char *)(p) - offsetof(type, member)))
#define timer_container_of(p, timer, member) container_of(timer, __typeof__(*(p)), member)
#define EXPORT_SYMBOL(...)
#define IEEE80211_NUM_TIDS 16
#define HT_AGG_STATE_STOPPING 0
#define test_bit(bit, value) (!!(*(value) & (1ul << (bit))))
#define ht_dbg(...)
static int warnings, rcu_depth, status_depth;
#define WARN_ON_ONCE(condition) ((condition) ? (++warnings, 1) : 0)
#define rcu_read_lock() (++rcu_depth)
#define rcu_read_unlock() do { assert(rcu_depth == 1); --rcu_depth; } while (0)
#define rcu_dereference(value) (assert(rcu_depth == 1), (value))
static unsigned long jiffies;
/* Deterministic HZ=1000 fixture, no wraparound/timer concurrency claim. */
static unsigned long usecs_to_jiffies(unsigned long us) { return (us + 999) / 1000; }
#define time_is_after_jiffies(value) ((long)(jiffies - (value)) < 0)
struct timer_list { bool armed; unsigned long expires; unsigned arms; };
struct ieee80211_sta { int unused; };
struct sta_info;
struct tid_ampdu_tx {
    struct timer_list session_timer;
    struct sta_info *sta;
    u8 tid;
    u16 timeout;
    unsigned long state, last_tx;
    unsigned stops;
};
struct sta_info {
    struct ieee80211_sta sta;
    struct { struct tid_ampdu_tx *tid_tx[IEEE80211_NUM_TIDS]; } ampdu_mlme;
};
struct mt76_wcid { bool sta; struct ieee80211_sta *peer; };
struct mt76_dev { struct { bool wed; } mmio; bool npu; };
struct mt7996_dev { struct mt76_dev mt76; };
struct ieee80211_mgmt {
    struct { struct { struct { u16 timeout; } addba_resp; } action; } u;
};
static struct {
    struct mt7996_dev dev;
    struct mt76_wcid wcid;
    struct sta_info peer;
    struct tid_ampdu_tx session[2];
    unsigned accepted;
} f;
static bool mtk_wed_device_active(bool *wed) { return *wed; }
static bool mt76_npu_device_active(struct mt76_dev *dev) { return dev->npu; }
static struct mt76_wcid *mt76_wcid_ptr(struct mt7996_dev *dev, u16 idx) {
    assert(dev == &f.dev && rcu_depth == 1);
    return idx == 7 ? &f.wcid : NULL;
}
static struct ieee80211_sta *wcid_to_sta(struct mt76_wcid *wcid) {
    assert(wcid->sta && rcu_depth == 1 && status_depth == 1);
    return wcid->peer;
}
static int mod_timer(struct timer_list *timer, unsigned long expires) {
    timer->armed = true; timer->expires = expires; timer->arms++; return 0;
}
static void ieee80211_stop_tx_ba_session(struct ieee80211_sta *sta, u16 tid) {
    struct sta_info *peer = container_of(sta, struct sta_info, sta);
    struct tid_ampdu_tx *session = peer->ampdu_mlme.tid_tx[tid];
    assert(session); session->stops++; session->state |= 1ul << HT_AGG_STATE_STOPPING;
}
'''


CASES = r'''
static int checked, failed, expected;
static void check(const char *name, bool ok) {
    checked++; failed += !ok; printf("%s %s\n", ok ? "PASS" : "FAIL", name);
}
static void setup(bool wed, bool npu, bool station, u16 timeout) {
    memset(&f, 0, sizeof(f)); jiffies = 100;
    assert(rcu_depth == 0 && status_depth == 0);
    f.dev.mt76.mmio.wed = wed; f.dev.mt76.npu = npu;
    f.wcid.sta = station; f.wcid.peer = &f.peer.sta;
    for (unsigned i = 0; i < 2; i++) {
        struct tid_ampdu_tx *s = &f.session[i];
        s->sta = &f.peer; s->tid = i ? 5 : 3;
        f.peer.ampdu_mlme.tid_tx[s->tid] = s;
        negotiate(s, timeout);
    }
}
static void event(unsigned tid, unsigned pid, unsigned wcid, unsigned format) {
    __le32 words[4] = {
        FIELD_PREP(MT_TXS0_TID, tid) | FIELD_PREP(MT_TXS0_TXS_FORMAT, format),
        0, FIELD_PREP(MT_TXS2_WCID, wcid), FIELD_PREP(MT_TXS3_PID, pid)
    };
    mt7996_mac_add_txs(&f.dev, words);
    assert(rcu_depth == 0 && status_depth == 0);
}
static void poll_timer(struct tid_ampdu_tx *s) {
    if (!s->session_timer.armed || s->session_timer.expires > jiffies) return;
    s->session_timer.armed = false;
    sta_tx_agg_session_timer_expired(&s->session_timer);
}
static void periodic(unsigned tid, unsigned pid, unsigned format) {
    for (jiffies = 101; jiffies <= 120; jiffies++) {
        if (jiffies % 5 == 0) event(tid, pid, 7, format);
        poll_timer(&f.session[0]);
    }
}
static void check_npu_progress(bool baseline, const char *name) {
    if (baseline) {
        bool exact = f.accepted == 4 && f.session[0].last_tx == 100 &&
                     f.session[0].stops == 1 && !f.session[0].session_timer.armed;
        checked++;
        if (exact) {
            expected++;
            printf("EXPECTED_FAIL %s: accepted TXS, stale last_tx, false-idle stop\n", name);
        } else {
            failed++;
            printf("FAIL %s: baseline did not have the exact false-idle outcome\n", name);
        }
    } else {
        check(name, f.accepted == 4 && f.session[0].last_tx == 120 &&
              f.session[0].stops == 0 && f.session[0].session_timer.armed);
    }
}
int main(int argc, char **argv) {
    bool baseline = argc == 2 && !strcmp(argv[1], "baseline");
    setup(false, true, true, 10);
    check("peer-negotiated nonzero timeout arms the real timer", f.session[0].timeout == 10 &&
          f.session[0].session_timer.armed && f.session[0].session_timer.expires == 111);
    periodic(3, MT_PACKET_ID_NO_SKB, 2);
    check("NPU periodic PID=NO_SKB TXS reaches actual dispatcher", f.accepted == 4);
    check_npu_progress(baseline, "NPU periodic PPDU NO_SKB TXS keeps BA session alive");
    setup(false, true, true, 10); periodic(3, MT_PACKET_ID_NO_SKB, 0);
    check_npu_progress(baseline, "NPU-only MPDU NO_SKB TXS keeps BA session alive");

    setup(true, false, true, 10); periodic(3, MT_PACKET_ID_WED, 2);
    check("existing WED refresh is retained", f.session[0].last_tx == 120 && !f.session[0].stops);
    setup(true, true, true, 10); periodic(3, MT_PACKET_ID_NO_SKB, 0);
    check("both engines and MPDU NO_SKB preserve refresh", f.session[0].last_tx == 120 && !f.session[0].stops);
    setup(false, false, true, 10); periodic(3, MT_PACKET_ID_NO_SKB, 2);
    check("neither offload engine adds a refresh", f.session[0].last_tx == 100 && f.session[0].stops == 1);
    setup(true, true, false, 10); periodic(3, MT_PACKET_ID_NO_SKB, 2);
    check("non-station WCID does not refresh a session", f.session[0].last_tx == 100 && f.session[0].stops == 1);
    setup(true, true, true, 10); f.peer.ampdu_mlme.tid_tx[3] = NULL;
    jiffies = 105; event(3, MT_PACKET_ID_NO_SKB, 7, 2);
    check("no BA session is a safe no-op", f.accepted == 1 && f.session[0].last_tx == 100);
    setup(true, true, true, 10); periodic(5, MT_PACKET_ID_NO_SKB, 2);
    check("TXS refreshes its TID without retaining another idle TID", f.session[0].last_tx == 100 &&
          f.session[0].stops == 1 && f.session[1].last_tx == 120);
    setup(true, true, true, 10); jiffies = 105; event(3, MT_PACKET_ID_NO_SKB, 7, 2);
    jiffies = 112; poll_timer(&f.session[0]);
    check("activity moves timer expiry using the actual callback", !f.session[0].stops &&
          f.session[0].session_timer.expires == 116);
    jiffies = 116; poll_timer(&f.session[0]);
    check("genuine silence still expires the session at its deadline", f.session[0].stops == 1);
    setup(true, true, true, 0); periodic(3, MT_PACKET_ID_NO_SKB, 2);
    check("negotiated timeout zero never arms an inactivity timer", !f.session[0].timeout &&
          !f.session[0].session_timer.armed && !f.session[0].stops);
    setup(true, true, true, 10); periodic(3, MT_PACKET_ID_NO_ACK, 2);
    check("PID zero is rejected by the real outer dispatcher", !f.accepted && f.session[0].stops == 1);
    setup(true, true, true, 10); jiffies = 105; event(3, MT_PACKET_ID_FIRST, 7, 0);
    check("tracked PID also reaches refresh", f.accepted == 1 && f.session[0].last_tx == 105);
    setup(true, true, true, 10); jiffies = 105; event(3, MT_PACKET_ID_NO_SKB, 8, 2);
    check("missing WCID is rejected under RCU", !f.accepted && f.session[0].last_tx == 100);
    setup(true, true, true, 10); f.session[0].state = 1ul << HT_AGG_STATE_STOPPING;
    jiffies = 111; poll_timer(&f.session[0]);
    check("already stopping session is not stopped twice", !f.session[0].stops);
    check("tested TIDs and lock fixture contracts stayed valid", !warnings && !rcu_depth && !status_depth);
    printf("%d checks, %d failed, %d expected failure\n", checked, failed, expected);
    return failed ? 1 : 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True, help='mt76 prepared source')
    parser.add_argument('--mac80211-dir', type=Path, required=True, help='backports/net/mac80211 directory')
    parser.add_argument('--patch', type=Path, help='Apply with fuzz 0 to a temporary mac.c only')
    parser.add_argument('--expect-missing-npu-refresh', action='store_true', help='Require exact old-code false-idle failure')
    args = parser.parse_args()
    extractor = Path(__file__).with_name('test_mt76_ps_wake.py')
    extract = runpy.run_path(str(extractor))['extract']
    sources = {name: (args.source_dir / name).read_text() for name in
               ('mt7996/mac.c', 'mt76.h', 'mt76_connac3_mac.h')}
    agg = (args.mac80211_dir / 'agg-tx.c').read_text()
    ieee = (args.mac80211_dir.parent.parent / 'include/linux/ieee80211.h').read_text()
    for name, source in list(sources.items()) + [('agg-tx.c', agg), ('ieee80211.h', ieee),
                                                (extractor.name, extractor.read_text())]:
        print(f'INPUT {name} sha256={hashlib.sha256(source.encode()).hexdigest()}', flush=True)
    with tempfile.TemporaryDirectory(prefix='mt7996-npu-aggregation-') as temporary:
        work = Path(temporary)
        driver = sources['mt7996/mac.c']
        if args.patch:
            (work / 'mt7996').mkdir()
            (work / 'mt7996/mac.c').write_text(driver)
            subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i',
                            str(args.patch.resolve())], cwd=work, check=True)
            driver = (work / 'mt7996/mac.c').read_text()
        inner = extract(driver, 'static bool\nmt7996_mac_add_txs_skb(', '\nstatic void mt7996_mac_add_txs(')
        gate_end = inner.index('\n\ttxrate =')
        gate_start = inner.rindex('\n\tif (', 0, gate_end)
        gate = inner[gate_start:gate_end]
        assert gate.count('ieee80211_refresh_tx_agg_session_timer(sta, tid);') == 1
        assert 'wcid->sta' in gate and 'FIELD_GET(MT_TXS0_TID, txs)' in gate
        prefix = inner[:gate_start]
        assert 'mt76_tx_status_lock(mdev, &list);' in prefix
        assert 'mt76_tx_status_skb_get(mdev, wcid, pid, &list)' in prefix
        assert not re.search(r'\b(return|goto)\b', prefix), 'refresh must not require a tracked skb'
        dispatch = extract(driver, 'static void mt7996_mac_add_txs(', '\nbool mt7996_rx_check(')
        assert 'pid < MT_PACKET_ID_NO_SKB' in dispatch
        assert dispatch.index('rcu_read_lock();') < dispatch.index('mt7996_mac_add_txs_skb(') < dispatch.index('rcu_read_unlock();')
        definitions = []
        for name, source in [(n, sources['mt76_connac3_mac.h']) for n in
                              ('MT_TXS0_TID', 'MT_TXS0_TXS_FORMAT', 'MT_TXS2_WCID', 'MT_TXS3_PID')] + [
                             (n, sources['mt76.h']) for n in ('MT_PACKET_ID_NO_ACK', 'MT_PACKET_ID_NO_SKB',
                                                              'MT_PACKET_ID_WED', 'MT_PACKET_ID_FIRST')] + [
                             ('TU_TO_JIFFIES', ieee), ('TU_TO_EXP_TIME', ieee)]:
            definitions.append(re.search(r'^#define ' + name + r'\b[^\n]*', source, re.M)[0] + '\n')
        refresh = extract(agg, 'void ieee80211_refresh_tx_agg_session_timer(', '\nEXPORT_SYMBOL(ieee80211_refresh_tx_agg_session_timer)')
        timer = extract(agg, 'static void sta_tx_agg_session_timer_expired(', '\nint ieee80211_start_tx_ba_session(')
        start = agg.index('\t\ttid_tx->timeout =\n\t\t\tle16_to_cpu(mgmt->u.action.addba_resp.timeout);')
        opening = agg.index('{', agg.index('if (tid_tx->timeout)', start))
        negotiated = agg[start:opening] + block(agg, opening)
        functions = refresh + timer + '''
static void negotiate(struct tid_ampdu_tx *tid_tx, u16 timeout) {
    struct ieee80211_mgmt response = { .u.action.addba_resp.timeout = timeout };
    struct ieee80211_mgmt *mgmt = &response;
''' + negotiated + '\n}\n'
        functions += '''
/* Rate/status work is omitted; its existing lock context is represented here. */
static bool mt7996_mac_add_txs_skb(struct mt7996_dev *dev, struct mt76_wcid *wcid,
                                int pid, __le32 *txs_data) {
    struct mt76_dev *mdev = &dev->mt76;
    u32 txs = txs_data[0];
    (void)mdev; (void)pid;
    assert(rcu_depth == 1 && status_depth == 0); status_depth++;
    f.accepted++;
''' + gate + '\n    status_depth--; return false;\n}\n' + dispatch
        c = work / 'aggregation.c'
        c.write_text(STUBS + ''.join(definitions) + functions + CASES)
        print('EXTRACT gate/dispatcher/refresh/timer/negotiated-timeout sha256=' +
              hashlib.sha256(functions.encode()).hexdigest(), flush=True)
        subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-parameter', '-Wno-unused-function', '-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', str(c), '-o',
                        str(work / 'aggregation')], check=True)
        command = [str(work / 'aggregation')]
        if args.expect_missing_npu_refresh:
            command.append('baseline')
        return subprocess.run(command).returncode


if __name__ == '__main__':
    raise SystemExit(main())
