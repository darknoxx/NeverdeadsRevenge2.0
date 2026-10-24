#!/usr/bin/env bash
# Build the Linux AppImage: a PyInstaller one-folder build inside an AppDir,
# packed by appimagetool. Run from anywhere.
#
#   packaging/linux/build_appimage.sh
#
# appimagetool is looked for on PATH, then in build/ (where the CI workflow
# downloads it); APPIMAGETOOL names one outright. ``--no-appstream`` keeps the
# build free of metadata files this game does not ship.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
cd "$root"

name="NeverdeadsRevenge2"
slug="neverdeads-revenge-2"
appdir="build/AppDir"
out="dist/$name-x86_64.AppImage"

command -v pyinstaller >/dev/null 2>&1 || {
    echo "pyinstaller is not on PATH: python -m pip install pyinstaller" >&2
    exit 1
}

tool="${APPIMAGETOOL:-}"
if [[ -z "$tool" ]]; then
    for candidate in appimagetool build/appimagetool-x86_64.AppImage; do
        if command -v "$candidate" >/dev/null 2>&1 || [[ -x "$candidate" ]]; then
            tool="$candidate"
            break
        fi
    done
fi
if [[ -z "$tool" ]]; then
    echo "appimagetool not found: put it in build/ or set APPIMAGETOOL" >&2
    exit 1
fi

pyinstaller --noconfirm --clean packaging/linux/neverdeads_revenge.spec

# The AppDir layout the specification asks for: the payload under usr/bin, the
# desktop entry and the icon at the root, and AppRun as the entry point.
rm -rf "$appdir"
install -d "$appdir/usr/bin" "$appdir/usr/share/icons/hicolor/256x256/apps"
cp -a "dist/$name/." "$appdir/usr/bin/"
# One desktop entry, generated from the same template the installer fills in:
# the AppImage's Exec is the frozen binary, the installer's is its launcher.
sed -e "s|@NAME@|Neverdead's Revenge 2.0|g" \
    -e "s|@EXEC@|$name|g" \
    -e "s|@SLUG@|$slug|g" \
    "$root/assets/$slug.desktop.in" > "$appdir/$slug.desktop"
chmod 0644 "$appdir/$slug.desktop"
install -m 0644 "$here/$slug.png" "$appdir/$slug.png"
install -m 0644 "$here/$slug.png" \
    "$appdir/usr/share/icons/hicolor/256x256/apps/$slug.png"
install -m 0755 "$here/AppRun" "$appdir/AppRun"

mkdir -p dist
ARCH="${ARCH:-x86_64}" "$tool" --no-appstream "$appdir" "$out"
echo "wrote $out"
