# The Android build

Everything Android lives here except one file: `main.py` sits at the repository
root, because p4a's SDL2 bootstrap runs `main.py` from the top of the source
directory it is handed, and that directory is the repository.

| file | what it is |
| --- | --- |
| `buildozer.spec` | the build: one architecture, landscape, one permission |
| `p4a-recipes/pygame_ce/` | the vendored recipe for pygame-ce (see its own notes) |
| `../../main.py` | the entry point p4a runs: `src` on the path, then the game's own `main()` |

Buildozer is run **from this directory**, so `.buildozer/` and `bin/` (both
ignored) land beside the spec. The build venv is made once -- p4a needs Python
3.11/3.12 and this game develops on 3.14, so the toolchain gets its own:

```sh
# once, with the toolchain's own Python
~/android-toolchain/python312/bin/python3.12 -m venv .venv-android
./.venv-android/bin/pip install -U pip wheel setuptools
./.venv-android/bin/pip install buildozer python-for-android 'cython<3.0'

# every build
cd packaging/android
. ~/android-toolchain/env.sh
export VIRTUAL_ENV="$PWD/../../.venv-android"
export PATH="$VIRTUAL_ENV/bin:$PATH"
buildozer android debug
```

`VIRTUAL_ENV` is not decoration: without it buildozer tries `pip install --user`,
which is illegal inside a virtualenv, and it cannot find Cython. The spec points
`android.sdk_path` and `android.ndk_path` at the toolchain itself -- buildozer
reads those from the spec only, never from `ANDROID_HOME`.

The result is `bin/neverdeads_revenge-<version>-arm64-v8a-debug.apk`, which
sideloads like any other APK (`adb install`, or copy it across and tap it).

## What the build does for a handheld

* **The grid is chosen, not inherited.** `ANDROID_PRIVATE` says which panel this
  is, and the grid aims at 64 columns instead of the desktop's 110. At 1240x1080
  that is **62x27 at scale 2** -- the original 960x540 design, doubled, pixel for
  pixel -- because ten-pixel characters on a dense four-inch screen are fine print.
* **The sidebar keeps its share of the width** (`sidebar_width`): at 62 columns it
  is 22 cells, and the map gets 40 instead of 28.
* **The glyphs are converted to the display's format** when they are cut
  (`font.py`), which is the difference between a blend and a blend plus a
  per-pixel conversion on an ARM build with no SIMD blitters.
* **The sound is SDL_mixer's** when there is no miniaudio (there is no Android
  wheel of it): `desktop/audio.py` picks the engine by what the machine has, and
  the APK's pygame already carries `libSDL2_mixer.so`.
* **The saves live in the app's own directory** (`ANDROID_PRIVATE`), not in a
  home directory a handheld does not have.
* **The pad is the game's own** (`sdl_front/pad.py`): the Android button numbers,
  the d-pad read as a hat, the stick, the repeats. There is no touch input, by
  design -- the panel is read, the buttons are played.

## What is not here yet

* **The CRT.** The desktop's glass is a moderngl shader; the APK takes the plain
  scaled blit. On a 620x540 buffer the shader would cost almost nothing, so this
  is a piece of work with a device to watch it on, not a missing capability.
* **The wake lock.** The permission is declared and nothing holds it yet: a screen
  that dims mid-fight is a screen a player taps. It needs pyjnius (p4a has the
  recipe) or a build-level switch.
* **Suspend and resume.** A run is saved on the floor's own terms; the app does
  not yet write it down when Android background it. On a device that may take the
  process away, that is the next thing to do.
* **A bench.** The desktop has `--timings`; on the phone the same lines go to
  `run.log` in the app's directory (`adb shell run-as ... cat files/run.log`), and
  that is the first thing to read on the device.

## The toolchain

It lives in `~/android-toolchain` and is **not** part of the repository: a JDK,
the Android command-line tools, platform 33 and build-tools, the NDK **25b**, a
build-only Python 3.12, and a `.venv-android` with buildozer, python-for-android
and `cython<3.0`. The spec points at it; nothing has to be exported by hand
except `env.sh` and `VIRTUAL_ENV` above.

## Traps, all of them paid for

* **`p4a.bootstrap`, not `android.bootstrap`** in the spec.
* **NDK 25b, not the newer one.** p4a's `recommendations.py` sets
  `MIN_NDK_VERSION = MAX_NDK_VERSION = 25`, so only a 25.x NDK is accepted.
* **buildozer 1.6 looks for `sdkmanager` under `$SDK/tools/bin`** (the old SDK
  layout) while the modern command-line tools install to
  `$SDK/cmdline-tools/latest`. A symlink bridges it:
  `ln -s cmdline-tools/latest ~/android-toolchain/sdk/tools`.
* **No ASCII apostrophe in the title.** p4a writes it into `strings.xml` and aapt
  reads it as a broken escape sequence; the spec uses U+2019.
* **`android.release_artifact = apk`** for a release build: the default is an
  `.aab`, which is a Play Store artifact nothing can sideload.
* **Cython and meson**, the two failures that shaped the vendored recipe -- both
  written down in `p4a-recipes/pygame_ce/__init__.py`. The recipe installs
  Cython 3.1 into the *host* Python (0.29 cannot compile against the 3.14 C API)
  and copies the `setup.py` build into the target's site-packages rather than
  asking meson to cross-compile.

## The release APK

`buildozer android release` makes an **unsigned** APK. Sign it once with a
keystore of your own:

```sh
BT=~/android-toolchain/sdk/build-tools/33.0.2
KS=~/android-toolchain/release.keystore        # keytool -genkeypair, once

"$BT/zipalign" -f 4 bin/*-release-unsigned.apk /tmp/aligned.apk
"$BT/apksigner" sign --ks "$KS" --ks-pass pass:ndr2-release \
    --key-pass pass:ndr2-release --ks-key-alias ndr2 \
    --out bin/neverdeads_revenge-release.apk /tmp/aligned.apk
"$BT/apksigner" verify --print-certs bin/*-release.apk
```
