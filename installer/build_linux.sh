#!/usr/bin/env bash
# Build Linux AppImage for PB Asset Decryptor
# Requirements: Python 3.10+, PyInstaller, appimagetool
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION=$(python3 -c "import sys; sys.path.insert(0,'$ROOT_DIR'); from pb_decryptor import __version__; print(__version__)")

echo "=== Building PB Asset Decryptor v${VERSION} for Linux ==="

# Ensure icon exists
if [ ! -f "$ROOT_DIR/pb_decryptor/icon.png" ]; then
    echo "Generating icon..."
    pip3 install --quiet pillow 2>/dev/null || true
    python3 "$ROOT_DIR/generate_icon.py"
fi

# PyInstaller build (onedir mode for AppImage)
echo "Running PyInstaller..."
cd "$ROOT_DIR"
pip3 install --quiet pyinstaller 2>/dev/null || true
pyinstaller \
    --name "pb-decryptor" \
    --onedir \
    --paths "$ROOT_DIR" \
    --add-data "$ROOT_DIR/pb_decryptor/icon.png:pb_decryptor" \
    --noconfirm \
    --clean \
    --distpath "$SCRIPT_DIR/build/dist" \
    --workpath "$SCRIPT_DIR/build/work" \
    --specpath "$SCRIPT_DIR/build" \
    "$SCRIPT_DIR/pyinstaller_entry.py"

DIST_DIR="$SCRIPT_DIR/build/dist/pb-decryptor"

# Build AppDir structure
APPDIR="$SCRIPT_DIR/build/PB_Asset_Decryptor.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy PyInstaller output
cp -r "$DIST_DIR"/* "$APPDIR/usr/bin/"

# Icon (AppImage looks for both top-level icon + hicolor)
cp "$ROOT_DIR/pb_decryptor/icon.png" \
   "$APPDIR/usr/share/icons/hicolor/256x256/apps/pb-decryptor.png"
cp "$ROOT_DIR/pb_decryptor/icon.png" "$APPDIR/pb-decryptor.png"

# Desktop entry
cat > "$APPDIR/pb-decryptor.desktop" <<EOF
[Desktop Entry]
Name=PB Asset Decryptor
Exec=pb-decryptor
Icon=pb-decryptor
Type=Application
Categories=Utility;
Comment=Extract and re-pack Pinball Brothers game assets
EOF

# AppRun script
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
SELF="$(readlink -f "$0")"
HERE="$(dirname "$SELF")"
exec "$HERE/usr/bin/pb-decryptor" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Build AppImage
echo "Building AppImage..."
mkdir -p "$SCRIPT_DIR/Output"
APPIMAGE_NAME="PB_Asset_Decryptor_v${VERSION}_Linux_x86_64.AppImage"

if command -v appimagetool &>/dev/null; then
    ARCH=x86_64 appimagetool "$APPDIR" "$SCRIPT_DIR/Output/$APPIMAGE_NAME"
else
    echo "appimagetool not found. Download from:"
    echo "  https://github.com/AppImage/appimagetool/releases"
    echo ""
    echo "AppDir is ready at: $APPDIR"
    echo "Run manually: ARCH=x86_64 appimagetool '$APPDIR' '$SCRIPT_DIR/Output/$APPIMAGE_NAME'"
    exit 1
fi

echo ""
echo "=== Build complete ==="
echo "Output: $SCRIPT_DIR/Output/$APPIMAGE_NAME"
