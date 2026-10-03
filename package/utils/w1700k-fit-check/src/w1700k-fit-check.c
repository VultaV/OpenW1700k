// SPDX-License-Identifier: GPL-2.0-only
/* W1700K UBI2 sysupgrade layout validation. Hashes are checked by fit_check_sign. */
#include <libfdt.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

static void reject(const char *why)
{
	fprintf(stderr, "W1700K FIT rejected: %s\n", why);
	exit(74);
}

static const char *string(const void *fdt, int node, const char *name)
{
	int len;
	const char *s = fdt_getprop(fdt, node, name, &len);
	if (!s || len < 2 || s[len - 1] || memchr(s, 0, len - 1))
		reject(name);
	return s;
}

static uint32_t cell(const void *fdt, int node, const char *name)
{
	int len;
	const fdt32_t *p = fdt_getprop(fdt, node, name, &len);
	if (!p || len != 4)
		reject(name);
	return fdt32_to_cpu(*p);
}

static void equals(const void *fdt, int node, const char *name, const char *value)
{
	if (strcmp(string(fdt, node, name), value))
		reject(name);
}

static void partition(const void *fdt, int node, uint32_t start, uint32_t size)
{
	int len;
	const fdt32_t *p = fdt_getprop(fdt, node, "reg", &len);
	if (!p || len != 8 || fdt32_to_cpu(p[0]) != start || fdt32_to_cpu(p[1]) != size)
		reject("UBI2 partition map");
	int parent = fdt_parent_offset(fdt, node);
	if (cell(fdt, parent, "#address-cells") != 1 || cell(fdt, parent, "#size-cells") != 1)
		reject("partition address cells");
}

static int label(const void *fdt, const char *name)
{
	int node = fdt_node_offset_by_prop_value(fdt, -1, "label", name, strlen(name) + 1);
	if (node < 0 || fdt_node_offset_by_prop_value(fdt, node, "label", name, strlen(name) + 1) >= 0)
		reject("missing or duplicate partition");
	return node;
}

static void active_path(const void *fdt, int node)
{
	for (; node >= 0; node = fdt_parent_offset(fdt, node)) {
		if (fdt_getprop(fdt, node, "status", NULL)) {
			const char *status = string(fdt, node, "status");
			if (strcmp(status, "okay") && strcmp(status, "ok"))
				reject("inactive flash path");
		}
	}
}

static void board_layout(const void *fdt, size_t size)
{
	if (fdt_check_full(fdt, size) || fdt_node_check_compatible(fdt, 0, "gemtek,w1700k-ubi"))
		reject("W1700K device tree");
	int ubi = label(fdt, "ubi"), bmt = label(fdt, "reserved_bmt");
	partition(fdt, ubi, 0x00700000, 0x1b700000);
	partition(fdt, bmt, 0x1be00000, 0x04200000);
	if (fdt_parent_offset(fdt, ubi) != fdt_parent_offset(fdt, bmt))
		reject("partition parent");
	int partitions = fdt_parent_offset(fdt, ubi);
	int nand = fdt_parent_offset(fdt, partitions);
	int controller = fdt_parent_offset(fdt, nand);
	if (fdt_node_check_compatible(fdt, partitions, "fixed-partitions") ||
	    fdt_node_check_compatible(fdt, nand, "spi-nand") ||
	    fdt_node_check_compatible(fdt, controller, "airoha,en7581-snand") ||
	    fdt_node_check_compatible(fdt, ubi, "linux,ubi") ||
	    cell(fdt, nand, "reg") != 0)
		reject("NAND partition path");
	if (fdt_node_offset_by_compatible(fdt, -1, "airoha,en7581-snand") != controller ||
	    fdt_node_offset_by_compatible(fdt, controller, "airoha,en7581-snand") >= 0)
		reject("ambiguous NAND controller");
	int len, bus = fdt_parent_offset(fdt, controller);
	const fdt32_t *reg = fdt_getprop(fdt, controller, "reg", &len);
	const uint32_t expected[] = {0, 0x1fa10000, 0, 0x140, 0, 0x1fa11000, 0, 0x160};
	if (!reg || len != (int)sizeof(expected) || cell(fdt, bus, "#address-cells") != 2 ||
	    cell(fdt, bus, "#size-cells") != 2)
		reject("NAND controller address");
	for (unsigned i = 0; i < sizeof(expected) / sizeof(expected[0]); i++)
		if (fdt32_to_cpu(reg[i]) != expected[i]) reject("NAND controller address");
	active_path(fdt, ubi);
	int chosen = fdt_path_offset(fdt, "/chosen");
	int root = fdt_node_offset_by_phandle(fdt, cell(fdt, chosen, "rootdisk"));
	if (root < 0 || fdt_parent_offset(fdt, fdt_parent_offset(fdt, root)) != ubi)
		reject("rootdisk volume");
	equals(fdt, root, "volname", "fit");
}

int main(int argc, char **argv)
{
	struct stat st;
	if (argc != 2) reject("expected one image path");
	int fd = open(argv[1], O_RDONLY);
	if (fd < 0 || fstat(fd, &st) || !S_ISREG(st.st_mode) ||
	    st.st_size < (off_t)sizeof(struct fdt_header) || st.st_size > 0x1b700000)
		reject("image size or file type");
	size_t size = st.st_size;
	const unsigned char *fdt = mmap(NULL, size, PROT_READ, MAP_PRIVATE, fd, 0);
	if (fdt == MAP_FAILED || fdt_check_full(fdt, size)) reject("FIT structure");
	int configs = fdt_path_offset(fdt, "/configurations");
	int config = fdt_subnode_offset(fdt, configs, string(fdt, configs, "default"));
	if (config < 0 || fdt_first_subnode(fdt, configs) != config || fdt_next_subnode(fdt, config) != -FDT_ERR_NOTFOUND)
		reject("one default configuration required");
	if (fdt_getprop(fdt, config, "ramdisk", NULL)) reject("recovery image is not sysupgrade");
	int images = fdt_path_offset(fdt, "/images");
	const char *refs[] = {"kernel", "fdt", "loadables"};
	const char *types[] = {"kernel", "flat_dt", "filesystem"};
	uint64_t start[3], end[3];
	for (unsigned i = 0; i < 3; i++) {
		int node = fdt_subnode_offset(fdt, images, string(fdt, config, refs[i]));
		if (node < 0) reject("missing referenced image");
		equals(fdt, node, "type", types[i]);
		equals(fdt, node, "arch", "arm64");
		equals(fdt, node, "compression", i == 0 ? "gzip" : "none");
		if (!i) equals(fdt, node, "os", "linux");
		/* This board's external-static recipe uses absolute positions. */
		if (fdt_getprop(fdt, node, "data", NULL) || fdt_getprop(fdt, node, "data-offset", NULL))
			reject("external static payload required");
		start[i] = cell(fdt, node, "data-position");
		uint64_t len = cell(fdt, node, "data-size");
		end[i] = start[i] + len;
		if (!len || start[i] < fdt_totalsize(fdt) || end[i] > size)
			reject("payload outside image");
		if (i == 2 && ((start[i] | len) & 4095)) reject("rootfs alignment");
		for (unsigned j = 0; j < i; j++)
			if (start[i] < end[j] && start[j] < end[i]) reject("overlapping payloads");
	}
	/* The real DTB is ~23 KiB; do not copy an arbitrarily large blob. */
	if (end[1] - start[1] > 0x100000) reject("device tree size");
	/* FDT data may start unaligned; libfdt requires an aligned buffer. */
	void *dtb = malloc(end[1] - start[1]);
	if (!dtb) reject("device tree allocation");
	memcpy(dtb, fdt + start[1], end[1] - start[1]);
	board_layout(dtb, end[1] - start[1]);
	free(dtb);
	if (end[2] - start[2] < 4 || memcmp(fdt + start[2], "hsqs", 4)) reject("squashfs rootfs");
	munmap((void *)fdt, size);
	close(fd);
	return 0;
}
