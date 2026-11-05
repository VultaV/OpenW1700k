# Exact NPU0.8 HOST RX contract review

The original125832-byte programSHA256 is7068a987bb95e89129a69de10d598f234a4400023eb23aacc8eb377e5f0fe0ea. The four-byte r69 candidate is not used. Selected original raw bytes were checked against the retained native instruction listing;512-index arithmetic and source register mappings were checked independently. This is static analysis, not an execution/interrupt trace.

## What the native software producer actually checks

The24-byte HOST RX producer at firmware code-view0x8400ff92 reads P from0x1ec0d188/198. It checks descriptor.ctrl bit0 at `(P+2)%512` (sites0x8401000a–10032 and0x840100b0–100d8). If available, its builderFBE2 uses VDMAchannel3 to copy payload, publishes descriptor data/info followed by DONE, and posts `(P+1)%512` to188/198. A busy guard path can return-1 after writingP-1 thenP to the producer CSR without advancing it. Three identified direct callers use this producer.

In that identified software path, **consumer CSR0x1ec0d18c/19c is not read to decide whether the next descriptor may be used**. Source mapping independently connects the driver's NPU RXdma_idx writes to those CSR addresses. The reported native guard is a descriptor-DONE lookahead of2, not the50-case host observer's assumed `nextP==limit` hardware limit condition. The24B HOST RX ring must not be confused with the32B FE/TDMA input ring or16B MT7996 output ring discussed in earlier reviews.

## What this does and does not establish for r71

r71's actual-C host cases verify ordering under the proposed upstream next-index/one-reserved-slot interface contract. They are **not a native0.8 firmware equivalence or safety proof**. Hardware credit/IRQ behavior and indirect CSR use outside the identified software path remain unknown. The native result does not prove the driver change is ineffective either: software can omit a register read while hardware still uses that register. Do not convert these code-view/register addresses into guessed writes or claim that all DMA ownership is proved.

The upstream PR1169 source fix delays ring publication until after replacement buffers are posted. With a fully refilled ring `(head+1)%ndesc` equals softwaretail; partial/zero-refill behavior and actual hardware compatibility need field checks. Existing descriptor-field ordering/whole-chain fixes are retained. The precise cause of r70's per-peerTXfreeze, weak-memory behavior, initial total allocation failure progress and producer quiescence remain unproved.

The image's exact stock firmware, changedmt76core, unchangedkernel/DTB and relevant kernelmodules were separately checked. Boot/readback/traffic/idle results are version-specific device evidence; they must not be inferred from this static report or its host models.
