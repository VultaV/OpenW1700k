#!/bin/sh
# Keep a Wi-Fi station off the PPE/NPU bridge offload while it cycles power save.
# When a client dozes and wakes many times a second (macOS AWDL, for example), the
# MT7996 rejects its offloaded TX frames (non-zero TXFREE status) and TCP stalls
# for seconds; the host path buffers them instead. A station is held for HOLD
# seconds when, within one second, its status 1+2 count grows by THRESH, or its
# links change power-save state PS_THRESH times while it completes BUSY frames.
# Idle phones and IoT devices cycle power save all the time; the traffic gate
# keeps them out. Both signals are visible on the host path too, so a hold is
# extended while the client keeps cycling under load.
HQ=${HQ:-/sys/kernel/debug/ieee80211/phy0/mt76/hw-queues}
RUN=${RUN:-/var/run}
HOLD_FILE=$RUN/bridge-flow-offload.hold
APPLY=${APPLY:-/usr/share/bridge-flow-offload/apply-rules.sh}
THRESH=${THRESH:-20}
PS_THRESH=${PS_THRESH:-6}
BUSY=${BUSY:-1000}
TABLE=w1700k_bridge_offload
HOLD=${HOLD:-30}

# "MAC FAILED PS DONE": TXFREE status 1+2, power-save changes and status 0
# completions, summed over a station's links. hw-queues prints each station once
# per band; only the first block is counted.
counts() {
	awk '/^STA /{ skip = seen[$2]++; if (!skip) { mac = $2; f[mac] = p[mac] = d[mac] = 0 } next }
	     !skip && $1 == "txfree_status:" { d[mac] += $2; f[mac] += $3 + $4 }
	     !skip && $1 == "ps_transitions:" { p[mac] += $2 }
	     END { for (m in f) print m, f[m], p[m], d[m] }' "$HQ" 2>/dev/null
}

# Stations to hold, given two snapshots one second apart.
rising() {
	awk -v t="$THRESH" -v pt="$PS_THRESH" -v b="$BUSY" \
	    'NR == FNR { f[$1] = $2; p[$1] = $3; d[$1] = $4; next }
	     ($1 in f) && ($2 - f[$1] >= t || ($3 - p[$1] >= pt && $4 - d[$1] >= b)) { print $1 }' "$1" "$2"
}

main() {
	[ -r "$HQ" ] && grep -q ps_transitions: "$HQ" || {
		logger -t bridge-flow-offload 'ps-guard: no power-save counters; not started'
		exit 0
	}

	prev=$RUN/bridge-flow-offload.ps.prev
	cur=$RUN/bridge-flow-offload.ps.cur
	: > "$HOLD_FILE"
	counts > "$prev"
	while sleep 1; do
		counts > "$cur"
		now=$(cut -d. -f1 /proc/uptime)
		changed=
		for mac in $(rising "$prev" "$cur"); do
			until=$(awk -v m="$mac" '$1 == m { print $2 }' "$HOLD_FILE")
			# Frames already queued keep failing for a few seconds after a hold
			# starts; only rebuild once the hold is half used.
			[ -z "$until" ] || [ $((until - now)) -le $((HOLD / 2)) ] || continue
			if [ -n "$until" ]; then
				# Already held, so nothing is offloaded: renew the entry in one
				# transaction instead of rebuilding.
				printf 'delete element bridge %s ps_hold { %s }\nadd element bridge %s ps_hold { %s timeout %ss }\n' \
					"$TABLE" "$mac" "$TABLE" "$mac" "$HOLD" | nft -f - 2>/dev/null || changed=1
			else
				changed=1
				logger -t bridge-flow-offload "ps-guard: holding $mac off offload for ${HOLD}s"
			fi
			grep -v "^$mac " "$HOLD_FILE" > "$HOLD_FILE.t"
			echo "$mac $((now + HOLD))" >> "$HOLD_FILE.t"
			mv "$HOLD_FILE.t" "$HOLD_FILE"
		done
		awk -v n="$now" '$2 > n' "$HOLD_FILE" > "$HOLD_FILE.t" && mv "$HOLD_FILE.t" "$HOLD_FILE"
		# A new hold rebuilds the table, which loads the holds and tears down the
		# station's offloaded flows. Set entries expire on their own, after which
		# the station is offloaded again.
		[ -z "$changed" ] || "$APPLY"
		mv "$cur" "$prev"
	done
}

# Tests source this file with PSGUARD_LIB=1 for counts() and rising().
[ -n "${PSGUARD_LIB:-}" ] || main
