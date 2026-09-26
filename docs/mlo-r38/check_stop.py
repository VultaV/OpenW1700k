#!/usr/bin/env python3
"""Read-only, bounded RV32 stop-handshake evidence check; never executes firmware.

Requires Capstone already installed (or --capstone-path). Inputs are read-only;
changed byte copies exist only for rejection tests and are never written. Selected
standard instructions are freshly decoded; unknown vendor words are not emulated.
stdout is the sole output.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

BASE = 0x84000000
PROGRAM_SHA = 'e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643'
DATA_SHA = '61a75afb052feed2ceb2f3023e16f50317c05c78f9c8e564bf01924ce39c7ec1'
RANGES = [
    (0xe084, 0xe0c0), (0xe220, 0xe266), (0xfc2c, 0xfc4a),
    (0xff9c, 0xffb8), (0xd7ca, 0xd836), (0xce10, 0xce18),
    (0xcf10, 0xcf40), (0xd0c0, 0xd0c8), (0xd140, 0xd178),
    (0xec74, 0xec7c), (0xecb8, 0xecf6), (0x990e, 0x994a),
    (0x9960, 0x99b4), (0x4e1c, 0x4e76), (0xa3bc, 0xa3f6),
]
# Decoded operands are pinned as well as the complete original hashes. Branch
# operands are PC-relative displacements in this Capstone RISCV backend.
ANCHORS = {
    0xe0ae: 'jal -0x47a0', 0xe0b2: 'jal -0x4752', 0xe0bc: 'j -0x3d00',
    0xe232: 'sb a5, 0x4c7(a4)', 0xe23a: 'sw zero, 0x4b6(a5)',
    0xe242: 'sw zero, 0x4b2(a5)', 0xe24a: 'sb zero, 0x4b3(a5)',
    0xe256: 'sb zero, 0x4a6(a5)', 0xe25e: 'sb zero, 0x4a0(a5)',
    0xfc38: 'andi a0, a5, 0xf', 0xfc3e: 'jal -0x1bba', 0xfc44: 'c.li a0, 1',
    0xffa6: 'c.andi a0, 0xf', 0xffa8: 'jal -0x27de',
    0xffac: 'c.sw a0, 8(s0)', 0xffb2: 'c.li a0, 1',
    0xd7d0: 'c.li a5, 3', 0xd7d2: 'beq a0, a5, 0x3c',
    0xd81a: 'lbu a0, -0x11f(a0)', 0xd81e: 'c.lw a4, 0(a5)',
    0xd824: 'lbu a5, -0x12a(a5)', 0xd828: 'seqz a5, a5',
    0xd82c: 'seqz a0, a0', 0xd830: 'c.or a0, a5', 0xd832: 'c.or a0, a4',
    0xcf10: 'c.lw a5, 0(s0)', 0xcf12: 'c.bnez a5, 0x18',
    0xcf18: 'sw zero, 0x7d4(a5)', 0xcf34: 'sw a4, 0x7b8(a3)',
    0xd140: 'c.li s3, 1', 0xd144: 'lbu a5, 0(s0)',
    0xd14c: 'c.bnez a5, 0x1e', 0xd152: 'sb s3, 0x5a8(a5)',
    0xd16e: 'sb zero, 0x58c(a5)', 0xd172: 'jal -0x20cc',
    0xecb8: 'c.li s3, 3', 0xecc2: 'lbu a5, 0(s2)', 0xecc6: 'beq s3, a5, 0x28',
    0xecca: 'c.li a5, 1', 0xecd0: 'sb a5, -0x5d5(a4)',
    0xecf2: 'sb zero, -0x5f7(a5)',
    0x991e: 'lw a4, -0x7f4(a5)', 0x9928: 'beq a4, a5, 0x18',
    0x9932: 'jal -0x6220', 0x9936: 'lw a5, -0x7f4(s1)',
    0x993c: 'bne a4, a5, -0xc',
    0x9976: 'lw a5, -0x1c(s0)', 0x997a: 'c.slli a5, 0x10',
    0x997c: 'c.srli a5, 0x10', 0x997e: 'c.bnez a5, 0x18',
    0x9988: 'c.beqz s1, 0x28', 0x9992: 'j -0x4b76',
    0x999e: 'lw a5, -0x1c(s0)', 0x99a6: 'c.bnez a5, -0x10',
    0x99b0: 'c.li s1, 1', 0x99b2: 'c.j -0x3c',
    0x4e3e: 'c.lui a3, 4', 0x4e42: 'sh a5, 0(a4)',
    0x4e4a: 'bne a5, a3, -8', 0xa3d2: 'c.lui a4, 2',
    0xa3d4: 'sh a5, 0(a0)', 0xa3dc: 'bne a5, a4, -8',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(program, data):
    require(len(program) == 122336 and sha(program) == PROGRAM_SHA, 'program identity')
    require(len(data) == 3084 and sha(data) == DATA_SHA, 'data identity')


def tables(program, data):
    result = []
    for offset, raw, target in [(0x1bd74, 'bc24ffff', 0xe220),
                                 (0x1bd7c, '3e23ffff', 0xe0a2)]:
        word = program[offset:offset + 4]
        require(word.hex() == raw, 'action table word')
        actual = BASE + 0x1bd64 + struct.unpack('<i', word)[0]
        require(actual == BASE + target, 'action table target')
        result.append({'program_offset': hex(offset), 'bytes': raw, 'target': hex(actual)})
    for offset, target in [(0x148, 0xff9c), (0x1d8, 0xfc2c)]:
        word = data[offset:offset + 4]
        require(struct.unpack('<I', word)[0] == BASE + target, 'wrapper pointer')
        result.append({'data_offset': hex(offset), 'bytes': word.hex(),
                       'target': hex(BASE + target)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program', required=True, type=Path)
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--instructions', required=True, type=Path)
    parser.add_argument('--capstone-path', type=Path)
    args = parser.parse_args()
    if args.capstone_path:
        sys.path.insert(0, str(args.capstone_path))
    import capstone
    decoder = capstone.Cs(capstone.CS_ARCH_RISCV,
                          capstone.CS_MODE_RISCV32 | capstone.CS_MODE_RISCVC)
    program, data = args.program.read_bytes(), args.data.read_bytes()
    identity(program, data)
    table_result = tables(program, data)
    saved = json.loads(args.instructions.read_text())
    indexed = {row['address']: row for row in saved}
    require(len(indexed) == len(saved), 'duplicate saved instruction address')
    decoded, ranges = {}, []
    for start, end in RANGES:
        fresh = list(decoder.disasm(program[start:end], BASE + start))
        pc = BASE + start
        for instruction in fresh:
            require(instruction.address == pc and instruction.size in (2, 4), 'fresh decoder gap')
            row = indexed[pc]
            require(row['address'] == pc and row['size'] == instruction.size
                    and row['bytes'] == bytes(instruction.bytes).hex(), 'saved row byte/boundary mismatch')
            require(row['mnemonic'] == instruction.mnemonic and row['operands'] == instruction.op_str,
                    'saved/fresh semantic mismatch')
            decoded[pc - BASE] = instruction
            pc += instruction.size
        require(pc == BASE + end, 'incomplete fresh decode')
        ranges.append({'start': hex(BASE + start), 'end_exclusive': hex(BASE + end),
                       'instructions': len(fresh), 'sha256': sha(program[start:end])})
    anchors = []
    for offset, expected in ANCHORS.items():
        instruction = decoded[offset]
        require(instruction.mnemonic + ' ' + instruction.op_str == expected, 'anchor semantics')
        anchors.append([hex(BASE + offset), bytes(instruction.bytes).hex(), expected])
    addresses = []
    for high, low, expected in [
        (0xd80e, 0xd812, 0x3e9046e8), (0xd816, 0xd81a, 0x3e9046f7),
        (0xd820, 0xd824, 0x3e9046f6), (0xce10, 0xce14, 0x3e9046ec),
        (0xd0c0, 0xd0c4, 0x3e9046fa), (0xec74, 0xec78, 0x3e9046f9),
        (0xcf14, 0xcf18, 0x3e9046e8), (0xd14e, 0xd152, 0x3e9046f6),
        (0xeccc, 0xecd0, 0x3e9046f7), (0xe22e, 0xe232, 0x3e9046f5),
        (0xe236, 0xe23a, 0x3e9046ec), (0xe23e, 0xe242, 0x3e9046f0),
        (0xe246, 0xe24a, 0x3e9046f9), (0xe252, 0xe256, 0x3e9046f8),
        (0xe25a, 0xe25e, 0x3e9046fa), (0x9910, 0x991e, 0x1fb5080c),
        (0x9916, 0x991a, 0x3e9046c0), (0x9972, 0x9976, 0x1fb50fe4),
    ]:
        first, second = decoded[high], decoded[low]
        register, immediate = first.op_str.split(', ')
        require(first.mnemonic in ('auipc', 'lui'), 'unexpected address base')
        operands = second.op_str.split(', ')
        if second.mnemonic == 'addi':
            require(operands[:2] == [register, register], 'address add register')
            displacement = int(operands[2], 0)
        else:
            require(operands[-1].endswith('(' + register + ')'), 'address memory register')
            displacement = int(operands[-1].split('(')[0], 0)
        actual = ((first.address if first.mnemonic == 'auipc' else 0)
                  + (int(immediate, 0) << 12) + displacement) & 0xffffffff
        require(actual == expected, 'address calculation')
        addresses.append([hex(BASE + high), hex(BASE + low), hex(actual)])
    targets = []
    for offset, target in [(0xe0ae, 0x990e), (0xe0b2, 0x9960), (0xe0bc, 0xa3bc),
                           (0xfc3e, 0xe084), (0xffa8, 0xd7ca), (0xd7d2, 0xd80e),
                           (0xd172, 0xb0a6), (0x9928, 0x9940), (0x9932, 0x3712),
                           (0x993c, 0x9930), (0x997e, 0x9996), (0x9988, 0x99b0),
                           (0x9992, 0x4e1c), (0x999a, 0x3712), (0x99a6, 0x9996),
                           (0x99b2, 0x9976)]:
        instruction = decoded[offset]
        require(instruction.mnemonic in ('jal', 'j', 'c.j', 'beq', 'bne', 'c.beqz', 'c.bnez'),
                'unexpected control flow')
        actual = instruction.address + int(instruction.op_str.split(', ')[-1], 0)
        require(actual == BASE + target, 'relative control-flow target')
        targets.append([hex(BASE + offset), hex(actual)])
    unknown = []
    for offset in (0xb19a, 0xb3ba):
        word = program[offset:offset + 4]
        require(word.hex() == '738029fc', 'unknown word bytes')
        require(not list(decoder.disasm(word, BASE + offset)), 'unknown word unexpectedly decoded')
        # The old linear dump split this undecoded four-byte word into two rows.
        require(indexed[BASE + offset]['bytes'] == word[:2].hex(), 'unknown prefix row')
        require(indexed[BASE + offset + 2]['bytes'] == word[2:].hex(), 'unknown suffix row')
        unknown.append({'address': hex(BASE + offset), 'bytes': word.hex(),
                        'scope': 'TXdone callee reached via d172 -> b0a6; semantics unknown'})
    negative = []
    for name, check, reason in [
        ('changed_program', lambda: identity(bytes([program[0] ^ 1]) + program[1:], data), 'program identity'),
        ('changed_action_table', lambda: tables(program[:0x1bd74] + bytes([program[0x1bd74] ^ 1])
                                               + program[0x1bd75:], data), 'action table word'),
        ('changed_wrapper_pointer', lambda: tables(program, data[:0x148] + bytes([data[0x148] ^ 1])
                                                   + data[0x149:]), 'wrapper pointer'),
    ]:
        try:
            check()
        except ValueError as error:
            require(str(error) == reason, 'wrong negative-control rejection')
            negative.append({'case': name, 'rejected': reason})
        else:
            raise ValueError('negative control accepted: ' + name)
    print(json.dumps({
        'status': 'PASS', 'capstone_version': capstone.__version__,
        'program': {'size': len(program), 'sha256': sha(program)},
        'data': {'size': len(data), 'sha256': sha(data)},
        'tables': table_result, 'ranges': ranges, 'decoded_instruction_count': len(decoded),
        'anchors': anchors, 'computed_addresses': addresses,
        'computed_control_targets': targets,
        'undecoded_words': unknown, 'negative_controls': negative,
        'interpretation': {
            'get_ifindex3': 'word[0x3e9046e8] | !byte[0x3e9046f6] | !byte[0x3e9046f7]',
            'workers': 'cf18: status=0 when gate46ec=0; d152: ack46f6=1 when gate46fa=0; ecd0: ack46f7=1 when gate46f9!=3',
            'action6': '990e waits MMIO1fb5080c == RAM3e9046c0; 9960 waits low16(MMIO1fb50fe4)==0; then 4e1c P reset and a3bc T reset',
        },
        'limitations': [
            'No firmware execution, emulation, mutation, device access or timing test.',
            'Byte identity and selected standard instruction decoding are checked; full call graph and ownership are not proved.',
            'GET zero reports worker acknowledgements, not a global DMA-idle bit or DMA disable.',
            'Action6 has backward polling branches without local timeout; external callees and MMIO progress are not modeled.',
            'Successful action6 return supports completion of these checks/resets, not all NPU/WFDMA/RRO DMA quiescence.',
            'Unsupported SYSTEM/vendor words in TXdone are explicitly undecoded; the old split rows do not supply semantics.',
            'The two undecoded words are selected dependency boundaries, not an exhaustive unsupported-opcode inventory.',
            'IRQ activity, inter-hart memory ordering, pending descriptors and reset cancellation contracts remain unverified.',
            'Host mailbox timeout/EBUSY does not prove firmware cancellation; this checker does not validate host recovery code.',
            'No attribution of the observed Air stall; FDK reimplementation is not treated as this vendor firmware source.',
        ],
    }, indent=2))


if __name__ == '__main__':
    main()
