#!/bin/sh
# Build the 3DS XNU: ios3ds/build/xnu/mk.sh [CONFIG] [make args]
. $HOME/.local/xnu-deps/env.sh
X="$(cd "$(dirname "$0")/../.." && pwd)"   # ios3ds/ (this script lives in build/xnu/)
CFG=${1:-ARM_RVEB_V6}; [ $# -gt 0 ] && shift
cd $X/xnu3ds && exec nice -n 19 make TARGET_CONFIGS="development arm $CFG" DEFAULT_ARM_MACHINE_CONFIG=$CFG \
  HOST_CC=$HOME/.local/xnu-deps/bin/hostcc HOST_FLEX=$HOME/.local/xnu-deps/root/usr/bin/flex HOST_BISON=$HOME/.local/xnu-deps/root/usr/bin/bison XCRUN=$HOME/.local/xnu-deps/bin/xcrun MAKEJOBS=--jobs=2 \
  OBJROOT=$X/build/xnu/obj SYMROOT=$X/build/xnu/sym DSTROOT=$X/build/xnu/dst "$@"
