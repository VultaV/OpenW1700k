#!/usr/bin/env python3
"""Check the MLO data link choice of mt7996 patch 0042.

Extracts mt7996_sta_link_signal() and mt7996_sta_best_link() from a
patched mt76 tree, compiles them with host shims and runs link cases.

usage: test_mt7996_data_link.py <patched mt76 dir>
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SHIM = r'''
#include <limits.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef unsigned char u8;
#define IEEE80211_MLD_MAX_NUM_LINKS 15
#define IEEE80211_LINK_UNSPECIFIED 15
#define READ_ONCE(x) (x)
#define for_each_set_bit(b, addr, size) \
	for ((b) = 0; (b) < (size); (b)++) if (*(addr) & (1UL << (b)))
struct ewma_avg_signal { unsigned long v; };
static unsigned long ewma_avg_signal_read(struct ewma_avg_signal *e) { return e->v; }
struct mt76_wcid { bool link_valid; u8 phy_idx; };
struct mt7996_sta_link { struct mt76_wcid wcid; struct ewma_avg_signal avg_ack_signal; };
struct mt7996_sta { u8 deflink_id; struct mt7996_sta_link *link[IEEE80211_MLD_MAX_NUM_LINKS]; };
struct ieee80211_sta { unsigned short valid_links; struct mt7996_sta drv_priv[1]; };
struct mt7996_dev { int unused; };
static struct mt7996_sta_link *
mt7996_sta_link_protected(struct mt7996_dev *dev, struct mt7996_sta *msta, u8 id)
{ return id < IEEE80211_MLD_MAX_NUM_LINKS ? msta->link[id] : NULL; }
#define MT7996_DATA_LINK_ENTER %(enter)s
#define MT7996_DATA_LINK_STAY %(stay)s
%(funcs)s

/* links: band index per link id (-1 = absent), signal in dBm (0 = none) */
static int pick(int deflink, const int band[3], const int signal[3])
{
	struct mt7996_sta_link l[3];
	struct ieee80211_sta sta = { 0 };
	struct mt7996_dev dev;
	int i;

	for (i = 0; i < 3; i++) {
		if (band[i] < 0)
			continue;
		l[i].wcid.link_valid = true;
		l[i].wcid.phy_idx = band[i];
		l[i].avg_ack_signal.v = -signal[i];
		sta.drv_priv->link[i] = &l[i];
		sta.valid_links |= 1 << i;
	}
	sta.drv_priv->deflink_id = deflink;
	return mt7996_sta_best_link(&dev, &sta);
}

int main(void)
{
	/* link 0 = 2.4 GHz, link 1 = 5 GHz, link 2 = 6 GHz */
	static const int b3[3] = { 0, 1, 2 }, b26[3] = { 0, -1, 2 };
	static const struct { int def; const int *band; int sig[3]; int want; const char *name; } c[] = {
		{ 0, b26, { -30, 0, -40 }, 2, "near: 2.4 association moves to 6 GHz" },
		{ 2, b26, { -30, 0, -40 }, 2, "near: 6 GHz stays" },
		{ 2, b26, { -60, 0, -76 }, 2, "6 GHz above the stay level stays" },
		{ 0, b26, { -60, 0, -76 }, 0, "6 GHz below the enter level is not taken" },
		{ 2, b26, { -60, 0, -80 }, 0, "6 GHz below the stay level falls back to 2.4" },
		{ 2, b3, { -60, -70, -80 }, 1, "6 GHz fades with 5 GHz usable: 5 GHz" },
		{ 2, b26, { -80, 0, -84 }, 2, "nothing usable, current within 6 dB stays" },
		{ 2, b26, { -76, 0, -84 }, 0, "nothing usable, 2.4 GHz 8 dB stronger wins" },
		{ 2, b26, { 0, 0, 0 }, 2, "no samples keep the current link" },
		{ 0, b3, { -40, -50, 0 }, 1, "6 GHz without a sample is skipped" },
	};
	int i, failed = 0;

	for (i = 0; i < (int)(sizeof(c) / sizeof(c[0])); i++) {
		int got = pick(c[i].def, c[i].band, c[i].sig);

		if (got != c[i].want) {
			printf("FAIL %%s: got %%d want %%d\n", c[i].name, got, c[i].want);
			failed++;
		}
	}
	printf("data link: %%d checks, %%d failed\n", i, failed);
	return failed != 0;
}
'''


def extract(source, name):
    m = re.search(r'^static (?:int|u8)\n%s\(.*?^}\n' % name, source, re.S | re.M)
    if not m:
        sys.exit('missing %s' % name)
    return m.group(0)


def main():
    source = (Path(sys.argv[1]) / 'mt7996/main.c').read_text()
    defs = dict(re.findall(r'#define (MT7996_DATA_LINK_\w+)\s+(-?\d+)', source))
    funcs = extract(source, 'mt7996_sta_link_signal') + extract(source, 'mt7996_sta_best_link')
    code = SHIM % {'enter': defs['MT7996_DATA_LINK_ENTER'],
                   'stay': defs['MT7996_DATA_LINK_STAY'], 'funcs': funcs}
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp) / 'check.c'
        c.write_text(code)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Werror', '-Wno-unused-function',
                        '-fsanitize=address,undefined', str(c), '-o', str(c.with_suffix(''))],
                       check=True)
        sys.exit(subprocess.run([str(c.with_suffix(''))]).returncode)


if __name__ == '__main__':
    main()
