# 2026-10-03 펌웨어 측 수정 후보 — r43 기반, 실기 미검증

`codex/mlo-r30-bridge-offload`(`0b91431404`, r43 소스 + 문서) 위의 로컬 브랜치
`claude/r44-candidate`다. `claude/r43-host-fixes`(`d8b02b5a25`)에 10월 1일 Codex 후보
`9ddf8eb185`에서 이식한 변경(2절 W01·W02·0004, 7–9절)을 더했다. 사용자 지시에 따라
내부망·실기기가 필요한 시험은 하지 않았다.
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
| LuCI `status/channel_analysis.js` | r43 이미지에는 공개되지 않은 패키지 패치 `998-single-wiphy.patch`가 들어 있었다(아래 "채널 분석 패치"). 이 브랜치에 넣은 뒤 같은 파일이 바이트 단위로 재현된다 |
| LuCI 패키지 버전 | r43 이미지는 `26.250.72430~e81743d`, 재빌드는 `26.253.65031~289a726`. 옛 빌드 트리의 피드 HEAD도 manifest와 같은 `289a726`이었다. LuCI는 패키지 폴더를 마지막으로 바꾼 커밋으로 버전을 만들므로, 피드 클론 깊이가 다르면 같은 커밋에서도 버전 문자열이 달라진다. 파일 내용에는 영향이 없다 |
| CA 번들 | r43은 같은 121개 인증서를 두 번씩 담았다(해시 링크 `*.1` 240개). 신뢰 범위는 같다. 원인은 아래 2절의 ca-certificates 재빌드 결함이며, 같은 트리에서 `make`를 다시 돌려 재현했다 |
| fastfetch | 8 KB 차이, 빌드 환경에 따른 기능 감지 차이 |
| 그 밖의 바이너리·디버그 스크립트 | 빌드 메타데이터, 공백 차이뿐 |

### 채널 분석 패치

옛 빌드 디스크(`w1700k-build.sparsebundle` + `build.shadow`)를 읽기 전용으로 붙여 확인했다.
붙이기 전후 shadow의 크기·수정 시각·앞뒤 1 MB 해시와 sparsebundle 상태가 같았다.
LuCI 피드의 추적되지 않은 폴더 `modules/luci-mod-status/patches/`에
`998-single-wiphy.patch`(작성 Gilly1970, 2026-06-19, 파일 생성 9월 8일)가 있었다.
MT7996처럼 라디오 여러 개가 한 wiphy를 쓰면 iwinfo가 `radio0/1/2`를 모두 첫 netdev로
해석해 5 GHz 탭이 "No data"가 되는 문제를 고친다. upstream LuCI master에는 아직 없다.

이 패치를 고정 피드 `289a7260`에 넣어 빌드한 `channel_analysis.js`는 r43 이미지의 파일과
바이트 단위로 같다(sha `a059125323f9c969…`). 원본 그대로 `feed-patches/998-single-wiphy.patch`에
보관했다(SHA256 `6b1ac6f1935b046f8028ccfb2ebe159e5b335c1750861202416d402d384d85c9`).
적용 방법은 r43 때와 같다. `./scripts/feeds update -a` 뒤, 빌드 전에:

```sh
mkdir -p feeds/luci/modules/luci-mod-status/patches
cp docs/host-fixes-20261003/feed-patches/998-single-wiphy.patch \
   feeds/luci/modules/luci-mod-status/patches/
```

OpenWrt가 패키지 준비 단계에서 이 폴더의 패치를 적용한다.

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
| wifi7 (W01, 포팅) | MLD config 탭의 Discard에 동작이 없음. 저장 뒤에도 기준값이 로드 시점 값. 후보의 Discard를 그대로 쓰면 목록에 없는 암호화(MLO 페이지의 `psk2` 등)에서 선택 상자가 비고, 저장하면 rpcd가 `encryption`을 지운다 | 편집 취소 불가. 후보 그대로면 개방 AP |
| wifi7 (W03, 독립 검증 전) | 암호화 선택 상자가 목록에 없는 저장값을 첫 항목으로 보이고 저장한다. Networks 탭(2.4·5 GHz)은 첫 항목이 Open이라 표준 Wireless의 `psk2+ccmp`·`wpa2` 등이 `none`이 되고, MLD 탭은 `wpa3-192` 등이 `sae`가 된다. 저장값을 그대로 선택 항목에 넣는다 | Networks 탭 저장만으로 개방 AP |
| wifi7 (W04, 독립 검증 전) | Networks 탭이 `lan`·`wan`·`guest`·`iot` 밖의 네트워크(`guest2` 등)를 `lan`으로 선택해 로드한다. 사용자 지정 입력란은 보이지만 저장은 `lan`을 쓴다. Discard는 이미 `custom`을 고른다. 첫 수정은 리스트 `network`(`luci-app-mlo`가 쓰고 rpcd가 배열로 준다)를 `custom`으로 열어 `["lan"]`을 저장했다. 공백으로 이은 문자열로 다룬다 | 저장만으로 손님 SSID가 LAN 브리지로. 첫 수정은 MLO를 끈 프로필을 어느 브리지에도 붙이지 않음 |
| wifi7 (W02, 포팅) | Save & apply가 로드 시점의 netdev로 hostapd를 폴링. MLO를 끈 프로필은 `hostapd.undefined`, 로드 때 꺼져 있던 MLD는 추정 이름 | Wi-Fi가 떠도 3분 뒤 재부팅 권고 |
| mlo (F06) | 비활성 MLO 프로필도 활성 라디오 2개를 요구해 저장 거절 | 저장 불가 |
| wifi7·mlo·fan·flowsense | SSID·암호화·장치·모드·ifname·프리셋·대상 문자열이 `innerHTML`로 | UCI 쓰기 위임 계정의 관리자 세션 XSS |
| LuCI 피드 패치 0003 → r3 | GitHub 릴리스 태그 이름이 `innerHTML`로 | 릴리스 저장소 쓰기 권한자의 관리자 세션 XSS |
| ca-certificates (OpenWrt 코어) | `certdata2pem.py`가 기존 `<이름>.crt`가 있으면 `<이름>_2.crt`로 저장한다. 쓰던 빌드 디렉터리에서 다시 컴파일하면 모든 인증서가 중복된다 | 번들 두 배, 해시 링크 중복. 클린 컴파일 뒤 2회 재컴파일: 수정 전 `_2` 3→123개, 수정 후 3·3·3개(인증서 121개 유지) |

LuCI `E()`는 배열이 아닌 문자열 자식을 `innerHTML`로 넣는다(r43 `luci.js` `dom.append`).
기존 시험 하네스의 가짜 `E()`는 문자열을 항상 텍스트로 만들어 이 종류를 놓쳤으므로
하네스도 실제 동작대로 고쳤다.

새 시험: `tests/test_board_luci_apps.py`, `tests/test_wifi7_ui.js`,
`tests/test_board_luci_views.js`. 확장: `tests/test_mlo_ui.js`.

### 표준 Wireless 다중 라디오 보호 (LuCI 피드 패치 0004)

10월 1일 Codex 후보 `9ddf8eb185`의 `0004`를 옮겼다. 3절 이미지에는 들어 있지 않다.
고정 LuCI `289a7260`의 Network > Wireless는 wifi-iface `device`를 라디오 하나로만 다룬다.
MLO 섹션(`device` 목록)의 Enable/Disable은 목록을 UCI 섹션 이름으로 넘기고, Edit는 라디오
하나의 옵션으로 모달을 만든다. 단일 라디오 네트워크를 끌 때도 `==` 비교 때문에 MLO 섹션이
아직 쓰는 라디오를 쓰지 않는 것으로 보고 라디오까지 끈다.

패치는 목록 포함 여부로 라디오 사용을 판단하고, 다중 라디오 섹션의 Enable/Disable·Edit 대신
MLO 페이지로 안내하며, 페이지 위에 그 섹션 이름과 MLO 링크를 보여 준다. Codex 원본과 달리
알림 문자열을 배열 자식으로 넘겨 `innerHTML`을 쓰지 않는다. 원본의 `PKG_RELEASE:=2`만으로는
LuCI 패키지 버전이 바뀌지 않으므로 0003처럼 `PKG_VERSION`을 r43 값으로 명시했다
(`26.250.72430~e81743d-r2`). Codex 기록의 Wireless 페이지 전체 공백은 원인을 모르며
이 패치로 고친 것이 아니다.

`./scripts/feeds update -a` 뒤, 빌드 전에 고정 피드에 적용한다(전체 순서는 7절). `git -C`는 상대
경로를 피드 폴더 기준으로 읽으므로 패치는 절대 경로로 준다:

```sh
git -C feeds/luci apply "$PWD/docs/host-fixes-20261003/feed-patches/0004-luci-wireless-multi-radio-guards.patch"
node tests/test_wireless_mlo_guard.js \
    feeds/luci/modules/luci-mod-network/htdocs/luci-static/resources/view/network/wireless.js
```

시험 결과: 고정 원본 1 PASS / 4 FAIL, Codex 원본 3 / 2(알림 `innerHTML`), 이 패치 5 / 0.
`289a7260` 압축본(SHA256 `bd1427266c57ab8c…`)을 새로 풀어 `git apply`·`patch -p1`로 적용했다.

| 파일 (LuCI 피드 기준) | 패치 적용 후 SHA256 |
| --- | --- |
| `modules/luci-mod-network/Makefile` | `f5b4e36e9157deb5b7f0aa2aa8b9552ed49159ba10eec81ce40d96c408dc6fb5` |
| `modules/luci-mod-network/htdocs/luci-static/resources/view/network/wireless.js` | `db180b224bfef20081c3b840610342657edf7a3d6a0f3965a07078808bf46c45` |

패치 파일 SHA256 `f8ad6c3fc8306c3c5a58145f038fe4e160503790b21eda952854644e0a776634`.

## 3. 수정본 이미지

이 절의 이미지와 시험은 `claude/r43-host-fixes`(`d8b02b5a25`) 상태다. 그 뒤 이식한 LuCI 0004·W01·W02
(2절), 피드 잠금(7절), 이미지 구조 검사(8절), GitHub 업데이트(9절)는 들어 있지 않다. 이미지 manifest에
`w1700k-fit-check`가 없고 `luci-app-attendedsysupgrade`는 `-r3`, `luci-mod-network`는 `26.253.65031~289a726`이다.
이 후보 전체로는 아직 이미지를 만들지 않았다. `luci-app-wifi7`은 두 상태 모두 `1.0.0-r20261003`이라
버전으로 구별되지 않는다.

같은 빌드 트리에서 `d8b02b5a25`로 다시 만든 이미지(파일 이름의 `r43` 표기는 config의
`VERSION_NUMBER`를 바꾸지 않아서 남은 것이다. r43으로 배포하면 안 된다):

- sysupgrade SHA256 `4935f90a62acb4e567855649f662c1090b943ec9b2bba83ad2e891fd76f4206f`, 30,274,410바이트
  (채널 분석 패치 포함)
- 위 1절의 r43 재빌드와 rootfs 비교: 파일 1,799개로 같고 추가·삭제 없음. 내용이 다른 파일은 22개로,
  수정한 앱의 화면·백엔드·ACL·init·설정 18개, 채널 분석 화면, apk DB 2개, `os-release`다.
  CA 번들은 121개로 중복 없음.
- 설치·검증된 r43과 비교: r43에만 있는 파일은 중복 인증서 240개뿐이다. 나머지 차이는 이 브랜치의 수정,
  메타데이터(서명 키·버전 문자열·apk DB·공백만 다른 디버그 스크립트), 빌드 환경에 따른 바이너리 7개다.
- 커널 모듈은 바뀌지 않았다(검증된 r43과 74/74 일치). DTB 일치. 커널 차이는 빌드 시각 메타데이터뿐이다.
- 호스트 시험(`d8b02b5a25`): `test_board_luci_apps.py`, `test_wifi7_ui.js`, `test_mlo_ui.js`,
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
- 패키지 피드(7절): sysupgrade(설정 유지) 뒤 `/etc/apk/repositories.d/distfeeds.list`가 주석뿐인지,
  `apk update`가 저장소 0개로 오류 없이 끝나는지, `apk upgrade --simulate`가 아무것도 제안하지 않는지.
  LuCI 시스템 → 소프트웨어의 목록 업데이트·구성 대화상자·설치된 목록. 유지된 `customfeeds.list`에
  snapshot 피드가 없는지.
- 이미지 구조 검사(8절): `command -v w1700k-fit-check`가 있는지, 설치한 이미지와 검증된 r43 이미지에
  `sysupgrade -T`가 통과하는지. 거절 대상(1.0.0 `chainload-uboot.itb` 등)에 `sysupgrade -T -F`가
  `W1700K FIT rejected:`와 "Image check failed."로 끝나는지, LuCI 플래시 화면도 강제 옵션 없이 거절하는지.
- FIT 잠금 탈출(8절): 이 이미지에서 검증된 r43(`562c6bae…`)으로의 sysupgrade(설정 유지)가 받아들여져
  부팅되는지, r43에서 `sysupgrade -T -F`가 예전처럼 강제 가능으로 나오는지, r43에서 다시 이 이미지로
  올라오는지. 시리얼·U-Boot 복구 수단을 확보한 뒤에만.

LuCI 보안·UI (실제 브라우저)
- 0004: Network > Wireless가 MLO 섹션이 있어도 그려지고, 위쪽 알림에 섹션 이름과 MLO 링크가 보이는지.
  MLO 섹션의 Disable·Edit는 알림만 띄우고 설정을 바꾸지 않는지. MLO가 쓰는 라디오의 단일 라디오
  네트워크를 Disable해도 라디오(`wireless.radioN.disabled`)가 켜진 채로 MLO가 유지되는지.
  apk에서 `luci-mod-network`가 `26.250.72430~e81743d-r2`로 올라가는지.
- wifi7 Overview·Networks·Stations·Diagnostics, MLO 페이지, Fan Status, FlowSense,
  ASU GitHub 목록이 정상 값을 텍스트로 그대로 보여 주는지.
- `ubus call luci-rpc getWirelessDevices`에 MLD 섹션의 `section`·`ifname`이 있는지(F08 전제).
  MLD Save & apply의 폴링이 `Done -- WiFi active`로 끝나는지. Networks 추가로 만든 legacy AP가 뜨는지.
- non-root 계정: `luci-app-wifi7` read만 가진 계정은 메뉴는 보이고 명령 실행·저장은 거부,
  netspeedtest read 계정은 다운로드·측정 거부. 배포 전 `/etc/config/rpcd`에
  `luci-mod-network-config`로 wifi7 메뉴를 쓰던 non-root 계정이 있는지 확인.
- F05 실패 경로: commit 거부 시 `Failed: …` 표시, Wi-Fi 재시작 없음.
- GitHub 업데이트(9절): 목록이 `VultaV/OpenW1700k` prerelease를 이미지 버전으로 보여 주고(502 아님)
  "View on GitHub"가 같은 저장소로 가는지. Keep settings를 켠 채 받기·설치. 끈 채(keep=false) 받으면
  `sysupgrade --test -n` 검증을 통과한 뒤 곧바로 설정 초기화 설치로 이어지므로, 설정 백업과 유선 접근
  (192.168.1.1)을 확보한 뒤에만. `keep` 없는 요청이 400인지. apk에서 `luci-app-attendedsysupgrade`가
  `26.250.72430~e81743d-r4`인지.
- W01·W02: MLD config에서 SSID를 바꾼 뒤 Discard가 저장값으로 되돌리는지, 저장 뒤 Discard가 새 값을
  유지하는지. MLO를 끈 프로필(`mlo=0`)과 로드 때 내려가 있던 MLD에서 Save & apply가
  `Done -- WiFi active`로 끝나는지(라디오별 netdev가 모두 ENABLED일 때). `psk2` 프로필에서 로드·Discard 뒤
  암호화 상자가 `psk2`를 보이고 Save & apply 뒤 `wireless.<sid>.encryption`이 `psk2`로 남는지.
- W03: 표준 Wireless에서 `psk2+ccmp`로 둔 2.4 GHz 네트워크를 Networks 탭에서 저장한 뒤
  `encryption`이 `psk2+ccmp`이고 개방 AP가 아닌지.
- W04: `network`가 `guest2`인 네트워크를 Networks 탭에서 열면 `custom`과 `guest2`가 보이고 저장 뒤에도
  `guest2`인지. MLO 페이지에서 만들고 MLD 탭에서 MLO를 끈 프로필(`list network 'lan'`)은 `lan`으로 열리고
  저장 뒤 `uci get wireless.<sid>.network`가 `lan`인지.
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
- 상태 → 채널 분석: 2.4·5·6 GHz 탭이 각자 자기 대역만 보여 주고 5·6 GHz 스캔 결과가 나오는지.
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

- 다음 r 버전으로 공개할지. 공개하려면 manifest·검증 JSON 재생성, GitHub prerelease가 필요하다.
- netspeedtest의 Ookla 다운로드는 사용자가 설정한 프록시(`netspeedtest.config.proxy_*`)를 따르고
  실행 비트만 확인한 뒤 root로 실행한다. 다운로드 권한(이 브랜치에서 write로 옮김)과 프록시 설정을
  가진 계정은 바이너리를 바꿔치기할 수 있다. upstream 설계이며 고치지 않았다. 다운로드 기능을 빼거나
  root 전용으로 둘지 정해야 한다.
- 10월 1일 Codex 세션의 `codex/release-hardening-20261001` 후보(로컬 `Documents/Codex/2026-10-01/task/OpenW1700k`)는
  빌드되지 않았다. sysupgrade 레이아웃 검사, GitHub 업데이트, 피드 잠금, LuCI 0004, MLD Discard·폴링은
  이 브랜치로 옮겼다(2·7–9절). 겹치는 F05–F08은 이 브랜치의 수정을 두고 W01·W02만 얹었다. NPU IRQ·RRO·
  복구 경로, CI, 준비 스크립트·source gate는 옮기지 않았으므로 따로 정해야 한다.

## 7. 패키지 피드 잠금 (Codex 후보 `9ddf8eb185`에서 이식)

r43 이미지의 `/etc/apk/repositories.d/distfeeds.list`는 r43.config의 `CONFIG_VERSION_REPO`(snapshot 주소)로
만든 snapshot 피드 6개를 켠다. kmods 피드는 이 빌드의 vermagic 경로라 upstream에 없다(404). 나머지는 실제로
있다. 10월 3일 snapshot target 피드는 `base-files 1709~9b95be917b`와 `kernel 6.18.54~c5987c5d`를 내놓았다
(이미지는 `6.18.44~73da9a42`). base·packages·luci·routing은 다른 피드 커밋의 rolling 빌드다. 라우터는
snapshot 서명 키(`/etc/apk/keys/openwrt-snapshots.pem`)를 신뢰한다. 그래서 `apk upgrade`나 LuCI 소프트웨어
페이지가 이 패키지들을 이 이미지의 private kernel·kmod ABI 위에 설치할 수 있다.

변경 (커널 ABI는 바꾸지 않았다)
- `package/base-files/Makefile`: APK 분기가 피드 목록 대신 주석만 있는 `distfeeds.list`를 쓴다. 평범한
  `make`에서 r43.config 그대로 적용된다. 준비 스크립트나 `files/`에 기대지 않는다.
- `feeds.conf.release`: r43 manifest의 피드 커밋 3개와 `feeds.conf.default`의 URL.
- `tests/test_package_feeds.py`: 실제 `rules.mk`·`version.mk`·`feeds.mk`와 r43.config로 base-files의 APK
  분기를 실행한다. 수정 전에는 snapshot URL 6줄이 나오고 실패한다. 이 출력은 설치된 r43 이미지의 파일과
  바이트 단위로 같다. 수정 후에는 아래 주석만 남는다. `feeds.conf.release`가 없거나 manifest와 다르면
  실패한다.

```
# This file is auto-generated and build-specific, any changes will be intentionally lost in sysupgrade.
# No remote feed is configured: this W1700K image has its own kernel and kmod ABI.
# OpenWrt snapshot and release packages are not built for it; do not add them.
# Install only packages built from the same source, feeds and .config as this image.
```

이식하지 않은 것
- `scripts/prepare-w1700k-release.sh`: distfeeds는 이제 base-files가 만든다. 스크립트의 나머지 단계는
  이식 대상이 아닌 `build.config`, Codex 원본 LuCI 0004·0005 적용과 묶여 있다. 이 브랜치는 고친 0004·0005를
  아래 순서로 `git apply`한다.
- `CONFIG_VERSION_REPO`를 unpublished 주소로 바꾸는 것: base-files가 더 이상 `%U`로 피드를 만들지 않는다.
  그래서 rootfs에서 이 값을 쓰는 곳이 없다. r43.config는 기록 그대로 둔다.
- `docs/release-hardening/sources.lock.json`: Codex source gate용이다. 피드 커밋은 manifest에 이미 있다.

다음 이미지를 만들 때
1. `cp feeds.conf.release feeds.conf`, `./scripts/feeds update -a`. 피드 패치를 이 순서로 넣고
   `./scripts/feeds install -a`. LuCI는 깨끗한 고정 피드에 0003 r3 → 0005 → 0004 순서다.

   ```sh
   cp docs/mlo-r29/feed-patches/0002-use-target-ar-for-bundled-libraries.patch \
      feeds/packages/libs/libpfring/patches/
   git -C feeds/packages apply "$PWD/docs/mlo-r30/feed-patches/0001-ovpn-backports-set-module-version.patch"
   git -C feeds/luci apply "$PWD/docs/mlo-r34/feed-patches/0003-luci-attendedsysupgrade-github-update.patch"
   git -C feeds/luci apply "$PWD/docs/mlo-r34/feed-patches/0005-luci-asu-keep-and-release-source.patch"
   git -C feeds/luci apply "$PWD/docs/host-fixes-20261003/feed-patches/0004-luci-wireless-multi-radio-guards.patch"
   mkdir -p feeds/luci/modules/luci-mod-status/patches
   cp docs/host-fixes-20261003/feed-patches/998-single-wiphy.patch \
      feeds/luci/modules/luci-mod-status/patches/
   ```

2. `cp docs/mlo-r43/r43.config .config`. 빈 `files/`에 이 커밋의 `docs/mlo-r30/overlay/*`를 복사한다
   (`github_check`·`github_fetch`는 0005와 짝이다, 9절). `files/etc/w1700k-mlo-repair`를
   `docs/mlo-r43/build-manifest.json`으로 바꾼다(r43 기록이다. 공개하려면 새로 만든다, 6절).
   `make defconfig` 뒤 `.config`에 `CONFIG_PACKAGE_w1700k-fit-check=y`가 있어야 한다(8절). 그리고 `make`.
   distfeeds를 위한 추가 단계는 없다. 쓰던 빌드 트리에서도 base-files는 Makefile이 바뀌었으므로
   다시 만들어진다.
3. `files/etc/apk/repositories.d/distfeeds.list`를 두지 않는다. 두면 base-files 결과를 덮는다.
   `docs/mlo-r30/overlay`에는 없다.
4. 빌드 뒤 `grep -v '^#' build_dir/target-aarch64_cortex-a53_musl/root-airoha/etc/apk/repositories.d/distfeeds.list`가
   아무것도 출력하지 않아야 한다.
5. 같은 소스·피드·config·커널로 만든 서명 패키지를 나중에 불변 경로로 게시하면, 그 주소를
   `files/etc/apk/repositories.d/distfeeds.list`에 넣는다.

라우터에서 달라지는 것
- LuCI 시스템 → 소프트웨어(`luci-app-package-manager`): 목록 업데이트는 저장소 없이 `apk update`를 돌린다.
  설치 가능 목록과 업그레이드 목록이 빈다. 이름으로 설치하면 "not available in any configured
  repository"가 나온다. 설치된 목록, 제거, `.apk` 업로드 설치는 그대로다. 구성 대화상자는 위 주석을
  보여 준다. `distfeeds.list`·`customfeeds.list` 편집도 여전히 된다(write ACL). 관리자가 피드를 다시
  넣는 것은 막지 않는다. `distfeeds.list` 편집은 sysupgrade 때 사라지고 `customfeeds.list`는 유지된다.
- owut(r43.config에 포함): 기본 `repositories_mode`가 `append`라 원래 `distfeeds.list`를 읽지 않는다.
  `replace` 모드에서는 이전에 snapshot 피드를 ASU 빌드 요청에 넣었지만, 이제는 넣을 피드가 없다.
  owut는 이미지 전체를 ASU(`sysupgrade.openwrt.org`)에 요청한다. 요청 기준은 os-release 버전이다. 이
  버전 문자열은 upstream 릴리스가 아니고, 받는 이미지에는 W1700K 수정이 없다. 이 변경과 관계없는 경로다.
- `luci-app-attendedsysupgrade`: 이 브랜치의 0003 r3·0005 패치는 GitHub 릴리스 이미지를 overlay CGI
  (`github_check`, `github_fetch`)로 받는다(9절). 피드를 쓰지 않으므로 바뀌지 않는다. 상태 페이지의
  업그레이드 알림(`11_upgrades.js`)은 설정을 켰을 때만 downloads.openwrt.org의 버전 목록을 읽는다. 패키지는 설치하지
  않는다.
- 남는 경로: `openwrt-keyring`의 snapshot 키는 계속 신뢰된다. 사용자가 `customfeeds.list`에 snapshot
  피드를 넣으면 다시 설치할 수 있다. 키를 빼면 패키지 선택이 바뀌므로 이번에는 하지 않았다.

## 8. sysupgrade 이미지 구조 검사 (Codex 후보 `9ddf8eb185`에서 이식)

r43까지 `platform_check_image()`에는 `gemtek,w1700k-ubi` 분기가 없어 0을 돌려줬다. 이 보드의 검사는
fwtool 메타데이터뿐이었고 `sysupgrade -F`로 넘길 수 있었다. 플래시 전에 FIT 해시도, 이 보드의 UBI2
sysupgrade FIT인지도 보지 않았다. UBI1·ubinized 이미지, recovery·chainloader FIT, 다른 보드 이미지를
강제로 쓸 수 있었다.

변경
- `platform.sh`(an7581): W1700K에서 `fit_check_image`(fit_check_sign 해시) 뒤 새 `w1700k-fit-check`를
  돌린다. 실패는 74(깨진 이미지)라 `sysupgrade -F`, LuCI Force, ubus force 플래그로 넘길 수 없다.
  fwtool 메타데이터 검사는 지금처럼 강제할 수 있다. GitHub 업데이트의 `sysupgrade --test`도 이 검사를 거친다.
- `package/utils/w1700k-fit-check`(libfdt): default 구성 하나, gzip 커널·flat_dt·squashfs rootfs가
  파일 안 FIT 헤더 뒤에 겹치지 않게 놓였는지(external-static, rootfs 4 KiB 정렬), DTB의
  `gemtek,w1700k-ubi`, UBI2 `ubi`·`reserved_bmt` 위치·크기, 활성 fixed-partitions → spi-nand →
  en7581-snand 경로와 주소, `chosen/rootdisk`가 `fit` 볼륨인지 본다. ramdisk가 있거나 rootfs가 없는
  recovery FIT는 거절한다. 이미지를 누가 만들었는지는 증명하지 않는다.
- `an7581.mk`: `DEVICE_PACKAGES`에 `w1700k-fit-check`.

호스트 시험: `python3 tests/test_w1700k_fit.py --libfdt <dtc-1.8.1/libfdt> [--image <itb>]`가 ASan/UBSan으로
합성 39개, 변이 400개, platform.sh 분기 4개(도우미가 없어도 74)를 통과한다. 빌드 호스트의 W1700K UBI
sysupgrade 이미지 58개(2026-08 빌드, r43까지의 MLO 시리즈, upstream·재게시 빌드, 3절 이미지, 1.0.0 릴리스,
SNAPSHOT r35753)를 모두 받아들이고, 1.0.0 `chainload-uboot.itb`와 r43에서 만든 recovery·다른 compatible·
UBI1·잘린·squashfs 아닌 이미지는 거절한다. 3절 이미지에는 이 검사가 없다.

주의
- `w1700k-fit-check`가 빠진 이미지는 모든 sysupgrade를 거절한다(도우미를 못 찾아도 74). r43.config에는
  이 패키지 줄이 없으므로 `make defconfig`가 장치 기본 패키지로 켜야 한다. 빌드 뒤 `.config`와 이미지
  manifest에서 확인한다.
- 잠금 탈출: 이 검사가 정상 이미지를 잘못 거절하거나 다른 레이아웃으로 옮겨야 하면 `-F`가 통하지 않는다.
  검사가 받아들이는 이전 이미지(예: 검증된 r43 `562c6bae…`)로 먼저 내려가면, 그 이미지에는 이 검사가
  없으므로 예전처럼 `-F`를 쓸 수 있다. 시리얼·U-Boot 복구는 sysupgrade를 거치지 않는다. 장치에서는
  확인하지 않았다(5절).

## 9. GitHub 펌웨어 업데이트 (LuCI 피드 패치 0005, overlay CGI)

r43 이미지의 GitHub 업데이트는 릴리스를 받을 수 없었다.
- 저장소가 fastbuild의 `w1700k/builds`였고, 자산 필터가 `openwrt-airoha-an7581-<x>-squashfs-sysupgrade`와
  소문자 `sha256sums`만 받았다. 이 트리의 이미지는 `VultaV/OpenW1700k` prerelease에
  `openwrt-ubi2-…-gemtek_w1700k-ubi-squashfs-sysupgrade.itb`와 `SHA256SUMS`로 올라간다.
- r29–r43 config는 Oniguruma 없이 빌드한 `jq`를 넣는다(`jq-full` 아님). CGI의 `test()`·`sub()`가 실행 중
  실패해 `github_fetch`는 모든 요청을 세션 없음(403)으로, `github_check`는 항상 502로 답했다. 호스트 jq에는
  정규식이 있어 시험이 통과했다.
- `github_fetch`는 "Keep settings"를 꺼도 설정 유지 모드로 `sysupgrade --test`를 돌렸다. fwtool은 설정 유지
  때만 compat_version minor 변경을 거절하므로(W1700K UBI 이미지는 2.0) 실제 설치(`-n`)라면 받을 이미지를
  준비 전에 거절했다.

변경
- `github_check`·`github_fetch`: 저장소 `VultaV/OpenW1700k`. W1700K UBI sysupgrade `.itb`(버전 접두사 허용)와
  `SHA256SUMS`만 받는다. 릴리스 이름은 이미지의 버전 접두사, 없으면 태그다. 정규식 대신
  `startswith`·`endswith`·`ltrimstr`·`rtrimstr`·`explode`로 검사한다. 같은 이름·URL을 받으면서 끝 개행,
  URL의 제어·비ASCII 문자, `github.com`의 이스케이프 안 된 `.`이 통과시키던 호스트를 더 거절한다.
  `keep`이 JSON boolean이 아니면 네트워크 접근 전에 400, false면 `sysupgrade --test -n`. 세션·ACL, https
  전용, 이미지 하나 규칙, SHA256 확인, 준비 전 `--test`는 그대로다.
- LuCI 피드 패치 0005(0003 r3 위): "View on GitHub" 링크를 `VultaV/OpenW1700k`로 바꾸고 대화상자의
  Keep settings 값을 `github_fetch`에 보낸다. `PKG_RELEASE:=4`(`26.250.72430~e81743d-r4`). r3의 텍스트 목록은
  그대로다.
- 0005와 같은 커밋의 CGI는 짝이다. 0005 없는 뷰는 `keep`을 보내지 않아 400을 받는다.

호스트 시험: `python3 tests/test_github_fetch.py`가 정규식 builtin을 거부하는 `jq`로 9/9 통과한다(jq 수정
전 CGI는 8/9 실패). `test_attendedsysupgrade_images.js`는 고정 피드에 0003 r3만 넣으면 9 PASS / 3 FAIL,
0005까지 넣으면 12 / 0이다. 적용 후 SHA256은 `docs/mlo-r34/feed-patches/README.md`에 있다. 3절 이미지에는
들어 있지 않다(그 이미지의 CGI와 뷰는 위 결함 그대로다).
