# r30 packages-feed metadata fix

Apply `0001-ovpn-backports-set-module-version.patch` at the root of the packages feed (pinned commit `d50c9e2ac63808f8ea487ef8bc91632e7a483804`):

```sh
git -C feeds/packages apply /absolute/path/to/0001-ovpn-backports-set-module-version.patch
```

The direct Kbuild recipe bypasses OpenVPN's top-level version generator. Defining `OVPN_MODULE_VERSION` from `PKG_VERSION` restores the module version metadata when `CONFIG_MODULE_STRIPPED` is disabled. `PKG_RELEASE` becomes 2. This does not change OpenVPN forwarding or disable kernel module version checks.

The source package is still 7.1.0.2026080300 with its existing source SHA256. Isolated compilation of actual `main.c` reproduced the original failure and passed after the macro was supplied; the resulting ELF `.modinfo` contains the package version. The full package/image build is a separate validation step.
