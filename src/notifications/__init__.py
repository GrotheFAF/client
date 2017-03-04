from PyQt4 import QtCore
import client
import util
from fa import maps
from notifications.ns_dialog import NotificationDialog
from notifications.ns_settings import NsSettingsDialog, IngameNotification

"""
The Notification Systems reacts on events and displays a popup.
Each event_type has a NsHook to customize it.
"""


class Notifications:
    USER_ONLINE = 'user_online'
    NEW_GAME = 'new_game'

    def __init__(self):

        self.settings = NsSettingsDialog()
        self.dialog = NotificationDialog(self.settings)
        self.events = []
        self.disabledStartup = True
        self.game_running = False

        client.instance.gameEnter.connect(self.game_enter)
        client.instance.gameExit.connect(self.game_exit)

        self.user = util.icon("client/user.png", pix=True)

    def game_enter(self):
        self.game_running = True

    def game_exit(self):
        self.game_running = False
        # kick the queue
        if self.settings.ingame_notifications == IngameNotification.QUEUE:
            self.check_event()

    def is_disabled(self):
        return (
            self.disabledStartup
            or self.game_running and self.settings.ingame_notifications == IngameNotification.DISABLE
            or not self.settings.enabled
        )

    def set_notification_enabled(self, enabled):
        self.settings.enabled = enabled
        self.settings.saveSettings()

    @QtCore.pyqtSlot()
    def on_event(self, event_type, data):
        """
        Puts an event in a queue, can trigger a popup.
        Keyword arguments:
        event_type -- Type of the event
        data -- Custom data that is used by the system to show a detailed popup
        """
        if self.is_disabled() or not self.settings.popupEnabled(event_type):
            return

        do_add = False

        if event_type == self.USER_ONLINE:
            if self.settings.getCustomSetting(event_type, 'mode') == 'all' or \
                    client.instance.players.isFriend(data['user']):
                do_add = True
        elif event_type == self.NEW_GAME:
            if self.settings.getCustomSetting(event_type, 'mode') == 'all' or \
                    ('host' in data and client.instance.players.isFriend(data['host'])):
                do_add = True

        if do_add:
            self.events.append((event_type, data))

        self.check_event()

    @QtCore.pyqtSlot()
    def on_show_settings(self):
        """ Shows a Settings Dialog with all registered notifications modules  """
        self.settings.show()

    def show_event(self):
        """
        Display the next event in the queue as popup

        Pops event from queue and checks if it is showable as per settings
        If event is showable, process event data and then feed it into notification dialog

        Returns True if showable event found, False otherwise
        """

        event = self.events.pop(0)

        event_type = event[0]
        data = event[1]
        pix_map = None
        text = str(data)
        if event_type == self.USER_ONLINE:
            userid = data['user']
            pix_map = self.user
            text = '<html>%s<br><font color="silver" size="-2">joined</font> %s</html>' % (client.instance.players[userid].login, data['channel'])
        elif event_type == self.NEW_GAME:

            preview = maps.preview(data['mapname'], pixmap=True)
            if preview:
                pix_map = preview.scaled(80, 80)

            # TODO: outsource as function?
            mod = data.get('featured_mod')
            mods = data.get('sim_mods')

            mod_str = ''
            if mod != 'faf' or mods:
                mod_str = mod
                if mods:
                    if mod == 'faf':
                        mod_str = ", ".join(mods.values())
                    else:
                        mod_str = mod + " & " + ", ".join(mods.values())
                    if len(mod_str) > 20:
                        mod_str = mod_str[:15] + "..."

            if mod_str == '':
                mod_html = ''
            else:
                mod_html = '<br><font size="-4"><font color="red">mods</font> %s</font>' % mod_str
            text = '<html>%s<br><font color="silver" size="-2">on</font> %s%s</html>' % (data['title'], maps.getDisplayName(data['mapname']), mod_html)

        self.dialog.newEvent(pix_map, text, self.settings.popup_lifetime, self.settings.soundEnabled(event_type))

    def check_event(self):
        """
        Checks that we are in correct state to show next notification popup

        This means:
            * There need to be events pending
            * There must be no notification showing right now (i.e. notification dialog hidden)
            * Game isn't running, or ingame notifications are enabled
        """
        if len(self.events) > 0 and self.dialog.isHidden() and \
                (not self.game_running or self.settings.ingame_notifications == IngameNotification.ENABLE):
            self.show_event()
