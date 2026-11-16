from qgis.core import QgsApplication, QgsProcessingProvider
from .export import Export
from qgis.PyQt.QtWidgets import QAction


class Provider(QgsProcessingProvider):
    def id(self):
        return "sgems"

    def name(self):
        return "SGeMS"

    def loadAlgorithms(self):
        self.addAlgorithm(Export())


class Plugin:
    def __init__(self, iface):
        self.iface = iface
        self.window = None
        self.provider = Provider()

    def initGui(self):
        QgsApplication.processingRegistry().addProvider(self.provider)

        if self.iface:
            self.action = QAction("SGeMS workbench…", self.iface.mainWindow())
            self.action.triggered.connect(self.open_workbench)
            self.iface.addPluginToMenu("SGeMS", self.action)

    def open_workbench(self):
        from .workbench import Workbench
        if self.window is None:
            self.window = Workbench(self.iface.mainWindow())
        self.window.show()
        self.window.raise_()

    def unload(self):
        if self.iface:
            self.iface.removePluginMenu("SGeMS", self.action)
            self.action.deleteLater()
        if self.window:
            if self.window.task:
                self.window.task.callback = lambda *_: None
                self.window.task.cancel()
            self.window.close()
            self.window.deleteLater()
        QgsApplication.processingRegistry().removeProvider(self.provider)
