#!/usr/bin/env bash
# Probe: install `linuxcnc-uspace` in a Debian system and import it.
#
# Run as a file (`bash probe_install.sh`, never piped into `bash -s`)
# as root inside Debian (a `debian:trixie` container, a distrobox
# box with `sudo`, or WSL).  A Debian older than Trixie is upgraded
# first.  Each step prints `PROBE <step> ok|FAIL`; the last line is
# `PROBE RESULT ...`.  Used by `.github/workflows/probe_linuxcnc.yml`.
# shellcheck disable=SC1091  # /etc/os-release is the system's.
set -u
exec < /dev/null  # Nothing below may read the caller's input.
export DEBIAN_FRONTEND=noninteractive
BASE=https://linuxcnc.org
DIST=dists/trixie/2.9-uspace
WORK=/tmp/lcnc_probe
mkdir -p "$WORK"
cd "$WORK" || exit 1

# Report one step and stop at the first failure.
step() {
    local name=$1
    shift
    echo "::group::PROBE $name"
    if "$@"; then
        echo "::endgroup::"
        echo "PROBE $name ok"
    else
        echo "::endgroup::"
        echo "PROBE $name FAIL"
        echo "PROBE RESULT FAIL at $name"
        exit 1
    fi
}

# Upgrade to Trixie if the system is older.
to_trixie() {
    . /etc/os-release
    echo "Debian ${VERSION_CODENAME:-?} (${PRETTY_NAME:-?})"
    [ "${VERSION_CODENAME:-}" = trixie ] && return 0
    sed -i "s/\b${VERSION_CODENAME}\b/trixie/g" \
        /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null
    apt-get update && apt-get -y full-upgrade && . /etc/os-release &&
        echo "now ${VERSION_CODENAME}" && [ "$VERSION_CODENAME" = trixie ]
}

# Tools the probe needs.
tools() {
    apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates
}

# Pick the newest `linuxcnc-uspace` for this architecture, fetch it,
# and check its SHA256 against the index.
fetch() {
    ARCH=$(dpkg --print-architecture)
    curl -fsSL -o Packages "$BASE/$DIST/binary-$ARCH/Packages" || return 1
    awk '/^Package: /{p=($2=="linuxcnc-uspace")}
         p&&/^Version: /{v=$2} p&&/^Filename: /{f=$2}
         p&&/^SHA256: /{s=$2}
         /^$/{if(p&&v!="")print v, f, s; p=0; v=""}
         END{if(p&&v!="")print v, f, s}' Packages > candidates
    cat candidates
    BEST=""
    while read -r v f s; do
        if [ -z "$BEST" ] || dpkg --compare-versions "$v" gt "$BEST"; then
            BEST=$v FILE=$f SUM=$s
        fi
    done < candidates
    [ -n "$BEST" ] || return 1
    echo "newest $BEST: $FILE"
    curl -fsSL -o "${FILE##*/}" "$BASE/$FILE" &&
        echo "$SUM  ${FILE##*/}" | sha256sum -c -
}

# Install it (with its dependencies) from the local file.
install() {
    apt-get install -y "./${FILE##*/}"
}

# Import the Python module.
import_it() {
    python3 -c 'import linuxcnc, sys
print(sys.version)
print("linuxcnc", getattr(linuxcnc, "version", "?"), linuxcnc.__file__)'
}

# Start the realtime layer briefly (shared memory, as the simulator
# does); `rtapi_app` loses its setuid bit, as for rootless podman.
halrun_it() {
    chmod u-s /usr/bin/rtapi_app || return 1
    printf 'loadrt threads name1=t period1=1000000\nshow thread\n' |
        timeout 120 halrun
}

step trixie to_trixie
step tools tools
step fetch fetch
step install install
step import import_it
if halrun_it; then
    echo "PROBE halrun ok"
    echo "PROBE RESULT ok: linuxcnc-uspace $BEST ($ARCH) imports," \
        "halrun ok"
else
    echo "PROBE halrun FAIL"
    echo "PROBE RESULT ok: linuxcnc-uspace $BEST ($ARCH) imports," \
        "halrun FAIL"
fi
