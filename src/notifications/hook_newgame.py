from PyQt4 import QtCore
import util
import config
from config import Settings
from notifications.ns_hook import NsHook
import notifications as ns

"""
Settings for notifications: if a new game is hosted.
"""


class NsHookNewGame(NsHook):
    def __init__(self):
        NsHook.__init__(self, ns.Notifications.NEW_GAME)
        self.button.setEnabled(True)
        self.dialog = NewGameDialog(self, self.eventType)
        self.button.clicked.connect(self.dialog.show)

FormClass, BaseClass = util.load_ui_type("notification_system/new_game.ui")


class NewGameDialog(FormClass, BaseClass):
    def __init__(self, parent, event_type):
        BaseClass.__init__(self)
        self.parent = parent
        self.eventType = event_type
        self._settings_key = 'notifications/{}'.format(event_type)
        self.setupUi(self)
        self.mode = None

        # remove help button
        self.setWindowFlags(self.windowFlags() & (~QtCore.Qt.WindowContextHelpButtonHint))

        self.load_settings()

    def load_settings(self):
        self.mode = Settings.get(self._settings_key+'/mode', 'friends')

        self.checkBoxFriends.setCheckState(QtCore.Qt.Checked if self.mode == 'friends' else QtCore.Qt.Unchecked)
        self.parent.mode = self.mode

    def save_settings(self):
        config.Settings.set(self._settings_key+'/mode', self.mode)
        self.parent.mode = self.mode

    @QtCore.pyqtSlot()
    def on_btnSave_clicked(self):
        self.mode = 'friends' if self.checkBoxFriends.checkState() == QtCore.Qt.Checked else 'all'
        self.save_settings()
        self.hide()
