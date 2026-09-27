# r41 실제 Neighbor Report 교환과 전송 관찰

**Mac의 NR 요청→응답→ACK 1회와 응답 안의 두 실제 AP 보고서를 확인했다. 같은 회차에서 속도 저하와 background scan 요청도 남았다.** ACK는 Mac의 정보 채택이나 스캔 정책 변경을 증명하지 않는다.

| 회차 | 평균 / 최저 Mbps | <500 / 0 표본 | 서버 재전송 | 전송 중 가능한 scan API 겹침 |
|---|---|---:|---:|---:|
| baseline_hw600 | 599.99 / 69.78 | 13 / 0 | 3422 | 33 |
| prior_nr600 | 600.03 / 67.43 | 13 / 0 | 1587 | 33 |
| observed_nr600 | 600.02 / 62.86 | 14 / 0 | 1420 | 33 |

세 회차는 스트림당 150Mbps × 4, 40초로 설정했다. 순간 전송률의 상한이 아니며 저하 뒤 catch-up이 가능하다. 서로 다른 연결이고 이번에는 netlink 관측기가 추가되어 부하·RF 조건의 완전한 일치를 주장하지 않는다.

이번 관측기는 1126개를 기록했고 kernel drop은 0, 잘린 레코드는 0개다. `received by filter` 1136개는 기록 수와 별도 집계다. 현재 인터페이스 GET/NEW 교환과 family boot pin도 검증했다. 관측기 상태는 `RESTORED`이고 이번 전송의 유선 확인 56회는 정상이었다. NR/AP 자동 복원은 실패했으며, 아래의 별도 복구 후 최종 상태를 검증했다.

요청된 background 채널의 전체 순서는 세 회차에서 동일했다. 이는 API 요청 목록이며 실제 RF 체류시간이 아니다. PS 이벤트 누락으로 연속 절전시간·복귀 지연을 계산하지 않는다. 이 회차의 NR ACK를 이전 회차에 소급하지 않으며, NR 전체의 무효나 원래 Air 문제 해결도 단정하지 않는다.

입력 해시와 수치: [NR_EXCHANGE.json](NR_EXCHANGE_20260927.json), [TRAFFIC_COMPARISON.json](NR_TRAFFIC_COMPARISON_20260927.json), [ANALYSIS.json](NR_TRAFFIC_ANALYSIS_20260927.json).

## 복원 실패와 최종 상태

첫 준비에서는 20초 AP 대기 한도가 실제 60초 DFS CAC보다 짧아 실패했다. 원본 설정으로 복구한 뒤 두 링크의 공통 대기를 90초로 바꾸고 60초 지연 성공·90초 초과 실패를 로컬 검사했다. 재시도에서는 실제 시험과 관측기 복원까지 완료했다.

이후 NR 설정 원복 중 5GHz가 `Could not set channel for kernel driver` → `Interface initialization failed` → `HT_SCAN→DISABLED`로 실패했다. 정확한 오류 번호와 드라이버 원인은 INFO 로그에서 확정할 수 없다. 원본 설정을 대조한 뒤 radio1만 재생성했고 60초 CAC를 거쳐 두 AP가 ENABLED로 복구됐다. 전체 네트워크 재시작이나 재부팅은 하지 않았다.

최종 검사는 원본 설정 34개, 정적 nft 규칙(재생성된 handle 제외), 부팅·taint, PS/BA 진단 옵션, NR 비활성 상태와 임시 관측 모듈 제거를 확인했다. NR 제어기 유선 확인 212회 및 수동 복구 중 63회는 모두 정상이었다. Mac은 iPhone 핫스팟으로 복원했다. **자동 복원 성공으로 기록하지 않는다.** [최종 복구 검증](NR_EXCHANGE_RESTORATION_20260927.json).

r41 펌웨어·태그는 그대로이며 이번에는 관측 도구와 진단 기록만 추가했다. 다음 원인 조사는 채널 설정 실패의 실제 netlink 오류와 Mac 스캔 시점의 절전·큐 처리 경로를 구분해야 한다. 원래 Air 절전 복귀 멈춤은 여전히 해결로 판정하지 않는다.
