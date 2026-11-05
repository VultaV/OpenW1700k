#!/usr/bin/env python3
"""Compile actual setup code with pending-work stubs; not a kernel/HW test."""
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

function = runpy.run_path(str(Path(__file__).with_name('test_bridge_fdb_cleanup.py')))['function']
PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
enum flow_block_command { FLOW_BLOCK_BIND, FLOW_BLOCK_UNBIND };
struct netlink_ext_ack { int unused; };
struct flow_block_offload { int unused; };
struct nf_flowtable { bool hw; int gc_work; } table;
struct ops { void *ndo_setup_tc; } ops;
struct net_device { struct ops *netdev_ops; } dev = { &ops };
static int system_power_efficient_wq, del_queue;
#define nf_flow_offload_del_wq (&del_queue)
static bool bound, installed, pending_add, pending_del, teardown, skip_gc, queued;
static int cleanups, direct_calls, indirect_calls, block_calls, xdp_calls, error;
static bool nf_flowtable_hw_offload(struct nf_flowtable *t) { return t->hw; }
static void gc(void) {
 if (skip_gc) { skip_gc=false; return; }
 if (teardown && !pending_add && installed) pending_del=true;
}
static void delete_work(void) {
 if (pending_del) { assert(bound); installed=false; pending_del=false; }
}
static void nf_flow_table_gc_cleanup(struct nf_flowtable *t, struct net_device *d) {
 assert(bound); cleanups++; teardown=true; gc();
 /* Existing helper flushes ADD/DEL/STATS after its first GC. */
 if (pending_add) { installed=true; pending_add=false; }
 delete_work();
}
static void mod_delayed_work(int wq, int *work, int delay) {
 assert(work==&table.gc_work && delay==0); queued=true;
}
static void flush_delayed_work(int *work) {
 assert(work==&table.gc_work && queued); queued=false; gc();
}
static void flush_workqueue(int *wq) { assert(wq==nf_flow_offload_del_wq); delete_work(); }
static int command(enum flow_block_command cmd) {
 if (error) return error;
 if (cmd==FLOW_BLOCK_UNBIND) bound=false;
 return 0;
}
static int nf_flow_table_offload_cmd(struct flow_block_offload *b,
 struct nf_flowtable *t, struct net_device *d, enum flow_block_command c,
 struct netlink_ext_ack *e) { direct_calls++; return command(c); }
static int nf_flow_table_indr_offload_cmd(struct flow_block_offload *b,
 struct nf_flowtable *t, struct net_device *d, enum flow_block_command c,
 struct netlink_ext_ack *e) { indirect_calls++; return command(c); }
static int nf_flow_table_block_setup(struct nf_flowtable *t,
 struct flow_block_offload *b, enum flow_block_command c) { block_calls++; return 0; }
static int nf_flow_offload_xdp_setup(struct nf_flowtable *t,
 struct net_device *d, enum flow_block_command c) { xdp_calls++; return 0; }
static void reset(void) {
 table=(struct nf_flowtable){true,0}; bound=true; installed=true;
 pending_add=pending_del=teardown=skip_gc=queued=false;
 cleanups=direct_calls=indirect_calls=block_calls=xdp_calls=error=0;
}
'''
TESTS = r'''
int main(void) {
 int checks=0;
 for (int direct=0; direct<2; direct++)
 for (int pending=0; pending<2; pending++)
 for (int stale_gc=0; stale_gc<2; stale_gc++) {
  reset(); ops.ndo_setup_tc=direct ? &ops : NULL;
  pending_add=pending; installed=!pending; skip_gc=stale_gc;
  assert(nf_flow_table_offload_setup(&table,&dev,FLOW_BLOCK_UNBIND)==0);
  assert(!installed && !pending_del && !pending_add && !bound);
  assert(cleanups==1 && direct_calls==direct && indirect_calls==!direct && block_calls==1);
  checks++;
 }
 for (int direct=0; direct<2; direct++) {
  reset(); ops.ndo_setup_tc=direct ? &ops : NULL;
  assert(nf_flow_table_offload_setup(&table,&dev,FLOW_BLOCK_BIND)==0);
  assert(cleanups==0 && bound && installed); checks++;
 }
 for (int cmd=0; cmd<2; cmd++) {
  reset(); table.hw=false;
  assert(nf_flow_table_offload_setup(&table,&dev,cmd)==0);
  assert(xdp_calls==1 && cleanups==0 && direct_calls==0 && indirect_calls==0);
  checks++;
 }
 reset(); error=-95;
 assert(nf_flow_table_offload_setup(&table,&dev,FLOW_BLOCK_BIND)==-95);
 assert(block_calls==0 && cleanups==0); checks++;
 printf("PASS: %d actual-setup cases; pending ADD/old GC drained before callback removal\n",checks);
}
'''

source = Path(sys.argv[1]).read_text()
with tempfile.TemporaryDirectory(prefix='flowtable-unbind-') as directory:
    p = Path(directory)
    (p/'check.c').write_text(PREFIX + function(source, 'nf_flow_table_offload_setup') + TESTS)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-Wno-unused-function',
                    '-fsanitize=address,undefined', str(p/'check.c'), '-o', str(p/'check')], check=True)
    subprocess.run([str(p/'check')], check=True)
print('Scope: callback/work ordering model only; no real GC locking, DMA or packet forwarding.')
