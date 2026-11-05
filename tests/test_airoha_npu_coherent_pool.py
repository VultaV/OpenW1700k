#!/usr/bin/env python3
"""Exercise the actual optional-pool probe block and its release callback."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('source', type=Path)
a = p.parse_args()
s = a.source.read_text()
start = s.index('static void airoha_npu_rmem_release(')
release = s[start:s.index('\n}\n', start) + 3]
start = s.index('\tif (of_property_match_string(dev->of_node, "memory-region-names",\n\t\t\t\t     "dma") >= 0)')
end = s.index('\n\tfor (i = 0; i < ARRAY_SIZE(npu->cores); i++)', start)
block = s[start:end]
probe = s[s.index('static int airoha_npu_probe('):]
assert probe.index('dma_set_mask_and_coherent') < probe.index(block) < probe.index('dmam_alloc_coherent') < probe.index('airoha_npu_run_firmware')
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
struct device { void *of_node; };
static struct device device;
static int region, attach_error, action_error, attaches, actions, releases, allocs;
static bool attached;
static void (*cleanup)(void *);
static int of_property_match_string(void *node, const char *property, const char *name) {
 assert(node == &device && !strcmp(property, "memory-region-names") && !strcmp(name, "dma"));
 return region;
}
static int of_reserved_mem_device_init_by_name(struct device *dev, void *node, const char *name) {
 assert(dev == &device && node == dev->of_node && !strcmp(name, "dma"));
 attaches++; if (attach_error) return attach_error;
 attached = true; return 0;
}
static void of_reserved_mem_device_release(void *dev) {
 assert(dev == &device && attached); releases++; attached = false;
}
static int devm_add_action_or_reset(struct device *dev, void (*fn)(void *), void *data) {
 assert(dev == &device && data == dev && attached); actions++;
 if (action_error) { fn(data); return action_error; }
 cleanup = fn; return 0;
}
'''
code += release + '\nstatic int pool_phase(struct device *dev) {\n int err;\n' + block + r'''
 assert(region < 0 || attached); allocs++; return 0;
}
static int checks;
static void run(int index, int attach_ret, int action_ret, int expected) {
 region=index; attach_error=attach_ret; action_error=action_ret;
 attaches=actions=releases=allocs=0; attached=false; cleanup=NULL; device.of_node=&device;
 int ret=pool_phase(&device); assert(ret==expected);
 if(index<0) { assert(!attaches&&!actions&&!releases&&allocs==1&&!attached); }
 else if(attach_ret) { assert(attaches==1&&!actions&&!releases&&!allocs&&!attached); }
 else if(action_ret) { assert(attaches==1&&actions==1&&releases==1&&!allocs&&!attached); }
 else { assert(attaches==1&&actions==1&&!releases&&allocs==1&&attached&&cleanup);
        cleanup(&device); assert(releases==1&&!attached); }
 checks++;
}
int main(void) {
 run(-22,0,0,0); run(-2,0,0,0);
 run(0,0,0,0); run(5,0,0,0);
 run(5,-517,0,-517); run(5,-22,0,-22); run(5,0,-12,-12);
 printf("NPU coherent pool: %d cases passed, actual probe block/release, ASan/UBSan\n",checks);
}
'''
with tempfile.TemporaryDirectory(prefix='npu-coherent-pool-') as tmp:
 c = Path(tmp) / 'check.c'
 c.write_text(code)
 exe = c.with_suffix('')
 subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', str(c), '-o', str(exe)], check=True)
 subprocess.run([str(exe)], check=True)
