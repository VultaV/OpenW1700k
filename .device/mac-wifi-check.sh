#!/bin/zsh
# Wi-Fi regression check from a Mac on the router's LAN.
# Usage: ROUTER=<ip> SERVER=<ip> PORT=<port> KEY=<ssh key> .device/mac-wifi-check.sh [reconnects]
# Needs: the Mac joined to the MLO SSID, an iperf3 server on the wired LAN,
# and System Settings' Wi-Fi pane closed (its scans stall the link).
set -u
: ${ROUTER:?} ${SERVER:?} ${PORT:=5201} ${KEY:?} ${IF:=en0}
S=(-i $KEY -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8)

# Traffic must leave through Wi-Fi: a wired adapter ranked first or a
# Tailscale subnet route for the LAN silently takes the test elsewhere.
via=$(route -n get $SERVER | awk '/interface/ {print $2}')
[ "$via" = "$IF" ] || { echo "route to $SERVER uses $via, not $IF" >&2; exit 1; }

links() {
	local m=$(ifconfig $IF | awk '/ether/ {print $2}')
	ssh $S root@$ROUTER "f=\$(find /sys/kernel/debug/ieee80211 -name hw-queues | head -1)
		grep -i -A3 '$m' \$f | grep -o 'valid_links:[^ ]* primary:[0-9]* secondary:[0-9]*' | head -1"
}

run() {	# name, extra iperf3 args
	iperf3 -c $SERVER -p $PORT -P 4 -t 30 $2 -J | python3 -I -c '
import json, sys
d = json.load(sys.stdin); iv = [i["sum"]["bits_per_second"] / 1e6 for i in d["intervals"]]
print(sys.argv[1], round(d["end"]["sum_received"]["bits_per_second"] / 1e6), "Mbps, min",
      round(min(iv)), ", intervals under 500:", sum(x < 500 for x in iv))' $1
}

for n in $(seq 1 ${1:-0}); do
	networksetup -setairportpower $IF off; sleep 3; networksetup -setairportpower $IF on
	for i in $(seq 1 30); do ping -c1 -t1 $ROUTER >/dev/null 2>&1 && break; done
	echo "reconnect $n: $(links)"
done
# macOS runs a background roam scan ~17 s after joining that stalls the
# link for ~16 s (docs/mlo-r53/JOIN_DIP_20261017.md); let it finish.
[ ${1:-0} -gt 0 ] && sleep 40
echo "links: $(links)"
for k in 1 2 3; do run down$k -R; done
for k in 1 2; do run up$k ""; done
ssh $S root@$ROUTER 'echo offloaded flows: $(grep -c OFFLOAD /proc/net/nf_conntrack)
	echo kernel warnings: $(dmesg | grep -iE "warn|bug|oops|call trace" | grep -vc ramoops)'
