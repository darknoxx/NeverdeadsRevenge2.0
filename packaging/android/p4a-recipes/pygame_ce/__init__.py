"""A python-for-android recipe for pygame-ce.

python-for-android ships a recipe for upstream pygame, pinned at 2.1.0 -- older
than the pygame-ce this game is built against, and a different project. But
pygame-ce is a fork with the same build system: at its 2.5.8 tag it still carries
its own ``buildconfig/Setup.Android.SDL2.in``, which is the one thing a pygame
Android recipe actually needs from the source tree. (Its ``main`` branch has moved
to meson; the tag has not.) So this is the upstream recipe pointed at the fork,
which is all a recipe for a fork should be.

It lives here, vendored, rather than patched into p4a, so that the version this
game builds against is the version written in this file and not whatever p4a
happens to ship. buildozer finds it through ``p4a.local_recipes``.

Two things in here are not in p4a's recipe, and both of them were found the hard
way -- by a build that failed:

* **Cython 3.1 in the *host* Python.** pygame-ce builds from ``.pyx`` sources, so
  the host Python that runs ``setup.py`` needs Cython -- and p4a 2026.05 pins its
  own Cython recipe at 0.29.36, which cannot compile against the 3.14 C-API
  (``_PyLong_AsByteArray`` gained an argument). ``hostpython_prerequisites`` is
  the mechanism kivy's own recipe uses to install a build tool into the host
  Python; p4a's cython recipe is then never built and its version never comes up.
* **``install_python_package`` overridden.** pygame-ce's ``pyproject.toml`` names
  meson-python as its build backend, and meson will not cross-compile a Python
  extension this way: its sanity check compiles a program for Android and then
  tries to *run* it on the build machine ("binary or interpreter not
  executable"). The ``setup.py`` build p4a already drives works, so this copies
  its output into the target site-packages instead of asking pip -- and so meson
  -- a second time.

This recipe is the one that produced the handheld fork's APK, and it is carried
here unchanged apart from the notes: it is known to work with p4a 2026.05.09, the
NDK 25b, and the Python 3.14.2 that p4a builds.
"""

from os.path import join

import sh

from pythonforandroid.logger import info, shprint
from pythonforandroid.recipe import CompiledComponentsPythonRecipe
from pythonforandroid.toolchain import current_directory
from pythonforandroid.util import ensure_dir

__all__ = ["PygameCeRecipe"]


class PygameCeRecipe(CompiledComponentsPythonRecipe):
    """Builds pygame-ce from source for Android, against p4a's own SDL2."""

    name = "pygame_ce"
    version = "2.5.8"
    url = (
        "https://github.com/pygame-community/pygame-ce/archive/refs/tags/"
        "{version}.tar.gz"
    )
    #: pygame-ce installs the ``pygame`` package -- the import name is the whole
    #: point of it being a drop-in replacement -- so this is what the app imports.
    site_packages_name = "pygame"

    depends = [
        "sdl2",
        "sdl2_image",
        "sdl2_mixer",
        "sdl2_ttf",
        "setuptools",
        "jpeg",
        "png",
    ]

    #: pygame-ce builds from .pyx sources, so the *host* Python that runs
    #: setup.py needs Cython -- and this is how p4a installs a build tool into the
    #: host Python (kivy's recipe does the same). 3.1 is not a preference: p4a
    #: 2026.05 builds the target Python as 3.14, and Cython below 3.1 cannot
    #: compile against the 3.14 C-API, which is what p4a's own cython recipe is
    #: pinned to.
    #:
    #: ``setuptools`` is here for a smaller reason with a louder failure: Python
    #: 3.12 does not bundle it any more, and p4a's host Python is built from
    #: source without it, so ``setup.py`` -- the first line of it, ``from
    #: setuptools import setup`` -- dies with ModuleNotFoundError. The target's
    #: setuptools (in the recipe's ``depends``) does not help the host, which is
    #: the one that runs setup.py.
    hostpython_prerequisites = ["cython==3.1.3", "setuptools"]
    call_hostpython_via_targetpython = False  # because of setuptools
    install_in_hostpython = False

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        with current_directory(self.get_build_dir(arch.arch)):
            setup_template = open(
                join("buildconfig", "Setup.Android.SDL2.in")
            ).read()
            env = self.get_recipe_env(arch)
            env["ANDROID_ROOT"] = join(self.ctx.ndk.sysroot, "usr")

            png = self.get_recipe("png", self.ctx)
            png_lib_dir = join(png.get_build_dir(arch.arch), ".libs")
            png_inc_dir = png.get_build_dir(arch)

            jpeg = self.get_recipe("jpeg", self.ctx)
            jpeg_inc_dir = jpeg_lib_dir = jpeg.get_build_dir(arch.arch)

            sdl_mixer_includes = ""
            sdl2_mixer_recipe = self.get_recipe("sdl2_mixer", self.ctx)
            for include_dir in sdl2_mixer_recipe.get_include_dirs(arch):
                sdl_mixer_includes += f"-I{include_dir} "

            sdl2_image_includes = ""
            sdl2_image_recipe = self.get_recipe("sdl2_image", self.ctx)
            for include_dir in sdl2_image_recipe.get_include_dirs(arch):
                sdl2_image_includes += f"-I{include_dir} "

            setup_file = setup_template.format(
                sdl_includes=(
                    " -I"
                    + join(self.ctx.bootstrap.build_dir, "jni", "SDL", "include")
                    + " -L"
                    + join(self.ctx.bootstrap.build_dir, "libs", str(arch))
                    + " -L"
                    + png_lib_dir
                    + " -L"
                    + jpeg_lib_dir
                    + " -L"
                    + arch.ndk_lib_dir_versioned
                ),
                sdl_ttf_includes="-I"
                + join(self.ctx.bootstrap.build_dir, "jni", "SDL2_ttf"),
                sdl_image_includes=sdl2_image_includes,
                sdl_mixer_includes=sdl_mixer_includes,
                jpeg_includes="-I" + jpeg_inc_dir,
                png_includes="-I" + png_inc_dir,
                freetype_includes="",
            )
            open("Setup", "w").write(setup_file)

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env["USE_SDL2"] = "1"
        env["PYGAME_CROSS_COMPILE"] = "TRUE"
        env["PYGAME_ANDROID"] = "TRUE"
        return env

    def install_python_package(self, arch, name=None, env=None, is_dir=True):
        """Install what setup.py built, instead of asking pip (and so meson).

        pygame-ce's pyproject.toml names meson-python as its build backend, and
        meson will not cross-compile a Python extension this way: its sanity check
        compiles a program for Android and then tries to *run* it on the build
        machine, which fails as "binary or interpreter not executable". But the
        setup.py build that p4a already drives -- the same one upstream pygame
        used -- works, so this copies its output straight into the target
        site-packages rather than rebuilding through meson.
        """
        import glob
        import shutil

        if env is None:
            env = self.get_recipe_env(arch)
        info("Installing {} into site-packages".format(self.name))
        target = self.ctx.get_python_install_dir(arch.arch)
        ensure_dir(target)
        hostpython = sh.Command(self.hostpython_location)
        with current_directory(self.get_build_dir(arch.arch)):
            shprint(hostpython, "setup.py", "build", "-v", _env=env)
            built = glob.glob("build/lib.*")[0]
            shutil.copytree(built, target, dirs_exist_ok=True)


recipe = PygameCeRecipe()
