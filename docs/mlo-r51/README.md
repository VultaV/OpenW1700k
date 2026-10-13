# r51 — mt76 2026-10-08

r50 위에서 mt76 드라이버만 `01367e60`(2026-09-01)에서 `639e1287`(2026-10-08)로 올린 후보입니다.
커널(6.18.55)과 무선·NPU 펌웨어는 r50과 같습니다. 2026-10-13 실제 장치에 설치해 확인했습니다.
MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.

## 바뀐 점

- upstream mt76 커밋 90개: MLO 단말 링크(돌아오는 링크 복원, 대표·보조 링크 선택, 링크별 BA 설정, 링크
  제거 시 wcid 정리), 여러 라디오를 한 번에 스캔, NPU 장치의 송신 BA 타이머 갱신, PLE 레지스터 오프셋,
  펌웨어 이벤트 길이 검증, 재시작 중 스캔 거부, SKU 출력 제한 켜기 등.
- 포크 패치:
  - 0030(링크 선택자 복원), 0031(링크 할당 실패 시 WCID 반환), 0035(NPU BA 타이머)는 upstream이 같은
    버그를 고쳐 뺐습니다.
  - 0009·0021·0022·0024: upstream이 hw-queues 출력을 링크별 PHY로 다시 써서 진단 줄을 새 구조에 맞췄습니다.
    링크 상태 줄은 PHY 조회 전에 출력해 채널이 없는 링크도 보입니다.
  - 0010: upstream이 SKU 출력 제한 명령과 켜기를 넣었으므로 중복 코드를 빼고, 포크의 백오프 표 업로드와
    `sku_limit_en`·`sku_path_en` 스위치(r50에서 실기기 확인)를 유지했습니다.
  - 0032: upstream `change_links`가 링크 동기화·되돌리기를 직접 하므로 TXQ 재설정을 그 성공 경로로 옮겼습니다.
  - 나머지는 fuzz 없이 갱신했습니다.

## 검증 (호스트)

- `test_mt76_npu_rx.py`(수정 전 실패·수정 후 통과), `test_mt76_ps_wake.py` 29개, `test_mt7996_mlo_ps.py` 99개,
  `test_mt7996_active_link.py`(SLO·MLO·제거된 링크·채널 없음), `test_mt7996_forward_path.py` 48개,
  `test_mt7996_npu_aggregation.py` 18개(0035 없이 upstream 수정으로 통과) 통과.
- mt76 컴파일 경고 없음. 이미지: r50 대비 패키지 차이는 mt76 kmod 5개, 커널 모듈 차이는 `mt76.ko`,
  `mt76-connac-lib.ko`, `mt7996e.ko` 3개. 무선·NPU 펌웨어는 설치된 r50과 같음. `fit_check_sign` 통과.

## 실기기 확인 (2026-10-13)

| 항목 | 결과 |
|---|---|
| 설치 | r50에서 설정 유지, `sysupgrade -T` "Signature check OK", 약 80초 만에 부팅 |
| 펌웨어·NPU | WM 20260721, NPU 예산 가드 적용, NPU 버전 응답, 커널 경고 0 |
| 무선 | 세 라디오, MLO 5 GHz·6 GHz 160 MHz. 5 GHz는 DFS CAC(약 1분) 뒤 켜짐 |
| 송신 출력 | 5 GHz 23, 6 GHz 18, 2.4 GHz 23 dBm (r50과 같음) |
| 진단 | hw-queues의 단말·링크·txfree·ps_transitions 출력 정상 |
| Mac 재연결 3회 | 매번 MLO 두 링크(primary 6 GHz, secondary 5 GHz)로 연결 |
| 스캔 | `iw` 6 GHz 스캔은 BSS를 찾음. 5 GHz·전체 스캔은 `Resource busy`(DFS 채널 운용 중). iwinfo 경로(채널 분석 화면)는 여전히 0개 |
| 브리지 오프로드 | 흐름 160개 오프로드 |
| Mac 무선(6 GHz 160 MHz, iperf3 4흐름 30초) | 하향 1,954·1,868·1,980 Mbps(500 Mbps 미만 구간 0), 상향 1,809·1,791 Mbps |

상향은 r48(1,604·1,622 Mbps)보다 높게 나왔지만 측정 시점의 AWDL 상태가 달라 직접 비교하지 않습니다.
