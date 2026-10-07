# r46 — 소프트웨어 탭 피드와 DNS 버스트 손실

r45에 사용자 영역 패키지 피드와 UDP 수신 버퍼 기본값만 더했습니다. 커널·모듈 74개·펌웨어 11개는
r45와 바이트 단위로 같고, 바뀐 패키지는 `base-files`뿐입니다. MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.

## 바뀐 점

- **소프트웨어 탭**: r44는 snapshot target 피드가 이 이미지의 커널(6.18.44)과 다른 `kernel`·`base-files`를
  내놓아 원격 피드를 모두 뺐고, 그 결과 LuCI 소프트웨어 탭이 비었습니다. r46은 snapshot의 base·packages·luci·routing
  피드만 넣고 target·kmods 피드는 넣지 않습니다. 첫 부팅 때 `99-w1700k-apk-pin`이 이미지의 패키지를 모두
  이미지 버전으로 `/etc/apk/world`에 고정합니다. 고정이 없으면 2026-10-07 snapshot 기준 `apk upgrade`가
  패치한 `luci-base`·`luci-mod-network`를 포함해 49개를 바꿉니다. 새 패키지는 설치할 수 있고, 고정된
  패키지의 새 버전이 필요한 패키지는 설치가 실패합니다(덮어쓰지 않음). kmod가 필요한 패키지는 설치할 수 없습니다.
- **DNS 버스트 손실**: 이 보드에서 작은 UDP 패킷 하나가 수신 버퍼를 약 16 KB 차지해 기본값(208 KB)으로는
  12개 정도만 쌓이고 dnsmasq가 동시 질의를 버렸습니다(OpenWrt 포럼 보고). `net.core.rmem_default=1048576`.

## 실기기 확인 (2026-10-07)

| 항목 | 결과 |
|---|---|
| 설치 | r45에서 설정 유지 sysupgrade, `sysupgrade -T` "Signature check OK" |
| 패키지 고정 | world 항목 210개 모두 `이름=버전` |
| 피드 | `apk update` 9,246개, `apk upgrade -s` 변경 0개, `apk add -s tcpdump` 성공 |
| 소프트웨어 탭 백엔드 | `list-available` 9.8 MB, `list-installed` 0.6 MB |
| DNS 버스트(동시 20/40/80/120) | r45: 12/12/12/12, r46: 20/40/67/85 |
| 무선 | 세 라디오 up, MLO 5 GHz·6 GHz 각 160 MHz, FDB 삭제 오류 로그 0 |

무선 경로는 바뀌지 않아 무선 처리량은 다시 재지 않았습니다. 소프트웨어 탭 화면은 사용자 브라우저 확인이 남아 있습니다.

## 빌드

[r44 절차](../mlo-r44/README.md)와 같고 `r46.config`와 `build-manifest.json`을 씁니다. 패키지 고정은 첫 부팅
스크립트라 이미지 밖 설정(`files/`)이 필요 없습니다.
