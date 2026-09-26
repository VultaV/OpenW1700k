#!/usr/bin/env python3
"""Check three preserved reverse-TCP iperf3 reports without network access.

Usage: check-sender.py TRIAL_DIRECTORY --output NEW_JSON
TRIAL_DIRECTORY contains bypass-cpu-open-60, bypass-restored-hw-open-60,
and bypass-restored-hw-closed-60, each containing iperf.json.
Inputs are read-only. Endpoint tuples are matched in memory and never exported.
Transfer/cwnd values in server_output_text are rounded human-readable reports.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import statistics


EXPECTED = {
    'cpu_open': '9e6eb164345028e9c11ded7e82398adaaaf28b58c708cb2e8b9574690724cb3c',
    'hw_open': 'ff20b2a6e7585d968a8774a7a0ff1a6800ebd0bd0c8e8e3dc8e777f28769dab5',
    'hw_closed': '4526bed48a81badda5451b7a4f55127087b5bcf475179158008480d9067c1bee',
}
TRIAL_NAMES = ('bypass-cpu-open-60', 'bypass-restored-hw-open-60',
               'bypass-restored-hw-closed-60')
UNITS = {'Bytes': 1, 'KBytes': 1024, 'MBytes': 1024**2,
         'GBytes': 1024**3, 'TBytes': 1024**4}
NUMBER = r'([\d.]+)'
PREFIX = (r'^\[\s*(\d+)\]\s+' + NUMBER + '-' + NUMBER + r'\s+sec\s+' +
          NUMBER + r'\s+([KMGT]?Bytes)\s+' + NUMBER + r'\s+([KMGT]?bits/sec)\s+')
INTERVAL = re.compile(PREFIX + r'(\d+)\s+' + NUMBER + r'\s+([KMGT]?Bytes)\s*$')
FINAL = re.compile(PREFIX + r'(\d+)\s+sender\s*$')
CONNECTION = re.compile(r'^\[\s*(\d+)\]\s+local (\S+) port (\d+) '
                        r'connected to (\S+) port (\d+)\s*$')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def groups(indices):
    result = []
    for index in indices:
        if result and index == result[-1][-1] + 1:
            result[-1].append(index)
        else:
            result.append([index])
    return result


def check(label, data, digest):
    require(data['start']['test_start']['protocol'] == 'TCP' and
            data['start']['test_start']['reverse'] == 1, f'{label}: not reverse TCP')
    connections = data['start']['connected']
    require(len(connections) == 4, f'{label}: expected four client connections')
    mapping, finals, rows, tails = {}, {}, [], []
    for line in data['server_output_text'].splitlines():
        match = CONNECTION.fullmatch(line)
        if match:
            sid, local, lport, remote, rport = match.groups()
            matches = [c['socket'] for c in connections
                       if (c['remote_host'], c['remote_port'], c['local_host'], c['local_port'])
                       == (local, int(lport), remote, int(rport))]
            require(len(matches) == 1 and int(sid) not in mapping,
                    f'{label}: ambiguous server/client stream mapping')
            mapping[int(sid)] = matches[0]
            continue
        match = FINAL.fullmatch(line)
        if match:
            sid, start, end, _, _, _, _, retrans = match.groups()
            require(int(sid) not in finals and float(start) == 0 and
                    60 <= float(end) < 61, f'{label}: invalid sender final row')
            finals[int(sid)] = int(retrans)
            continue
        match = INTERVAL.fullmatch(line)
        if match:
            sid, start, end, amount, unit, _, _, retrans, cwnd, cunit = match.groups()
            start, end = float(start), float(end)
            index = round(start)
            row = {'server_stream': int(sid), 'bin': index,
                   'start_s': start, 'end_s': end,
                   'reported_transfer_bytes_approx': float(amount) * UNITS[unit],
                   'retransmits': int(retrans),
                   'reported_cwnd_bytes_approx': float(cwnd) * UNITS[cunit]}
            if start == 60 and 0 < end - start < .2:
                tails.append(row)
                continue
            require(0 <= index < 60 and abs(start - index) < .12 and
                    abs(end - index - 1) < .12 and .9 < end - start < 1.1,
                    f'{label}: unexpected server interval')
            rows.append(row)

    ids = sorted(mapping)
    require(len(ids) == 4 and len(set(mapping.values())) == 4 and set(finals) == set(ids),
            f'{label}: expected four uniquely mapped sender final rows')
    require(len(rows) == 240 and
            {(r['server_stream'], r['bin']) for r in rows} ==
            {(sid, i) for sid in ids for i in range(60)},
            f'{label}: expected exactly four streams by sixty unique intervals')
    require(len(tails) == 4 and {r['server_stream'] for r in tails} == set(ids) and
            sum(r['retransmits'] for r in tails) == 0,
            f'{label}: unexpected final partial intervals or retransmissions')
    end_streams = {s['sender']['socket']: s['sender'] for s in data['end']['streams']}
    require(len(end_streams) == 4 and set(end_streams) == set(mapping.values()),
            f'{label}: client end stream set mismatch')
    totals = []
    for sid in ids:
        retrans = sum(r['retransmits'] for r in rows if r['server_stream'] == sid)
        require(retrans == finals[sid] == end_streams[mapping[sid]]['retransmits'],
                f'{label}: per-stream retransmission totals differ')
        totals.append({'server_stream': sid, 'client_socket': mapping[sid],
                       'interval_retransmits': retrans, 'server_final_retransmits': finals[sid],
                       'client_end_retransmits': end_streams[mapping[sid]]['retransmits']})
    retrans_total = sum(r['retransmits'] for r in rows)
    require(retrans_total == data['end']['sum_sent']['retransmits'],
            f'{label}: aggregate retransmission total differs')

    require(len(data['intervals']) == 60, f'{label}: expected sixty client intervals')
    bins = []
    for i, interval in enumerate(data['intervals']):
        client = interval['sum']
        require(abs(client['start'] - i) < .12 and abs(client['end'] - i - 1) < .12,
                f'{label}: client relative time grid mismatch')
        require(len(interval['streams']) == 4 and
                {s['socket'] for s in interval['streams']} == set(mapping.values()) and
                sum(s['bytes'] for s in interval['streams']) == client['bytes'],
                f'{label}: client stream byte sum mismatch')
        flows = sorted((r for r in rows if r['bin'] == i), key=lambda r: r['server_stream'])
        bins.append({'bin': i, 'client_start_s': client['start'], 'client_end_s': client['end'],
                     'client_mbps': client['bits_per_second'] / 1e6,
                     'server_sum_mbps_approx': sum(r['reported_transfer_bytes_approx'] /
                         (r['end_s'] - r['start_s']) for r in flows) * 8 / 1e6,
                     'server_flows': flows})
    alignment = {str(shift): statistics.mean(abs(bins[i]['client_mbps'] -
                 bins[i + shift]['server_sum_mbps_approx'])
                 for i in range(60) if 0 <= i + shift < 60) for shift in (-1, 0, 1)}
    require(alignment['0'] < alignment['-1'] and alignment['0'] < alignment['1'],
            f'{label}: same-bin alignment is not best within plus/minus one second')
    zero = [r for r in rows if r['reported_transfer_bytes_approx'] == 0]
    all_zero = [b['bin'] for b in bins if all(r['reported_transfer_bytes_approx'] == 0
                                            for r in b['server_flows'])]
    mss = data['start']['tcp_mss_default']
    near_mss = [r for r in rows if r['reported_cwnd_bytes_approx'] <= mss * 1.02]
    dips = []
    for group in groups([b['bin'] for b in bins if b['client_mbps'] < 500]):
        start, end = group[0], group[-1] + 1
        selected = [r for r in rows if start <= r['bin'] < end]
        threshold = 1000 if label == 'cpu_open' else 1500
        recovery = next((b['bin'] for b in bins[end:] if b['client_mbps'] >= threshold), None)
        dips.append({'relative_interval_s': [start, end],
                     'client_min_mbps': min(bins[i]['client_mbps'] for i in group),
                     'server_sum_min_mbps_approx': min(bins[i]['server_sum_mbps_approx'] for i in group),
                     'retransmits_in_bins': sum(r['retransmits'] for r in selected),
                     'min_cwnd_bytes_approx': min(r['reported_cwnd_bytes_approx'] for r in selected),
                     'recovery_threshold_mbps': threshold, 'first_recovery_bin': recovery})
    return {'input_sha256': digest, 'status': 'PASS',
            'checks': {'four_streams_times_sixty_unique_rows': True,
                       'endpoint_matched_stream_mapping': True,
                       'per_stream_retransmission_totals_match': True,
                       'aggregate_retransmission_total_matches': True,
                       'client_stream_bytes_sum_matches': True,
                       'four_final_partial_intervals_have_zero_retransmissions': True,
                       'relative_grid_and_best_same_bin_alignment': True},
            'server_interval_rows': len(rows), 'client_interval_rows': len(bins),
            'receiver_mean_mbps': data['end']['sum_received']['bits_per_second'] / 1e6,
            'tcp_mss_default_bytes': mss, 'retransmits': retrans_total,
            'streams': totals, 'individual_zero_transfer_intervals': zero,
            'all_stream_zero_transfer_bins': all_zero,
            'cwnd_at_most_1_02_mss_intervals': near_mss,
            'final_partial_intervals_excluded_from_one_second_analysis': tails,
            'min_cwnd_bytes_approx': min(r['reported_cwnd_bytes_approx'] for r in rows),
            'alignment_mean_absolute_mbps_difference_by_server_bin_shift': alignment,
            'client_below_500mbps_groups': dips, 'intervals': bins}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trial_directory', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New JSON; existing files are refused')
    args = parser.parse_args()
    trials = {}
    for label, name in zip(EXPECTED, TRIAL_NAMES):
        raw = (args.trial_directory / name / 'iperf.json').read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(digest == EXPECTED[label], f'{label}: unexpected input SHA256')
        data = json.loads(raw)
        trials[label] = check(label, data, digest)
        if label == 'cpu_open':
            original = data
    negative_checks = {}
    for name in ('missing_sender_interval', 'wrong_stream_mapping'):
        altered = copy.deepcopy(original)
        if name == 'missing_sender_interval':
            lines = altered['server_output_text'].splitlines()
            del lines[next(i for i, line in enumerate(lines) if INTERVAL.fullmatch(line))]
            altered['server_output_text'] = '\n'.join(lines)
            expected_error = 'expected exactly four streams by sixty unique intervals'
        else:
            altered['start']['connected'][0]['remote_port'] += 1
            expected_error = 'ambiguous server/client stream mapping'
        try:
            check('cpu_open', altered, EXPECTED['cpu_open'])
        except ValueError as error:
            require(expected_error in str(error), f'{name}: wrong rejection reason')
            negative_checks[name] = 'rejected_as_expected'
        else:
            raise ValueError(f'{name}: malformed input incorrectly accepted')
    hw = trials['hw_open']
    require([(r['server_stream'], r['bin']) for r in hw['individual_zero_transfer_intervals']] == [(5, 6)],
            'HW-open zero-transfer event mismatch')
    require([(r['server_stream'], r['bin']) for r in hw['cwnd_at_most_1_02_mss_intervals']] == [(8, 5)],
            'HW-open one-MSS event mismatch; do not conflate the two streams')
    require(all(not t['all_stream_zero_transfer_bins'] for t in trials.values()),
            'Unexpected all-stream zero-transfer bin')
    for label in ('cpu_open', 'hw_closed'):
        require(not trials[label]['individual_zero_transfer_intervals'] and
                not trials[label]['cwnd_at_most_1_02_mss_intervals'],
                f'{label}: unexpected zero transfer or near-one-MSS event')
    result = {'status': 'PASS', 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Offline analysis of three pinned reverse-TCP reports; no network or device operations.',
              'limitations': [
                  'Server Transfer and Cwnd are rounded text values; derived bytes and rates are approximate.',
                  'Zero Transfer means no reported application transfer in that bin, not zero wire packets.',
                  'Retransmissions are Linux TCP observations, not a count of wireless packet losses.',
                  'Relative one-second alignment does not synchronize absolute clocks or identify packet timing.',
                  'Four final partial intervals per report are retained separately and excluded from full-bin zero counts.',
                  'Cwnd is sampled once per second; no RTT, RTO, ACK trace, receive window or UDP result is present.',
                  'These records show TCP responses but do not prove their initiating cause, RED behavior, or Air repair.',
              ], 'parser_negative_checks': negative_checks, 'trials': trials}
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.write('\n')
    print('PASS: three reports; each has 240 mapped sender rows and matching per-stream retransmission totals.')


if __name__ == '__main__':
    main()
