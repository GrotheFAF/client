from PyQt4 import QtCore, QtGui
import util
import time
import client
from .ns_settings import NotificationPosition

"""
The UI popup of the notification system
"""
FormClass, BaseClass = util.load_ui_type("notification_system/dialog.ui")


class NotificationDialog(FormClass, BaseClass):

    def __init__(self, settings, *args, **kwargs):
        BaseClass.__init__(self, *args, **kwargs)

        self.setupUi(self)

        self.labelIcon.setPixmap(util.icon("client/tray_icon.png", pix=True).scaled(32, 32))
        self.standardIcon = util.icon("client/comment.png", pix=True)

        self.settings = settings
        self.update_position()

        # Frameless, always on top, steal no focus & no entry at the taskbar
        self.setWindowFlags(QtCore.Qt.ToolTip)

        # TODO: integrate into client.css
        # self.set_stylesheet(client.instance.styleSheet())

    @QtCore.pyqtSlot()
    def newEvent(self, pixmap, text, lifetime, sound):
        """ Called to display a new popup
        Keyword arguments:
        pix_map -- Icon for the event (displayed left)
        text- HTMl-Text of the vent (displayed right)
        lifetime -- Display duration
        sound -- true|false if should played
        """
        self.labelEvent.setText(str(text))
        if not pixmap:
            pixmap = self.standardIcon
        self.labelImage.setPixmap(pixmap)

        self.labelTime.setText(time.strftime("%H:%M:%S", time.gmtime()))
        QtCore.QTimer.singleShot(lifetime * 1000, self.hide)
        if sound:
            util.sound("chat/sfx/query.wav")

        self.update_position()
        self.show()

    @QtCore.pyqtSlot()
    def hide(self):
        super(FormClass, self).hide()
        # check for next event to show notification for
        client.instance.notificationSystem.check_event()

    # mouseReleaseEvent sometimes not fired
    def mousePressEvent(self, event):  # Qt Event handler
        if event.button() == QtCore.Qt.RightButton:
            self.hide()

    def update_position(self):
        screen = QtGui.QDesktopWidget().screenGeometry()
        dialog_size = self.geometry()
        position = self.settings.popup_position  # client.instance.notificationSystem.settings.popup_position

        if position == NotificationPosition.TOP_LEFT:
            self.move(0, 0)
        elif position == NotificationPosition.TOP_RIGHT:
            self.move(screen.width() - dialog_size.width(), 0)
        elif position == NotificationPosition.BOTTOM_LEFT:
            self.move(0, screen.height() - dialog_size.height())
        else:
            self.move(screen.width() - dialog_size.width(), screen.height() - dialog_size.height())
