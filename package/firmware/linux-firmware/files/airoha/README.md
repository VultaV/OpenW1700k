# EN7581 + MT7996 NPU firmware

Vendor v0.8 test pair from https://github.com/zhengping-zhang/airoha-npu/commit/1df6a36f849ea52cadfc326ec5b583d658be630e . Packaged under the existing linux-firmware `LICENSE.airoha` terms.

- `en7581_MT7996_npu_rv32.bin`: 125832 bytes; SHA256 `7068a987bb95e89129a69de10d598f234a4400023eb23aacc8eb377e5f0fe0ea`
- `en7581_MT7996_npu_data.bin`: 3092 bytes; SHA256 `6fd9506e399ebb309801ac2ecc74d3e10fa66731afc828c76fde8a67b2153f49`

The old exact-pair instruction guard does not match these files and must not patch them at the old offset. Runtime NPU execution and stability are unverified.
