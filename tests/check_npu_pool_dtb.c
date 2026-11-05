/* Validate the compiled W1700K pool topology, not a text rendering of the DTS. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libfdt.h>

static uint64_t cells64(const fdt32_t *p)
{
	return ((uint64_t)fdt32_to_cpu(p[0]) << 32) | fdt32_to_cpu(p[1]);
}

static const fdt32_t *property(const void *fdt, int node, const char *name, int bytes)
{
	int len;
	const fdt32_t *p = fdt_getprop(fdt, node, name, &len);
	assert(p && len == bytes);
	return p;
}

int main(int argc, char **argv)
{
	assert(argc == 2);
	FILE *f = fopen(argv[1], "rb");
	assert(f && !fseek(f, 0, SEEK_END));
	long bytes = ftell(f);
	assert(bytes > 0 && !fseek(f, 0, SEEK_SET));
	void *dt = malloc((size_t)bytes);
	assert(dt && fread(dt, 1, (size_t)bytes, f) == (size_t)bytes);
	fclose(f);
	assert(!fdt_check_header(dt) && fdt_totalsize(dt) <= bytes);
	assert(!fdt_node_check_compatible(dt, 0, "gemtek,w1700k-ubi"));
	int pool = fdt_path_offset(dt, "/reserved-memory/dma-pool");
	assert(pool >= 0 && !fdt_node_check_compatible(dt, pool, "shared-dma-pool"));
	int len;
	assert(fdt_getprop(dt, pool, "no-map", &len) && len == 0);
	assert(cells64(property(dt, pool, "size", 8)) == 0x1000000);
	assert(cells64(property(dt, pool, "alignment", 8)) == 0x200000);
	const fdt32_t *range = property(dt, pool, "alloc-ranges", 16);
	assert(cells64(range) == 0x80000000 && cells64(range + 2) == 0x40000000);
	int npu = fdt_node_offset_by_compatible(dt, -1, "airoha,en7581-npu");
	assert(npu >= 0 && fdt_stringlist_search(dt, npu, "memory-region-names", "firmware") == 0);
	int index = fdt_stringlist_search(dt, npu, "memory-region-names", "dma");
	assert(index == 5);
	const fdt32_t *regions = property(dt, npu, "memory-region", 24);
	assert(fdt32_to_cpu(regions[index]) == fdt_get_phandle(dt, pool));
	int ramoops = fdt_path_offset(dt, "/reserved-memory/ramoops@86ff0000");
	assert(ramoops >= 0);
	const fdt32_t *reg = property(dt, ramoops, "reg", 16);
	assert(cells64(reg) == 0x86ff0000 && cells64(reg + 2) == 0x10000);
	free(dt);
	puts("NPU DTB pool: 16MiB, 2MiB aligned, reachable window, phandle and ramoops preserved");
	return 0;
}
