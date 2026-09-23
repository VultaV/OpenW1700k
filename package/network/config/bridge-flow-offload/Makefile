include $(TOPDIR)/rules.mk

PKG_NAME:=bridge-flow-offload
PKG_VERSION:=1.0
PKG_RELEASE:=2
PKG_LICENSE:=GPL-2.0

include $(INCLUDE_DIR)/package.mk

define Package/bridge-flow-offload
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Firewall
  TITLE:=Bridge hardware flow offloading
  DEPENDS:=+kmod-nft-bridge +kmod-nft-offload +firewall4 +ip-bridge +jsonfilter
endef

define Package/bridge-flow-offload/description
  Optional IPv4 TCP hardware offloading between two explicitly trusted
  bridge ports. Disabled by default; unsupported topology or policy
  disables acceleration without restarting the firewall or network.
endef

define Package/bridge-flow-offload/conffiles
/etc/config/bridge-flow-offload
endef

define Build/Configure
	true
endef

define Build/Compile
	true
endef

define Package/bridge-flow-offload/install
	$(INSTALL_DIR) $(1)/usr/share/bridge-flow-offload
	$(INSTALL_BIN) ./files/usr/share/bridge-flow-offload/apply-rules.sh $(1)/usr/share/bridge-flow-offload/apply-rules.sh
	$(INSTALL_DIR) $(1)/etc/config $(1)/etc/hotplug.d/net $(1)/etc/uci-defaults
	$(INSTALL_CONF) ./files/etc/config/bridge-flow-offload $(1)/etc/config/bridge-flow-offload
	$(INSTALL_BIN) ./files/etc/hotplug.d/net/51-bridge-flow-offload $(1)/etc/hotplug.d/net/51-bridge-flow-offload
	$(INSTALL_BIN) ./files/etc/uci-defaults/90-bridge-flow-offload $(1)/etc/uci-defaults/90-bridge-flow-offload
endef

$(eval $(call BuildPackage,bridge-flow-offload))
