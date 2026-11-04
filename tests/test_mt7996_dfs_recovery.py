#!/usr/bin/env python3
"""Extract real radar/DFS resume C paths; kernel locking/firmware are fixtures."""
import argparse, pathlib, runpy, subprocess, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('source',type=pathlib.Path);p.add_argument('mac80211',type=pathlib.Path);p.add_argument('--baseline',action='store_true');a=p.parse_args()
extract=runpy.run_path(str(ROOT/'tests/test_airoha_ppe_ownership.py'))['function']
cut=runpy.run_path(str(ROOT/'tests/test_mt76_ps_wake.py'))['extract']
mcu=(a.source/'mt7996/mcu.c').read_text();main=(a.source/'mt7996/main.c').read_text()
header=a.source/'mt7996/mcu.h'
h=header.read_text();wire=cut(h,'struct mt7996_mcu_rxd {','struct mt7996_mcu_uni_event')+cut(h,'struct mt7996_mcu_rdd_report {','struct mt7996_mcu_background_chain_ctrl')
shim=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
typedef uint8_t u8;typedef uint16_t __le16;typedef uint32_t __le32;
#define __packed __attribute__((packed))
#define offsetofend(t,m) (offsetof(t,m)+sizeof(((t *)0)->m))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define READ_ONCE(x) (x)
#define cpu_to_le16(x) (x)
#define MT_RDD_IDX_BAND1 1
#define MT_RDD_IDX_BAND2 2
#define MT_RDD_IDX_BACKGROUND 3
#define MT_BAND1 1
#define MT_BAND2 2
#define GFP_ATOMIC 0
#define IEEE80211_CHANCTX_REPLACES_OTHER 1
#define UNI_BAND_CONFIG_MAC_ENABLE_CTRL 9
#define MCU_WM_UNI_CMD(x) 1
#define UNI_CHANNEL_SWITCH 1
#define UNI_CHANNEL_RX_PATH 2
#define MT7996_WATCHDOG_TIME 1
#define MT_DFS_STATE_UNKNOWN 0
#define MT_DFS_STATE_DISABLED 1
#define MT_DFS_STATE_CAC 2
#define MT_DFS_STATE_ACTIVE 3
struct mt76_chanctx { int unused; };
struct ieee80211_chanctx_conf { struct mt76_chanctx drv_priv[1]; };
struct ieee80211_chanctx { int replace_state; bool radar_detected;struct ieee80211_chanctx_conf conf; };
struct ieee80211_hw { void *wiphy; };
struct mt76_phy { struct ieee80211_hw *hw;void *priv;struct mt76_chanctx *chanctx;bool offchannel;int dfs_state,mac_work,band_idx; };
struct mt7996_phy { struct mt76_phy *mt76;struct mt7996_dev *dev;bool rdd_tx_paused;int noise; };
struct mt7996_dev { struct {struct mt76_phy phy;struct mt76_phy *phys[3];void *dev;} mt76;struct mt7996_phy *rdd2_phy;int rdd2_chandef;unsigned hw_pattern; };
struct sk_buff { size_t len;void *data; };
static struct ieee80211_chanctx contexts[3];static int depth,radar_calls,background,invalid;
static int stage_error,dfs_error,resume_error,mcus,updates,scheduled,dfs_next;
'''
shim+=extract((a.mac80211/'util.c').read_text(),'ieee80211_radar_mark_chan_ctx_iterator')
shim+=r'''
static void ieee80211_iter_chan_contexts_atomic(struct ieee80211_hw *hw,void (*fn)(struct ieee80211_hw *,struct ieee80211_chanctx_conf *,void *),void *data) {
 depth++;for(int i=0;i<3;i++)fn(hw,&contexts[i].conf,data);depth--;
}
static void ieee80211_radar_detected(struct ieee80211_hw *hw,struct ieee80211_chanctx_conf *c) {
 if(c)assert(depth>0);radar_calls++;ieee80211_iter_chan_contexts_atomic(hw,ieee80211_radar_mark_chan_ctx_iterator,c);
}
static void cfg80211_background_radar_event(void *w,int *c,int flags) { background++; }
#define dev_err(...) (invalid++)
static void mt7996_mac_update_beacons(struct mt7996_phy *p) { updates++; }
static int mt7996_mcu_set_chan_info(struct mt7996_phy *p,int cmd) { return stage_error==cmd?-5:0; }
static int mt7996_mcu_set_txpower_sku(struct mt7996_phy *p) { return stage_error==3?-6:0; }
static int mt7996_dfs_init_radar_detector(struct mt7996_phy *p) { if(!dfs_error)p->mt76->dfs_state=dfs_next;return dfs_error; }
static void mt7996_mac_cca_stats_reset(struct mt7996_phy *p) {}
static void mt7996_mac_reset_counters(struct mt7996_phy *p) {}
static void ieee80211_queue_delayed_work(struct ieee80211_hw *hw,int *w,int delay) {scheduled++;}
static int mt76_mcu_send_msg(void *dev,int cmd,void *msg,size_t len,bool wait) {mcus++;return resume_error;}
'''
funcs=cut(mcu,'int mt7996_mcu_rdd_resume_tx(', '\nint mt7996_mcu_rdd_cmd(')
if 'mt7996_radar_detected_iter(' in mcu:funcs+=extract(mcu,'mt7996_radar_detected_iter')
funcs+=extract(mcu,'mt7996_mcu_rx_radar_detected')
funcs+=cut(main,'int mt7996_set_channel(', '\nstatic int mt7996_set_key(')
cases=r'''
static int checks,failed;
#define CHECK(x) do {checks++;if(!(x)){failed++;fprintf(stderr,"FAIL: %s\n",#x);}}while(0)
static void reset(struct mt7996_dev *d,struct mt7996_phy p[3],struct mt76_phy m[3],struct ieee80211_hw *hw) {
 memset(d,0,sizeof(*d));memset(p,0,sizeof(*p)*3);memset(m,0,sizeof(*m)*3);memset(contexts,0,sizeof(contexts));
 for(int i=0;i<3;i++){m[i].band_idx=i;m[i].hw=hw;m[i].priv=&p[i];m[i].chanctx=contexts[i].conf.drv_priv;p[i].mt76=&m[i];p[i].dev=d;d->mt76.phys[i]=&m[i];}
 depth=radar_calls=background=invalid=stage_error=dfs_error=resume_error=mcus=updates=scheduled=0;dfs_next=MT_DFS_STATE_DISABLED;
}
static void report(struct mt7996_dev *d,int idx,size_t len) {
 struct mt7996_mcu_rdd_report r={.rdd_idx=idx};struct sk_buff s={.len=len,.data=&r};mt7996_mcu_rx_radar_detected(d,&s);
}
int main(void) {
 struct mt7996_dev d;struct mt7996_phy p[3];struct mt76_phy m[3];struct ieee80211_hw hw={};size_t len=offsetofend(struct mt7996_mcu_rdd_report,rdd_idx);
 reset(&d,p,m,&hw);report(&d,MT_RDD_IDX_BAND1,len);
 CHECK(!contexts[0].radar_detected&&contexts[1].radar_detected&&!contexts[2].radar_detected);
 CHECK(p[1].rdd_tx_paused&&!p[0].rdd_tx_paused&&!p[2].rdd_tx_paused);
 CHECK(d.hw_pattern==1&&radar_calls==1);
 reset(&d,p,m,&hw);report(&d,MT_RDD_IDX_BAND2,len);
 CHECK(!contexts[0].radar_detected&&!contexts[1].radar_detected&&contexts[2].radar_detected);
 reset(&d,p,m,&hw);m[1].chanctx=NULL;report(&d,MT_RDD_IDX_BAND1,len);CHECK(radar_calls==0&&p[1].rdd_tx_paused);
 reset(&d,p,m,&hw);contexts[1].replace_state=IEEE80211_CHANCTX_REPLACES_OTHER;report(&d,MT_RDD_IDX_BAND1,len);CHECK(!contexts[0].radar_detected&&!contexts[1].radar_detected&&!contexts[2].radar_detected);
 reset(&d,p,m,&hw);d.rdd2_phy=&p[1];report(&d,MT_RDD_IDX_BACKGROUND,len);CHECK(background==1&&radar_calls==0&&!p[1].rdd_tx_paused);
 reset(&d,p,m,&hw);report(&d,MT_RDD_IDX_BACKGROUND,len);CHECK(invalid==1&&radar_calls==0&&d.hw_pattern==0);
 reset(&d,p,m,&hw);d.mt76.phys[1]=NULL;report(&d,MT_RDD_IDX_BAND1,len);CHECK(invalid==1&&radar_calls==0);
 reset(&d,p,m,&hw);report(&d,99,len);CHECK(invalid==1&&radar_calls==0);
#ifndef BASELINE
 reset(&d,p,m,&hw);report(&d,MT_RDD_IDX_BAND1,len-1);CHECK(radar_calls==0&&d.hw_pattern==0&&!p[1].rdd_tx_paused);
#endif
 reset(&d,p,m,&hw);p[1].rdd_tx_paused=true;CHECK(mt7996_set_channel(&m[1])==0&&mcus==1&&!p[1].rdd_tx_paused);
 reset(&d,p,m,&hw);p[1].rdd_tx_paused=true;dfs_next=MT_DFS_STATE_ACTIVE;CHECK(mt7996_set_channel(&m[1])==0&&mcus==1&&!p[1].rdd_tx_paused);
 reset(&d,p,m,&hw);p[1].rdd_tx_paused=true;dfs_next=MT_DFS_STATE_CAC;CHECK(mt7996_set_channel(&m[1])==0&&mcus==0&&p[1].rdd_tx_paused);
 reset(&d,p,m,&hw);p[1].rdd_tx_paused=true;dfs_next=MT_DFS_STATE_UNKNOWN;CHECK(mt7996_set_channel(&m[1])==0&&mcus==0&&p[1].rdd_tx_paused);
 reset(&d,p,m,&hw);p[1].rdd_tx_paused=true;m[1].offchannel=true;CHECK(mt7996_set_channel(&m[1])==0&&mcus==0&&p[1].rdd_tx_paused);
 for(int i=1;i<=3;i++){reset(&d,p,m,&hw);p[1].rdd_tx_paused=true;stage_error=i;CHECK(mt7996_set_channel(&m[1])<0&&mcus==0&&p[1].rdd_tx_paused&&scheduled==1);}
 reset(&d,p,m,&hw);p[1].rdd_tx_paused=true;dfs_error=-7;CHECK(mt7996_set_channel(&m[1])==-7&&mcus==0&&p[1].rdd_tx_paused&&updates==0);
 reset(&d,p,m,&hw);p[1].rdd_tx_paused=true;resume_error=-8;CHECK(mt7996_set_channel(&m[1])==-8&&mcus==1&&p[1].rdd_tx_paused&&updates==0);
 reset(&d,p,m,&hw);CHECK(mt7996_set_channel(&m[1])==0&&mcus==0&&updates==1&&scheduled==1);
 printf("DFS recovery: %d checks, %d failed; actual C paths, ASan/UBSan; firmware/RCU scheduling not emulated\n",checks,failed);
 return failed?1:0;
}
'''
with tempfile.TemporaryDirectory(prefix='mt7996-dfs-') as t:
 c=pathlib.Path(t)/'check.c';exe=c.with_suffix('');c.write_text(shim+wire+funcs+cases)
 cmd=['cc','-std=gnu11','-O1','-g','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all']
 if a.baseline:cmd+=['-DBASELINE']
 subprocess.run(cmd+[str(c),'-o',str(exe)],check=True)
 raise SystemExit(subprocess.run([str(exe)]).returncode)
