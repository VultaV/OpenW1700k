
build-volume/source/build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mt76-2026.09.01~01367e60/npu.o:     file format elf64-littleaarch64


Disassembly of section .text:

0000000000000e70 <mt76_npu_dma_add_buf>:
     e70:	a9bc7bfd 	stp	x29, x30, [sp, #-64]!
     e74:	52801805 	mov	w5, #0xc0                  	// #192
     e78:	910003fd 	mov	x29, sp
     e7c:	a90153f3 	stp	x19, x20, [sp, #16]
     e80:	aa0103f3 	mov	x19, x1
     e84:	aa0403e1 	mov	x1, x4
     e88:	a9025bf5 	stp	x21, x22, [sp, #32]
     e8c:	52801a16 	mov	w22, #0xd0                  	// #208
     e90:	a90363f7 	stp	x23, x24, [sp, #48]
     e94:	aa0203f7 	mov	x23, x2
     e98:	aa0303f8 	mov	x24, x3
     e9c:	f9400406 	ldr	x6, [x0, #8]
     ea0:	79405660 	ldrh	w0, [x19, #42]
     ea4:	f9401275 	ldr	x21, [x19, #32]
     ea8:	f94428c2 	ldr	x2, [x6, #2128]
     eac:	9bb67c00 	umull	x0, w0, w22
     eb0:	8b0002a0 	add	x0, x21, x0
     eb4:	79401054 	ldrh	w20, [x2, #8]
     eb8:	91004000 	add	x0, x0, #0x10
     ebc:	7103029f 	cmp	w20, #0xc0
     ec0:	1a859294 	csel	w20, w20, w5, ls	// ls = plast
     ec4:	92403e82 	and	x2, x20, #0xffff
     ec8:	12003e94 	and	w20, w20, #0xffff
     ecc:	94000000 	bl	0 <memcpy>
			ecc: R_AARCH64_CALL26	memcpy
     ed0:	79405660 	ldrh	w0, [x19, #42]
     ed4:	f9400301 	ldr	x1, [x24]
     ed8:	9bb67c00 	umull	x0, w0, w22
     edc:	8b0002a0 	add	x0, x21, x0
     ee0:	b9000401 	str	w1, [x0, #4]
     ee4:	d50332bf 	dmb	oshst
     ee8:	79405660 	ldrh	w0, [x19, #42]
     eec:	52800501 	mov	w1, #0x28                  	// #40
     ef0:	b94072e2 	ldr	w2, [x23, #112]
     ef4:	12800004 	mov	w4, #0xffffffff            	// #-1
     ef8:	9bb67c00 	umull	x0, w0, w22
     efc:	d36e3042 	ubfiz	x2, x2, #18, #13
     f00:	2a140454 	orr	w20, w2, w20, lsl #1
     f04:	32000294 	orr	w20, w20, #0x1
     f08:	b8206ab4 	str	w20, [x21, x0]
     f0c:	f9400a62 	ldr	x2, [x19, #16]
     f10:	79405660 	ldrh	w0, [x19, #42]
     f14:	9ba10802 	umaddl	x2, w0, w1, x2
     f18:	39409843 	ldrb	w3, [x2, #38]
     f1c:	32000063 	orr	w3, w3, #0x1
     f20:	39009843 	strb	w3, [x2, #38]
     f24:	79405663 	ldrh	w3, [x19, #42]
     f28:	f9400a62 	ldr	x2, [x19, #16]
     f2c:	9ba17c63 	umull	x3, w3, w1
     f30:	8b030042 	add	x2, x2, x3
     f34:	39409843 	ldrb	w3, [x2, #38]
     f38:	321f0063 	orr	w3, w3, #0x2
     f3c:	39009843 	strb	w3, [x2, #38]
     f40:	79405663 	ldrh	w3, [x19, #42]
     f44:	f9400a62 	ldr	x2, [x19, #16]
     f48:	9ba17c63 	umull	x3, w3, w1
     f4c:	8b030042 	add	x2, x2, x3
     f50:	f900045f 	str	xzr, [x2, #8]
     f54:	79405662 	ldrh	w2, [x19, #42]
     f58:	f9400a63 	ldr	x3, [x19, #16]
     f5c:	9ba17c42 	umull	x2, w2, w1
     f60:	f822687f 	str	xzr, [x3, x2]
     f64:	79405663 	ldrh	w3, [x19, #42]
     f68:	f9400a62 	ldr	x2, [x19, #16]
     f6c:	9ba17c61 	umull	x1, w3, w1
     f70:	8b010041 	add	x1, x2, x1
     f74:	79004824 	strh	w4, [x1, #36]
     f78:	79405661 	ldrh	w1, [x19, #42]
     f7c:	29460a63 	ldp	w3, w2, [x19, #48]
     f80:	11000421 	add	w1, w1, #0x1
     f84:	11000442 	add	w2, w2, #0x1
     f88:	b9003662 	str	w2, [x19, #52]
     f8c:	1ac30c22 	sdiv	w2, w1, w3
     f90:	1b038441 	msub	w1, w2, w3, w1
     f94:	79005661 	strh	w1, [x19, #42]
     f98:	a94153f3 	ldp	x19, x20, [sp, #16]
     f9c:	a9425bf5 	ldp	x21, x22, [sp, #32]
     fa0:	a94363f7 	ldp	x23, x24, [sp, #48]
     fa4:	a8c47bfd 	ldp	x29, x30, [sp], #64
     fa8:	d65f03c0 	ret
