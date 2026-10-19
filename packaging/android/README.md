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
ignored) land beside the spec rather than in the repository root. The build venv
is made once -- p4a needs Python 3.11/3.12 and this game develops on 3.14, so the
toolchain gets its own:

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

## The toolchain

It lives in `~/android-toolchain` and is **not** part of the repository: a JDK, the
Android command-line tools, platform 33 and build-tools, the NDK **25b**, a
build-only Python 3.12, and a `.venv-android` with buildozer, python-for-android
and `cython<3.0`.

The long version -- every URL, every published hash and the one honest correction
about how Google's XML lists its checksums -- is in the handheld fork's
`docs/ANDROID.md`, which is where the toolchain was first installed. What matters
here is that it is already on this machine and the spec points at it.

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
  written down in `p4a-recipes/pygame_ce/__init__.py`.

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

## What is in it

* **the pad.** `src/neverdeads_revenge/sdl_front/pad.py`: the Android button
  numbers, the d-pad read as a hat *and* as four buttons, the stick never walked
  with, and the repeat streams a pad does not send by itself. The bench shows every
  axis, button and hat raw beside the game's own name for each -- reachable from
  the pause menu (there is no command line on a handheld) and from `--sniff`.
* **the canvas.** A handheld *chooses* its grid instead of deriving it from the
  window: the screen, a face size (`--zoom S|M|L`, `M` by default on Android) and
  the cells the two make. At the device's own screen, `M` is 62x26 at a 34-pixel
  face -- the same twenty-seven-ish rows as the desktop, and the painting shown at
  1.025 of its own size rather than 1.4.
* **the art's own scale.** The sprites, the shadows and the bars are drawn at a
  whole multiple of the cell's own ratio (2 on the handheld, 1 on a desktop), so a
  figure's footprint in cells -- and with it the composition -- is the same on both.
* **the face without freetype**, the phone's **save directory**
  (`ANDROID_PRIVATE`), the **lifecycle** (a run is written down when the app goes to
  the background and the process may be taken away) and the **keyboard**, which a
  phone has to be asked for.

## What is not here yet

Honest list, so this APK is not mistaken for a finished one:

* **the sound.** The game plays through `miniaudio`, which has no p4a recipe, so on
  a handheld it is silent -- gracefully: the audio layer already treats a missing
  library as a silent machine rather than a broken one. The handheld fork's answer
  was SDL_mixer, which is *already* built into this APK (`libSDL2_mixer.so` is in
  it), so this is a third backend behind the seam that exists and not a new build.
* **the CRT.** The desktop's glass is a moderngl shader; this APK takes the plain
  software path (a scaled blit, no scanlines). The handheld fork's answer was a
  coarse scanline every third row, drawn by the GPU where there is one and baked
  into the frame where there is not.
* **the wake lock.** The permission is declared and nothing holds it yet: a screen
  that dims mid-fight is a screen a player taps. It needs pyjnius (p4a has the
  recipe) or a build-level switch, and it is a small piece of work with a device to
  watch it on.
* **what only the device can say.** The pad mapping was written from SDL's Android
  numbering and from a bench, not from this exact unit: the bench is the first thing
  to open on the handheld, and it says in one line what each button sends.

## The toolchain

It lives in `~/android-toolchain` and is **not** part of the repository: a JDK, the
Android command-line tools, platform 33 and build-tools, the NDK **25b**, a
build-only Python 3.12, and a `.venv-android` with buildozer, python-for-android
and `cython<3.0`.

The long version -- every URL, every published hash and the one honest correction
about how Google's XML lists its checksums -- is in the handheld fork's
`docs/ANDROID.md`, which is where the toolchain was first installed. What matters
here is that it is already on this machine and the spec points at it.

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
  written down in `p4a-recipes/pygame_ce/__init__.py`.

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

## What is not here yet

Honest list, so the first APK is not mistaken for a finished one:

* **the face, without freetype -- and this one is a *boot* blocker.** The Android
  pygame build leaves `pygame.freetype` out (its `Setup.Android.SDL2.in` comments
  the module out) and the game's font module imports it at import time, so an APK
  built from this branch today would close as soon as it opened. The handheld fork
  rendered with `pygame.font` instead, and the four DejaVu faces it needs already
  ship in this repository; that backend is the next piece of work, not an optional
  extra.
* **the grid for the device.** The canvas is derived from the window today, which
  on a 1240x1080 screen lands on 124x54 cells -- figures at half their relative
  size and the painting cropped to 46%. The handheld's own grid is about 65x28 (the
  same twenty-seven-ish rows as the desktop, at the device's own resolution), and
  two narrow-grid repairs that it needed are already in: the ORDER strip keeps its
  cells and the prologue wraps instead of cutting.
* **the art's own scale.** The sprites are installed at the size they are drawn
  for a 960x540 frame, and a frame at the device's resolution is twice that: the
  same ghoul is half its relative size. It is the same insight the handheld fork
  used for its map zoom, and it needs one factor -- derived from the cell -- for
  the sprites, the shadows and the bars.
* **the sound.** The game plays through `miniaudio`, which has no p4a recipe; the
  handheld fork's answer was SDL_mixer, which is already built into this APK's
  pygame -- it needs the third backend behind `desktop/audio.py`'s existing seam.
* **the phone's own plumbing**: the save directory on Android, the wake lock, and
  pause/resume when the app goes to the background.
* **the pad.** Done, and in this branch: see `src/neverdeads_revenge/sdl_front/pad.py`
  and the bench (`--sniff`, or the pause menu whenever a pad is plugged in).
