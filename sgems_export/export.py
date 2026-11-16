import math
import os
import re
import struct
from tempfile import NamedTemporaryFile

from qgis.core import (
    Qgis, NULL, QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterBoolean, QgsProcessingParameterEnum, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterFileDestination,

)


class Export(QgsProcessingAlgorithm):
    def name(self):
        return "exportpoints"

    def displayName(self):
        return "Export point set to SGeMS"

    def createInstance(self):
        return Export()

    def shortHelpString(self):
        return ("Use a projected point layer. X and Y use the layer coordinates. "
                "Choose geometry Z or an elevation field for 3D samples. "
                "Use the same units on all axes. Positive Z points up. "
                "For 2D, all points receive Z = 0. In SGeMS load the file as "
                "a GSLIB Point Set, choose columns 1/2/3 for X/Y/Z and set "
                "the no-data value to -99999.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            "INPUT", "Sample points (projected CRS)", [QgsProcessing.SourceType.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            "PROPS", "Measured properties", parentLayerParameterName="INPUT",
            type=QgsProcessingParameterField.DataType.Numeric, allowMultiple=True))
        self.addParameter(QgsProcessingParameterEnum(
            "MODE", "Vertical coordinate", ["2D (Z = 0)", "Geometry Z", "Elevation field"]))
        self.addParameter(QgsProcessingParameterField(
            "ELEV", "Elevation field (when chosen above)", parentLayerParameterName="INPUT",
            type=QgsProcessingParameterField.DataType.Numeric, optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            "RAW", "Use stored local model XY (matching XY and Z units)", defaultValue=False))
        self.addParameter(QgsProcessingParameterFileDestination(
            "OUTPUT", "GSLIB point set", "GSLIB data (*.dat)"))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, "INPUT", context)
        if source is None:
            raise QgsProcessingException("Choose a point layer.")
        crs = source.sourceCrs()
        raw = self.parameterAsBool(parameters, "RAW", context)
        if not raw and crs.type() not in (Qgis.CrsType.Projected, Qgis.CrsType.DerivedProjected):
            raise QgsProcessingException("Choose a projected layer, or enable stored local XY for a model grid.")
        props = self.parameterAsFields(parameters, "PROPS", context)
        elev = self.parameterAsString(parameters, "ELEV", context)
        mode = self.parameterAsEnum(parameters, "MODE", context)
        if not props or any(p not in source.fields().names() for p in props):
            raise QgsProcessingException("Choose at least one numeric property.")
        if mode == 2 and elev not in source.fields().names():
            raise QgsProcessingException("Choose the field containing sample elevations.")
        names = ["X", "Y", "Z"]
        for prop in props:
            base = re.sub(r"[^A-Za-z0-9_]+", "_", prop).strip("_") or "property"
            name = base
            suffix = 2
            while name.lower() in {n.lower() for n in names}:
                name = f"{base}_{suffix}"
                suffix += 1
            names.append(name)
            if name != prop:
                feedback.pushInfo(f"{prop} exported as {name}")
        dest = self.parameterAsFileOutput(parameters, "OUTPUT", context)
        temp = None
        count = 0
        total = source.featureCount()
        try:
            with NamedTemporaryFile(mode="w", encoding="ascii", newline="\n",
                                    dir=os.path.dirname(os.path.abspath(dest)),
                                    delete=False) as out:
                temp = out.name
                out.write("QGIS samples\n" + str(len(names)) + "\n" + "\n".join(names) + "\n")
                for index, feature in enumerate(source.getFeatures()):
                    if feedback.isCanceled():
                        raise QgsProcessingException("Export canceled.")
                    geom = feature.geometry()
                    if geom.isEmpty():
                        raise QgsProcessingException(f"Feature {feature.id()} has no location.")
                    values = []
                    for prop in props:
                        raw = feature[prop]
                        if raw is None or raw == NULL:
                            values.append("-99999")
                            continue
                        value = float(raw)
                        single = struct.unpack("f", struct.pack("f", value))[0]
                        if not math.isfinite(single) or single == -99999:
                            raise QgsProcessingException(f"Feature {feature.id()}: invalid or reserved value in {prop}.")
                        values.append(format(value, ".17g"))
                    for point in geom.vertices():
                        z = 0.0
                        if mode == 1:
                            z = point.z()
                        elif mode == 2:
                            raw = feature[elev]
                            z = math.nan if raw is None or raw == NULL else float(raw)
                        coords = (point.x(), point.y(), z)
                        if not all(math.isfinite(c) for c in coords):
                            raise QgsProcessingException(f"Feature {feature.id()} has a missing or invalid coordinate.")
                        out.write(" ".join([format(c, ".17g") for c in coords] + values) + "\n")
                        count += 1
                    if total > 0:
                        feedback.setProgress(100 * (index + 1) / total)
                if not count:
                    raise QgsProcessingException("The input contains no points.")
            if feedback.isCanceled():
                raise QgsProcessingException("Export canceled.")
            os.replace(temp, dest)
            temp = None
        finally:
            if temp is not None:
                os.unlink(temp)
        frame = "stored model XY" if raw else crs.authid()
        feedback.pushInfo(f"Exported {count} points in {frame}. In SGeMS use Point Set, X/Y/Z = 1/2/3, no-data = -99999.")
        return {"OUTPUT": dest}
