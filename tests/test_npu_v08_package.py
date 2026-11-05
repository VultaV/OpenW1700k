#!/usr/bin/env python3
"""Check stock v0.8 identities and actual loader copying without the old guard."""
import hashlib,pathlib,runpy,subprocess,sys,tempfile
root=pathlib.Path(__file__).resolve().parents[1]
h=runpy.run_path(str(root/'tests/test_airoha_npu_budget.py'))
files=root/'package/firmware/linux-firmware/files/airoha'
program=files/'en7581_MT7996_npu_rv32.bin';data=files/'en7581_MT7996_npu_data.bin'
assert hashlib.sha256(program.read_bytes()).hexdigest()=='7068a987bb95e89129a69de10d598f234a4400023eb23aacc8eb377e5f0fe0ea'
assert hashlib.sha256(data.read_bytes()).hexdigest()=='6fd9506e399ebb309801ac2ecc74d3e10fa66731afc828c76fde8a67b2153f49'
source=pathlib.Path(sys.argv[1]).read_text()
funcs='\n'.join(h['function'](source,n) for n in ['airoha_npu_load_firmware','airoha_npu_load_firmware_from_dts','airoha_npu_run_firmware','airoha_npu_rmem_release','airoha_npu_probe'])
prefix=h['PREFIX'].replace('@DUMMIES@','\n'.join(f'#define {n} dummy' for n in h['DUMMY_NAMES']))
prefix += r'''
static int of_property_match_string(void *node,const char *property,const char *name) { assert(!strcmp(property,"memory-region-names")&&!strcmp(name,"dma"));return -1; }
static int of_reserved_mem_device_init_by_name(struct device *d,void *node,const char *name) { abort(); }
static void of_reserved_mem_device_release(void *d) { abort(); }
static int devm_add_action_or_reset(struct device *d,void (*fn)(void *),void *arg) { abort(); }
'''
# Pool attachment has its own7-case production-source harness.
tests=h['TESTS'].split('int main(int argc,char **argv)',1)[0]+r'''
int main(int argc,char **argv) {
 assert(argc==3);
 u8 p[125832],d[3092],p_before[125832],d_before[3092];
 input(argv[1],p,sizeof(p));input(argv[2],d,sizeof(d));
 memcpy(p_before,p,sizeof(p));memcpy(d_before,d,sizeof(d));
 program_io=malloc(PCAP);data_io=malloc(DCAP);assert(program_io&&data_io);
 for(int i=0;i<2;i++) {
  reset();dt=!i;
  images[0]=(struct firmware){sizeof(p),p};images[1]=(struct firmware){sizeof(d),d};
  verify(0,false,2,3);
  assert(!memcmp(p,p_before,sizeof(p))&&!memcmp(d,d_before,sizeof(d)));
 }
 reset();free(program_io);free(data_io);
 puts("PASS: stock v0.8 hashes and 2 actual loader/probe cases; file bytes retained, old guard not applicable");
}
'''
with tempfile.TemporaryDirectory(prefix='npu-v08-') as t:
 p=pathlib.Path(t);(p/'check.c').write_text(prefix+funcs+tests)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-Wno-deprecated-declarations',str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check'),str(program),str(data)],check=True)
