# 최신 공개 빌드의 적용 후 Airoha 드라이버 검토



OpenWrt `425d4a2ae929094a9157afd36547c694ec01591e`의 패치와 Linux v6.18.52의 원본을 고정해, `include/quilt.mk` 순서대로 Airoha 디렉터리에 해당하는 71개 패치를 적용했다. 71/71 적용 성공, fuzz 0이다. 범위는 `drivers/net/ethernet/airoha/`이며 전체 커널 빌드나 다른 디렉터리의 API 호환성을 검증한 결과는 아니다. 현재 r32의 준비된 소스와 비교했다.

| 차이 | 확인된 영향과 한계 |
| --- | --- |
| RX 큐 31 인터럽트 비트 추가 | r32 마스크 `0x7fe00000`에는 큐 31이 빠져 있다. 최신 값은 `0xffe00000`이며 해당 큐의 NAPI 처리를 가능하게 한다. Air 멈춤과의 직접 인과관계는 미검증이다. |
| HW GRO 검사 보완 | aggregate 개수 64 초과 거부, descriptor의 timestamp reply가 0이면 기존 TSecr 보존, `SKB_GSO_DODGY` 추가. 활성 경로에서 유효한 정확성 수정이나 특정 시험 멈춤을 해결한다는 증거는 아직 없다. |
| RX descriptor 수 증가 | 큐 4는 128개, 기본 큐는 16→32개다. 큐 0의 1024개는 동일하다. |
| NPU DMA mask | `dma_set_coherent_mask()`를 `dma_set_mask_and_coherent()`로 변경한다. 펌웨어 바이너리 교체가 아니다. |
| TX 잠금·카운터 정리 | `spin_lock_irq()`→`spin_lock_bh()`, 소비자가 없는 큐 카운터 제거. 작성자 커밋의 의도적 변경이며 다른 파일로 이동한 것이 아니다. hard IRQ의 별도 잠금과 TX/NAPI 호출 경로를 확인했으며 제거 자체를 회귀로 판정하지 않는다. |
| 자체 PPE 수정 | 최신 원본에는 r32의 소유권·슬롯·FDB·TTL 보완이 모두 들어 있지 않다. 원본 전체 교체 시 검증된 수정이 사라지므로 병합 검토가 필요하다. |

잠금 변경 근거: https://github.com/OpenWRT-fanboy/OpenW1700k/commit/6c0d974cfdc39a385f4054df289f2fc3310e4480

보존 자료: `applied-source/apply.log`, `applied-source/applied-patches.json`, `applied-source/SOURCE_COMPARISON.json`, `applied-source/airoha.diff`. 실제 빌드 트리 및 실행 중인 펌웨어는 변경하지 않았다.

## 실행 중인 r32 레지스터 확인

장치 트리·드라이버·`/proc/iomem`으로 확인한 주소에서 22개 읽기 전용 설정/인덱스 레지스터를 3회 읽었다. MMIO 쓰기 및 인터럽트 상태 읽기는 하지 않았다.

- 두 CDM의 HW LRO/GRO enable 값은 `0xff`로 활성 상태다.
- 두 QDMA의 RX IRQ enable2 bank 1은 `0x7fe07fe0`, 다른 bank는 0으로 큐 31 활성 비트가 없다.
- 큐 31은 16 descriptor, CPU 인덱스 15·DMA 인덱스 2가 세 표본에서 고정됐다. 같은 동안 큐 0의 인덱스는 움직였다. IRQ 누락과 일치하지만 descriptor 완료 비트·패킷 종류·발생 시각을 확인하지 않았으므로 큐 정지 원인과 Air 증상은 아직 동일시하지 않는다.
- 같은 부팅·설정 해시, PS trace OFF, LAN2 2.5Gbps·LAN4 1Gbps 연결을 확인했다.

근거: `applied-source/register-plan.json`, `applied-source/read-registers.sh`, `applied-source/private/registers.txt`. 원시 장치 식별 정보는 공개하지 않는다.

## RX 큐 31 descriptor 추가 관측 — 인덱스만으로 정지 판정 불가

실행 중인 ring base 주소가 System RAM에 속하고 DMA 변환이 없는 장치 매핑임을 확인했다. 공개된 구조체 레이아웃(32바이트, ctrl +4, msg1 +20)에 따라 완료 비트와 분류 메타데이터만 읽었고 패킷 데이터/주소를 수정하지 않았다.

유휴 및 Mac 20초 MLO 시험 끝 구간에서 각각 두 QDMA×16 descriptor×2회, 총 128개 표본을 읽었다. **DONE 비트 0개, 수신 분류 메타데이터 비영(非零) 0개**였다. 각 ring의 0~14는 준비된 길이 `0x680`, 마지막 항목은 0이었다. 따라서 고정된 CPU 15/DMA 2 인덱스로부터 완료된 패킷이 쌓여 있다고 추론하지 않는다. IRQ 비트 누락이라는 소스 결함은 별개로 남지만, 현재 Air 멈춤의 원인이라는 증거는 얻지 못했다.

동시 Mac 시험은 평균 1,920.98Mbps, 네 HW offload 흐름·동일 설정을 유지했다. 관측 파일은 클라이언트 프로세스 실행 구간 안에서 생성·종료됐지만 마지막 읽기까지 실제 payload 전송과 겹쳤는지는 입증하지 않았다. 드문 이벤트, 표본 사이 변화, Air 절전 실패 시점은 이 관측으로 배제하지 않는다.

재검증: `applied-source/check-rx31.py`. 요약 `applied-source/RX31_VALIDATION.json`에 표본 수·해시·한계를 보존한다. 이번 결과만으로 새 드라이버 수정본을 설치하지 않았다.
