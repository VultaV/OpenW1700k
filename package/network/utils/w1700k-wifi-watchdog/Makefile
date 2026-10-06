include $(TOPDIR)/rules.mk

PKG_NAME:=w1700k-wifi-watchdog
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/w1700k-wifi-watchdog
  SECTION:=net
  CATEGORY:=Network
  TITLE:=W1700K Wi-Fi outage evidence collector
  DEPENDS:=@TARGET_airoha +iw +ubus +jsonfilter +logd +ip \
	+@BUSYBOX_CONFIG_FLOCK +@BUSYBOX_CONFIG_TIMEOUT \
	+@BUSYBOX_CONFIG_FEATURE_FANCY_HEAD +@BUSYBOX_CONFIG_FEATURE_FANCY_TAIL
endef

define Package/w1700k-wifi-watchdog/description
  Capture bounded, private diagnostics when both W1700K APs show an outage
  signature. Never changes wireless configuration or restarts Wi-Fi.
endef

define Build/Compile
endef

define Package/w1700k-wifi-watchdog/install
	$(INSTALL_DIR) $(1)/etc/init.d $(1)/usr/sbin
	$(INSTALL_BIN) ./files/w1700k-wifi-watchdog.init $(1)/etc/init.d/w1700k-wifi-watchdog
	$(INSTALL_BIN) ./files/w1700k-wifi-watchdog.sh $(1)/usr/sbin/w1700k-wifi-watchdog
endef

$(eval $(call BuildPackage,w1700k-wifi-watchdog))
