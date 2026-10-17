#!/usr/bin/env bash
#
# Install Neverdead's Revenge 2.0 for the current user.
#
# Everything goes under $HOME -- no sudo, nothing system-wide, and the game stays
# in this directory. Run it again any time; it reuses what is already there and
# installs whatever is missing.
#
#   ./install.sh                 set up, and add the menu entry on Linux
#   ./install.sh --no-desktop    set up only
#   ./install.sh --sdl           ignored: there is one front end now, and the
#                                flag is kept so an old script still runs
#   ./install.sh --python PATH   use a specific interpreter, not python3
#   ./install.sh --dry-run       say what it would do, change nothing
#   ./install.sh --uninstall     remove the menu entry and the icon
#
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
slug="neverdeads-revenge-2"
name="Neverdead's Revenge 2.0"

data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
launcher_dir="$data_home/$slug"
desktop_dir="$data_home/applications"
icon_dir="$data_home/icons/hicolor/scalable/apps"
venv_dir="$here/.venv"

python_bin="python3"
want_desktop="auto"   # auto | yes | no
want_uninstall=0
dry_run=0

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m warning:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m error:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    # Everything between the shebang and the first line of code. Robust to the
    # header growing, and awk is the same awk on Linux and macOS.
    awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' "$0"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --desktop) want_desktop="yes" ;;
        --sdl) ;;   # one front end now; the flag is kept so old scripts run
        --no-desktop) want_desktop="no" ;;
        --dry-run) dry_run=1 ;;
        --uninstall) want_uninstall=1 ;;
        --python)
            # A Mac can easily have four Pythons installed at once and no
            # reliable answer to which one python3 is, so let the user say.
            [[ $# -ge 2 ]] || die "--python needs the path to an interpreter"
            python_bin="$2"
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option '$1' (try --help)" ;;
    esac
    shift
done

# -- what kind of machine is this -------------------------------------------

os="$(uname -s 2>/dev/null || echo unknown)"
is_macos=0
[[ "$os" == "Darwin" ]] && is_macos=1

if [[ "$want_desktop" == "auto" ]]; then
    if [[ $is_macos -eq 1 ]]; then
        # macOS has no applications menu that reads .desktop files. Writing one
        # there would not fail -- it would just be a file nothing ever opens,
        # which is worse than saying so.
        want_desktop="no"
    else
        want_desktop="yes"
    fi
fi

# -- uninstall --------------------------------------------------------------

if [[ $want_uninstall -eq 1 ]]; then
    say "Removing the menu entry"
    rm -f "$desktop_dir/$slug.desktop"
    rm -f "$icon_dir/$slug.svg"
    rm -rf "$launcher_dir"
    command -v update-desktop-database >/dev/null && update-desktop-database "$desktop_dir" 2>/dev/null || true
    say "Done. The game itself is untouched -- delete this directory to remove it,"
    say "and .venv inside it if you want the virtualenv gone too."
    exit 0
fi

# -- python -----------------------------------------------------------------

command -v "$python_bin" >/dev/null || {
    if [[ $is_macos -eq 1 ]]; then
        die "'$python_bin' not found. Install Python 3.12 or newer from
       https://www.python.org/downloads/ or with Homebrew:
         brew install python"
    fi
    die "'$python_bin' not found. Install it with: sudo apt install python3"
}

# Running it is not the same as it existing. On a Mac without the Xcode command
# line tools, /usr/bin/python3 is a shim that prints "no developer tools were
# found" and exits -- so a bare `command -v` check passes and then the version
# check fails with a message about a version nobody can see.
if ! "$python_bin" -c 'import sys' >/dev/null 2>&1; then
    if [[ $is_macos -eq 1 ]]; then
        die "'$python_bin' exists but does not run. On macOS that usually means
       the command line tools are missing. Either:
         xcode-select --install
       or install Python 3.12 or newer from https://www.python.org/downloads/
       or with Homebrew:
         brew install python"
    fi
    die "'$python_bin' exists but does not run. Reinstall Python 3.12 or newer."
fi

if ! "$python_bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
    found="$("$python_bin" -V 2>&1)"
    if [[ $is_macos -eq 1 ]]; then
        # macOS ships a Python from 2021 and never replaces it, so this is the
        # ordinary first step on a Mac rather than an unusual failure.
        die "$found is too old -- Python 3.12 or newer is needed.
       macOS ships an old Python and never updates it, so this is the normal
       first step on a Mac. Either:
         brew install python
       or download the installer from https://www.python.org/downloads/

       Then run this again. If python3 is still the old one -- Homebrew keeps
       versioned formulae out of the way -- point at the new interpreter:
         ./install.sh --python \$(brew --prefix)/bin/python3"
    fi
    die "Python 3.12 or newer is required, but $found is what is installed."
fi

if [[ $dry_run -eq 1 ]]; then
    say "Dry run -- nothing has been changed."
    note "system      $os$([[ $is_macos -eq 1 ]] && echo ' (macOS)')"
    note "python      $("$python_bin" -V 2>&1)  ($python_bin)"
    note "virtualenv  $venv_dir$([[ -x "$venv_dir/bin/python" ]] && echo ' (already there)' || echo ' (will be created)')"
    note "menu entry  $([[ "$want_desktop" == "yes" ]] && echo 'yes' || echo 'no')"
    if [[ "$want_desktop" == "yes" ]]; then
        note "            $desktop_dir/$slug.desktop"
        note "            $icon_dir/$slug.svg"
    fi
    exit 0
fi

# -- virtualenv -------------------------------------------------------------

python=""
if [[ -x "$venv_dir/bin/python" ]]; then
    python="$venv_dir/bin/python"
    say "Reusing the virtualenv in .venv"
else
    say "Creating a virtualenv in .venv"
    # The one Ubuntu trap worth catching by hand: python3-venv is a separate
    # package, and without it this fails with a message about ensurepip that
    # does not name the package you actually need.
    if ! err="$("$python_bin" -m venv "$venv_dir" 2>&1)"; then
        printf '%s\n' "$err" >&2
        if [[ $is_macos -eq 1 ]]; then
            die "could not create a virtualenv. Reinstall Python 3.12 or newer
       from https://www.python.org/downloads/ or with Homebrew."
        fi
        die "could not create a virtualenv. On Ubuntu this is usually fixed by:
       sudo apt install python3-venv"
    fi
    python="$venv_dir/bin/python"
fi

say "Installing $name and its dependencies"
"$python" -m pip install --quiet --upgrade pip
"$python" -m pip install --quiet --editable "$here"

# A zip download does not reliably keep the executable bit, and ./ndr2 is the
# first thing the README tells you to run.
chmod +x "$here/ndr2"

# A virtualenv that was set up while the game had two launchers still has the
# second one in it, pointing at a module that is gone. It is not ours to keep.
rm -f "$venv_dir/bin/ndr2-sdl"
note "start it with  $here/ndr2 --seed 3 --fps"
note "or straight into a fight  $here/ndr2 --battle-scene --fps"

say "Checking the install"
# The window is pygame and the CRT is a shader; either one missing is an install
# that says green and then has no window, or none of its glass.
"$python" -c "import neverdeads_revenge" \
    || die "the game was installed but cannot be imported -- please report this."
"$python" -c "import miniaudio" \
    || die "miniaudio did not come along -- please report this. Manual fix:
       $venv_dir/bin/pip install 'miniaudio>=1.71'"

"$python" -c "import pygame" \
    || die "pygame-ce did not come along -- please report this. Manual fix:
       $venv_dir/bin/pip install 'pygame-ce>=2.5'"
"$python" -c "import moderngl" \
    || die "moderngl did not come along -- please report this. Manual fix:
       $venv_dir/bin/pip install 'moderngl>=5.13'"

want_desktop_ok=0

# -- menu entry -------------------------------------------------------------

if [[ "$want_desktop" == "yes" ]]; then
    say "Adding $name to your applications menu"
    mkdir -p "$launcher_dir" "$desktop_dir" "$icon_dir"

    # The game is windowed, so the desktop entry does not ask for a terminal --
    # it opens its own CRT fullscreen and keeps the keys inside it. What needs a
    # wrapper instead is the path: an Exec line cannot carry a folder name with
    # spaces in it, and $here is whereever the player unzipped this, so the
    # entry points at a spaceless launcher under the data home.
    cat > "$launcher_dir/launch.sh" <<WRAPPER
#!/usr/bin/env bash
exec "$here/ndr2" "\$@"
WRAPPER
    chmod +x "$launcher_dir/launch.sh"

    # The entry lives in assets/ rather than in a heredoc here, so it can be
    # read, diffed and validated like any other file.
    template="$here/assets/$slug.desktop.in"
    if [[ -f "$template" ]]; then
        sed -e "s|@NAME@|$name|g" \
            -e "s|@EXEC@|$launcher_dir/launch.sh|g" \
            -e "s|@SLUG@|$slug|g" \
            "$template" > "$desktop_dir/$slug.desktop"
    else
        warn "no desktop entry template at $template; skipping the menu entry"
    fi
    if [[ -f "$here/assets/$slug.svg" ]]; then
        cp "$here/assets/$slug.svg" "$icon_dir/$slug.svg"
    else
        warn "no icon at $here/assets/$slug.svg; the menu entry keeps an empty one"
    fi

    command -v update-desktop-database >/dev/null && update-desktop-database "$desktop_dir" 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -qtf "$data_home/icons/hicolor" 2>/dev/null || true
    want_desktop_ok=1
fi

# -- done -------------------------------------------------------------------

say "Done."
printf '\n  Play it now:      %s/ndr2\n' "$here"
if [[ $want_desktop_ok -eq 1 ]]; then
    printf '  Or from the menu: look for "%s" (it may take a moment to appear)\n' "$name"
elif [[ $is_macos -eq 1 ]]; then
    printf '  Tip: in Finder, right-click this folder and "Open Terminal",\n'
    printf '       then run ./ndr2 -- or drag this folder into the Dock.\n'
fi
printf '  To remove it:     %s/install.sh --uninstall\n\n' "$here"
