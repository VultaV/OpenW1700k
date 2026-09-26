#!/usr/bin/env python3
"""Offline RED payload/error regression using actual extracted mt7996 functions.

--source-dir accepts a mt76 root containing mt7996/mcu.{c,h}, or mt7996 itself.
Use --expect-baseline for the specifically missing three-message contract.
Optional --patch checks a fuzz/offset-free apply/reverse round trip in a temp dir.
Only this host test's temporary files are written; no device/network operations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def require(value, message):
    if not value:
        raise ValueError(message)


def function(source, name):
    match = re.search(r'^(?:static )?int\s+' + re.escape(name) + r'\(', source, re.M)
    require(match, 'missing function: ' + name)
    opening = source.index('{', match.start())
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end] + '\n'


def enums(header, names):
    blocks = re.findall(r'enum(?:\s+\w+)?\s*\{[^}]*\};', header)
    chosen = []
    for name in names:
        matches = [block for block in blocks if re.search(r'\b' + name + r'\b', block)]
        require(len(matches) == 1, 'missing/ambiguous enum: ' + name)
        if matches[0] not in chosen:
            chosen.append(matches[0])
    return '\n'.join(chosen)


STUBS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint16_t __le16;
typedef uint32_t __le32;
#define __packed __attribute__((packed))
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error This fixture targets the actual little-endian AArch64 payload layout.
#endif
#define cpu_to_le16(v) ((u16)(v))
#define cpu_to_le32(v) ((u32)(v))
/* Transport command identities and unrelated init operations are host stubs.
 * They distinguish actual call sites; no full MCU transport header is tested. */
#define MCU_WM_UNI_CMD(x) (0x10000 + HOST_WM_##x)
#define MCU_WA_PARAM_CMD(x) (0x20000 + MCU_WA_PARAM_CMD_##x)
#define MCU_WA_UNI_CMD(x) (0x30000 + HOST_WA_##x)
#define HOST_WM_VOW 0x37
#define HOST_WA_SDO 0x82
#define MT7996_TOKEN_SIZE 16384
#define MT_SWDEF_MODE 1
#define MT_SWDEF_NORMAL_MODE 0
#define MT76_STATE_MCU_RUNNING 0
#define MCU_FW_LOG_WM 0
#define MCU_FW_LOG_WA 1
struct mt76_dev { bool chip7996, npu; unsigned token_size; void *dev; };
struct mt7996_dev { struct mt76_dev mt76; bool hif2, has_wa; struct { unsigned long state; } mphy; };
struct message { int command, length; bool wait; unsigned char data[700]; };
static struct message messages[4];
static int count, fail_send, error_code, logs, pre_count, fail_pre;
static unsigned passed, expected_missing;
static bool is_mt7996(struct mt76_dev *dev) { return dev->chip7996; }
static bool mt76_npu_device_active(struct mt76_dev *dev) { return dev->npu; }
static bool mt7996_has_wa(struct mt7996_dev *dev) { return dev->has_wa; }
static void mt76_wr(struct mt7996_dev *d, int reg, int val) {
    (void)d; assert(reg == MT_SWDEF_MODE && val == MT_SWDEF_NORMAL_MODE);
}
static int prepare_step(void) { return ++pre_count == fail_pre ? error_code : 0; }
static int mt7996_driver_own(struct mt7996_dev *d, int band) {
    (void)d; assert(band == 0 || band == 1); return prepare_step();
}
static int mt7996_load_firmware(struct mt7996_dev *d) { (void)d; return prepare_step(); }
static void set_bit(int bit, unsigned long *value) { *value |= 1UL << bit; }
static int mt7996_mcu_fw_log_2_host(struct mt7996_dev *d, int who, int value) {
    (void)d; assert((who == MCU_FW_LOG_WM || who == MCU_FW_LOG_WA) && value == 0);
    return prepare_step();
}
static int mt7996_mcu_set_mwds(struct mt7996_dev *d, int value) {
    (void)d; assert(value == 1); return prepare_step();
}
static int mt7996_mcu_init_rx_airtime(struct mt7996_dev *d) { (void)d; return prepare_step(); }
#define dev_info(...) do { logs++; } while (0)
static int mt76_mcu_send_msg(struct mt76_dev *d, int command,
                           const void *bytes, int length, bool wait) {
    (void)d; assert(count < 4 && length > 0 && length <= 700);
    struct message *m = &messages[count++];
    m->command = command; m->length = length; m->wait = wait;
    memcpy(m->data, bytes, (size_t)length);
    return count == fail_send ? error_code : 0;
}
'''


CASES = r'''
static struct mt7996_dev setup(bool chip, bool npu, bool wa, unsigned tokens) {
    memset(messages, 0xa5, sizeof(messages));
    count = fail_send = error_code = logs = pre_count = fail_pre = 0;
    return (struct mt7996_dev){ .mt76 = { .chip7996 = chip, .npu = npu, .token_size = tokens },
                               .has_wa = wa, .hif2 = true };
}
/* Independent byte-offset oracle: no candidate structs/constants encode expected bytes. */
static void le16(unsigned char *p, unsigned v) { p[0] = v & 255; p[1] = (v >> 8) & 255; }
static void expect_message(int index, int command, bool wait, const unsigned char *bytes, int len) {
    assert(index < count);
    assert(messages[index].command == command && messages[index].wait == wait);
    assert(messages[index].length == len && !memcmp(messages[index].data, bytes, (size_t)len));
}
static void contract_prefix(unsigned tokens, int sent) {
    unsigned char wm[12] = {0}, enable[12] = {0}, config[644] = {0};
    wm[4] = 0x18; wm[6] = 8; wm[8] = 2;
    enable[0] = 0x0e; enable[4] = 1;
    config[0] = 0x40; config[12] = 2;
    le16(config + 18, 632); le16(config + 20, 200); le16(config + 22, 255);
    for (int i = 0; i < 4; i++) {
        le16(config + 24 + i * 2, i == 3 ? tokens : 16384);
        le16(config + 32 + i * 2, 16384);
    }
    /* Full memcmp checks all reserved bytes, body length and packet order. */
    if (sent >= 1) expect_message(0, 0x10037, true, wm, sizeof(wm));
    if (sent >= 2) expect_message(1, 0x20001, false, enable, sizeof(enable));
    if (sent >= 3) expect_message(2, 0x20001, false, config, sizeof(config));
}
static void legacy_packet(bool has_wa) {
    unsigned char expected[20] = {0};
    if (has_wa) {
        expected[0] = 0x0e;
        expect_message(0, 0x20001, false, expected, 12);
    } else {
        expected[4] = 1; expected[6] = 16; expected[8] = 0x0e;
        expect_message(0, 0x30082, false, expected, 20);
    }
}
int main(void) {
    const int errors[] = {-ENOMEM, -EIO, -ETIMEDOUT, 7};
#if HAS_RED_HELPER
    const unsigned budgets[] = {0, 1, 0x1234, 8192, 16384, 65535};
    for (unsigned i = 0; i < sizeof(budgets)/sizeof(budgets[0]); i++) {
        struct mt7996_dev d = setup(true, true, true, budgets[i]);
        assert(mt7996_mcu_init_firmware(&d) == 0);
        assert(count == 3 && logs == 1 && pre_count == 7);
        contract_prefix(budgets[i], 3); passed++;
    }
    for (int stage = 1; stage <= 3; stage++) {
        for (unsigned i = 0; i < sizeof(errors)/sizeof(errors[0]); i++) {
            struct mt7996_dev d = setup(true, true, true, 0x1234);
            fail_send = stage; error_code = errors[i];
            assert(mt7996_mcu_init_firmware(&d) == errors[i]);
            assert(count == stage && logs == 0);
            contract_prefix(0x1234, stage); passed++;
        }
    }
#else
    /* Specific baseline phenotype, not an arbitrary build/assertion failure. */
    struct mt7996_dev baseline = setup(true, true, true, 16384);
    assert(mt7996_mcu_init_firmware(&baseline) == 0);
    assert(count == 1 && logs == 0 && pre_count == 7);
    legacy_packet(true);
    expected_missing++;
#endif
    const bool selectors[][3] = {{true,false,true}, {false,true,true}, {false,false,true},
                                 {false,true,false}, {false,false,false}};
    for (unsigned s = 0; s < sizeof(selectors)/sizeof(selectors[0]); s++) {
        for (unsigned e = 0; e <= sizeof(errors)/sizeof(errors[0]); e++) {
            struct mt7996_dev d = setup(selectors[s][0], selectors[s][1], selectors[s][2], 0x1234);
            if (e) { fail_send = 1; error_code = errors[e-1]; }
            assert(mt7996_mcu_init_firmware(&d) == error_code);
            assert(count == 1 && logs == 0);
            legacy_packet(selectors[s][2]); passed++;
        }
    }
    /* Earlier initialization failure must not enqueue any RED operation. */
    for (int stage = 1; stage <= 7; stage++) {
        struct mt7996_dev d = setup(true, true, true, 16384);
        fail_pre = stage; error_code = -EIO;
        assert(mt7996_mcu_init_firmware(&d) == -EIO);
        assert(pre_count == stage && count == 0 && logs == 0); passed++;
    }
    printf("{\"passed\":%u,\"expected_missing_contract\":%u}\n", passed, expected_missing);
    return 0;
}
'''


def patch_roundtrip(patch, inputs, candidate, root):
    tree = root / 'roundtrip'
    (tree / 'mt7996').mkdir(parents=True)
    for name, raw in inputs.items():
        (tree / 'mt7996' / name).write_bytes(raw)
    base = ['patch', '-p1', '--batch', '--fuzz=0', '-i', str(patch.resolve())]
    for reverse in (candidate, not candidate):
        result = subprocess.run(base + (['--reverse'] if reverse else ['--forward']),
                                cwd=tree, capture_output=True, text=True, check=True)
        require(not re.search(r'offset|fuzz', result.stdout + result.stderr, re.I),
                'patch needed offset/fuzz')
    require(all((tree / 'mt7996' / name).read_bytes() == raw for name, raw in inputs.items()),
            'patch round trip changed source bytes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--expect-baseline', action='store_true')
    parser.add_argument('--patch', type=Path)
    parser.add_argument('--cc', default=os.environ.get('CC', 'clang'))
    args = parser.parse_args()
    source_dir = args.source_dir / 'mt7996' if (args.source_dir / 'mt7996').is_dir() else args.source_dir
    inputs = {name: (source_dir / name).read_bytes() for name in ('mcu.c', 'mcu.h')}
    source, header = (inputs[name].decode() for name in ('mcu.c', 'mcu.h'))
    present = bool(re.search(r'^static int mt7996_mcu_init_npu_red\(', source, re.M))
    require(present != args.expect_baseline, 'source does not match candidate/baseline expectation')
    names = ['mt7996_mcu_wa_cmd']
    symbols = ['MCU_WA_PARAM_RED', 'MCU_WA_PARAM_CMD_SET', 'UNI_CMD_SDO_SET']
    endian_checks = []
    if present:
        names.append('mt7996_mcu_init_npu_red')
        symbols += ['UNI_VOW_RED_ENABLE', 'MCU_WA_PARAM_RED_CONFIG']
        helper = function(source, names[-1])
        patterns = [r'\.tag\s*=\s*cpu_to_le16\(UNI_VOW_RED_ENABLE\)',
                    r'\.args\s*=\s*\{\s*cpu_to_le32\(MCU_WA_PARAM_RED_CONFIG\)',
                    r'\.len\s*=\s*cpu_to_le16\(sizeof\(wm\)\s*-\s*4\)',
                    r'\.len\s*=\s*cpu_to_le16\(sizeof\(wa\)\s*-\s*sizeof\(wa.args\)\)',
                    r'\.tcp_offset\s*=\s*cpu_to_le16\(200\)',
                    r'\.priority_offset\s*=\s*cpu_to_le16\(255\)',
                    r'wa.token_per_src\[i\]\s*=\s*cpu_to_le16\(MT7996_TOKEN_SIZE\)',
                    r'wa.token_thr_per_src\[i\]\s*=\s*cpu_to_le16\(MT7996_TOKEN_SIZE\)',
                    r'wa.token_per_src\[RED_TOKEN_SRC_CNT - 1\]\s*=\s*cpu_to_le16\(dev->mt76.token_size\)']
        for pattern in patterns:
            require(re.search(pattern, helper), 'missing explicit little-endian conversion: ' + pattern)
        endian_checks = patterns
    names.append('mt7996_mcu_init_firmware')
    extracted = {name: function(source, name) for name in names}
    code = STUBS + enums(header, symbols) + '\n' + '\n'.join(extracted.values()) + CASES
    cc = shutil.which(args.cc)
    require(cc, 'compiler not found')
    flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
             '-Wno-unused-function', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
             '-DHAS_RED_HELPER=' + str(int(present))]
    with tempfile.TemporaryDirectory(prefix='mt7996-red-test-') as tmp:
        root = Path(tmp)
        if args.patch:
            patch_roundtrip(args.patch, inputs, present, root)
        c_file, binary = root / 'test.c', root / 'test'
        c_file.write_text(code)
        subprocess.run([cc, *flags, str(c_file), '-o', str(binary)], check=True, capture_output=True, text=True)
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
        result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, env=env)
        require(not result.stderr.strip(), 'unexpected runtime/sanitizer stderr')
        counts = json.loads(result.stdout)
    require(counts == ({'passed': 50, 'expected_missing_contract': 0} if present else
                       {'passed': 32, 'expected_missing_contract': 1}), 'unexpected case counts')
    print(json.dumps({'status': 'PASS' if present else 'EXPECTED_MISSING_CONTRACT', **counts,
        'source_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in inputs.items()},
        'extracted_sha256': {name: hashlib.sha256(text.encode()).hexdigest() for name, text in extracted.items()},
        'explicit_endian_source_checks': len(endian_checks),
        'compiler': Path(cc).name, 'compiler_flags': flags,
        'patch_roundtrip_fuzz0_no_offset': bool(args.patch),
        'limitations': ['Actual helper, WA wrapper and full firmware-init function; unrelated operations and MCU transport are stubs.',
                        'Native little-endian host payload oracle plus explicit endian conversion checks; no big-endian runtime.',
                        'MT7996_TOKEN_SIZE=16384 is the contract fixture; no full kernel ABI or MCU envelope compilation.',
                        'ASan/UBSan are host checks; no firmware execution, RED readback, token ownership or throughput claim.',
                        'Zero and boundary token values test encoding only, not valid firmware budgets.']}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stderr or error.stdout or str(error), file=sys.stderr)
        raise SystemExit(1)
