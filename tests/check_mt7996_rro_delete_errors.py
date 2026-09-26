#!/usr/bin/env python3
"""Reproduce ignored RRO delete errors in actual prepared driver functions.

Offline only. PASS means the specified current error loss was reproduced,
not that RRO cleanup is correct. Reuses the existing bounded mailbox model.
No firmware execution, real DMA, concurrent queues or device fault injection.
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

import test_airoha_npu_mailbox as mailbox
from test_airoha_npu_watchdog import function as static_function
from test_mt7996_npu_red import function, enums


def define(source, name):
    match = re.search(r'^#define ' + re.escape(name) + r'(?=\s|\().*$', source, re.M)
    assert match, name
    result = match[0]
    for line in source[match.end():].splitlines()[1:]:
        if not result.endswith('\\'):
            break
        result += '\n' + line
    return result


STUBS = r'''
#include <stddef.h>
#include <stdlib.h>
typedef uint32_t __le32;
typedef uint16_t __le16;
#define __packed __attribute__((packed))
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error The payload check requires the actual little-endian target layout.
#endif
#define cpu_to_le32(v) ((u32)(v))
#define cpu_to_le16(v) ((u16)(v))
#define GFP_ATOMIC 1
#define DECLARE_FLEX_ARRAY(type, name) type name[]
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
/* Single-thread list fixture; scheduling/concurrent enqueue is not modeled. */
struct list_head { struct list_head *next, *prev; };
#define LIST_HEAD(name) struct list_head name = { &name, &name }
static void init_list(struct list_head *h) { h->next = h->prev = h; }
static bool list_empty(struct list_head *h) { return h->next == h; }
static void list_del_init(struct list_head *e) {
    e->prev->next = e->next; e->next->prev = e->prev; init_list(e);
}
static void list_splice_init(struct list_head *from, struct list_head *to) {
    if (list_empty(from)) return;
    from->next->prev = to; from->prev->next = to->next;
    to->next->prev = from->prev; to->next = from->next; init_list(from);
}
#define list_first_entry(h, t, m) container_of((h)->next, t, m)
struct work_struct { int unused; };
struct mt76_dev { bool chip7996; struct { struct airoha_npu *npu; } mmio; };
struct mt7996_dev {
    struct mt76_dev mt76;
    struct {
        struct work_struct work; int lock; struct list_head poll_list;
        struct { void *ptr; } session, addr_elem[MT7996_RRO_ADDR_ELEM_LEN];
    } wed_rro;
};
static struct mt7996_dev dev;
static unsigned event_frees, request_frees, allocations, submitted, wm_calls, rcu_depth;
static int npu_return, wm_return;
static bool allocation_failure;
static void *event_ptr, *request_ptr;
static char order[8];
static void step(char c) { size_t n = strlen(order); assert(n + 1 < sizeof(order)); order[n] = c; }
static void *kzalloc(size_t size, gfp_t gfp) {
    assert(gfp == GFP_ATOMIC && !request_ptr); allocations++;
    if (allocation_failure) return NULL;
    request_ptr = calloc(1, size); assert(request_ptr); return request_ptr;
}
static void kfree(void *p) {
    assert(p);
    if (p == event_ptr) { event_frees++; event_ptr = NULL; step('F'); }
    else { assert(p == request_ptr); request_frees++; request_ptr = NULL; }
    free(p);
}
static void rcu_read_lock(void) { assert(!rcu_depth); rcu_depth++; }
static void rcu_read_unlock(void) { assert(rcu_depth == 1); rcu_depth--; }
#define rcu_dereference(p) (p)
static bool mt76_npu_device_active(struct mt76_dev *d) { return d->mmio.npu != NULL; }
static bool is_mt7996(struct mt76_dev *d) { return d->chip7996; }
/* Only command transport identity is reduced, as in the existing RED test. */
#define MCU_WM_UNI_CMD(x) HOST_WM_##x
#define HOST_WM_RRO 0x57
static int mt76_mcu_send_msg(struct mt76_dev *d, int cmd, const void *p, int len, bool wait) {
    const unsigned char *b = p;
    assert(d == &dev.mt76 && cmd == HOST_WM_RRO && wait && len == 14);
    unsigned char expected[14] = {0};
    expected[4] = UNI_RRO_DEL_BA_SESSION; expected[6] = 10; expected[8] = 7;
    assert(!memcmp(b, expected, sizeof(expected)));
    wm_calls++; step('W'); return wm_return;
}
'''

CASES = r'''
static void record_submit(void) {
    struct wlan_mbox_data *w = (void *)f.buffer;
    u32 *payload = (void *)w->d;
    assert(f.ctrl[1] == sizeof(*w) + 16);
    assert(FIELD_GET(MBOX_MSG_FUNC_ID, f.ctrl[3]) == NPU_FUNC_WIFI);
    assert(w->ifindex == 3 && w->func_type == NPU_OP_SET);
    assert(w->func_id == WLAN_FUNC_SET_WAIT_INODE_TXRX_REG_ADDR);
    assert(payload[0] == 7 && !payload[1] && !payload[2] && !payload[3]);
    submitted++;
}
static int observed_ops(struct airoha_npu *n, int i, enum airoha_npu_wlan_set_cmd c,
                        void *p, int len, gfp_t gfp) {
    npu_return = airoha_npu_wlan_msg_send(n, i, c, p, len, gfp);
    step('N'); return npu_return;
}
static void trial(const char *name, bool no_memory, bool busy, int wm_error) {
    setup(busy ? MBOX_MSG_WAIT_RSP : 0);
    memset(&dev, 0, sizeof(dev)); memset(order, 0, sizeof(order));
    event_frees = request_frees = allocations = submitted = wm_calls = rcu_depth = 0;
    allocation_failure = no_memory; wm_return = wm_error; npu_return = -999;
    dev.mt76.chip7996 = true; dev.mt76.mmio.npu = &f.npu;
    f.npu.ops.wlan_send_msg = observed_ops;
    init_list(&dev.wed_rro.poll_list);
    struct mt7996_wed_rro_session_id *e = calloc(1, sizeof(*e)); assert(e);
    e->id = 7; event_ptr = e;
    e->list.next = e->list.prev = &dev.wed_rro.poll_list;
    dev.wed_rro.poll_list.next = dev.wed_rro.poll_list.prev = &e->list;
    /* Host event lifetime is distinct from persistent RRO descriptor storage. */
    u32 descriptor_sentinel = 0xaabbccdd;
    dev.wed_rro.session.ptr = &descriptor_sentinel;
    for (unsigned i = 0; i < ARRAY_SIZE(dev.wed_rro.addr_elem); i++)
        dev.wed_rro.addr_elem[i].ptr = &descriptor_sentinel;
    struct snapshot before = snapshot();
    mt7996_wed_rro_work(&dev.wed_rro.work);
    int expected = no_memory ? -ENOMEM : busy ? -EBUSY : 0;
    assert(npu_return == expected && wm_calls == 1 && event_frees == 1);
    assert(!strcmp(order, "NWF") && allocations == 1);
    assert(request_frees == (unsigned)!no_memory && !event_ptr && !request_ptr);
    assert(!dev.wed_rro.lock && !f.npu.cores[0].lock && !rcu_depth);
    assert(list_empty(&dev.wed_rro.poll_list) && descriptor_sentinel == 0xaabbccdd);
    assert(submitted == (unsigned)(!no_memory && !busy));
    if (no_memory || busy) assert(!f.writes && !f.polls && unchanged(&before));
    else assert(f.writes == 4 && f.polls == 1);
    printf("{\"name\":\"%s\",\"npu_return\":%d,\"submitted\":%u,"
           "\"mailbox_writes\":%u,\"wm_calls\":%u,\"wm_return\":%d,"
           "\"event_frees\":%u,\"request_frees\":%u,\"order\":\"%s\","
           "\"descriptor_unchanged\":true,\"observation_verified\":true}",
           name, npu_return, submitted, f.writes, wm_calls, wm_return,
           event_frees, request_frees, order);
}
int main(void) {
    printf("["); trial("success", false, false, 0);
    printf(","); trial("request_allocation_ENOMEM", true, false, 0);
    printf(","); trial("pending_mailbox_EBUSY", false, true, 0);
    printf(","); trial("WM_positive_status", false, false, 1);
    printf(","); trial("WM_transport_ENOMEM", false, false, -ENOMEM);
    printf("]\n"); return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mt76', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    args = parser.parse_args()
    sources = {name: (args.mt76 / name).read_text() for name in
               ['npu.c', 'airoha_offload.h', 'mt7996/init.c', 'mt7996/mcu.c', 'mt7996/mcu.h', 'mt7996/mt7996.h']}
    sources['airoha_npu.c'] = (args.kernel / 'drivers/net/ethernet/airoha/airoha_npu.c').read_text()
    npu, header = sources['airoha_npu.c'], sources['mt7996/mt7996.h']
    actual = {}
    for name in ['__airoha_npu_send_msg', 'airoha_npu_send_msg', 'airoha_npu_wlan_msg_send']:
        actual[name] = function(npu, name)
    actual['airoha_npu_wlan_send_msg'] = static_function(sources['airoha_offload.h'], 'airoha_npu_wlan_send_msg')
    actual['mt76_npu_send_txrx_addr'] = function(sources['npu.c'], 'mt76_npu_send_txrx_addr')
    actual['mt7996_mcu_wed_rro_reset_sessions'] = function(sources['mt7996/mcu.c'], 'mt7996_mcu_wed_rro_reset_sessions')
    actual['mt7996_wed_rro_work'] = static_function(sources['mt7996/init.c'], 'mt7996_wed_rro_work')
    assert 'npu->ops.wlan_send_msg = airoha_npu_wlan_msg_send;' in npu
    event = static_function(sources['mt7996/mcu.c'], 'mt7996_mcu_wed_rro_event')
    delete = event.split('case UNI_WED_RRO_BA_SESSION_DELETE:')[1].split('default:')[0]
    for token in ['list_add_tail(', 'le16_to_cpu(e->session_id)', 'ieee80211_queue_work(', '&dev->wed_rro.work']:
        assert token in delete, token
    names = ['AIROHA_NPU_MBOX_SIZE', 'NPU_MBOX_BASE_ADDR', 'REG_CR_MBQ0_CTRL', 'MBOX_MSG_FUNC_ID',
             'MBOX_MSG_STATIC_BUF', 'MBOX_MSG_STATUS', 'MBOX_MSG_DONE', 'MBOX_MSG_WAIT_RSP']
    base = mailbox.STUBS.replace('ACTUAL_DEFINES', '\n'.join(define(npu, x) for x in names))
    extra = 'typedef uint8_t u8;\ntypedef int gfp_t;\n' + enums(sources['airoha_offload.h'], ['WLAN_FUNC_SET_WAIT_INODE_TXRX_REG_ADDR'])
    base = base.replace('#define BIT(n)', extra + '\n#define BIT(n)', 1)
    base = base.replace('struct airoha_npu { void *regmap;', '''struct airoha_npu { struct {
        int (*wlan_send_msg)(struct airoha_npu *, int, enum airoha_npu_wlan_set_cmd, void *, int, gfp_t);
    } ops; void *regmap;''', 1)
    base = base.replace('static int poll_once(', 'static void record_submit(void);\nstatic int poll_once(', 1)
    base = base.replace('    f.polls++;', '    f.polls++; record_submit();', 1)
    constants = '\n'.join(define(header, x) for x in ['MT7996_RRO_MAX_SESSION', 'MT7996_RRO_WINDOW_MAX_LEN',
        'MT7996_RRO_ADDR_ELEM_LEN', 'MT7996_RRO_BA_BITMAP_SESSION_SIZE', 'WED_RRO_ADDR_SIGNATURE_MASK'])
    constants += '\n' + enums(npu, ['NPU_FUNC_WIFI', 'NPU_OP_SET'])
    constants += '\n' + enums(sources['mt7996/mcu.h'], ['UNI_RRO_DEL_BA_SESSION'])
    structs = []
    for text, name in [(npu, 'wlan_mbox_data'), (header, 'mt7996_wed_rro_addr'), (header, 'mt7996_wed_rro_session_id')]:
        structs.append(re.search(r'^struct ' + name + r' \{.*?^};', text, re.M | re.S)[0])
    code = base + constants + STUBS + '\n'.join(structs) + '\n'.join(actual.values()) + CASES
    clang = shutil.which('clang'); assert clang
    with tempfile.TemporaryDirectory(prefix='rro-delete-') as temp:
        root = Path(temp); src, exe = root / 'check.c', root / 'check'
        src.write_text(code)
        build = subprocess.run([clang, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                                '-Wno-unused-function', '-Wno-unused-variable', '-fsanitize=address,undefined',
                                '-fno-sanitize-recover=all', str(src), '-o', str(exe)], text=True, capture_output=True)
        assert build.returncode == 0, build.stderr
        run = subprocess.run([str(exe)], text=True, capture_output=True,
                             env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'))
        assert run.returncode == 0 and not run.stderr, (run.returncode, run.stderr)
        cases = json.loads(run.stdout)
    print(json.dumps({
        'scope': 'Current ignored-error behavior reproduced, not a product correctness pass or runtime failure attribution',
        'cases': cases, 'verified_observations': len(cases), 'failed_checks': 0,
        'actual_functions_sha256': {n: hashlib.sha256(t.encode()).hexdigest() for n, t in actual.items()},
        'source_sha256': {n: hashlib.sha256(t.encode()).hexdigest() for n, t in sources.items()},
        'fixture_sha256': hashlib.sha256(code.encode()).hexdigest(),
        'compiler': subprocess.check_output([clang, '--version'], text=True).splitlines()[0],
        'sanitizers': ['address', 'undefined'], 'production_modified': False,
        'limits': ['Event parser reachability is source-checked, not executed.',
                   'Mailbox/WM device responses and list/RCU scheduling are bounded host models.',
                   'Neither firmware session reuse nor DMA completion, error incidence or wireless stalls are proved.',
                   'The event is freed; persistent DMA descriptor storage is not freed by this path.',
                   'No proposed retry/guard patch is tested or deployed.']}, indent=2))


if __name__ == '__main__':
    main()
