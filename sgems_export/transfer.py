from math import prod

import numpy as np
from qgis.PyQt.QtCore import QMetaType, QVariant
from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QGridLayout, QLabel, QSpinBox,
)
from qgis.core import (
    Qgis, QgsFeature, QgsField, QgsFields, QgsGeometry, QgsMemoryProviderUtils,
    QgsPoint,
)


def point_options(parent, names):
    dialog = QDialog(parent)
    dialog.setWindowTitle("SGeMS point-set columns")
    layout = QGridLayout(dialog)
    selectors = []
    upper = [name.upper() for name in names]
    for row, axis in enumerate("XYZ"):
        combo = QComboBox()
        combo.addItems(names)
        combo.setCurrentIndex(upper.index(axis) if axis in upper else row)
        selectors.append(combo)
        layout.addWidget(QLabel(axis + " coordinate"), row, 0)
        layout.addWidget(combo, row, 1)
    missing = QDoubleSpinBox()
    missing.setDecimals(9)
    missing.setRange(-1e30, 1e30)
    missing.setValue(-99999)
    layout.addWidget(QLabel("Missing property value"), 3, 0)
    layout.addWidget(missing, 3, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    def validate():
        indices = {combo.currentIndex() for combo in selectors}
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(len(indices) == 3)
    for combo in selectors:
        combo.currentIndexChanged.connect(validate)
    validate()
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons, 4, 0, 1, 2)
    if dialog.exec():
        return [combo.currentIndex() for combo in selectors], missing.value()


def grid_options(parent):
    dialog = QDialog(parent)
    dialog.setWindowTitle("SGeMS Cartesian grid geometry")
    layout = QGridLayout(dialog)
    layout.addWidget(QLabel("Enter the geometry from SGeMS. Use the centre of the first cell."), 0, 0, 1, 4)
    for column, title in enumerate(("Axis", "Nodes", "First centre", "Spacing")):
        layout.addWidget(QLabel(title), 1, column)
    axes = []
    for row, axis in enumerate("XYZ", 2):
        count = QSpinBox()
        count.setRange(1, 2147483647)
        origin, step = QDoubleSpinBox(), QDoubleSpinBox()
        for box in (origin, step):
            box.setDecimals(9)
            box.setRange(-1e12, 1e12)
        step.setMinimum(1e-9)
        step.setValue(1)
        axes.append((count, origin, step))
        for col, widget in enumerate((QLabel(axis), count, origin, step)):
            layout.addWidget(widget, row, col)
    missing = QDoubleSpinBox()
    missing.setDecimals(9)
    missing.setRange(-1e30, 1e30)
    missing.setValue(-99999)
    layout.addWidget(QLabel("Missing property value"), 5, 0, 1, 2)
    layout.addWidget(missing, 5, 2, 1, 2)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons, 6, 0, 1, 4)
    if dialog.exec():
        return tuple(tuple(box.value() for box in axis) for axis in axes), missing.value()


def grid_points(values, axes):
    counts, origins, steps = zip(*axes)
    if len(values) != prod(counts):
        raise ValueError(f"Grid dimensions require {prod(counts):,} rows. File has {len(values):,}.")
    index = np.arange(len(values))
    nx, ny, _ = counts
    indices = np.column_stack((index % nx, index // nx % ny, index // (nx * ny)))
    return np.column_stack((origins + indices * steps, values))


def point_layer(name, names, data, crs):
    fields = QgsFields()
    for column in names:
        try:
            field = QgsField(column, QMetaType.Type.Double)
        except TypeError:  # QGIS 3.34 uses the QVariant constructor.
            field = QgsField(column, QVariant.Double)
        if not fields.append(field):
            raise ValueError(f"QGIS could not create field {column}.")
    layer = QgsMemoryProviderUtils.createMemoryLayer(name, fields, Qgis.WkbType.PointZ, crs)
    if not layer or not layer.isValid():
        raise RuntimeError("QGIS could not create the point layer.")
    layer.setCrs(crs)
    provider = layer.dataProvider()
    for start in range(0, len(data), 1000):
        batch = []
        for row in data[start:start + 1000]:
            feature = QgsFeature(fields)
            feature.setGeometry(QgsGeometry(QgsPoint(*map(float, row[:3]))))
            feature.setAttributes([float(v) if np.isfinite(v) else None for v in row[3:]])
            batch.append(feature)
        if not provider.addFeatures(batch)[0]:
            raise RuntimeError("QGIS could not store all sample points.")
    layer.updateExtents()
    return layer
