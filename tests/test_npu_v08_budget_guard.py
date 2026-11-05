"""Exact guarded NPU0.8 identity and bounded instruction checks; not firmware execution.

Before packaging, pass --program /path/to/private/candidate.bin. The default
requires the future guarded package; an unmodified vendor0.8 package must fail.
"""
from pathlib import Path
import argparse,ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1];BASE=0x84000000;ENTRY=0x8400a41e;BODY=0x8400a4a0;EXIT=0x8400a55e;END=0x8400a58e;SITE=0x8400a494;MASK=0xffffffff
NAMES='zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6'.split();REG={n:i for i,n in enumerate(NAMES)};SAVED=[REG[n] for n in ['ra','sp','gp','tp','s0','s1']+['s'+str(i) for i in range(2,12)]]
def require(x,message):
 if not x:raise ValueError(message)
# Reuse only generic instruction-step/memory semantics, excluding all historical identities and its old initializer.
old=(ROOT/'docs/npu-budget-guard-20260926/check_guard.py').read_text();tree=ast.parse(old);cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='State');cls.name='GenericState';cls.body=[n for n in cls.body if not isinstance(n,ast.FunctionDef) or n.name!='__init__']
for node in ast.walk(cls):
 if isinstance(node,ast.If) and isinstance(node.test,ast.Compare) and isinstance(node.test.left,ast.Name) and node.test.left.id=='op' and isinstance(node.test.comparators[0],ast.Constant) and node.test.comparators[0].value=='c.beqz':
  extra=ast.parse("if op == 'c.bnez':\n next_pc = self.pc + a[1] if r[a[0]] != 0 else next_pc").body[0];extra.orelse=node.orelse;node.orelse=[extra];break
else:raise AssertionError('Generic branch semantic insertion point missing')
ns={'MASK':MASK,'require':require};exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),'generic-rv32-semantics','exec'),ns)
class State(ns['GenericState']):
 def __init__(self,band,budget):
  self.regs=[(0xa5100101*(i+1)^budget)&MASK for i in range(32)];self.regs[0],self.regs[1],self.regs[2],self.regs[3]=0,0x12000000,0x20001000,0x20000000;self.regs[10],self.regs[11]=band,budget;self.initial=tuple(self.regs);self.pc=ENTRY;self.stack={};self.index_address=self.regs[3]+0x3dc+band*4;self.initial_index=(budget*17+band*3)%1024;table=(0x8400a430+(0xba8f8<<12)-0x500)&MASK;self.globals={self.index_address:self.initial_index,table+band*4:0x50000000+band*0x2000};self.external_writes=[];self.read_addresses=set()
# Extract only architecture-neutral branch helpers, excluding historical firmware constants.
branch_tree=ast.parse((ROOT/'docs/mlo-r36/check-tx-budget.py').read_text());branch_ns={}
exec(compile(ast.Module(body=[n for n in branch_tree.body if isinstance(n,ast.FunctionDef) and n.name in ['signed','branch_target']],type_ignores=[]),'generic-riscv-branch-immediates','exec'),branch_ns)
branch_decode=branch_ns['branch_target']

# Fixed instruction fixture: fresh Ghidra12.1.4 RISCV32 original/candidate decode.
# Exact hashes and byte correspondence gate it; this is not a general-purpose decoder.
ORIGINAL_ROWS = [
    (0x8400a41e, '13172500', 'slli', 'a4, a0, 0x2'),
    (0x8400a422, '9387c13d', 'addi', 'a5, gp, 0x3dc'),
    (0x8400a426, '5971', 'c.addi16sp', 'sp, -0x70'),
    (0x8400a428, 'ba97', 'c.add', 'a5, a4'),
    (0x8400a42a, '6ede', 'c.swsp', 's11, 0x3c, sp'),
    (0x8400a42c, '83ad0700', 'lw', 's11, 0x0, a5'),
    (0x8400a430, '97878fba', 'auipc', 'a5, 0xba8f8'),
    (0x8400a434, '938707b0', 'addi', 'a5, a5, -0x500'),
    (0x8400a438, 'ba97', 'c.add', 'a5, a4'),
    (0x8400a43a, '3acc', 'c.swsp', 'a4, 0x18, sp'),
    (0x8400a43c, '13070008', 'li', 'a4, 0x80'),
    (0x8400a440, 'd2cc', 'c.swsp', 's4, 0x58, sp'),
    (0x8400a442, '3ad6', 'c.swsp', 'a4, 0x2c, sp'),
    (0x8400a444, '86d6', 'c.swsp', 'ra, 0x6c, sp'),
    (0x8400a446, 'a2d4', 'c.swsp', 's0, 0x68, sp'),
    (0x8400a448, 'a6d2', 'c.swsp', 's1, 0x64, sp'),
    (0x8400a44a, 'cad0', 'c.swsp', 's2, 0x60, sp'),
    (0x8400a44c, 'cece', 'c.swsp', 's3, 0x5c, sp'),
    (0x8400a44e, 'd6ca', 'c.swsp', 's5, 0x54, sp'),
    (0x8400a450, 'dac8', 'c.swsp', 's6, 0x50, sp'),
    (0x8400a452, 'dec6', 'c.swsp', 's7, 0x4c, sp'),
    (0x8400a454, 'e2c4', 'c.swsp', 's8, 0x48, sp'),
    (0x8400a456, 'e6c2', 'c.swsp', 's9, 0x44, sp'),
    (0x8400a458, 'eac0', 'c.swsp', 's10, 0x40, sp'),
    (0x8400a45a, 'a3050102', 'sb', 'zero, 0x2b, sp'),
    (0x8400a45e, '1307f007', 'li', 'a4, 0x7f'),
    (0x8400a462, '03aa0700', 'lw', 's4, 0x0, a5'),
    (0x8400a466, '6363b700', 'bltu', 'a4, a1, 0x8400a46c'),
    (0x8400a46a, '2ed6', 'c.swsp', 'a1, 0x2c, sp'),
    (0x8400a46c, '137cf50f', 'andi', 's8, a0, 0xff'),
    (0x8400a470, 'b71bb51f', 'lui', 's7, 0x1fb51'),
    (0x8400a474, '93174c00', 'slli', 'a5, s8, 0x4'),
    (0x8400a478, '938b8b90', 'addi', 's7, s7, -0x6f8'),
    (0x8400a47c, '3ece', 'c.swsp', 'a5, 0x1c, sp'),
    (0x8400a47e, 'c16a', 'c.lui', 's5, 0x10'),
    (0x8400a480, 'de97', 'c.add', 'a5, s7'),
    (0x8400a482, '3eca', 'c.swsp', 'a5, 0x14, sp'),
    (0x8400a484, '370b0040', 'lui', 's6, 0x40000'),
    (0x8400a488, '8569', 'c.lui', 's3, 0x1'),
    (0x8400a48a, '9387faff', 'addi', 'a5, s5, -0x1'),
    (0x8400a48e, '02c8', 'c.swsp', 'zero, 0x10, sp'),
    (0x8400a490, '814b', 'c.li', 's7, 0x0'),
    (0x8400a492, '0149', 'c.li', 's2, 0x0'),
    (0x8400a494, '9374f50f', 'andi', 's1, a0, 0xff'),
    (0x8400a498, '7d1b', 'c.addi', 's6, -0x1'),
    (0x8400a49a, '93890980', 'addi', 's3, s3, -0x800'),
    (0x8400a49e, '3ec4', 'c.swsp', 'a5, 0x8, sp'),
    (0x8400a552, 'b257', 'c.lwsp', 'a5, 0x2c, sp'),
    (0x8400a554, 'fd17', 'c.addi', 'a5, -0x1'),
    (0x8400a556, '3ed6', 'c.swsp', 'a5, 0x2c, sp'),
    (0x8400a558, 'a1f7', 'c.bnez', 'a5, 0x8400a4a0'),
    (0x8400a55e, 'c24c', 'c.lwsp', 's9, 0x10, sp'),
    (0x8400a560, '6247', 'c.lwsp', 'a4, 0x18, sp'),
    (0x8400a562, 'b650', 'c.lwsp', 'ra, 0x6c, sp'),
    (0x8400a564, '2654', 'c.lwsp', 's0, 0x68, sp'),
    (0x8400a566, '9387c13d', 'addi', 'a5, gp, 0x3dc'),
    (0x8400a56a, '338de700', 'add', 's10, a5, a4'),
    (0x8400a56e, '2320bd01', 'sw', 's11, 0x0, s10'),
    (0x8400a572, '6685', 'c.mv', 'a0, s9'),
    (0x8400a574, '9654', 'c.lwsp', 's1, 0x64, sp'),
    (0x8400a576, '0659', 'c.lwsp', 's2, 0x60, sp'),
    (0x8400a578, 'f649', 'c.lwsp', 's3, 0x5c, sp'),
    (0x8400a57a, '664a', 'c.lwsp', 's4, 0x58, sp'),
    (0x8400a57c, 'd64a', 'c.lwsp', 's5, 0x54, sp'),
    (0x8400a57e, '464b', 'c.lwsp', 's6, 0x50, sp'),
    (0x8400a580, 'b64b', 'c.lwsp', 's7, 0x4c, sp'),
    (0x8400a582, '264c', 'c.lwsp', 's8, 0x48, sp'),
    (0x8400a584, '964c', 'c.lwsp', 's9, 0x44, sp'),
    (0x8400a586, '064d', 'c.lwsp', 's10, 0x40, sp'),
    (0x8400a588, 'f25d', 'c.lwsp', 's11, 0x3c, sp'),
    (0x8400a58a, '6561', 'c.addi16sp', 'sp, 0x70'),
    (0x8400a58c, '8280', 'ret', ''),
]
def decode(blob,guarded):
 rows=[{'address':a,'size':len(bytes.fromhex(raw)),'bytes':raw,'mnemonic':op,'operands':operands} for a,raw,op,operands in ORIGINAL_ROWS]
 indexed={r['address']:r for r in rows};program={}
 if guarded:
  indexed[SITE]={'address':SITE,'size':2,'bytes':'e284','mnemonic':'c.mv','operands':'s1, s8'}
  indexed[SITE+2]={'address':SITE+2,'size':2,'bytes':'e1c5','mnemonic':'c.beqz','operands':'a1, 0x8400a55e'}
  move=int.from_bytes(blob[SITE-BASE:SITE-BASE+2],'little')
  require(move&0xf003==0x8002 and (move>>7)&31==REG['s1'] and (move>>2)&31==REG['s8'],'Raw compressed move fields differ')
 for start,end in [(ENTRY,BODY),(EXIT,END),(0x8400a552,0x8400a55a)]:
  pc=start
  while pc<end:
   r=indexed[pc];size=int(r['size']);raw=bytes.fromhex(r['bytes']);require(size in [2,4] and raw==blob[pc-BASE:pc-BASE+size],'Actual listing byte mismatch');op=r['mnemonic'];o=r['operands'].split(', ') if r['operands'] else []
   if op=='li':op='addi';a=[REG[o[0]],0,int(o[1],0)]
   elif op in ['addi','slli','andi','add']:a=[REG[o[0]],REG[o[1]],REG[o[2]] if op=='add' else int(o[2],0)]
   elif op in ['auipc','lui','c.lui','c.li','c.addi','c.addi16sp']:a=[REG[o[0]],int(o[1],0)]
   elif op in ['c.add','c.mv']:a=[REG[o[0]],REG[o[1]]]
   elif op in ['lw','sw','sb','c.lwsp','c.swsp']:a=[REG[o[0]],REG[o[2]],int(o[1],0)]
   elif op=='bltu':target,kind=branch_decode(pc,raw);require(target==int(o[2],0),'Branch target differs');a=[REG[o[0]],REG[o[1]],target-pc]
   elif op in ['c.beqz','c.bnez']:target,kind=branch_decode(pc,raw);require(target==int(o[1],0),'Compressed branch target differs');a=[REG[o[0]],target-pc]
   elif op=='ret':op='c.jr';a=[REG['ra']]
   else:raise ValueError('Unsupported bounded opcode '+op+' at '+hex(pc))
   program[pc]=(size,op,a);pc+=size
  require(pc==end,'Region not an exact instruction boundary')
 return program
ORIGINAL_SHA='7068a987bb95e89129a69de10d598f234a4400023eb23aacc8eb377e5f0fe0ea'
CANDIDATE_SHA='b821c8f3ac47624a93c833070405ea19c19bcd89ffa7bf57c735550120044e0e'
DATA_SHA='6fd9506e399ebb309801ac2ecc74d3e10fa66731afc828c76fde8a67b2153f49'

def identity(program,data):
 require(len(program)==125832 and hashlib.sha256(program).hexdigest()==CANDIDATE_SHA,'Expected exact guarded0.8 candidate; unmodified vendor0.8 is not this test target')
 require(program[SITE-BASE:SITE-BASE+4]==bytes.fromhex('e284e1c5'),'Wrong0.8 guard bytes')
 original=program[:SITE-BASE]+bytes.fromhex('9374f50f')+program[SITE-BASE+4:]
 require(hashlib.sha256(original).hexdigest()==ORIGINAL_SHA,'Reversed four-byte vendor identity differs')
 require(len(data)==3092 and hashlib.sha256(data).hexdigest()==DATA_SHA,'Expected unchanged exact0.8 data image')
 require([i for i,(a,b) in enumerate(zip(original,program)) if a!=b]==list(range(SITE-BASE,SITE-BASE+4)),'Program changes extend beyond exactly four bytes')
 return original

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--program',type=Path,default=ROOT/'package/firmware/linux-firmware/files/airoha/en7581_MT7996_npu_rv32.bin')
parser.add_argument('--data',type=Path,default=ROOT/'package/firmware/linux-firmware/files/airoha/en7581_MT7996_npu_data.bin')
args=parser.parse_args();candidate=args.program.read_bytes();data=args.data.read_bytes();original=identity(candidate,data)
op=decode(original,False);cp=decode(candidate,True)
require(cp[SITE]==(2,'c.mv',[REG['s1'],REG['s8']]) and cp[SITE+2]==(2,'c.beqz',[REG['a1'],EXIT-SITE-2]),'Candidate decode differs')
budgets=list(range(256))+[256,257,65535,65536,65537,0x7fffffff,0x80000000,0xfffffffe,0xffffffff];positive=zero=decrements=0;rows=[]
for band in [0,1,2]:
 for budget in budgets:
  before=State(band,budget);after=State(band,budget);before.run(op,BODY)
  effective=min(budget,128)
  require(before.load(before.regs[2]+0x2c)==effective,'Original budget selection differs')
  if budget:
   after.run(cp,BODY);after.load(after.regs[2]+0x2c);require(before.snapshot()==after.snapshot(),'Nonzero prefix semantics differ');positive+=1
  else:
   after.run(cp,after.initial[REG['ra']]);require(after.regs[REG['a0']]==0,'Guard return is not zero');require(all(after.regs[i]==after.initial[i] for i in SAVED),'Callee-saved register/frame not restored');require(after.external_writes==[(0x8400a56e,after.index_address,after.initial_index)],'Unexpected external write');require(after.globals[after.index_address]==after.initial_index,'Cached consumer changed');zero+=1
  # Execute only the actual success budget-decrement block, not packet/allocator/MMIO code.
  before.pc=0x8400a552;expected=(effective-1)&MASK;target=BODY if expected else 0x8400a55a;before.run(op,target);require(before.load(before.regs[2]+0x2c)==expected,'Decrement or backedge differs');decrements+=1
  if budget in [0,1,127,128,129,0xffffffff]:rows.append({'band':band,'input_budget':budget,'effective_budget':effective,'original_after_one_success':expected,'original_success_backedge':target==BODY,'guarded_zero_returns_before_body':budget==0})
# Negative controls verify both trust boundaries and fixed-region mismatch detection.
rejected=[]
for mode in ['wrong_program_identity','wrong_data_identity','original_is_not_candidate','wrong_region_byte','wrong_instruction_fixture']:
 try:
  if mode=='wrong_program_identity':b=bytearray(candidate);b[0]^=1;identity(bytes(b),data)
  elif mode=='wrong_data_identity':b=bytearray(data);b[0]^=1;identity(candidate,bytes(b))
  elif mode=='original_is_not_candidate':identity(original,data)
  elif mode=='wrong_region_byte':b=bytearray(candidate);b[SITE-BASE]^=1;decode(bytes(b),True)
  else:decode(original,True)
 except (ValueError,AssertionError):rejected.append(mode)
require(len(rejected)==5,'A negative control was not rejected')
require(args.program.read_bytes()==candidate and args.data.read_bytes()==data,'Input files changed during read-only test')
result={'status':'PASS_BOUNDED_INSTRUCTION_EQUIVALENCE','source_program_sha256':hashlib.sha256(original).hexdigest(),'candidate_program_sha256':hashlib.sha256(candidate).hexdigest(),'data_sha256_unchanged':hashlib.sha256(data).hexdigest(),'bands':[0,1,2],'budgets_per_band':len(budgets),'positive_prefix_states_identical':positive,'zero_prefix_epilogue_states_passed':zero,'actual_success_decrement_blocks_checked':decrements,'selected_cases':rows,'negative_controls_rejected':rejected,'generic_semantics_reused':'Old checker State.load/store/run/snapshot only; all old initializer, identities and offsets excluded','instruction_fixture_provenance':'Ghidra12.1.4 original/candidate decode at fixture generation; fixed fixture replay plus independent raw branch checks','input_program_and_data_unchanged':True,'limits':['Only fixed prefix/epilogue/decrement code runs in a scalar host model. Packet/allocator/DMA/MMIO/IRQ/reset/other-hart behavior is not emulated.','No actual firmware execution, boot, throughput or causal stall result is established.', 'Original vendor zero-means-unlimited API intent and concurrent cached-consumer reset writers are unknown.']}
print(json.dumps({k:v for k,v in result.items() if k!='selected_cases'},indent=2))
