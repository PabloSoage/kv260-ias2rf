"""
Where the external tools live, found the same way on every machine.

kicad-cli: $KICAD_CLI if set, else kicad-cli on PATH, else the KiCad 10 install
folders winget and the KiCad installer use (per user, then per machine).
The stock footprints sit next to it in the same install.

Set KICAD_CLI only when KiCad is somewhere else (an untracked mise.local.toml
[env] section is the place for it).
"""

import os
import shutil

_INSTALLS = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "KiCad", "10.0"),
             os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "KiCad", "10.0")]


def kicad_cli():
    if os.environ.get("KICAD_CLI"):
        return os.environ["KICAD_CLI"]
    found = shutil.which("kicad-cli")
    if found:
        return found
    for d in _INSTALLS:
        exe = os.path.join(d, "bin", "kicad-cli.exe")
        if os.path.isfile(exe):
            return exe
    raise SystemExit("kicad-cli not found: install KiCad 10 or set KICAD_CLI")


def stock_footprints():
    """The folder of KiCad's own .pretty libraries, with a trailing separator."""
    d = os.environ.get("KICAD10_FOOTPRINT_DIR")
    if not d:
        d = os.path.join(os.path.dirname(os.path.dirname(kicad_cli())), "share", "kicad", "footprints")
    return os.path.join(d, "")


KICAD_CLI = kicad_cli()
