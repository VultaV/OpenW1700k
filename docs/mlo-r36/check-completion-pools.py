#!/usr/bin/env python3
"""Read-only byte correspondence and ring arithmetic; not firmware execution."""
import argparse
import copy
import hashlib
import json
import struct
from pathlib import Path

BASE = 0x84000000
SHA256 = "e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643"
RANGES = [
    (0x84004B96, 0x84004D0E), (0x84004D0E, 0x84004F4A),
    (0x84008F6E, 0x84009034), (0x840098A2, 0x840098D4),
    (0x8400990E, 0x840099B4), (0x8400A3F6, 0x8400A5FA),
    (0x8400B0A6, 0x8400B432), (0x8400D0AE, 0x8400D1A0),
    (0x8400E084, 0x8400E27A), (0x8400E4DE, 0x8400E514),
    (0x8400F8BE, 0x8400FAB2),
]
ANCHORS = [
    0x84004BAA, 0x84004BB8, 0x84004BE8, 0x84004BF8,
    0x84004D22, 0x84004D44, 0x84004D6E, 0x84004DC0,
    0x84004DEA, 0x84004DF2, 0x84004E14, 0x84004E18,
    0x84004E42, 0x84004E5A, 0x84004E5E, 0x84004ED0, 0x84004EF4,
    0x84008F76, 0x84008FAE, 0x84008FBE, 0x84008FE2, 0x84009008,
    0x840098A2, 0x840098B4, 0x840098B8, 0x840098D0,
    0x8400993C, 0x8400997E, 0x84009992, 0x840099A6,
    0x8400A570, 0x8400A574, 0x8400A58C, 0x8400A5B2, 0x8400A5DA,
    0x8400B100, 0x8400B108, 0x8400B1AE, 0x8400B1E8,
    0x8400B20C, 0x8400B25E, 0x8400B308, 0x8400B342,
    0x8400B408, 0x8400B42C, 0x8400B430,
    0x8400D144, 0x8400D172, 0x8400D17A, 0x8400D19E,
    0x8400E0AE, 0x8400E0B2, 0x8400E500, 0x8400E510,
    0x8400F95E, 0x8400F98A, 0x8400FA04, 0x8400FA2E,
]


def verify(blob, rows):
    if len(blob) != 122336 or hashlib.sha256(blob).hexdigest() != SHA256:
        raise ValueError("unrecognized vendor program")
    indexed = {row["address"]: row for row in rows}
    result = []
    for start, end in RANGES:
        selected = [row for row in rows if start <= row["address"] < end]
        cursor = start
        for row in selected:
            address, size = row["address"], row["size"]
            raw = bytes.fromhex(row["bytes"])
            if address != cursor or len(raw) != size or blob[address - BASE:address - BASE + size] != raw:
                raise ValueError(f"decoder correspondence mismatch at {address:#x}")
            cursor += size
        if cursor != end:
            raise ValueError(f"incomplete selected range {start:#x}")
        result.append({"start": hex(start), "end_exclusive": hex(end),
                       "rows": len(selected), "sha256": hashlib.sha256(blob[start - BASE:end - BASE]).hexdigest()})
    anchors = [{"pc": hex(pc), **{key: indexed[pc][key] for key in ("size", "bytes", "mnemonic", "operands")}} for pc in ANCHORS]
    table = 0x8401BD64
    entry = table + 6 * 4
    offset = struct.unpack_from("<i", blob, entry - BASE)[0]
    if table + offset != 0x8400E0A2:
        raise ValueError("RRO action6 target mismatch")
    return {"program_sha256": SHA256, "program_bytes": len(blob),
            "matched_rows": sum(item["rows"] for item in result), "ranges": result,
            "anchors": anchors, "rro_action6": {"entry": hex(entry), "bytes": blob[entry - BASE:entry - BASE + 4].hex(), "target": hex(table + offset)}}


class Pool:
    def __init__(self, count):
        self.count, self.entries, self.consumer, self.producer = count, list(range(count)), 0, 0

    def allocate(self):
        following = (self.consumer + 1) % self.count
        if following == self.producer:
            return None
        value = self.entries[self.consumer]
        self.consumer = following
        return value

    def release(self, value):
        self.entries[self.producer] = value
        self.producer = (self.producer + 1) % self.count


def ring_model():
    packet, token = Pool(16384), Pool(8192)
    borrowed_token = token.allocate()
    borrowed_packets = [packet.allocate() for _ in range(16383)]
    assert borrowed_packets == list(range(16383)) and packet.allocate() is None
    for _ in range(10000):
        assert packet.allocate() is None
    token.release(borrowed_token)
    assert packet.allocate() is None
    packet.release(borrowed_packets[0])
    first = packet.allocate()
    assert first == 16383 and packet.allocate() is None
    packet.release(borrowed_packets[1])
    second = packet.allocate()
    assert second == 0
    return {"cases_passed": 5, "initial_packet_allocatable": 16383,
            "unchanged_failure_retries": 10000, "token_return_rescues_packet_pool": False,
            "single_packet_return_rescues_next_allocation": True, "first_two_rescued_ids": [first, second],
            "scope": "Exact scalar ring arithmetic with legal releases; not firmware execution. Runtime reachability, aggregate ownership, concurrency, fairness, locks and MMIO are not modeled."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blob", type=Path, required=True)
    parser.add_argument("--instructions", type=Path, required=True)
    args = parser.parse_args()
    blob, rows = args.blob.read_bytes(), json.loads(args.instructions.read_text())
    result = verify(blob, rows)
    changed_blob = bytearray(blob)
    changed_blob[0xB100] ^= 1
    changed_rows = copy.deepcopy(rows)
    next(row for row in changed_rows if row["address"] == 0x8400B100)["bytes"] = "00000000"
    rejected = 0
    for bad_blob, bad_rows in ((changed_blob, rows), (blob, changed_rows)):
        try:
            verify(bad_blob, bad_rows)
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError("negative control was not rejected")
    result["negative_controls_rejected"] = rejected
    result["model"] = ring_model()
    result["limitation"] = "Byte correspondence is not independent instruction decoding, semantic proof, hardware testing or evidence of Air stall attribution. Unsupported custom opcodes in the saved linear decoder remain uninterpreted."
    print(json.dumps(result, indent=2))
