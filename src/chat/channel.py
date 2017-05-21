
from fa.replay import replay

import util
from PyQt4 import QtGui, QtCore
import time
import chat
from chat import logger
from chat.chatter import Chatter
import re
import client
import json

from client import Player

QUERY_BLINK_SPEED = 250
CHAT_TEXT_LIMIT = 350
CHAT_REMOVEBLOCK = 50

FormClass, BaseClass = util.load_ui_type("chat/channel.ui")


class IRCPlayer(Player):
    def __init__(self, name):
        Player.__init__(self, **{
            "id": -1,
            "login": name,
            "global_rating": (1500, 500),
            "ladder_rating": (1500, 500),
            "number_of_games": 0
        })


class Formatters(object):
    FORMATTER_ANNOUNCEMENT   = u'' + util.readfile("chat/formatters/announcement.qthtml")
    FORMATTER_MESSAGE        = u'' + util.readfile("chat/formatters/message.qthtml")
    FORMATTER_MESSAGE_AVATAR = u'' + util.readfile("chat/formatters/messageAvatar.qthtml")
    FORMATTER_ACTION         = u'' + util.readfile("chat/formatters/action.qthtml")
    FORMATTER_ACTION_AVATAR  = u'' + util.readfile("chat/formatters/actionAvatar.qthtml")
    FORMATTER_RAW            = u'' + util.readfile("chat/formatters/raw.qthtml")
    NICKLIST_COLUMNS         = json.loads(util.readfile("chat/formatters/nicklist_columns.json"))


class Channel(FormClass, BaseClass):
    """
    This is an actual chat channel object, representing an IRC chat room and the users currently present.
    """
    def __init__(self, lobby, name, private=False, *args, **kwargs):
        BaseClass.__init__(self, lobby, *args, **kwargs)

        self.setupUi(self)

        #self.filterIdle.setIcon(util.icon("chat/status/none.png"))
        self.filterHost.setIcon(util.icon("chat/status/host.png"))
        self.filterLobby.setIcon(util.icon("chat/status/lobby.png"))
        self.filterPlaying5.setIcon(util.icon("chat/status/playing_delay.png"))
        self.filterPlaying.setIcon(util.icon("chat/status/playing.png"))
        self.filterStrange.setIcon(util.icon("chat/status/status_unclear.png"))

        self.filterIdle.clicked.connect(self.status_filter_nicks)
        self.filterHost.clicked.connect(self.status_filter_nicks)
        self.filterLobby.clicked.connect(self.status_filter_nicks)
        self.filterPlaying5.clicked.connect(self.status_filter_nicks)
        self.filterPlaying.clicked.connect(self.status_filter_nicks)
        self.filterStrange.clicked.connect(self.status_filter_nicks)

        # Special HTML formatter used to layout the chat lines written by people
        self.lobby = lobby
        self.chatters = {}

        self.last_timestamp = None

        # Query flasher
        self.blinker = QtCore.QTimer()
        self.blinker.timeout.connect(self.blink)
        self.blinked = False

        # Table width of each chatter's name cell...
        self.maxChatterWidth = 100  # TODO: This might / should auto-adapt

        # count the number of line currently in the chat
        self.lines = 0

        # Perform special setup for public channels as opposed to private ones
        self.name = name
        self.private = private

        if not self.private:
            # Non-query channels have a sorted nicklist
            self.nickList.sortItems(Chatter.SORT_COLUMN)

            # Properly and snugly snap all the columns
            self.nickList.horizontalHeader().setResizeMode(Chatter.RANK_COLUMN, QtGui.QHeaderView.Fixed)
            self.nickList.horizontalHeader().resizeSection(Chatter.RANK_COLUMN, Formatters.NICKLIST_COLUMNS['RANK'])

            self.nickList.horizontalHeader().setResizeMode(Chatter.AVATAR_COLUMN, QtGui.QHeaderView.Fixed)
            self.nickList.horizontalHeader().resizeSection(Chatter.AVATAR_COLUMN, Formatters.NICKLIST_COLUMNS['AVATAR'])

            self.nickList.horizontalHeader().setResizeMode(Chatter.STATUS_COLUMN, QtGui.QHeaderView.Fixed)
            self.nickList.horizontalHeader().resizeSection(Chatter.STATUS_COLUMN, Formatters.NICKLIST_COLUMNS['STATUS'])

            self.nickList.horizontalHeader().setResizeMode(Chatter.SORT_COLUMN, QtGui.QHeaderView.Stretch)

            self.nickList.itemDoubleClicked.connect(self.nick_doubleclicked)
            self.nickList.itemPressed.connect(self.nick_pressed)

            self.nickFilter.textChanged.connect(self.filter_nicks)

            client.instance.usersUpdated.connect(self.update_users)
        else:
            self.nickFrame.hide()
            self.announceLine.hide()

        self.chatArea.anchorClicked.connect(self.open_url)
        self.chatEdit.returnPressed.connect(self.send_line)
        self.chatEdit.set_chatters(self.chatters)

    def joinChannel(self, index):  # Qt ?
        """ join another channel """
        channel = self.channelsComboBox.itemText(index)
        if channel.startswith('#'):
            self.lobby.auto_join([channel])

    def keyReleaseEvent(self, key_event):  # Qt QShowEvent
        """
        Allow the ctrl-C event.
        """
        if key_event.key() == 67:
            self.chatArea.copy()

    def resizeEvent(self, size):
        BaseClass.resizeEvent(self, size)
        self.setTextWidth()

    def setTextWidth(self):
        self.chatArea.setLineWrapColumnOrWidth(self.chatArea.size().width() - 20)  # Hardcoded, but seems to be enough (tabstop was a bit large)

    def showEvent(self, event):  # Qt QShowEvent
        self.stop_blink()
        self.setTextWidth()
        return BaseClass.showEvent(self, event)

    @QtCore.pyqtSlot()
    def clearWindow(self):  # Qt ?
        if self.isVisible():
            self.chatArea.setPlainText("")
            self.last_timestamp = 0

    @QtCore.pyqtSlot()
    def status_filter_chatter(self, chatter):
        if self.chatters[chatter].is_filtered(self.nickFilter.text().lower()):  # visible by nick filter
            if chatter == client.instance.me.login:  # don't filter me
                self.chatters[chatter].set_visible(True)
            elif self.filterIdle.isChecked() or self.filterHost.isChecked() or \
               self.filterLobby.isChecked() or self.filterPlaying5.isChecked() or \
               self.filterPlaying.isChecked() or self.filterStrange.isChecked():
                if self.chatters[chatter].status == "idle":
                    self.chatters[chatter].set_visible(self.filterIdle.isChecked())
                elif self.chatters[chatter].status == "host":
                    self.chatters[chatter].set_visible(self.filterHost.isChecked())
                elif self.chatters[chatter].status == "lobby":
                    self.chatters[chatter].set_visible(self.filterLobby.isChecked())
                elif self.chatters[chatter].status == "playing5":
                    self.chatters[chatter].set_visible(self.filterPlaying5.isChecked())
                elif self.chatters[chatter].status == "playing":
                    self.chatters[chatter].set_visible(self.filterPlaying.isChecked())
                elif self.chatters[chatter].status == "strange":
                    self.chatters[chatter].set_visible(self.filterStrange.isChecked())
            else:  # no filter checked
                self.chatters[chatter].set_visible(True)
        else:  # hidden by nick filter
            self.chatters[chatter].set_visible(False)

    @QtCore.pyqtSlot()
    def status_filter_nicks(self):
        for chatter in self.chatters.keys():
            self.status_filter_chatter(chatter)

    @QtCore.pyqtSlot()
    def filter_nicks(self):
        for chatter in self.chatters.keys():
            self.chatters[chatter].set_visible(self.chatters[chatter].is_filtered(self.nickFilter.text().lower()))

    def update_user_count(self):
        count = len(self.chatters.keys())
        self.nickFilter.setPlaceholderText(str(count) + " users... (type to filter)")

        if self.nickFilter.text():
            self.filter_nicks()

    @QtCore.pyqtSlot()
    def blink(self):
        if self.blinked:
            self.blinked = False
            self.lobby.tabBar().setTabText(self.lobby.indexOf(self), self.name)
        else:
            self.blinked = True
            self.lobby.tabBar().setTabText(self.lobby.indexOf(self), "")

    @QtCore.pyqtSlot()
    def stop_blink(self):
        self.blinker.stop()
        self.lobby.tabBar().setTabText(self.lobby.indexOf(self), self.name)

    @QtCore.pyqtSlot()
    def start_blink(self):
        self.blinker.start(QUERY_BLINK_SPEED)

    @QtCore.pyqtSlot()
    def ping_window(self):
        QtGui.QApplication.alert(client.instance, 0)

        if not self.isVisible() or QtGui.QApplication.activeWindow() != client.instance:
            if self.one_minute_or_older():
                if client.instance.soundeffects:
                    util.sound("chat/sfx/query.wav")

        if not self.isVisible():
            if not self.blinker.isActive() and not self == self.lobby.currentWidget():
                    self.start_blink()

    @QtCore.pyqtSlot(QtCore.QUrl)
    def open_url(self, url):
        logger.debug("Clicked on URL: " + url.toString())
        if url.scheme() == "faflive":
            replay(url)
        elif url.scheme() == "fafgame":
            client.instance.join_game_from_url(url)
        else:
            QtGui.QDesktopServices.openUrl(url)

    @QtCore.pyqtSlot(str, str)
    def print_announcement(self, text, color, size, scroll_forced=True):
        # scroll if close to the last line of the log
        scroll_current = self.chatArea.verticalScrollBar().value()
        scroll_needed = scroll_forced or ((self.chatArea.verticalScrollBar().maximum() - scroll_current) < 20)

        cursor = self.chatArea.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.chatArea.setTextCursor(cursor)

        formatter = Formatters.FORMATTER_ANNOUNCEMENT
        line = formatter.format(size=size, color=color, text=util.irc_escape(text, self.lobby.a_style))
        self.chatArea.insertHtml(line)

        if scroll_needed:
            self.chatArea.verticalScrollBar().setValue(self.chatArea.verticalScrollBar().maximum())
        else:
            self.chatArea.verticalScrollBar().setValue(scroll_current)

    def print_line(self, name, text, scroll_forced=False, formatter=Formatters.FORMATTER_MESSAGE):
        if self.lines > CHAT_TEXT_LIMIT:
            cursor = self.chatArea.textCursor()
            cursor.movePosition(QtGui.QTextCursor.Start)
            cursor.movePosition(QtGui.QTextCursor.Down, QtGui.QTextCursor.KeepAnchor, CHAT_REMOVEBLOCK)
            cursor.removeSelectedText()
            self.lines = self.lines - CHAT_REMOVEBLOCK

        if client.instance.players.is_player(name):
            player = client.instance.players[name]
        else:
            player = IRCPlayer(name)

        display_name = name
        if player.clan is not None:
            display_name = "<b>[%s]</b>%s" % (player.clan, name)

        # Play a ping sound and flash the title under certain circumstances
        mentioned = text.find(client.instance.login) != -1
        if mentioned or (self.private and not (formatter is Formatters.FORMATTER_RAW and text == "quit.")):
            self.ping_window()

        avatar = None
        avatar_tip = ""
        if name in self.chatters:
            chatter = self.chatters[name]
            color = chatter.textColor().name()
            if chatter.avatar:
                avatar = chatter.avatar["url"]
                avatar_tip = chatter.avatarTip or ""

        else:
            # Fallback and ask the client. We have no Idea who this is.
            color = client.instance.players.get_user_color(player.id)

        if mentioned:
            color = client.instance.get_color("you")

        # scroll if close to the last line of the log
        scroll_current = self.chatArea.verticalScrollBar().value()
        scroll_needed = scroll_forced or ((self.chatArea.verticalScrollBar().maximum() - scroll_current) < 20)

        cursor = self.chatArea.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.chatArea.setTextCursor(cursor)

        # This whole block seems to be duplicated further up.
        # For fucks sake.
        if avatar:
            pix = util.respix(avatar)
            if pix:
                if not self.chatArea.document().resource(QtGui.QTextDocument.ImageResource, QtCore.QUrl(avatar)):
                    self.chatArea.document().addResource(QtGui.QTextDocument.ImageResource,  QtCore.QUrl(avatar), pix)
                line = formatter.format(time=self.timestamp(), avatar=avatar, avatarTip=avatar_tip, name=display_name,
                                        color=color, width=self.maxChatterWidth,
                                        text=util.irc_escape(text, self.lobby.a_style))
            else:
                formatter = Formatters.FORMATTER_MESSAGE
                line = formatter.format(time=self.timestamp(), name=display_name, color=color,
                                        width=self.maxChatterWidth, text=util.irc_escape(text, self.lobby.a_style))
        else:
            line = formatter.format(time=self.timestamp(), name=display_name, color=color, width=self.maxChatterWidth,
                                    text=util.irc_escape(text, self.lobby.a_style))

        self.chatArea.insertHtml(line)
        self.lines += 1

        if scroll_needed:
            self.chatArea.verticalScrollBar().setValue(self.chatArea.verticalScrollBar().maximum())
        else:
            self.chatArea.verticalScrollBar().setValue(scroll_current)

    @QtCore.pyqtSlot(str, str)
    def print_msg(self, name, text, scroll_forced=False):
        if name in self.chatters and self.chatters[name].avatar:
            fmt = Formatters.FORMATTER_MESSAGE_AVATAR
        else:
            fmt = Formatters.FORMATTER_MESSAGE
        self.print_line(name, text, scroll_forced, fmt)

    @QtCore.pyqtSlot(str, str)
    def print_action(self, name, text, scroll_forced=False, server_action=False):
        if server_action:
            fmt = Formatters.FORMATTER_RAW
        elif name in self.chatters and self.chatters[name].avatar:
            fmt = Formatters.FORMATTER_ACTION_AVATAR
        else:
            fmt = Formatters.FORMATTER_ACTION
        self.print_line(name, text, scroll_forced, fmt)

    @QtCore.pyqtSlot(str, str)
    def print_raw(self, name, text, scroll_forced=False):
        """
        Print an raw message in the chatArea of the channel
        """
        name_id = client.instance.players.get_id(name)

        color = client.instance.players.get_user_color(name_id)

        # Play a ping sound
        if self.private and name != client.instance.login:
            self.ping_window()

        # scroll if close to the last line of the log
        scroll_current = self.chatArea.verticalScrollBar().value()
        scroll_needed = scroll_forced or ((self.chatArea.verticalScrollBar().maximum() - scroll_current) < 20)

        cursor = self.chatArea.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.chatArea.setTextCursor(cursor)

        formatter = Formatters.FORMATTER_RAW
        line = formatter.format(time=self.timestamp(), name=name, color=color, width=self.maxChatterWidth, text=text)
        self.chatArea.insertHtml(line)

        if scroll_needed:
            self.chatArea.verticalScrollBar().setValue(self.chatArea.verticalScrollBar().maximum())
        else:
            self.chatArea.verticalScrollBar().setValue(scroll_current)

    def timestamp(self):
        """ returns a fresh timestamp string once every minute, and an empty string otherwise """
        timestamp = time.strftime("%H:%M")
        if self.last_timestamp != timestamp:
            self.last_timestamp = timestamp
            return timestamp
        else:
            return ""

    def one_minute_or_older(self):
        timestamp = time.strftime("%H:%M")
        return self.last_timestamp != timestamp

    @QtCore.pyqtSlot(QtGui.QTableWidgetItem)
    def nick_doubleclicked(self, item):
        chatter = self.nickList.item(item.row(), Chatter.SORT_COLUMN)  # Look up the associated chatter object
        chatter.doubleclicked(item)

    @QtCore.pyqtSlot(QtGui.QTableWidgetItem)
    def nick_pressed(self, item):
        if QtGui.QApplication.mouseButtons() == QtCore.Qt.RightButton:
            # Look up the associated chatter object
            chatter = self.nickList.item(item.row(), Chatter.SORT_COLUMN)
            chatter.pressed(item)

    @QtCore.pyqtSlot(list)
    def update_users(self, updated_users):
        for user in updated_users:
            if user in client.instance.players:
                name = client.instance.players[user].login
            else:
                name = user
            if name in self.chatters:
                self.chatters[name].update()
                self.status_filter_chatter(name)

        self.update_user_count()

    def elevate_chatter(self, name, modes):
        add = re.compile(".*\+([a-z]+)")
        remove = re.compile(".*\-([a-z]+)")
        if name in self.chatters:
            addmatch = re.search(add, modes)
            if addmatch:
                modes = addmatch.group(1)
                mode = ""
                if "v" in modes:
                    mode = "+"
                if "o" in modes:
                    mode = "@"
                if "q" in modes:
                    mode = "~"
                if mode in chat.colors.OPERATOR_COLORS:
                    self.chatters[name].elevation = mode
                    self.chatters[name].update()
            removematch = re.search(remove, modes)
            if removematch:
                modes = removematch.group(1)
                if "o" in modes and self.chatters[name].elevation == "@":
                    self.chatters[name].elevation = None
                    self.chatters[name].update()
                if "q" in modes and self.chatters[name].elevation == "~":
                    self.chatters[name].elevation = None
                    self.chatters[name].update()
                if "v" in modes and self.chatters[name].elevation == "+":
                    self.chatters[name].elevation = None
                    self.chatters[name].update()

            self.status_filter_chatter(name)

    def add_chatter(self, user_name, user_id=-1, elevation='', hostname='', join=False):
        """
        Adds an user to this chat channel, and assigns an appropriate icon depending on friendship and FAF player status
        """
        if user_name not in self.chatters:
            item = Chatter(self.nickList, (user_name, user_id, elevation, hostname), self.lobby, None)
            self.chatters[user_name] = item

        self.chatters[user_name].update()
        self.status_filter_chatter(user_name)
        self.update_user_count()

        if join and client.instance.joinsparts:
            self.print_action(user_name, "joined the channel.", server_action=True)

    def rename_chatter(self, oldname, newname):
        if oldname in self.chatters:
            chatter = self.chatters.pop(oldname)
            chatter.name = newname
            self.chatters[newname] = chatter
            chatter.update()

    def remove_chatter(self, name, server_action=None):
        if name in self.chatters:
            self.nickList.removeRow(self.chatters[name].row())
            del self.chatters[name]

            if server_action and (client.instance.joinsparts or self.private):
                self.print_action(name, server_action, server_action=True)
                self.stop_blink()

        self.update_user_count()

    def set_announce_text(self, text):
        self.announceLine.clear()
        self.announceLine.setText("<style>a{color:cornflowerblue}</style><b><font color=white>" + util.irc_escape(text)
                                  + "</font></b>")

    @QtCore.pyqtSlot()
    def send_line(self, target=None):
        self.stop_blink()

        if not target:
            target = self.name  # pubmsg in channel

        line = self.chatEdit.text()
        # Split into lines if newlines are present
        fragments = line.split("\n")
        for text in fragments:
            # Compound wacky Whitespace
            text = re.sub('\s', ' ', text)
            text = text.strip()

            # Reject empty messages
            if not text:
                continue

            # System commands
            if text.startswith("/"):
                if text.startswith("/join "):
                    self.lobby.join(text[6:])
                elif text.startswith("/topic "):
                    self.lobby.set_topic(self.name, text[7:])
                elif text.startswith("/msg "):
                    blobs = text.split(" ")
                    self.lobby.send_msg(blobs[1], " ".join(blobs[2:]))
                elif text.startswith("/me "):
                    if self.lobby.send_action(target, text[4:]):
                        self.print_action(client.instance.login, text[4:], True)
                    else:
                        self.print_action("IRC", "action not supported", True)
                elif text.startswith("/seen "):
                    if self.lobby.send_msg("nickserv", "info %s" % (text[6:])):
                        self.print_action("IRC", "info requested on %s" % (text[6:]), True)
                    else:
                        self.print_action("IRC", "not connected", True)
            else:
                if self.lobby.send_msg(target, text):
                    self.print_msg(client.instance.login, text, True)
        self.chatEdit.clear()
