#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

# /var/run is root-owned and not world-writable, so nobody can pre-create the directory or a lock symlink.
state_dir=/var/run/w1700k-wifi-watchdog
known=
deauth_mld=
deauth_legacy=
seen_clients=0
empty_since=
log_pid=

uptime_seconds() {
	read -r now rest < /proc/uptime
	now=${now%%.*}
}

# Remember associated stations for 60 seconds, including the interval between
# disassociation and local deauthentication. A deauth consumes the observation.
remember_station() {
	local stamp=$1 key=$2/$3 item kept= count=0
	# ponytail: bound history to 256 stations; raise only for larger deployments.
	for item in $known; do
		[ "${item#*/}" = "$key" ] && continue
		[ "$((stamp - ${item%%/*}))" -le 60 ] || continue
		[ "$count" -lt 255 ] || break
		kept="$kept $item"
		count=$((count + 1))
	done
	known="$stamp/$key$kept"
}

consume_station() {
	local stamp=$1 key=$2/$3 item kept= found=1
	for item in $known; do
		[ "$((stamp - ${item%%/*}))" -le 60 ] || continue
		if [ "${item#*/}" = "$key" ]; then
			found=0
		else
			kept="$kept $item"
		fi
	done
	known=$kept
	return "$found"
}

# Four local deauths within 60 seconds, with at least one on each AP. Retaining
# the last three per AP is sufficient for that predicate and bounds state.
detect_log() {
	local stamp=$1 line=$2 iface mac item a=0 b=0
	case "$line" in
		*'hostapd: ap-mld0: STA '*) iface=ap-mld0 ;;
		*'hostapd: phy0.0-ap0: STA '*) iface=phy0.0-ap0 ;;
		*) return 1 ;;
	esac
	mac=${line#*"$iface: STA "}
	mac=${mac%% *}
	case "$mac" in *[!0-9a-fA-F:]*|'') return 1 ;; esac
	case "$mac" in ??:??:??:??:??:??) ;; *) return 1 ;; esac
	case "$line" in
		*' IEEE 802.11: associated ('*)
			remember_station "$stamp" "$iface" "$mac"
			seen_clients=1
			empty_since=
			return 1 ;;
		*' IEEE 802.11: deauthenticated due to local deauth request'*) ;;
		*) return 1 ;;
	esac
	consume_station "$stamp" "$iface" "$mac" || return 1
	if [ "$iface" = ap-mld0 ]; then
		set -- $stamp $deauth_mld
		deauth_mld="$1 ${2-} ${3-}"
	else
		set -- $stamp $deauth_legacy
		deauth_legacy="$1 ${2-} ${3-}"
	fi
	for item in $deauth_mld; do
		[ "$((stamp - item))" -le 60 ] && a=$((a + 1))
	done
	for item in $deauth_legacy; do
		[ "$((stamp - item))" -le 60 ] && b=$((b + 1))
	done
	[ "$a" -gt 0 ] && [ "$b" -gt 0 ] && [ "$((a + b))" -ge 4 ]
}

# Unknown/failed station queries and disabled APs break the continuous window.
detect_empty() {
	local stamp=$1 count=$2 enabled=$3
	if [ "$count" -gt 0 ]; then
		seen_clients=1
		empty_since=
	elif [ "$count" -ne 0 ] || [ "$enabled" != 1 ] || [ "$seen_clients" != 1 ]; then
		empty_since=
	else
		[ -n "$empty_since" ] || empty_since=$stamp
		[ "$((stamp - empty_since))" -gt 300 ] && return 0
	fi
	return 1
}

# /tmp and monotonic uptime preserve the limit across service restarts, while
# reboot starts a new incident history. Reserve before collecting, even on error.
reserve_snapshot() {
	local stamp=$1 last=
	[ ! -f "$state_dir/last-snapshot" ] || read -r last < "$state_dir/last-snapshot"
	case "$last" in
		''|*[!0-9]*) ;;
		*) [ "$((stamp - last))" -ge 3600 ] || return 1 ;;
	esac
	printf '%s\n' "$stamp" > "$state_dir/last-snapshot"
}

snapshot_section() {
	printf '\n== %s\n' "$*"
	timeout -s KILL 3 "$@" 2>&1 | head -c 16384
	printf '\n'
}

snapshot_body() {
	local iface dir name file n=0
	printf 'W1700K Wi-Fi snapshot: %s\n' "$1"
	date -u
	cat /proc/uptime
	snapshot_section cat /proc/interrupts
	sleep 2
	snapshot_section cat /proc/interrupts
	for iface in ap-mld0 phy0.0-ap0; do
		snapshot_section iw dev "$iface" station dump
		snapshot_section ip -s link show dev "$iface"
		snapshot_section ubus -t 2 call "hostapd.$iface" get_status
	done
	printf '\n== logread (last 512 lines, at most 128 KiB)\n'
	timeout -s KILL 3 logread -l 512 2>&1 | tail -n 512 | tail -c 131072
	printf '\n== dmesg (last 512 lines, at most 128 KiB)\n'
	timeout -s KILL 3 dmesg 2>&1 | tail -n 512 | tail -c 131072
	# Only these diagnostic files may be read. In mt7996, sys_recovery's
	# read handler reads SER counters; only its write handler starts recovery.
	for dir in /sys/kernel/debug/ieee80211/phy*/mt76 \
		/sys/kernel/debug/ieee80211/phy*/mt76/band*; do
		[ -d "$dir" ] || continue
		for name in token_info xmit-queues hw-queues tx_stats rx-queues sys_recovery; do
			file=$dir/$name
			[ -r "$file" ] || continue
			n=$((n + 1))
			[ "$n" -le 96 ] || { printf '\nDebug file limit reached\n'; return; }
			snapshot_section cat "$file"
		done
	done
	for file in /sys/kernel/debug/ieee80211/phy*/netdev:*/stations/*/hw-queues \
		/sys/kernel/debug/ieee80211/phy*/netdev:*/stations/*/link*/hw-queues; do
		[ -r "$file" ] || continue
		n=$((n + 1))
		[ "$n" -le 96 ] || { printf '\nDebug file limit reached\n'; return; }
		snapshot_section cat "$file"
	done
}

capture_snapshot() {
	reserve_snapshot "$1" || return 0
	# One retained snapshot, at most 2 MiB; temporary replacement is also capped.
	timeout -s KILL 60 "$0" --snapshot "$2" 2>&1 |
		head -c 2097152 > "$state_dir/snapshot.new" || return 1
	mv -f "$state_dir/snapshot.new" "$state_dir/snapshot.txt" || return 1
	logger -t w1700k-wifi-watchdog "captured $2 in $state_dir/snapshot.txt"
}

poll_stations() {
	local iface dump clients mac status count=0 enabled=1
	for iface in ap-mld0 phy0.0-ap0; do
		if dump=$(timeout -s KILL 3 iw dev "$iface" station dump 2>/dev/null); then
			clients=$(printf '%s\n' "$dump" | awk '
				/^Station / { mac = $2 }
				$1 == "associated:" && $2 == "yes" { print mac }')
			for mac in $clients; do
				remember_station "$now" "$iface" "$mac"
				count=$((count + 1))
			done
		else
			enabled=0
		fi
		status=$(timeout -s KILL 3 ubus -t 2 call "hostapd.$iface" get_status 2>/dev/null)
		[ "$(printf '%s\n' "$status" | jsonfilter -e '@.status' 2>/dev/null)" = ENABLED ] || enabled=0
	done
	detect_empty "$now" "$count" "$enabled" && capture_snapshot "$now" no-stations
	return 0
}

main() {
	local line now rest last_poll=0
	umask 077
	mkdir -p "$state_dir" || exit 1
	chmod 700 "$state_dir"
	exec 9> "$state_dir/lock"
	flock -n 9 || exit 0
	rm -f "$state_dir/log.fifo"
	mkfifo "$state_dir/log.fifo" || exit 1
	# Open read/write before starting logread, so startup failure cannot block.
	exec 3<> "$state_dir/log.fifo"
	logread -f -l 0 -e 'hostapd: .*: STA .*IEEE 802.11:' 3>&- 9>&- > "$state_dir/log.fifo" &
	log_pid=$!
	trap 'kill "$log_pid" 2>/dev/null; wait "$log_pid" 2>/dev/null; rm -f "$state_dir/log.fifo"' EXIT
	trap 'exit 0' INT TERM
	while kill -0 "$log_pid" 2>/dev/null; do
		uptime_seconds
		if [ "$((now - last_poll))" -ge 10 ]; then
			poll_stations
			last_poll=$now
		fi
		if IFS= read -r -t 10 line <&3; then
			uptime_seconds
			if detect_log "$now" "$line"; then
				capture_snapshot "$now" local-deauth-burst
				deauth_mld=
				deauth_legacy=
			fi
		fi
	done
}

case "${1-}" in
	--library) ;;
	--snapshot) snapshot_body "$2" ;;
	*) main ;;
esac
