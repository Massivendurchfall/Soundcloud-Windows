import subprocess
import sys
import os
import urllib.request
import shutil

ICON_URL  = "https://images.icon-icons.com/1109/PNG/512/1486053626-soundcloud_79184.png"
ICON_PNG  = "soundcloud.png"
ICON_ICO  = "soundcloud.ico"
MAIN_FILE = "main.py"
APP_NAME  = "SoundCloud"


def download_icon():
    if not os.path.exists(ICON_PNG):
        print(f"Downloading icon ...")
        req = urllib.request.Request(
            ICON_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req) as response:
            with open(ICON_PNG, "wb") as f:
                f.write(response.read())
        print("Icon downloaded.")
    else:
        print("Icon already present, skipping download.")


def convert_to_ico():
    try:
        from PIL import Image
    except ImportError:
        print("Installing Pillow...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "Pillow"])
        from PIL import Image
    try:
        img = Image.open(ICON_PNG).convert("RGBA")
        sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
        img.save(ICON_ICO, format="ICO", sizes=sizes)
        print(f"Converted {ICON_PNG} -> {ICON_ICO}")
        return True
    except Exception as e:
        print(f"ICO conversion failed: {e}")
        return False


def ensure_pyinstaller():
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "pyinstaller"])


def find_qtwebengine_binaries():
    """Findet den Pfad zu den QtWebEngine-Prozess-Binaries die PyInstaller nicht automatisch findet."""
    extras = []
    try:
        import PyQt6
        qt_dir = os.path.dirname(PyQt6.__file__)

        # QtWebEngineProcess.exe + alle .pak / .dat / icudtl.dat Dateien
        webengine_dir = os.path.join(qt_dir, "Qt6", "bin")
        process_exe   = os.path.join(webengine_dir, "QtWebEngineProcess.exe")
        if os.path.exists(process_exe):
            extras += [f"--add-binary={process_exe};PyQt6/Qt6/bin"]

        # Resources (pak-Dateien, icudtl.dat, etc.)
        resources_dir = os.path.join(qt_dir, "Qt6", "resources")
        if os.path.exists(resources_dir):
            extras += [f"--add-data={resources_dir};PyQt6/Qt6/resources"]

        # Translations
        translations_dir = os.path.join(qt_dir, "Qt6", "translations")
        if os.path.exists(translations_dir):
            extras += [f"--add-data={translations_dir};PyQt6/Qt6/translations"]

        # WebEngine-spezifische Resources
        webengine_res = os.path.join(qt_dir, "Qt6", "bin", "QtWebEngineProcess.exe")
        locales_dir   = os.path.join(qt_dir, "Qt6", "bin", "locales")
        if os.path.exists(locales_dir):
            extras += [f"--add-data={locales_dir};PyQt6/Qt6/bin/locales"]

    except Exception as e:
        print(f"Warning: Could not locate QtWebEngine binaries: {e}")
    return extras


def build():
    ensure_pyinstaller()
    download_icon()
    has_ico = convert_to_ico()

    icon_arg = ICON_ICO if has_ico and os.path.exists(ICON_ICO) else ICON_PNG

    qt_extras = find_qtwebengine_binaries()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",          # onedir statt onefile — QtWebEngine braucht externe Prozess-Binaries
        "--windowed",
        f"--name={APP_NAME}",
        f"--icon={icon_arg}",
        f"--add-data={ICON_PNG};.",   # Icon ins Root der .exe
        # Versteckte Imports die PyInstaller oft übersieht
        "--hidden-import=PyQt6.QtWebEngineWidgets",
        "--hidden-import=PyQt6.QtWebEngineCore",
        "--hidden-import=PyQt6.QtWebChannel",
        "--hidden-import=PyQt6.QtNetwork",
        "--hidden-import=pypresence",
    ] + qt_extras + [MAIN_FILE]

    print("\nRunning PyInstaller...")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        dist_dir = os.path.join("dist", APP_NAME)
        exe      = os.path.join(dist_dir, f"{APP_NAME}.exe")
        print(f"\nBuild successful!")
        print(f"Executable: {exe}")

        # Icon in dist-Ordner kopieren (für Tray)
        if os.path.exists(ICON_PNG):
            shutil.copy(ICON_PNG, os.path.join(dist_dir, ICON_PNG))
            print(f"Copied {ICON_PNG} to {dist_dir}/")

        print(f"\nZum Starten: {exe}")
        print(f"Zum Verteilen: den ganzen Ordner '{dist_dir}' weitergeben.")
    else:
        print("\nBuild failed.")
        sys.exit(1)


if __name__ == "__main__":
    build()
