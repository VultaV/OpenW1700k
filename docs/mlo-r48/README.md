# r48 — 커널 6.18.55

r46의 사용자 영역 위에서 커널만 6.18.44에서 6.18.55로 올린 후보입니다. 커널 ABI는
`6.18.55-w1700k-mlo-r32`로 바뀌어 모든 kmod를 다시 빌드했습니다. 무선·NPU 펌웨어는 r46과 같습니다.
MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.

## 바뀐 점

- upstream OpenWrt가 6.18.45–6.18.55 업데이트에서 지운 패치(stable에 흡수) 77개를 지우고, 이 트리가 업데이트
  전 판 그대로 쓰던 generic·airoha 패치 113개를 upstream이 갱신한 판으로 바꿨습니다. airoha config에서
  upstream이 지운 SCPSYS 두 줄도 지웠습니다.
- 포크 패치 갱신:
  - 675-02(브리지 오프로드): 6.18.55가 경로의 출력 장치를 기록하고 방향마다 따로 경로를 찾도록 바뀌었습니다.
    이를 유지하면서, 어느 방향이든 경로를 못 찾은 브리지 흐름은 전처럼 오프로드하지 않습니다.
  - 675-03(브리지 conntrack VLAN·PPPoE): 6.18.55의 `nf_reset_ct` 추가는 패치의 notrack 경로가 이미 수행합니다.
  - 992-20(airoha 안정화): stable이 넓힌 `RX_IRQ1` 마스크(31번 큐)를 유지하고, 패치는 `RX_IRQ0`만 바꿉니다.
  - 9999-z3(NPU 워치독 작업 수명): 6.18.55에 들어 있어 뺐습니다.
- `bridge-flow-offload`가 검증된 커널 목록에 `6.18.55-w1700k-mlo-r32`를 추가했습니다.
- mt76 0038: 링크별 `ps_transitions` 진단 카운터(r46 이후 추가).

## 검증

- 새 커널 소스로 `test_bridge_ttl.py`(구조 12, 추출 C 2,091건), `test_bridge_conntrack_ownership.py`,
  `test_bridge_fdb_cleanup.py`, `test_dsa_fdb_delete.py`(수정 전 실패·수정 후 통과) 통과. `test_bridge_flow_offload.py` 21개 통과.
- 이미지: 모듈 구성·무선/NPU 펌웨어·패키지 목록이 r46과 같음. `fit_check_sign` 통과.
- 실기기(2026-10-08): r46에서 설정 유지 설치, `sysupgrade -T` "Signature check OK", 약 80초 만에 부팅.
  NPU 예산 가드 적용, NPU 버전 응답, 세 라디오와 MLO 두 링크(5·6 GHz 160 MHz), 브리지 오프로드 흐름 72개.
  커널 경고 없음.
- Mac 무선(6 GHz 160 MHz, iperf3 4흐름 30초): 하향 1,939·1,999 Mbps, 한 회차는 AWDL로 보이는 짧은 멈춤과
  함께 1,398 Mbps. 상향 1,125·1,230·1,604·1,622 Mbps.

## 빌드

[r44 절차](../mlo-r44/README.md)와 같고 `r48.config`와 `build-manifest.json`을 씁니다. 커널 소스는
`linux-6.18.55.tar.xz`(SHA256 `f4106380…24df9`)입니다.
