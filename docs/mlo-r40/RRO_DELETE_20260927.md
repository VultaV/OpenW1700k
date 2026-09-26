# r40 RRO 삭제 오류의 오프라인 재현

2026-09-27. 기존 검토에서 남겨 둔 **NPU 삭제·WM 초기화 반환값 무시**를 현재 prepared source의 실제 함수로 재현했다. 새 제품 패치·펌웨어 설치·공유기 오류 주입은 하지 않았다. **실제 무선 멈춤과의 인과관계는 미확인**이다.

## 재현 결과

[검사 코드](../../tests/check_mt7996_rro_delete_errors.py)는 기존 mailbox host model과 함수 추출기를 재사용한다. 실제 `mt7996_wed_rro_work` → `mt76_npu_send_txrx_addr` → inline ops 전달 → `airoha_npu_wlan_msg_send` → mailbox 함수, 그리고 실제 `mt7996_mcu_wed_rro_reset_sessions` 요청 생성 함수를 연결했다. 유효한 SID 7의 삭제 이벤트를 넣고 다음을 확인했다.

| 입력 조건 | NPU 반환 | NPU 요청 게시 | 후속 WM 호출 / 반환 | 이벤트 해제 |
|---|---:|---:|---:|---:|
| 정상 대조군 | 0 | 1 | 1 / 0 | 1 |
| 실제 WLAN 요청 할당 실패 | -ENOMEM | 0 | 1 / 0 | 1 |
| 미완료 mailbox 선행 요청 | -EBUSY | 0 | 1 / 0 | 1 |
| WM 비성공 status 주입 | 0 | 1 | 1 / +1 | 1 |
| WM 전송 할당 오류 주입 | 0 | 1 | 1 / -ENOMEM | 1 |

**5개 관측 검사 통과 / 0 실패 / 0 건너뜀**, ASan·UBSan 진단 0건. 이것은 의도한 오류 무시 동작의 재현에 성공했다는 뜻이며, 제품의 오류 처리가 정상이라는 PASS가 아니다. [원본 결과](RRO_DELETE_20260927.json)에 추출 함수 7개·입력 소스 7개의 SHA256과 fixture hash를 보존했다.

핵심 두 실패는 worker의 NPU 호출에 임의 오류를 바로 반환한 것이 아니다. 실제 WLAN 요청 `kzalloc` 실패와 실제 mailbox의 `WAIT_RSP && !DONE` 검사에서 발생한다. 두 경우 mailbox write·poll은 0회이고 이전 payload/CTRL 상태도 보존됐지만, worker는 WM DEL 요청을 보내고 이벤트를 해제했다. 정상 요청의 action=3, SID=7, 나머지 payload=0 및 WM 요청의 tag·길이·SID·동기 응답 여부도 확인했다.

WM +1/-ENOMEM은 transport 응답 모형에서 주입했다. 실제 MCU parser 자체를 이 프로그램으로 실행하지는 않았다. 별도 소스 검토상 mt7996 MCU parser는 일치하는 UNI RESULT의 0이 아닌 status를 그대로 반환하고 common MCU 경로는 `-EAGAIN`만 반복하므로 양수도 실패다. timeout은 로그와 recovery 예약 경로가 별도로 있다.

## 실제 운용에서의 도달성과 한계

`MCU_UNI_EVENT_WED_RRO`의 `UNI_WED_RRO_BA_SESSION_DELETE`가 SID를 추출해 poll list에 넣고 이 worker를 예약한다. 재현기는 해당 연결을 source assertion으로 확인했으며 event parser·IRQ·동시 enqueue를 실행한 것은 아니다. reset/debug 명령이 필요한 전용 경로는 아니다.

`kfree(e)`는 작은 host 이벤트 항목의 해제다. NPU 임시 요청 버퍼의 해제 횟수와 구분했고 descriptor sentinel은 그대로였다. **DMA descriptor를 해제했다거나 실기기 DMA 접근이 안전하다고 증명한 결과가 아니다.**

## 단순 재시도를 넣지 않은 이유

기존 vendor NPU program SHA256 `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`의 action 3은 1024개 descriptor의 byte+7에 `0xff`를 쓴다. 메모리 해제·token 반환·DMA 정지가 아니다. [기존 바이너리 근거](../mlo-r34/FIRMWARE_FOLLOWUP_20260926.md#rro-action-3의-실제-범위)를 다시 대조했다.

- 일반 SID의 table base는 반복마다 다시 읽으며, 특수 SID 1024는 별도 base를 한 번 읽는다. 같은 table·같은 세션 세대·동시 producer 없음이 보장되면 재실행의 최종 쓰기 효과는 동일하다.
- timeout은 이전 요청의 취소를 뜻하지 않는다. 지연된 요청 또는 재시도가 이미 재사용된 SID의 새 descriptor를 무효화할 수 있는지 아직 배제하지 못했다.
- DELETE 이벤트에는 WLAN ID·TID도 있으나 host 대기 항목과 WM DEL 요청에는 SID만 보존된다. WM이 NPU 삭제·DEL 완료 전 SID 재사용을 금지한다는 계약은 확보하지 못했다.
- 선택된 실제 action 3 종료 경로는 마지막 store 후 return이고 wrapper는 상수 1을 반환한다. 이것만으로 generic mailbox 완료·다른 hart/DMA의 가시성·WM 세션 종료를 함께 보장한다고 해석하지 않는다.

따라서 **미게시 오류(-ENOMEM/-EBUSY), 게시 후 결과 불명(timeout), WM 실패를 구분해야 한다.** 무조건 retry나 단순 return은 안전한 복구의 검증을 대신할 수 없다. 이번에는 관측 가능한 소스 결함을 재현·기록하는 범위로 유지했다.

## 기존 실기기 기록과의 대조

r32 Air 실패 구간의 `kernel-during-test`는 개행 1바이트이고, 사후 dmesg의 마지막 시각은 실제 wake 수집보다 앞선다. 관련 오류 문자열은 없으나 연속 로그 coverage를 입증하지 못한다. r40 저장 kmsg 세 스트림에서도 관련 실패 문구는 없었다. 그러나 NPU -ENOMEM/-EBUSY와 무시된 반환값에는 전용 로그가 없으므로 **로그 부재는 성공의 증거가 아니다**. r37 이후 추가한 mailbox -EBUSY 방어를 r32 당시 코드에 소급하지 않는다.

이 항목은 [Mac Wi-Fi 설정 화면의 반복 검색 부하](LIVE_SCAN_20260927.md)와 별개의 드라이버 오류 처리 결함이다. 원래 Air 멈춤이나 Mac 검색 중 저하의 원인으로 확정하지 않았다. 수정에 앞서 필요한 근거는 WM SID 재사용 계약과 실기기 실패 반환의 실제 발생 여부다.

## 재현 명령

준비된 동일 소스를 사용해 저장소 루트에서 실행한다. compiler는 설치된 clang을 사용하며 임시 C 파일만 생성한다.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/check_mt7996_rro_delete_errors.py \
  --mt76 /path/to/prepared/mt76-2026.09.01~01367e60 \
  --kernel /path/to/prepared/linux-6.18.44
```

이 코드는 현재 알려진 결함의 재현기다. 향후 오류 처리가 바뀌면 기존 관측 assertion이 실패하는 것이 정상이며, 회귀 검사는 새 복구 계약에 맞춰 별도로 검토해야 한다.
