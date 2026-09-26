#!/usr/bin/env python3
"""Run extracted PPE ownership paths with fake hardware under ASan/UBSan.

Usage: test_airoha_ppe_ownership.py /path/to/airoha_ppe.c [/path/to/airoha_eth.h] [case]
Use --flush-baseline only to verify the old flush's exact false-success bug.
This checks driver control flow, not SRAM timing, NPU behavior or kernel locking.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def function(source, name):
    match = re.search(r'^static (?:bool|int|void|u32)\s+' + name + r'\(', source, re.M)
    assert match, name
    opening = source.index('{', match.start())
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end] + '\n'


PREFIX = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((~0U << (l)) & (~0U >> (31 - (h))))
#define FIELD_GET(m, v) (((v) & (m)) >> __builtin_ctz(m))
#define FIELD_PREP(m, v) (((u32)(v) << __builtin_ctz(m)) & (m))
#define DECLARE_FLEX_ARRAY(type, name) type name[0]
#define PPE_ENTRY_SIZE 80
#define GFP_ATOMIC 0
#define WARN_ON_ONCE(v) assert(!(v))
#define READ_ONCE(v) (v)
#define lockdep_assert_held(x) ((void)0)
#define spin_lock_bh(x) ((void)0)
#define spin_unlock_bh(x) ((void)0)
#define wmb() ((void)0)
#define kzalloc(n, f) calloc(1, n)
static int frees;
#define kfree(p) do { frees++; free(p); } while (0)
struct hlist_node { struct hlist_node *next, **pprev; };
struct hlist_head { struct hlist_node *first; };
struct rhash_head { void *next; };
static void hlist_add_head(struct hlist_node *n, struct hlist_head *h) {
    n->next = h->first;
    if (n->next) n->next->pprev = &n->next;
    h->first = n; n->pprev = &h->first;
}
static void hlist_del_init(struct hlist_node *n) {
    if (!n->pprev) return;
    *n->pprev = n->next;
    if (n->next) n->next->pprev = n->pprev;
    n->next = NULL; n->pprev = NULL;
}
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define hlist_for_each_entry_safe(p, n, h, m) \
    for (struct hlist_node *_node = (h)->first; \
         _node && ((p) = container_of(_node, __typeof__(*(p)), m), (n) = _node->next, 1); \
         _node = (n))
'''

SERVICES = r'''
enum { SLOTS = 16 };
struct airoha_ppe {
    struct hlist_head foe_flow[SLOTS];
    struct airoha_flow_table_entry *l2_flows;
    struct airoha_foe_entry *foe;
};
struct sk_buff { int unused; };
static struct airoha_foe_entry hardware[SLOTS];
static int commits, sram_commits, read_error = -1, write_error;
static unsigned sram_entries = SLOTS;
static int flush_error_index = -1;
static int airoha_l2_flow_table_params;
static u32 airoha_ppe_get_total_num_entries(struct airoha_ppe *p) { return SLOTS; }
static u32 airoha_ppe_get_total_sram_num_entries(struct airoha_ppe *p) { return sram_entries; }
static struct airoha_foe_entry *airoha_ppe_foe_get_entry_locked(struct airoha_ppe *p, u32 h) {
    assert(h < SLOTS);
    return (int)h == read_error ? NULL : &hardware[h];
}
static int airoha_ppe_foe_commit_sram_entry(struct airoha_ppe *p, u32 h) {
    assert(h < sram_entries);
    if (p->foe) {
        /* Flush must clear this shadow entry before committing it, in order. */
        assert(h == (unsigned)sram_commits);
        unsigned char *bytes = (unsigned char *)&p->foe[h];
        for (unsigned i = 0; i < sizeof(p->foe[h]); i++) assert(!bytes[i]);
        sram_commits++;
        return (int)h == flush_error_index ? write_error : 0;
    }
    sram_commits++; return write_error;
}
static int airoha_ppe_foe_commit_entry(struct airoha_ppe *p, struct airoha_foe_entry *e, u32 h, bool rx) {
    assert(h < SLOTS); commits++; hardware[h] = *e; return write_error;
}
static void *rhashtable_lookup_fast(struct airoha_flow_table_entry **table, void *key, int params) { return *table; }
static void airoha_ppe_foe_set_bridge_addrs(struct airoha_foe_bridge *b, void *h) {}
#define eth_hdr(skb) NULL
static int airoha_ppe_get_entry_idle_time(struct airoha_ppe *p, u32 ib1) { return 100 - (ib1 & 0xff); }
'''

CASES = r'''
static unsigned state(unsigned slot) { return FIELD_GET(AIROHA_FOE_IB1_BIND_STATE, hardware[slot].ib1); }
static void set_state(struct airoha_foe_entry *e, unsigned value) {
    e->ib1 = (e->ib1 & ~AIROHA_FOE_IB1_BIND_STATE) | FIELD_PREP(AIROHA_FOE_IB1_BIND_STATE, value);
}
static struct airoha_flow_table_entry make_flow(unsigned tuple, unsigned wcid, bool ipv6) {
    struct airoha_flow_table_entry e = { .type = FLOW_TYPE_L4, .hash = 0xffff };
    e.data.ib1 = FIELD_PREP(AIROHA_FOE_IB1_BIND_STATE, AIROHA_FOE_STATE_BIND);
    if (ipv6) {
        e.data.ib1 |= FIELD_PREP(AIROHA_FOE_IB1_BIND_PACKET_TYPE, PPE_PKT_TYPE_IPV6_ROUTE_5T);
        e.data.ipv6.src_ip[0] = tuple; e.data.ipv6.dest_ip[3] = 456;
        e.data.ipv6.ports = 789; e.data.ipv6.l2.vlan2 = wcid;
    } else {
        e.data.ipv4.orig_tuple.src_ip = tuple; e.data.ipv4.orig_tuple.dest_ip = 456;
        e.data.ipv4.orig_tuple.ports = 789; e.data.ipv4.l2.common.vlan2 = wcid;
    }
    return e;
}
static void add(struct airoha_ppe *p, struct airoha_flow_table_entry *e) {
    hlist_add_head(&e->list, &p->foe_flow[airoha_ppe_foe_get_entry_hash(p, &e->data)]);
}
static void reset(void) {
    memset(hardware, 0, sizeof(hardware));
    commits = sram_commits = frees = write_error = 0; read_error = -1;
    sram_entries = SLOTS; flush_error_index = -1;
}
static void duplicate(bool ipv6) {
    struct airoha_ppe p = {};
    struct sk_buff skb = {};
    struct airoha_flow_table_entry old = make_flow(123, 7, ipv6), fresh = make_flow(123, 29, ipv6);
    old.hash = 4; add(&p, &old); add(&p, &fresh);
    hardware[4] = old.data; set_state(&hardware[4], AIROHA_FOE_STATE_UNBIND);
    airoha_ppe_foe_insert_entry(&p, &skb, 4, false);
    assert(commits == 1);
    assert(old.hash == 0xffff && fresh.hash == 4);
    assert((ipv6 ? hardware[4].ipv6.l2.vlan2 : hardware[4].ipv4.l2.common.vlan2) == 29);
    airoha_ppe_foe_remove_flow(&p, &old);
    assert(state(4) == AIROHA_FOE_STATE_BIND);
    airoha_ppe_foe_remove_flow(&p, &fresh);
    assert(state(4) == AIROHA_FOE_STATE_INVALID);
}
static void collision(void) {
    struct airoha_ppe p = {};
    struct sk_buff skb = {};
    struct airoha_flow_table_entry old = make_flow(123, 7, false), fresh = make_flow(123, 29, false);
    unsigned bucket = airoha_ppe_foe_get_entry_hash(&p, &old.data);
    do { fresh.data.ipv4.orig_tuple.src_ip++; }
    while (airoha_ppe_foe_get_entry_hash(&p, &fresh.data) != bucket);
    old.hash = 6; hardware[6] = old.data; add(&p, &old); add(&p, &fresh);
    hardware[4] = fresh.data; set_state(&hardware[4], AIROHA_FOE_STATE_UNBIND);
    airoha_ppe_foe_insert_entry(&p, &skb, 4, false);
    assert(fresh.hash == 4 && old.hash == 6 && state(6) == AIROHA_FOE_STATE_BIND);
    airoha_ppe_foe_remove_flow(&p, &old);
    assert(state(4) == AIROHA_FOE_STATE_BIND && state(6) == AIROHA_FOE_STATE_INVALID);
    airoha_ppe_foe_remove_flow(&p, &fresh);
}
static void recycled(bool same_bucket) {
    struct airoha_ppe p = {};
    struct sk_buff skb = {};
    struct airoha_flow_table_entry old = make_flow(123, 7, false), fresh = make_flow(123, 29, false);
    unsigned bucket = airoha_ppe_foe_get_entry_hash(&p, &old.data);
    do { fresh.data.ipv4.orig_tuple.src_ip++; }
    while ((airoha_ppe_foe_get_entry_hash(&p, &fresh.data) == bucket) != same_bucket);
    old.hash = 4; add(&p, &old); add(&p, &fresh);
    hardware[4] = fresh.data; set_state(&hardware[4], AIROHA_FOE_STATE_UNBIND);
    airoha_ppe_foe_insert_entry(&p, &skb, 4, false);
    airoha_ppe_foe_remove_flow(&p, &old);
    assert(state(4) == AIROHA_FOE_STATE_BIND && fresh.hash == 4);
    airoha_ppe_foe_remove_flow(&p, &fresh);
}
static void packet_type(void) {
    struct airoha_flow_table_entry a = make_flow(123, 7, false);
    struct airoha_foe_entry b = a.data;
    b.ib1 |= FIELD_PREP(AIROHA_FOE_IB1_BIND_PACKET_TYPE, PPE_PKT_TYPE_IPV4_ROUTE);
    assert(!airoha_ppe_foe_compare_entry(&a, &b));
    b = a.data; b.ib1 |= AIROHA_FOE_IB1_BIND_UDP;
    assert(!airoha_ppe_foe_compare_entry(&a, &b));
}
static void invalid(void) {
    struct airoha_ppe p = {};
    struct sk_buff skb = {};
    struct airoha_flow_table_entry e = make_flow(123, 7, false);
    add(&p, &e);
    for (unsigned i = 0; i < 4; i++) {
        if (i == AIROHA_FOE_STATE_UNBIND) continue;
        hardware[4] = e.data; set_state(&hardware[4], i);
        airoha_ppe_foe_insert_entry(&p, &skb, 4, false);
        assert(commits == 0 && e.hash == 0xffff && state(4) == i);
    }
    airoha_ppe_foe_remove_flow(&p, &e);
}
static void move(void) {
    struct airoha_ppe p = {};
    struct sk_buff skb = {};
    struct airoha_flow_table_entry e = make_flow(123, 7, false);
    e.hash = 6; add(&p, &e); hardware[6] = e.data;
    hardware[4] = e.data; set_state(&hardware[4], AIROHA_FOE_STATE_UNBIND);
    read_error = 6;
    airoha_ppe_foe_insert_entry(&p, &skb, 4, false);
    assert(e.hash == 6 && commits == 0 && state(4) == AIROHA_FOE_STATE_UNBIND);
    read_error = -1;
    airoha_ppe_foe_insert_entry(&p, &skb, 4, false);
    assert(e.hash == 4 && state(6) == AIROHA_FOE_STATE_INVALID && state(4) == AIROHA_FOE_STATE_BIND);
    airoha_ppe_foe_remove_flow(&p, &e);
}
static void subflow(bool ipv6) {
    struct airoha_ppe p = {};
    struct sk_buff skb = {};
    struct airoha_flow_table_entry parent = { .type = FLOW_TYPE_L2 };
    struct airoha_flow_table_entry learned = make_flow(123, 7, ipv6);
    parent.data.ib1 = FIELD_PREP(AIROHA_FOE_IB1_BIND_STATE, AIROHA_FOE_STATE_BIND);
    parent.data.bridge.l2.common.vlan2 = 29;
    hardware[4] = learned.data; set_state(&hardware[4], AIROHA_FOE_STATE_UNBIND);
    assert(airoha_ppe_foe_commit_subflow_entry(&p, &parent, 4, false) == 0);
    struct airoha_flow_table_entry *sf = container_of(parent.l2_flows.first, struct airoha_flow_table_entry, l2_subflow_node);
    assert(sf->list.pprev && airoha_ppe_foe_compare_entry(sf, &hardware[4]));
    assert((ipv6 ? sf->data.ipv6.l2.vlan2 : sf->data.ipv4.l2.common.vlan2) == 29);
    /* An unrelated physical slot sharing its software bucket stays alive. */
    hardware[6] = learned.data; set_state(&hardware[6], AIROHA_FOE_STATE_UNBIND);
    airoha_ppe_foe_insert_entry(&p, &skb, 6, false);
    assert(frees == 0 && sf->hash == 4 && state(4) == AIROHA_FOE_STATE_BIND);
    /* L4 takes the recycled slot: retire/free the tracked L2 subflow once. */
    add(&p, &learned); set_state(&hardware[4], AIROHA_FOE_STATE_UNBIND);
    airoha_ppe_foe_insert_entry(&p, &skb, 4, false);
    assert(frees == 1 && !parent.l2_flows.first && learned.hash == 4);
    airoha_ppe_foe_remove_flow(&p, &learned);
}
static void stale_stats(void) {
    struct airoha_ppe p = {};
    struct airoha_flow_table_entry parent = { .type = FLOW_TYPE_L2 };
    struct airoha_flow_table_entry learned = make_flow(123, 7, true);
    struct airoha_flow_table_entry other = make_flow(124, 29, true);
    hardware[4] = learned.data; set_state(&hardware[4], AIROHA_FOE_STATE_UNBIND);
    assert(airoha_ppe_foe_commit_subflow_entry(&p, &parent, 4, false) == 0);
    hardware[4] = other.data;
    airoha_ppe_foe_flow_l2_entry_update(&p, &parent);
    assert(frees == 1 && !parent.l2_flows.first && state(4) == AIROHA_FOE_STATE_BIND);
    learned.hash = 4; add(&p, &learned);
    airoha_ppe_foe_flow_entry_update(&p, &learned);
    assert(learned.hash == 0xffff);
    hardware[4] = learned.data; set_state(&hardware[4], AIROHA_FOE_STATE_UNBIND); learned.hash = 4;
    airoha_ppe_foe_flow_entry_update(&p, &learned);
    assert(learned.hash == 0xffff);
    airoha_ppe_foe_remove_flow(&p, &learned);
}
#ifndef EXPECT_FLUSH_FALSE_SUCCESS
#define EXPECT_FLUSH_FALSE_SUCCESS 0
#endif
static bool flush(unsigned count, int fail_at, int error) {
    struct airoha_ppe p = {};
    sram_entries = count; flush_error_index = fail_at; write_error = error;
    /* Exact-sized allocation lets ASan detect accesses past the last entry. */
    if (count) {
        p.foe = malloc(count * sizeof(*p.foe));
        assert(p.foe);
        memset(p.foe, 0xa5, count * sizeof(*p.foe));
    }
    int ret = airoha_ppe_flush_sram_entries(&p);
    unsigned touched = fail_at < 0 ? count : (unsigned)fail_at + 1;
    assert(sram_commits == (int)touched && !commits);
    for (unsigned i = 0; i < count; i++) {
        unsigned char *bytes = (unsigned char *)&p.foe[i];
        for (unsigned j = 0; j < sizeof(p.foe[i]); j++)
            assert(bytes[j] == (i < touched ? 0 : 0xa5));
    }
    free(p.foe);
    if (EXPECT_FLUSH_FALSE_SUCCESS && fail_at >= 0) {
        /* Reject crashes, a different errno, or any other failure as proof. */
        assert(ret == 0 && error < 0);
        printf("EXPECTED_FAIL flush index %d: expected %d, observed false success 0\n", fail_at, error);
        return true;
    }
    assert(ret == (fail_at < 0 ? 0 : error));
    return false;
}
int main(int argc, char **argv) {
    int which = argc > 1 ? atoi(argv[1]) : -1;
    unsigned passed = 0, expected_failures = 0;
    for (int i = 0; i < 16; i++) {
        if (which >= 0 && which != i) continue;
        reset();
        bool expected_failure = false;
        switch (i) {
        case 0: duplicate(false); break;
        case 1: duplicate(true); break;
        case 2: collision(); break;
        case 3: recycled(false); break;
        case 4: recycled(true); break;
        case 5: packet_type(); break;
        case 6: invalid(); break;
        case 7: move(); break;
        case 8: subflow(false); break;
        case 9: subflow(true); break;
        case 10: stale_stats(); break;
        case 11: expected_failure = flush(0, -1, 0); break;
        case 12: expected_failure = flush(SLOTS, -1, 0); break;
        case 13: expected_failure = flush(SLOTS, 0, -EIO); break;
        case 14: expected_failure = flush(SLOTS, SLOTS / 2, -ETIMEDOUT); break;
        case 15: expected_failure = flush(SLOTS, SLOTS - 1, -EBUSY); break;
        }
        if (expected_failure) expected_failures++;
        else { passed++; printf("PASS case %d\n", i); }
    }
    printf("TOTAL %u PASS, %u EXPECTED_FAIL\n", passed, expected_failures);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('header', type=Path, nargs='?')
    parser.add_argument('case', type=int, choices=range(16), nargs='?')
    parser.add_argument('--flush-baseline', action='store_true',
                        help='require the old flush to return 0 for each injected SRAM error')
    args = parser.parse_args()
    source_path = args.source
    header_path = args.header or source_path.with_name('airoha_eth.h')
    source, header = source_path.read_text(), header_path.read_text()
    start = header.index('enum {\n\tAIROHA_FOE_STATE_INVALID,')
    end = header.index('\nstruct airoha_flow_data', start)
    types = header[start:end]
    start = header.index('enum airoha_flow_entry_type {')
    end = header.index('\nstruct airoha_wdma_info', start)
    types += header[start:end]
    names = ['airoha_ppe_foe_get_entry_hash', 'airoha_ppe_foe_compare_entry']
    if 'static int airoha_ppe_foe_clear_entry(' in source:
        names.append('airoha_ppe_foe_clear_entry')
    names += ['airoha_ppe_foe_remove_flow', 'airoha_ppe_foe_commit_subflow_entry',
              'airoha_ppe_foe_insert_entry', 'airoha_ppe_foe_flow_l2_entry_update',
              'airoha_ppe_foe_flow_entry_update', 'airoha_ppe_flush_sram_entries']
    code = PREFIX + types + SERVICES + ''.join(function(source, name) for name in names) + CASES
    with tempfile.TemporaryDirectory(prefix='ppe-ownership-') as directory:
        path = Path(directory)
        (path / 'check.c').write_text(code)
        subprocess.run(['cc', '-O1', '-g', '-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all',
                        f'-DEXPECT_FLUSH_FALSE_SUCCESS={int(args.flush_baseline)}',
                        str(path / 'check.c'), '-o', str(path / 'check')], check=True)
        result = subprocess.run([str(path / 'check'),
                                 *([] if args.case is None else [str(args.case)])], timeout=20)
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
