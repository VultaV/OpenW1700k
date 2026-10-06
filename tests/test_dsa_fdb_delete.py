#!/usr/bin/env python3
"""Compile the actual DSA deletion function with stubs, before/after the patch.

Usage: python3 tests/test_dsa_fdb_delete.py [path/to/net/dsa/switch.c]
The default input is the supplied, unmodified r44 build-tree evidence.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

from test_bridge_fdb_cleanup import function


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'target/linux/airoha/patches-6.18/9999-z7-net-dsa-make-absent-host-fdb-delete-idempotent.patch'
PREFIX = r'''
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
typedef unsigned short u16;
struct dsa_db { int id; };
struct dsa_switch;
struct dsa_switch_ops {
    int (*port_fdb_del)(struct dsa_switch *, int, const unsigned char *, u16, struct dsa_db);
};
struct dsa_switch { const struct dsa_switch_ops *ops; };
struct dsa_mac_addr { int refcount, list; };
struct dsa_port { struct dsa_switch *ds; int index, type, addr_lists_lock, fdbs; };
static struct dsa_mac_addr entry;
static bool present;
static int hw_result, hw_calls, misses, drops, hw_traces, freed, locked, failures;
static bool dsa_port_is_cpu(struct dsa_port *dp) { return dp->type == 1; }
static bool dsa_port_is_dsa(struct dsa_port *dp) { return dp->type == 2; }
static void mutex_lock(int *lock) { assert(!locked); locked = 1; }
static void mutex_unlock(int *lock) { assert(locked); locked = 0; }
static struct dsa_mac_addr *dsa_mac_addr_find(int *list, const unsigned char *addr,
                                            u16 vid, struct dsa_db db) {
    assert(locked && vid == 0 && db.id == 7);
    return present ? &entry : NULL;
}
static bool refcount_dec_and_test(int *count) { assert(*count > 0); return --*count == 0; }
static void refcount_set(int *count, int value) { *count = value; }
static void list_del(int *list) { assert(locked); present = false; }
static void kfree(void *addr) { assert(addr == &entry); freed++; }
#define trace_dsa_fdb_del_hw(...) (hw_traces++)
#define trace_dsa_fdb_del_not_found(...) (misses++)
#define trace_dsa_fdb_del_drop(...) (drops++)
static int hw_delete(struct dsa_switch *ds, int port, const unsigned char *addr,
                     u16 vid, struct dsa_db db) { hw_calls++; return hw_result; }
#define CHECK(test) do { if (!(test)) { fprintf(stderr, "FAIL: %s\n", #test); failures++; } } while (0)
'''
SUFFIX = r'''
int main(void) {
    const struct dsa_switch_ops ops = { .port_fdb_del = hw_delete };
    struct dsa_switch ds = { .ops = &ops };
    struct dsa_port dp = { .ds = &ds, .index = 6 };
    const unsigned char addr[6] = {2, 0, 0, 0, 0, 1};
    struct dsa_db db = { .id = 7 };
    int cases = 0;
    for (int type = 1; type <= 2; type++) {
        dp.type = type;
        present = false; hw_calls = misses = 0;
        /* Two bridged user ports, repeated unpaired STA teardown notifications. */
        for (int i = 0; i < 4; i++) {
            CHECK(dsa_port_do_fdb_del(&dp, addr, 0, db) == 0);
            CHECK(!locked && !hw_calls && misses == i + 1);
            cases++;
        }
        present = true; entry.refcount = 2; drops = freed = 0; hw_result = 0;
        CHECK(dsa_port_do_fdb_del(&dp, addr, 0, db) == 0);
        CHECK(present && entry.refcount == 1 && drops == 1 && !hw_calls && !locked);
        cases++;
        CHECK(dsa_port_do_fdb_del(&dp, addr, 0, db) == 0);
        CHECK(!present && freed == 1 && hw_calls == 1 && !locked);
        cases++;
        for (int i = 0; i < 3; i++) {
            const int errors[] = {-ETIMEDOUT, -EIO, -ENOENT};
            present = true; entry.refcount = 1; hw_result = errors[i];
            CHECK(dsa_port_do_fdb_del(&dp, addr, 0, db) == errors[i]);
            CHECK(present && entry.refcount == 1 && freed == 1 && !locked);
            cases++;
        }
    }
    /* Ordinary user-port driver errors are never swallowed. */
    dp.type = 0; present = false;
    for (int i = 0; i < 4; i++) {
        const int results[] = {0, -ENOENT, -EIO, -ETIMEDOUT};
        hw_result = results[i]; hw_calls = 0;
        CHECK(dsa_port_do_fdb_del(&dp, addr, 0, db) == results[i]);
        CHECK(hw_calls == 1 && !locked);
        cases++;
    }
    printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
'''


def run(source, directory):
    c = directory / 'check.c'
    c.write_text(PREFIX + function(source, 'dsa_port_do_fdb_del') + SUFFIX)
    binary = directory / 'check'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-fsanitize=address,undefined',
                    str(c), '-o', str(binary)], check=True)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
    print(result.stdout.strip())
    return result


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / '.evidence/kernel/net-dsa/switch.c'
    with tempfile.TemporaryDirectory(prefix='dsa-fdb-') as temporary:
        directory = Path(temporary)
        candidate = directory / 'net/dsa/switch.c'
        candidate.parent.mkdir(parents=True)
        candidate.write_text(source.read_text())
        print('Before:', end=' ', flush=True)
        before = run(candidate.read_text(), directory)
        assert before.returncode == 1 and before.stdout == 'cases=22 failures=8\n', before.stderr
        subprocess.run(['patch', '-s', '-p1', '-i', str(PATCH)], cwd=directory, check=True)
        print('After: ', end=' ', flush=True)
        after = run(candidate.read_text(), directory)
        assert after.returncode == 0 and after.stdout == 'cases=22 failures=0\n', after.stderr
    print('PASS: expected pre-fix failures, post-fix success; extracted C, not a kernel/device test.')


if __name__ == '__main__':
    main()
