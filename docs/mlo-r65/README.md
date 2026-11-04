# r65 — MLO DFS 대피 채널 선택

r64는 잘못된 다른 대역의 레이더 감지를 막았으나, 160MHz 시험에서 hostapd가 즉시 사용 가능한 80MHz보다 CAC가 필요한 160MHz 채널을 선택해 AP를 재시작했다. 실기기에서 연속 27초의 0Mbps가 남아 후속 수정한다.

r65는 MLD의 DFS_AVAILABLE 선택에서 사용 가능한 좁은 채널을 먼저 찾아 기존 링크별 CSA를 사용한다. 없으면 기존 CAC/NOP 절차로 돌아간다. ETSI uniform spreading 및 일반 AP 경로는 유지한다. 커널, mt76, NPU는 r64와 같다.

- 소스: `447f3823006507b792e518764230ce931a4e6381`
- hostapd/wpad: 2026.08.07~831364bf-r9
- mt76: 2026.10.08~639e1287-r40
- 커널/모듈 ABI: `6.18.59-w1700k-mlo-r32`
- NPU: 변경 없는 0.8 시험 펌웨어. 구형 바이트쌍 전용 budget guard는 적용되지 않는다.
- 실제 hostapd C 선택 검사: 기존 13개 중 3개 실패, 수정 13개 통과; non-BE 10개 및 DFS dispatcher 216개 통과. ASan/UBSan 사용. 채널 가용성 fixture는 실제 무선 동작을 대체하지 않는다.

빌드 시점 기록과 설치 후 실기기 기록은 별도로 보존한다. `BUILD_RESULT.json`은 빌드 시점의 상태이며 후속 실기기 결과는 `DEVICE_TESTS.json`에 기록한다. 원시 로그와 설정 백업은 공개하지 않는다.
