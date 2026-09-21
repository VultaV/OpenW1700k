"""Exercise the real nl80211 dispatcher before/after the pending-link fix."""
from pathlib import Path
import subprocess
import tempfile

r = Path(__file__).resolve().parents[1]
a = r / 'tests/fixtures/hostapd-dfs'

def function(source, marker):
    start = source.index(marker)
    end = source.index('\n}\n', start) + 3
    return source[start:end]

stub = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef int8_t s8;
#define NL80211_DRV_LINK_ID_NA -1
#define MSG_DEBUG 0
#define wpa_printf(...) ((void)0)
#define os_memset memset
#define for_each_link(links,i) for ((i)=0;(i)<3;(i)++) if ((links)&(1u<<(i)))
#define for_each_link_default(links,i,def) for_each_link((links)?(links):(1u<<(def)),i)
enum { NL80211_ATTR_WIPHY_FREQ, NL80211_ATTR_RADAR_EVENT,
 NL80211_ATTR_WIPHY_CHANNEL_TYPE, NL80211_ATTR_CHANNEL_WIDTH,
 NL80211_ATTR_CENTER_FREQ1, NL80211_ATTR_CENTER_FREQ2, ATTR_COUNT };
enum { NL80211_CHAN_NO_HT, NL80211_CHAN_HT20, NL80211_CHAN_HT40PLUS, NL80211_CHAN_HT40MINUS };
enum nl80211_radar_event { NL80211_RADAR_DETECTED, NL80211_RADAR_CAC_FINISHED,
 NL80211_RADAR_CAC_ABORTED, NL80211_RADAR_NOP_FINISHED,
 NL80211_RADAR_PRE_CAC_EXPIRED, NL80211_RADAR_CAC_STARTED };
struct nlattr { uint32_t value; };
#define nla_get_u32(a) ((a)->value)
#define convert2width(v) (v)
union wpa_event_data { struct { int freq, ht_enabled, chan_offset, chan_width, cf1, cf2, link_id; } dfs_event; };
struct i802_bss;
struct wpa_driver_nl80211_data { struct i802_bss *first_bss; };
struct i802_bss { struct wpa_driver_nl80211_data *drv; struct i802_bss *next;
 unsigned valid_links; struct { int freq; } links[3]; int id; };
static unsigned delivered, calls;
static void nl80211_process_radar_event(struct i802_bss *bss,
 union wpa_event_data *data, enum nl80211_radar_event event) {
 (void)event;
 int link = data->dfs_event.link_id;
 assert(link == -1 || (link >= 0 && link < 3));
 delivered |= 1u << (bss->id*4 + (link < 0 ? 0 : link));
 calls++;
}
'''
main = r'''
int main(void) {
 struct nlattr freq={5260}, event={0};
 struct nlattr *attrs[ATTR_COUNT]={[NL80211_ATTR_WIPHY_FREQ]=&freq,[NL80211_ATTR_RADAR_EVENT]=&event};
 unsigned cases=0;
 for (unsigned type=0;type<6;type++) {
  bool update=type==NL80211_RADAR_NOP_FINISHED || type==NL80211_RADAR_PRE_CAC_EXPIRED;
  for (int shape=0;shape<12;shape++) {
   struct wpa_driver_nl80211_data drv={0};
   struct i802_bss b={.drv=&drv}, second={.drv=&drv,.id=1};
   drv.first_bss=&b;
   unsigned want=0;
   switch(shape) {
   case 0: want=FIXED && update ? 1:0; break;
   case 1: b.links[0].freq=2412; break;
   case 2: b.links[0].freq=5180; want=1; break;
   case 3: b.links[0].freq=5260; want=1; break;
   case 4: b.valid_links=6; b.links[2].freq=6135; want=FIXED && update ? 2:0; break;
   case 5: b.valid_links=6; b.links[1].freq=5180; b.links[2].freq=6135; want=2; break;
   case 6: b.valid_links=6; b.links[1].freq=5500; want=2 | (FIXED && update ? 4:0); break;
   case 7: b.links[0].freq=2412; b.next=&second; break;
   case 8: b.links[0].freq=5260; b.next=&second; want=1; break;
   case 9: b.valid_links=6; b.links[1].freq=5260; b.links[2].freq=6135; want=2; break;
   case 10: b.links[0].freq=5180; b.next=&second; second.links[0].freq=5500; want=17; break;
   case 11: b.links[0].freq=6135; break;
   }
   if (FIXED && update) want=(b.valid_links ? b.valid_links:1) | (b.next ? 16:0);
   event.value=type; delivered=calls=0;
   nl80211_radar_event(&b,attrs);
   assert(delivered==want && calls==(unsigned)__builtin_popcount(want));
   for (int missing=0;missing<2;missing++) {
    struct nlattr *saved=attrs[missing]; attrs[missing]=NULL;
    delivered=calls=0; nl80211_radar_event(&b,attrs);
    assert(!delivered && !calls); attrs[missing]=saved; cases++;
   }
   cases++;
  }
 }
 printf("PASS %u dispatcher cases (%s)\n",cases,FIXED?"fixed":"baseline reproduces lost pending-link events");
}
'''
patch = (r/'package/network/services/hostapd/patches/9999-deliver-dfs-state-to-unconfigured-links.patch').read_text()
for fixed, name in enumerate(('before', 'fixed')):
    source = (a/f'driver_nl80211_event.{name}.c').read_text()
    if fixed:
        for line in patch.splitlines():
            if line.startswith('+') and not line.startswith('+++') and line[1:].strip():
                assert line[1:] in source
    functions = function(source, 'static s8\nnl80211_get_link_id_by_freq(')
    functions += function(source, 'static void nl80211_radar_event(')
    with tempfile.TemporaryDirectory(prefix='hostapd-dfs-check-') as tmp:
        path=Path(tmp)/'check.c'; path.write_text(stub+functions+main)
        exe=path.with_suffix('')
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
            f'-DFIXED={fixed}',str(path),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
