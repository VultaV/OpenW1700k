# r52 — upstream 0 dBm 송신 출력 수정과 mt7530 VLAN 백포트

r51 위에 OpenWrt upstream 커밋 두 개만 더한 버전입니다. mt76 드라이버, 무선·NPU 펌웨어, 커널 버전과 설정은
r51과 같습니다. 2026-10-16 실제 장치에 설치해 부팅만 확인했고, 무선 처리량과 바뀐 기능의 실측은 아직 하지
않았습니다. MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.

## 바뀐 점

- `5ee6f1fdbe` wifi-scripts: UCI `txpower`를 0으로 두면 auto로 처리되던 문제를 고칩니다
  (`if (config.txpower)` → `if (config.txpower != null)`).
- `3a985c7398` kernel: Linux v7.1의 mt7530 VLAN 수정 두 개를 백포트합니다(`721-01` VLAN-aware 브리지를 없앤 뒤
  CPU 포트를 VLAN-unaware로 되돌림, `721-02` VLAN-aware 브리지의 PVID를 untag). 이 장치의 스위치 드라이버
  (`kmod-dsa-mt7530`, `kmod-dsa-mt7530-mmio`)에 해당합니다.
- 두 커밋은 w1700k/builds `ubi2-oc` 2026-10-14 빌드가 바탕으로 쓴 OpenWrt main에서 가져왔습니다. 그 빌드의
  CPU 오버클럭은 넣지 않았습니다.

## 빌드

- r51 트리에서 cherry-pick(`-x`) 두 개. 커널 패치는 모두 적용되었고 기존 `746`(mt7530 리셋 GPIO) 패치만
  13줄 오프셋이 생겼습니다(fuzz 없음).
- 패키지 manifest는 r51과 같습니다. 바뀐 파일은 `mac80211.sh`와 mt7530 모듈 두 개입니다.

## 실기기 확인 (2026-10-16, 원격)

| 항목 | 결과 |
|---|---|
| 설치 | r51에서 설정 유지, `sysupgrade -T` "Signature check OK", 약 95초 만에 접속 |
| 부팅 | 커널 `6.18.55-w1700k-mlo-r32`, 커널 경고 0, NPU 버전 0.1111 응답 |
| 무선 | MLO 5 GHz(ch36)·6 GHz(ch37) 160 MHz, 2.4 GHz. 송신 출력 23/18/23 dBm(r51과 같음) |
| 유선 | wan·lan2·lan3·br-lan up, 인터넷 연결 정상 |
| 0 dBm 수정 | 이미지의 `mac80211.sh`에 반영됨을 확인. 실제 0 dBm 적용은 아직 시험하지 않음 |

## 남은 확인

- Mac MLO 재연결과 iperf3 처리량.
- 2.4 GHz `txpower 0` 적용 확인.
- VLAN 구성은 쓰지 않으므로 mt7530 백포트는 기존 브리지 동작에 회귀가 없는지만 볼 수 있습니다.

## 알려진 제약

r51과 같습니다([r51 기록](../mlo-r51/README.md)).
