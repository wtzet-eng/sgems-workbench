import os
import re
import shutil
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
from qgis.PyQt.QtCore import QProcess, QSettings, QTimer, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)


def load_samples(path):
    with open(path, encoding="utf-8-sig") as stream:
        stream.readline()
        columns = int(stream.readline())
        if not 4 <= columns <= 4096:
            raise ValueError("Select a point set with XYZ and at least one property.")
        names = [stream.readline().strip() for _ in range(columns)]
        if [n.upper() for n in names[:3]] != ["X", "Y", "Z"]:
            raise ValueError("Expected X, Y and Z as the first three columns.")
        properties = names[3:]
        if len(set(properties)) != len(properties) or any(
                not re.fullmatch(r"[A-Za-z0-9_]+", n) for n in properties):
            raise ValueError("Use unique property names containing letters, digits or underscores.")
        data = np.loadtxt(stream, ndmin=2)
    if not len(data) or data.shape[1] != columns or not np.isfinite(data[:, :3]).all():
        raise ValueError("Check the number of columns and sample coordinates.")
    data[:, 3:] = np.where(data[:, 3:] == -99999, np.nan, data[:, 3:])
    return properties, data


def write_vtk(path, properties, data):
    temp = None
    try:
        with NamedTemporaryFile(mode="w", encoding="ascii", delete=False,
                                dir=os.path.dirname(os.path.abspath(path))) as out:
            temp = out.name
            count = len(data)
            out.write('<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian"><PolyData>\n')
            out.write(f'<Piece NumberOfPoints="{count}" NumberOfVerts="{count}" '
                      'NumberOfLines="0" NumberOfStrips="0" NumberOfPolys="0">\n')
            out.write('<Points><DataArray type="Float64" NumberOfComponents="3" format="ascii">\n')
            np.savetxt(out, data[:, :3], fmt="%.17g")
            out.write('</DataArray></Points><Verts>\n')
            for name, start in (("connectivity", 0), ("offsets", 1)):
                out.write(f'<DataArray Name="{name}" type="Int64" format="ascii">\n')
                np.savetxt(out, np.arange(start, count + start), fmt="%d")
                out.write('</DataArray>\n')
            out.write(f'</Verts><PointData Scalars="{properties[0]}">\n')
            for index, name in enumerate(properties):
                out.write(f'<DataArray Name="{name}" type="Float64" format="ascii">\n')
                np.savetxt(out, data[:, index + 3], fmt="%.17g")
                out.write('</DataArray>\n')
            out.write('</PointData></Piece></PolyData></VTKFile>\n')
        os.replace(temp, path)
        temp = None
    finally:
        if temp:
            os.unlink(temp)


class Workbench(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SGeMS workbench")
        self.resize(740, 550)
        self.settings = QSettings()
        self.data = None
        self.canvas = None
        outer = QVBoxLayout(self)
        tabs = QTabWidget()
        outer.addWidget(tabs)
        self.status = QLabel()
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        for label in ("Sample points", "Applications"):
            widget = QWidget()
            tabs.addTab(widget, label)
            layout = QVBoxLayout(widget)
            if label == "Sample points":
                self.sample_layout = layout
            else:
                self.setup_layout = layout
        row = QHBoxLayout()
        self.sample_layout.addLayout(row)
        self.button(row, "Export QGIS points…", self.export)
        self.button(row, "Open point set…", self.open_data)
        self.property = QComboBox()
        self.property.currentIndexChanged.connect(self.draw)
        row.addWidget(self.property)
        from .model import METHODS
        self.method = QComboBox()
        for key, title in METHODS.items():
            self.method.addItem(title, key)
        self.sample_layout.addWidget(self.method)
        self.model_button = self.button(self.sample_layout, "Run selected algorithm…", self.model)
        self.model_button.setEnabled(False)
        self.task = None
        self.pv_button = self.button(self.sample_layout, "Save and open in ParaView…", self.paraview)
        self.pv_button.setEnabled(False)
        self.setup_layout.addWidget(QLabel("SGeMS setup"))
        if sys.platform.startswith("linux"):
            self.setup_layout.addWidget(QLabel("Select the native Linux sgems or s-gems executable."))
            self.button(self.setup_layout, "Linux build instructions", lambda:
                        QDesktopServices.openUrl(QUrl("https://github.com/gerwathome/sgems#readme")))
            self.button(self.setup_layout, "Locate native SGeMS…", self.choose_native)
        else:
            self.button(self.setup_layout, "1. Get official SGeMS installer", lambda:
                        QDesktopServices.openUrl(QUrl("https://sourceforge.net/projects/sgems/files/sgems/sgems-2.5Beta/")))
            self.button(self.setup_layout, "2. Run downloaded installer…", self.install)
            self.button(self.setup_layout, "3. Locate installed SGeMS…", lambda: self.locate("sgems"))
        self.button(self.setup_layout, "Launch SGeMS", self.launch_sgems)
        self.setup_layout.addWidget(QLabel("ParaView setup"))
        self.button(self.setup_layout, "Get ParaView", lambda:
                    QDesktopServices.openUrl(QUrl("https://www.paraview.org/download/")))
        self.button(self.setup_layout, "Locate installed ParaView…", lambda: self.locate("paraview"))
        self.setup_layout.addStretch()

    def button(self, layout, label, callback):
        button = QPushButton(label)
        layout.addWidget(button)
        button.clicked.connect(callback)
        return button

    def locate(self, app):
        path, _ = QFileDialog.getOpenFileName(self, f"Choose installed {app} executable")
        if path:
            self.settings.setValue("sgems_export/" + app, path)
            self.status.setText(f"Selected {path}")
        return path

    def executable(self, app):
        path = self.settings.value("sgems_export/" + app, "", type=str) or shutil.which(app)
        return path if path and os.path.isfile(path) else self.locate(app)

    def run_app(self, path, args):
        if not path:
            return
        if os.name != "nt" and path.lower().endswith(".exe"):
            wine = shutil.which("wine")
            if not wine:
                self.status.setText("This Windows executable requires Wine. On Ubuntu, install Wine in your software manager, then retry.")
                return
            args = [path] + args
            program = wine
        else:
            program = path
        ok, _ = QProcess.startDetached(program, args, str(Path(path).absolute().parent))
        self.status.setText("Launch requested. Check the application window." if ok else f"Could not start {program}.")

    def install(self):
        path, _ = QFileDialog.getOpenFileName(self, "Run the SGeMS installer you downloaded",
                                               str(Path.home() / "Downloads"), "Windows installer (*.exe)")
        self.run_app(path, [])

    def choose_native(self):
        from .native import native_binary
        path, _ = QFileDialog.getOpenFileName(self, "Select the native Linux sgems or s-gems binary")
        binary = native_binary(path)
        if binary:
            self.settings.setValue("sgems_export/linux_binary", str(binary))
            self.status.setText(f"Selected {binary}")
        elif path:
            self.status.setText("Select an executable Linux ELF binary from the SGeMS installation.")
        return binary

    def launch_sgems(self):
        if sys.platform.startswith("linux"):
            from .native import discover, start_native
            binary = discover(self.settings.value("sgems_export/linux_binary", "", type=str))
            if not binary:
                self.status.setText("A native Linux SGeMS installation is required. Choose its binary or see Linux build instructions.")
                binary = self.choose_native()
            if binary:
                try:
                    pid, log = start_native(binary)
                except OSError as error:
                    self.status.setText(f"Could not launch {binary}: {error}")
                    return
                self.status.setText(f"Started {binary.name}. Startup log: {log}")
                def check():
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        self.status.setText(f"SGeMS closed after launch. Check the startup log: {log}")
                QTimer.singleShot(1500, check)
            return
        self.run_app(self.executable("sgems"), [])

    def export(self):
        import processing
        result = processing.execAlgorithmDialog("sgems:exportpoints")
        if isinstance(result, dict) and result.get("OUTPUT"):
            self.read(result["OUTPUT"])

    def open_data(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open SGeMS point set", "", "Point set (*.dat *.gslib);;All files (*)")
        if path:
            self.read(path)

    def read(self, path):
        try:
            names, data = load_samples(path)
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        self.source_path = Path(path).resolve()
        self.names, self.data = names, data
        self.model_button.setEnabled(self.task is None)
        self.property.blockSignals(True)
        self.property.clear()
        self.property.addItems(names)
        self.property.blockSignals(False)
        self.pv_button.setEnabled(True)
        self.status.setText(f"{Path(path).name} · {len(data):,} samples. Drag the preview to rotate.")
        self.draw()

    def draw(self, *_):
        if self.data is None:
            return
        if self.canvas is None:
            try:
                from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
                from matplotlib.figure import Figure
                self.canvas = FigureCanvasQTAgg(Figure())
            except ImportError:
                self.status.setText("The embedded preview requires Matplotlib. ParaView export is available.")
                return
            self.sample_layout.insertWidget(1, self.canvas, 1)
        fig = self.canvas.figure
        fig.clear()
        ax = fig.add_subplot(111, projection="3d")
        i = self.property.currentIndex()
        values = self.data[:, i + 3]
        known = np.isfinite(values)
        if known.any():
            scatter = ax.scatter(*self.data[known, :3].T, c=values[known], cmap="viridis")
            fig.colorbar(scatter, ax=ax, label=self.names[i], shrink=.65)
        if not known.all():
            ax.scatter(*self.data[~known, :3].T, color="grey", label="No data")
            ax.legend()
        ax.set(xlabel="X", ylabel="Y", zlabel="Z")
        spans = np.ptp(self.data[:, :3], axis=0)
        ax.set_box_aspect(np.maximum(spans, max(float(max(spans)), 1) * .015))
        self.canvas.draw_idle()

    def model(self):
        from qgis.core import QgsApplication
        from .model import KrigingTask, settings
        i = self.property.currentIndex()
        samples = self.data[:, [0, 1, 2, i+3]]
        samples = samples[np.isfinite(samples[:, 3])]
        if len(np.unique(samples[:, :3], axis=0)) < 2:
            self.status.setText("Choose a property with values at two or more distinct locations.")
            return
        name = self.names[i]
        method = self.method.currentData()
        options = settings(self, samples[:, :3], name, method)
        if options is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save estimated grid points", f"{name}_{method}.dat", "Point set (*.dat)")
        if not path:
            return
        if Path(path).resolve() == self.source_path:
            self.status.setText("Choose a separate output file to preserve your input samples.")
            return
        radius, counts, *simulation = options
        self.task = KrigingTask(samples, name, radius, counts, path, self.model_finished, method, *simulation)
        self.model_button.setEnabled(False)
        self.status.setText("Running the selected algorithm. You can cancel in QGIS Background Tasks.")
        QgsApplication.taskManager().addTask(self.task)

    def model_finished(self, success, path, message):
        self.task = None
        self.model_button.setEnabled(True)
        if success:
            self.read(path)
        else:
            self.status.setText(message)

    def paraview(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save ParaView point set", "samples.vtp", "VTK XML PolyData (*.vtp)")
        if path:
            try:
                write_vtk(path, self.names, self.data)
            except (ValueError, OSError) as error:
                self.status.setText(str(error))
                return
            self.status.setText(f"Saved {path}")
            self.run_app(self.executable("paraview"), [os.path.abspath(path)])
