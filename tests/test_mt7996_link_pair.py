#!/usr/bin/env python3
"""Run actual link-pair/TLV functions with host fixtures and ASan/UBSan.

Usage: test_mt7996_link_pair.py /path/to/prepared/mt76
This checks command contents and selector ordering, not MCU execution or RCU.
"""
from pathlib import Path
import re, subprocess, sys, tempfile

def function(source, name):
    match = re.search(r'^(?:static )?(?:void|u8)\s+' + name + r'\(', source, re.M)
    assert match, name
    start = source.index('{', match.start()); end = start + 1; depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}'); end += 1
    return source[match.start():end] + '\n'

src = Path(sys.argv[1]); main = (src/'mt7996/main.c').read_text()
mcu = (src/'mt7996/mcu.c').read_text()
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
#define BIT(i) (1UL << (i))
#define ARRAY_SIZE(v) (sizeof(v)/sizeof(*(v)))
#define IEEE80211_LINK_UNSPECIFIED 255
#define IEEE80211_MLD_MAX_NUM_LINKS 16
#define ETH_ALEN 6
#define STA_REC_MLD 1
#define cpu_to_le16(v) (v)
#define hweight16(v) __builtin_popcount(v)
#define for_each_set_bit(i,p,max) for ((i)=0;(i)<(max);(i)++) if (*(p)&BIT(i))
#define mt76_dereference(p,d) (p)
struct mt76_wcid { unsigned idx; bool link_valid; };
struct mt7996_sta_link { struct mt76_wcid wcid; };
struct mt7996_sta { u8 deflink_id, seclink_id; struct mt7996_sta_link *link[16]; };
struct ieee80211_sta { void *drv_priv; u8 addr[6]; };
struct mt7996_dev { int mt76; };
struct ieee80211_vif { int unused; };
struct mt7996_vif_link { struct { unsigned idx; } mt76; };
struct mld_setup_link { unsigned wcid, bss_idx; };
struct sta_rec_mld_setup { u8 mld_addr[6]; unsigned setup_wcid, primary_id, seconed_id, link_num; struct mld_setup_link link_info[16]; };
struct tlv { int unused; };
struct sk_buff { struct sta_rec_mld_setup data; };
static unsigned links, txq_wcid;
static struct mt7996_vif_link viflinks[16];
static struct mt7996_sta_link *mt7996_sta_link_protected(struct mt7996_dev *d,struct mt7996_sta *s,unsigned i) { return i<16?s->link[i]:0; }
static unsigned long mt7996_mac_sta_links(struct mt7996_dev *d,struct ieee80211_vif *v,struct ieee80211_sta *s) { return links; }
static struct mt7996_vif_link *mt7996_vif_link(struct mt7996_dev *d,struct ieee80211_vif *v,unsigned i) { return &viflinks[i]; }
static struct tlv *mt76_connac_mcu_add_tlv(struct sk_buff *s,unsigned tag,unsigned size) { assert(size<=sizeof(s->data)+16*sizeof(struct mld_setup_link)); return (void *)&s->data; }
static void mt7996_sta_init_txq_wcid(struct ieee80211_sta *s,int i) { txq_wcid=i; }
'''
code += function(main,'mt7996_sta_seclink_get')
code += function(main,'mt7996_sta_deflink_set')
code += function(main,'mt7996_sta_deflink_release')
code += function(mcu,'mt7996_mcu_sta_mld_setup_tlv')
code += r'''
int main(void) {
 unsigned cases=0;
 struct mt7996_dev d={}; struct ieee80211_vif v={};
 struct mt7996_sta ms={}; struct ieee80211_sta s={.drv_priv=&ms,.addr={1,2,3,4,5,6}};
 struct mt7996_sta_link slots[3]={};
 for (unsigned mask=1;mask<8;mask++) for (unsigned p=0;p<3;p++) if(mask&BIT(p)) {
  for (unsigned sec=0;sec<3;sec++) {
   memset(&ms,0,sizeof(ms)); ms.deflink_id=p;ms.seclink_id=sec;
   for(unsigned i=0;i<3;i++) { slots[i].wcid.idx=10+i;slots[i].wcid.link_valid=!!(mask&BIT(i));ms.link[i]=&slots[i];viflinks[i].mt76.idx=20+i; }
   unsigned expected=p;
   if(sec!=p && (mask&BIT(sec))) expected=sec;
   else for(unsigned i=0;i<3;i++) if(i!=p && (mask&BIT(i))) {expected=i;break;}
   assert(mt7996_sta_seclink_get(&d,&ms)==expected);
   struct sk_buff skb={}; links=mask;
   mt7996_mcu_sta_mld_setup_tlv(&d,&skb,&v,&s);
   assert(skb.data.primary_id==10+p && skb.data.setup_wcid==10+p);
   assert(skb.data.seconed_id==10+expected && skb.data.link_num==(unsigned)__builtin_popcount(mask));
   assert(!memcmp(skb.data.mld_addr,s.addr,6));
   unsigned n=0;for(unsigned i=0;i<3;i++) if(mask&BIT(i)) {assert(skb.data.link_info[n].wcid==10+i && skb.data.link_info[n].bss_idx==20+i);n++;}
   /* A negotiated, valid secondary may be absent from this setup command. */
   links=BIT(p);memset(&skb,0,sizeof(skb));mt7996_mcu_sta_mld_setup_tlv(&d,&skb,&v,&s);
   assert(skb.data.seconed_id==10+p && skb.data.link_num==1);cases++;
  }
 }
 memset(&ms,0,sizeof(ms));ms.deflink_id=ms.seclink_id=255;
 mt7996_sta_deflink_set(&s,1,11);assert(ms.deflink_id==1 && ms.seclink_id==1 && txq_wcid==11);
 slots[1].wcid.link_valid=slots[2].wcid.link_valid=true;ms.link[1]=&slots[1];ms.link[2]=&slots[2];
 mt7996_sta_deflink_release(&d,&s,1);assert(ms.deflink_id==2 && ms.seclink_id==2 && txq_wcid==12);
 ms.deflink_id=255;assert(mt7996_sta_seclink_get(&d,&ms)==255);
 printf("PASS: %u link-pair/TLV fixtures plus initial-primary and removal fallback, ASan/UBSan\n",cases);
}
'''
with tempfile.TemporaryDirectory(prefix='mt7996-pair-') as tmp:
    p=Path(tmp);(p/'check.c').write_text(code)
    subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p/'check.c'),'-o',str(p/'check')],check=True)
    subprocess.run([str(p/'check')],check=True)
