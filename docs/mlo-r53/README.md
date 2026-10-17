# r53 — upstream airoha_eth 백포트와 W25N04LV 지원

r52 위에서 OpenWrt upstream의 airoha 이더넷 드라이버 갱신(2026-10-16)을 가져오고, 겹치는 포크 패치를 정리한
버전입니다. mt76 드라이버, 무선·NPU 펌웨어, 커널 버전(6.18.55)은 r52와 같습니다. 2026-10-17 실제 장치에
설치해 확인했습니다. MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.

## 바뀐 점

- upstream 커밋 4개(cherry-pick `-x`):
  - `002faeed3c` 작은 RX 링 크기 확대(182).
  - `059895c014` airoha_eth 수정 8개: PPE SRAM flush 오류 처리, QDMA trtcm 설정 재시도, 공유 QDMA TX 링의 BQL
    언더플로, 조각 패킷 DMA 매핑, 최대 수신 크기, MIB 통계 손실 방지, 모듈 라이선스, TX 하드웨어 설정 준비(185–192).
  - `d4083ed9ee` GDM3/GDM4를 HTB 하드웨어 오프로드 요청 때만 WAN으로 전환, ETS 통계 수정(193-01–03).
  - `e1bd479ba8` LRO v7(194). 기존 HW-GRO 패치(916-02)를 대체합니다.
- 포크 패치 정리:
  - `992-20`: upstream 187과 겹치는 trtcm 재시도를 빼고, TX 링 락의 irq 변환을 새 TX 정리 함수와 xmit 오류
    경로에 다시 맞췄습니다.
  - `9999-net-airoha-honor-flow-action-keep-ttl`: 선언 위치만 다시 맞췄습니다.
  - `9990`(QDMA 공유 기기 간 HW-GRO 상태 공유)를 뺐습니다. upstream 194는 QDMA를 둘 이상의 기기가 쓰면 LRO를
    끄는 방식으로 같은 문제를 처리합니다. 이 장치는 LAN 쪽 eth0·lan2가 같은 QDMA를 써서 LRO가 꺼지며, 공유기를
    거쳐 가는 흐름은 PPE·NPU 오프로드라 영향이 없습니다.
  - `9999-z5`(PPE SRAM flush 오류 전파)를 뺐습니다. upstream 185와 같은 수정입니다.
- `ba9f3bf306`(OpenWRT-fanboy): Winbond W25N04LV SPI-NAND 지원(커널·U-Boot). 이 칩이 들어간 하드웨어 리비전용입니다.

## 빌드

- 커널 패치 적용 시 fuzz는 기존과 같은 `9999-z1` 한 곳뿐입니다. 패키지 manifest는 r52와 같습니다.

## 실기기 확인 (2026-10-17)

| 항목 | 결과 |
|---|---|
| 설치 | r52에서 설정 유지, `sysupgrade -T` "Signature check OK", 약 95초 만에 접속 |
| 부팅 | 커널 `6.18.55-w1700k-mlo-r32`, 커널 경고 0, NPU 버전 0.1111 응답 |
| 유선 링크 | eth0 10G(내부), lan2 2.5G, wan 1G(RTL8261CE), lan3·lan4 up, 인터넷 정상 |
| 무선 | MLO 5 GHz(ch36)·6 GHz(ch37) 160 MHz, 2.4 GHz. 송신 출력 23/18/23 dBm |
| Mac 재연결 3회 | 매번 MLO 두 링크(valid_links 0x0006, primary 6 GHz) |
| 브리지 오프로드 | 오프로드 흐름 204개 |
| Mac 무선(iperf3 4흐름 30초, 2.5GbE 서버) | 하향 1,979·1,972·2,006 Mbps, 상향 1,839·1,838 Mbps |
| Mac → 공유기 CPU(iperf3 4흐름 20초) | 575 Mbps (이전 버전의 무선 기준값 없음) |

- 핫스팟에서 OpenWrt로 다시 붙은 직후 첫 하향 회차는 919 Mbps였고, 14~29초 구간에 0.05~0.5 Gbps로
  떨어졌습니다. 이후 세 회차는 1.97~2.01 Gbps였습니다. r49·r51에서 본 접속 직후 저하와 같은 양상이며 원인은
  확정하지 않았습니다.

## 알려진 제약

r51과 같습니다([r51 기록](../mlo-r51/README.md)).
