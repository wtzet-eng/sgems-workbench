import os
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from qgis.PyQt.QtCore import QProcess, QProcessEnvironment


def native_binary(candidate):
    if not candidate:
        return None
    path = Path(candidate).expanduser()
    try:
        if path.is_file() and os.access(path, os.X_OK):
            with path.open("rb") as file:
                if file.read(4) == b"\x7fELF":
                    return path.resolve()
    except OSError:
        return None
    return None


def discover(saved):
    candidates = [saved]
    for key in ("GSTLAPPLIHOME", "GSTLAPPLI_HOME"):
        if os.environ.get(key):
            candidates.extend(Path(os.environ[key]) / "bin/linux" / n for n in ("sgems", "s-gems"))
    candidates.extend(shutil.which(n) for n in ("sgems", "s-gems"))
    for candidate in candidates:
        binary = native_binary(candidate)
        if binary:
            return binary
    return None


def start_native(binary):
    binary = native_binary(binary)
    if binary is None:
        raise OSError("Choose an executable Linux SGeMS binary.")
    env = QProcessEnvironment.systemEnvironment()
    directory = binary.parent
    if directory.name == "linux" and directory.parent.name == "bin":
        root = directory.parent.parent
        env.insert("GSTLAPPLIHOME", str(root) + "/")
        env.insert("GSTLAPPLI_HOME", str(root))
        libraries = [str(p) for p in (root / "lib/linux", root / "plugins/designer") if p.is_dir()]
        if env.value("LD_LIBRARY_PATH"):
            libraries.append(env.value("LD_LIBRARY_PATH"))
        if libraries:
            env.insert("LD_LIBRARY_PATH", os.pathsep.join(libraries))
        directory = root
    log_dir = Path.home() / ".cache/sgems-workbench"
    log_dir.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix="launch-", suffix=".log", dir=log_dir, delete=False) as log:
        process = QProcess()
        process.setProgram(str(binary))
        process.setWorkingDirectory(str(directory))
        process.setProcessEnvironment(env)
        process.setStandardInputFile(QProcess.nullDevice())
        process.setStandardOutputFile(log.name)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        started, pid = process.startDetached()
        if not started:
            raise OSError(process.errorString())
        return pid, log.name
