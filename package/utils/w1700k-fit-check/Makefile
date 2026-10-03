include $(TOPDIR)/rules.mk

PKG_NAME:=w1700k-fit-check
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/w1700k-fit-check
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=W1700K UBI2 FIT layout validation
  DEPENDS:=+libfdt
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -Wall -Wextra \
		-o $(PKG_BUILD_DIR)/w1700k-fit-check $(PKG_BUILD_DIR)/w1700k-fit-check.c \
		$(TARGET_LDFLAGS) -lfdt
endef

define Package/w1700k-fit-check/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/w1700k-fit-check $(1)/usr/bin/
endef

$(eval $(call BuildPackage,w1700k-fit-check))
