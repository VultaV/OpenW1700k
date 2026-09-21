#!/usr/bin/env python3
"""Compile the exact pinned mt76 RX functions against ownership fixtures.

Usage: python3 tests/test_mt76_npu_rx.py --source-dir PATH_TO_MT76_01367e60
Requires a C compiler and patch; no router, kernel build or network access.
This proves the conditional code defects, not their incidence on hardware.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-dir', type=Path, required=True)
args = parser.parse_args()
patches = Path(__file__).resolve().parents[1] / 'package/kernel/mt76/patches'


def extract(source, start, end):
    return source[source.index(start):source.index(end, source.index(start))]


NPU_STUB = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
#define FIELD_GET(mask, v) (((v) & (mask)) >> __builtin_ctz(mask))
#define NPU_RX_DMA_PKT_COUNT_MASK 0xe0000000u
#define NPU_RX_DMA_DESC_CUR_LEN_MASK 0x7ffeu
#define NPU_RX_DMA_DESC_DONE_MASK 1u
#define max_t(type, a, b) ((type)(a) > (type)(b) ? (a) : (b))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define Q_WRITE(q, reg, value) ((q)->reg = (value))
#define READ_ONCE(v) (*(volatile __typeof__(v) *)&(v))
#define dma_rmb() __asm__ __volatile__("" ::: "memory")
#define dma_sync_single_for_cpu(...) ((void)0)
#define page_pool_get_dma_dir(...) 0
struct page { bool recycled; u32 dma; unsigned char data[64]; };
struct skb_shared_info { int nr_frags; struct page *frags[17]; };
struct sk_buff {
    struct page *head;
    struct skb_shared_info shinfo;
    bool recycle;
    int len;
};
struct airoha_npu_rx_dma_desc { u32 ctrl, info, data, addr; uint64_t rsv; };
struct mt76_queue_entry { void *buf; int dma_addr[1], dma_len[1]; };
struct mt76_queue {
    void *desc;
    struct mt76_queue_entry *entry;
    int tail, head, ndesc, queued, buf_size, dma_idx;
    void *page_pool;
};
struct mt76_dev { void *dma_dev; };
static int recycled_page_reuses, allocations, fail_allocation;
static struct page *virt_to_head_page(void *buf) {
    return (void *)((char *)buf - offsetof(struct page, data));
}
static void *page_address(struct page *page) { return page->data; }
static struct sk_buff *napi_build_skb(void *buf, int size) {
    allocations++;
    if (fail_allocation) return NULL;
    struct page *page = virt_to_head_page(buf);
    if (page->recycled) recycled_page_reuses++;
    struct sk_buff *skb = calloc(1, sizeof(*skb));
    skb->head = page;
    return skb;
}
static void __skb_put(struct sk_buff *skb, int len) { skb->len += len; }
static void skb_reset_mac_header(struct sk_buff *skb) {}
static void skb_mark_for_recycle(struct sk_buff *skb) { skb->recycle = true; }
static struct skb_shared_info *skb_shinfo(struct sk_buff *skb) { return &skb->shinfo; }
static void skb_add_rx_frag(struct sk_buff *skb, int n, struct page *page,
                            int offset, int len, int size) {
    skb->shinfo.frags[n] = page;
    skb->shinfo.nr_frags++;
    skb->len += len;
}
static void dev_kfree_skb(struct sk_buff *skb) {
    if (!skb) return;
    if (skb->recycle) skb->head->recycled = true;
    for (int i = 0; i < skb->shinfo.nr_frags; i++)
        skb->shinfo.frags[i]->recycled = true;
    free(skb);
}
'''
NPU_CASES = r'''
int main(void) {
    struct page pages[4] = {0};
    struct airoha_npu_rx_dma_desc desc[4] = {0};
    struct mt76_queue_entry entries[4] = {0};
    for (int i = 0; i < 4; i++) entries[i].buf = pages[i].data;
    struct mt76_queue q = {
        .desc = desc, .entry = entries, .ndesc = 4,
        .tail = 3, .queued = 3, .buf_size = 64
    };
    struct mt76_dev dev = {0};
    u32 info = 0;
    /* The chain wraps around the ring; the second descriptor is pending. */
    desc[3].ctrl = 21; desc[3].info = 2u << 29; desc[0].ctrl = 20;
    assert(mt76_npu_dequeue(&dev, &q, &info) == NULL);
    assert(q.tail == 3 && q.queued == 3);
    if (pages[3].recycled) {
        desc[0].ctrl |= 1;
        struct sk_buff *skb = mt76_npu_dequeue(&dev, &q, &info);
        assert(skb && recycled_page_reuses == 1);
        dev_kfree_skb(skb);
        puts("baseline: retry consumed a recycled ring buffer");
        return 1;
    }
    assert(allocations == 0);
    desc[0].ctrl |= 1;
    /* Failure to allocate the head must also preserve the entire ring. */
    fail_allocation = 1;
    assert(mt76_npu_dequeue(&dev, &q, &info) == NULL);
    assert(q.tail == 3 && q.queued == 3 && !pages[3].recycled);
    fail_allocation = 0;
    struct sk_buff *skb = mt76_npu_dequeue(&dev, &q, &info);
    assert(skb && skb->len == 20 && skb->shinfo.nr_frags == 1);
    assert(q.tail == 1 && q.queued == 1 && q.dma_idx == 1);
    assert(recycled_page_reuses == 0);
    dev_kfree_skb(skb);
    /* A count exceeding the posted descriptors must not consume anything. */
    desc[1].ctrl = 21; desc[1].info = 2u << 29;
    int old_allocations = allocations;
    assert(mt76_npu_dequeue(&dev, &q, &info) == NULL);
    assert(q.tail == 1 && q.queued == 1 && allocations == old_allocations);
    /* Zero count means one descriptor, as in the original driver. */
    desc[1].info = 0;
    skb = mt76_npu_dequeue(&dev, &q, &info);
    assert(skb && skb->len == 10 && q.tail == 2 && q.queued == 0);
    dev_kfree_skb(skb);
    desc[2].ctrl = 21;
    old_allocations = allocations;
    assert(mt76_npu_dequeue(&dev, &q, &info) == NULL);
    assert(allocations == old_allocations);
    puts("patched: partial chain, wrap, allocation failure, count bound and empty ring pass");
    return 0;
}
'''

# Model an NPU observation at descriptor publication, not real DMA timing.
REFILL_CASES = r'''
#define SKB_WITH_OVERHEAD(size) (size)
static struct page refill_pages[4];
static int supplied, supply_limit, published, barriers, bad_publications;
static struct mt76_queue *observed_queue;
static void *mt76_get_page_pool_buf(struct mt76_queue *q, int *off, int size) {
    if (supplied == supply_limit) return NULL;
    *off = 8;
    return refill_pages[supplied++].data;
}
static u32 page_pool_get_dma_addr(struct page *p) { return p->dma; }
static void observe_publication(void) {
    struct mt76_queue *q = observed_queue;
    struct airoha_npu_rx_dma_desc *d = q->desc;
    if (!(d[q->head].ctrl & NPU_RX_DMA_DESC_DONE_MASK)) {
        published++;
        if (d[q->head].addr != (u32)q->entry[q->head].dma_addr[0] ||
            d[q->head].info || d[q->head].data || d[q->head].rsv ||
            barriers != published)
            bad_publications++;
    }
}
static void *observed_memset(void *p, int c, size_t n) {
    void *result = memset(p, c, n);
    observe_publication();
    return result;
}
static void publication_barrier(void) {
    struct mt76_queue *q = observed_queue;
    struct airoha_npu_rx_dma_desc *d = q->desc;
    assert(d[q->head].ctrl & NPU_RX_DMA_DESC_DONE_MASK);
    assert(d[q->head].addr == (u32)q->entry[q->head].dma_addr[0]);
    barriers++;
}
#define memset observed_memset
#define dma_wmb() publication_barrier()
#define WRITE_ONCE(v, value) do { (v) = (value); observe_publication(); } while (0)
'''

REFILL_MAIN = r'''
#undef memset
int main(void) {
    struct airoha_npu_rx_dma_desc desc[4];
    struct mt76_queue_entry entries[4] = {0};
    struct mt76_queue q = {
        .desc = desc, .entry = entries, .ndesc = 4,
        .head = 3, .queued = 0, .buf_size = 64
    };
    struct mt76_dev dev = {0};
    observed_queue = &q;
    memset(desc, 0xff, sizeof(desc));
    for (int i = 0; i < 4; i++) refill_pages[i].dma = 4096 + 256 * i;
    /* Wrap while refilling, then stop before touching an unavailable page. */
    supply_limit = 2;
    assert(mt76_npu_fill_rx_queue(&dev, &q) == 2);
    assert(q.head == 1 && q.queued == 2 && published == 2);
    assert(desc[1].ctrl == UINT32_MAX && desc[1].addr == UINT32_MAX);
    if (bad_publications) {
        puts("baseline: NPU can observe ownership before the replacement address");
        return 1;
    }
    supply_limit = 4;
    assert(mt76_npu_fill_rx_queue(&dev, &q) == 1);
    assert(q.head == 2 && q.queued == 3 && published == 3 && barriers == 3);
    assert(mt76_npu_fill_rx_queue(&dev, &q) == 0);
    assert(supplied == 3 && desc[2].ctrl == UINT32_MAX);
    assert(!bad_publications);
    puts("patched: ordered ownership, wrap, allocation failure and reserved slot pass");
    return 0;
}
'''

RX_STUB = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef uint32_t __le32;
#define container_of(p, type, field) ((type *)((char *)(p) - offsetof(type, field)))
#define unlikely(v) (v)
#define le32_get_bits(v, mask) (((v) & (mask)) >> __builtin_ctz(mask))
#define MT_RXD0_PKT_TYPE 0xfu
#define MT_RXD0_SW_PKT_TYPE_MASK 0xff00u
#define MT_RXD0_SW_PKT_TYPE_MAP 0xffu
#define MT_RXD0_SW_PKT_TYPE_FRAME 0x80u
#define MT_TXS_HDR_SIZE 2
#define MT_TXS_SIZE 2
#define fallthrough __attribute__((fallthrough))
enum mt76_rxq_id { MT_RXQ_NPU0, MT_RXQ_TXFREE_BAND2 };
enum rx_pkt_type { PKT_TYPE_TXRX_NOTIFY, PKT_TYPE_NORMAL, PKT_TYPE_RX_EVENT,
                   PKT_TYPE_TXS, PKT_TYPE_RX_FW_MONITOR };
struct mt76_dev { struct { int wed_hif2; } mmio; };
struct mt7996_dev { struct mt76_dev mt76; };
struct sk_buff { unsigned char *data; int len, headlen; unsigned char fragment[8]; };
static int linearizations, fail_linearize, delivered, discarded, parsed;
static int mtk_wed_device_active(void *p) { return 0; }
static int skb_linearize(struct sk_buff *skb) {
    if (skb->headlen == skb->len) return 0;
    linearizations++;
    if (fail_linearize) return -1;
    unsigned char *data = malloc(skb->len);
    memcpy(data, skb->data, skb->headlen);
    memcpy(data + skb->headlen, skb->fragment, skb->len - skb->headlen);
    free(skb->data);
    skb->data = data;
    skb->headlen = skb->len;
    return 0;
}
static void dev_kfree_skb(struct sk_buff *skb) { discarded++; }
static void napi_consume_skb(struct sk_buff *skb, int n) { discarded++; }
static void check_report(void *data, int len) {
    uint32_t word;
    memcpy(&word, (char *)data + len - 4, 4);
    parsed = word == 0x12345678u;
}
static void mt7996_mac_tx_free(struct mt7996_dev *dev, void *data, int len) {
    check_report(data, len);
}
static void mt7996_mcu_rx_event(struct mt7996_dev *dev, struct sk_buff *skb) {
    check_report(skb->data, skb->len);
}
static void mt7996_mac_add_txs(struct mt7996_dev *dev, void *data) {
    check_report(data, 8);
}
static void mt7996_debugfs_rx_fw_monitor(struct mt7996_dev *dev, void *data, int len) {
    check_report(data, len);
}
static int mt7996_mac_fill_rx(struct mt7996_dev *dev, enum mt76_rxq_id q,
                            struct sk_buff *skb, u32 *info) { return 0; }
static void mt76_rx(struct mt76_dev *dev, enum mt76_rxq_id q, struct sk_buff *skb) {
    delivered++;
}
'''
RX_CASES = r'''
static struct sk_buff make_skb(enum rx_pkt_type type) {
    struct sk_buff skb = {.data = malloc(16), .len = 16, .headlen = 8};
    memset(skb.data, 0xcc, 16);
    memset(skb.fragment, 0, 8);
    u32 value = type, last = 0x12345678u;
    memcpy(skb.data, &value, 4);
    memcpy(skb.fragment + 4, &last, 4);
    return skb;
}
int main(void) {
    struct mt7996_dev dev = {0};
    u32 info = 0;
    enum rx_pkt_type controls[] = {PKT_TYPE_TXRX_NOTIFY, PKT_TYPE_TXS,
                                   PKT_TYPE_RX_EVENT, PKT_TYPE_RX_FW_MONITOR};
    for (int i = 0; i < 4; i++) {
        struct sk_buff skb = make_skb(controls[i]);
        parsed = 0;
        mt7996_queue_rx_skb(&dev.mt76, MT_RXQ_NPU0, &skb, &info);
        free(skb.data);
        if (!parsed) {
            puts("baseline: TXFREE parsed head padding instead of the fragment");
            return 1;
        }
    }
    int old_linearizations = linearizations;
    struct sk_buff skb = make_skb(PKT_TYPE_NORMAL);
    mt7996_queue_rx_skb(&dev.mt76, MT_RXQ_NPU0, &skb, &info);
    assert(delivered == 1 && linearizations == old_linearizations && skb.headlen == 8);
    free(skb.data);
    skb = make_skb(PKT_TYPE_TXRX_NOTIFY);
    fail_linearize = 1; parsed = 0;
    int old_discarded = discarded;
    mt7996_queue_rx_skb(&dev.mt76, MT_RXQ_NPU0, &skb, &info);
    assert(!parsed && discarded == old_discarded + 1);
    free(skb.data);
    puts("patched: fragmented controls, refreshed pointers, normal zero-copy and allocation failure pass");
    return 0;
}
'''


def compile_and_run(directory, name, content, expected):
    c = directory / (name + '.c')
    binary = directory / name
    c.write_text(content)
    subprocess.run(['cc', '-std=gnu11', '-O2', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', str(c), '-o', str(binary)], check=True)
    result = subprocess.run([str(binary)])
    assert result.returncode == expected, (name, result.returncode, expected)


with tempfile.TemporaryDirectory(prefix='mt76-npu-rx-test-') as tmp:
    temp = Path(tmp)
    (temp / 'mt7996').mkdir()
    for name in ('npu.c', 'mt7996/mac.c'):
        (temp / name).write_text((args.source_dir / name).read_text())
    for patched in (False, True):
        if patched:
            for patch in ('0006-wifi-mt76-npu-preserve-incomplete-rx-chain.patch',
                          '0029-wifi-mt76-npu-publish-rx-buffer-before-ownership.patch'):
                subprocess.run(['patch', '-s', '-F', '0', '-p1', '-i', str(patches / patch)],
                               cwd=temp, check=True)
        label = 'patched' if patched else 'baseline'
        refill = extract((temp / 'npu.c').read_text(),
                         'int mt76_npu_fill_rx_queue(',
                         '\nvoid mt76_npu_queue_cleanup(')
        compile_and_run(temp, label + '_refill',
                        NPU_STUB + REFILL_CASES + refill + REFILL_MAIN,
                        0 if patched else 1)
        if patched:
            compile_and_run(temp, 'missing_barrier_refill', NPU_STUB + REFILL_CASES +
                            refill.replace('dma_wmb();', '') + REFILL_MAIN, 1)
        function = extract((temp / 'npu.c').read_text(),
                           'static struct sk_buff *mt76_npu_dequeue(',
                           '\nvoid mt76_npu_check_ppe(')
        compile_and_run(temp, label + '_dequeue', NPU_STUB + function + NPU_CASES,
                        0 if patched else 1)
        function = extract((temp / 'mt7996/mac.c').read_text(),
                           'void mt7996_queue_rx_skb(',
                           '\nstatic struct mt7996_msdu_page *')
        compile_and_run(temp, label + '_control', RX_STUB + function + RX_CASES,
                        0 if patched else 1)
print('Three exact-source regressions reproduced before the patches and passed after them.')
