[app]

# The game, as Android sees it.
#
# The title uses a typographic apostrophe (U+2019) and not the ASCII one: p4a
# writes this line straight into strings.xml, and aapt reads an unescaped ASCII
# apostrophe as a broken escape sequence and refuses to build the APK. U+2019 is
# not that character, so it passes -- and the launcher shows the same words.
title = Neverdead’s Revenge
package.name = neverdeads_revenge
package.domain = org.darknoxx

# The source directory is the *repository*, because the game is a package under
# src/ and p4a wants one directory to hand to the bootstrap. `main.py` at the top
# of it is the entry point -- it has to be there and not here, see the file's own
# note -- and everything below is relative to that directory.
source.dir = ../..
source.include_exts = py,png,wav,ttf
# Everything the game reads at runtime travels with it: the sounds, the face, the
# sprites, the flagstones and the painting. They are all inside the package, so
# the extension list above is what carries them -- the pattern below is the belt
# to that pair of braces, and it is the list the wheel names too.
source.include_patterns = src/neverdeads_revenge/sounds/*.wav,src/neverdeads_revenge/desktop/fonts/*.ttf,src/neverdeads_revenge/desktop/sprites/**/*.png,src/neverdeads_revenge/desktop/tiles/*.png,src/neverdeads_revenge/desktop/backdrops/*.png
# Not shipped: the suite, the tools, the other platform's packaging, the docs, and
# the things a build would only carry to be carried. The byte-code caches need no
# line of their own -- they hold `.pyc` and nothing else, and the extension list
# above already leaves those behind.
source.exclude_dirs = tests,tools,docs,packaging,.venv,.venv-android,.git,.buildozer,__pycache__
source.exclude_patterns = *.md,LICENSE,install.sh,pyproject.toml

# One source of truth for the version: the number in pyproject.toml, which is the
# number the release tag carries. Two files that both say "0.5.3" are two files
# that disagree by the next release.
version.regex = version = "([0-9.]+)"
version.filename = %(source.dir)s/pyproject.toml

# pygame_ce is the vendored recipe in p4a-recipes/ (see that file for why it is
# not p4a's own pygame, which is upstream 2.1.0). The SDL2 bootstrap is what
# pygame needs and what buildozer would pick anyway; said out loud so the build
# does not depend on a default.
requirements = python3,pygame_ce
p4a.bootstrap = sdl2
p4a.local_recipes = p4a-recipes

# The device is 1240x1080 -- wider than tall, so landscape -- and the game draws
# its own frame centred inside whatever it is given, so full screen is right.
# (p4a appends `.Fullscreen` to the app theme itself when fullscreen is on, so the
# default Theme.NoTitleBar becomes Theme.NoTitleBar.Fullscreen; setting the theme
# by hand here would double the suffix and aapt would reject it.)
orientation = landscape
fullscreen = 1

# The wake lock is the one permission the game asks for: it keeps the panel lit
# while a fight is on. Nothing else is needed -- no network, no storage beyond the
# app's own sandbox, no location.
android.permissions = WAKE_LOCK

# A 64-bit Snapdragon 865, so one architecture is enough.
android.archs = arm64-v8a
android.api = 33
android.minapi = 24
android.ndk = 25b

# Where this machine keeps the SDK and NDK (see README.md in this directory for
# how they got there). buildozer's own default is under ~/.buildozer, which is
# empty; these point it at the toolchain that was installed. The paths are the
# one machine-local thing in this file.
android.sdk_path = ~/android-toolchain/sdk
android.ndk_path = ~/android-toolchain/sdk/ndk/android-ndk-r25b

# The SDK and NDK are already installed and their licences accepted there; do not
# let buildozer try to re-download or re-ask on every build.
android.accept_sdk_license = True
android.skip_update = True

[buildozer]
log_level = 1
warn_on_root = 1
