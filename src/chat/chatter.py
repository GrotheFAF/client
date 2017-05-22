from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import QUrl
from PyQt4.QtNetwork import QNetworkRequest
from chat._avatarWidget import AvatarWidget
import time
import urllib2
import chat
from fa.replay import replay
import util
import client
from config import Settings

"""
A chatter is the representation of a person on IRC, in a channel's nick list.
There are multiple chatters per channel.
There can be multiple chatters for every Player in the Client.
"""


class Chatter(QtGui.QTableWidgetItem):
    SORT_COLUMN = 2
    AVATAR_COLUMN = 1
    RANK_COLUMN = 0
    STATUS_COLUMN = 3

    RANK_ELEVATION = 0
    RANK_FRIEND = 1
    RANK_USER = 2
    RANK_NONPLAYER = 3
    RANK_FOE = 4

    def __init__(self, parent, user, lobby, *args):
        QtGui.QTableWidgetItem.__init__(self, *args)

        # TODO: for now, userflags and ranks aren't properly interpreted :-/
        # This is impractical if an operator reconnects too late.
        self.parent = parent
        self.lobby = lobby

        self.name, self.id, self.elevation, self.hostname = user

        self.avatar = None
        self.status = None
        self.country = None
        self.league = None
        self.clan = ""
        self.avatarTip = ""

        self.setText(self.name)
        self.setFlags(QtCore.Qt.ItemIsEnabled)
        self.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        row = self.parent.rowCount()
        self.parent.insertRow(row)

        self.parent.setItem(row, Chatter.SORT_COLUMN, self)

        self.avatarItem = QtGui.QTableWidgetItem()
        self.avatarItem.setFlags(QtCore.Qt.ItemIsEnabled)
        self.avatarItem.setTextAlignment(QtCore.Qt.AlignHCenter)

        self.rankItem = QtGui.QTableWidgetItem()
        self.rankItem.setFlags(QtCore.Qt.ItemIsEnabled)
        self.rankItem.setTextAlignment(QtCore.Qt.AlignHCenter)

        self.statusItem = QtGui.QTableWidgetItem()
        self.statusItem.setFlags(QtCore.Qt.ItemIsEnabled)
        self.statusItem.setTextAlignment(QtCore.Qt.AlignHCenter)

        self.parent.setItem(self.row(), Chatter.RANK_COLUMN, self.rankItem)
        self.parent.setItem(self.row(), Chatter.AVATAR_COLUMN, self.avatarItem)
        self.parent.setItem(self.row(), Chatter.STATUS_COLUMN, self.statusItem)

        self.update()

    def is_filtered(self, nick_filter):
        if nick_filter in (self.clan or "").lower() or nick_filter in self.name.lower():
            return True
        return False

    def set_visible(self, visible):
        if visible:
            self.tableWidget().showRow(self.row())
        else:
            self.tableWidget().hideRow(self.row())

    def __ge__(self, other):
        """ Comparison operator used for item list sorting """
        return not self.__lt__(other)

    def __lt__(self, other):
        """ Comparison operator used for item list sorting """
        first_status = self.get_user_rank(self)
        second_status = self.get_user_rank(other)

        if self.name == client.instance.login:
            return True
        if other.name == client.instance.login:
            return False

        # if not same rank sort
        if first_status != second_status:
            return first_status < second_status

        # Default: Alphabetical
        return self.name.lower() < other.name.lower()

    def get_user_rank(self, other_chatter):
        # TODO: Add subdivision for admin?

        if other_chatter.elevation:
            return self.RANK_ELEVATION
        if client.instance.players.is_friend(other_chatter.id):
            return self.RANK_FRIEND - (2 if client.instance.friendsontop else 0)
        if client.instance.players.is_foe(other_chatter.id):
            return self.RANK_FOE
        if client.instance.players.is_player(other_chatter.id):
            return self.RANK_USER

        return self.RANK_NONPLAYER

    def update_avatar(self):
        if self.avatar:

            self.avatarTip = self.avatar["tooltip"]
            self.avatar["url"] = urllib2.unquote(self.avatar["url"])
            url = self.avatar["url"]

            avatar_pix = util.respix(url)

            if avatar_pix:
                self.avatarItem.setIcon(QtGui.QIcon(avatar_pix))
                self.avatarItem.setToolTip(self.avatarTip)
            else:
                if util.add_current_download_avatar(url, self.name):
                    self.lobby.nam.get(QNetworkRequest(QtCore.QUrl(url)))
        else:
            # No avatar set.
            self.avatarItem.setIcon(QtGui.QIcon())
            self.avatarItem.setToolTip(None)

    def update(self):
        """
        Updates the appearance of this chatter in the nicklist
         according to its lobby and irc states
        """
        self.setText(self.name)

        # First make sure we've got the correct id for ourselves
        if self.id == -1 and client.instance.players.is_player(self.name):
            self.id = client.instance.players.get_id(self.name)

        # Color handling
        self.set_color()

        player = client.instance.players[self.id]
        if not player and not self.id == -1:  # We should have a player object for this
            player = client.instance.players[self.name]

        # Weed out IRC users and those we don't know about early.
        if self.id == -1 or player is None:
            self.rankItem.setIcon(util.icon("chat/rank/civilian.png"))
            self.rankItem.setToolTip("IRC User")
            return

        country = player.country
        if country is not None:
            self.setIcon(util.icon("chat/countries/%s.png" % country.lower()))
            self.setToolTip(country)

        if player.avatar != self.avatar:
            self.avatar = player.avatar
            self.update_avatar()

        self.clan = player.clan
        if self.clan is not None:
            self.setText("[%s]%s" % (self.clan, self.name))

        # Status icon handling
        url = client.instance.urls.get(player.login)
        if url:
            if int(url.queryItemValue("uid")) in client.instance.games.games:
                game = client.instance.games.games[int(url.queryItemValue("uid"))]
                game_str = "  " + game.mod + "  on  '" + game.mapdisplayname + "'  (" + str(game.uid) + ") "
                if url.scheme() == "fafgame":
                    if game.password_protected:
                        game_str = " (private) Game Lobby:  '" + game.title + "'" + game_str
                    else:
                        game_str = " Game Lobby:  '" + game.title + "'" + game_str
                    if game.host == self.name:
                        self.status = "host"
                        self.statusItem.setIcon(util.icon("chat/status/host.png"))
                        self.statusItem.setToolTip("Hosting" + game_str)
                    else:
                        self.status = "lobby"
                        self.statusItem.setIcon(util.icon("chat/status/lobby.png"))
                        self.statusItem.setToolTip("In" + game_str)
                elif url.scheme() == "faflive":
                    if game.launched_at:
                        if time.time() - game.launched_at > 5 * 60:
                            self.status = "playing"
                            self.statusItem.setIcon(util.icon("chat/status/playing.png"))
                            self.statusItem.setToolTip("Playing" + game_str)
                        else:
                            self.status = "playing5"
                            self.statusItem.setIcon(util.icon("chat/status/playing_delay.png"))
                            self.statusItem.setToolTip("Playing" + game_str + " -  LIVE DELAY (5 Min)")
                    else:
                        self.status = "strange"
                        self.statusItem.setIcon(util.icon("chat/status/status_unclear.png"))
                        self.statusItem.setToolTip("Playing (missing start time) " + game_str + "<br/>" + url.toString())
                else:
                    self.status = "idle"

            else:  # that shouldn't happen - but it does in rare cases
                self.status = "strange"
                self.statusItem.setIcon(util.icon("chat/status/status_unclear.png"))
                self.statusItem.setToolTip("(has url - but no matching running game found)<br/>" + url.toString())
        else:
            self.status = "idle"
            self.statusItem.setIcon(QtGui.QIcon())
            self.statusItem.setToolTip("Idle")

        # Rating icon choice  (chr(0xB1) = +-)
        self.rankItem.setToolTip("Global Rating: " + str(int(player.rating_estimate())) + " ("
                                 + str(player.number_of_games) + " Games) [" + str(int(round(player.rating_mean)))
                                 + chr(0xB1) + str(int(round(player.rating_deviation))) + "]\n"
                                 + "Ladder Rating: " + str(int(player.ladder_estimate())) + " ["
                                 + str(int(round(player.ladder_rating_mean)))
                                 + chr(0xB1) + str(int(round(player.ladder_rating_deviation))) + "]")

        if player.league:
            self.rankItem.setToolTip("Division : " + player.league["division"] + "\nGlobal Rating: "
                                     + str(int(player.rating_estimate())))
            self.rankItem.setIcon(util.icon("chat/rank/%s.png" % player.league["league"]))
        else:
            self.rankItem.setIcon(util.icon("chat/rank/newplayer.png"))

    def set_color(self):
        if client.instance.id == self.id and self.elevation in chat.OPERATOR_COLORS.keys():
            self.setTextColor(QtGui.QColor(chat.get_color("self_mod")))
            return
        if client.instance.players.is_friend(self.id) and self.elevation in chat.OPERATOR_COLORS.keys():
            self.setTextColor(QtGui.QColor(chat.get_color("friend_mod")))
            return
        if self.elevation in chat.colors.OPERATOR_COLORS.keys():
            self.setTextColor(QtGui.QColor(chat.colors.OPERATOR_COLORS[self.elevation]))
            return

        if self.id != -1:
            self.setTextColor(QtGui.QColor(client.instance.players.get_user_color(self.id)))
            return

        self.setTextColor(QtGui.QColor(chat.get_color("default")))

    def view_aliases(self):
        QtGui.QDesktopServices.openUrl(QUrl("{}?name={}".format(Settings.get("USER_ALIASES_URL"), self.name)))

    def select_avatar(self):
        avatar_selection = AvatarWidget(self.name, personal=True)
        avatar_selection.exec_()

    def add_avatar(self):
        avatar_selection = AvatarWidget(self.name)
        avatar_selection.exec_()

    def kick(self):
        pass

    def doubleclicked(self, item):
        # filter yourself
        if client.instance.login == self.name:
            return
        # Chatter name clicked
        if item == self:
            self.lobby.open_query(self.name, self.id, activate=True)  # open and activate query window

        elif item == self.statusItem:
            if self.name in client.instance.urls:
                url = client.instance.urls[self.name]
                if url.scheme() == "fafgame":
                    self.join_in_game()
                elif url.scheme() == "faflive":
                    self.view_replay()

    def pressed(self, item):
        menu = QtGui.QMenu(self.parent)

        # Actions for stats
        action_select_avatar = QtGui.QAction("Select Avatar", menu)

        # Action for aliases link
        action_view_aliases = QtGui.QAction("View Aliases", menu)

        # Actions for Games and Replays
        action_replay = QtGui.QAction("View Live Replay", menu)
        action_vault_replay = QtGui.QAction("View Replays in Vault", menu)
        action_join = QtGui.QAction("Join in Game", menu)

        # Default is all disabled, we figure out what we can do after this
        action_replay.setDisabled(True)
        action_join.setDisabled(True)

        # Don't allow self to be invited to a game, or join one
        if client.instance.login != self.name:
            if self.name in client.instance.urls:
                url = client.instance.urls[self.name]
                if url.scheme() == "fafgame":
                    action_join.setEnabled(True)
                elif url.scheme() == "faflive":
                    action_replay.setEnabled(True)

        # Triggers
        action_view_aliases.triggered.connect(self.view_aliases)
        action_select_avatar.triggered.connect(self.select_avatar)
        action_replay.triggered.connect(self.view_replay)
        action_vault_replay.triggered.connect(self.view_vault_replay)
        action_join.triggered.connect(self.join_in_game)

        # only for us. Either way, it will display our avatar, not anyone avatar.
        if client.instance.login == self.name:
            menu.addAction(action_select_avatar)
            menu.addSeparator()

        # power menu
        if client.instance.power > 1:
            # admin and mod menus
            action_add_avatar = QtGui.QAction("Assign avatar", menu)
            menu.addAction(action_add_avatar)
            action_add_avatar.triggered.connect(self.add_avatar)

            if client.instance.power == 2:
                action_inspect_in_mordor = QtGui.QAction("Send the Orcs", menu)
                menu.addAction(action_inspect_in_mordor)

                def send_the_orcs():
                    route = Settings.get('mordor/host')

                    if self.id != -1:
                        QtGui.QDesktopServices.openUrl(QUrl("{}/users/{}".format(route, self.id)))
                    else:
                        QtGui.QDesktopServices.openUrl(QUrl("{}/users/{}".format(route, self.name)))

                action_inspect_in_mordor.triggered.connect(send_the_orcs)

                action_close_fa = QtGui.QAction("Close Game", menu)
                menu.addAction(action_close_fa)
                action_close_fa.triggered.connect(lambda: client.instance.close_fa(self.name))

                action_close_lobby = QtGui.QAction("Close FAF Client", menu)
                menu.addAction(action_close_lobby)
                action_close_lobby.triggered.connect(lambda: client.instance.close_lobby(self.name))

            menu.addSeparator()

        # Adding to menu
        menu.addAction(action_view_aliases)
        menu.addSeparator()
        menu.addAction(action_replay)
        menu.addAction(action_vault_replay)
        menu.addSeparator()
        menu.addAction(action_join)

        # Actions for the Friends List
        action_add_friend = QtGui.QAction("Add friend", menu)
        action_rem_friend = QtGui.QAction("Remove friend", menu)

        # Actions for the Foes List
        action_add_foe = QtGui.QAction("Add foe", menu)
        action_rem_foe = QtGui.QAction("Remove foe", menu)

        # Don't allow self to be added or removed from friends or foes
        if client.instance.me.id == self.id:
            action_add_friend.setDisabled(1)
            action_rem_friend.setDisabled(1)
            action_add_foe.setDisabled(1)
            action_rem_foe.setDisabled(1)

        # Enable / Disable actions according to friend status
        if client.instance.players.is_friend(self.id):
            action_add_friend.setDisabled(1)
            action_rem_foe.setDisabled(1)
            action_add_foe.setDisabled(1)
        else:
            action_rem_friend.setDisabled(1)

        if client.instance.players.is_foe(self.id):
            action_add_foe.setDisabled(1)
            action_add_friend.setDisabled(1)
            action_rem_friend.setDisabled(1)
        else:
            action_rem_foe.setDisabled(1)

        # Triggers
        action_add_friend.triggered.connect(lambda: client.instance.add_friend(self.id))
        action_rem_friend.triggered.connect(lambda: client.instance.rem_friend(self.id))
        action_add_foe.triggered.connect(lambda: client.instance.add_foe(self.id))
        action_rem_foe.triggered.connect(lambda: client.instance.rem_foe(self.id))

        # Adding to menu
        menu.addAction(action_add_friend)
        menu.addAction(action_rem_friend)
        menu.addSeparator()
        menu.addAction(action_add_foe)
        menu.addAction(action_rem_foe)

        # Finally: Show the popup
        menu.popup(QtGui.QCursor.pos())

    @QtCore.pyqtSlot()
    def view_replay(self):
        if self.name in client.instance.urls:
            replay(client.instance.urls[self.name])

    @QtCore.pyqtSlot()
    def view_vault_replay(self):
        """ see the player replays in the vault """
        client.instance.replays.setCurrentIndex(2)  # focus on Online Fault
        client.instance.replays.playerName.setText(self.name)
        client.instance.replays.mapName.setText("")
        client.instance.replays.modList.setCurrentIndex(0)  # "All"
        client.instance.replays.minRating.setValue(0)
        client.instance.replays.search_vault()
        client.instance.mainTabs.setCurrentIndex(client.instance.mainTabs.indexOf(client.instance.replaysTab))

    @QtCore.pyqtSlot()
    def join_in_game(self):
        if self.name in client.instance.urls:
            client.instance.join_game_from_url(client.instance.urls[self.name])
