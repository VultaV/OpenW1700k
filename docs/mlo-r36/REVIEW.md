# r36: 호스트 TX 게시 순서 및 실제 NPU 펌웨어 경계 검토

2026-09-26. r35 공개 소스와 기존 vendor NPU 바이너리·저장 로그를 추가 검토했다. **장비 접속·설치·재부팅·새 무선 시험은 하지 않았다.** r36은 호스트의 확인된 게시 순서만 고친다. Air의 간헐 멈춤 원인이나 해결을 확정하지 않는다.

## 이번에 수정한 호스트 결함

`mt76_dma_tx_queue_skb()`는 TX 준비 후 NPU 큐일 때 공통 `mt76_npu_dma_add_buf()`로 들어간다. 이 함수는 coherent descriptor에 TXWI와 DMA 주소를 쓴 다음 DONE을 설정한다. 기존 소스에는 데이터와 DONE 사이의 메모리 barrier가 없다. 뒤의 `mt76_dma_kick_queue()`가 `wmb()` 후 CPU index를 쓰더라도 이미 공개한 DONE을 보호하지 못한다.

이는 실제 vendor consumer의 순서로 확인했다. program SHA256은 `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`, 크기 122336 bytes, load base는 `0x84000000`이다.

| 실제 PC | 동작 |
|---|---|
| `0x8400f6b6 / 0x8400f772` | 각 host TX ring의 descriptor control을 읽고 bit0 DONE 검사 |
| `0x8400f6cc / 0x8400f788` | 준비된 descriptor를 `0x8400f0c4`로 전달 |
| `0x8400f178 / 0x8400f182 / 0x8400f198` | 주소 offset4를 읽고 TXWI offset16의 76 bytes를 복사하는 함수 호출 |
| `0x8400f6a8 / 0x8400f766` | 처리 index를 MMIO에 기록; 소비 시작을 gate하는 CPU index 읽기가 아님 |

[0034](../../package/kernel/mt76/patches/0034-wifi-mt76-npu-order-tx-descriptor-publication.patch)는 TXWI와 주소 뒤에 `dma_wmb()`를 두고 `WRITE_ONCE()`로 DONE을 공개한다. descriptor 레이아웃·길이·token·ring accounting·메타데이터를 바꾸지 않는다. 208-byte stride와 control offset0의 정렬도 유지된다. 앞선 streaming TXWI 동기화나 queue lock은 이후 coherent descriptor로 복사한 필드의 게시 순서를 대신하지 않는다.

coherent DMA에도 store ordering이 필요하다는 [Linux DMA 문서](https://docs.kernel.org/core-api/dma-api-howto.html)와 payload를 ownership 전에 게시하는 [DMA barrier 계약](https://docs.kernel.org/core-api/wrappers/memory-barriers.html)을 따른다. `dma_wmb()`는 이 호스트 게시 경계의 보완이며 NPU 내부 DMA·consumer의 모든 순서를 보장하는 수정이 아니다.

실제 함수를 추출한 TX 8사례는 길이 0/64/192/224, head 0/3, wrap, 길이 clamp와 미사용 suffix, metadata와 다른 descriptor 보존을 검사한다. 수정 전 8사례와 barrier 제거 대조군 8사례가 의도대로 실패한다. 기존 RX 3그룹도 유지한다. host fixture와 ASan/UBSan 검사이며 실제 약한 메모리 순서의 발생률·kernel ABI·firmware 반응 시험이 아니다. 가속 bulk traffic은 호스트의 매 패킷 송신을 우회하므로 **이 결함만으로 기존 Air 멈춤 전체를 설명하지 않는다.**

## 실제 NPU 바이너리의 추가 발견

| 항목 | 확인한 동작 | 미확정 범위·조치 |
|---|---|---|
| TX budget 경계 | 여유 descriptor가 정확히 7일 때 fast worker에 budget0이 전달된다. 진입 0 검사가 없어 성공 처리 뒤 32-bit 감소가 `0xffffffff`로 되감긴다. | 정상 128개 budget 한도가 깨지는 경계 오류. 다른 exit 조건은 남으며 영구 교착·Air 원인·발생률은 미확정. 바이너리 수정 없음. |
| next-descriptor 대기·stop | 실제 slow/fast stop 분기는 안전 취소 대신 READY 성공 경로로 합류한다. 현재 descriptor의 1000회 제한 종료도 계속 진행한다. | 단순 timeout·분기 변경은 token 회수·RX 소유권·부분 batch 게시를 손상시킬 수 있어 적용하지 않음. |
| 교체 버퍼 고갈 | 교체 packet buffer P와 TX token T는 다른 풀이다. TXdone 이전 P 할당 실패는 completion을 지연시킨다. | 독립 P 반환 IRQ·packet consumer가 있어 P 부족만으로 영구 교착을 입증하지 못함. T 반환 순서 변경으로 P 부족을 직접 해결할 수 없음. |
| buffer reset | action6은 MMIO index와 FIFO drain을 시간 제한 없이 기다린 뒤 P를 초기화한다. | 호스트 약500ms mailbox timeout은 firmware 명령 취소나 NPU 재시작이 아님. 자동 복구 성공 보장 없음. |

[NPU_TX_BUDGET.md](NPU_TX_BUDGET.md)와 [NPU_COMPLETION_POOLS.md](NPU_COMPLETION_POOLS.md)에 실제 PC·바이트·caller·모델과 재실행 방법을 기록한다. FDK와 Clanker는 재구현이며 vendor 원본 소스가 아니다. FDK의 `free>7` guard와 안전 취소를 실제 blob에 있는 것으로 대입하지 않는다. 선택 바이트 일치와 제한 산술 모델은 전체 CFG·firmware 실행·메모리 소유권·공정성 증명이 아니다. 새 blob이나 검증하지 않은 binary patch는 포함하지 않았다.

## 기존 Air 기록 재검토

[AIR_EVIDENCE.md](AIR_EVIDENCE.md)는 r32 MLO 멈춤, single6 속도 저하, PS 로그 ON 정상 회차를 구분한다. 상세 상태는 약5초의 수집 공백이 있고 한 표본도 0.62–0.81초에 걸친 순차 읽기다. 집계 최저 구간과 사용자가 본 멈춤의 정확한 시각은 일치가 입증되지 않았다. 다른 peer의 짧은 제어 트래픽이나 느린 표본 사이 TXS 증가로 멈춤 순간의 NPU fastpath 생존을 확정할 수 없다. CPU·PPE가 정상이라는 이유로 NPU를 배제하지 않으며 전역 worker 정지와 단일 peer ACK/스케줄 정체는 구분되지 않는다.

## 전체 검토와 새 공개 패치의 상태

[9월26일 upstream 조사](../mlo-r33/FULL_REVIEW_20260926.md)와 [r35 미해결 목록](../mlo-r35/REVIEW.md)을 이어받는다. 최신 일반 UBI2 조사본은 `r36602-54e453b074`·kernel6.18.52이고 직전 일반 빌드와 펌웨어12개가 동일했다. 순수 L2 TTL·cross-ingress 995/996은 기존 KEEP_TTL·PPE 소유권·FDB 보완 전체의 대체물이 아니다. 공식 NPU watchdog 수정은 r34부터 포함됐다. Clanker의 eagle queue 제한과 E2/E3는 현재 MT7996 vendor blob의 같은 수정으로 귀속하지 않는다. 이 문서에서 그 upstream 조회를 새로 수행했다고 주장하지 않는다. 접근하지 못한 포럼 본문은 여전히 미확인이다.

F01 권한, F05–F08 설정 UI, 실패한 link activation rollback, 기존 PPE binding 무효화, RRO/PPE 삭제 오류 경계는 남아 있다. r36의 좁은 TX barrier 수정으로 해결됐다고 표시하지 않는다. WAN/IPv6/UDP/VLAN/QoS/Tailscale 전체 기능, 부팅·실기기 안정성도 이번 검사 범위 밖이다.
