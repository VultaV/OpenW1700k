# r39: NPU 전송의 집계 세션 유휴 판정 검토

2026-09-26. r38 이후 정상 데이터 경로를 조사해 **NPU 가속 전송의 TX aggregation inactivity 갱신 누락**을 확인했다. 상대가 0이 아닌 ADDBA timeout을 협상하고, 드라이버가 받는 TXS 보고가 그 timeout보다 자주 도착하는 경우에 해당한다. 이 조건에서 원본은 계속된 전송 활동을 세션 유휴로 판단할 수 있다. Air의 실제 ADDBA timeout은 기존 자료에 없으므로 이 수정이 관측된 순간 멈춤의 원인이나 해결이라고 확정하지 않는다.

## 실제 호출 경로와 최소 수정

r38 prepared `mt76 01367e60`의 `mt7996/mac.c` SHA256은 `7750a9a259fbc3a36abc1f5cb5bf1de24c19e8f2f198d393b5e4cd1778257b0e`다. 다음 행은 수정 전 파일을 기준으로 한다.

1. DMA의 `mt7996_rx_check()`와 NPU RX의 `mt7996_queue_rx_skb()`가 TXS를 공통 `mt7996_mac_add_txs()`로 전달한다. `:1723`의 dispatcher는 PID가 `MT_PACKET_ID_NO_SKB` 이상인 경우만 RCU 안에서 WCID를 조회한다.
2. `mt7996_mac_add_txs_skb()`는 status lock을 잡고 TXS를 처리한다. MPDU에 대응하는 skb가 없어도 뒤의 refresh 블록을 건너뛰지 않는다.
3. `:1607`의 refresh는 **WED active와 station WCID**일 때만 실행됐다. NPU 경로는 mac80211의 일반/fast/802.3 host TX를 우회할 수 있어, 그 경로의 `last_tx` 갱신으로 대체된다고 보장할 수 없다.
4. 실제 backports 7.2 `agg-tx.c:1056–1062`는 peer ADDBA 응답의 timeout을 받아 0이 아니면 timer를 건다. `:558–573`의 refresh는 해당 TID의 기존 세션 `last_tx`를 갱신한다. `:579–601`의 만료 콜백은 `last_tx + timeout`이 지났으면 BA 세션을 중지한다.

[0035 패치](../../package/kernel/mt76/patches/0035-mt7996-refresh-npu-tx-aggregation-timer.patch)는 기존 WED 조건에 `mt76_npu_device_active(mdev)`를 OR로 추가한다. station guard, TID 추출, timeout 협상·만료 로직은 유지한다. 수정 후보 `mac.c` SHA256은 `5fc307c8b90654a16e8dbe204ae119966967a0a83fd49117ef766f17733ef00d`다. 새 주기 timer나 강제 세션 유지·reset은 추가하지 않는다.

[공식 mt76 기준 소스](https://github.com/openwrt/mt76/blob/be5ce7910521492d4a2e4ce7ee3843680a46c047/mt7996/mac.c)도 대조했다. 이번은 현재 트리의 NPU 갱신 누락을 보완한 로컬 패치이며, 새 공식 병합 패치를 가져왔다고 표시하지 않는다.

## 반례와 동시성 범위

- TXS 공통 TID 필드는 DW0의 28:26 비트이며 0–7이다. 기존 MT7996 WED도 MPDU/PPDU format을 제한하지 않고 같은 필드를 사용한다. 링크 WCID는 같은 station의 TID별 BA 상태로 연결된다.
- QoS null RX의 PS/UAPSD 처리와 host TX의 QoS null 제외 경로는 이 BA TX `last_tx`를 갱신하지 않는다. mesh forwarding의 별도 갱신은 일반 AP 전송의 대체 경로가 아니다.
- refresh는 기존 RCU/status-lock 문맥에서 기존 세션의 시간만 저장한다. 새 수면이나 추가 lock은 없다. NPU active helper는 MMIO와 pointer 존재만 확인하며 NPU를 역참조하지 않는다. 이 값이 NPU의 정상 동작을 보장하지는 않는다.
- PID 0으로 거부된 TXS, 보고 자체가 없는 정체, timeout보다 긴 보고 간격, 이미 STOPPING인 세션은 이 수정으로 해결되지 않는다. 오류 TXS도 활동으로 보는 기존 WED 동작을 유지하므로 TXS 수신을 ACK 성공으로 표현하지 않는다.
- 기존 `wcid->sta` 검사와 `wcid_to_sta()`의 재확인 사이 disassociation 경쟁은 전체 kernel concurrency 검증 범위 밖이다. 현재 바이너리에서 NULL 전달이 발생한다는 증거는 확보하지 못했으며 이번 OR 조건만의 새 결함으로 판정하지 않았다.

## 원본 실패와 수정본 검사

[회귀 검사](../../tests/test_mt7996_npu_aggregation.py)는 실제 dispatcher, refresh 조건, 협상 timeout 대입, mac80211 refresh·만료 함수를 추출한다. 기존 extractor를 재사용하고 실제 TID/PID mask와 TU 변환 매크로도 읽는다. rate/status 처리, RCU·lock·timer 실행 환경은 fixture다.

| 입력 | 실제 결과 | 의미 |
|---|---|---|
| r38 원본 일반 실행 | 16 PASS / 2 FAIL | NPU-only PPDU·MPDU에서 계속된 TXS에도 잘못된 유휴 종료 재현 |
| r38 정확한 음성 대조 모드 | 16 PASS / 2 EXPECTED_FAIL, 예상 외 실패 0 | accepted TXS 4개, `last_tx=100`, stop 1회라는 지정된 실패만 인정 |
| 0035 적용 후보 | 18 PASS / 0 FAIL | 같은 사례의 `last_tx=120`, stop 0회; 기존 WED·실제 무전송 만료 등 보존 |

ASan/UBSan 진단은 없었다. 검사에는 비가속·비station·없는 BA 세션·다른 TID·timeout 0·거부 PID·없는 WCID·이미 STOPPING 상태가 포함된다. HZ=1000의 동기식 host fixture이며 실제 timer 경쟁·firmware TXS 생성·보고 간격·Air timeout·무선 안정성을 검증하지 않는다. [실행 기록](ba-regression-tests.json)에 명령·입력 해시·원문 출력을 보존한다.

## 기존 Air 기록의 실제 TXS 진입 근거

r32 Air 절전 복귀 실패 회차의 기존 로그를 다시 확인했다. 선택된 Air의 6GHz 링크에서 아래 카운터가 관측됐다. 원본 SHA256은 `ebff80ad5e15d7659dd20fb29b07acd97dfbc4daf9c7a55c931edeaf7ba7b395`이며 식별자를 제외한 값·행 위치는 [대조 기록](AIR_TXS_EVIDENCE.json)에 보존했다.

| 표본 | 수집창 uptime | format-2 TXS 변화 | host tx_prepared 변화 |
|---|---|---|---|
| 18→19 | 87268.31–87268.99 → 87273.99–87274.63 | 74733→76304, +1571 | 7423→7423, 0 |
| 20→21 | 87279.64–87280.29 → 87285.29–87285.95 | 78910→81156, +2246 | 7424→7424, 0 |

해당 진단 카운터는 PID≥1 dispatcher 뒤에 있으므로 수용된 TXS 처리 경로가 실제 Air에서 실행됐음을 뒷받침한다. host 준비 카운터가 이 활동을 대신한다고 볼 수 없다. 그러나 raw PID·TID, ADDBA timeout, 정확한 앱 멈춤 시각은 드러나지 않는다. 표본도 비원자적으로 수집됐으며 멈춤 없는 Air 회차에서도 같은 경향이 있다. 따라서 **실제 실행 경로의 근거를 확보한 것이지 BA timeout 원인을 확정한 것은 아니다.**

## 펌웨어 정상 경로 후보를 좁힌 결과

실제 vendor program `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`의 caller를 다시 디코딩했다. `0x8400ecba`의 `s1=5`를 6으로 올리는 대안은 free=7의 0 예산 호출을 막지만, **free=6에서 기존 slow 호출도 생략하고 DMA 재조회 대기 루프를 1,000회에서 5,000회로 바꾼다.** 동작 보존 대안으로 채택하지 않았다. 앞서 검증한 [callee 내부 4바이트 메모리 guard](../npu-budget-guard-20260926/GUARD_DESIGN.md)를 다시 구현하거나 firmware 파일로 만들지 않았다.

정상 같은 band·단일 producer·이전 batch 게시 완료 조건에서는 current P와 next P+1이 이번 미게시 집합 `{P−1…P−u}`, `u≤7`에 들어가지 않는다. ring 512/1024의 모든 P와 u에 대해 12,288개 산술 조합을 검사했다. 따라서 free=7에서 8개 batch 전에 하드웨어 대기에 들어갈 가능성과, 자신의 미게시 descriptor를 기다리는 순환 교착은 구분해야 한다. 후자는 이 조건에서 성립하지 않는다. [범위와 결과](FIRMWARE_FOLLOWUP.json)는 실제 명령·MMIO 실행을 대신하지 않는다.

혼합 출력 band 가설도 호스트 경로에서는 근거를 찾지 못했다. 같은 `info.idx`가 PPE의 NBQ와 FOE band 필드에 함께 쓰이고, L2 복사도 두 필드를 함께 유지한다. 따라서 stale PPE만으로 두 값이 서로 달라진다고 해석하지 않는다. 하드웨어의 NBQ→RX ring 및 FOE bit11→metadata bit25 변환 계약은 아직 확인하지 못했다.

vendor fast record와 최종 TXD PID의 변환도 완전히 연결하지 못했다. 미작성 record 필드를 곧 PID 0으로 간주하지 않으며, pure NPU fastpath가 항상 PID≥1 TXS를 만든다는 주장도 하지 않는다. BA 수정의 효과는 드라이버가 실제 수용하는 TXS가 있다는 조건에 한정한다.

## 유지되는 미해결 범위

[r38 상태 목록](../mlo-r38/REVIEW.md#남은-범위)의 NPU stop/reset·IRQ 수명·RRO 오류 처리, runtime PPE 삭제 실패, F01/F05–F08 권한·설정 문제는 그대로 남는다. 이번 변경은 CPU/가속으로 이미 회복한 최대 처리량을 추가 향상시켰다는 주장도 아니다. 공유기 접속·설치·재부팅·추가 무선 시험은 하지 않았다.

## 빌드 경고 대조

전체 9단계 로그에서 경고 386회·고유 149개를 기록했다. r38 대비 새 문구 하나는 `xtables-addons` 외부 모듈 설치의 `System.map` 부재로 `depmod`를 생략한 경고다. 해당 `xt_LUA.ko`는 추출 이미지에 없으며 이미지의 74개 module payload·ABI를 별도 검증했다. 누락 의존성 14건과 empty-kmod 28개에도 현재 이미지에 설치된 해당 항목은 없었다. 경고 감소는 증분 재빌드의 범위 차이일 수 있어 해결된 경고 수로 계산하지 않는다. 모든 경고가 무해하다는 판정도 아니다.
