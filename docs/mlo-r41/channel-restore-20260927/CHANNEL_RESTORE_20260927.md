# r41 채널 설정 실패 관찰

**5GHz 채널 설정 실패와 DFS 2초 유예의 인과관계는 아직 확인하지 못했습니다.** 원래 무선 설정을 유지한 두 번의 AP 재생성에서는 5GHz·6GHz 채널 설정과 AP 시작이 성공했습니다. 마지막 소수점 대기 변형은 시험 스크립트 실행 오류로 중단했으며, 채널 실패 재현 결과에서 제외합니다. 추가 재시작 시험은 종료합니다.

| 회차 | 관측 결과 | 판정 |
|---|---|---|
| 첫 관찰 | AP 준비·설정 복원은 확인했지만 선택된 캡처 0건 | 관찰 실패. 채널 오류가 없었다는 증거가 아님 |
| 읽기 전용 live canary | 패킷 67개, 정확히 대응하는 GET_INTERFACE/NEW_INTERFACE 1쌍, 커널 캡처 드롭 0, 유선 확인 13회 정상 | 수정한 실시간 캡처 경로 확인 |
| 정상 재생성 | 기록 180개, 5GHz STOP_AP 요청→주파수 SET_WIPHY 요청 1.568108초 | 두 대역 주파수 설정·START_AP 성공, 원본 복원 확인 |
| 1초 대기 변형 | 기록 190개, 같은 요청 간격 1.932121초 | 두 대역 주파수 설정·START_AP 성공, 원본 복원 확인 |
| 1.5초 대기 변형 | 장치 BusyBox가 `sleep 1.5`를 거부하여 AP down 이후 up 이전 중단 | 실행 실패로 제외. 자동 복원 실패 후 수동 AP 시작으로 최종 복원 |

표의 간격은 **요청→요청** 기준입니다. STOP_AP 성공 응답→주파수 SET_WIPHY 요청 기준은 각각 1.567018초와 1.931085초입니다. 두 유효 회차 모두 2초 미만이므로, 이 결과로 2초 경계 이후의 동작을 판단할 수 없습니다. 두 회차의 캡처에 DFS PRE-CAC 만료 이벤트는 관측되지 않았습니다.

첫 빈 캡처는 실시간 Linux netlink 캡처와 저장된 SLL 패킷을 읽을 때의 BPF 길이 의미 차이 때문이었습니다. 실시간·오프라인 필터를 분리하고, 실제 읽기 전용 교환으로 검증했습니다. 이후 가드는 AP 명령 전에 pcap이 헤더만 있는 24바이트를 넘어서는지 최대 5초간 확인합니다. 이 크기 검사는 빈 캡처를 막는 조건이며, 교환 내용 분석을 대신하지 않습니다.

오류 이름도 분석을 수행한 Mac의 errno 표 대신 **실제 대상 Linux AArch64 헤더**로 해석하도록 수정했습니다. 예를 들어 `-95`는 `EOPNOTSUPP`, `-19`는 `ENODEV`, `-22`는 `EINVAL`입니다. 유효 회차에도 양쪽 안테나 마스크 `0xffffffff` 요청의 SET_WIPHY `-95`와 제거 중인 이전 netdev의 STOP_AP·GET_INTERFACE `-19`는 기록됐습니다. 이를 이후 성공한 주파수 설정 실패로 합치지 않았으며, 요청과 응답의 대응을 개별 확인했습니다.

이 관찰은 원래 설정의 radio down/up만 수행했고, NR 플래그 변경·전체 network reload·규제 상태 변경·새 펌웨어 적용은 하지 않았습니다. 따라서 앞선 NR 복원 실패의 전체 조건을 재현한 시험은 아닙니다. 기존 Mac의 연결 후 background scan과 속도 저하 관측은 별도 근거로 유지하며, 이번 결과가 원래 iPhone Air 절전 복귀 멈춤을 해결하거나 배제하지는 않습니다.

**최종 상태는 `RESTORED_AFTER_MANUAL_AP_START`입니다.** 자동 `RESTORE_FAILED` 기록은 그대로 보존했습니다. 수동 복구 후 설정 파일 34개와 원래 가속 규칙이 정확히 일치하고, 두 AP가 활성화됐으며 부팅·커널 taint 값은 유지됐습니다. nlmon은 제거됐고 PS·BA·TXDROP 진단은 OFF입니다. 유선 링크는 LAN2 2.5Gbps·LAN4 1Gbps이며 제어 중 27회와 복구 중 56회의 유선 관측은 모두 정상이었습니다. 이 관측은 샘플 사이의 순간 중단까지 배제하는 연속 측정은 아닙니다.

공개 근거: [정상 재생성](CHANNEL_BASELINE_20260927.json), [1초 지연](CHANNEL_DELAY1_20260927.json), [관측기 검증](CHANNEL_OBSERVER_20260927.json), [최종 복원](CHANNEL_RESTORATION_20260927.json). 원시 캡처·장치 식별자·설정 백업은 공개하지 않습니다.

관련 기존 패치도 다시 확인했습니다. [Linux의 non-ETSI DFS 만료 동작](https://github.com/torvalds/linux/commit/b35a51c7dd25a823767969e3089542d7478777e9), [AP 중단 시 유예기간 시작을 갱신하는 310 패치](https://github.com/OpenWRT-fanboy/OpenW1700k/blob/bf44cb5fb0f510b89e7a651e650dbf71062441d9/package/kernel/mac80211/patches/subsys/310-cfg80211-allow-grace-period-for-DFS-available-after-.patch), [우리 DFS 이벤트 전 링크 전달 패치](https://github.com/VultaV/OpenW1700k/blob/3f461e86a2d3238ae0a784de4f17ca4a96746f57/package/network/services/hostapd/patches/9999-deliver-dfs-state-to-unconfigured-links.patch)는 이미 prepared 소스에 있습니다. 이 좁은 경로에서 바로 적용할 새 수정은 확인하지 못했으며, 모든 upstream 대기 패치에 대한 전수조사 결론은 아닙니다.

설치 펌웨어는 r41, 커널은 `6.18.44-w1700k-mlo-r32`로 유지했습니다. 이번 변경은 로컬 관측·분석 도구와 문서에 한정되며 새 빌드나 성능 개선 판정은 없습니다.
