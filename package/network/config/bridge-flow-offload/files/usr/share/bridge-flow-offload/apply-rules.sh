#!/bin/sh
# A fw4 script include may dot-source this file. Keep state/traps in a subshell.
(
set -f
umask 077
TABLE=w1700k_bridge_offload
OWNER='bridge-flow-offload:v1'
RULES=

get() { uci -q get "bridge-flow-offload.main.$1"; }
note() {
	printf '%s\n' "$*" >&2
	logger -t bridge-flow-offload "$*"
	printf '%s\n' "$*" > /var/run/bridge-flow-offload.status
}
identifier() {
	case "$1" in ''|*[!a-zA-Z0-9_.-]*) return 1;; esac
	[ "${#1}" -le 15 ]
}
owned() {
	local tables text
	tables=$(timeout 5 nft list tables) || return 2
	printf '%s\n' "$tables" | grep -qx "table bridge $TABLE" || return 1
	text=$(timeout 5 nft list table bridge "$TABLE") || return 2
	printf '%s\n' "$text" | grep -Fq "comment \"$OWNER\"" || return 2
}
clear_owned() {
	local rc
	owned; rc=$?
	case "$rc" in
		0) timeout 5 nft destroy table bridge "$TABLE" || { note 'error: owned table removal failed'; return 1; };;
		1) :;;
		*) note 'error: cannot establish table ownership; existing table left untouched'; return 1;;
	esac
}
reject() {
	note "disabled: $*"
	clear_owned || return 1
	return 1
}

validate() {
	local port master value tables line details
	case "$(uname -r)" in
		6.18.44-w1700k-mlo-r30|6.18.44-w1700k-mlo-r32) :;;
		*) reject 'unvalidated kernel TTL behavior'; return 1;;
	esac
	[ "$(cat /tmp/sysinfo/board_name 2>/dev/null)" = 'gemtek,w1700k-ubi' ] || { reject 'unvalidated board'; return 1; }
	identifier "$BRIDGE" && [ "$BRIDGE" = br-lan ] || { reject 'unsupported bridge'; return 1; }
	[ "$COUNT" = 2 ] && [ "$PORT_A" != "$PORT_B" ] || { reject 'exactly two distinct trusted ports required'; return 1; }
	[ -d "/sys/class/net/$BRIDGE/bridge" ] || { reject 'bridge absent'; return 1; }
	[ "$(cat "/sys/class/net/$BRIDGE/bridge/vlan_filtering" 2>/dev/null)" = 0 ] || { reject 'VLAN filtering enabled or unknown'; return 1; }
	for value in /proc/sys/net/bridge/bridge-nf-call-iptables /proc/sys/net/bridge/bridge-nf-call-ip6tables /proc/sys/net/bridge/bridge-nf-call-arptables; do
		[ ! -e "$value" ] || [ "$(cat "$value")" = 0 ] || { reject 'legacy bridge netfilter policy active'; return 1; }
	done
	# Unknown bridge/netdev tables may impose policy after our admission hook.
	tables=$(timeout 5 nft list tables) || { reject 'cannot inspect nft policy'; return 1; }
	while IFS= read -r line; do
		case "$line" in
			"table bridge $TABLE") owned || { reject 'owned table name collision'; return 1; };;
			'table bridge '*|'table netdev '*) reject 'other bridge/netdev policy present'; return 1;;
		esac
	done <<EOF
$tables
EOF
	# inet can also have ingress base chains; it is not covered by a family-only check.
	details=$(timeout 5 nft list chains) || { reject 'cannot inspect ingress policy'; return 1; }
	if printf '%s\n' "$details" | grep -Eq 'hook (ingress|egress)([[:space:];]|$)'; then
		reject 'ingress/egress nft policy present'; return 1
	fi
	for port in "$PORT_A" "$PORT_B"; do
		identifier "$port" || { reject 'invalid port identifier'; return 1; }
		case "$port" in
			lan[1-4]) :;;
			phy[0-9]*-ap[0-9]*|ap-mld[0-9]*) [ -e "/sys/class/net/$port/phy80211" ] || { reject 'unknown wireless port'; return 1; };;
			*) reject 'unsupported selected port'; return 1;;
		esac
		master=$(readlink "/sys/class/net/$port/master")
		[ "${master##*/}" = "$BRIDGE" ] && [ -d "/sys/class/net/$BRIDGE/brif/$port" ] || { reject "missing or moved port: $port"; return 1; }
		[ ! -e "/proc/net/vlan/$port" ] || { reject "tagged port: $port"; return 1; }
		[ "$(cat "/sys/class/net/$port/brport/state" 2>/dev/null)" = 3 ] || { reject "port not forwarding: $port"; return 1; }
		# locked/mab have no sysfs attributes: inspect the actual netlink flags.
		details=$(timeout 5 bridge -j -d link show dev "$port") || { reject "cannot inspect port policy: $port"; return 1; }
		for value in isolated locked mab neigh_suppress neigh_vlan_suppress vlan_tunnel; do
			[ "$(printf '%s\n' "$details" | jsonfilter -e "@[0].$value")" = false ] || { reject "unsupported or unknown $value: $port"; return 1; }
		done
		# Hairpin only permits same-port forwarding; our rules require distinct ports.
		case "$(printf '%s\n' "$details" | jsonfilter -e '@[0].hairpin')" in
			true|false) :;;
			*) reject "unknown hairpin policy: $port"; return 1;;
		esac
		for value in learning flood; do
			[ "$(printf '%s\n' "$details" | jsonfilter -e "@[0].$value")" = true ] || { reject "unsupported or unknown $value: $port"; return 1; }
		done
		[ -z "$(printf '%s\n' "$details" | jsonfilter -e '@[0].backup_port')" ] || { reject "backup port configured: $port"; return 1; }
	done
}

main() {
	local enabled rc legacy
	# Filter events by configured names, including removed ports with no master link.
	BRIDGE=$(get bridge)
	PORTS=$(get ports)
	case "${1:-}" in
		--iface-event)
			case "${ACTION:-}" in ifup|ifupdate|ifdown) :;; *) return 0;; esac
			[ "${INTERFACE:-}" = "$(get network)" ] || return 0;;
		--net-event)
			case "${ACTION:-}" in add|remove) :;; *) return 0;; esac
			case " $PORTS $BRIDGE " in *" ${DEVICENAME:-/} "*) :;; *) return 0;; esac;;
		'') :;;
		*) note 'error: unsupported invocation'; return 1;;
	esac
	# No fw4 lock/command: fw4 already holds its lock when invoking script includes.
	exec 9>/var/lock/bridge-flow-offload.lock
	timeout 15 flock -x 9 || { note 'error: refresh lock timed out; retry required'; return 1; }
	# Read again after serialized waiting; the last event must inspect current state.
	enabled=$(get enabled)
	if [ "$enabled" = 0 ] || [ -z "$enabled" ]; then
		clear_owned || return 1
		note 'disabled: configuration'
		return 0
	fi
	[ "$enabled" = 1 ] || { reject 'invalid enabled value'; return 1; }
	for legacy in /etc/hotplug.d/iface/00-disable-bridge-flow-offload /usr/share/nftables.d/ruleset-post/30-bridge-offload.nft; do
		[ ! -e "$legacy" ] || { reject "legacy migration required: $legacy"; return 1; }
	done
	BRIDGE=$(get bridge)
	PORTS=$(get ports)
	set -- $PORTS
	COUNT=$# PORT_A=${1:-} PORT_B=${2:-}
	validate || return 1
	RULES=$(mktemp /tmp/bridge-flow-offload.XXXXXX) || { reject 'temporary file creation failed'; return 1; }
	trap 'rm -f "$RULES"' EXIT
	trap 'exit 1' HUP INT TERM
	cat > "$RULES" <<EOF
destroy table bridge $TABLE
table bridge $TABLE {
	comment "$OWNER"
	flowtable ft {
		hook ingress priority 0; devices = { "$PORT_A", "$PORT_B" };
		flags offload; counter;
	}
	chain forward {
		type filter hook forward priority 10; policy accept;
		iifname "$PORT_A" oifname "$PORT_B" ether type ip meta l4proto tcp ct state established counter flow add @ft counter
		iifname "$PORT_B" oifname "$PORT_A" ether type ip meta l4proto tcp ct state established counter flow add @ft counter
	}
}
EOF
	timeout 5 nft -c -f "$RULES" || { reject 'nft validation failed'; return 1; }
	validate || return 1
	timeout 5 nft -f "$RULES" || { reject 'nft atomic apply failed'; return 1; }
	note "enabled: IPv4 TCP $PORT_A <-> $PORT_B on $BRIDGE"
}

main "$@"
)
