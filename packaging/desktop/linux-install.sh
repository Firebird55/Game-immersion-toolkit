#!/bin/sh
set -eu

# Runs from an extracted self-contained bundle; no Python/Node/package manager.
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
prefix="${HOME}/.local/opt/game-immersion-toolkit"
menu=yes
desktop=no
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) [ "$#" -ge 2 ] || exit 2; prefix=$2; shift 2 ;;
    --no-menu) menu=no; shift ;;
    --desktop) desktop=yes; shift ;;
    --help) printf '%s\n' 'Usage: ./install.sh [--prefix ABSOLUTE_DIRECTORY] [--no-menu] [--desktop]'; exit 0 ;;
    *) printf '%s\n' 'Unknown installation option.' >&2; exit 2 ;;
  esac
done
case "$prefix" in /*) ;; *) printf '%s\n' 'Installation directory must be absolute.' >&2; exit 2 ;; esac
case "$prefix" in *'"'*|*'`'*|*'$'*|*'%'*|*'\'*|*'
'*) printf '%s\n' 'Installation directory contains unsupported launcher characters.' >&2; exit 2 ;; esac
if [ -e "$prefix" ]; then
  printf '%s\n' 'Choose an empty installation directory. Quit the previous version before changing its shortcut.' >&2
  exit 1
fi
mkdir -p -- "$(dirname -- "$prefix")"
prefix=$(CDPATH= cd -- "$(dirname -- "$prefix")" && pwd -P)/$(basename -- "$prefix")
case "$prefix/" in "$source_dir/"*) printf '%s\n' 'Installation cannot be inside the extracted source directory.' >&2; exit 2 ;; esac
cp -R -- "$source_dir" "$prefix"
chmod +x -- "$prefix/ProxyTranscriptRuntime"
applications="${XDG_DATA_HOME:-${HOME}/.local/share}/applications"
write_launcher() {
  printf '[Desktop Entry]\nType=Application\nName=Game Immersion Toolkit\nExec="%s/ProxyTranscriptRuntime"\nIcon=%s/_internal/desktop/proxy-transcript.png\nTerminal=false\nCategories=Game;Education;\n' "$prefix" "$prefix" > "$1"
  chmod +x -- "$1"
}
if [ "$menu" = yes ]; then
  mkdir -p -- "$applications"
  write_launcher "$applications/game-immersion-toolkit.desktop"
fi
if [ "$desktop" = yes ]; then
  desktop_dir="${HOME}/Desktop"
  if command -v xdg-user-dir >/dev/null 2>&1; then desktop_dir=$(xdg-user-dir DESKTOP); fi
  if [ -d "$desktop_dir" ]; then write_launcher "$desktop_dir/game-immersion-toolkit.desktop"; fi
fi
printf 'Installed in %s\nStart the executable or its application-menu shortcut. User data is kept separately.\n' "$prefix"
