#!/usr/bin/env python3
"""Compile the real RC and queue-output callbacks with an inactive MLO default link."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
expect_errors = "--tx-errors" in sys.argv[2:]
expect_feedback = "--tx-feedback" in sys.argv[2:] or expect_errors
def function(name, file):
    s = (root / file).read_text()
    start = s.rfind('static void', 0, s.index(name + '('))
    brace = s.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (s[end] == '{') - (s[end] == '}')
        end += 1
    return s[start:end]

preamble = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <assert.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { u32 counter; } atomic_t;
static void atomic_inc(atomic_t *v) { v->counter++; }
static u32 atomic_read(const atomic_t *v) { return v->counter; }
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
struct list_head { int queued; };
struct mt7996_dev { struct { int sta_poll_lock; } mt76; struct list_head sta_rc_list; };
struct ieee80211_hw { struct mt7996_dev *dev; };
struct mt76_phy { struct ieee80211_hw *hw; void *priv; };
struct mt7996_phy { struct mt7996_dev *dev; };
struct mt76_vif_link { struct mt76_phy *phy; unsigned wmm_idx; };
struct mt7996_vif_link { struct mt76_vif_link mt76; };
struct mt7996_sta;
struct mt76_wcid {
    unsigned idx, link_id, link_valid, sta;
    unsigned long flags;
    struct { u64 tx_mode[17]; u32 tx_retries, tx_failed; } stats;
};
struct mt7996_sta_link {
    struct mt7996_sta *sta;
    struct mt76_wcid wcid;
    u32 changed;
    struct list_head rc_list;
    u32 txs_formats[4], txs_mpdu_flags[7];
    atomic_t txfree_status[4];
    atomic_t tx_prepared, tx_awake_checks, tx_awake_redirects;
};
struct mt7996_vif {
    struct mt7996_vif_link deflink;
    struct { struct mt76_vif_link *link[16]; } mt76;
};
struct ieee80211_vif { struct mt7996_vif drv_priv; };
struct mt7996_sta {
    struct mt7996_vif *vif;
    unsigned deflink_id, seclink_id;
    struct mt7996_sta_link *link[16];
};
struct ieee80211_link_sta { int unused; };
struct ieee80211_sta { void *drv_priv; unsigned char addr[6]; unsigned valid_links; bool mlo; };
struct seq_file { unsigned stations, links, last_link, feedback, formats, flags, status;
    struct { u64 reports; u32 retries, failed; u32 formats[4], flags[7], status[4]; } values[16]; };
#define BIT(x) (1U << (x))
#define GENMASK(h,l) (((~0U) << (l)) & ((~0U) >> (31-(h))))
#define FIELD_GET(mask,value) (((value) & (mask)) >> __builtin_ctz(mask))
#define MT_WCID_FLAG_PS 0
#define MT_FL_Q0_CTRL 0
#define MT_FL_Q3_CTRL 0
#define MT_PLE_AC_QEMPTY(a,i) 0
#define READ_ONCE(x) (x)
#define rcu_dereference(x) (x)
#define rcu_read_lock() ((void)0)
#define rcu_read_unlock() ((void)0)
#define spin_lock_bh(x) ((void)(x))
#define spin_unlock_bh(x) ((void)(x))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define for_each_sta_active_link(v,s,ls,id) \
    for ((id)=0; (id)<16; (id)++) \
        if (!(((s)->valid_links ? (s)->valid_links : 1) & BIT(id)) || \
            ((ls)=(void *)1)==NULL) {} else
#define test_bit(b,f) (!!(*(f) & (1UL << (b))))
#define mt76_rr(d,r) ((void)(d),~0U)
#define mt76_wr(d,r,v) ((void)(d),(void)(v))
#define mt76_get_field(d,r,m) ((void)(d),0U)
#define list_empty(l) (!(l)->queued)
#define list_add_tail(l,h) ((l)->queued=1,(h)->queued++)
static struct mt76_phy *mt76_vif_link_phy(struct mt76_vif_link *link) { return link->phy; }
static struct mt7996_phy *mt7996_vif_link_phy(struct mt7996_vif_link *link) { return link->mt76.phy ? link->mt76.phy->priv : NULL; }
static struct mt7996_dev *mt7996_hw_dev(struct ieee80211_hw *hw) { return hw->dev; }
static struct mt7996_sta_link *mt7996_sta_link(struct mt7996_sta *s, unsigned id) { return s->link[id]; }
static void seq_printf(struct seq_file *s, const char *fmt, ...) {
    if (!strncmp(fmt,"STA ",4)) s->stations++;
    va_list args;
    va_start(args, fmt);
    if (!strncmp(fmt,"\tlink:",6)) {
        s->links++; s->last_link=va_arg(args,unsigned);
    }
    if (!strncmp(fmt,"\t\ttxs_reports:",14)) {
        s->feedback++;
        s->values[s->last_link].reports=va_arg(args,unsigned long long);
        s->values[s->last_link].retries=va_arg(args,unsigned);
        s->values[s->last_link].failed=va_arg(args,unsigned);
    }
    if (strstr(fmt,"txs_formats:")) {
        s->formats++;
        for (unsigned i=0;i<4;i++) s->values[s->last_link].formats[i]=va_arg(args,unsigned);
    }
    if (strstr(fmt,"txs_mpdu_flags:")) {
        s->flags++;
        for (unsigned i=0;i<7;i++) s->values[s->last_link].flags[i]=va_arg(args,unsigned);
    }
    if (strstr(fmt,"txfree_status:")) {
        s->status++;
        for (unsigned i=0;i<4;i++) s->values[s->last_link].status[i]=va_arg(args,unsigned);
    }
    va_end(args);
}
'''
main = r'''
int main(void) {
    unsigned failures=0;
    CHECK_TX_ERRORS();
    for (unsigned mode=0;mode<4;mode++) {
        struct mt7996_dev dev={0};
        struct ieee80211_hw hw={.dev=&dev};
        struct mt7996_phy phy={.dev=&dev};
        struct mt76_phy mphy={.hw=&hw,.priv=&phy};
        struct ieee80211_vif vif={0};
        struct mt7996_sta msta={.vif=&vif.drv_priv,.deflink_id=mode?1:0,.seclink_id=mode?2:0};
        struct ieee80211_sta sta={.drv_priv=&msta,.valid_links=mode?6:0};
        struct mt7996_vif_link links[3]={0};
        struct mt7996_sta_link sl[3]={0};
        for (unsigned i=0;i<3;i++) {
            links[i].mt76.phy=&mphy;
            sl[i].sta=&msta;sl[i].wcid.link_id=i;sl[i].wcid.idx=7+i;
            sl[i].wcid.link_valid=mode!=0;sl[i].wcid.flags=i&1;
            sl[i].wcid.stats.tx_mode[0]=((u64)1<<34)+i;
            sl[i].wcid.stats.tx_mode[16]=10+i;
            sl[i].wcid.stats.tx_retries=i;
            sl[i].wcid.stats.tx_failed=UINT32_MAX-i;
            for (unsigned j=0;j<4;j++) {
                sl[i].txs_formats[j]=100*i+j;
                sl[i].txfree_status[j].counter=UINT32_MAX-10*i-j;
            }
            for (unsigned j=0;j<7;j++) sl[i].txs_mpdu_flags[j]=1000*i+j;
            msta.link[i]=&sl[i];
            vif.drv_priv.mt76.link[i]=&links[i].mt76;
        }
        if (!mode) vif.drv_priv.deflink.mt76.phy=&mphy;
        if (mode==2) vif.drv_priv.mt76.link[2]=NULL;
        if (mode==3) links[2].mt76.phy=NULL;
        unsigned id=mode?2:0;
        u32 changed=4;
        mt7996_link_rate_ctrl_update(&changed,&sl[id]);
        unsigned expected=mode<2?4:0;
        if (sl[id].changed!=expected || dev.sta_rc_list.queued!=(mode<2)) {
            fprintf(stderr,"RC mode %u: changed=%u queued=%d\n",mode,sl[id].changed,dev.sta_rc_list.queued); failures++;
        }
        struct seq_file out={0};
        mt7996_sta_hw_queue_read(&out,&sta);
        unsigned expected_links=mode==0||mode==2?1:2;
        if (out.stations!=1 || out.links!=expected_links || out.feedback!=(EXPECT_FEEDBACK ? expected_links : 0)) {
            fprintf(stderr,"debug mode %u: stations=%u links=%u\n",mode,out.stations,out.links);failures++;
        }
        for (unsigned i=0;i<3;i++) {
            bool present=mode ? i>0 && !(mode==2 && i==2) : i==0;
            if (EXPECT_ERRORS && present) {
                assert(out.formats==expected_links && out.flags==expected_links && out.status==expected_links);
                for (unsigned j=0;j<4;j++) {
                    assert(out.values[i].formats[j]==100*i+j);
                    assert(out.values[i].status[j]==UINT32_MAX-10*i-j);
                }
                for (unsigned j=0;j<7;j++) assert(out.values[i].flags[j]==1000*i+j);
            }
            if (EXPECT_FEEDBACK && present && (out.values[i].reports!=((u64)1<<34)+10+2*i ||
                out.values[i].retries!=i || out.values[i].failed!=UINT32_MAX-i)) {
                fprintf(stderr,"TX feedback mode %u link %u mismatch\n",mode,i); failures++;
            }
        }
    }
    printf("%u failing checks across SLO, MLO, removed-link and no-channel cases\n",failures);
    return failures!=0;
}
'''
trace_stub = r'''
/* This harness checks callback routing/counters, not trace output or firmware. */
static unsigned ps_trace_calls;
static void mt7996_trace_mlo_ps(struct mt7996_dev *dev, struct mt76_wcid *wcid,
                               char kind, u32 info) {
    assert(dev == NULL && wcid->sta && kind == 'F');
    assert(((info >> 28) & 3) == 1);
    ps_trace_calls++;
}
'''
error_cases = r'''
static void check_tx_errors(void) {
    struct mt76_wcid nonsta={0};
    mt7996_mac_txs_diag(&nonsta,UINT32_MAX);
    mt7996_mac_txfree_diag(NULL, &nonsta,UINT32_MAX);
    for (unsigned format=0;format<4;format++) {
        for (unsigned flags=0;flags<128;flags++) {
            struct mt7996_sta_link links[2]={0};
            links[1].wcid.sta=1;
            mt7996_mac_txs_diag(&links[1].wcid,(format<<23)|(flags<<16)|0xffff);
            for (unsigned f=0;f<4;f++) assert(links[1].txs_formats[f]==(f==format));
            for (unsigned bit=0;bit<7;bit++) assert(links[1].txs_mpdu_flags[bit]==(!format && !!(flags & (1U<<bit))));
            for (unsigned f=0;f<4;f++) assert(links[0].txs_formats[f]==0);
            for (unsigned status=0;status<4;status++) {
                mt7996_mac_txfree_diag(NULL, &links[1].wcid,(status<<28)|0xcfffffff);
                assert(links[1].txfree_status[status].counter==1);
                assert(links[0].txfree_status[status].counter==0);
            }
        }
    }
    assert(ps_trace_calls == 4 * 128);
    struct mt7996_sta_link wrap={0}; wrap.wcid.sta=1;
    wrap.txs_formats[0]=wrap.txs_mpdu_flags[0]=UINT32_MAX;
    wrap.txfree_status[3].counter=UINT32_MAX;
    mt7996_mac_txs_diag(&wrap.wcid,1U<<16);
    mt7996_mac_txfree_diag(NULL, &wrap.wcid,3U<<28);
    assert(wrap.txs_formats[0]==0 && wrap.txs_mpdu_flags[0]==0 && wrap.txfree_status[3].counter==0);
}
'''
with tempfile.TemporaryDirectory() as temp:
    p = Path(temp)
    diagnostics = '#define CHECK_TX_ERRORS() ((void)0)\n'
    if expect_errors:
        import re
        header = (root.parent/'mt76_connac3_mac.h').read_text()
        diagnostics = '\n'.join(re.search(r'^#define '+name+r'\s+.*$',header,re.M)[0] for name in ('MT_TXS0_TXS_FORMAT','MT_TXFREE_INFO_STAT'))+'\n'
        diagnostics += trace_stub + function('mt7996_mac_txfree_diag','mac.c')+'\n'+function('mt7996_mac_txs_diag','mac.c')+error_cases
        diagnostics += '\n#define CHECK_TX_ERRORS() check_tx_errors()\n'
    (p/'check.c').write_text('#define EXPECT_FEEDBACK %d\n#define EXPECT_ERRORS %d\n' % (expect_feedback,expect_errors) + preamble + diagnostics + function('mt7996_link_rate_ctrl_update','main.c') + '\n' + function('mt7996_sta_hw_queue_read','debugfs.c') + main)
    subprocess.run(['cc','-std=gnu11','-fsanitize=address,undefined','-g',str(p/'check.c'),'-o',str(p/'check')],check=True)
    sys.exit(subprocess.run([str(p/'check')]).returncode)
