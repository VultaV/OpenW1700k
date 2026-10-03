#!/usr/bin/env python3
"""Check the package feeds of a W1700K build.

Router side: evaluate the APK branch of Package/base-files/install with the
real rules.mk, version.mk and feeds.mk and docs/mlo-r43/r43.config, and check
that the generated /etc/apk/repositories.d/distfeeds.list enables no remote
feed.

Usage: python3 tests/test_package_feeds.py [SOURCE_ROOT]
SOURCE_ROOT defaults to this checkout. Needs GNU make and GNU sed, like the
build itself.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parents[1]).resolve()


def gnu(*names):
    for name in names:
        path = shutil.which(name)
        if path and 'GNU' in subprocess.run([path, '--version'], capture_output=True,
                                            text=True).stdout:
            return path
    sys.exit(f'GNU {names[-1]} not found')


make, sed = gnu('gmake', 'make'), gnu('gsed', 'sed')
recipe = (root / 'package/base-files/Makefile').read_text()
apk_block = re.search(r'^define Package/base-files/install\n.*?'
                      r'^ifneq \(\$\(CONFIG_USE_APK\),\)\n(.*?)^else\n',
                      recipe, re.S | re.M).group(1)

with tempfile.TemporaryDirectory() as tmp:
    # LINUX_* are the values of the installed r43 image; they only name the
    # kmods feed that upstream logic would add.
    (Path(tmp) / 'Makefile').write_text(f'''\
TOPDIR := {root}
include $(TOPDIR)/docs/mlo-r43/r43.config
include $(TOPDIR)/rules.mk
SED := {sed} -i -e
include $(INCLUDE_DIR)/version.mk
include $(INCLUDE_DIR)/feeds.mk
FEEDS_AVAILABLE := luci packages routing
LINUX_VERSION := 6.18.44
LINUX_RELEASE := 1
LINUX_VERMAGIC := 73da9a4281bd33ef609e81ecc0cb78e7
STAGING_DIR := {tmp}
define apk_block
{apk_block}endef
all:
\t$(call apk_block,{tmp}/root)
''')
    subprocess.run([make, '-s', '-C', tmp], check=True, stdout=subprocess.DEVNULL)
    distfeeds = (Path(tmp) / 'root/etc/apk/repositories.d/distfeeds.list').read_text()

print('distfeeds.list from base-files with r43.config:')
print(distfeeds, end='')
feeds = [line for line in distfeeds.splitlines()
         if line.strip() and not line.lstrip().startswith('#')]
assert not feeds, f'image enables remote feeds built for another kernel ABI: {feeds}'

print('package feeds: PASS')
