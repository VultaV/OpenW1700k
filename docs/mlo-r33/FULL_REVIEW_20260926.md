# W1700K 전체 변경 및 신규 패치 검토 — 2026-09-26

사용자 요청에 따라 추가 무선 실물 시험을 종료하고, 현재 수정본의 커널·mt76·NPU·오프로딩·설정 UI·배포 경로와 새 공개 자료를 검토했다. **기존 F01–F10 중 F04의 핵심 경로는 수정됐고 9건은 남아 있다.** 별도로 NPU watchdog의 실제 코드 결함과 빌드 기록 재사용 위험을 확인했다. 이 숫자는 프로젝트 전체의 결함 총수가 아니다.

검토 기준은 공개본 `01538019f51d8f712aed65161480a6b39fd07411`, r33 manifest, 실제 r32 prepared source다. 실행 중 장비는 `6.18.44-w1700k-mlo-r32` + `bridge-flow-offload 1.0-r3`이며, r33 전체 이미지의 부팅을 검증한 것은 아니다. 이번 작업은 소스·이미지 검사와 장비 상태 조회이며 설정 변경·재부팅·설치·추가 무선 시험은 하지 않았다.

## 1. 새 공개 빌드와 실제 파일 비교

최신 일반 UBI2는 [ubi2_2026.09.26_r36602-54e453b074](https://github.com/w1700k/builds/releases/tag/ubi2_2026.09.26_r36602-54e453b074)다. 9월 26일 18:03:58 KST 공개됐으며 source는 `54e453b074fc243c33f6b6cc36f6b4e8a176aa45`, kernel은 **6.18.52**다. `kernel73` 시험 빌드도 별도로 공개됐지만 이 검토의 적용 기준은 일반 UBI2다.

- sysupgrade 이미지: 22,180,671바이트.
- SHA256: `3f474396b2f55781d02d05986767fb61847ab29ed5fd51ae5af835814a0e5e4e`.
- GitHub asset digest와 다운로드 파일이 일치한다. FIT의 kernel·DTB·rootfs 세 노드 해시도 모두 검증했다.
- 9월 24일 UBI2와 비교한 **일반 펌웨어 파일 12/12개가 바이트 동일**하다. NPU program/data, MT7996 WM/WA/DSP/ROM/EEPROM, regdb, PHY firmware를 포함한다. 이전 r32 비교에서는 공통 11개가 동일했고, `rtl8261c.bin`은 UBI2 쪽 추가 파일이었다.
- mt76 source와 패치 디렉터리, hostapd, linux-firmware recipe, FlowSense는 9월 24일과 동일하다. 커밋 목록의 새 날짜는 리베이스 결과도 포함하므로 신규 기능으로 세지 않았다.
- 두 소스의 최종 Git tree를 직접 비교한 차이는 **34개 파일**이며 Airoha target의 새 차이는 아래 **995·996 두 패치**다. FlowSense 호환성 문구는 이번에 새로 추가된 코드가 아니다.
- `w1700k/fastbuild`의 main은 7월 2일 `bb2e64fe...`로 동일하다. 빌드 자동화와 펌웨어 소스의 갱신을 구분한다.

### 새 패치의 채택 판단

| 패치 | 실제 범위 | 현재 수정본과의 관계·우선순위 |
| --- | --- | --- |
| [995: bridge TTL](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/3f2d49ccbedaa7b8e2f3bd32791993dc9a57e380) | `PPE_PKT_TYPE_BRIDGE`의 TTL 감소 비트를 제거 | 순수 L2 항목 보완. 현재 IPv4 TCP 가속은 `IPV4_HNAPT`이므로 **우리 KEEP_TTL을 대체하지 못한다**. 소프트웨어 경로 보존도 별개다. |
| [996: cross-ingress L2 충돌](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/e5bf0ec29452477e6a1d75ad98ec8b4ab1f8f05e) | 동일 MAC 쌍에서 10초 안에 다른 입력 포트를 관측하면 L2 가속을 거부하고 하위 흐름 제거 | 현재 없는 보호다. L4 tuple 경로에는 guard가 적용되지 않아 IPv4/IPv6 전체 충돌 방지를 보장하지 않는다. 자체 PPE 소유권·슬롯·FDB 수정과 병합 검토 필요. |
| [NPU watchdog IRQ/work 수명](https://github.com/torvalds/linux/commit/4bdee8060d1e4581624e68fbd369b1afb14df4bc) | probe 초기 IRQ와 remove/probe 실패 때 작업 재등록·해제 후 접근 방지 | **백포트 우선순위 높음.** 현재 r32 및 9월 26일 UBI2 Airoha 소스에 동일 결함 패턴이 남아 있다. 정상 운용 중 Air 멈춤을 고친다고 입증된 패치는 아니다. |
| RX31 IRQ·HW GRO·RX ring·DMA mask | 9월 25일 이미 비교한 수신 정확성·안정성 보완 | 여전히 채택 후보다. 이번 새 발견으로 다시 세지 않는다. RX31 DONE=0 관측 때문에 Air 멈춤 원인으로 확정할 수 없다. |

995·996은 9월 24일의 실제 적용 Airoha 소스 복사본 위에 **2/2 적용 성공, fuzz 0**을 확인했다. 이는 우리 커스텀 트리에 대한 병합·전체 커널 컴파일·API/ABI 검증이 아니다. upstream PPE 전체를 교체하면 자체 소유권·슬롯·FDB·KEEP_TTL 수정을 잃을 수 있다.

996의 입력 포트 보호는 L2 parent MAC 쌍에만 걸린다. 새 upstream의 IPv4/IPv6 처리 경로는 tuple 일치 후 먼저 commit하고 종료하므로 해당 guard를 지나지 않는다. 복수 ingress에서 동일 tuple을 쓰는 토폴로지의 보호 공백은 별도 검토 대상이며, 현재 단순 LAN→Air 측정의 원인이라고 판단하지 않는다. 10초 휴리스틱을 보안 격리 보장으로 설명해서도 안 된다.

## 2. 현재 남아 있는 코드·배포 문제

F 번호는 2026-09-22 검토와 동일하다. 파일 위치는 공개본 기준이며, mt76/rpcd/실제 LuCI feed는 prepared source 기준이다.

| ID | 우선순위·상태 | 트리거와 영향 | 코드 근거 |
| --- | --- | --- | --- |
| F01 | P1 조건부 · 미해결 | Wi-Fi 읽기만 가진 위임 계정이 `wifi down` 등 변경 명령 실행 가능. 그런 계정이 실제 있다는 증거는 없음 | `luci-app-wifi7/.../acl.d/luci-app-wifi7.json:16–22`; rpcd `file.c:1060–1082` |
| F02 | P2 · 미해결 | secondary 링크 제거 후 보존 링크를 재활성화하면 `seclink_id`가 primary로 남음. 호스트 WCID 선택·두 링크 PS 가드가 잘못 fallback 가능 | mt7996 `main.c:1347–1348,1394–1397,1452–1453` |
| F03 | P2 · 미해결 | secondary WCID 예약 뒤 `kzalloc` 실패 시 bitmap 반환 누락. 메모리 압박 중 반복 실패하면 슬롯 소진 가능 | mt7996 `main.c:1258–1293,1434–1435` |
| F04 | 핵심 수정됨 | fw4와 공유 생성기, net/iface hotplug, 실패 시 자체 테이블 제거로 갱신 경로 보완. IPv4 TCP 및 허용한 포트 범위에 한정 | `bridge-flow-offload/.../apply-rules.sh:99–154`, `90-bridge-flow-offload:12–17` |
| F05 | P2 · 재현됨 | UCI set/commit 실패를 삼킨 뒤 Wi-Fi 재시작. 적용 성공 오인·불필요한 중단 | WiFi7 `index.js:762–768,1205–1222` |
| F06 | P2 · 재현됨 | 비활성 MLO 프로필에도 활성 라디오 2개를 강제하여 저장 거절 | MLO `mlo.js:541–553` |
| F07 | P2 · 재현됨 | 편집은 마지막 MLO 프로필, 상태는 첫 프로필 데이터. 꺼진 유일한 프로필 선택도 상실 | WiFi7 `index.js:637–650` |
| F08 | P2 · 미해결 | UCI 이름에서 MLD netdev를 추정해 사용자 지정 ifname·복수 프로필 상태 오인 가능 | WiFi7 `index.js:291–298`; `wireless.uc:mlo_vif_create()` |
| F09 | P2 · 미해결 | 실제 빌드 LuCI GitHub 업데이트 UI 수정이 공개 feed patch/manifest에 없음. 깨끗한 재빌드로 동일 UI 재현 불가 | `docs/mlo-r33/build-manifest.json:84–88`; 실제 feed `overview.js` 미커밋 변경 |
| F10 | P2 · 재현됨 | 호환 업데이트 이미지가 없을 때 undefined 역참조. 기존 단일 non-factory fallback도 제거됨 | 실제 feed `overview.js:170–177,395–402` |
| N01 | P1 조건부 · 새 확인 | NPU IRQ가 초기화 전 work를 예약하거나 remove 뒤 work를 다시 예약해 UAF 가능. probe/remove 오류 경계 | r32 `airoha_npu.c:804–809,865–876`; 공식 `4bdee806...` |
| N02 | P2 운영 위험 · 새 확인 | r33 build.py가 입력 해시 없이 과거 성공 step을 재사용. 같은 폴더에서 소스 수정 후 재실행하면 필요한 빌드 생략 가능 | 로컬 `artifacts/mlo-bridge-compat-r33-2026-09-24/build.py:23–27` |

N01의 해결 방향은 work의 자동 정리를 IRQ 등록보다 먼저 등록하고 devres 역순 해제를 이용하는 것이다. 필요한 `devm_work_autocancel()` helper는 현재 6.18.44에도 있다. 이번에는 소스에 적용하지 않았다.

N02는 **다음 버전 빌드의 위험**이다. 이미 해시·내용 검증을 통과한 r33 이미지가 잘못됐다는 증거는 아니다. 새 r 버전은 새 기록 디렉터리를 사용하고 OpenWrt make의 의존성 검사를 실행해야 한다.

F09도 구분이 필요하다. manifest에 기재된 커스텀 소스 41개는 공개본과 실제 빌드 트리 각각 모두 일치한다. 그러나 목록에서 빠진 feed UI 수정까지 재현 가능하다는 뜻은 아니다.

## 3. 아직 결함·증상 원인으로 확정하지 않은 경계

- **primary 변경 후 TXQ 재스케줄:** 이전 primary 때문에 멈춘 큐를 현재 완료 경로가 깨우지 않는 모델 사례가 `tests/test_mt76_ps_wake.py:456–461`에 제한으로 남아 있다. 다른 wake 이벤트가 실물에서 복구하는지 미확인이다.
- **RRO 삭제 오류:** mt7996 `init.c:1186–1216`은 NPU 삭제·WM reset 실패 반환값을 버리고 항목을 해제한다. timeout/할당 실패 경로는 실제 존재하지만 실제 stale session이나 Air 멈춤은 입증되지 않았다. 9월 17일에도 기록한 기존 경계다.
- **PPE 삭제 오류:** SRAM clear 실패 후 객체 정리를 진행하는 경계가 남는다. 소유권·FDB 개선이 완전한 오류 재시도를 제공하지는 않는다.
- **상시 진단 비용:** TXQ 순회와 atomic TXFREE/TXS 카운터는 trace OFF에서도 실행된다. 정리 후보지만 가속 후 약 2Gbps와 낮은 CPU가 관측됐으므로 과거 1.1Gbps 상한 원인으로 계속 분류하지 않는다.
- **소스 경로 차이:** `OpenW1700k`는 mt76 release14/11패치, 현재 build/public 트리는 release26/21패치다. 다음 빌드의 경로·manifest를 명시해야 한다. 현재 산출물의 해시 불일치는 발견하지 못했다.
- **Air 절전 복귀 멈춤:** 기존 실패 기록은 유지한다. CPU·가속 문제가 해결된 것과 간헐 정체의 원인 규명은 별개다. 이번 요청에 따라 추가 Air 준비·잠금·Start를 요청하지 않는다.
- **FDB 로그:** 현재 상태 조회의 최근 로그에 switch FDB 삭제 `-ENOENT`가 있다. 이미 없는 항목의 중복 삭제일 수 있어 새 유선 장애나 Air 정체의 원인으로 분류하지 않는다.

## 4. mt76·NPU·커뮤니티 신규 정보

### mt76와 커널

공식 mt76 master는 9월 1일 `be5ce7910521492d4a2e4ce7ee3843680a46c047`이다. 사용 중 포크 `01367e60...`는 이를 기반으로 한다. 새로 병합된 MT7996 수정은 이번 조회에서 확인하지 못했다.

- [PR #1126](https://github.com/openwrt/mt76/pull/1126): in-band discovery interval을 0으로 바꿀 때 firmware disable 명령 누락 보완. 현재 코드에도 관련 경로가 있으며 **open** 상태다. 8월 제안이고 오늘의 신규 패치나 MLO 속도 수정은 아니다.
- [PR #1125](https://github.com/openwrt/mt76/pull/1125): STA 제거 전 WCID/TXQ 정리 순서 제안, **open**. MLO 전용 제거 및 자체 패치와 관계를 확인해야 한다.
- 9월 24일 PR #1138은 mt7603/mt76x02/mt76x2 대상이므로 MT7996 적용 후보에서 제외한다. 기존 PS-sync TLV 길이 검사는 현재 소스에 있어 누락된 새 수정으로 세지 않는다.
- 공식 stable은 [Linux 6.18.54](https://github.com/gregkh/linux/commit/1b357ecb321392158d507b04672ffee57bfa071d)까지 공개됐다. 전체 변경 감사·clean build는 별도다. OpenWrt의 mac80211은 별도 backports 패키지이므로 커널 숫자만 올려 무선 수정까지 반영됐다고 판단하지 않는다.

### NPU 바이너리와 재구현 프로젝트

공식 linux-firmware 9월 25일 HEAD의 [Airoha tree](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/+/a06a853ae6c43f66bc0e3d3ba6d12efc5fd95c9c/airoha/)는 기존과 동일하다. 공식 MT7996 tree도 20260910 이후 동일하다. 단, **공식 MT7996 Wi-Fi 바이너리와 사용 중 포크 바이너리가 같다는 뜻은 아니다.** 오늘 UBI2에 새 NPU/MT7996 바이너리가 없다는 결론은 실제 이미지 비교에서 별도로 확인했다.

[airoha-npu-fdk](https://github.com/hurryman2212/airoha-npu-fdk)는 8월 9일 초기 커밋 상태이며 공개 릴리스가 없다. [ClankerNPU](https://github.com/ClankerConstruction/ClankerNPU/blob/6d0cd8ae9f6f324a82faa68352624f7cbc237e37/README.md)는 9월 23–26일 구현이 진전됐다. 예전의 “eagle fast path stub, NPUTX default 0” 평가는 현재 상태에 적용하면 안 된다. 현재 기본값은 1이다. vendor 원본 소스가 아닌 재구현 프로젝트이며, 확인한 실기기 검증 대상은 AN7583+MT7993이다. W1700K AN7581+MT7996 검증 자료는 확인하지 못했다.

[새 errata](https://github.com/ClankerConstruction/ClankerNPU/blob/6d0cd8ae9f6f324a82faa68352624f7cbc237e37/docs/errata.md)는 kite/MT7996 계열 pipeline에 대해 TDMA ring full 시 mutex 미해제(E2), 잘못된 pool 반환으로 buffer ID 유실(E3)을 주장한다. 그러나 **원본 firmware 파일명·SHA256·함수 주소·명령어가 없다.** 기존 분석본은 `TLB7.7.0.0_v03`, 해당 소스 문자열은 `TLB7.8.0.0_v003`다. 따라서 우리 바이너리에서 같은 결함을 확인했다고 말할 수 없다. 조사 후보로만 유지한다.

오늘의 [station queue/CoDel 제한](https://github.com/ClankerConstruction/ClankerNPU/commit/faa1cd244cf7220040c9399ad792fcea3a1c1b1b)은 eagle 경로다. MT7996 kite의 수정으로 가져오거나 현재 vendor firmware 대신 설치할 근거가 되지 않는다. WM/WA/DSP의 암호화된 PS/TX 구현은 여전히 직접 검증 범위 밖이다.

### 포럼·토론

[GitHub Discussion #25](https://github.com/w1700k/builds/discussions/25#discussioncomment-18559604)의 9월 22일 보고는 복수 VLAN과 외부 라우터를 거치는 토폴로지에서 루프·라우터 우회·TTL 감소를 설명한다. 9월 26일 관리자가 별도 버그 주제로 옮길 것을 요청했다. 실제 코드의 MAC 쌍 L2 키와 L4 tuple 키는 구분해야 하며, 해당 보고를 단순 LAN→Air와 동일한 장애로 보지 않는다.

[Discussion #34](https://github.com/w1700k/builds/discussions/34#discussioncomment-18608758)는 오늘 OpenWrt 포럼 글 473으로 안내한 뒤 시험 결과를 옮기겠다는 답변까지 확인했다. 새 안정성 수치가 게시됐다고 해석하지 않는다. OpenWrt 포럼 두 주제는 웹 도구 접근 실패 및 직접 JSON 조회 HTTP 403으로 최신 본문을 확보하지 못했다. **포럼에 새 정보가 없다고 판단한 것이 아니다.**

## 5. 검사 결과와 다음 수정 순서

| 검사 | 결과 | 한계 |
| --- | --- | --- |
| 브리지 규칙 생성기 | **21 PASS / 0 FAIL / 0 WARN / 0 SKIP, 100%** | 로컬 stub 기반, 실물 전체 네트워크 검증 아님 |
| manifest 소스 41개 | 공개본 41/41, build source 41/41 해시 일치 | 목록에서 빠진 LuCI feed 변경은 별도 F09 |
| 기존 UI 재현 2개 스크립트 | F05/F06/F07/F10 재현 | 성공 종료는 결함이 남아 있다는 뜻 |
| 새 이미지 | asset 크기/SHA256·FIT 3개 노드 정상, 펌웨어 12/12 동일 | 설치·부팅·성능 검사 아님 |
| 신규 995·996 적용 | 2/2, fuzz 0 | upstream Airoha 복사본만, 커스텀 병합·전체 컴파일 아님 |
| 장비 읽기 전용 상태 | uptime 2일 3시간, overlay 34% 사용·221.8MiB 여유, available RAM 약 1.52GiB, LAN2 2.5Gbps·LAN4 1Gbps carrier 정상 | 한 시점 상태이며 장기 메모리 누수·유선 무중단 증명 아님 |

다음 수정은 **F01 권한 → F09/F10 재현 가능한 업데이트 UI → F02/F03 작은 드라이버 정리 → N01 및 RX/GRO 후보 병합 → 나머지 UI 오류** 순서가 적절하다. 빌드 기록 재사용을 막고 현재 PPE·TTL 보호를 보존해야 한다. cross-ingress 보호는 토폴로지·L2/L4 적용 범위를 정리한 뒤 별도로 다룬다.

이번에는 전체 clean build, r33 이미지 부팅, WAN/IPv6/UDP/VLAN/QoS/Tailscale 전체 기능 시험, 모든 패키지 CVE 감사는 수행하지 않았다. 무선 시험을 더 하지 않아도 정적 결함 수정과 로컬 회귀 검증은 계속할 수 있다. 간헐 Air 멈춤은 해결 완료로 표시하지 않는다.

로컬 원본 근거는 `artifacts/full-review-2026-09-26/`에 저장했다. 공개 요약은 이 문서와 같은 `docs/mlo-r33` 폴더의 `REVIEW_VALIDATION_20260926.json`, `UPSTREAM_20260926_IMAGE_VALIDATION.json`이며, 개인 설정·단말 식별자·원시 패킷·자격 증명은 포함하지 않는다.
