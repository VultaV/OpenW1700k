#!/usr/bin/env python3
"""Compile real NPU probe/remove/IRQ paths and the kernel's devm work helper.

Usage: python3 tests/test_airoha_npu_watchdog.py PATH_TO_PREPARED_KERNEL
Applies/reverses the backport only in a temporary copy. Fake devres/IRQs check
initialization, reverse release order and every probe failure boundary. This
does not model actual IRQ concurrency, firmware behavior or device throughput.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def function(source, name):
    match = re.search(r'^static (?:inline )?(?:int|void|irqreturn_t)\s+' + name + r'\(', source, re.M)
    assert match, name
    start = source.index('{', match.start())
    end, depth = start + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end] + '\n'


STUBS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef int irqreturn_t;
struct work_struct { bool initialized, pending; };
typedef void (*work_func_t)(struct work_struct *);
struct device { void *of_node; };
struct platform_device { struct device dev; void *data; };
struct resource { unsigned long start; };
struct airoha_npu;
struct airoha_npu_core {
    struct airoha_npu *npu;
    struct work_struct wdt_work;
    int lock;
    bool irq_active;
    void *buf;
    unsigned long addr;
};
struct airoha_npu {
    struct device *dev;
    void *regmap;
    struct airoha_npu_core cores[8];
    int irqs[4];
    struct { OPS_FIELDS } ops;
};
#define __iomem
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define GFP_KERNEL 0
#define IRQF_SHARED 0
#define IRQ_HANDLED 1
#define NPU_NUM_CORES 8
#define AIROHA_NPU_MBOX_SIZE 32
#define NPU_EN7581_FIRMWARE_RV32_MAX_SIZE 0
#define WLAN_FUNC_GET_WAIT_NPU_VERSION 0
#define WDT_INTR_MASK 1
#define WDT_EN_MASK 1
#define FIELD_GET(mask, value) ((mask) & (value))
#define REG_WDT_TIMER_CTRL(i) (i)
#define REG_CR_NPU_MIB(i) (i)
#define REG_CR_BOOT_BASE(i) (i)
#define REG_CR_BOOT_CONFIG 0
#define REG_CR_BOOT_TRIGGER 0
#define DMA_BIT_MASK(n) 0xffffffffUL
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define dev_info(...) ((void)0)
#define msleep(...) ((void)0)
#define usleep_range(...) ((void)0)
#define spin_lock_init(p) (*(p) = 0)
static int fail_at, steps, resources, immediate_irq, frees, cancels;
static struct airoha_npu *allocated;
static struct { void (*drop)(void *); void *arg; } stack[64];
static int fail(void) { return ++steps == fail_at; }
static void push(void (*drop)(void *), void *arg) {
    assert(resources < 64); stack[resources].drop = drop;
    stack[resources++].arg = arg;
}
static void schedule_work(struct work_struct *w) {
    assert(w->initialized); w->pending = true;
}
static void init_work(struct work_struct *w, work_func_t fn) { w->initialized = true; }
#define INIT_WORK(w, fn) init_work(w, fn)
static void cancel_work_sync(void *p) {
    struct work_struct *w = p;
    struct airoha_npu_core *c = (void *)((char *)w - offsetof(struct airoha_npu_core, wdt_work));
    assert(w->initialized && !c->irq_active);
    w->pending = false; cancels++;
}
static int devm_add_action(struct device *d, void (*fn)(void *), void *p) {
    if (fail()) return -ENOMEM;
    push(fn, p); return 0;
}
static void free_npu(void *p) {
    struct airoha_npu *n = p;
    for (unsigned i = 0; i < ARRAY_SIZE(n->cores); i++)
        assert(!n->cores[i].irq_active && !n->cores[i].wdt_work.pending);
    free(p); allocated = NULL; frees++;
}
static void *devm_kzalloc(struct device *d, size_t n, int flags) {
    if (fail()) return NULL;
    allocated = calloc(1, n); assert(allocated);
    push(free_npu, allocated); return allocated;
}
static void *devm_platform_ioremap_resource(struct platform_device *p, int i) {
    return fail() ? (void *)(intptr_t)-ENOMEM : (void *)1;
}
static int regmap_config;
static void *devm_regmap_init_mmio(struct device *d, void *b, void *cfg) {
    return fail() ? (void *)(intptr_t)-ENOMEM : (void *)1;
}
static int of_reserved_mem_region_to_resource(void *node, int i, struct resource *r) {
    return fail() ? -ENOENT : 0;
}
static int platform_get_irq(struct platform_device *p, int i) { return fail() ? -ENXIO : i; }
static void platform_set_drvdata(struct platform_device *p, void *data) { p->data = data; }
static void *platform_get_drvdata(struct platform_device *p) { return p->data; }
static int regmap_read(void *r, int off, u32 *val) { *val = WDT_EN_MASK; return 0; }
static void regmap_write(void *r, int off, unsigned long val) {}
static void regmap_set_bits(void *r, int off, u32 val) {}
static int airoha_npu_mbox_handler(int irq, void *arg) { return IRQ_HANDLED; }
static void airoha_npu_wdt_work(struct work_struct *w) {}
static int airoha_npu_wdt_handler(int irq, void *arg);
static void drop_irq(void *arg) {
    struct airoha_npu_core *c = arg;
    /* Last IRQ before free_irq synchronizes; cancellation must follow it. */
    airoha_npu_wdt_handler(0, c); c->irq_active = false;
}
static int devm_request_irq(struct device *d, int irq,
                            irqreturn_t (*handler)(int, void *), int flags,
                            const char *name, void *arg) {
    if (fail()) return -EBUSY;
    if (handler == airoha_npu_wdt_handler) {
        struct airoha_npu_core *c = arg;
        c->irq_active = true; push(drop_irq, c);
        if (immediate_irq) handler(irq, arg);
    }
    return 0;
}
static int dma_set_coherent_mask(struct device *d, unsigned long mask) { return fail() ? -EIO : 0; }
#define dma_set_mask_and_coherent dma_set_coherent_mask
static void *dmam_alloc_coherent(struct device *d, int size, void *addr, int flags) {
    return fail() ? NULL : (void *)1;
}
static int airoha_npu_run_firmware(struct device *d, void *b, struct resource *r) {
    return fail() ? -EIO : 0;
}
static int airoha_npu_wlan_msg_get(struct airoha_npu *n, int a, int b, u32 *val, int size, int flags) {
    *val = 0; return 0;
}
'''

CASES = r'''
static int run(int failure) {
    struct platform_device p = {};
    steps = resources = frees = cancels = 0; fail_at = failure;
    int ret = airoha_npu_probe(&p);
    int reached = steps;
    assert(failure ? ret < 0 : ret == 0);
    if (!ret) { REMOVE_CALL }
    while (resources) {
        resources--; stack[resources].drop(stack[resources].arg);
    }
    assert(!allocated);
    if (!failure) assert(cancels == 8 && frees == 1);
    return reached;
}
int main(int argc, char **argv) {
    immediate_irq = atoi(argv[1]);
    int total = run(0);
    for (int i = 1; i <= total; i++) run(i);
    printf("PASS immediate_irq=%d: success + %d probe failure boundaries\n", immediate_irq, total);
    return 0;
}
'''


def harness(source, helpers):
    probe = function(source, 'airoha_npu_probe')
    ops = re.findall(r'npu->ops\.(\w+) = (\w+);', probe)
    stubs = STUBS.replace('OPS_FIELDS', '\n'.join('void *' + field + ';' for field, _ in ops))
    # These assignments are unrelated to watchdog lifetime; preserve the probe itself.
    defines = ''.join('#define ' + name + ' NULL\n' for _, name in ops
                      if name != 'airoha_npu_wlan_msg_get')
    remove = function(source, 'airoha_npu_remove') if '.remove = airoha_npu_remove,' in source else ''
    return (stubs + defines + function(helpers, 'devm_work_drop')
            + function(helpers, 'devm_work_autocancel')
            + function(source, 'airoha_npu_wdt_handler') + probe + remove
            + CASES.replace('REMOVE_CALL', 'airoha_npu_remove(&p);' if remove else ''))


def main():
    kernel = Path(sys.argv[1]).resolve()
    relative = Path('drivers/net/ethernet/airoha/airoha_npu.c')
    source = (kernel / relative).read_text()
    helpers = (kernel / 'include/linux/devm-helpers.h').read_text()
    patch = Path(__file__).resolve().parents[1] / 'target/linux/airoha/patches-6.18/9999-z3-net-airoha-npu-fix-watchdog-work-lifetime.patch'
    with tempfile.TemporaryDirectory(prefix='airoha-wdt-') as tmp:
        root = Path(tmp)
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_text(source)
        already_fixed = 'devm_work_autocancel(dev, &core->wdt_work,' in source
        direction = ['-R'] if already_fixed else []
        command = ['patch', '-p1', '--batch', '--fuzz=0', *direction, '-i', str(patch)]
        subprocess.run(command + ['--dry-run'], cwd=root, check=True, capture_output=True)
        subprocess.run(command, cwd=root, check=True, capture_output=True)
        before, after = (path.read_text(), source) if already_fixed else (source, path.read_text())
        for label, text in [('before', before), ('after', after)]:
            c = root / (label + '.c')
            c.write_text(harness(text, helpers))
            binary = root / label
            subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-fsanitize=address,undefined',
                            '-Werror=implicit-function-declaration', str(c), '-o', str(binary)], check=True)
            for immediate in (0, 1):
                result = subprocess.run([str(binary), str(immediate)], cwd=root,
                                        capture_output=True, text=True)
                if label == 'before':
                    assert result.returncode != 0, 'unfixed lifecycle unexpectedly passed'
                    expected = '(w->initialized)' if immediate else '(w->initialized && !c->irq_active)'
                    assert 'Assertion' in result.stderr and expected in result.stderr, result.stderr
                    print(f'EXPECTED FAIL before immediate_irq={immediate}')
                else:
                    assert result.returncode == 0, result.stderr
                    print(result.stdout.strip())
    print('PASS patch applicability, kernel helper compatibility and both negative controls')


if __name__ == '__main__':
    main()
