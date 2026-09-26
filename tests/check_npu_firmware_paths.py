#!/usr/bin/env python3
"""Match selected saved decoder rows to a pinned raw NPU firmware blob.

Usage: python3 tests/check_npu_firmware_paths.py FIRMWARE.bin INSTRUCTIONS.json
Read-only; Python standard library only. This checks addresses, sizes and bytes,
not decoded mnemonic correctness, control flow, runtime behavior or safety.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys


BASE = 0x84000000
SHA256 = "e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643"
RANGES = (
    ("tdma_submit", 0x840091B4, 0x840093D4, 179),
    ("software_pool_return_and_allocate", 0x84004D0E, 0x84004E1C, 92),
    ("hardware_mutex_helpers", 0x840064B4, 0x8400655C, 63),
    ("tdma_caller", 0x8400AEDC, 0x8400B074, 140),
    ("indication_worker", 0x8400CB1A, 0x8400CD1A, 162),
    ("rro_action_dispatch", 0x8400E084, 0x8400E292, 171),
)
RAW_ANCHORS = (
    ("rro_action3_table_entry", 0x8401BD70, "6224ffff"),
    ("rro_wrapper_call", 0x8400FC3E, "efe06fc4"),
    ("rro_wrapper_return", 0x8400FC44, "0545"),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check(blob, rows):
    digest = hashlib.sha256(blob).hexdigest()
    require(len(blob) == 122336 and digest == SHA256, "unexpected firmware size or SHA256")
    require(isinstance(rows, list), "decoder JSON must be a list")
    result = []
    for name, start, end, expected_count in RANGES:
        selected = [row for row in rows if start <= row["address"] < end]
        require(len(selected) == expected_count, f"{name}: unexpected decoder row count")
        cursor = start
        for row in selected:
            address, size = row["address"], row["size"]
            encoded = bytes.fromhex(row["bytes"])
            require(address == cursor and size in (2, 4) and len(encoded) == size,
                    f"{name}: non-contiguous or malformed row at {address:#x}")
            require(encoded == blob[address - BASE:address - BASE + size],
                    f"{name}: byte mismatch at {address:#x}")
            cursor += size
        require(cursor == end, f"{name}: end boundary mismatch")
        result.append(dict(name=name, start=hex(start), end_exclusive=hex(end),
                           matched_decoder_rows=len(selected)))
    for name, address, encoded in RAW_ANCHORS:
        raw = bytes.fromhex(encoded)
        require(blob[address - BASE:address - BASE + len(raw)] == raw,
                f"{name}: raw anchor mismatch")
    offset = int.from_bytes(blob[0x1BD70:0x1BD74], "little", signed=True)
    target = 0x8401BD64 + offset
    require(target == 0x8400E1C6, "RRO action3 table target mismatch")
    return dict(status="PASS", firmware_sha256=digest, firmware_bytes=len(blob),
                decoder_ranges=result, matched_decoder_rows=sum(r[3] for r in RANGES),
                raw_byte_anchors=len(RAW_ANCHORS), rro_action3_table_target=hex(target),
                scope="Pinned blob identity and selected decoder-row bytes only; "
                      "not mnemonic, control-flow, execution or defect verification.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("instructions", type=Path)
    args = parser.parse_args()
    try:
        result = check(args.firmware.read_bytes(), json.loads(args.instructions.read_text()))
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
