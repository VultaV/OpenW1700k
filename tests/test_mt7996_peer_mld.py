#!/usr/bin/env python3
"""Compile actual PEER_MLD serializers/caller with host fixtures and ASan/UBSan.

Usage: test_mt7996_peer_mld.py <prepared mt76 directory>
The baseline reverses only the stable association-index override. MCU transport,
mac80211 link selection, locking and firmware execution remain fixtures.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def function(source, name):
    match = re.search(r'^(?:static )?(?:int|void|u32)\s+' + name + r'\(', source, re.M)
    assert match, name
    opening = source.index('{', match.start())
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end] + '\n'


def wire_struct(source, name):
    match = re.search(r'^struct ' + name + r'\s*\{.*?\}\s*__packed;', source, re.M | re.S)
    assert match, name
    return match[0] + '\n'


SHIM = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint16_t __le16;
typedef uint32_t __le32;
#define __packed __attribute__((packed))
#define ETH_ALEN 6
#define BIT(n) (1UL << (n))
#define U16_MAX UINT16_MAX
#define IEEE80211_MLD_MAX_NUM_LINKS 15
#define IEEE80211_LINK_UNSPECIFIED 15
#define IEEE80211_MAX_MPDU_LEN_VHT_11454 11454
#define IEEE80211_MAX_MPDU_LEN_HT_7935 7935
#define IEEE80211_MAX_MPDU_LEN_VHT_7991 7991
#define IEEE80211_VHT_CAP_MAX_MPDU_LENGTH_3895 0
#define IEEE80211_VHT_CAP_MAX_MPDU_LENGTH_7991 1
#define IEEE80211_VHT_CAP_MAX_MPDU_LENGTH_11454 2
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#define cpu_to_le16(v) ((u16)(v))
#define cpu_to_le32(v) ((u32)(v))
#else
#define cpu_to_le16(v) __builtin_bswap16((u16)(v))
#define cpu_to_le32(v) __builtin_bswap32((u32)(v))
#endif
#define le16_to_cpu(v) cpu_to_le16(v)
#define le32_to_cpu(v) cpu_to_le32(v)
#define min(a,b) ((a)<(b)?(a):(b))
#define for_each_set_bit(b,addr,n) \
 for ((b)=0;(b)<(n);(b)++) if (*(addr)&BIT(b))
#define hweight16(v) __builtin_popcount((u16)(v))
#define mutex_lock(p) (*(p)=1)
#define mutex_unlock(p) (*(p)=0)
#define MCU_WMWA_UNI_CMD(n) (0xc0000 | MCU_UNI_CMD_##n)
#define STA_REC_MLD 0x20
#define CONN_STATE_DISCONNECT 0
#define CONN_STATE_CONNECT 1
#define CONN_STATE_PORT_SECURE 2
struct tlv { __le16 tag,len; } __packed;
struct mt7996_sta_link { struct { u16 idx; } wcid; };
struct mt7996_vif_link { struct { u8 idx,band_idx; } mt76; };
struct ieee80211_link_sta { struct { u16 max_amsdu_len; } agg; };
struct mt7996_vif { int unused; };
struct mt7996_sta {
 struct mt7996_vif *vif; u16 ba_tx_mask,ba_rx_mask;
 u8 deflink_id,seclink_id,conn_state;
 u16 peer_mld_links,fw_mld_idx;
 struct mt7996_sta_link *link[15];
};
struct ieee80211_sta {
 void *drv_priv; u8 addr[ETH_ALEN]; u16 valid_links; bool mlo;
 struct ieee80211_link_sta *link[15];
};
struct ieee80211_vif { void *drv_priv; struct mt7996_vif_link *link[15]; };
struct mt7996_dev { struct { int mutex; } mt76; };
enum mt76_sta_event { MT76_STA_EVENT_ASSOC,MT76_STA_EVENT_AUTHORIZE,MT76_STA_EVENT_DISASSOC };
struct sk_buff { unsigned char data[256]; size_t len,capacity; };
static struct sk_buff command;
static unsigned char sent[256];
static int allocs,sends,alloc_fail,send_error,link_error,links_events,clear_events;
static size_t requested,sent_len;
static int sent_cmd,order,last_send_order,last_links_order,add_links_calls,add_links_error;
static unsigned long added_links;
static bool sent_wait;
static struct sk_buff *mt76_mcu_msg_alloc(void *d,void *data,int len) {
 (void)d;(void)data;allocs++;requested=len;
 if(alloc_fail)return NULL;
 assert(len>0&&(size_t)len<=sizeof(command.data));
 memset(&command,0,sizeof(command));command.capacity=len;return &command;
}
static void *skb_put_zero(struct sk_buff *s,size_t len) {
 assert(s->len+len<=s->capacity);void *p=s->data+s->len;
 memset(p,0,len);s->len+=len;return p;
}
static struct tlv *mt7996_mcu_add_uni_tlv(struct sk_buff *s,u16 tag,size_t len) {
 struct tlv *t=skb_put_zero(s,len);t->tag=cpu_to_le16(tag);t->len=cpu_to_le16(len);return t;
}
static struct tlv *mt76_connac_mcu_add_tlv(struct sk_buff *s,u16 tag,size_t len) {
 return mt7996_mcu_add_uni_tlv(s,tag,len);
}
static int mt76_mcu_skb_send_msg(void *d,struct sk_buff *s,int cmd,bool wait) {
 (void)d;sends++;last_send_order=++order;sent_len=s->len;sent_cmd=cmd;sent_wait=wait;
 memcpy(sent,s->data,sent_len);return send_error;
}
static u16 mt7996_mac_sta_links(struct mt7996_dev *d,struct ieee80211_vif *v,struct ieee80211_sta *s) {
 (void)d;(void)v;return s->valid_links;
}
static struct mt7996_sta_link *mt7996_sta_link_protected(struct mt7996_dev *d,struct mt7996_sta *s,unsigned id) {
 assert(d->mt76.mutex&&id<15&&s->link[id]);return s->link[id];
}
static struct mt7996_vif_link *mt7996_vif_link(struct mt7996_dev *d,struct ieee80211_vif *v,unsigned id) {
 (void)d;assert(id<15&&v->link[id]);return v->link[id];
}
static struct ieee80211_link_sta *link_sta_dereference_protected(struct ieee80211_sta *s,unsigned id) {
 assert(id<15&&s->link[id]);return s->link[id];
}
static int mt7996_mac_sta_links_event(struct mt7996_dev *d,struct ieee80211_vif *v,struct ieee80211_sta *s,u16 links,enum mt76_sta_event ev) {
 (void)d;(void)v;(void)s;(void)links;(void)ev;links_events++;last_links_order=++order;return link_error;
}
static int mt7996_mac_sta_add_links(struct mt7996_dev *d,struct ieee80211_vif *v,struct ieee80211_sta *s,unsigned long links) {
 (void)d;(void)v;(void)s;add_links_calls++;added_links=links;return add_links_error;
}
static void mt7996_mac_sta_clear_connected(struct mt7996_dev *d,struct mt7996_sta *s) {
 (void)d;(void)s;clear_events++;
}
'''

CASES = r'''
_Static_assert(sizeof(struct peer_mld_req_hdr)==12,"request ABI");
_Static_assert(sizeof(struct peer_mld_link_info)==8,"link ABI");
_Static_assert(sizeof(struct peer_mld_info)==16,"info ABI");
_Static_assert(sizeof(struct peer_mld_cap)==16,"cap ABI");
_Static_assert(sizeof(struct peer_mld_cap_entry)==8,"cap entry ABI");
_Static_assert(EXTRA_INFO_MLD_SKIP==BIT(2),"skip flag ABI");
static int checks,failed;
#define CHECK(x) do { checks++;if(!(x)){failed++;fprintf(stderr,"FAIL %s\n",#x);} } while(0)
static struct mt7996_dev dev;
static struct ieee80211_vif vif;
static struct ieee80211_sta sta;
static struct mt7996_sta msta;
static struct mt7996_sta_link links[3];
static struct mt7996_vif_link vlinks[3];
static struct ieee80211_link_sta lstas[3];
static bool zeroes(const void *p,size_t n) {
 const unsigned char *s=p;while(n--)if(*s++)return false;return true;
}
static void reset(u16 mask,u8 primary,u8 secondary) {
 memset(&dev,0,sizeof(dev));dev.mt76.mutex=1;
 memset(&vif,0,sizeof(vif));memset(&sta,0,sizeof(sta));memset(&msta,0,sizeof(msta));
 memset(links,0,sizeof(links));memset(vlinks,0,sizeof(vlinks));memset(lstas,0,sizeof(lstas));
 msta.deflink_id=primary;msta.seclink_id=secondary;msta.fw_mld_idx=0xface;
 sta.drv_priv=&msta;sta.valid_links=mask;sta.mlo=true;
 const u8 mac[]={0x02,0x11,0x22,0x33,0x44,0x55};memcpy(sta.addr,mac,sizeof(mac));
 for(unsigned i=0;i<3;i++) {
  links[i].wcid.idx=0x123+i*0x111;vlinks[i].mt76.idx=11+i*4;vlinks[i].mt76.band_idx=i;
  lstas[i].agg.max_amsdu_len=i==0?7935:i==1?3895:11454;
  msta.link[i]=&links[i];vif.link[i]=&vlinks[i];sta.link[i]=&lstas[i];
 }
 allocs=sends=alloc_fail=send_error=link_error=links_events=clear_events=0;
 requested=sent_len=0;sent_cmd=order=last_send_order=last_links_order=0;sent_wait=false;add_links_calls=add_links_error=0;added_links=0;
 memset(sent,0,sizeof(sent));
}
static void serialize(u16 mask,u8 primary,u8 secondary,u32 amsdu) {
 reset(mask,primary,secondary);CHECK(mt7996_mcu_set_peer_mld(&dev,&vif,&sta)==0);
 unsigned count=hweight16(mask);CHECK(allocs==1&&sends==1);
 CHECK(requested==60+8*count&&sent_len==requested);
 CHECK(sent_cmd==MCU_WMWA_UNI_CMD(PEER_MLD)&&sent_wait);
 struct peer_mld_req_hdr *h=(void *)sent;
 struct peer_mld_info *info=(void *)(sent+sizeof(*h));
 struct peer_mld_cap *cap=(void *)((unsigned char *)info+sizeof(*info)+count*sizeof(struct peer_mld_link_info));
 CHECK(le16_to_cpu(h->fw_mld_idx)==links[primary].wcid.idx);
 CHECK(!memcmp(h->peer_mld_addr,sta.addr,ETH_ALEN)&&h->ver==0&&h->rsv==0&&h->flag==0);
 CHECK(le16_to_cpu(info->tag)==UNI_CMD_PEER_MLD_INFO&&le16_to_cpu(info->len)==16+8*count);
 CHECK(info->link_num==count&&info->ver==0&&zeroes(info->rsv,sizeof(info->rsv))&&zeroes(info->rsv2,sizeof(info->rsv2)));
 CHECK(le16_to_cpu(info->primary_id)==links[primary].wcid.idx&&info->setup_wcid==info->primary_id);
 unsigned second=(mask&BIT(secondary))?secondary:primary;
 CHECK(le16_to_cpu(info->second_id)==links[second].wcid.idx);
 unsigned n=0;
 for(unsigned id=0;id<3;id++)if(mask&BIT(id)) {
  struct peer_mld_link_info *l=&info->link_info[n++];
  CHECK(l->link_id==id&&le16_to_cpu(l->fw_link_id)==links[id].wcid.idx&&le16_to_cpu(l->wlan_idx)==links[id].wcid.idx);
  CHECK(l->bss_idx==vlinks[id].mt76.idx&&l->band_idx==id&&l->rsv==0);
 }
 CHECK(le16_to_cpu(cap->tag)==UNI_CMD_PEER_MLD_CAP&&le16_to_cpu(cap->len)==32);
 CHECK(cap->ver==0&&cap->rsv==0&&cap->bitmap==0&&zeroes(cap->rsv2,sizeof(cap->rsv2)));
 CHECK(le32_to_cpu(cap->entry[0].type)==UNI_CMD_PEER_MLD_CAP_TYPE_AMSDU_MAX_LEN&&le32_to_cpu(cap->entry[0].val)==amsdu);
 CHECK(le32_to_cpu(cap->entry[1].type)==UNI_CMD_PEER_MLD_CAP_TYPE_AMSDU_MAX_CNT&&le32_to_cpu(cap->entry[1].val)==31);
 CHECK(msta.peer_mld_links==mask&&msta.fw_mld_idx==links[primary].wcid.idx);
 CHECK(sent[8]==(links[primary].wcid.idx&255)&&sent[9]==(links[primary].wcid.idx>>8));
}
static struct sta_rec_mld_setup *setup(struct sk_buff *s) {
 memset(s,0,sizeof(*s));s->capacity=sizeof(s->data);
 mt7996_mcu_sta_mld_setup_tlv(&dev,s,&vif,&sta);return (void *)s->data;
}
static void stable_primary(void) {
 reset(5,0,2);CHECK(mt7996_mcu_set_peer_mld(&dev,&vif,&sta)==0);
 u16 association_idx=msta.fw_mld_idx;msta.deflink_id=2;msta.seclink_id=0;
 struct sk_buff s;struct sta_rec_mld_setup *t=setup(&s);
 CHECK(le16_to_cpu(t->setup_wcid)==association_idx);
 CHECK(le16_to_cpu(t->primary_id)==association_idx);
#ifndef BASELINE
 CHECK(t->extra_info==EXTRA_INFO_MLD_SKIP&&t->link_num==2);
 CHECK(le16_to_cpu(t->seconed_id)==links[0].wcid.idx);
 CHECK(s.len==sizeof(*t)+2*sizeof(struct mld_setup_link));
 struct mld_setup_link *l=(void *)t->link_info;
 CHECK(le16_to_cpu(l[0].wcid)==links[0].wcid.idx&&l[0].bss_idx==11);
 CHECK(le16_to_cpu(l[1].wcid)==links[2].wcid.idx&&l[1].bss_idx==19);
 sta.valid_links=4;t=setup(&s);CHECK(t->extra_info==0&&le16_to_cpu(t->primary_id)==association_idx);
 msta.peer_mld_links=4;sta.valid_links=5;t=setup(&s);CHECK(t->extra_info==0&&le16_to_cpu(t->primary_id)==association_idx);
 msta.peer_mld_links=0;t=setup(&s);CHECK(t->extra_info==0&&le16_to_cpu(t->primary_id)==links[2].wcid.idx);
 sta.valid_links=1;t=setup(&s);CHECK(s.len==0);
#endif
}
int main(void) {
#ifdef BASELINE
 /* Only the old mutable-default behavior is reversed, not a firmware model. */
 stable_primary();
#else
 serialize(4,2,0,2);serialize(5,0,2,1);serialize(7,1,2,0);
 reset(5,0,2);msta.peer_mld_links=7;msta.ba_tx_mask=msta.ba_rx_mask=0xffff;
 CHECK(mt7996_mac_sta_add(&dev,&vif,&sta)==0&&add_links_calls==1&&added_links==5);
 CHECK(msta.peer_mld_links==0&&msta.ba_tx_mask==0&&msta.ba_rx_mask==0&&msta.conn_state==CONN_STATE_DISCONNECT);
 CHECK(msta.deflink_id==IEEE80211_LINK_UNSPECIFIED&&msta.seclink_id==IEEE80211_LINK_UNSPECIFIED&&dev.mt76.mutex==0);
 reset(0,0,0);add_links_error=-ENOSPC;msta.peer_mld_links=7;
 CHECK(mt7996_mac_sta_add(&dev,&vif,&sta)==-ENOSPC&&added_links==1&&msta.peer_mld_links==0&&dev.mt76.mutex==0);
 CHECK(mt7996_mcu_peer_mld_amsdu_len(11454)==2);
 CHECK(mt7996_mcu_peer_mld_amsdu_len(7935)==1);
 CHECK(mt7996_mcu_peer_mld_amsdu_len(7991)==1);
 CHECK(mt7996_mcu_peer_mld_amsdu_len(3895)==0);
 CHECK(mt7996_mcu_peer_mld_amsdu_len(0)==0);
 CHECK(mt7996_mcu_peer_mld_amsdu_len(U16_MAX)==0);
 reset(1,2,0);msta.peer_mld_links=3;msta.fw_mld_idx=0xabcd;
 CHECK(mt7996_mcu_set_peer_mld(&dev,&vif,&sta)==0&&allocs==0&&sends==0);
 CHECK(msta.peer_mld_links==3&&msta.fw_mld_idx==0xabcd);
 reset(5,0,2);alloc_fail=1;msta.peer_mld_links=3;msta.fw_mld_idx=0xabcd;
 CHECK(mt7996_mcu_set_peer_mld(&dev,&vif,&sta)==-ENOMEM&&sends==0);
 CHECK(msta.peer_mld_links==3&&msta.fw_mld_idx==0xabcd);
 reset(5,0,2);send_error=-ETIMEDOUT;msta.peer_mld_links=3;msta.fw_mld_idx=0xabcd;
 CHECK(mt7996_mcu_set_peer_mld(&dev,&vif,&sta)==-ETIMEDOUT&&sends==1);
 CHECK(msta.peer_mld_links==3&&msta.fw_mld_idx==0xabcd);
 stable_primary();
 reset(5,0,2);CHECK(mt7996_mac_sta_event(&dev,&vif,&sta,MT76_STA_EVENT_ASSOC)==0);
 CHECK(sends==1&&links_events==1&&last_send_order<last_links_order);
 CHECK(msta.peer_mld_links==5&&msta.conn_state==CONN_STATE_CONNECT&&dev.mt76.mutex==0);
 reset(5,0,2);send_error=-EIO;msta.peer_mld_links=3;msta.fw_mld_idx=0xabcd;
 CHECK(mt7996_mac_sta_event(&dev,&vif,&sta,MT76_STA_EVENT_ASSOC)==-EIO);
 CHECK(links_events==0&&msta.peer_mld_links==3&&msta.fw_mld_idx==0xabcd&&msta.conn_state==0&&dev.mt76.mutex==0);
 reset(5,0,2);alloc_fail=1;
 CHECK(mt7996_mac_sta_event(&dev,&vif,&sta,MT76_STA_EVENT_ASSOC)==-ENOMEM&&links_events==0&&sends==0&&dev.mt76.mutex==0);
 reset(1,0,0);sta.mlo=false;
 CHECK(mt7996_mac_sta_event(&dev,&vif,&sta,MT76_STA_EVENT_ASSOC)==0&&sends==0&&links_events==1&&msta.conn_state==CONN_STATE_CONNECT);
 reset(5,0,2);msta.peer_mld_links=5;
 CHECK(mt7996_mac_sta_event(&dev,&vif,&sta,MT76_STA_EVENT_DISASSOC)==0);
 CHECK(sends==0&&msta.peer_mld_links==0&&clear_events==1&&msta.conn_state==CONN_STATE_DISCONNECT&&dev.mt76.mutex==0);
 reset(5,0,2);msta.peer_mld_links=5;
 CHECK(mt7996_mac_sta_event(&dev,&vif,&sta,MT76_STA_EVENT_AUTHORIZE)==0&&sends==0&&msta.peer_mld_links==5&&msta.conn_state==CONN_STATE_PORT_SECURE);
 reset(5,0,2);link_error=-EINVAL;msta.peer_mld_links=5;msta.conn_state=CONN_STATE_PORT_SECURE;
 CHECK(mt7996_mac_sta_event(&dev,&vif,&sta,MT76_STA_EVENT_DISASSOC)==-EINVAL&&msta.peer_mld_links==5&&clear_events==0&&dev.mt76.mutex==0);
#endif
 printf("PEER_MLD: %d checks, %d failed; actual C serializers/caller and wire structs, ASan/UBSan\n",checks,failed);
 return failed?1:0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    mcu = (args.source / 'mt7996/mcu.c').read_text()
    driver = (args.source / 'mt7996/main.c').read_text()
    header = (args.source / 'mt7996/mcu.h').read_text()
    common = (args.source / 'mt76_connac_mcu.h').read_text()
    fields = (args.source / 'mt7996/mt7996.h').read_text()
    for name in ['peer_mld_links', 'fw_mld_idx']:
        assert re.search(r'\bu16\s+' + name + r';', fields), name
    structs = ''.join(wire_struct(header, name) for name in [
        'peer_mld_req_hdr', 'peer_mld_link_info', 'peer_mld_info',
        'peer_mld_cap_entry', 'peer_mld_cap', 'sta_rec_mld_setup', 'mld_setup_link'])
    constants = ''
    for name, text in [('MCU_UNI_CMD_PEER_MLD', common), ('UNI_CMD_PEER_MLD_INFO', header),
                       ('UNI_CMD_PEER_MLD_CAP', header),
                       ('UNI_CMD_PEER_MLD_CAP_TYPE_AMSDU_MAX_LEN', header),
                       ('UNI_CMD_PEER_MLD_CAP_TYPE_AMSDU_MAX_CNT', header)]:
        value = re.search(r'\b' + name + r'\s*=\s*(0x[0-9a-fA-F]+|\d+)', text)
        assert value, name
        constants += '#define ' + name + ' ' + value[1] + '\n'
    functions = function(mcu, 'mt7996_mcu_peer_mld_amsdu_len')
    functions += function(mcu, 'mt7996_mcu_set_peer_mld')
    setup = function(mcu, 'mt7996_mcu_sta_mld_setup_tlv')
    baseline, count = re.subn(r'\n\tif \(msta->peer_mld_links\)\n\t\tmld_setup->setup_wcid = cpu_to_le16\(msta->fw_mld_idx\);', '', setup)
    assert count == 1, 'Stable primary override changed; review baseline before changing test'
    caller = function(driver, 'mt7996_mac_sta_add') + function(driver, 'mt7996_mac_sta_event')
    with tempfile.TemporaryDirectory(prefix='mt7996-peer-mld-') as tmp:
        path = Path(tmp)
        for name, body, options in [('baseline', baseline, ['-DBASELINE']), ('candidate', setup, [])]:
            source = path / (name + '.c')
            source.write_text(SHIM + constants + structs + functions + body + caller + CASES)
            binary = source.with_suffix('')
            subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-Werror',
                            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                            *options, str(source), '-o', str(binary)], check=True)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            if name == 'baseline':
                assert run.returncode == 1 and '3 checks, 2 failed' in run.stdout, (run.stdout, run.stderr)
                assert run.stderr.count('FAIL ') == 2, run.stderr
                print('Baseline reversal: association setup/primary WCIDs fail after host default-link switch (2 expected failures).')
            else:
                print(run.stdout.strip())
                assert run.returncode == 0, (run.stdout, run.stderr)
    # Existing control-path fixtures cover0044 remove-only and0045 management selection.
    subprocess.run(['python3', str(Path(__file__).with_name('test_mt7996_mlo_backports.py')),
                    str(args.source)], check=True)
    print('Limits: wire/control-flow fixture; no MCU transport, DMA, radio, firmware, IRQ/RCU or performance emulation.')


if __name__ == '__main__':
    main()
