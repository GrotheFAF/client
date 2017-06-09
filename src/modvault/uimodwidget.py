
from PyQt4 import QtCore, QtGui

import modvault
import util
import client

FormClass, BaseClass = util.load_ui_type("modvault/uimod.ui")


class UIModWidget(FormClass, BaseClass):
    FORMATTER_UIMOD = util.readfile("modvault/uimod.qthtml")

    def __init__(self, *args, **kwargs):
        BaseClass.__init__(self, *args, **kwargs)

        self.setupUi(self)

        self.setStyleSheet(client.instance.styleSheet())
        
        self.setWindowTitle("Ui Mod Manager")

        self.doneButton.clicked.connect(self.done_clicked)
        self.modList.itemEntered.connect(self.hover_over)
        allmods = modvault.get_installed_mods()
        self.uimods = {}
        for mod in allmods:
            if mod.ui_only:
                self.uimods[mod.totalname] = mod
                self.modList.addItem(mod.totalname)

        names = [mod.totalname for mod in modvault.get_active_mods(uimods=True)]
        for name in names:
            l = self.modList.findItems(name, QtCore.Qt.MatchExactly)
            if l:
                l[0].setSelected(True)

        if len(self.uimods) != 0:
            self.hover_over(self.modList.item(0))

    @QtCore.pyqtSlot()
    def done_clicked(self):
        selected_mods = [self.uimods[str(item.text())] for item in self.modList.selectedItems()]
        success = modvault.set_active_mods(selected_mods, False)
        if not success:
            QtGui.QMessageBox.information(None, "Error", "Could not set the active UI mods. Maybe something is wrong "
                                                         "with your game.prefs file. Please send your log.",
                                          QtGui.QMessageBox.Ok)
        self.done(1)

    @QtCore.pyqtSlot(QtGui.QListWidgetItem)
    def hover_over(self, item):
        mod = self.uimods[str(item.text())]
        self.modInfo.setText(self.FORMATTER_UIMOD.format(name=mod.totalname, description=mod.description))
