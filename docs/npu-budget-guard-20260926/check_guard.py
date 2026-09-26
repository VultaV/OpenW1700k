#!/usr/bin/env python3
"""Bounded RV32 prefix/epilogue check. The candidate exists only in memory.

This is not a firmware emulator: only the two fixed, decoded code ranges below
may execute. Unknown instructions, uninitialized reads and other accesses fail.
Requires the already available Capstone; does not install packages or write blobs.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import capstone

BASE, ENTRY, GUARD, EXIT = 0x84000000, 0x84009DA4, 0x84009E1A, 0x84009EE4
RANGES = [(ENTRY, 0x84009E26), (EXIT, 0x84009F14)]
SHA = 'e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643'
OLD, NEW = bytes.fromhex('9374f50f'), bytes.fromhex('e284e1c5')
MASK = 0xFFFFFFFF
NAMES = 'zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6'.split()
REG = {name: number for number, name in enumerate(NAMES)}
SAVED = [REG[name] for name in ['ra', 'sp', 's0', 's1'] + ['s' + str(i) for i in range(2, 12)]]
EXTRA_BUDGETS = [0x10000, 0x10001, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFE, 0xFFFFFFFF]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(blob, rows, expected=OLD):
    require(len(blob) == 122336 and hashlib.sha256(blob).hexdigest() == SHA, 'wrong original program')
    require(blob[GUARD-BASE:GUARD-BASE+4] == expected == OLD, 'wrong baseline instruction')
    indexed = {row['address']: row for row in rows}
    for start, end in RANGES:
        pc = start
        while pc < end:
            row = indexed[pc]
            require(row['address'] == pc and row['size'] in (2, 4) and pc + row['size'] <= end,
                    'invalid saved instruction boundary')
            raw = blob[pc-BASE:pc-BASE+row['size']]
            require(raw.hex() == row['bytes'], 'saved decoder byte mismatch')
            pc += row['size']
        require(pc == end, 'saved decoder range does not end at boundary')
    candidate = bytearray(blob)
    candidate[GUARD-BASE:GUARD-BASE+4] = NEW
    return candidate


def decode(blob, candidate=False):
    decoder = capstone.Cs(capstone.CS_ARCH_RISCV, capstone.CS_MODE_RISCV32 | capstone.CS_MODE_RISCVC)
    program, listing = {}, []
    for start, end in RANGES:
        pc = start
        for insn in decoder.disasm(bytes(blob[start-BASE:end-BASE]), start):
            require(insn.address == pc, 'fresh decoder gap')
            pc += insn.size
            op, operands = insn.mnemonic, [part.strip() for part in insn.op_str.split(',')]
            if op in ('slli', 'addi', 'andi', 'add', 'bltu'):
                args = [REG[operands[0]], REG[operands[1]],
                        REG[operands[2]] if op == 'add' else int(operands[2], 0)]
            elif op in ('auipc', 'lui', 'c.lui', 'c.li', 'c.addi', 'c.addi16sp', 'c.beqz'):
                args = [REG[operands[0]], int(operands[1], 0)]
            elif op in ('c.add', 'c.mv'):
                args = [REG[operands[0]], REG[operands[1]]]
            elif op in ('lw', 'sw', 'sb', 'c.lwsp', 'c.swsp'):
                match = re.fullmatch(r'(-?(?:0x[0-9a-f]+|\d+))\((\w+)\)', operands[1])
                require(match is not None, 'unknown memory operand')
                args = [REG[operands[0]], REG[match[2]], int(match[1], 0)]
            elif op == 'c.jr' and operands == ['ra']:
                args = [REG['ra']]
            else:
                raise ValueError(f'unsupported opcode at {insn.address:#x}: {op}')
            program[insn.address] = (insn.size, op, args)
            listing.append({'pc': hex(insn.address), 'bytes': insn.bytes.hex(), 'instruction': op + ' ' + insn.op_str})
        require(pc == end, 'fresh decoder stopped before range end')
    if candidate:
        require(program[GUARD] == (2, 'c.mv', [REG['s1'], REG['s8']]), 'wrong candidate move')
        require(program[GUARD+2] == (2, 'c.beqz', [REG['a1'], EXIT-GUARD-2]), 'wrong guard target')
    return program, listing


class State:
    """Only fixed prefix/epilogue effects; no descriptor, allocator or MMIO model."""
    def __init__(self, band, budget):
        self.regs = [(0xA5100101 * (i + 1) ^ budget) & MASK for i in range(32)]
        self.regs[0], self.regs[1], self.regs[2], self.regs[3] = 0, 0x12000000, 0x20001000, 0x20000000
        self.regs[10], self.regs[11] = band, budget
        self.initial = tuple(self.regs)
        self.pc, self.stack = ENTRY, {}
        self.index_address = self.regs[3] + 0x3D4 + band * 4
        self.initial_index = (budget * 17 + band * 3) % (512 if band == 0 else 1024)
        # Actual prefix uses this PC-relative table. Values are synthetic fixtures.
        table = (0x84009DB6 + (0xBA8F8 << 12) + 0x172) & MASK
        self.globals = {self.index_address: self.initial_index, table + band * 4: 0x50000000 + band * 0x2000}
        self.external_writes, self.read_addresses = [], set()

    def load(self, address):
        self.read_addresses.add(address)
        if address in self.globals:
            return self.globals[address]
        require(all(address+i in self.stack for i in range(4)), f'uninitialized or forbidden read {address:#x}')
        return sum(self.stack[address+i] << (i * 8) for i in range(4))

    def store(self, address, value, width):
        if self.initial[2] - 0x70 <= address and address + width <= self.initial[2]:
            for i in range(width):
                self.stack[address+i] = value >> (i * 8) & 255
        else:
            require(address == self.index_address and width == 4, f'forbidden external/MMIO write {address:#x}')
            self.globals[address] = value
            self.external_writes.append((self.pc, address, value))

    def run(self, program, stop):
        steps = 0
        while self.pc != stop:
            require(self.pc in program, f'execution left bounded code at {self.pc:#x}')
            size, op, a = program[self.pc]
            r, next_pc = self.regs, self.pc + size
            if op == 'addi': r[a[0]] = (r[a[1]] + a[2]) & MASK
            elif op == 'andi': r[a[0]] = r[a[1]] & a[2]
            elif op == 'slli': r[a[0]] = (r[a[1]] << a[2]) & MASK
            elif op == 'add': r[a[0]] = (r[a[1]] + r[a[2]]) & MASK
            elif op == 'auipc': r[a[0]] = (self.pc + (a[1] << 12)) & MASK
            elif op in ('lui', 'c.lui'): r[a[0]] = (a[1] << 12) & MASK
            elif op == 'c.li': r[a[0]] = a[1] & MASK
            elif op in ('c.addi', 'c.addi16sp'): r[a[0]] = (r[a[0]] + a[1]) & MASK
            elif op == 'c.add': r[a[0]] = (r[a[0]] + r[a[1]]) & MASK
            elif op == 'c.mv': r[a[0]] = r[a[1]]
            elif op in ('lw', 'c.lwsp'): r[a[0]] = self.load((r[a[1]] + a[2]) & MASK)
            elif op in ('sw', 'sb', 'c.swsp'): self.store((r[a[1]] + a[2]) & MASK, r[a[0]], 1 if op == 'sb' else 4)
            elif op == 'bltu': next_pc = self.pc + a[2] if r[a[0]] < r[a[1]] else next_pc
            elif op == 'c.beqz': next_pc = self.pc + a[1] if r[a[0]] == 0 else next_pc
            elif op == 'c.jr': next_pc = r[a[0]] & ~1
            else: raise ValueError('unsupported step')
            require(r[0] == 0, 'unexpected x0 write')
            self.pc = next_pc
            steps += 1
            require(steps < 100, 'bounded instruction limit exceeded')

    def snapshot(self):
        return (tuple(self.regs), self.stack, self.globals, self.external_writes, self.read_addresses, self.pc)


def check_states(original, candidate):
    results = []
    for band in (0, 1, 255):
        positives, zero_result = 0, None
        for budget in list(range(65536)) + EXTRA_BUDGETS:
            old, new = State(band, budget), State(band, budget)
            if budget:
                for stop in (0x84009E1E, 0x84009E26):
                    old.run(original, stop)
                    new.run(candidate, stop)
                    require(old.snapshot() == new.snapshot(), 'positive state changed')
                require(new.load(new.initial[2] - 0x70 + 0x2C) == min(budget, 128), 'budget clamp changed')
                require(not new.external_writes, 'prefix wrote external state')
                positives += 1
            else:
                old.run(original, 0x84009E26)
                new.run(candidate, new.initial[1])
                require(new.regs[10] == 0 and all(new.regs[i] == new.initial[i] for i in SAVED), 'zero return/ABI restoration mismatch')
                require(new.external_writes == [(0x84009EF4, new.index_address, new.initial_index)], 'zero path advanced or changed index')
                require(new.globals[new.index_address] == new.initial_index, 'consumer index changed')
                require(old.load(old.initial[2] - 0x70 + 0x2C) == 0, 'baseline zero was unexpectedly guarded')
                external_reads = sorted(new.read_addresses.intersection(new.globals))
                require(external_reads == sorted(new.globals), 'unexpected external read set')
                try:
                    old.run(original, old.initial[1])
                except ValueError as error:
                    require(str(error) == 'execution left bounded code at 0x84009e26',
                            'baseline rejected for an unrelated reason')
                else:
                    raise ValueError('baseline zero incorrectly satisfied no-descriptor return contract')
                zero_result = {'return': 0, 'sp_ra_callee_saved_restored': True,
                               'same_index_store': {'pc': '0x84009ef4', 'value': new.initial_index},
                               'external_reads': len(external_reads),
                               'external_read_addresses': [hex(address) for address in external_reads],
                               'descriptor_allocator_mmio_reached': False,
                               'baseline_no_descriptor_return_contract': 'rejected_at_0x84009e26',
                               'baseline_reaches_first_descriptor_boundary_with_budget_zero': True}
        results.append({'band': band, 'normal_direct_caller': band in (0, 1),
                        'positive_cases': positives, 'state_checkpoints_per_positive': 2,
                        'positive_failures': 0, 'zero_case': zero_result})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blob', type=Path, required=True)
    parser.add_argument('--instructions', type=Path, required=True)
    args = parser.parse_args()
    blob, rows = args.blob.read_bytes(), json.loads(args.instructions.read_text())
    candidate = prepare(blob, rows)
    old_program, old_listing = decode(blob)
    new_program, new_listing = decode(candidate, True)
    rejected = []
    try: prepare(blob, rows, expected=bytes(4))
    except ValueError: rejected.append('wrong_expected_baseline_word')
    bad_blob = bytearray(blob)
    bad_blob[0] ^= 1
    try: prepare(bad_blob, rows)
    except ValueError: rejected.append('wrong_full_program_hash')
    bad_rows = [dict(row, size=0) if row['address'] == ENTRY else row for row in rows]
    try: prepare(blob, bad_rows)
    except ValueError: rejected.append('zero_sized_saved_instruction')
    bad_target = bytearray(candidate)
    bad_target[GUARD-BASE+2] ^= 4
    try: decode(bad_target, True)
    except ValueError: rejected.append('wrong_candidate_branch_target')
    require(len(rejected) == 4, 'negative control accepted')
    result = {'program_sha256': SHA, 'program_bytes': len(blob), 'candidate_memory_only': True,
              'modified_blob_file_written': False, 'candidate_sha256': hashlib.sha256(candidate).hexdigest(),
              'guard': {'pc': hex(GUARD), 'before': OLD.hex(), 'after': NEW.hex(), 'target': hex(EXIT)},
              'fresh_decoder': 'Capstone ' + capstone.__version__, 'original_selected_instructions': len(old_listing),
              'candidate_selected_instructions': len(new_listing), 'ranges': [[hex(a), hex(b)] for a, b in RANGES],
              'candidate_instructions': new_listing, 'negative_controls_rejected': rejected,
              'budget_sweep': '0..65535 inclusive', 'additional_32bit_boundaries': EXTRA_BUDGETS,
              'results': check_states(old_program, new_program),
              'limitations': ['Only fixed prefix/epilogue standard instructions execute; all other code/opcodes/accesses fail.',
                              'Synthetic register/stack/index/table fixtures; not actual RAM, MMIO, firmware execution or weak-memory modeling.',
                              'Band 255 is an artificial robustness input, not a supported caller or proven valid hardware table index.',
                              'Same-index store is retained; concurrent reset and unknown indirect/mid-function entries are not proved safe.',
                              'No modified firmware artifact, distribution permission, installation, or Air stall repair is established.',
                              'Earlier clang RV32 assembler attempt failed; it is not counted as successful validation.']}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
