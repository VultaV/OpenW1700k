# 2026-10-03 펌웨어 측 수정 후보 — r43 기반, 실기 미검증

`codex/mlo-r30-bridge-offload`(`0b91431404`, r43 소스 + 문서) 위의 로컬 브랜치
`claude/r43-host-fixes`다. 사용자 지시에 따라 내부망·실기기가 필요한 시험은 하지 않았다.
소스·호스트 시험·이미지 빌드로 바로 확인되는 것만 처리했고, 장치가 필요한 항목은 아래
"실기기 시험 대기"에 모았다. 새 r 버전으로 공개하지 않았고 push·설치도 하지 않았다.
MLO 간헐 멈춤과는 관계없는 수정이다.

## 1. r43 공개 소스의 클린 재빌드

대소문자 구분 APFS 볼륨에서 공개 소스만으로 r43을 처음부터 다시 빌드했다(툴체인 포함).
입력: 이 브랜치의 기준 커밋, 고정 피드 3개, 피드 패치 3개(libpfring AR, ovpn 모듈 버전,
LuCI 0003 r2), `docs/mlo-r43/r43.config`, `docs/mlo-r30/overlay` + r43 manifest.
패치한 피드 파일 3개의 SHA256과 defconfig 뒤 `.config`가 r43 기록과 같았다.
Apple clang 21에서 `tools/b43-tools`가 깨져 호스트 전용 패치를 넣었다(대상 이미지와 무관).
Apple clang 21은 생성한 의존성 파일 맨 앞에 `SDKSettings.json`을 넣어 `$<`가 그 파일이 된다.
이 패치는 이 브랜치에 별도 커밋으로 들어 있다.

설치·검증된 r43 이미지(`562c6bae…`)와 비교:

| 항목 | 결과 |
|---|---|
| 커널 모듈 | 74/74 바이트 일치, 기록된 해시와도 74/74 |
| 무선·NPU·PHY 펌웨어 | 11/11 일치 |
| wpad/hostapd, DTB | 일치 |
| 커널 | 크기 같음. 다른 444바이트는 툴체인 표기(`r0+1-73c3ab3081` 대 `r36182-6d74443bce`), 빌드 시각, 이를 반영한 build-id·vDSO 주석뿐 |
| LuCI `status/channel_analysis.js` | **r43 이미지에 공개되지 않은 로컬 수정이 있다**(iwinfo `scan` RPC, 무선 네트워크 ifname 매핑, 대역 필터). upstream `e81743d`·`289a726`의 파일(sha `30dc22f`)과 공개 패치 어디에도 없다 |
| LuCI 패키지 버전 | r43 이미지는 `26.250.72430~e81743d`, 재빌드는 `26.253.65031~289a726`. 실제 r43 빌드의 LuCI 피드 HEAD가 manifest의 `289a7260`이 아니라 `e81743d`였다. 설치된 파일 내용은 위 파일 하나를 빼고 같다 |
| CA 번들 | r43은 같은 121개 인증서를 두 번씩 담았다(해시 링크 `*.1` 240개). 신뢰 범위는 같다. 원인은 아래 2절의 ca-certificates 재빌드 결함이며, 같은 트리에서 `make`를 다시 돌려 재현했다 |
| fastfetch | 8 KB 차이, 빌드 환경에 따른 기능 감지 차이 |
| 그 밖의 바이너리·디버그 스크립트 | 빌드 메타데이터, 공백 차이뿐 |

따라서 공개 소스로 r43의 커널·모듈·펌웨어·무선 데몬은 재현되지만, 채널 분석 화면은
재현되지 않는다(검토 문서 F09와 같은 종류). 원본 소스는 마운트하지 않은 옛 빌드 디스크
(`w1700k-build.sparsebundle` + `build.shadow`)의 LuCI 피드에 있을 것으로 보인다.

## 2. 수정한 결함

모든 수정은 수정 전 실패·수정 후 통과하는 호스트 시험이 있고, 작성자와 다른 검증자가
원본에서 결함을 재현한 뒤 수정을 확인했다.

| 패키지 | 결함 | 영향 |
|---|---|---|
| netspeedtest | `arch` 입력이 다운로드 URL을 고르는 sed 스크립트를 바꿔 임의 바이너리를 root로 설치·실행. 다운로드·실행 RPC가 read 권한 | read 권한 계정의 root 실행 |
| w1700k-fancontrol | 소수·`08` 같은 커브 값에서 init 스크립트가 수동 모드로 바꾼 뒤 중단, 재부팅마다 팬 고정 | 과열 위험 |
| w1700k-fancontrol | 상태 JSON에 UCI 문자열을 `printf "%s"`로 넣어 키 덧붙이기 → `innerHTML` | 배포된 쓰기 ACL로 관리자 세션 XSS |
| w1700k-fancontrol | 커브 JSON(`getCurve`·`getAllCurves`)에 UCI 값을 그대로 출력 | 위임 계정이 설정 페이지를 깨뜨림 |
| airoha-npu | `/dev/mem` 읽기·쓰기 ACL, 오버클럭 상한 1600 MHz, 숫자 아닌 값·20자리 값이 범위 검사 우회 후 임의 PLL 값 기록 | 물리 메모리 쓰기, CPU 정지 |
| airoha-flowsense | 1.1.1.1 하드코딩으로 부팅부터 외부 ping. 대상 문자열을 awk 프로그램과 JSON에 그대로 삽입, 위조된 `last_ping`을 root awk 코드로 실행 | 상시 외부 트래픽, root 명령 실행(npu-monitor UCI 쓰기 필요). 데몬이 대상을 검증하고(IPv6 zone `%` 허용) 백엔드는 숫자만 받는다 |
| wifi7 (F01) | ACL 그룹 이름이 core `luci-mod-network-config`에 병합, read 권한으로 `iw`·`hostapd_cli`·`wifi` 실행 | read 계정이 Wi-Fi 중단·WPS 개방 |
| wifi7 (F05) | UCI set/commit 실패를 삼키고 Wi-Fi 재시작 | 실패를 성공으로 표시, 불필요한 중단 |
| wifi7 (F07) | 편집은 마지막 MLD 프로필, 표시는 첫 프로필 | 다른 프로필을 덮어씀 |
| wifi7 (F08) | MLD netdev를 UCI 이름에서 추정(`ap-mld-1`) | 상태·적용 확인이 존재하지 않는 대상을 조회 |
| mlo (F06) | 비활성 MLO 프로필도 활성 라디오 2개를 요구해 저장 거절 | 저장 불가 |
| wifi7·mlo·fan·flowsense | SSID·암호화·장치·모드·ifname·프리셋·대상 문자열이 `innerHTML`로 | UCI 쓰기 위임 계정의 관리자 세션 XSS |
| LuCI 피드 패치 0003 → r3 | GitHub 릴리스 태그 이름이 `innerHTML`로 | 릴리스 저장소 쓰기 권한자의 관리자 세션 XSS |
| ca-certificates (OpenWrt 코어) | `certdata2pem.py`가 기존 `<이름>.crt`가 있으면 `<이름>_2.crt`로 저장한다. 쓰던 빌드 디렉터리에서 다시 컴파일하면 모든 인증서가 중복된다 | 번들 두 배, 해시 링크 중복. 클린 컴파일 뒤 2회 재컴파일: 수정 전 `_2` 3→123개, 수정 후 3·3·3개(인증서 121개 유지) |

LuCI `E()`는 배열이 아닌 문자열 자식을 `innerHTML`로 넣는다(r43 `luci.js` `dom.append`).
기존 시험 하네스의 가짜 `E()`는 문자열을 항상 텍스트로 만들어 이 종류를 놓쳤으므로
하네스도 실제 동작대로 고쳤다.

새 시험: `tests/test_board_luci_apps.py`, `tests/test_wifi7_ui.js`,
`tests/test_board_luci_views.js`. 확장: `tests/test_mlo_ui.js`.

## 3. 수정본 이미지

같은 빌드 트리에서 이 브랜치로 다시 만든 이미지(파일 이름의 `r43` 표기는 config의
`VERSION_NUMBER`를 바꾸지 않아서 남은 것이다. r43으로 배포하면 안 된다):

- sysupgrade SHA256 `090cb848ec7734ea76c203f783295d28fe93c0f6da3121bb7274d4bf478e18f7`, 30,274,410바이트
- 위 1절의 r43 재빌드와 rootfs 비교: 파일 1,799개로 같고 추가·삭제 없음. 내용이 다른 파일은 21개로,
  수정한 앱의 화면·백엔드·ACL·init·설정 18개와 apk DB 2개, `os-release`다. CA 번들은 121개로 중복 없음.
- 커널 모듈은 바뀌지 않았다(검증된 r43과 74/74 일치). DTB 일치. 커널 차이는 빌드 시각 메타데이터뿐이다.
- 호스트 시험(이 브랜치): `test_board_luci_apps.py`, `test_wifi7_ui.js`, `test_mlo_ui.js`,
  `test_board_luci_views.js`, `test_attendedsysupgrade_images.js`(r3 적용 원본 뷰),
  `test_image_metadata.py`, `test_bridge_flow_offload.py`, hostapd 2종 통과.
- 이 빌드 트리의 준비된 mt76·커널 소스로 돌린 드라이버 시험: MLO PS 99/0, active link(`--tx-errors`) 0,
  link lifecycle 631/0, forward path 48/0, link transition(문서화된 한계 재현), NPU aggregation 18/0,
  NPU RED 50 PASS, NPU watchdog·mailbox·budget(24) PASS, PPE ownership 16/0.

## 4. 같은 날 정리한 기록·도구

- `docs/mlo-r34/feed-patches/README.md`: r3 피드 패치 적용 후 SHA256 기록.
- 엔드포인트 양단 캡처 도구: `mac-capture.sh`의 `stop_owned()` 종료 경합으로 정상 캡처가
  `FAILED`로 기록되는 결함을 찾았다(10월 3일 모의 실패와 같은 형태). 원본은 바꾸지 않았고
  검토용 수정 후보를 로컬 `artifacts/endpoint-pair-candidate-20261003/`에 두었다.

## 5. 실기기 시험 대기

망·장치·브라우저가 필요해 하지 않았다. 사용자가 지시하면 진행한다.

이미지·설치
- 이 브랜치로 만든 이미지의 sysupgrade(설정 유지) 후 부팅, LuCI 로그인, 무선·MLO 기동,
  가속 flow와 유선 관리 경로 유지.

LuCI 보안·UI (실제 브라우저)
- wifi7 Overview·Networks·Stations·Diagnostics, MLO 페이지, Fan Status, FlowSense,
  ASU GitHub 목록이 정상 값을 텍스트로 그대로 보여 주는지.
- `ubus call luci-rpc getWirelessDevices`에 MLD 섹션의 `section`·`ifname`이 있는지(F08 전제).
  MLD Save & apply의 폴링이 `Done -- WiFi active`로 끝나는지. Networks 추가로 만든 legacy AP가 뜨는지.
- non-root 계정: `luci-app-wifi7` read만 가진 계정은 메뉴는 보이고 명령 실행·저장은 거부,
  netspeedtest read 계정은 다운로드·측정 거부. 배포 전 `/etc/config/rpcd`에
  `luci-mod-network-config`로 wifi7 메뉴를 쓰던 non-root 계정이 있는지 확인.
- F05 실패 경로: commit 거부 시 `Failed: …` 표시, Wi-Fi 재시작 없음.
- F06: 비활성 MLO 프로필 저장 허용, 활성화 시 2라디오 재검증.
- 팬: 정수 커브 저장·재부팅 뒤 `pwm1_enable=2`, auto point 값(밀리도). 장치 busybox에서
  `40.5`·`08` 입력의 수정 전 중단·수정 후 자동 복귀.
- NPU: 수정 이미지에서만 `setOverclock` 문자열 `99999999999999999999` 거부와 PLL 레지스터
  불변 확인(수정 전 이미지에서는 PLL을 덮어쓰므로 하지 않는다). 1200 MHz 적용 후 readback.
  `/dev/mem` ACL 없이 상태 페이지 로드. PLL 쓰기는 복구 수단을 확보한 뒤에만.
- FlowSense: 새 설치에서 ping 대상이 기본 게이트웨이인지(라우터·AP 모드), route가 없을 때의
  1.1.1.1 대체, 설정 유지 장비는 `uci delete npu-monitor.jitter.target` 뒤 동작. 지연이 60 ms를 넘을 때
  'NPU Bypass Detected' 경고가 여전히 뜨는지. 장치에서
  `echo '{"a":1,"a":"x"}' | jsonfilter -e '@.a'`가 `x`인지(json-c 중복 키 동작).
- netspeedtest: admin에서 aarch64 다운로드·측정(인터넷 필요).
- 팬 커브: `fan.custom.pointN_*`에 따옴표·`abc`·빈 값·`08`을 넣은 뒤 `getAllCurves`가 유효한 JSON이고
  커브 미리보기가 그려지는지. busybox ash에서 `printf %d`에 숫자 아닌 값을 줘도 응답이 이어지는지.
- FlowSense 대상: `fe80::1%br-lan` 같은 링크로컬 게이트웨이가 유지되고 busybox ping이 응답하는지,
  따옴표가 든 대상은 1.1.1.1로 대체되는지.
- 런타임 `sysctl fs.protected_symlinks`가 1인지(`/tmp` 고정 이름 파일의 symlink 공격 방어 전제).

MLO 원인 조사 (인계서 10절)
- iperf3 서버 `192.168.1.118:5203`(CT105)이 10월 3일 응답하지 않았다. 서버 복구 후
  `endpoint-pair` 양단 캡처. 캡처 도구 수정 후보 검토 뒤 sudo 실행.
- 가속 수명: primary 링크 변경 뒤 PPE binding 갱신, RRO/PPE 삭제 오류·복구 오류 주입.
- RX31 IRQ·GRO·ring·DMA mask 업스트림 후보 병합 시험, Air 절전 복귀, 장기 운용, 3링크 MLO.

## 6. 결정이 필요한 항목

- `channel_analysis.js` 로컬 수정의 원본 복구: 옛 빌드 디스크를 shadow와 함께 마운트해야 한다.
  복구 전까지 공개 소스 이미지는 r43과 채널 분석 화면이 다르다.
- LuCI 피드 고정값: r43 manifest의 `289a7260`과 실제 빌드 `e81743d` 중 어느 쪽으로 맞출지.
- 다음 r 버전으로 공개할지. 공개하려면 manifest·검증 JSON 재생성, GitHub prerelease가 필요하다.
- netspeedtest의 Ookla 다운로드는 사용자가 설정한 프록시(`netspeedtest.config.proxy_*`)를 따르고
  실행 비트만 확인한 뒤 root로 실행한다. 다운로드 권한(이 브랜치에서 write로 옮김)과 프록시 설정을
  가진 계정은 바이너리를 바꿔치기할 수 있다. upstream 설계이며 고치지 않았다. 다운로드 기능을 빼거나
  root 전용으로 둘지 정해야 한다.
- 10월 1일 Codex 세션의 `codex/release-hardening-20261001` 후보(로컬 `Documents/Codex/2026-10-01/task/OpenW1700k`)는
  NPU IRQ·RRO·복구 경로와 sysupgrade 레이아웃 검사를 다루지만 빌드되지 않았다. 이 브랜치와 겹치는
  F05–F08을 서로 다르게 고쳤으므로 하나를 골라야 한다.
