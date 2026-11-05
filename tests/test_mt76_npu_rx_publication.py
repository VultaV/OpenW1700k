#!/usr/bin/env python3
"""Exercise actual refill/dequeue ordering with an immediate NPU observer.

The observer uses PR1169's next-index/one-reserved-slot contract. It does
not execute firmware or reproduce real DMA timing.
"""
import ast
from pathlib import Path
import subprocess
import sys
import tempfile

fixture = ast.parse(Path(__file__).with_name('test_mt76_npu_rx.py').read_text())
constants = {n.targets[0].id: ast.literal_eval(n.value) for n in fixture.body
             if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
             and isinstance(n.value.value, str)}
prefix = constants['NPU_STUB'] + constants['REFILL_CASES'].replace(
    'refill_pages[4]', 'refill_pages[8]')
observer = r'''
static bool ready[8];
static int producer, doorbells, consumed, invalid_dma;
static void publish(struct mt76_queue *q, int value) {
 q->dma_idx=value; doorbells++;
 for(int i=0; i<q->ndesc && (producer+1)%q->ndesc!=value; i++) {
  if(!ready[producer]) { invalid_dma++; break; }
  ready[producer]=false; consumed++; producer=(producer+1)%q->ndesc;
 }
}
#undef Q_WRITE
#define Q_WRITE(q, reg, value) publish(q,value)
#undef WRITE_ONCE
#define WRITE_ONCE(v, value) do { (v)=(value); observe_publication(); \
 ready[observed_queue->head]=true; } while(0)
'''
cases = r'''
#undef memset
static void reset(struct mt76_queue *q) {
 observed_queue=q; supplied=published=barriers=bad_publications=0;
 doorbells=consumed=invalid_dma=0;
 memset(ready,0,sizeof(ready)); memset(refill_pages,0,sizeof(refill_pages));
 for(int i=0;i<8;i++)refill_pages[i].dma=4096+256*i;
}
int main(void) {
 int checks=0;
 for(int n=4;n<=8;n+=4) {
  /* Initial refill, including no buffers and partial allocation. */
  for(int supply=0;supply<n;supply++) {
   struct airoha_npu_rx_dma_desc desc[8];
   struct mt76_queue_entry e[8]={0};
   struct mt76_queue q={.desc=desc,.entry=e,.ndesc=n,.buf_size=64,.dma_idx=1};
   struct mt76_dev dev={0};
   memset(desc,0xff,sizeof(desc));reset(&q);producer=0;supply_limit=supply;
   assert(mt76_npu_fill_rx_queue(&dev,&q)==supply);
   assert(doorbells==1 && !invalid_dma && !bad_publications);
   assert(consumed==supply && q.dma_idx==(q.head+1)%n);
   checks++;
  }
  for(int tail=0;tail<n;tail+=n-1)
  for(int count=1;count<=3;count++)
  for(int supply=0;supply<=count;supply++) {
   struct page old_pages[8]={0};
   struct airoha_npu_rx_dma_desc desc[8]={0};
   struct mt76_queue_entry e[8]={0};
   struct mt76_queue q={.desc=desc,.entry=e,.ndesc=n,.buf_size=64,
                       .tail=tail,.head=(tail+n-1)%n,.queued=n-1,.dma_idx=tail};
   struct mt76_dev dev={0};u32 info=0;
   for(int i=0;i<n;i++) { e[i].buf=old_pages[i].data;desc[i].ctrl=21; }
   desc[tail].info=(u32)count<<29;
   reset(&q);producer=q.head;supply_limit=supply;
   struct sk_buff *skb=mt76_npu_dequeue(&dev,&q,&info);
   assert(skb && q.queued==n-1-count);
   /* A doorbell here would expose the unfilled old guard slot. */
   assert(!doorbells && !invalid_dma && q.dma_idx==tail);
   assert(mt76_npu_fill_rx_queue(&dev,&q)==supply);
   assert(doorbells==1 && !invalid_dma && !bad_publications);
   assert(consumed==supply && q.dma_idx==(q.head+1)%n);
   dev_kfree_skb(skb);checks++;
  }
  /* A full ring's zero-refill call must not expose its guard. */
  struct airoha_npu_rx_dma_desc desc[8]={0};
  struct mt76_queue_entry e[8]={0};
  struct mt76_queue q={.desc=desc,.entry=e,.ndesc=n,.head=n-1,.queued=n-1};
  struct mt76_dev dev={0};reset(&q);producer=q.head;supply_limit=0;
  assert(mt76_npu_fill_rx_queue(&dev,&q)==0);
  assert(doorbells==1 && !invalid_dma && !consumed && q.dma_idx==0);checks++;
 }
 printf("PASS: %d actual RX publication cases; consume/refill, wrap, partial/zero allocation, reserved slot\n",checks);
}
'''
source = Path(sys.argv[1]).read_text()
fill = source[source.index('int mt76_npu_fill_rx_queue('):source.index('\nvoid mt76_npu_queue_cleanup(')]
dequeue = source[source.index('static struct sk_buff *mt76_npu_dequeue('):source.index('\nvoid mt76_npu_check_ppe(')]
with tempfile.TemporaryDirectory(prefix='npu-rx-publication-') as directory:
    p = Path(directory)
    (p/'check.c').write_text(prefix + observer + fill + dequeue + cases)
    subprocess.run(['cc','-std=gnu11','-O1','-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all',str(p/'check.c'),'-o',str(p/'check')],check=True)
    subprocess.run([str(p/'check')],check=True)
print('Scope: host observer contract only; firmware ownership, DMA timing and OOM progress not proved.')
