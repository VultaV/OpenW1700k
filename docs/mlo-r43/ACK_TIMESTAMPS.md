# 기존 r43 저속·정상 회차의 ACK timestamp 비교

서버에 저장된 패킷만 다시 분석했다. 새 장치 조작이나 캡처는 없으며, 원본 캡처·iperf·기존 TCP 검증 결과의 SHA와 실제 네 흐름을 대조했다. 저속 1,728,003개, 정상 1,684,407개 레코드에서 커널 캡처 손실은 0이다. 결과는 [ACK_TIMESTAMPS.json](ACK_TIMESTAMPS.json), 재현 코드는 [check-ack-timestamps.py](check-ack-timestamps.py)에 있다.

| 관측 | 저속 회차 | 같은 연결의 후속 정상 회차 |
|---|---:|---:|
| 평균 수신 속도 | 1,135.77Mbps | 1,962.08Mbps |
| 네 흐름 모두 ACK가 없는 100ms 초과 공백 | 108개 | 0개 |
| 그중 100–300ms / 300ms 초과 | 103개 / 5개 | 0개 / 0개 |
| 연결별 실측 TS tick/서버 초 | 999.971–1,000.015 | 999.928–999.936 |

저속 회차의 **짧은 공백 103개**에서 각 흐름의 공백 전후 ACK 수신간격 중앙값은 137.52–137.64ms이고, TSval 증가 중앙값은 네 흐름 모두 2ticks다. 연결별 실측 기울기로 환산하면 약 2ms다. 흐름별 88–95개 공백에서 TSval 증가는 5ticks 이하였다. 98–101개에서는 첫 복귀 ACK 이후 20ms 안에 timestamp가 실측 환산 100ms 이상 진행했다. 이는 긴 수신 공백을 사이에 두고 비슷한 timestamp의 ACK가 도착한 뒤, 더 진행한 timestamp의 ACK가 빠르게 도착하는 패턴이다.

반면 **최장 공통 공백 22.913048–24.122492초(1,209.444ms)**는 다르다. 각 흐름을 둘러싼 ACK 수신간격은 1,209.451–1,210.717ms이고 TSval은 각각 **1,220 / 1,220 / 1,222 / 1,222ticks** 진행했다. 다음 20ms 동안의 증가는 모두 18ticks였다. 따라서 짧은 반복 공백의 패턴을 1.2초 공백까지 같은 형태로 일반화할 수 없다. 나머지 긴 공백도 별도 집계했다.

[RFC 7323 §4.4](https://www.rfc-editor.org/rfc/rfc7323.html#section-4.4)는 연결별 timestamp offset을 허용한다. 비교는 연결마다 TSval 증가량만 사용한다. 절대 timestamp를 흐름 사이에 비교하지 않으며 1kHz를 상수로 가정하지 않는다. 32비트 rollover는 허용하되 역행·반 공간 이상의 모호한 증가·관측 전체 반 공간 초과를 거부한다. 해당 입력에는 그런 모호성이 없었다. 자체 검사는 rollover·동일값·연결별 offset 불변성과 세 가지 잘못된 입력의 거부를 확인한다.

서버 도착 시각과 TSval은 패킷 생성·무선 송신 시각의 직접 관측이 아니다. clock sampling, timestamp 재사용, TSO/GSO 및 batching은 정확한 생성 시각이나 기록 경계 해석에 영향을 줄 수 있다. 여기서 계산한 두 증가량의 차이는 정확한 편도 지연이나 RF 이탈 시간이 아니다. ACK에는 누적 확인 바이트가 늘지 않는 ACK도 포함된다. 이 자료만으로 Mac 내부, 무선 구간, AP/NPU 수신 경로 중 지연 위치를 특정하거나 AWDL 원인·Air 문제 해결·r43 간헐 회귀 부재를 주장할 수 없다. 짝지은 Mac 캡처는 같은 timestamp/바이트 범위가 Mac 관측 지점과 서버에 언제 나타났는지 구분하는 추가 가치가 남는다.

원본이 같은 위치에 보존된 작업 폴더에서 실행한다. 결과 파일이 있으면 바이트 동일성까지 확인한다.

```sh
python3 artifacts/npu-zero-budget-r43-2026-09-27/endpoint-pair/check-ack-timestamps.py --self-test
python3 artifacts/npu-zero-budget-r43-2026-09-27/endpoint-pair/check-ack-timestamps.py
```
