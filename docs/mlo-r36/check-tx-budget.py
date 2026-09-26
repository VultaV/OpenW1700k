#!/usr/bin/env python3
"""Check r35 vendor bytes and bounded scalar models; never execute/change firmware."""
import argparse
import copy
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = 0x84000000
SHA256 = "e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643"
RANGES = [(0x84000104, 0x840001C0), (0x84009DA4, 0x84009FC8),
          (0x8400E084, 0x8400E278), (0x8400E87A, 0x8400EC48),
          (0x8400EC48, 0x8400EE10), (0x8400F1EA, 0x8400F508)]
# Expected raw bytes at the caller/callee arithmetic and the ownership writes.
EXACT = {
    0x84004212: "732540f1",  # csrr a0,mhartid
    0x8400ECBA: "9544",    # s1=5, caller admission/skip threshold
    0x8400ED18: "7d14", 0x8400ED60: "7d14",  # s0--
    0x8400ED88: "9305a4ff", 0x8400EDD2: "9305a4ff",  # a1=s0-6
    0x84009DC2: "13070008", 0x84009DE4: "1307f007",  # 128,127
    0x84009DF0: "2ed6", 0x84009ED8: "b257",  # budget store/load
    0x84009EDA: "fd17", 0x84009EDC: "3ed6",  # budget-- and store
    0x8400EB7E: "23a04401", 0x8400F3EE: "5cc1",  # output writes
}
# These standard RISC-V branch offsets are independently decoded below.
BRANCHES = {
    0x84000108: 0x84004212, 0x8400013E: 0x840001A0,
    0x840001B4: 0x8400EE0A, 0x8400EE0E: 0x8400EC48,
    0x8400ED14: 0x8400EDF0, 0x8400ED22: 0x8400ED88,
    0x8400ED5C: 0x8400EDB8, 0x8400ED6A: 0x8400EDD2,
    0x8400ED8E: 0x84009DA4, 0x8400EDD8: 0x84009DA4,
    0x84009DEC: 0x84009DF2, 0x84009EDE: 0x84009E26,
    0x8400E9BE: 0x8400EA78, 0x8400E9C2: 0x8400EA78,
    0x8400E9CE: 0x8400EA78, 0x8400EAC6: 0x8400EB10,
    0x8400EAD2: 0x8400EB10, 0x8400F28E: 0x8400F30A,
    0x8400F292: 0x8400F30A, 0x8400F29E: 0x8400F30A,
    0x8400F350: 0x8400F386, 0x8400F35C: 0x8400F386,
    0x84009E32: 0x84009FA4, 0x84009E7A: 0x84009F18,
    0x84009EBE: 0x84009F66, 0x84009ED4: 0x84009EE0,
}


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def branch_target(pc, raw):
    """Only standard B/JAL/C.J/C.JAL/C.BEQZ/C.BNEZ, no vendor opcodes."""
    value = int.from_bytes(raw, "little")
    if len(raw) == 4 and value & 0x7F == 0x63:
        offset = ((value >> 31) << 12 | ((value >> 7) & 1) << 11 |
                  ((value >> 25) & 0x3F) << 5 | ((value >> 8) & 15) << 1)
        kind, bits = "B", 13
    elif len(raw) == 4 and value & 0x7F == 0x6F:
        offset = ((value >> 31) << 20 | ((value >> 12) & 0xFF) << 12 |
                  ((value >> 20) & 1) << 11 | ((value >> 21) & 0x3FF) << 1)
        kind, bits = "JAL", 21
    elif len(raw) == 2 and value & 3 == 1 and value >> 13 in (1, 5):
        offset = (((value >> 12) & 1) << 11 | ((value >> 8) & 1) << 10 |
                  ((value >> 9) & 3) << 8 | ((value >> 6) & 1) << 7 |
                  ((value >> 7) & 1) << 6 | ((value >> 2) & 1) << 5 |
                  ((value >> 11) & 1) << 4 | ((value >> 3) & 7) << 1)
        kind, bits = "CJ", 12
    elif len(raw) == 2 and value & 3 == 1 and value >> 13 in (6, 7):
        offset = (((value >> 12) & 1) << 8 | ((value >> 5) & 3) << 6 |
                  ((value >> 2) & 1) << 5 | ((value >> 10) & 3) << 3 |
                  ((value >> 3) & 3) << 1)
        kind, bits = "CB", 9
    else:
        raise ValueError(f"unsupported branch at {pc:#x}")
    return pc + signed(offset, bits), kind


def verify(blob, rows):
    if len(blob) != 122336 or hashlib.sha256(blob).hexdigest() != SHA256:
        raise ValueError("unrecognized vendor program")
    indexed = {row["address"]: row for row in rows}
    matched = []
    for start, end in RANGES:
        selected = [row for row in rows if start <= row["address"] < end]
        cursor = start
        for row in selected:
            address, size = row["address"], row["size"]
            raw = bytes.fromhex(row["bytes"])
            if address != cursor or len(raw) != size or blob[address-BASE:address-BASE+size] != raw:
                raise ValueError(f"saved decoder correspondence mismatch at {address:#x}")
            cursor += size
        if cursor != end:
            raise ValueError(f"incomplete selected range {start:#x}")
        matched.append({"start": hex(start), "end_exclusive": hex(end), "rows": len(selected),
                        "sha256": hashlib.sha256(blob[start-BASE:end-BASE]).hexdigest()})
    anchors = []
    for pc in sorted(EXACT.keys() | BRANCHES.keys()):
        row = indexed[pc]
        raw = blob[pc-BASE:pc-BASE+row["size"]]
        if raw.hex() != row["bytes"] or (pc in EXACT and raw.hex() != EXACT[pc]):
            raise ValueError(f"anchor mismatch at {pc:#x}")
        item = {"pc": hex(pc), **{key: row[key] for key in ("bytes", "mnemonic", "operands")}}
        if pc in BRANCHES:
            target, kind = branch_target(pc, raw)
            if target != BRANCHES[pc]:
                raise ValueError(f"raw branch target mismatch at {pc:#x}")
            item.update(raw_branch_class=kind, raw_target=hex(target))
        anchors.append(item)
    tables = []
    for table, index, expected in [(0x8401A2E8, 2, 0x8400013E),
                                   (0x8401BD64, 4, 0x8400E220),
                                   (0x8401BD64, 7, 0x8400E0C0)]:
        entry = table + index * 4
        target = table + struct.unpack_from("<i", blob, entry-BASE)[0]
        if target != expected:
            raise ValueError("jump table mismatch")
        tables.append({"table": hex(table), "index": index, "entry_bytes": blob[entry-BASE:entry-BASE+4].hex(), "target": hex(target)})
    return {"program_sha256": SHA256, "program_bytes": len(blob),
            "matched_rows": sum(item["rows"] for item in matched), "ranges": matched,
            "anchors": anchors, "independent_standard_branch_checks": len(BRANCHES), "jump_tables": tables}


def caller_budget(free, ring_count, safe=False):
    if not 0 <= free < ring_count:
        raise ValueError("free count outside one-empty-slot ring range")
    if free <= 5:
        return None
    after_slow_reserve = (free - 1) & 0xFFFF
    if after_slow_reserve == 5:
        return None
    argument = after_slow_reserve - 6
    if safe and argument == 0:
        return None
    return 128 if argument > 127 else argument


def budget_models():
    failures, examples, arithmetic = [], [], 0
    valid_cases = safe_passes = baseline_passes = rejected = 0
    for count in (512, 1024):
        for free in range(count + 1):  # include invalid count as a boundary control
            if free == count:
                try:
                    caller_budget(free, count)
                except ValueError:
                    rejected += 1
                continue
            valid_cases += 1
            for producer in (0, count - 1):
                dma = (producer + free + 1) % count
                calculated = dma - producer - 1 if producer < dma else dma + count - producer - 1
                assert calculated == free
                arithmetic += 1
            baseline = caller_budget(free, count)
            safe = caller_budget(free, count, safe=True)
            good = baseline is None or 1 <= baseline <= 128
            baseline_passes += int(good)
            assert safe is None or 1 <= safe <= 128
            safe_passes += 1
            if not good:
                first_remaining = (baseline - 1) & 0xFFFFFFFF
                assert first_remaining == 0xFFFFFFFF
                failures.append({"ring_count": count, "free": free,
                                 "callee_initial_budget": baseline,
                                 "after_first_success": first_remaining,
                                 "after_128_successes": (baseline - 128) & 0xFFFFFFFF,
                                 "arithmetic_successes_until_zero": 1 << 32})
            if free in (0, 5, 6, 7, 8, 134, 135, count - 1):
                examples.append({"ring_count": count, "free": free,
                                 "baseline_budget": baseline, "safe_budget": safe})
    assert len(failures) == 2 and all(item["free"] == 7 for item in failures)
    return {"valid_boundary_cases": valid_cases, "ring_arithmetic_checks": arithmetic,
            "invalid_ring_limit_controls_rejected": rejected,
            "baseline": {"passed": baseline_passes, "failed": len(failures), "failures": failures},
            "safe_model": {"passed": safe_passes, "failed": 0,
                           "change": "Do not enter the TDM consumer when its argument is zero; no firmware modification."},
            "examples": examples,
            "scope": "Scalar branch/budget arithmetic only. No packet/DMA/MMIO execution, concurrency or time-to-failure model."}


def wait_models():
    cases = []
    for current_ready in (False, True):
        for next_ready in (False, True):
            for stop in (False, True):
                for current_expired in (False, True):
                    current_exit = current_ready or stop or current_expired
                    actual_publish = current_exit and (next_ready or stop)
                    safe_publish = current_ready and next_ready
                    cases.append({"current_ready": current_ready, "next_ready": next_ready,
                                  "stop": stop, "current_expired": current_expired,
                                  "actual_reaches_publish": actual_publish,
                                  "safe_ownership_model_publishes": safe_publish})
    nonready = [case for case in cases if case["actual_reaches_publish"] and not case["safe_ownership_model_publishes"]]
    assert len(nonready) == 7
    return {"cases": len(cases), "publish_continuations_without_both_ready": len(nonready),
            "publish_continuations_with_current_not_ready": sum(not case["current_ready"] for case in nonready),
            "examples": nonready,
            "scope": "Frozen descriptor/stop observations; no claim that every combination is reachable or erroneous during a coordinated hardware stop."}


def relative(path):
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return path.name  # avoid publishing user-specific filesystem identifiers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blob", type=Path, required=True)
    parser.add_argument("--instructions", type=Path, required=True)
    args = parser.parse_args()
    blob, rows = args.blob.read_bytes(), json.loads(args.instructions.read_text())
    result = verify(blob, rows)
    bad_blob = bytearray(blob)
    bad_blob[0xED22] ^= 1
    bad_rows = copy.deepcopy(rows)
    next(row for row in bad_rows if row["address"] == 0x84009DF0)["bytes"] = "0000"
    rejected = 0
    for candidate_blob, candidate_rows in ((bad_blob, rows), (blob, bad_rows)):
        try:
            verify(candidate_blob, candidate_rows)
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError("negative correspondence control accepted")
    result.update(schema_version=1, status="PASS_EXPECTED_BASELINE_FAILURE_REPRODUCED",
                  input_program=relative(args.blob), input_instructions=relative(args.instructions),
                  instructions_sha256=hashlib.sha256(args.instructions.read_bytes()).hexdigest(),
                  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  correspondence_negative_controls_rejected=rejected,
                  budget=budget_models(), stop_timeout=wait_models(),
                  runtime_execution=False, firmware_modified=False,
                  limitations=["The full saved disassembly is not independently decoded; only listed standard branch offsets are.",
                               "Vendor custom opcodes, complete CFG, hardware ordering and concurrent actors are not modeled.",
                               "Early RX-empty, allocator/dispatch failure and hardware waits can terminate/block the scalar path first.",
                               "A 2^32 decrement count is arithmetic, not an observed uninterrupted execution.",
                               "No causal attribution to the Air sleep/wake stall; no live test was performed."])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
