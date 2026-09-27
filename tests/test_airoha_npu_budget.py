#!/usr/bin/env python3
"""Compile actual loader/probe functions with fake I/O and real host SHA-256.

Explicit input/output paths; current host support is macOS with CommonCrypto.
Offline only: no firmware execution, devices, privileged operations or product
builds. CommonCrypto supplies host SHA-256; kernel crypto code is not tested.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import tempfile

EXTRACTOR = Path(__file__).resolve().with_name('test_airoha_ppe_ownership.py')
function = runpy.run_path(str(EXTRACTOR))['function']
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

PREFIX = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <CommonCrypto/CommonDigest.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define __iomem
#define SHA256_DIGEST_SIZE 32
#define sha256_ctx CC_SHA256state_st
static void sha256_init(struct sha256_ctx *c) { assert(CC_SHA256_Init(c)); }
static void sha256_update(struct sha256_ctx *c,const u8 *p,size_t n) { assert(n<=UINT32_MAX); assert(CC_SHA256_Update(c,p,n)); }
static void sha256_final(struct sha256_ctx *c,u8 *p) { assert(CC_SHA256_Final(p,c)); }
static void sha256(const u8 *p,size_t n,u8 *out) { assert(n<=UINT32_MAX); assert(CC_SHA256(p,n,out)==out); }
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define EPROBE_DEFER 517
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define GFP_KERNEL 0
#define IRQF_SHARED 0
#define DMA_BIT_MASK(n) ((1ULL<<(n))-1)
#define NPU_NUM_CORES 8
#define NPU_NUM_IRQ 6
#define AIROHA_NPU_MBOX_SIZE 256
#define NPU_EN7581_FIRMWARE_RV32_MAX_SIZE 0x200000
#define NPU_EN7581_FIRMWARE_DATA_MAX_SIZE 0x10000
#define REG_NPU_LOCAL_SRAM 0
#define REG_CR_NPU_MIB(n) (0x30c140+(n)*4)
#define REG_CR_BOOT_BASE(n) (0x306020+(n)*4)
#define REG_CR_BOOT_CONFIG 0x306004
#define REG_CR_BOOT_TRIGGER 0x306000
#define WLAN_FUNC_GET_WAIT_NPU_VERSION 0
struct device { void *of_node; };
struct platform_device { struct device dev; };
struct resource { uintptr_t start; };
struct firmware { size_t size; const u8 *data; };
struct airoha_npu_fw { const char *name; int max_size; };
struct airoha_npu_soc_data { struct airoha_npu_fw fw_rv32,fw_data; };
struct airoha_npu {
 struct device *dev; void *regmap;
 struct airoha_npu_core { struct airoha_npu *npu; int lock,wdt_work; void *buf; uintptr_t addr; } cores[NPU_NUM_CORES];
 int irqs[NPU_NUM_IRQ];
 struct { void *ppe_init,*ppe_deinit,*ppe_init_stats,*ppe_flush_sram_entries,*ppe_foe_commit_entry;
 void *wlan_init_reserved_memory,*wlan_send_msg,*wlan_get_msg,*wlan_get_queue_addr;
 void *wlan_set_irq_status,*wlan_get_irq_status,*wlan_enable_irq,*wlan_disable_irq; } ops;
};
static int regmap_config;
static void dummy(void) {}
@DUMMIES@
enum { PSIZE=122336, DSIZE=3084, OFFSET=0x9e1a, PCAP=0x200000, DCAP=0x10000 };
static u8 original_program[PSIZE],original_data[DSIZE],program[PSIZE],data[DSIZE];
static u8 *program_io,*data_io;
static struct firmware images[2];
static struct airoha_npu_soc_data soc;
static const char *dt_names[2];
static int requests,released,copies,patches,reads,barriers,register_writes,triggers,bases,configured,bound;
static int request_error[2],dt_count,map_error,corrupt_offset,match_missing,version_error;
static int applied_message,skipped_message; static bool dt;
static void *allocs[32]; static int allocated;
static void *allocate(size_t n) { void *p=calloc(1,n);assert(p);allocs[allocated++]=p;return p; }
static void *devm_kzalloc(struct device *d,size_t n,int f) { return allocate(n); }
static void *devm_platform_ioremap_resource(struct platform_device *p,int i) { assert(i==0);return data_io; }
static void *devm_regmap_init_mmio(struct device *d,void *b,const void *c) { return (void *)1; }
static int of_reserved_mem_region_to_resource(void *node,int i,struct resource *r) { r->start=0x84000000;return 0; }
static int platform_get_irq(struct platform_device *p,int i) { return i+1; }
static int devm_request_irq(struct device *d,int irq,void *fn,int flags,const char *name,void *arg) { return 0; }
static int devm_work_autocancel(struct device *d,int *work,void *fn) { return 0; }
static void spin_lock_init(int *p) {}
static int dma_set_coherent_mask(struct device *d,uint64_t mask) { return 0; }
static void *dmam_alloc_coherent(struct device *d,size_t n,uintptr_t *a,int f) { *a=1;return allocate(n); }
static void *of_device_get_match_data(struct device *d) { return match_missing ? NULL:&soc; }
static void *devm_ioremap_resource(struct device *d,struct resource *r) { return map_error?ERR_PTR(map_error):program_io; }
static void *of_find_property(void *node,const char *name,void *len) { return dt?(void *)1:NULL; }
static int of_property_read_string_array(void *node,const char *prop,const char **out,int n) {
 assert(n==2);out[0]=dt_names[0];out[1]=dt_names[1];return dt_count;
}
static int dev_err_probe(struct device *d,int error,const char *format,...) { return error; }
static void dev_err(struct device *d,const char *format,...) {}
static void dev_info(struct device *d,const char *format,...) {
 if (!strcmp(format,"NPU TX budget guard %s\n")) {
  va_list ap;va_start(ap,format);const char *s=va_arg(ap,const char *);
  if (!strcmp(s,"applied")) applied_message++; else { assert(!strcmp(s,"not applicable"));skipped_message++; }
  va_end(ap);
 }
}
static int request_firmware_direct(const struct firmware **fw,const char *name,struct device *d) {
 int role=!strcmp(name,soc.fw_rv32.name)?0:!strcmp(name,soc.fw_data.name)?1:-1;
 assert(role>=0);requests++;
 if(request_error[role]) { *fw=NULL;return request_error[role]; }
 *fw=&images[role];return 0;
}
static void release_firmware(const struct firmware *fw) {
 if(!fw)return;int role=fw==&images[0]?0:fw==&images[1]?1:-1;
 assert(role>=0 && !(released&(1<<role)));released|=1<<role;
}
static void memcpy_toio(void *dest,const void *src,size_t n) {
 uintptr_t at=(uintptr_t)dest,p=(uintptr_t)program_io,d=(uintptr_t)data_io;
 assert((at>=p && at-p<=PCAP && n<=PCAP-(at-p)) || (at>=d && at-d<=DCAP && n<=DCAP-(at-d)));
 copies++;memcpy(dest,src,n);
 if(at==p+OFFSET) {
  assert(n==4 && (at-p)%4==2);patches++;
  if(corrupt_offset>=0) program_io[corrupt_offset]^=1;
 }
}
static void wmb(void) { barriers++; }
static void memcpy_fromio(void *dest,const void *src,size_t n) {
 uintptr_t at=(uintptr_t)src,p=(uintptr_t)program_io;
 assert(barriers==1 && at>=p && n<=PSIZE-(at-p));reads++;memcpy(dest,src,n);
}
static int regmap_write(void *map,unsigned reg,unsigned value) {
 assert(released==3);register_writes++;
 if(reg==REG_CR_BOOT_TRIGGER) { assert(value==1 && bases==8 && configured==1);triggers++; }
 if(reg==REG_CR_BOOT_CONFIG) { assert(value==0xff);configured++; }
 if(reg>=REG_CR_BOOT_BASE(0) && reg<=REG_CR_BOOT_BASE(7)) { assert(value==0x84000000);bases++; }
 return 0;
}
static void msleep(int ms) {}
static void usleep_range(int a,int b) {}
static int airoha_npu_wlan_msg_get(struct airoha_npu *n,int a,int cmd,void *out,int size,int flags) {
 assert(triggers==1);*(u32 *)out=1;return version_error;
}
static void platform_set_drvdata(struct platform_device *p,struct airoha_npu *n) { assert(triggers==1);bound++; }
'''

TESTS = r'''
static void reset(void) {
 for(int i=0;i<allocated;i++)free(allocs[i]);allocated=0;
 memcpy(program,original_program,PSIZE);memcpy(data,original_data,DSIZE);
 memset(program_io,0xa5,PCAP);memset(data_io,0xa5,DCAP);
 images[0]=(struct firmware){PSIZE,program};images[1]=(struct firmware){DSIZE,data};
 soc=(struct airoha_npu_soc_data){{"program",PCAP},{"data",DCAP}};
 dt_names[0]=soc.fw_rv32.name;dt_names[1]=soc.fw_data.name;dt_count=2;dt=true;
 requests=released=copies=patches=reads=barriers=register_writes=triggers=bases=configured=bound=0;
 request_error[0]=request_error[1]=map_error=match_missing=version_error=0;corrupt_offset=-1;
 applied_message=skipped_message=0;
}
static void verify(int result,bool guarded,int copies_expected,int released_expected) {
 u8 program_before[PSIZE],data_before[DSIZE];
 memcpy(program_before,program,PSIZE);memcpy(data_before,data,DSIZE);
 struct platform_device p={};int got=airoha_npu_probe(&p);assert(got==result);
 assert(!memcmp(program_before,program,PSIZE) && !memcmp(data_before,data,DSIZE));
 assert(copies==copies_expected && released==released_expected);
 if(result) { assert(!triggers && !register_writes && !bound && !applied_message && !skipped_message);return; }
 assert(triggers==1 && configured==1 && bases==8 && bound==1);
 const struct firmware *pf=dt && dt_names[0]==soc.fw_data.name?&images[1]:&images[0];
 const struct firmware *df=dt && dt_names[1]==soc.fw_rv32.name?&images[0]:&images[1];
 assert(!memcmp(data_io,df->data,df->size));
 if(guarded) {
  static const u8 patch[]={0xe2,0x84,0xe1,0xc5};
  assert(patches==1 && reads==(PSIZE+255)/256 && barriers==1 && applied_message==1 && skipped_message==0);
  assert(!memcmp(program_io,pf->data,OFFSET) && !memcmp(program_io+OFFSET,patch,4));
  assert(!memcmp(program_io+OFFSET+4,pf->data+OFFSET+4,pf->size-OFFSET-4));
 } else {
  assert(!patches && !reads && !barriers && !applied_message && skipped_message==1);
  assert(!memcmp(program_io,pf->data,pf->size));
 }
 for(size_t i=pf->size;i<PCAP;i++)assert(program_io[i]==0xa5);
 for(size_t i=df->size;i<DCAP;i++)assert(data_io[i]==0xa5);
}
static void input(const char *name,u8 *out,size_t n) {
 FILE *f=fopen(name,"rb");assert(f);assert(fread(out,1,n,f)==n && fgetc(f)==EOF);fclose(f);
}
int main(int argc,char **argv) {
 assert(argc==3);input(argv[1],original_program,PSIZE);input(argv[2],original_data,DSIZE);
 program_io=malloc(PCAP);data_io=malloc(DCAP);assert(program_io && data_io);
 #ifdef BASELINE
 reset();struct platform_device p={};assert(airoha_npu_probe(&p)==0);
 assert(triggers==1 && copies==2 && !patches && !reads && !barriers && released==3);
 assert(!memcmp(program_io,original_program,PSIZE) && !memcmp(data_io,original_data,DSIZE));
 assert(!memcmp(program,original_program,PSIZE) && !memcmp(data,original_data,DSIZE));
 reset();free(program_io);free(data_io);
 puts("PASS: baseline control loads the exact original program unguarded and reaches boot (1 expected baseline case)");return 0;
 #endif
 int cases=0;
 #define CHECK(error,guard,copies,release) do { verify(error,guard,copies,release);cases++; } while(0)
 reset();CHECK(0,true,3,3); /* actual pair through DT */
 reset();dt=false;CHECK(0,true,3,3); /* same actual pair through default */
 reset();soc.fw_rv32.name="renamed-program";soc.fw_data.name="renamed-data";
 dt_names[0]=soc.fw_rv32.name;dt_names[1]=soc.fw_data.name;CHECK(0,true,3,3);
 reset();program[17]^=1;CHECK(0,false,2,3); /* whole program hash */
 reset();data[31]^=1;CHECK(0,false,2,3); /* whole paired data hash */
 reset();program[OFFSET]^=1;CHECK(0,false,2,3); /* wrong old instruction */
 reset();images[0].size=1;CHECK(0,false,2,3); /* cannot read guard offset */
 reset();images[1].size=1;CHECK(0,false,2,3);
 reset();images[0].size=PSIZE-1;CHECK(0,false,2,3);
 reset();images[1].size=DSIZE-1;CHECK(0,false,2,3);
 reset();dt_names[0]=soc.fw_data.name;dt_names[1]=soc.fw_rv32.name;CHECK(-E2BIG,false,0,3); /* role swapped: data max */
 reset();request_error[0]=-ENOENT;CHECK(-EPROBE_DEFER,false,0,0);
 reset();request_error[0]=-EIO;CHECK(-EIO,false,0,0);
 reset();request_error[1]=-ENOENT;CHECK(-EPROBE_DEFER,false,0,1);
 reset();request_error[1]=-EIO;CHECK(-EIO,false,0,1);
 reset();images[0].size=PCAP+1;CHECK(-E2BIG,false,0,1);
 reset();images[1].size=DCAP+1;CHECK(-E2BIG,false,0,3);
 reset();dt_count=1;CHECK(-EINVAL,false,0,0);
 reset();match_missing=1;CHECK(-EINVAL,false,0,0);
 reset();map_error=-ENOMEM;CHECK(-ENOMEM,false,0,0);
 reset();corrupt_offset=OFFSET;CHECK(-EIO,true,3,3);assert(patches==1 && reads==(PSIZE+255)/256);
 reset();corrupt_offset=0;CHECK(-EIO,true,3,3);assert(patches==1 && reads==(PSIZE+255)/256);
 reset();corrupt_offset=PSIZE-1;CHECK(-EIO,true,3,3);assert(patches==1 && reads==(PSIZE+255)/256);
 reset();version_error=-EIO;CHECK(0,true,3,3); /* inherited probe does not enforce version response */
 reset();for(int i=0;i<allocated;i++)free(allocs[i]);free(program_io);free(data_io);
 printf("PASS: %d actual loader/probe cases; exact pair, unknown unchanged, source immutable, role/size/error, full readback and pre-boot failure boundaries\n",cases);
 return 0;
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--baseline',action='store_true',help='Verify one exact unguarded baseline outcome; use --source before/airoha_npu.c')
    p.add_argument('--program',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    assert sha(args.program)=='e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643'
    assert sha(args.data)=='61a75afb052feed2ceb2f3023e16f50317c05c78f9c8e564bf01924ce39c7ec1'
    source=args.source.read_text()
    names=['airoha_npu_load_firmware','airoha_npu_load_firmware_from_dts','airoha_npu_run_firmware','airoha_npu_probe']
    funcs='\n'.join(function(source,n) for n in names)
    dummy_names=['airoha_npu_ppe_init','airoha_npu_ppe_deinit','airoha_npu_ppe_stats_setup','airoha_npu_ppe_flush_sram_entries',
        'airoha_npu_foe_commit_entry','airoha_npu_wlan_init_memory','airoha_npu_wlan_msg_send','airoha_npu_wlan_queue_addr_get',
        'airoha_npu_wlan_irq_status_set','airoha_npu_wlan_irq_status_get','airoha_npu_wlan_irq_enable','airoha_npu_wlan_irq_disable',
        'airoha_npu_mbox_handler','airoha_npu_wdt_work','airoha_npu_wdt_handler']
    prefix=PREFIX.replace('@DUMMIES@','\n'.join(f'#define {n} dummy' for n in dummy_names))
    with tempfile.TemporaryDirectory(prefix='npu-loader-host-') as tmp:
        c=Path(tmp)/'check.c';exe=Path(tmp)/'check';c.write_text(prefix+funcs+TESTS)
        command=['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-Werror',
                 '-Wno-deprecated-declarations',str(c),'-o',str(exe)]
        if args.baseline: command.insert(1,'-DBASELINE')
        label='baseline-' if args.baseline else ''
        build=subprocess.run(command,text=True,capture_output=True)
        (args.output_dir/(label+'compile.log')).write_text(build.stdout+build.stderr)
        assert build.returncode==0,build.stderr
        run=subprocess.run([str(exe),str(args.program),str(args.data)],text=True,capture_output=True)
        (args.output_dir/(label+'host-tests.log')).write_text(run.stdout+run.stderr)
        assert run.returncode==0,run.stdout+run.stderr
    result=dict(status='BASELINE_UNGUARDED_OUTCOME_VERIFIED' if args.baseline else 'HOST_LOADER_PROBE_FIXTURE_PASS',cases=1 if args.baseline else 24,
        source_functions=names,compiler_flags=command[1:command.index(str(c))],
        input_sha256={n:sha(path) for n,path in [('candidate_source',args.source),('original_program',args.program),('original_data',args.data),('extractor',EXTRACTOR),('checker',Path(__file__))]},
        limits=['Actual loader, DT/default dispatch and probe C bodies are extracted; request/IO/register/IRQ/allocation services are fixtures, not hardware.',
                'Host CommonCrypto computes the actual SHA-256. This is not a test of kernel SHA implementation, bus visibility, NPU instruction execution or cold-boot/reset behavior.',
                'Version mailbox failure still returns successful probe in inherited code; a bound driver is not firmware boot validation.',
                'Unknown pairs load unchanged; firmware files and source buffers are not patched. This does not identify the cause of Mac/Air throughput or sleep/wake symptoms.'])
    (args.output_dir/(label+'HOST_TESTS.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(run.stdout,end='')


if __name__=='__main__':main()
