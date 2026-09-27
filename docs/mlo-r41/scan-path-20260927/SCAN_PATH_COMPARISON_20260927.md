# r41 연결 초기 스캔과 데이터 가속 경로 비교 — 2026-09-27

같은 Mac에서 새 MLO 연결 두 회차를 비교했습니다. TCP 설정은 150Mbps × 4스트림, 합계 목표 600Mbps였습니다. 한 회차는 PPE 가속, 다른 회차는 시험 단말과 서버의 새 TCP 데이터 연결만 가속 추가에서 제외했습니다. **두 경로 모두 연결 나이 약 22초에 급락했습니다.** 이 회차의 저하는 시험 데이터의 PPE 가속을 필요조건으로 하지 않았습니다. 전역 NPU·공통 Wi-Fi 경로의 영향을 배제하거나 원래 Air 절전 복귀 멈춤을 해결했다는 뜻은 아닙니다.

| 경로 | 전송 시작 연결 나이 | 평균 / 최저 Mbps | 500Mbps 미만 / 0 표본 | 서버 TCP 재전송 |
|---|---|---|---:|---:|
| PPE 가속 | 7.385–7.731초 | 599.99 / 69.78 | 13 / 0 | 3,422 |
| 새 데이터 가속 우회 | 8.123–8.967초 | 599.97 / 46.21 | 14 / 0 | 3,078 |

양쪽에서 연결 후 약 20.3초의 BEST CONNECTED 스캔 요청과, 전송 구간에 겹칠 수 있는 scan API 호출 33쌍을 기록했습니다. 첫 500Mbps 미만 구간의 연결 나이 범위는 가속 21.392–22.741초, 우회 22.127–23.970초입니다. 첫 가능한 scan 이전의 수신 평균은 각각 약 600.17/599.88Mbps였습니다. 설정 전송률은 순간 상한이 아니며 회복 후 catch-up burst는 각각 최고 1664.57/1304.92Mbps였습니다. 서로 다른 새 연결이므로 순간 입력량·RF 조건까지 같았다고 판단하지 않습니다. 별도 native 요청 비교에서 두 회차의 33개 요청이 열거한 97개 채널 항목(2GHz 13·5GHz 25·6GHz 59)의 순서가 같았습니다. API 호출 시간 합은 12.333/12.212초였지만 실제 RF 체류 시간이나 Neighbor Report 사용을 입증하지 않습니다.

우회 회차는 실제 데이터 tuple 네 개의 conntrack 존재와 OFFLOAD/HW_OFFLOAD·양방향 PPE BND 부재를 전송 중 6개 시점, 총 24개 표본에서 확인했습니다. 두 임시 규칙 카운터가 증가했고 종료 후 원래 규칙 SHA256 일치와 복원을 확인했습니다. **전역 NPU는 계속 활성**이었으며 라디오·네트워크·서비스·flowtable을 재시작하지 않았습니다. 두 회차의 유선 HTTP 확인은 합계 109회 모두 정상이었습니다. 표본 사이 모든 패킷 경로를 입증하지 않으며 우회 경로 조회 부하도 남습니다.

드라이버 기록의 대상 TXFREE status2(RED-drop HEADER 카운터)는 우회 회차에서 시험 전·저하·시험 후 모두 0이었고, 가속 회차는 0 → 671 → 3,248이었습니다. 따라서 관측된 RED-drop 카운터 증가도 이번 급락의 필수 조건은 아니었습니다. 중복된 무선별 큐 출력은 한 번만 집계했으며 이 카운터는 TCP 손실 패킷 수가 아닙니다. 양쪽 TID0 BA 응답과 두 링크 활성화 명령 성공은 연결 후 약 0.405/0.440초로 전송 시작 전이었습니다. 이는 이후 모든 aggregate 전달이나 펌웨어 상태를 보증하지 않습니다.

API 구간은 RF 체류 시간이 아닙니다. PS 이벤트 번호 누락은 가속 111개·우회 184개여서 정확한 wake 지연을 복원할 수 없습니다. TCP 재전송은 무선 손실 패킷 수와 같지 않으며, 1초 표본의 0이 없다는 결과도 더 짧은 멈춤을 배제하지 않습니다. 시험 후 부팅·네 설정 파일 해시·기존 bridge 규칙은 같았고 PS/BA/강제 awake 진단은 OFF로 복원했습니다. Mac의 원래 핫스팟을 복원했고, 유선 공유기 관리 접속과 핫스팟 외부 인터넷의 HTTP 200 응답도 확인했습니다. 신규 제품 소스·펌웨어·태그 변경은 없고 기존 Air 문제의 원인은 여전히 미확정입니다.

[비교 수치·입력 해시](https://github.com/VultaV/OpenW1700k/blob/codex/mlo-r30-bridge-offload/docs/mlo-r41/scan-path-20260927/ANALYSIS.json) · [가속 상세](https://github.com/VultaV/OpenW1700k/blob/codex/mlo-r30-bridge-offload/docs/mlo-r41/scan-path-20260927/hw/ANALYSIS.json) · [우회 상세·복원 증거 해시](https://github.com/VultaV/OpenW1700k/blob/codex/mlo-r30-bridge-offload/docs/mlo-r41/scan-path-20260927/noft/ANALYSIS.json) · [최종 복원 확인](https://github.com/VultaV/OpenW1700k/blob/codex/mlo-r30-bridge-offload/docs/mlo-r41/scan-path-20260927/RESTORATION.json) · [요청 채널 대조](https://github.com/VultaV/OpenW1700k/blob/codex/mlo-r30-bridge-offload/docs/mlo-r41/scan-path-20260927/SCAN_CHANNEL_CHECK.json) · [드라이버 기록 대조](https://github.com/VultaV/OpenW1700k/blob/codex/mlo-r30-bridge-offload/docs/mlo-r41/scan-path-20260927/DRIVER_CHECK.json)
