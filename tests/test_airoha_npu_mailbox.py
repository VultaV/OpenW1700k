#!/usr/bin/env python3
"""Run the actual coherent-mailbox function with a bounded host device model.

Only temporary C copies are changed. This orders one timeout/late-response
scenario; it does not emulate firmware, real concurrency, DMA or MMIO timing.
Prints JSON; never changes production source or contacts a device.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

def function(source, name):
    match = re.search(r'^static int\s+' + name + r'\(', source, re.M)
    assert match, name
    start = source.index('{', match.start())
    end, depth = start + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end] + '\n'


def variants(text, patch, root):
    """Apply/reverse the actual product patch in a disposable source copy."""
    name = '__airoha_npu_send_msg'
    marker = 'if ((val & (MBOX_MSG_WAIT_RSP | MBOX_MSG_DONE)) == MBOX_MSG_WAIT_RSP)'
    already_applied = marker in function(text, name)
    path = root / 'drivers/net/ethernet/airoha/airoha_npu.c'
    path.parent.mkdir(parents=True)
    path.write_text(text)
    base = ['patch', '-p1', '--batch', '--force', '--fuzz=0', '-i', str(patch.resolve())]
    direction = ['--reverse'] if already_applied else ['--forward']
    subprocess.run(base + direction + ['--dry-run'], cwd=root, check=True, capture_output=True)
    subprocess.run(base + direction, cwd=root, check=True, capture_output=True)
    other = path.read_text()
    before, after = (other, text) if already_applied else (text, other)
    assert marker not in function(before, name) and marker in function(after, name)
    # Round trip must reproduce the entire provided source, not just the function.
    opposite = ['--forward'] if already_applied else ['--reverse']
    subprocess.run(base + opposite, cwd=root, check=True, capture_output=True)
    assert path.read_text() == text, 'product patch round trip changed unrelated source'
    return function(before, name), function(after, name), already_applied


STUBS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
typedef uint16_t u16;
#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((0xffffffffU >> (31-(h))) & (0xffffffffU << (l)))
#define FIELD_PREP(mask, value) (((u32)(value) << __builtin_ctz(mask)) & (mask))
#define FIELD_GET(mask, value) (((u32)(value) & (mask)) >> __builtin_ctz(mask))
#define MSEC_PER_SEC 1000
ACTUAL_DEFINES
#define NPU_MBOX_SUCCESS 1
/* Reduced host fixtures, not the kernel ABI structures. */
struct airoha_npu_core { int lock; void *buf; u32 addr; };
struct airoha_npu { void *regmap; struct airoha_npu_core cores[1]; };
enum response { SUCCESS, ERROR_STATUS, TIMEOUT, POLL_IO_ERROR, LATE_A };
struct fixture {
    struct airoha_npu npu;
    u32 ctrl[4];
    unsigned char buffer[AIROHA_NPU_MBOX_SIZE];
    unsigned char data[AIROHA_NPU_MBOX_SIZE], reply[AIROHA_NPU_MBOX_SIZE];
    unsigned writes, polls, locks, unlocks;
    int preflight_error;
    enum response response;
};
static struct fixture f;
static const char *why;
static unsigned passed, failed;
static int b_return, resumed_return = -999;
static bool late_a_accepted_as_b, b_preserved;
#define CHECK(condition, reason) do { if (!(condition)) { why = reason; return false; } } while (0)
static unsigned char answer(unsigned i, bool late) { return (unsigned char)((late ? 0xa0 : 0xb0) + i); }
static unsigned slot(unsigned reg) {
    assert(reg >= REG_CR_MBQ0_CTRL(0) && reg <= REG_CR_MBQ0_CTRL(3));
    assert((reg - REG_CR_MBQ0_CTRL(0)) % 4 == 0);
    return (reg - REG_CR_MBQ0_CTRL(0)) / 4;
}
static void spin_lock_bh(int *lock) { assert(!*lock); *lock = 1; f.locks++; }
static void spin_unlock_bh(int *lock) { assert(*lock == 1); *lock = 0; f.unlocks++; }
static int regmap_read(void *map, unsigned reg, u32 *value) {
    assert(map == &f && f.npu.cores[0].lock);
    unsigned i = slot(reg);
    if (i == 3 && f.preflight_error) return f.preflight_error;
    *value = f.ctrl[i]; return 0;
}
static int regmap_write(void *map, unsigned reg, u32 value) {
    assert(map == &f && f.npu.cores[0].lock);
    f.ctrl[slot(reg)] = value; f.writes++; return 0;
}
static void complete(bool late, unsigned status) {
    assert(f.ctrl[1] <= sizeof(f.buffer));
    for (unsigned i = 0; i < f.ctrl[1]; i++) f.buffer[i] = answer(i, late);
    f.ctrl[3] = (f.ctrl[3] & ~MBOX_MSG_STATUS) | MBOX_MSG_DONE | FIELD_PREP(MBOX_MSG_STATUS, status);
}
static int poll_once(void *map, unsigned reg, u32 *value) {
    assert(map == &f && f.npu.cores[0].lock && slot(reg) == 3);
    f.polls++;
    if (f.response == TIMEOUT) { *value = f.ctrl[3]; return -ETIMEDOUT; }
    if (f.response == POLL_IO_ERROR) return -EIO;
    /* LATE_A is an explicit possible device ordering, not a firmware claim. */
    complete(f.response == LATE_A, f.response == ERROR_STATUS ? 0 : NPU_MBOX_SUCCESS);
    *value = f.ctrl[3]; return 0;
}
#define regmap_read_poll_timeout_atomic(map, reg, value, condition, delay, timeout) \
    ({ assert((delay) == 100 && (timeout) == 500000); \
       int e = poll_once(map, reg, &(value)); assert(e || (condition)); e; })
static void setup(u32 ctrl3) {
    memset(&f, 0, sizeof(f));
    f.npu.regmap = &f; f.npu.cores[0].buf = f.buffer; f.npu.cores[0].addr = 0x12340000;
    f.ctrl[0] = 0x12340000; f.ctrl[1] = 16; f.ctrl[2] = 41; f.ctrl[3] = ctrl3;
    memset(f.buffer, 0x91, sizeof(f.buffer));
    memset(f.data, 0x32, sizeof(f.data)); memset(f.reply, 0xcc, sizeof(f.reply));
    f.response = SUCCESS;
}
struct snapshot { u32 ctrl[4]; unsigned char buffer[AIROHA_NPU_MBOX_SIZE], reply[AIROHA_NPU_MBOX_SIZE]; };
static struct snapshot snapshot(void) {
    struct snapshot s; memcpy(s.ctrl, f.ctrl, sizeof(s.ctrl));
    memcpy(s.buffer, f.buffer, sizeof(s.buffer)); memcpy(s.reply, f.reply, sizeof(s.reply)); return s;
}
static bool unchanged(struct snapshot *s) {
    return !memcmp(s->ctrl, f.ctrl, sizeof(s->ctrl)) &&
           !memcmp(s->buffer, f.buffer, sizeof(s->buffer)) &&
           !memcmp(s->reply, f.reply, sizeof(s->reply));
}
'''

CASES = r'''
static bool normal(u32 previous, unsigned kind, unsigned len) {
    setup(previous);
    unsigned reply_len = kind == 0 ? (len < 4 ? len : 4) : len;
    void *reply = kind == 0 ? f.reply : kind == 1 ? f.data : NULL;
    int ret = __airoha_npu_send_msg(&f.npu, 5, f.data, len, reply, reply_len);
    CHECK(ret == 0, "normal_response_failed");
    CHECK(!f.npu.cores[0].lock && f.locks == 1 && f.unlocks == 1, "normal_lock_imbalance");
    CHECK(f.writes == 4 && f.polls == 1 && f.ctrl[2] == 42, "normal_publish_sequence_changed");
    CHECK(f.ctrl[0] == f.npu.cores[0].addr && f.ctrl[1] == len, "normal_address_or_length_changed");
    CHECK(FIELD_GET(MBOX_MSG_FUNC_ID, f.ctrl[3]) == 5, "normal_function_id_changed");
    for (unsigned i = 0; i < sizeof(f.buffer); i++) {
        CHECK(f.buffer[i] == (i < len ? answer(i, false) : 0x91), "buffer_tail_modified");
        unsigned char expected = kind == 0 && i < reply_len ? answer(len-reply_len+i, false) : 0xcc;
        CHECK(f.reply[i] == expected, "trailing_GET_reply_incorrect");
        expected = kind == 1 && i < len ? answer(i, false) : 0x32;
        CHECK(f.data[i] == expected, "SET_alias_or_no_reply_changed");
    }
    return true;
}
static bool busy(u32 ctrl3) {
    setup(ctrl3); struct snapshot s = snapshot();
    int ret = __airoha_npu_send_msg(&f.npu, 5, f.data, 16, f.reply, 4);
    CHECK(ret == -EBUSY, "busy_must_not_publish");
    CHECK(unchanged(&s) && !f.writes && !f.polls, "busy_changed_buffer_CTRL_SEQ_or_reply");
    CHECK(!f.npu.cores[0].lock && f.locks == 1 && f.unlocks == 1, "busy_lock_imbalance");
    return true;
}
static bool read_error(void) {
    setup(0); struct snapshot s = snapshot(); f.preflight_error = -EIO;
    int ret = __airoha_npu_send_msg(&f.npu, 5, f.data, 16, f.reply, 4);
    CHECK(ret == -EIO, "ctrl3_read_error_must_be_returned");
    CHECK(unchanged(&s) && !f.writes && !f.polls, "read_error_changed_request_state");
    CHECK(!f.npu.cores[0].lock && f.locks == 1 && f.unlocks == 1, "read_error_lock_imbalance");
    return true;
}
static bool failed_response(enum response response) {
    setup(0); f.response = response;
    int ret = __airoha_npu_send_msg(&f.npu, 5, f.data, 16, f.reply, 4);
    int expected = response == TIMEOUT ? -ETIMEDOUT : response == POLL_IO_ERROR ? -EIO : -EINVAL;
    CHECK(ret == expected, "existing_response_error_changed");
    CHECK(f.writes == 4 && f.ctrl[2] == 42, "error_request_not_published_once");
    for (unsigned i = 0; i < sizeof(f.reply); i++) CHECK(f.reply[i] == 0xcc, "failed_response_copied_reply");
    CHECK(!f.npu.cores[0].lock && f.locks == 1 && f.unlocks == 1, "failed_response_lock_imbalance");
    return true;
}
static bool invalid(bool oversize) {
    setup(0); struct snapshot s = snapshot();
    int len = oversize ? AIROHA_NPU_MBOX_SIZE + 1 : 16;
    int ret = __airoha_npu_send_msg(&f.npu, 5, f.data, len, f.reply, oversize ? 4 : 17);
    CHECK(ret == -EINVAL, "existing_input_rejection_changed");
    CHECK(unchanged(&s) && !f.writes && !f.polls && !f.locks && !f.unlocks, "invalid_input_touched_mailbox");
    return true;
}
static bool timeout_reuse(void) {
    setup(0); f.response = TIMEOUT;
    int ret = __airoha_npu_send_msg(&f.npu, 5, f.data, 16, f.reply, 4);
    CHECK(ret == -ETIMEDOUT && f.ctrl[2] == 42, "A_timeout_not_reproduced");
    struct snapshot a = snapshot();
    memset(f.data, 0x53, sizeof(f.data)); f.response = LATE_A;
    unsigned writes = f.writes, polls = f.polls;
    b_return = __airoha_npu_send_msg(&f.npu, 5, f.data, 16, f.reply, 4);
    late_a_accepted_as_b = b_return == 0 && f.reply[0] == answer(12, true);
    b_preserved = unchanged(&a) && f.writes == writes && f.polls == polls;
    CHECK(b_return == -EBUSY, "timeout_reuse_must_return_EBUSY");
    CHECK(b_preserved, "B_overwrote_timed_out_A");
    CHECK(!f.npu.cores[0].lock, "B_busy_left_lock_held");
    /* A completes while no host request is being published. */
    complete(true, NPU_MBOX_SUCCESS); f.response = SUCCESS;
    resumed_return = __airoha_npu_send_msg(&f.npu, 5, f.data, 16, f.reply, 4);
    CHECK(resumed_return == 0 && f.ctrl[2] == 43, "B_cannot_resume_after_A_done");
    for (unsigned i = 0; i < 4; i++) CHECK(f.reply[i] == answer(12+i, false), "B_received_A_reply_after_done");
    CHECK(!f.npu.cores[0].lock && f.locks == 3 && f.unlocks == 3, "reuse_lock_imbalance");
    return true;
}
static void report(const char *name, bool ok) {
    printf("%s{\"name\":\"%s\",\"pass\":%s,\"reason\":\"%s\"}",
           passed + failed ? "," : "", name, ok ? "true" : "false", ok ? "" : why);
    if (ok) passed++; else failed++;
}
int main(void) {
    char name[64]; u32 allowed[] = {0, MBOX_MSG_DONE, MBOX_MSG_WAIT_RSP | MBOX_MSG_DONE};
    unsigned funcs[] = {0, 1, 5, 15};
    printf("{\"cases\":[");
    for (unsigned i = 0; i < 3; i++) for (unsigned status = 0; status < 8; status++) for (unsigned kind = 0; kind < 3; kind++) {
        snprintf(name, sizeof(name), "normal_flags%u_status%u_kind%u", i, status, kind);
        report(name, normal(allowed[i] | FIELD_PREP(MBOX_MSG_STATUS, status), kind, 16));
    }
    report("normal_zero_length", normal(0, 0, 0));
    report("normal_max_length", normal(0, 1, AIROHA_NPU_MBOX_SIZE));
    for (unsigned i = 0; i < 4; i++) for (unsigned status = 0; status < 8; status++) for (unsigned sb = 0; sb < 2; sb++) {
        snprintf(name, sizeof(name), "busy_func%u_status%u_static%u", funcs[i], status, sb);
        report(name, busy(MBOX_MSG_WAIT_RSP | FIELD_PREP(MBOX_MSG_FUNC_ID, funcs[i]) |
                         FIELD_PREP(MBOX_MSG_STATUS, status) | (sb ? MBOX_MSG_STATIC_BUF : 0)));
    }
    report("ctrl3_read_error", read_error());
    report("response_error_status", failed_response(ERROR_STATUS));
    report("response_timeout", failed_response(TIMEOUT));
    report("response_poll_read_error", failed_response(POLL_IO_ERROR));
    report("oversize_payload", invalid(true)); report("reply_longer_than_request", invalid(false));
    report("timeout_A_then_B", timeout_reuse());
    printf("],\"passed\":%u,\"failed\":%u,\"timeout_observation\":{\"B_return\":%d,"
           "\"late_A_accepted_as_B\":%s,\"B_preserved_A_state\":%s,\"B_after_A_done_return\":%d}}\n",
           passed, failed, b_return, late_a_accepted_as_b ? "true" : "false",
           b_preserved ? "true" : "false", resumed_return);
    return failed ? 1 : 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--patch', type=Path, default=Path(__file__).resolve().parents[1] / 'target/linux/airoha/patches-6.18/9999-z4-net-airoha-npu-preserve-pending-mailbox.patch')
    args = parser.parse_args()
    text = args.source.read_text()
    names = ['AIROHA_NPU_MBOX_SIZE', 'NPU_MBOX_BASE_ADDR', 'REG_CR_MBQ0_CTRL',
             'MBOX_MSG_FUNC_ID', 'MBOX_MSG_STATIC_BUF', 'MBOX_MSG_STATUS', 'MBOX_MSG_DONE', 'MBOX_MSG_WAIT_RSP']
    defines = []
    for name in names:
        match = re.search(r'^#define ' + name + r'(?=\s|\().*$', text, re.M)
        assert match, name
        defines.append(match[0])
    assert re.search(r'enum\s*{\s*NPU_MBOX_ERROR,\s*NPU_MBOX_SUCCESS,\s*}', text)
    clang = shutil.which('clang')
    assert clang, 'clang is required; no installation attempted'
    versions = subprocess.run([clang, '--version'], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    results = {}
    with tempfile.TemporaryDirectory(prefix='npu-mailbox-') as tmp:
        root = Path(tmp)
        original, modified, already_applied = variants(text, args.patch, root)
        for label, body in [('baseline', original), ('candidate', modified)]:
            src, exe = root / (label + '.c'), root / label
            src.write_text(STUBS.replace('ACTUAL_DEFINES', '\n'.join(defines)) + body + CASES)
            command = [clang, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                       '-fsanitize=address,undefined', '-fno-sanitize-recover=all', str(src), '-o', str(exe)]
            build = subprocess.run(command, text=True, capture_output=True)
            assert build.returncode == 0, build.stderr
            env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
            run = subprocess.run([str(exe)], text=True, capture_output=True, env=env)
            assert run.returncode in (0, 1) and not run.stderr, (label, run.returncode, run.stderr)
            result = json.loads(run.stdout)
            failures = [x for x in result['cases'] if not x['pass']]
            if label == 'candidate':
                assert run.returncode == 0 and not failures, failures
            else:
                expected = {x['name']: 'busy_must_not_publish' for x in failures if x['name'].startswith('busy_')}
                assert len(expected) == 64
                expected.update(ctrl3_read_error='ctrl3_read_error_must_be_returned',
                                timeout_A_then_B='timeout_reuse_must_return_EBUSY')
                assert {x['name']: x['reason'] for x in failures} == expected, failures
                assert result['timeout_observation']['late_A_accepted_as_B'] is True
            result['exit_code'] = run.returncode
            result['function_sha256'] = hashlib.sha256(body.encode()).hexdigest()
            results[label] = result
    print(json.dumps({'source': str(args.source),
                      'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
                      'product_patch_sha256': hashlib.sha256(args.patch.read_bytes()).hexdigest(),
                      'source_already_applied': already_applied,
                      'product_patch_fuzz': 0, 'whole_source_patch_round_trip_equal': True,
                      'compiler': versions, 'sanitizers': ['address', 'undefined'],
                      'actual_definitions': defines, 'production_modified': False,
                      'candidate_scope': 'CTRL3 read and WAIT_RSP&&!DONE guard after lock; shared unlock label only',
                      'results': results,
                      'limitations': [
                          'One explicitly ordered device model; not firmware execution, hardware DMA, IRQ concurrency or elapsed timeout modeling.',
                          'The model assumes WAIT_RSP&&!DONE remains observable for unfinished work and DONE marks completion; firmware contract is not proved.',
                          'Busy return is not cancellation or recovery; permanently unfinished commands can leave subsequent requests EBUSY.',
                          'Existing CTRL0..3 write errors, CTRL2 read errors, sequence wrap, negative lengths, lifecycle/reset interleavings and barriers are not changed or verified.',
                          'No Air stall attribution or real device repair is established.'
                      ]}, indent=2))


if __name__ == '__main__':
    main()
