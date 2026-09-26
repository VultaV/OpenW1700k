#!/usr/bin/env python3
"""Exercise the extracted mt7996 forward-path callback with scheduled mutations.

Usage: test_mt7996_forward_path.py /path/to/mt76
Runs both NPU-only and WED-enabled compilation under ASan/UBSan. RCU and
hardware are stubs; the RCU-only caller/mutex-only helper contract is modeled,
not kernel lockdep. Mutation hooks represent interleavings, not real threads.
The final-read case demonstrates the remaining check-to-use window. This does
not prove atomic publication, invalidate existing PPE entries, or test firmware.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def function(source, name):
    match = re.search(r'^static int\s+' + name + r'\(', source, re.M)
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
#include <string.h>
typedef uint8_t u8;
#define IEEE80211_MLD_MAX_NUM_LINKS 16
#define MT7996_WTBL_STA 1087
#define MT_BAND1 1
#define MT_BAND2 2
#define DEV_PATH_MTK_WDMA 9
#define SUPPORTS_AMSDU_IN_AMPDU 1
struct mtk_wed_device { bool active, amsdu; unsigned wdma_idx; };
struct mt76_dev {
    struct { struct mtk_wed_device wed, wed_hif2; } mmio;
    bool npu;
    unsigned chip;
};
struct mt7996_dev { struct mt76_dev mt76; bool hif2; };
struct ieee80211_hw { struct mt7996_dev *dev; bool amsdu; };
struct ieee80211_vif { void *drv_priv; };
struct mt76_wcid { unsigned idx, phy_idx; bool sta, link_valid, amsdu; };
struct mt7996_sta_link { struct mt76_wcid wcid; };
struct mt7996_sta { u8 deflink_id; struct mt7996_sta_link *link[16]; };
struct ieee80211_sta { void *drv_priv; bool mlo; };
struct mt76_vif_link { unsigned idx, band_idx; };
struct mt7996_vif_link { struct mt76_vif_link mt76; };
struct mt76_vif_data { struct mt76_vif_link *link[16]; };
struct mt7996_vif { struct mt7996_vif_link deflink; struct mt76_vif_data mt76; };
struct net_device { int unused; };
struct net_device_path_ctx { struct net_device *dev; };
struct net_device_path {
    unsigned type;
    struct net_device *dev;
    struct { unsigned wdma_idx, bss, queue, wcid, amsdu; } mtk_wdma;
};
enum mutation { NONE, BETWEEN_LOOKUPS, LOOKUP_ABA, LATE_SELECTOR,
                LATE_INACTIVE, AFTER_FINAL_OBSERVATION };
static struct {
    struct mt7996_dev dev;
    struct ieee80211_hw hw;
    struct ieee80211_vif vif;
    struct ieee80211_sta sta;
    struct mt7996_sta msta;
    struct mt7996_vif mvif;
    struct mt7996_sta_link peer[16];
    struct mt7996_vif_link bss[16];
    struct net_device net;
    struct net_device_path_ctx ctx;
    struct net_device_path path;
    enum mutation mutation;
    int missing_bss, missing_peer;
    unsigned vif_lookup, sta_lookup, valid_reads;
    unsigned rcu_depth, mutex_depth, protected_without_mutex;
    bool fired;
} f;
static unsigned long read_once(const void *address, unsigned size) {
    unsigned long value = 0;
    assert(size <= sizeof(value));
    memcpy(&value, address, size);
    if (address == &f.peer[1].wcid.link_valid && ++f.valid_reads == 2 &&
        f.mutation == AFTER_FINAL_OBSERVATION) {
        /* The read returned its old value; a writer runs immediately after it. */
        f.msta.deflink_id = 2;
        f.fired = true;
    }
    return value;
}
#define READ_ONCE(x) ((__typeof__(x))read_once(&(x), sizeof(x)))
static struct mt7996_dev *mt7996_hw_dev(struct ieee80211_hw *hw) { return hw->dev; }
static struct mt76_vif_link *read_vif_slot(unsigned id) {
    struct mt76_vif_link *value = f.mvif.mt76.link[id];
    f.vif_lookup = id;
    if (f.mutation == BETWEEN_LOOKUPS || f.mutation == LOOKUP_ABA) {
        f.msta.deflink_id = 2;
        f.fired = true;
    }
    return (int)id == f.missing_bss ? NULL : value;
}
static void *read_rcu_pointer(const void *slot) {
    void *value;
    assert(f.rcu_depth == 1);
    for (unsigned i = 0; i < 16; i++)
        if (slot == &f.mvif.mt76.link[i]) return read_vif_slot(i);
    memcpy(&value, slot, sizeof(value));
    return value;
}
#define rcu_dereference(p) ((__typeof__(p))read_rcu_pointer(&(p)))
static struct mt7996_vif_link *mt7996_vif_link(struct mt7996_dev *dev,
    struct ieee80211_vif *vif, unsigned id) {
    /* Match mt76_vif_link: embedded link 0, protected dereference otherwise. */
    if (!id) return &f.mvif.deflink;
    if (id >= 16) return NULL;
    if (!f.mutex_depth) f.protected_without_mutex++;
    return (struct mt7996_vif_link *)read_vif_slot(id);
}
static struct mt7996_sta_link *mt7996_sta_link(struct mt7996_sta *sta, u8 id) {
    f.sta_lookup = id;
    if (f.mutation == LOOKUP_ABA) f.msta.deflink_id = 1;
    return id >= 16 || (int)id == f.missing_peer ? NULL : rcu_dereference(sta->link[id]);
}
static bool is_mt7996(struct mt76_dev *dev) { return dev->chip == 7996; }
static bool is_mt7992(struct mt76_dev *dev) { return dev->chip == 7992; }
static bool mtk_wed_device_active(struct mtk_wed_device *wed) { return wed->active; }
static bool mt76_npu_device_active(struct mt76_dev *dev) { return dev->npu; }
static bool mtk_wed_is_amsdu_supported(struct mtk_wed_device *wed) { return wed->amsdu; }
static bool ieee80211_hw_check(struct ieee80211_hw *hw, int flag) {
    if (f.mutation == LATE_SELECTOR) {
        f.msta.deflink_id = 2;
        f.fired = true;
    } else if (f.mutation == LATE_INACTIVE) {
        f.peer[1].wcid.link_valid = false;
        f.fired = true;
    }
    return hw->amsdu;
}
'''


CASES = r'''
static unsigned checked, failed;
static void check(const char *name, bool ok) {
    checked++;
    if (!ok) { failed++; printf("FAIL: %s\n", name); }
}
static void setup(bool mlo) {
    memset(&f, 0, sizeof(f));
    f.dev.mt76.chip = 7996; f.dev.mt76.npu = true;
    f.hw.dev = &f.dev; f.hw.amsdu = true;
    f.vif.drv_priv = &f.mvif;
    f.sta.drv_priv = &f.msta; f.sta.mlo = mlo;
    f.msta.deflink_id = 1; f.ctx.dev = &f.net;
    f.missing_bss = f.missing_peer = -1;
    f.vif_lookup = f.sta_lookup = 255;
    for (unsigned i = 0; i < 16; i++) {
        f.peer[i].wcid = (struct mt76_wcid){ .idx = 100 + i,
            .phy_idx = i, .sta = true, .link_valid = mlo, .amsdu = true };
        f.msta.link[i] = &f.peer[i];
        f.bss[i].mt76.idx = 20 + i; f.bss[i].mt76.band_idx = i;
        f.mvif.mt76.link[i] = &f.bss[i].mt76;
    }
    f.mvif.deflink.mt76 = f.bss[0].mt76;
}
static int fill(void) {
    assert(f.mutex_depth == 0 && f.rcu_depth == 0);
    f.rcu_depth++;
    int ret = mt7996_net_fill_forward_path(&f.hw, &f.vif, &f.sta, &f.ctx, &f.path);
    f.rcu_depth--;
    return ret;
}
static bool consistent(unsigned id) {
    return f.path.mtk_wdma.bss == 20 + id && f.path.mtk_wdma.wcid == 100 + id;
}
static void rejected(const char *name, int expected) {
    check(name, fill() == expected);
    check("rejection preserves forward-path context", f.ctx.dev == &f.net);
}
int main(void) {
    setup(true);
    check("stable MLO succeeds", fill() == 0);
    check("stable MLO BSS/WCID pair", consistent(1));
    check("RCU-only callback avoids mutex-protected VIF lookup", f.protected_without_mutex == 0);
    check("stable NPU queue selection", f.path.mtk_wdma.wdma_idx == 1);
    check("successful path consumes context", f.ctx.dev == NULL);
    check("successful path records type/device/queue", f.path.type == DEV_PATH_MTK_WDMA &&
          f.path.dev == &f.net && f.path.mtk_wdma.queue == 0);
    check("no WED AMSDU capability stays disabled", f.path.mtk_wdma.amsdu == 0);

    setup(true); f.msta.deflink_id = 2;
    check("NPU 6GHz succeeds", fill() == 0 && consistent(2));
    check("NPU 6GHz uses queue index 1", f.path.mtk_wdma.wdma_idx == 1);

    setup(false);
    check("non-MLO link_valid=false remains eligible", !f.peer[1].wcid.link_valid && fill() == 0);
    check("non-MLO BSS/WCID pair preserved", consistent(1));
    setup(false); f.msta.deflink_id = 0; f.mvif.mt76.link[0] = NULL;
    check("link zero uses embedded VIF even without array entry", fill() == 0 && consistent(0));
    check("embedded default link needs no protected lookup", f.protected_without_mutex == 0);

    setup(true); f.peer[1].wcid.link_valid = false;
    rejected("inactive MLO link rejected", -EIO);

    setup(true); f.mutation = BETWEEN_LOOKUPS;
    rejected("primary change between lookups rejected", -EIO);
    check("scheduled primary change occurred", f.fired);
    check("BSS and station lookups use one selector", f.vif_lookup == f.sta_lookup);

    setup(true); f.mutation = LOOKUP_ABA;
    check("selector ABA can return coherent original snapshot", fill() == 0);
    check("selector ABA never mixes BSS and WCID", consistent(1));
    check("selector ABA lookups remain equal", f.vif_lookup == f.sta_lookup);

    setup(true); f.mutation = LATE_SELECTOR;
    rejected("observed late selector change rejected", -EIO);
    check("late selector change occurred", f.fired);

    setup(true); f.mutation = LATE_INACTIVE;
    rejected("observed late MLO inactivity rejected", -EIO);
    check("late inactive transition occurred", f.fired);

    setup(false); f.mutation = LATE_INACTIVE;
    check("non-MLO remains eligible with unchanged false validity", fill() == 0 && consistent(1));

    setup(true); f.missing_bss = 1; rejected("missing VIF link rejected", -EIO);
    setup(true); f.mvif.mt76.link[1] = NULL;
    rejected("unpublished VIF link rejected under RCU", -EIO);
    setup(true); f.missing_peer = 1; rejected("missing station link rejected", -EIO);
    setup(true); f.peer[1].wcid.sta = false; rejected("non-station WCID rejected", -EIO);
    setup(true); f.peer[1].wcid.idx = MT7996_WTBL_STA + 1; rejected("out of range WCID rejected", -EIO);
    setup(true); f.msta.deflink_id = 255; rejected("unspecified selector rejected", -EIO);
    setup(true); f.dev.mt76.npu = false; rejected("inactive acceleration rejected", -ENODEV);

#ifdef CONFIG_NET_MEDIATEK_SOC_WED
    setup(true); f.dev.mt76.npu = false;
    f.dev.mt76.mmio.wed = (struct mtk_wed_device){ .active = true, .amsdu = true, .wdma_idx = 7 };
    check("WED route unchanged", fill() == 0 && consistent(1) && f.path.mtk_wdma.wdma_idx == 7);
    check("WED AMSDU retained", f.path.mtk_wdma.amsdu == 1);
    setup(true); f.dev.hif2 = true; f.msta.deflink_id = 2;
    f.dev.mt76.mmio.wed_hif2 = (struct mtk_wed_device){ .active = true, .amsdu = true, .wdma_idx = 8 };
    check("MT7996 second WED HIF unchanged", fill() == 0 && consistent(2) && f.path.mtk_wdma.wdma_idx == 8);
    setup(true); f.dev.hif2 = true; f.dev.mt76.chip = 7992;
    f.dev.mt76.mmio.wed_hif2 = (struct mtk_wed_device){ .active = true, .amsdu = true, .wdma_idx = 8 };
    check("MT7992 second WED HIF unchanged", fill() == 0 && consistent(1) && f.path.mtk_wdma.wdma_idx == 8);
#endif

    /* This documents a limit, not a promised fix: a writer can run after the
     * last READ_ONCE and before the caller publishes the resulting PPE entry. */
    setup(true); f.mutation = AFTER_FINAL_OBSERVATION;
    int ret = fill();
    /* The old callback has no final READ_ONCE hook; mutate after return there.
     * In the patched callback the writer runs before ctx->dev is consumed. */
    if (!f.fired) f.msta.deflink_id = 2;
    printf("boundary writer: %s\n", f.fired ? "after final read, before return" : "after callback return");
    check("subsequent mutation remains outside callback guarantee",
          ret == 0 && consistent(1) && f.msta.deflink_id == 2);
    printf("forward path: %u checks, %u failed\n", checked, failed);
    return failed ? 1 : 0;
}
'''


if __name__ == '__main__':
    source = (Path(sys.argv[1]) / 'mt7996/main.c').read_text()
    callback = function(source, 'mt7996_net_fill_forward_path')
    with tempfile.TemporaryDirectory(prefix='mt7996-forward-path-') as directory:
        work = Path(directory)
        c = work / 'check.c'
        c.write_text(STUBS + callback + CASES)
        failed = False
        for mode, flags in [('npu', []), ('wed', ['-DCONFIG_NET_MEDIATEK_SOC_WED'])]:
            binary = work / mode
            subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-parameter', '-Wno-unused-function',
                            '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                            *flags, str(c), '-o', str(binary)], check=True)
            print(f'configuration: {mode}', flush=True)
            failed |= subprocess.run([str(binary)]).returncode != 0
        raise SystemExit(int(failed))
