# r64 — 대역별 DFS 전달과 AP 재시작 후 송신 복구

r63 위에 11월 4일 야간 장애 조사에서 확인한 mt7996 DFS 경로를 수정한다. 커널은 `6.18.59-w1700k-mlo-r32`, mt76 pin은 `639e1287`, 패키지 release는 **40**이다. NPU v0.8 시험 파일 쌍과 기존 r63 MLO 수정은 유지한다.

## 변경 사항

- 모든 radio가 공유하는 hw에 NULL context를 전달하던 레이더 보고를, 감지한 radio의 현재 channel context로 제한한다. mac80211 atomic iterator의 RCU 보호 범위에서 pointer를 비교하고 보고하여 context 수명을 보존한다. 현재 context가 없으면 다른 대역에 대신 보고하지 않는다. 배경 레이더 경로는 유지한다.
- RDD 보고가 rdd_idx까지 포함하는지 검사한 뒤 읽는다.
- AP 재시작/CAC fallback은 post_channel_switch를 거치지 않을 수 있다. 운영 채널 설정과 DFS 초기화가 성공하고 DFS 상태가 disabled/active일 때, 이전 레이더로 중단된 MAC 송신을 재개한다. CAC·unknown·offchannel에서는 재개하지 않는다. DFS 초기화나 재개 실패는 호출자에게 반환한다.
- 레이더 감지나 CAC 자체를 끄지 않는다. 자동 리셋으로 오류를 숨기지 않는다.

## 호스트 검증

실제 radar report·channel setup·MCU resume·mac80211 iterator C를 추출했다. 수정 전 공통 21개 검사 중 8개가 실패하고, 수정 후 22개 검사가 모두 통과했다(추가 1개는 짧은 RDD 보고 검사). ASan/UBSan 사용. 배경 레이더, 잘못된 인덱스, 사라진 radio/context, 교체 중 context, CAC·unknown·offchannel, MCU/DFS 오류를 포함한다.

기존 MLO backport 20개, best-link 10개, MLO PS 29+99개 검사도 통과했다. 호스트의 RCU·MCU 서비스는 fixture이므로 실제 펌웨어 실행이나 동시성을 검증한 것은 아니다.

## 실제 장비 확인

최종 빌드·이미지 확인과 설치·실기기 결과는 `BUILD_RESULT.json`과 별도 장치 시험 기록에 저장한다. 설치 전에는 장비에서 해결됐다고 표시하지 않는다. 11월 4일 원시 장애 로그·설정 백업·단말 식별자는 비공개 로컬 artifacts에만 보존한다.
