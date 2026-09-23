# NPU investigation, as of 2026-09-23

The actual MT7996 NPU program/data in the installed build matched the checked official linux-firmware distribution. This dated observation does not describe future releases.

| File | Bytes | SHA256 |
|---|---:|---|
| en7581_MT7996_npu_rv32.bin | 122336 | e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643 |
| en7581_MT7996_npu_data.bin | 3084 | 61a75afb052feed2ceb2f3023e16f50317c05c78f9c8e564bf01924ce39c7ec1 |

Program string: TLB7.7.0.0_v03. RV32/compressed instructions were decoded at loader base 0x84000000 and diagnostic string references traced. The raw binary lacks original symbols; labels are inferred from behavior. Linear decoding is not proof that every byte is executable code.

- At 0x8400eac4–0x8400eb0e, next-descriptor readiness waiting has no outer timeout; readiness or a shared flag can exit it. A nearby current-descriptor loop is bounded. A stalled producer could block progress, but normal backpressure can also enter this path.
- TX-done calls the replacement-buffer allocator at 0x8400b100. Failure branches through 0x8400b424 to an exit before token-return calls at 0x8400b308/0x8400b342. Resource shortage could delay token return; this does not prove permanent deadlock.

[airoha-npu-fdk at 2d13e29](https://github.com/hurryman2212/airoha-npu-fdk/tree/2d13e291ab511b6b319dc5073f47e26cac958ae4) contains actual reverse-engineered C datapaths, not merely headers. It is not original vendor source or byte-identical replacement firmware; its data-image format differs. Another reconstruction, [ClankerNPU at 0f660e1](https://github.com/ClankerConstruction/ClankerNPU/tree/0f660e133c21374079439ba55093c01589568d11), has incomplete fast paths and different allocation ordering. Neither was deployed.

Live PC samples confirmed CPU-fed Wi-Fi descriptor processing and later fast-TX activity with bridge offload. The unbounded wait was not captured as the cause of an Air stall. Linux CPU0–3 and the NPU's eight harts are separate execution contexts; an NPU wait is not direct evidence for Linux CPU saturation.

The inherited r29 RX refill ownership-order fix concerns the host/NPU boundary, not these firmware paths. r30/r31 therefore retain the official NPU binary. Bridge OFF/ON throughput/CPU evidence and bounded Air acceptance support the acceleration repair; no hypothetical firmware timeout patch was added.

Private local disassembly, string references, PC samples and original logs are retained. Recurrence needs contemporaneous descriptor/ring/token and NPU-PC evidence before attributing a stall to these paths.
