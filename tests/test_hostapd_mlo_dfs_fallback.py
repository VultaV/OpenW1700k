#!/usr/bin/env python3
"""Compile actual DFS selection paths; availability is a regulatory-filter fixture."""
import argparse,pathlib,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('source',type=pathlib.Path);p.add_argument('--legacy',action='store_true');a=p.parse_args();s=a.source.read_text()
def fn(marker):
 t=s[s.rindex(marker):];return t[:t.index('\n}\n')+3]
code=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
#define MSG_DEBUG 0
#define MSG_INFO 1
#define wpa_printf(...) ((void)0)
#define HOSTAPD_DFS_REGION_ETSI 1
#define CONF_OPER_CHWIDTH_USE_HT 0
#define CONF_OPER_CHWIDTH_80MHZ 1
#define CONF_OPER_CHWIDTH_160MHZ 2
enum dfs_channel_type { DFS_ANY_CHANNEL,DFS_AVAILABLE,DFS_NO_CAC_YET };
struct hostapd_channel_data { int chan,freq; };
struct hostapd_config { int width,channel,secondary_channel,seg0,seg1; };
struct bss_config { bool mld_ap; };
struct hostapd_data { struct bss_config *conf; };
struct hostapd_iface { struct hostapd_config *conf;struct hostapd_data *bss[1];int cac_started,dfs_domain,freq; };
static unsigned available,cac;
static int busy,queries,restarts,requests,picked_width,original_width,cac_requests;
static int hostapd_get_oper_chwidth(struct hostapd_config *c) { return c->width; }
static void hostapd_set_oper_chwidth(struct hostapd_config *c,int width) { c->width=width; }
static void hostapd_set_oper_centr_freq_seg0_idx(struct hostapd_config *c,int x) { c->seg0=x; }
static void hostapd_set_oper_centr_freq_seg1_idx(struct hostapd_config *c,int x) { c->seg1=x; }
static int hostapd_csa_in_progress(struct hostapd_iface *i) { return busy; }
static int hostapd_dfs_start_channel_switch_cac(struct hostapd_iface *i) { cac_requests++;return 37; }
static int hostapd_disable_iface(struct hostapd_iface *i) { restarts++;return 0; }
static int hostapd_enable_iface(struct hostapd_iface *i) { return 0; }
static struct hostapd_channel_data *dfs_get_valid_channel(struct hostapd_iface *i,int *sec,u8 *s0,u8 *s1,enum dfs_channel_type type) {
 static struct hostapd_channel_data ch;queries++;int w=i->conf->width;
 if(!(available&(1u<<w))&&!(type==DFS_ANY_CHANNEL&&(cac&(1u<<w))))return 0;
 *sec=1;*s0=42;*s1=0;ch.chan=(available&(1u<<w))?149:100;ch.freq=ch.chan==149?5745:5500;return &ch;
}
static int hostapd_dfs_request_channel_switch(struct hostapd_iface *i,int ch,int freq,int sec,u8 old,u8 s0,u8 s1) {
 requests++;picked_width=i->conf->width;original_width=old;return 0;
}
'''
code+=fn('static struct hostapd_channel_data *\ndfs_downgrade_bandwidth(')+fn('static int hostapd_dfs_start_channel_switch(')
code+=r'''
static int checks,failed;
#define CHECK(x) do{checks++;if(!(x)){failed++;fprintf(stderr,"FAIL: %s\n",#x);}}while(0)
static int run(bool mld,int width,unsigned avail,unsigned needs_cac,int etsi,int in_cac,int csa) {
 struct hostapd_config config={.width=width};struct bss_config bc={.mld_ap=mld};struct hostapd_data b={.conf=&bc};struct hostapd_iface iface={.conf=&config,.bss={&b},.dfs_domain=etsi,.cac_started=in_cac};
 available=avail;cac=needs_cac;busy=csa;queries=restarts=requests=cac_requests=0;picked_width=original_width=-1;
 int ret=hostapd_dfs_start_channel_switch(&iface);return ret;
}
int main(void) {
#ifndef LEGACY
 run(true,2,2,4,0,0,0);CHECK(requests==1&&picked_width==1&&original_width==2&&restarts==0);
 run(true,2,1,4,0,0,0);CHECK(requests==1&&picked_width==0&&original_width==2&&restarts==0);
 run(true,1,1,2,0,0,0);CHECK(requests==1&&picked_width==0&&original_width==1&&restarts==0);
#endif
 run(true,2,4,0,0,0,0);CHECK(requests==1&&picked_width==2&&queries==1&&restarts==0);
 run(true,2,0,4,0,0,0);CHECK(restarts==1&&requests==0);
 run(true,2,2,0,0,0,0);CHECK(requests==1&&picked_width==1&&restarts==0);
 run(false,2,2,4,0,0,0);CHECK(restarts==1&&requests==0);
 run(false,2,2,0,0,0,0);CHECK(requests==1&&picked_width==1&&restarts==0);
 run(true,2,2,4,HOSTAPD_DFS_REGION_ETSI,0,0);CHECK(requests==1&&picked_width==2&&queries==1&&restarts==0);
 run(true,0,0,1,0,0,0);CHECK(restarts==1&&requests==0);
 run(true,2,0,0,0,0,0);CHECK(restarts==1&&requests==0);
 CHECK(run(true,2,2,4,0,0,1)==0&&queries==0&&restarts==0);
 CHECK(run(true,2,2,4,0,1,0)==37&&queries==0&&cac_requests==1);
 printf("MLO DFS fallback: %d checks, %d failed; actual selection C with availability fixtures, ASan/UBSan\n",checks,failed);
 return failed?1:0;
}
'''
with tempfile.TemporaryDirectory(prefix='mlo-dfs-fallback-') as t:
 c=pathlib.Path(t)/'check.c';exe=c.with_suffix('');c.write_text(code);cmd=['cc','-std=gnu11','-O1','-g','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all']+(['-DLEGACY'] if a.legacy else ['-DCONFIG_IEEE80211BE']);subprocess.run(cmd+[str(c),'-o',str(exe)],check=True);raise SystemExit(subprocess.run([str(exe)]).returncode)
