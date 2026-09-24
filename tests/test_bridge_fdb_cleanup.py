#!/usr/bin/env python3
"""Exercise candidate C with stubbed kernel services; not a hardware test.

Usage: python3 tests/test_bridge_fdb_cleanup.py /path/to/candidate/nf_flow_table_core.c
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def function(source, name):
    start = re.search(r'^(?:static )?(?:bool|int|void) ' + name + r'\(', source, re.M)
    assert start, name
    opening = source.index('{', start.start())
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start.start():end]


PREFIX = r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint64_t u64;
typedef int64_t s64;
#define ETH_ALEN 6
#define FLOW_OFFLOAD_DIR_MAX 2
#define FLOW_OFFLOAD_XMIT_DIRECT 3
#define NF_FLOW_BRIDGE 0
#define NF_FLOW_TEARDOWN 1
#define IPS_OFFLOAD_BIT 0
#define CONFIG_NET_SWITCHDEV 1
#define IS_ENABLED(x) (x)
#define NOTIFY_DONE 0
#define GFP_ATOMIC 0
#define SWITCHDEV_FDB_DEL_TO_DEVICE 1
struct net { int refs; } net_a, net_b;
struct nf_conn { struct net *net; unsigned long status; } ct = { .net = &net_a };
struct flow_offload_tuple {
    int xmit_type, encap_num;
    struct { unsigned ifidx; u8 h_dest[6]; } out;
};
struct flow_offload {
    unsigned long flags;
    struct nf_conn *ct;
    u64 fdb_gen;
    struct { struct flow_offload_tuple tuple; } tuplehash[2];
};
struct nf_flowtable { int unused; } table;
struct work_struct { void (*callback)(struct work_struct *); };
struct flow_fdb_cleanup {
    struct work_struct work; struct net *net; u64 gen; uint32_t ifindex; u8 addr[6];
};
struct net_device { struct net *net; int ifindex; bool bridge; } device = { &net_a, 7, true };
struct switchdev_notifier_info { struct net_device *dev; };
struct switchdev_notifier_fdb_info { struct switchdev_notifier_info info; const u8 *addr; int is_local, vid; };
struct notifier_block { int unused; };
static pthread_mutex_t flow_fdb_lock = PTHREAD_MUTEX_INITIALIZER;
static u64 flow_fdb_gen;
static int flow_fdb_wq, add_result, queued_count, published;
static bool alloc_failure;
static atomic_bool add_started, event_allocated, gate;
static struct flow_fdb_cleanup *queued;
static bool test_bit(int bit, const unsigned long *value) { return !!(*value & (1UL << bit)); }
static bool test_and_set_bit(int bit, unsigned long *value) { return !!(__atomic_fetch_or(value, 1UL << bit, __ATOMIC_SEQ_CST) & (1UL << bit)); }
static void clear_bit(int bit, unsigned long *value) { __atomic_fetch_and(value, ~(1UL << bit), __ATOMIC_SEQ_CST); }
#define clear_bit_unlock clear_bit
static int fixup_count;
static void flow_offload_fixup_ct(struct flow_offload *flow) {
    assert(test_bit(IPS_OFFLOAD_BIT, &flow->ct->status));
    fixup_count++;
}
static bool net_eq(const struct net *a, const struct net *b) { return a == b; }
static struct net *nf_ct_net(const struct nf_conn *c) { return c->net; }
static bool ether_addr_equal(const u8 *a, const u8 *b) { return memcmp(a, b, 6) == 0; }
static bool is_valid_ether_addr(const u8 *a) { static const u8 zero[6]; return !(a[0] & 1) && memcmp(a, zero, 6); }
static void ether_addr_copy(u8 *to, const u8 *from) { memcpy(to, from, 6); }
static struct net_device *switchdev_notifier_info_to_dev(struct switchdev_notifier_info *info) { return info->dev; }
static bool netif_is_bridge_port(const struct net_device *dev) { return dev->bridge; }
static struct net *dev_net(struct net_device *dev) { return dev->net; }
static struct net *get_net(struct net *net) { net->refs++; return net; }
static void *kmalloc(size_t n, int flags) {
    if (alloc_failure) return NULL;
    void *result = calloc(1, n);
    assert(result);
    atomic_store(&event_allocated, true);
    return result;
}
static void nf_flow_fdb_cleanup_work(struct work_struct *work) {}
#define INIT_WORK(w, fn) ((w)->callback = (fn))
static void queue_work(int wq, struct work_struct *work) {
    assert(!queued);
    queued = (struct flow_fdb_cleanup *)work;
    queued_count++;
}
static void spin_lock_bh(pthread_mutex_t *lock) { assert(!pthread_mutex_lock(lock)); }
static void spin_unlock_bh(pthread_mutex_t *lock) { assert(!pthread_mutex_unlock(lock)); }
static int __flow_offload_add(struct nf_flowtable *ft, struct flow_offload *flow) {
    if (test_bit(NF_FLOW_BRIDGE, &flow->flags))
        assert(pthread_mutex_trylock(&flow_fdb_lock) == EBUSY);
    if (atomic_load(&gate)) {
        atomic_store(&add_started, true);
        while (!atomic_load(&event_allocated)) sched_yield();
    }
    published = add_result ? 0 : 2;
    return add_result;
}
'''

SUFFIX = r'''
static struct flow_offload baseline(void) {
    struct flow_offload f = { .flags = 1, .ct = &ct };
    f.tuplehash[1].tuple.xmit_type = FLOW_OFFLOAD_XMIT_DIRECT;
    f.tuplehash[1].tuple.out.ifidx = 7;
    f.tuplehash[1].tuple.out.h_dest[0] = 2;
    f.tuplehash[1].tuple.out.h_dest[5] = 1;
    return f;
}
static void release_event(void) {
    assert(queued && queued->net->refs == 1);
    queued->net->refs--;
    free(queued);
    queued = NULL;
}
static void *publish_flow(void *arg) {
    assert(flow_offload_add(&table, arg) == 0);
    return NULL;
}
int main(void) {
    struct flow_offload f = baseline(), copy;
    struct flow_fdb_cleanup event = { .net = &net_a, .gen = 1, .ifindex = 7, .addr = {2, 0, 0, 0, 0, 1} };
    struct switchdev_notifier_fdb_info info = { .info.dev = &device, .addr = event.addr };
    struct nf_conn other_ct = { .net = &net_b };
    assert(nf_flow_fdb_matches(&f, &event));
    copy = f; copy.flags = 0; assert(!nf_flow_fdb_matches(&copy, &event));
    copy = f; copy.ct = &other_ct; assert(!nf_flow_fdb_matches(&copy, &event));
    copy = f; copy.fdb_gen = 1; assert(!nf_flow_fdb_matches(&copy, &event));
    copy = f; copy.fdb_gen = 2; assert(!nf_flow_fdb_matches(&copy, &event));
    copy = f; copy.tuplehash[1].tuple.out.ifidx = 8; assert(!nf_flow_fdb_matches(&copy, &event));
    copy = f; copy.tuplehash[1].tuple.out.h_dest[5] = 2; assert(!nf_flow_fdb_matches(&copy, &event));
    copy = f; copy.tuplehash[1].tuple.xmit_type = 1; assert(!nf_flow_fdb_matches(&copy, &event));
    copy = f; copy.tuplehash[0].tuple.encap_num = 1; assert(!nf_flow_fdb_matches(&copy, &event));
    copy = f; copy.tuplehash[1].tuple.encap_num = 1; assert(!nf_flow_fdb_matches(&copy, &event));
    copy = f; copy.tuplehash[0] = copy.tuplehash[1]; copy.tuplehash[1].tuple.xmit_type = 0;
    assert(nf_flow_fdb_matches(&copy, &event));
    copy = f; copy.fdb_gen = UINT64_MAX; event.gen = 0; assert(nf_flow_fdb_matches(&copy, &event));
    copy.fdb_gen = 0; event.gen = UINT64_MAX; assert(!nf_flow_fdb_matches(&copy, &event));
    nf_flow_fdb_event(NULL, 99, &info);
    nf_flow_fdb_event(NULL, 1, NULL);
    info.addr = NULL; nf_flow_fdb_event(NULL, 1, &info); info.addr = event.addr;
    info.info.dev = NULL; nf_flow_fdb_event(NULL, 1, &info); info.info.dev = &device;
    device.bridge = false; nf_flow_fdb_event(NULL, 1, &info); device.bridge = true;
    info.is_local = 1; nf_flow_fdb_event(NULL, 1, &info); info.is_local = 0;
    info.vid = 1; nf_flow_fdb_event(NULL, 1, &info); info.vid = 0;
    event.addr[0] = 1; nf_flow_fdb_event(NULL, 1, &info); event.addr[0] = 2;
    alloc_failure = true; nf_flow_fdb_event(NULL, 1, &info); alloc_failure = false;
    assert(!queued_count && !net_a.refs && !flow_fdb_gen);
    add_result = -12;
    assert(flow_offload_add(&table, &f) == -12);
    assert(!pthread_mutex_trylock(&flow_fdb_lock)); pthread_mutex_unlock(&flow_fdb_lock);
    add_result = 0;
    for (int i = 0; i < 1000; i++) {
        pthread_t thread;
        f = baseline();
        atomic_store(&add_started, false); atomic_store(&event_allocated, false); atomic_store(&gate, true);
        assert(!pthread_create(&thread, NULL, publish_flow, &f));
        while (!atomic_load(&add_started)) sched_yield();
        nf_flow_fdb_event(NULL, 1, &info);
        assert(!pthread_join(thread, NULL));
        assert(published == 2 && f.fdb_gen + 1 == queued->gen);
        assert(nf_flow_fdb_matches(&f, queued));
        atomic_store(&gate, false);
        copy = baseline();
        assert(!flow_offload_add(&table, &copy));
        assert(!nf_flow_fdb_matches(&copy, queued));
        release_event();
    }
    assert(net_a.refs == 0 && queued_count == 1000);
    f = baseline(); ct.status = 1;
    flow_offload_teardown(&f);
    assert(!ct.status && fixup_count == 1 && test_bit(NF_FLOW_TEARDOWN, &f.flags));
    copy = baseline(); ct.status = 1; /* Same conntrack has a replacement flow. */
    flow_offload_teardown(&f);
    assert(ct.status == 1 && fixup_count == 1);
    flow_offload_teardown(&copy);
    assert(!ct.status && fixup_count == 2);
    puts("PASS: 13 matching cases, 9 rejected events, 1 insertion failure, 1000 publication races, 3 teardown cases; failures=0");
    return 0;
}
'''


def main():
    source = Path(sys.argv[1]).read_text()
    c = PREFIX + '\n'.join(function(source, name) for name in
        ['flow_offload_add', 'flow_offload_teardown', 'nf_flow_fdb_matches', 'nf_flow_fdb_event']) + SUFFIX
    with tempfile.TemporaryDirectory(prefix='bridge-fdb-check-') as directory:
        path = Path(directory)
        (path / 'check.c').write_text(c)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                        '-fsanitize=address,undefined', '-pthread', str(path / 'check.c'), '-o', str(path / 'check')], check=True)
        subprocess.run([str(path / 'check')], check=True, timeout=20)
    print('Scope: extracted C with stubs, not kernel locking/GC/hardware acceptance.')


if __name__ == '__main__':
    main()
