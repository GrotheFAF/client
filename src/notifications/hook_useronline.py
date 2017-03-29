from PyQt4 import QtCore
import util
from config import Settings
from notifications.ns_hook import NsHook
import notifications as ns

"""
Settings for notifications: if a player comes online
"""


class NsHookUserOnline(NsHook):
    def __init__(self):
        NsHook.__init__(self, ns.Notifications.USER_ONLINE)
        self.button.setEnabled(True)
        self.dialog = UserOnlineDialog(self, self.eventType)
        self.button.clicked.connect(self.dialog.show)

FormClass, BaseClass = util.load_ui_type("notification_system/user_online.ui")


class UserOnlineDialog(FormClass, BaseClass):
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

        if self.mode == 'friends':
            self.radioButtonFriends.setChecked(True)
        else:
            self.radioButtonAll.setChecked(True)
        self.parent.mode = self.mode

    def save_settings(self):
        Settings.set(self._settings_key+'/mode', self.mode)
        self.parent.mode = self.mode

    @QtCore.pyqtSlot()
    def on_btnSave_clicked(self):
        self.mode = 'friends' if self.radioButtonFriends.isChecked() else 'all'
        self.save_settings()
        self.hide()
