# W1700K FDB 로그 및 Wi-Fi 장애 증거 보존

기준 소스: `bc8d949032` (r44), `codex/mlo-r30-bridge-offload`.
이 변경은 소스 후보이며 펌웨어 빌드, 공유기 설치/재부팅, 실제 장애 재현을 하지 않았다.
push 및 릴리스 배포도 하지 않았다. 아래 커널 파일 줄 번호는 제공된
`.evidence/kernel/`의 변경 전 빌드 소스 기준이다. 원시 로그와 단말 식별자는
이 문서나 커밋에 포함하지 않는다.

## A. 삭제 요청과 -ENOENT의 정확한 경로

1. 포크의 `package/kernel/mac80211/patches/subsys/999-mac80211-station-fdb-notify.patch:20-29`가
   AP/AP_VLAN의 STA 제거 때마다 VID 0의 `SWITCHDEV_FDB_DEL_TO_DEVICE`를 합성한다.
   실제 브리지 FDB 학습 여부를 검사하지 않고, 브리지 FDB 자체를 삭제하지도 않는다.
   r44의 `docs/mlo-r44/build-manifest.json:32`에 포함된 패치다.
2. DSA `net-dsa/user.c:3778-3785`의 switchdev 이벤트 처리가 같은 브리지의
   DSA 포트들에 전달한다. `dsa_user_fdb_event()`의 `:3712-3731`은
   assisted CPU learning이 켜진 스위치의 foreign Wi-Fi MAC을 host 주소로 분류한다.
   mt7530은 `mt7530.c:2397,2588`에서 이 기능을 켠다.
3. `dsa_user_switchdev_event_work()` (`net-dsa/user.c:3661-3671`) →
   `dsa_port_bridge_host_fdb_del()` (`net-dsa/port.c:1094-1113`) →
   `dsa_switch_host_fdb_del()` (`net-dsa/switch.c:462-487`) →
   `dsa_port_do_fdb_del()` (`net-dsa/switch.c:308-352`)로 진행한다.
   로그의 포트 1/2는 요청을 전달한 lan3/lan4다
   (`target/linux/airoha/dts/an7581-w1700k-ubi.dts:390-402`).
   실제 host FDB 삭제 대상은 이 포트들이 공유하는 CPU 포트다.
4. CPU 포트의 **소프트웨어 참조 목록**에 주소가 없으면
   `net-dsa/switch.c:326-330`이 `-ENOENT`를 반환한다.
   `user.c:3670`이 이를 각 요청 포트의 오류로 출력한다.
   이 경우 `mt7530_port_fdb_del()`까지 도달하지 않는다.
   `mt7530.c:1676-1690`은 FDB WRITE만 실행하고,
   `mt7530_fdb_cmd()` (`:236-264`)도 이 WRITE에서 `-ENOENT`를 만들지 않는다.
   따라서 mt7530 반환값만 수정하면 이 로그는 없어지지 않는다.

첫 STA 삭제가 CPU 목록의 참조를 소진해도 소프트웨어 브리지 FDB는 남는다.
같은 AP로 재연결하면 `br_fdb_update()` (`br_fdb.c:1021-1052`)가 기존 항목의
시간만 갱신하고 ADD를 보내지 않을 수 있다. 다음 합성 DEL은 짝이 없어진다.
처음부터 학습되지 않은 STA, 먼저 aging된 항목 (`br_fdb.c:578`),
이미 다른 포트로 이동한 항목 (`:1029`)도 중복 DEL을 만들 수 있다.
제공 로그의 MLO teardown/disconnect 직후 포트 1/2 오류 쌍은 이 경로와 일치한다.
모든 개별 오류의 호출 스택을 기록한 런타임 trace는 없으므로, 각 오류를
aging/roaming/STA teardown 중 하나로 개별 확정한 것은 아니다.

`9999-z1-netfilter-bridge-fdb-cleanup.patch:168-195`는 이 알림을 **수신**하여
기존 bridge flow를 정리한다. 삭제 알림을 생성하지 않는다.
iface/net의 `51-bridge-flow-offload`는 `apply-rules.sh`를 호출하여 nft 규칙을
갱신할 뿐, FDB 삭제 명령이나 switchdev 이벤트를 생성하지 않는다.

추가 확인: `port.c:1107-1110`의 `dev_uc_del()`도 오류를 반환할 수 있으나,
[Linux v6.18.44 Airoha 원본](https://raw.githubusercontent.com/gregkh/linux/v6.18.44/drivers/net/ethernet/airoha/airoha_eth.c)과
이 포크의 Airoha 드라이버 패치는 `IFF_UNICAST_FLT`를 설정하지 않는다.
[ether_setup()](https://raw.githubusercontent.com/gregkh/linux/v6.18.44/net/ethernet/eth.c)는
`IFF_TX_SKB_SHARING`만 기본 설정하므로 해당 조건부 경로는 이 보드에 적용되지 않는다.

### 수정 범위

`9999-z7-net-dsa-make-absent-host-fdb-delete-idempotent.patch`는
`dsa_port_do_fdb_del()`의 목록 누락 분기에서 `err = -ENOENT` 한 줄만 제거한다.
이미 없는 항목은 성공으로 처리하며 not-found tracepoint는 유지한다.
기존 참조 감소, 마지막 참조의 하드웨어 삭제, 실패 시 참조 복원,
일반 user 포트/드라이버의 실제 오류 전달은 바꾸지 않는다.

합성 STA 알림을 단순 삭제하면 즉시 flow 정리 동작도 사라진다.
별도 커널 API/의존성을 추가하거나 switchdev replay용 ctx를 다른 용도로 쓰는 대신,
요청한 로그 문제에 한정하여 공유 삭제 경로를 idempotent하게 만든다.
이 수정은 기존 STA/브리지 FDB의 수명 관계나 Wi-Fi 장애 자체의 해결을 뜻하지 않는다.

**커널 이미지가 바뀐다.** AN7581의 `CONFIG_NET_DSA=y`이므로 DSA 코드는
커널에 포함된다. userland-only 변경이 아니며 재빌드 후 커널/모듈 바이트의
동일성을 가정해서는 안 된다. `include/kernel.mk:58`의
`-w1700k-mlo-r32` ABI suffix는 그대로 유지한다. 구조체/공개 API 변경은 없다.

## B. 로그 및 장애 스냅샷

`99-w1700k-log-size` uci-defaults는 `gemtek,w1700k-ubi`에서만
`system.@system[0].log_size`가 unset/빈 값/128이면 1024 KiB로 설정한다.
다른 값은 보존한다. 사용자가 의도적으로 고른 128과 stock 128은 구별할 수 없어
요청한 정책대로 둘 다 이관한다. kept settings는 preinit의 `80_mount_root`에서
복원되고 boot(START=10)의 defaults가 실행된 뒤 log(START=12)가 시작한다.
사용자 정의 `log_buffer_size`는 변경하지 않으며 이 값이 있으면 logd 설정상
`log_size`보다 우선한다. UCI 실패 시 defaults 파일을 다음 부팅에 재시도한다.

새 `w1700k-wifi-watchdog` 패키지(PKG_RELEASE=1)는 W1700K 기본 이미지에 포함한다.
procd 서비스이며 설정 파일/conffile은 없다. 대상 AP는 `ap-mld0`, `phy0.0-ap0`다.
서비스를 끄려면 `/etc/init.d/w1700k-wifi-watchdog disable` 및 `stop`을 사용한다.
Wi-Fi 설정 변경이나 자동 재시작은 하지 않는다.

- 60초 안에 두 AP 모두에서 합계 4회 이상의 local deauth를 관찰하면 수집한다.
  해당 AP의 association 로그 또는 최근 station dump에서 확인한 STA만 계산한다.
  중복 deauth는 새 association 관찰 없이는 다시 세지 않는다.
- 10초 간격으로 station dump와 hostapd 상태를 확인한다. 이전에 클라이언트를
  관찰했고, 두 AP가 모두 ENABLED이며 station 합계가 0인 상태가 연속 300초를
  넘으면 수집한다. 조회 실패/비활성 AP는 이 연속 시간을 끊는다.
- 기존 logread ring은 detector 시작 시 재생하지 않는다. 시간 창과 rate limit은
  wall clock/NTP 대신 `/proc/uptime`을 사용한다.
- `/var/run/w1700k-wifi-watchdog/snapshot.txt` 하나만 유지한다. 0700 디렉터리,
  0600 파일이며 자동 전송하지 않는다. 이 파일에는 단말 주소가 포함될 수 있으므로
  외부 공유 전에 비식별화한다. 부팅하면 `/tmp` 증거는 사라진다.
- 수집 시작 전에 시간을 기록하므로 실패해도 1시간 안에 다시 수집하지 않는다.
  같은 부팅 내 서비스 재시작에도 제한이 유지된다.
- 각 명령은 최대 3초, 전체 수집은 최대 60초, 결과는 최대 2 MiB로 제한한다.
  원자적 교체용 임시 파일도 같은 한도를 적용한다. 각 일반 구간은 16 KiB,
  logread/dmesg는 각각 마지막 512줄 및 128 KiB 한도다.
- 두 AP의 `iw station dump`, `ip -s link`, hostapd `get_status`, 2초 간격
  `/proc/interrupts` 2회, logread/dmesg tail을 보존한다.
  mt76 및 band*의 `token_info`, `xmit-queues`, `hw-queues`, `tx_stats`,
  `rx-queues`, `sys_recovery`와 per-station/link `hw-queues`를 명시적으로 읽는다.
  debugfs 전체를 재귀적으로 읽지 않으며, 지정된 파일 중 존재하는 최대 96개만 수집한다.
  `sys_recovery`는 읽기 handler의 SER 통계만 읽고 recovery를 요청하는 쓰기는 하지 않는다.

## 호스트 검증과 남은 장치 검증

실행 명령:

```sh
python3 tests/test_dsa_fdb_delete.py
python3 tests/test_w1700k_log_defaults.py
python3 tests/test_w1700k_wifi_watchdog.py
perl scripts/checkpatch.pl --no-tree target/linux/airoha/patches-6.18/9999-z7-net-dsa-make-absent-host-fdb-delete-idempotent.patch
git diff --check
```

DSA 검증은 제공된 실제 함수를 추출하고 패치를 적용하여 C compiler와
AddressSanitizer/UndefinedBehaviorSanitizer로 실행한다.
수정 전 22개 사례 중 8개 실패, 수정 후 22개 모두 통과했다.
CPU/cascade의 중복 삭제, 참조 감소, 최종 삭제, 드라이버 오류 유지/복원을 검사한다.
log defaults는 보드/stock/custom/kept-settings/실패 처리를 포함한 29개 사례를 통과했다.
watchdog의 14개 검사는 모두 통과했다. 실제 shell 함수를 합성 로그와 monotonic
시간으로 실행하여 임계값/시간 창, association 조건, 빈 AP, 시간당 제한/재시작,
상태 크기 제한, 16 KiB 구간 한도/3초 timeout을 검사한다. 수집 중 종료 검사는
처음에 자식 PID의 shell local 범위 문제로 실패했으며, PID 수명을 수정한 뒤
logread 자식 종료/FIFO 제거/0600·0700 권한 검사를 통과했다.
커널 patch checkpatch는 오류 0, 경고 0이며 shell syntax와 diff whitespace 검사도 통과했다.
실제 패키지 install recipe를 임시 디렉터리에서 실행하여 init/daemon 두 파일이
0755로 배치되는 것을 확인했다. target APK 빌드는 실행하지 않았다.

장치에서 추가로 확인할 사항:

1. 전체 펌웨어/패키지 빌드와 부팅, `uname -r` suffix 및 패키지 의존성 확인.
2. kept-settings sysupgrade 후 stock 128→1024, 사용자 지정값 보존,
   실제 logd 실행 인수 `-S 1024` 확인 (`log_buffer_size` 사용자 override도 고려).
3. procd 서비스가 시작되고 BusyBox ash/logread/iw/ubus 출력 및 debugfs 경로가
   실제 r44 장치와 일치하는지 확인. 서비스 종료/재시작 시 자식 프로세스도 확인.
4. 실제 STA disconnect/reconnect 및 장시간 관찰에서 FDB 로그 쌍이 사라지고
   LAN/Wi-Fi 전달 및 bridge flow cleanup이 유지되는지 확인. 필요하면 보존된
   `dsa_fdb_del_not_found` tracepoint와 bridge FDB trace를 함께 관찰.
5. 실제 장애 또는 통제된 detector 입력으로 스냅샷 파일 권한/크기/내용,
   두 interrupts 샘플, 1시간 제한(서비스 재시작 포함), Wi-Fi 무재시작을 확인.
   정상적인 전원 끄기나 무클라이언트 환경도 같은 heuristic에 걸릴 수 있다.

호스트 통과는 하드웨어 장애 재현, 실제 복구, 성능 또는 공유기 설치 성공의 증거가 아니다.
