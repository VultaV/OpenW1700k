# This is free software, licensed under the Apache License, Version 2.0.

include $(TOPDIR)/rules.mk

PKG_VERSION = $(PKG_SRC_VERSION)
PKG_RELEASE:=2

LUCI_TITLE:=LuCI Support for Wi-Fi MLO
LUCI_DEPENDS:=+luci-base +luci-mod-network

PKG_LICENSE:=Apache-2.0
PKG_MAINTAINER:=YYH2913

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
