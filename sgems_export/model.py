import os
import platform
import stat
import subprocess
import tempfile
from pathlib import Path
from statistics import NormalDist

import numpy as np
from qgis.core import QgsTask
from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QSpinBox,
)


def grid_axes(xyz, counts):
    bounds = np.array([xyz.min(axis=0), xyz.max(axis=0)])
    return [np.linspace(lo, hi, n) if lo != hi else np.array([lo])
            for lo, hi, n in zip(*bounds, counts)]


METHODS = {"ordinary": "Ordinary kriging", "sgsim": "SGSIM · sequential Gaussian simulation",
           "sisim": "SISIM · categorical sequential indicator simulation"}


def settings(parent, xyz, name, method="ordinary"):
    dialog = QDialog(parent)
    dialog.setWindowTitle(METHODS[method])
    form = QFormLayout(dialog)
    intro = QLabel(f"Estimate {name} across the sample bounding box. XYZ must use matching linear units. "
                   "Estimates may extend beyond the sample footprint. The model uses up to 16 nearest samples, "
                   "a spherical covariance, zero nugget and unit sill.")
    intro.setWordWrap(True)
    form.addRow(intro)
    spans = np.ptp(xyz, axis=0)
    radius = QDoubleSpinBox()
    radius.setDecimals(6)
    radius.setRange(0.000001, 1e12)
    radius.setValue(max(float(spans.max()) / 3, 0.000001))
    form.addRow("Variogram range (initial suggestion)", radius)
    counts = []
    for axis, span, default in zip("XYZ", spans, (20, 20, 5)):
        count = QSpinBox()
        count.setRange(2 if span else 1, 100 if span else 1)
        count.setValue(default if span else 1)
        form.addRow(f"{axis} grid nodes", count)
        counts.append(count)
    if method != "ordinary":
        seed = QSpinBox()
        seed.setRange(0, 2147483647)
        seed.setValue(12345)
        form.addRow("Random seed", seed)
        realizations = QSpinBox()
        realizations.setRange(1, 100)
        realizations.setValue(3)
        form.addRow("Realizations", realizations)
        explanation = ("Empirical normal scores, with back-transformed values bounded by the sample range."
                       if method == "sgsim" else "Integer facies codes, observed proportions and one shared indicator covariance.")
        detail = QLabel(explanation)
        detail.setWordWrap(True)
        form.addRow(detail)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    if dialog.exec():
        common = radius.value(), [c.value() for c in counts]
        return common if method == "ordinary" else (*common, seed.value(), realizations.value())


class KrigingTask(QgsTask):
    def __init__(self, samples, name, radius, counts, output, callback, method="ordinary", seed=12345, realizations=1):
        super().__init__("SGeMS Workbench · " + METHODS[method], QgsTask.CanCancel)
        self.method, self.seed, self.realizations = method, seed, realizations
        self.samples = samples
        self.name = name
        self.radius = radius
        self.counts = counts
        self.output = output
        self.callback = callback
        self.error = ""

    def run(self):
        try:
            return self.calculate()
        except (OSError, ValueError, RuntimeError) as error:
            self.error = str(error)
            return False

    def calculate(self):
        simulation = self.method != "ordinary"
        worker = "simulate" if simulation else "ordinary"
        binary = Path(__file__).parent / "engine" / (worker + "-linux-x86_64")
        if platform.system() != "Linux" or platform.machine().lower() not in ("x86_64", "amd64"):
            raise ValueError("This bundled solver requires 64-bit Intel or AMD Linux.")
        if not os.access(binary, os.X_OK):
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        # Zip installers can drop the executable bit.
        samples = np.unique(self.samples, axis=0)
        if len(np.unique(samples[:, :3], axis=0)) != len(samples):
            raise ValueError("Two observations have different values at identical XYZ. Resolve them before modelling.")
        axes = grid_axes(samples[:, :3], self.counts)
        nodes = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
        command = [str(binary)]
        columns = [f"{self.name}_estimate", "unit_sill_variance"]
        title = f"GsTL ordinary kriging, spherical range {self.radius:g}, unit sill, zero nugget"
        if simulation:
            command.extend([self.method, str(self.seed), str(self.realizations)])
            values, codes, frequencies = np.unique(samples[:, 3], return_inverse=True, return_counts=True)
            if len(values) < 2:
                raise ValueError("Simulation needs at least two different conditioning values.")
            if self.method == "sisim":
                if not np.equal(values, np.floor(values)).all():
                    raise ValueError("Choose an integer-coded categorical property for SISIM.")
                samples[:, 3] = codes
            else:
                ranks = (np.cumsum(frequencies) - frequencies / 2) / len(samples)
                scores = np.array([NormalDist().inv_cdf(float(p)) for p in ranks])
                samples[:, 3] = scores[codes]
            columns = [f"{self.name}_{self.method}_{i+1}" for i in range(self.realizations)]
            title = f"GsTL {self.method}, spherical range {self.radius:g}, zero nugget, seed {self.seed}"
        with tempfile.TemporaryDirectory() as temp:
            job = Path(temp)
            with (job / "in").open("w") as inp:
                inp.write(f"{self.radius:.17g} {len(samples)} {len(nodes)}\n")
                np.savetxt(inp, samples, fmt="%.17g")
                np.savetxt(inp, nodes, fmt="%.17g")
            with (job / "in").open("rb") as inp, (job / "out").open("wb") as out:
                with subprocess.Popen(command, stdin=inp, stdout=out) as proc:
                    while proc.poll() is None:
                        if self.isCanceled():
                            proc.terminate()
                            return False
                        try:
                            proc.wait(timeout=.12)
                        except subprocess.TimeoutExpired:
                            pass
                    if proc.returncode:
                        raise ValueError("The solver could not condition this grid. Check sample spacing and range.")
            estimates = np.loadtxt(job / "out", ndmin=2)
        if simulation:
            if estimates.size != len(nodes) * self.realizations or not np.isfinite(estimates).all():
                raise ValueError("Incomplete simulation output.")
            estimates = estimates.reshape(self.realizations, len(nodes)).T
            estimates = values[estimates.astype(int)] if self.method == "sisim" else np.interp(estimates, scores, values)
        if estimates.shape != (len(nodes), len(columns)) or not np.isfinite(estimates).all():
            raise ValueError("Solver returned incomplete estimates.")
        if np.any(estimates == -99999):
            raise ValueError("An estimate collides with the point-set missing value (-99999).")
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=Path(self.output).parent, delete=False) as out:
                tmp = out.name
                out.write(f"{title}\n{3 + len(columns)}\nX\nY\nZ\n" + "\n".join(columns) + "\n")
                np.savetxt(out, np.column_stack((nodes, estimates)), fmt="%.17g")
            if self.isCanceled():
                return False
            os.replace(tmp, self.output)
            tmp = None
        finally:
            if tmp:
                os.unlink(tmp)
        return True

    def finished(self, success):
        self.callback(success, self.output, self.error or "Kriging canceled.")
