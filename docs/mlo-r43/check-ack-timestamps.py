#!/usr/bin/env python3
"""Compare saved ACK timestamp phases; no live calls or absolute cross-flow clocks."""
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import re
import runpy
import statistics

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
REPEAT = BASE/'check-repeat.py'
REPEAT_SHA = 'e28ce6ee96e4d318bf5fcb59e16f72364746f592b068e2c92fd9e4a06f519287'
CASES = {
    'low': (BASE/'device-20260927/private/download-repeat-60/iperf.json',
            BASE/'private/server-repeat-capture', BASE/'REPEAT_TCP_SERVER.json'),
    'healthy': (BASE/'ps-repeat/private/session/private/ps-repeat-unlimited-60/iperf.json',
                BASE/'ps-repeat/private/endpoint/server-capture', BASE/'ps-repeat/TCP_SERVER.json'),
}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def unwrap(values):
    """Reject backward/ambiguous half-space steps, permit an ordinary wire wrap."""
    assert values and all(type(x) is int and 0 <= x < 2**32 for x in values)
    ticks = [0]
    for a, b in zip(values, values[1:]):
        delta = (b-a) % 2**32
        assert delta < 2**31, 'Backward or ambiguous TCP timestamp step'
        ticks.append(ticks[-1]+delta)
    assert ticks[-1] < 2**31, 'Timestamp observation spans an ambiguous half-space'
    return ticks


def self_test():
    assert unwrap([2**32-2, 1, 1, 4]) == [0, 3, 3, 6]
    a = [100, 102, 238]
    assert unwrap(a) == unwrap([(x+789123) % 2**32 for x in a]) == [0, 2, 138]
    for bad in ([10, 9], [0, 2**31], [0, 2**31-1, 2**31]):
        try: unwrap(bad)
        except AssertionError: pass
        else: raise AssertionError('Backward/ambiguous timestamp accepted')
    return 'PASS: wire wrap, repeated values, independent per-flow offsets and three ambiguous/backward rejections'


def stats(rows):
    if not rows: return {'boundaries': 0}
    return dict(boundaries=len(rows),
        median_server_receive_gap_ms=statistics.median(x['receive_ms'] for x in rows),
        median_timestamp_delta_ticks=statistics.median(x['ticks'] for x in rows),
        median_timestamp_delta_ms_at_empirical_ratio=statistics.median(x['timestamp_ms'] for x in rows),
        median_receive_minus_timestamp_ms=statistics.median(x['difference_ms'] for x in rows),
        timestamp_delta_at_most_5_ticks=sum(x['ticks'] <= 5 for x in rows),
        receive_minus_timestamp_over_100ms=sum(x['difference_ms'] > 100 for x in rows),
        subsequent_timestamp_advance_at_least_100ms_within_20ms=sum(x['subsequent_jump'] for x in rows))


def analyze(label, inputs, repeat, h):
    iperf_path, directory, report_path = inputs
    data, verified = [json.loads(p.read_text()) for p in (iperf_path, report_path)]
    test = data['start']['test_start']; con = data['start']['connected']
    assert not data.get('error') and test['protocol'] == 'TCP' and test['reverse'] == 1
    assert test['duration'] == 60 and test['target_bitrate'] == 0 and test['num_streams'] == 4 and test['omit'] == 0
    bounds = repeat['application_bounds'](data); ports = sorted(bounds)
    assert len({c['local_host'] for c in con}) == len({c['remote_host'] for c in con}) == 1
    assert {c['remote_port'] for c in con} == {5203} and 5203 not in ports
    assert verified['status'] == 'OFFLINE_REPEAT_CAPTURE_VERIFIED'
    assert verified['input_sha256']['iperf'] == sha(iperf_path)
    assert verified['input_sha256']['checker'] == REPEAT_SHA
    assert verified['input_sha256']['helpers'] == {k:v[1] for k,v in repeat['INPUTS'].items()}
    assert verified['input_sha256']['tcpdump_log'] == sha(directory/'tcpdump.log')
    counts = h['clock_tcp']['capture_counts']((directory/'tcpdump.log').read_text())
    files = repeat['rotation_order'](list(directory.glob('test.pcap*')))
    assert [p.name for p in files] == [s['name'] for s in verified['capture']['segments']]
    ack = {p:[] for p in ports}; first = {p:float('inf') for p in ports}
    syn = {p:{} for p in ports}; records = 0
    for path, segment in zip(files, verified['capture']['segments']):
        # Exact bytes already passed the pinned endpoint/IP/port scope checker.
        assert sha(path) == segment['sha256'] and path.stat().st_size == segment['bytes']
        assert segment['endpoint_pairs_match'] and segment['snaplen'] == 96 and segment['link_type'] == 'Ethernet'
        n = 0
        for row in h['parser']['packets'](path, tcp_options=True):
            n += 1
            if row[2] == 5203 and row[3] in ack: p, server = row[3], True
            elif row[3] == 5203 and row[2] in ack: p, server = row[2], False
            else: continue  # The separately verified iperf control connection.
            options = h['tcp']['options'](row[11])
            if row[6] & 2:
                assert server not in syn[p], 'Multiple SYNs require separate interpretation'
                assert 8 in options
                syn[p][server] = row
            if server and row[8]: first[p] = min(first[p], row[0])
            if not server and row[6] & 16 and not row[6] & (2|4):
                assert 8 in options, 'ACK lacks negotiated timestamp option'
                ack[p].append((row[0], options[8][0]))
        assert n == segment['records']; records += n
    assert records == counts[0] == counts[1] == verified['capture']['total_records'] and counts[2] == 0
    origin = min(first.values()); end = origin+60
    series, common = {}, None
    for p in ports:
        assert set(syn[p]) == {False, True} and syn[p][True][6] & 16
        assert syn[p][True][5] == (syn[p][False][4]+1) % 2**32
        rows = sorted(x for x in ack[p] if x[0] >= first[p])
        times = [x[0] for x in rows]; ticks = unwrap([x[1] for x in rows])
        assert times[0] < origin+.1 and times[-1] >= end
        stop = bisect.bisect_right(times, end)
        assert stop > 1 and times[stop-1]-times[0] >= 59
        ratio = ticks[stop-1]/(times[stop-1]-times[0])
        assert ratio > 0
        series[p] = times, ticks, stop, ratio
        gaps = [(a,b) for a,b in zip(times,times[1:]) if b-a > .1]
        common = gaps if common is None else h['tcp']['intersect'](common, gaps)
    common = [(max(a,origin),min(b,end)) for a,b in common if min(b,end)-max(a,origin) > .1]
    public = [dict(start_seconds=round(a-origin,6), end_seconds=round(b-origin,6), duration_ms=round((b-a)*1000,3)) for a,b in common]
    assert public == verified['common_all_four_no_ack_gaps'], 'Raw common gaps differ from verified report'
    longest = max(range(len(common)), key=lambda i:common[i][1]-common[i][0]) if common else None
    flow_reports, longest_rows = [], []
    for number,p in enumerate(ports,1):
        times,ticks,stop,ratio = series[p]
        rows, short, long = [], [], []
        for i,(a,b) in enumerate(common):
            left, right = bisect.bisect_right(times,a)-1, bisect.bisect_left(times,b)
            assert 0 <= left < right < len(times)
            receive_ms = (times[right]-times[left])*1000
            delta = ticks[right]-ticks[left]; timestamp_ms = delta/ratio*1000
            until = bisect.bisect_right(times,times[right]+.02)
            jump = (ticks[until-1]-ticks[right])/ratio >= .1
            row = dict(receive_ms=receive_ms,ticks=delta,timestamp_ms=timestamp_ms,
                       difference_ms=receive_ms-timestamp_ms,subsequent_jump=jump)
            rows.append(row); (short if b-a <= .3 else long).append(row)
            if i == longest:
                longest_rows.append(dict(flow=number,server_receive_gap_ms=receive_ms,
                    timestamp_delta_ticks=delta,timestamp_delta_ms_at_empirical_ratio=timestamp_ms,
                    receive_minus_timestamp_ms=receive_ms-timestamp_ms,
                    timestamp_advance_ticks_in_next_20ms=ticks[until-1]-ticks[right]))
        adjacent = [(times[i]-times[i-1])*1000-(ticks[i]-ticks[i-1])/ratio*1000 for i in range(1,stop)]
        flow_reports.append(dict(flow=number,ack_records_with_timestamp=len(ack[p]),
            observed_server_seconds_for_ratio=times[stop-1]-times[0],
            observed_timestamp_ticks_for_ratio=ticks[stop-1],
            empirical_timestamp_ticks_per_server_second=ratio,
            timestamp_steps_monotonic_and_below_half_space=True,total_timestamp_span_below_half_space=True,
            maximum_adjacent_receive_minus_timestamp_ms=max(adjacent),
            all_common_gap_boundaries=stats(rows),short_common_gaps_100_to_300ms=stats(short),
            long_common_gaps_over_300ms=stats(long)))
    return dict(trial=label,receiver_mbps=verified['iperf']['receiver_mbps'],capture_records=records,
        dropped_by_kernel=0,actual_flows=4,common_gap_count=len(common),
        short_common_gap_count=sum(b-a <= .3 for a,b in common),
        long_common_gap_count=sum(b-a > .3 for a,b in common),flows=flow_reports,
        longest_common_gap=({**public[longest],'flow_boundary_observations':longest_rows} if common else None),
        input_sha256=dict(iperf=sha(iperf_path),verified_tcp_report=sha(report_path),
            tcpdump_log=sha(directory/'tcpdump.log'),capture_segments=[dict(name=p.name,sha256=s['sha256']) for p,s in zip(files,verified['capture']['segments'])]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true'); args=parser.parse_args()
    checks = self_test()
    if args.self_test: print(checks); return
    assert sha(REPEAT) == REPEAT_SHA
    repeat = runpy.run_path(str(REPEAT)); h = repeat['helpers']()
    result = dict(status='OFFLINE_TCP_TIMESTAMP_PHASE_OBSERVATIONS',self_test=checks,
        trials=[analyze(label,inputs,repeat,h) for label,inputs in CASES.items()],
        helper_sha256=dict(repeat=REPEAT_SHA,**{k:v[1] for k,v in repeat['INPUTS'].items()}),
        checker_sha256=sha(Path(__file__)),
        limits=[
            'Only already verified server captures are read. No Mac-side packet, RF timestamp, PS state or new live measurement is supplied.',
            'Each TCP connection is unwrapped and analyzed independently. Absolute TSval offsets are never compared across flows.',
            'Backward or ambiguous timestamp steps and a total half-space span are rejected, not silently interpreted as a wrap.',
            'The per-flow empirical ratio uses first/last ACKs in the 60-second window. It is an arrival-clock ratio influenced by queueing, not a calibrated sender clock or an error bound.',
            'A small TSval increase over a long server receive gap, followed by a rapid TSval advance, is an observed phase pattern. Timestamp generation, reuse and batching are not independently observed.',
            'Server arrival gaps minus scaled TSval deltas are not exact one-way delay or RF dwell. The source of any delay cannot be assigned to Mac, AP, NPU or server from this capture alone.',
            'ACK timestamp observations include nonprogress ACKs; neither these counts nor repeated payload ranges are physical packet-loss counts.',
            'The 300ms short/long split is an explicit descriptive threshold. The largest common gap is also reported individually; the two patterns need not have one cause.',
            'No normal run or timestamp pattern proves the original Air stall repaired or excludes an intermittent r43 regression.'
        ])
    text=json.dumps(result,indent=2)+'\n'
    assert not re.search(r'(?:\d{1,3}\.){3}\d{1,3}|(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|/Users/|/private/',text,re.I)
    target=ROOT/'ACK_TIMESTAMPS.json'
    if target.exists(): assert target.read_text()==text, 'Preserve differing existing output'
    else:
        with target.open('x') as f:f.write(text)
    print(text)


if __name__=='__main__': main()
