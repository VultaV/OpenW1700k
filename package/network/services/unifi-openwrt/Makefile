# SPDX-License-Identifier: GPL-2.0-or-later
include $(TOPDIR)/rules.mk

PKG_NAME:=unifi-openwrt
PKG_VERSION:=0.3.0_p20261122
PKG_RELEASE:=1

PKG_SOURCE:=unifi-openwrt-0.3.0.tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/antoniocosta/unifi-openwrt/tar.gz/1f7ba1282c24c34ae248704893361c3ab80a9889?
PKG_HASH:=a755dd3dca77b8b43091212fd98e2a2be1b940fb677e34491c29e96e2d8776cb
PKG_BUILD_DIR:=$(BUILD_DIR)/unifi-openwrt-1f7ba1282c24c34ae248704893361c3ab80a9889

PKG_MAINTAINER:=
PKG_LICENSE:=GPL-2.0-or-later
PKG_LICENSE_FILES:=LICENSE

PKG_BUILD_DEPENDS:=golang/host
PKG_BUILD_PARALLEL:=1
PKG_BUILD_FLAGS:=no-mips16

GO_PKG:=github.com/antoniocosta/unifi-openwrt
GO_PKG_BUILD_PKG:=github.com/antoniocosta/unifi-openwrt/cmd/uow

include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/golang/golang-package.mk

define Package/unifi-openwrt
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Wireless
  TITLE:=Adopt this access point into a UniFi controller
  URL:=https://github.com/antoniocosta/unifi-openwrt
  # Runtime needs (besides base: uci, ubus, jsonfilter, iw, nftables):
  #  hostapd-utils   hostapd_cli for the runtime client deny list
  #  kmod-nft-bridge per-client rate limits (nftables on the bridge)
  #  kmod-veth       802.11r key exchange with UniFi APs (the relay's bridge port)
  # A *full* hostapd/wpad (wpad-mbedtls, wpad-wolfssl, wpad-openssl, or the
  # hostapd-* equivalents) is recommended but deliberately not a dependency:
  # every variant, basic and full, provides the same virtual names (hostapd,
  # wpad-*-any), so there is no name that means "full"; naming one concrete
  # variant would pick the TLS library for the user and conflict with the
  # wpad-basic-* that images ship by default. The daemon works with a basic
  # wpad (falling back to ubus del_client for blocking) and the post-install
  # script says when a basic variant is installed and how to swap it.
  # iw and nftables are not listed because iw-full and nftables-json are
  # alternatives a Kconfig select cannot express; both come with default
  # images (tools/mkapk.sh lists them, apk resolves virtual names).
  DEPENDS:=$(GO_ARCH_DEPENDS) +hostapd-utils +kmod-nft-bridge +kmod-veth
endef

define Package/unifi-openwrt/description
  A daemon that makes an OpenWrt access point adopt into a UniFi Network
  controller as a UniFi AP model and applies the controller's Wi-Fi settings
  through UCI. Disabled until enabled in /etc/config/unifi-openwrt.
  Optional: usteer (band steering), alsa-utils (Locate beep), snmpd.
endef

define Package/unifi-openwrt/conffiles
/etc/config/unifi-openwrt
/etc/unifi-openwrt/
endef

define Package/unifi-openwrt/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/etc/init.d $(1)/etc/config
	$(INSTALL_BIN) $(GO_PKG_BUILD_BIN_DIR)/uow $(1)/usr/bin/uow
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/packaging/files/etc/init.d/unifi-openwrt $(1)/etc/init.d/
	$(INSTALL_CONF) $(PKG_BUILD_DIR)/packaging/files/etc/config/unifi-openwrt $(1)/etc/config/
	$(INSTALL_DIR) $(1)/lib/upgrade/keep.d
	echo /etc/unifi-openwrt/ > $(1)/lib/upgrade/keep.d/unifi-openwrt
endef

# Runs after OpenWrt's default_postinst (which enables the init script at
# boot and starts it; with option enabled '0', the default, start does
# nothing). tools/mkapk.sh copies this block into its packages, so keep it
# plain sh ($$ is make's escape for $).
define Package/unifi-openwrt/postinst
#!/bin/sh
mkdir -p "$${IPKG_INSTROOT}/etc/unifi-openwrt/state"
chmod 700 "$${IPKG_INSTROOT}/etc/unifi-openwrt" "$${IPKG_INSTROOT}/etc/unifi-openwrt/state"
[ -z "$${IPKG_INSTROOT}" ] || exit 0
# an already running daemon (upgrade, or a former manual install) picks up
# the new binary
/etc/init.d/unifi-openwrt running 2>/dev/null && /etc/init.d/unifi-openwrt restart
for f in /lib/apk/packages/wpad-basic*.list /lib/apk/packages/hostapd-basic*.list \
	/usr/lib/opkg/info/wpad-basic*.list /usr/lib/opkg/info/hostapd-basic*.list; do
	[ -f "$$f" ] || continue
	b=$${f##*/}; b=$${b%.list}
	echo "unifi-openwrt: $$b is a basic hostapd; a full one is recommended (802.11k/v, WPA-Enterprise, deny list):"
	echo "unifi-openwrt:   apk del $$b && apk add $$(echo $$b | sed 's/-basic//')   (Wi-Fi restarts; do it over a cable)"
done
[ "$$(uci -q get unifi-openwrt.main.enabled)" = 1 ] || {
	echo "unifi-openwrt: installed, disabled. Suggested UniFi models for this AP:"
	echo "unifi-openwrt:   uow -ap local -mac \$$(cat /sys/class/net/br-lan/address) -suggest"
	echo "unifi-openwrt: then set model, inform_url and enabled=1 in /etc/config/unifi-openwrt and run"
	echo "unifi-openwrt:   /etc/init.d/unifi-openwrt start"
}
exit 0
endef

define Package/unifi-openwrt/postrm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] || [ ! -d /etc/unifi-openwrt ] || \
	echo "unifi-openwrt: kept /etc/unifi-openwrt (adoption state); rm -rf /etc/unifi-openwrt to forget it"
exit 0
endef

$(eval $(call GoBinPackage,unifi-openwrt))
$(eval $(call BuildPackage,unifi-openwrt))
