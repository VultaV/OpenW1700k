#!/usr/bin/env python3
"""Extract four patched control paths and run host C regressions, not radio tests."""
import pathlib,re,runpy,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parent
extract=runpy.run_path(str(ROOT/'test_airoha_ppe_ownership.py'))['function']
src=pathlib.Path(sys.argv[1])
mac=(src/'mt7996/mac.c').read_text();main=(src/'mt7996/main.c').read_text()
start=mac.index('\tif ((is_8023 || ieee80211_is_data_qos')
end=mac.index('\n\tif (link_id != wcid->link_id',start)
tx=mac[start:end]
start=mac.index('\tif (vif && ieee80211_vif_is_mld(vif) &&')
end=mac.index(';',mac.index('txwi[5] |=',start))+1
mgmt=mac[start:end]
sync=extract(main,'mt7996_mac_sta_links_sync')
gate=re.search(r'updated = sta->mlo[^;]+;',sync)[0]
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
#define WLAN_CIPHER_SUITE_CCMP 1
struct mt76_dev {};
struct ieee80211_key_conf { int cipher; u8 pn[6]; };
struct ieee80211_key_seq { struct { u8 pn[6]; } ccmp; };
static void ieee80211_get_key_rx_seq(struct ieee80211_key_conf *key,int tid,struct ieee80211_key_seq *seq) { memcpy(seq->ccmp.pn,key->pn,6); }
#define RX_FLAG_DECRYPTED 1
#define RX_FLAG_ONLY_MONITOR 2
#define RX_FLAG_8023 4
#define RX_FLAG_IV_STRIPPED 8
#define RX_FLAG_PN_VALIDATED 16
#define IEEE80211_NUM_TIDS 16
#define IEEE80211_QOS_CTL_TID_MASK 15
#define BUILD_BUG_ON(x) do { _Static_assert(!(x),"size"); } while(0)
struct mt76_wcid { bool rx_check_pn,sta; u8 rx_key_pn[17][6]; struct mt76_wcid *def_wcid; u8 link_id; };
struct mt76_rx_status { unsigned flag; struct mt76_wcid *wcid; unsigned qos_ctl; u8 iv[6]; };
struct ieee80211_hdr { unsigned frame_control,seq_ctrl; };
struct sk_buff { union { struct mt76_rx_status status; unsigned char cb[128]; }; struct ieee80211_hdr hdr; unsigned priority,protocol; };
static struct ieee80211_hdr *mt76_skb_get_hdr(struct sk_buff *s) { return &s->hdr; }
#define ieee80211_is_frag(h) false
#define ieee80211_is_first_frag(s) true
#define ieee80211_is_mgmt(f) (((f)&0xc)==0)
#define ieee80211_has_tods(f) ((f)&0x100)
#define IEEE80211_LINK_UNSPECIFIED 255
#define ETH_P_PAE 0x888e
#define MT_TXD5_FL 0x100
#define cpu_to_be16(x) (x)
#define cpu_to_le32(x) (x)
#define IEEE80211_TX_CTRL_MLO_LINK 0xff
#define u32_get_bits(v,m) ((v)&(m))
#define READ_ONCE(v) (v)
#define likely(v) (v)
#define unlikely(v) (v)
#define ieee80211_is_data_qos(f) ((f)==0x88)
struct ieee80211_sta { bool mlo; };
struct mt7996_sta { u8 deflink_id,seclink_id; };
struct mt7996_dev { struct { struct mt76_wcid global_wcid; } mt76; };
struct ieee80211_tx_info { struct { unsigned flags; } control; };
struct mt76_tx_info { struct sk_buff *skb; };
struct vif { bool mld; };
#define ieee80211_vif_is_mld(v) ((v)->mld)
static bool mt7996_mlo_best_link=true;
static u8 mt7996_tx_awake_link(struct ieee80211_sta *s,u8 link) { return link; }
'''
cut=runpy.run_path(str(ROOT/'test_mt76_ps_wake.py'))['extract']
primary=cut((src/'mt76.h').read_text(),'static inline struct mt76_wcid *\nmt76_wcid_primary','static inline struct ieee80211_sta *')
header=(src/'mt76.h').read_text();core=(src/'mac80211.c').read_text()
key_setup=cut(core,'void mt76_wcid_key_setup(', 'EXPORT_SYMBOL(mt76_wcid_key_setup)')
if 'mt76_wcid_key_link_setup' in header:
 link_setup=cut(header,'static inline void\nmt76_wcid_key_link_setup','void mt76_wcid_key_setup')
else:
 # Baseline callers seed every link instead of just enabling the check.
 link_setup='static void mt76_wcid_key_link_setup(struct mt76_wcid *w,struct ieee80211_key_conf *k) { mt76_wcid_key_setup(0,w,k); }'
 key_setup,link_setup=link_setup,key_setup
body=prefix+'\n'+primary+'\n'+link_setup+'\n'+key_setup+'\n'+extract(core,'mt76_check_ccmp_pn')
body+='''
static u8 tx_link(bool encap,bool mlo,u8 own,unsigned priority) {
 struct mt7996_dev d={}; struct mt7996_dev *dev=&d;
 struct mt76_wcid wc={.link_id=own},*wcid=&wc;
 struct ieee80211_sta st={.mlo=mlo},*sta=&st;
 struct mt7996_sta ms={.deflink_id=2,.seclink_id=1},*msta=&ms;
 struct sk_buff skb={.priority=priority}; struct mt76_tx_info ti={.skb=&skb},*tx_info=&ti;
 struct ieee80211_tx_info inf={},*info=&inf;
 struct ieee80211_hdr h={.frame_control=0x88},*hdr=&h;
 bool is_8023=encap; u8 link_id;
'''+tx+r'''
 return link_id;
}
static bool force_link(bool mld,bool peer,unsigned fc) {
 struct vif vi={.mld=mld},*vif=&vi;
 struct mt76_wcid wc={.sta=peer},*wcid=&wc;
 struct sk_buff s={},*skb=&s; bool multicast=false; unsigned txwi[8]={};
'''+mgmt+r'''
 return !!(txwi[5]&MT_TXD5_FL);
}
static unsigned mld_updates(bool mlo,unsigned joined,unsigned links,unsigned updated) {
 struct ieee80211_sta s={.mlo=mlo},*sta=&s;
'''+gate+r'''
 return updated;
}
static unsigned frame(struct mt76_wcid *wc,int tid,int pn) {
 struct sk_buff skb={};struct mt76_rx_status *s=(void *)skb.cb;
 s->wcid=wc;s->qos_ctl=tid;s->iv[5]=pn;s->flag=RX_FLAG_8023|RX_FLAG_DECRYPTED|RX_FLAG_IV_STRIPPED;
 mt76_check_ccmp_pn(&skb);return s->flag;
}
#define CHECK(x) do { checks++; if (!(x)) { failed++; fprintf(stderr,"FAIL: %s\n",#x); } } while(0)
int main(void) {
 int checks=0,failed=0;
 assert(tx_link(true,false,2,0)==2);
 assert(tx_link(true,true,0,0)==2);
 mt7996_mlo_best_link=false;assert(tx_link(true,true,0,1)==1);
 assert(force_link(true,true,0));assert(!force_link(false,true,0));assert(!force_link(true,true,0x88));
 assert(mld_updates(true,0,4,0)==0);
 assert(mld_updates(true,2,6,2)==4);assert(mld_updates(false,2,6,2)==0);
 struct mt76_wcid peer={},a={.rx_check_pn=true,.def_wcid=&peer},b={.rx_check_pn=true,.def_wcid=&peer};
 assert(frame(&a,0,10)&RX_FLAG_PN_VALIDATED);
 assert(frame(&b,0,10)&RX_FLAG_ONLY_MONITOR);
 assert(frame(&b,0,11)&RX_FLAG_PN_VALIDATED);
 assert(frame(&a,0,9)&RX_FLAG_ONLY_MONITOR);
 assert(frame(&a,1,1)&RX_FLAG_PN_VALIDATED);
 struct mt76_wcid solo={.rx_check_pn=true};
 assert(frame(&solo,0,2)&RX_FLAG_PN_VALIDATED);assert(frame(&solo,0,2)&RX_FLAG_ONLY_MONITOR);
 struct ieee80211_key_conf key={.cipher=WLAN_CIPHER_SUITE_CCMP,.pn={0,0,0,0,0,5}};
 mt76_wcid_key_setup(0,&peer,&key);
 assert(peer.rx_key_pn[0][5]==5&&peer.rx_key_pn[16][5]==5);
 assert(frame(&a,0,20)&RX_FLAG_PN_VALIDATED);
 mt76_wcid_key_link_setup(&b,&key);
 assert(peer.rx_key_pn[0][5]==20&&(frame(&b,0,19)&RX_FLAG_ONLY_MONITOR));
 mt76_wcid_key_setup(0,&peer,&key);
 assert(frame(&b,0,6)&RX_FLAG_PN_VALIDATED);
 printf("MLO backports: %d checks, %d failed\n",checks,failed);
 return failed ? 1 : 0;
}
'''
a=body.index('int main(void)');body=body[:a]+body[a:].replace('assert(', 'CHECK(')
with tempfile.TemporaryDirectory(prefix='mt7996-r63-') as t:
 p=pathlib.Path(t);(p/'test.c').write_text(body)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
