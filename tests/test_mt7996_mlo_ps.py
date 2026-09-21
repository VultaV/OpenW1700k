#!/usr/bin/env python3
"""Compile actual two-link MLO queue/callback functions with the existing PS/AQL harness.
Firmware, RCU/concurrency, allocation are shims; this is host-path
validation, not proof of hardware throughput or firmware PS buffer safety.
"""
from pathlib import Path
import runpy
import subprocess
import tempfile

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-dir', type=Path, required=True, help='Patched mt76 source tree')
parser.add_argument('--mac80211-dir', type=Path, required=True, help='mac80211 source containing tx.c and sta_info.c')
args = parser.parse_args()
old = runpy.run_path(str(Path(__file__).with_name('test_mt76_ps_wake.py')))
extract = old['extract']
source = (args.source_dir / 'tx.c').read_text()
main = (args.source_dir / 'mt7996/main.c').read_text()
mac = args.mac80211_dir
aql = extract((mac / 'tx.c').read_text(), 'u32 ieee80211_txq_aql_pending(', '\nEXPORT_SYMBOL(ieee80211_txq_aql_pending)')
aql += extract((mac / 'sta_info.c').read_text(), 'void ieee80211_sta_update_pending_airtime(', '\nstatic struct ieee80211_sta_rx_stats *')
functions = ''.join(extract(source, start, end) for start, end in [
    ('static int\nmt76_txq_get_qid(', '\nvoid\nmt76_tx_check_agg_ssn('),
    ('void\nmt76_tx_status_lock(', '\nvoid\nmt76_tx_status_skb_done('),
    ('static void\nmt76_tx_check_non_aql(', '\nstatic int\n__mt76_tx_queue_skb('),
    ('static bool\nmt76_txq_stopped(', '\nvoid mt76_txq_schedule('),
])
callback = extract(main, 'static bool mlo_ps_gate_fix = true;', '\nint mt7996_run(')
assert 'mlo_ps_gate_fix, bool, 0600);' in callback
stubs = old['STUBS'].replace('unsigned char addr[6];', 'unsigned char addr[6]; bool mlo; u16 valid_links; void *drv_priv;')
stubs = stubs.replace('int phy_idx, tx_info;', 'int phy_idx, tx_info; bool link_valid; u8 link_id;')
stubs = stubs.replace('unsigned int drv_flags; };', 'unsigned int drv_flags; bool (*txq_ps)(struct mt76_wcid *); };')
shims = r'''
#define BIT(n) (1ul << (n))
#define IEEE80211_MLD_MAX_NUM_LINKS 16
#define module_param_named(...)
#define MODULE_PARM_DESC(...)
struct mt7996_sta_link { struct mt76_wcid wcid; };
struct mt7996_sta {
    struct mt7996_sta_link deflink, *link[16];
    u8 deflink_id, seclink_id;
};
static struct mt7996_sta_link *mt7996_sta_link(struct mt7996_sta *s, u8 id) {
    return id < 16 ? s->link[id] : NULL;
}
'''
cases = old['CASES'].replace('int main(void)', 'static int old_checks(void)')
new = r'''
static struct mt7996_sta mlo;
static struct mt7996_sta_link secondary;
static struct mt76_wcid *primary;
static void setup(void) {
    reset(); memset(&mlo, 0, sizeof(mlo)); memset(&secondary, 0, sizeof(secondary));
    mlo_ps_gate_fix = true;
    mlo.deflink.wcid = f.wcids[0]; primary = &mlo.deflink.wcid;
    secondary.wcid = f.wcids[1]; secondary.wcid.def_wcid = primary;
    primary->phy_idx = primary->link_id = 2; primary->link_valid = true;
    secondary.wcid.phy_idx = secondary.wcid.link_id = 1;
    secondary.wcid.link_valid = true;
    mlo.deflink_id = 2; mlo.seclink_id = 1;
    mlo.link[2] = &mlo.deflink; mlo.link[1] = &secondary;
    f.peer.sta.mlo = true; f.peer.sta.valid_links = 6; f.peer.sta.drv_priv = &mlo;
    f.dev.wcids[0] = primary; f.dev.wcids[1] = &secondary.wcid;
    f.drv.txq_ps = mt7996_txq_ps;
}
static int burst(void) {
    return mt76_txq_send_burst(&f.phys[2], &f.queues[2][0], &f.mtxq[3], primary);
}
int main(void) {
    if (old_checks()) return 1;
    setup(); check("default fixes shared queue", !mt7996_txq_ps(primary) && burst() == 10);
    check("raw link PS flags preserved", primary->flags == 1 && secondary.wcid.flags == 0);
    setup(); mlo_ps_gate_fix = false;
    check("disable restores one-frame gating", mt7996_txq_ps(primary) && burst() == 1);
    const int ids[] = {0, 1, 2, 15};
    for (unsigned i = 0; i < ARRAY_SIZE(ids); i++) for (unsigned j = 0; j < ARRAY_SIZE(ids); j++) {
        if (i == j) continue;
        for (int p = 0; p < 2; p++) for (int s = 0; s < 2; s++) {
            setup(); memset(mlo.link, 0, sizeof(mlo.link));
            primary->link_id = mlo.deflink_id = ids[i];
            secondary.wcid.link_id = mlo.seclink_id = ids[j];
            mlo.link[ids[i]] = &mlo.deflink; mlo.link[ids[j]] = &secondary;
            f.peer.sta.valid_links = BIT(ids[i]) | BIT(ids[j]);
            primary->flags = p; secondary.wcid.flags = s;
            check("pair order and all PS combinations", mt7996_txq_ps(primary) == (p && s));
        }
    }
    setup(); f.txq[3].scheduled = true;
    check("actual schedule loop drains full backlog", mt76_txq_schedule_list(&f.phys[2], 0) == 10);
    setup(); primary->non_aql_packets = MT_MAX_NON_AQL_PKT;
    check("non-AQL cap retained", burst() == 0 && f.txq[3].backlog == 10);
    setup(); secondary.wcid.flags = 1; f.peer.airtime[0].aql_tx_pending = 100;
    check("both asleep pending AQL blocks burst", burst() == 0);
    setup(); secondary.wcid.flags = 1;
    check("both asleep permits one frame without pending AQL", burst() == 1);
    for (int c = 0; c < 12; c++) {
        setup();
        switch (c) {
        case 0: primary->sta = NULL; break;
        case 1: primary->link_valid = false; break;
        case 2: f.peer.sta.mlo = false; break;
        case 3: f.peer.sta.valid_links = 4; break;
        case 4: f.peer.sta.valid_links = 7; break;
        case 5: mlo.deflink_id = 16; break;
        case 6: mlo.seclink_id = 255; break;
        case 7: mlo.seclink_id = mlo.deflink_id; break;
        case 8: mlo.link[1] = NULL; break;
        case 9: secondary.wcid.link_valid = false; break;
        case 10: secondary.wcid.link_id = 0; break;
        case 11: mlo.link[2] = NULL; break;
        }
        check("incomplete or unsupported topology retains original PS gate", mt7996_txq_ps(primary));
    }
    setup(); struct mt7996_sta_link replacement = mlo.deflink;
    mlo.link[2] = &replacement;
    check("old WCID cannot use replacement link", mt7996_txq_ps(primary));
    check("replacement primary need not be embedded deflink", !mt7996_txq_ps(&replacement.wcid));
    setup(); secondary.wcid.flags = 1;
    check("secondary WCID preserves own PS state", mt7996_txq_ps(&secondary.wcid));
    printf("combined: %d checks, %d failed\n", checked, failed);
    return failed ? 1 : 0;
}
'''
with tempfile.TemporaryDirectory(prefix='mt76-mlo-ps-') as temporary:
    work = Path(temporary)
    c = work / 'ps-gate.c'
    c.write_text(stubs + shims + callback + aql + old['STATUS_SHIM'] + functions + cases + new)
    cmd = ['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
           '-Wno-unused-parameter', '-Wno-sign-compare', '-fsanitize=address,undefined',
           '-fno-sanitize-recover=all', str(c), '-o', str(work / 'ps-gate')]
    subprocess.run(cmd, check=True)
    subprocess.run([str(work / 'ps-gate')], check=True)
