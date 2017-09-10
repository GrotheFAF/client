from PyQt4 import QtCore, QtGui
from fa import maps
import util
import os
from games.moditem import mod_invisible
import client
import time
import logging
logger = logging.getLogger(__name__)


class GameItemDelegate(QtGui.QStyledItemDelegate):

    def __init__(self, *args, **kwargs):
        QtGui.QStyledItemDelegate.__init__(self, *args, **kwargs)

    def paint(self, painter, option, index, *args, **kwargs):
        self.initStyleOption(option, index)

        painter.save()

        html = QtGui.QTextDocument()
        html.setHtml(option.text)

        icon = QtGui.QIcon(option.icon)

        # clear icon and text before letting the control draw itself because we're rendering these parts ourselves
        option.icon = QtGui.QIcon()        
        option.text = ""  
        option.widget.style().drawControl(QtGui.QStyle.CE_ItemViewItem, option, painter, option.widget)

        # Shadow (100x100 shifted 8 right and 8 down)
        painter.fillRect(option.rect.left()+8, option.rect.top()+8, 100, 100, QtGui.QColor("#202020"))

        # Icon  (110x110 adjusted: shifts top,left 3 and bottom,right -7 -> makes/clips it to 100x100)
        icon.paint(painter, option.rect.adjusted(3, 3, -7, -7), QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)

        # Frame around the icon (100x100 shifted 3 right and 3 down)
        pen = QtGui.QPen()
        pen.setWidth(1)
        pen.setBrush(QtGui.QColor("#303030"))
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        painter.drawRect(option.rect.left() + 3, option.rect.top() + 3, 100, 100)

        # Description (text right of map icon(100), shifted 10 more right and 10 down)
        painter.translate(option.rect.left() + 100 + 10, option.rect.top()+10)
        clip = QtCore.QRectF(0, 0, option.rect.width() - 100 - 10 - 5, option.rect.height())
        html.drawContents(painter, clip)

        painter.restore()

    def sizeHint(self, option, index, *args, **kwargs):
        text_width = 275
        icon_size = 110
        padding = 10
        # Gameitem has fixed size
        return QtCore.QSize(icon_size + text_width + padding, icon_size)


class GameItem(QtGui.QListWidgetItem):

    FORMATTER_FAF = util.readfile("games/formatters/faf.qthtml")
    FORMATTER_MOD = util.readfile("games/formatters/mod.qthtml")
    FORMATTER_TOOL = util.readfile("games/formatters/tool.qthtml")

    def __init__(self, uid, *args):
        QtGui.QListWidgetItem.__init__(self, *args)

        self.uid = uid
        self.mapname = None
        self.mapdisplayname = ""
        self.title = None
        self.host = ""
        self.host_id = -1
        self.password_protected = False
        self.mod = None
        self.mods = None
        self.moddisplayname = None
        self.state = None
        self.launched_at = None
        self.options = []
        self.players = []

        self.setHidden(True)

    def url(self, player_id=None):  # <- update
        if not player_id:
            player_id = self.host_id  # <- announce_replay

        if self.state == "playing":
            url = QtCore.QUrl()
            url.setScheme("faflive")
            url.setHost("lobby.faforever.com")
            url.setPath(str(self.uid) + "/" + str(player_id) + ".SCFAreplay")
            url.addQueryItem("map", self.mapname)
            url.addQueryItem("mod", self.mod)
            url.addQueryItem("uid", str(self.uid))
            return url
        elif self.state == "open":
            url = QtCore.QUrl()
            url.setScheme("fafgame")
            url.setHost("lobby.faforever.com")
            url.setPath(str(player_id))
            url.addQueryItem("map", self.mapname)
            url.addQueryItem("mod", self.mod)
            url.addQueryItem("uid", str(self.uid))
            return url
        return None 

    @QtCore.pyqtSlot()
    def announce_replay(self):  # <- update - timer

        if not self.state == "playing":  # game already over
            return

        client.instance.usersUpdated.emit(list(self.players))  # red cross to white cross

        # User does not want to see this in chat
        if not client.instance.livereplays:
            return

        for player in self.players:
            if client.instance.players.is_friend(player.id):
                in_str = ' in <a style="color:' + client.instance.get_color("url") + '" href="' + \
                         client.instance.urls[str(player.login)].toString() + '">' + self.title + '</a> on "' + \
                         self.mapdisplayname + '"'
                if self.mod != "faf":
                    in_str = ' ' + self.mod + in_str
                client.instance.forward_local_broadcast(player.login, 'is playing' + in_str)

    @QtCore.pyqtSlot()
    def announce_hosting(self):  # <- update
        if not client.instance.players.is_friend(self.host_id):
            return

        if not self.state == "open":  # game has started or hosting aborted
            return

        # User does not want to see this in chat
        if not client.instance.opengames:
            return

        if self.host in client.instance.urls:
            name = self.host
        elif len(self.players) > 0:
            name = self.players[0].login
        else:  # no player in game online
            return

        in_str = ' <a style="color:' + client.instance.get_color("url") + '" href="' + \
                 client.instance.urls[name].toString() + '">' + self.title + '</a> on "' + \
                 self.mapdisplayname + '"'
        if self.mod != "faf":
            in_str = ' ' + self.mod + in_str
        if self.mod != "ladder1v1":
            client.instance.forward_local_broadcast(self.host, 'is hosting' + in_str)
        else:
            client.instance.forward_local_broadcast(self.host, 'started' + in_str)

    @QtCore.pyqtSlot()
    def announce_joining(self, name=None):  # <- update
        if not self.state == "open":  # game has started or hosting aborted
            return

        # User does not want to see this in chat
        if not client.instance.opengames:
            return

        if name:
            if not client.instance.players.is_friend(name):
                return

            in_str = ' <a style="color:' + client.instance.get_color("url") + '" href="' + \
                     client.instance.urls[name].toString() + '">' + self.title + '</a> on "' + self.mapdisplayname + '"'
            if self.mod != "faf":
                in_str = ' ' + self.mod + in_str
            client.instance.forward_local_broadcast(name, 'joined' + in_str)
        else:  # at client start all players who are friends ... of course
            for player in self.players:
                if client.instance.players.is_friend(player.login):
                    in_str = ' <a style="color:' + client.instance.get_color("url") + '" href="' + \
                         client.instance.urls[player.login].toString() + '">' + self.title + '</a> on "' + \
                         self.mapdisplayname + '"'
                    if self.mod != "faf":
                        in_str = ' ' + self.mod + in_str
                    client.instance.forward_local_broadcast(player.login, 'joined' + in_str)

    def update(self, message):
        """
        Updates this item from the message dictionary supplied
        """

        self.title = message['title']  # can be renamed in Lobby (now)

        if self.host == "":  # new game
            self.host = message['host']
            self.password_protected = message.get('password_protected', False)
            self.mod = message['featured_mod']
        elif self.host != message['host']:  # somethings funny (offline)
            self.host = message['host']

        if 'host_id' in message:  # then we would take that (but that never happens...)
            self.host_id = message['host_id']
        elif self.host_id == -1:  # fresh game
            self.host_id = client.instance.players.get_id(self.host)
        elif self.host_id != client.instance.players.get_id(self.host):  # somethings funny (offline)
            self.host_id = client.instance.players.get_id(self.host)

        # Map preview code
        if self.mapname != message['mapname']:
            self.mapname = message['mapname']
            self.mapdisplayname = str(maps.get_display_name(self.mapname))
            refresh_map_icon = True
        else:
            refresh_map_icon = False

        old_state = self.state
        self.state = message['state']

        self.setHidden((self.state != 'open') or (self.mod in mod_invisible))

        # Clear the status for all involved players (url may change, or players may have left, or game closed)        
        for player in self.players:
            if player.login in client.instance.urls:
                del client.instance.urls[player.login]

        # Just jump out if we've left the game, but tell the client that all players need their states updated
        if self.state == "closed":
            client.instance.usersUpdated.emit(self.players)
            return

        # Maps integral team numbers (from 2, with 1 "none") to lists of names.
        teams_map = dict.copy(message['teams'])

        # Used to differentiate between newly added / removed and previously present players
        old_players = set([p.login for p in self.players])

        # Following the convention used by the game, a team value of 1 represents "No team". Let's
        # desugar those into "real" teams now (and convert the dict to a list)
        # Also, turn the lists of names into lists of players, and build a player name list.
        self.players = []  # list of all players in all teams (without observers)
        teams = []  # list of teams of list of players in team (without observers)
        observers = []  # list of observers
        for team_index in teams_map:
            if team_index == u'-1' or team_index == u'null':  # observers (we hope)
                for name in teams_map[team_index]:
                    observers.append(name)
            else:  # everything else - faf, ffa and other mods
                real_team = []
                for name in teams_map[team_index]:
                    if name in client.instance.players:
                        self.players.append(client.instance.players[name])
                        real_team.append(client.instance.players[name])
                teams.append(real_team)

        if self.state == "open":  # things only needed while hosting

            # self.modVersion = message.get('featured_mod_versions', [])  # in message but not used
            self.mods = message.get('sim_mods', {})  # -> editTooltip
            # self.options = message.get('options', [])  # not in message and not used
            num_players = message.get('num_players', 0)
            slots = message.get('max_players', 12)

            # Alternate icon: If private game, use game_locked icon. Otherwise, use preview icon from map library.
            if refresh_map_icon:
                if self.password_protected:
                    icon = util.icon("games/private_game.png")
                else:
                    icon = maps.preview(self.mapname)
                    if not icon:
                        client.instance.downloader.download_map(self.mapname, self)
                        icon = util.icon("games/unknown_map.png")

                self.setIcon(icon)

            # Extra teams + observer info
            if len(teams) > 1:
                # list of team sizes
                team_list = []
                for team in teams:
                    team_list.append(str(len(team)))

                team_str = "<font size='-1'> in </font>" + " vs ".join(team_list)
            elif len(teams) == 1:  # only one team
                if len(observers) > 0:  # only extra info if also observer
                    team_str = "<font size='-1'> in </font>" + str(len(teams[0]))
                else:  # all in one team no observer -> no extra info
                    team_str = ""
            else:  # no team
                team_str = ""
            if len(observers) > 0:
                team_str += "<font size='-1'> + " + str(len(observers)) + " O.</font>"

            if self.host_id == -1:  # user offline (?)
                ol = " <font color='darkred'>(offline)</font>"
            else:
                ol = ""
            color = client.instance.players.get_user_color(self.host_id)

            self.edit_tooltip(teams, observers)

            if self.mod == "faf" or self.mod == "coop":
                self.setText(self.FORMATTER_FAF.format(color=color, mapslots=slots, mapdisplayname=self.mapdisplayname,
                                                       title=self.title, host=self.host + ol, players=num_players,
                                                       teams=team_str, avgrating=self.average_rating,
                                                       devrating=self.deviation_rating))
            else:
                self.setText(self.FORMATTER_MOD.format(color=color, mapslots=slots, mapdisplayname=self.mapdisplayname,
                                                       title=self.title, host=self.host + ol, players=num_players,
                                                       teams=team_str, mod=self.mod, avgrating=self.average_rating,
                                                       devrating=self.deviation_rating))
        elif self.state != "playing":
            self.state = "funky"

        # Spawn announcers: IF we had a gamestate change, show replay and hosting announcements
        if old_state != self.state:
            if self.state == "playing":  # The delay is there because we have a 5 minutes delay in the livereplay server
                self.launched_at = message['launched_at']
                if time.time() - self.launched_at > 5*60:  # most games after client start
                    QtCore.QTimer().singleShot(4000, self.announce_replay)
                else:
                    QtCore.QTimer().singleShot(1000*(5*60 - (time.time() - self.launched_at)), self.announce_replay)
            elif self.state == "open":  # The 5s delay is there because the host needs time to set up
                QtCore.QTimer().singleShot(3000, self.announce_hosting)

        # Update player URLs
        for player in self.players:
            client.instance.urls[player.login] = self.url(player.id)
            if old_state and player.login != self.host and player.login not in old_players:
                self.announce_joining(player.login)

        if not old_state:  # announce all on client start
            QtCore.QTimer().singleShot(3500, self.announce_joining)

        # Determine which players are affected by this game's state change            
        new_players = set([p.login for p in self.players])
        affected_players = old_players | new_players
        client.instance.usersUpdated.emit(list(affected_players))

    def edit_tooltip(self, teams, observers):

        teams_list = []
        for i, team in enumerate(teams, start=1):
            players_list = ["<td><table>"]
            for player in team:

                if player == client.instance.me:
                    player_str = "<b><i>%s</b></i>" % player.login
                else:
                    player_str = player.login

                if player.rating_deviation < 200:
                    player_str += " (%s)" % str(player.rating_estimate())

                country = os.path.join(util.COMMON_DIR, "chat/countries/%s.png" % (player.country or '').lower())

                if i == 1:
                    player_html = "<tr><td><img src='%s'></td><td align='left' " \
                                    "valign='middle' width='135'>%s</td></tr>" % (country, player_str)
                elif i == len(teams):
                    player_html = "<tr><td align='right' valign='middle' width='135'>%s</td>" \
                                    "<td><img src='%s'></td></tr>" % (player_str, country)
                else:
                    player_html = "<tr><td><img src='%s'></td><td align='center' " \
                                    "valign='middle' width='135'>%s</td></tr>" % (country, player_str)

                players_list.append(player_html)

            players_list.append("</table></td>")
            team_html = "".join(players_list)

            teams_list.append(team_html)

        teams_str = "<td valign='middle' height='100%'><font color='black' size='+5'>VS</font></td>".join(teams_list)

        if len(observers) != 0:
            observers_str = "Observers : " + ", ".join(observers)
        else:
            observers_str = ""

        if self.mods:
            mods_str = "<br />With mod: " + "<br />".join(list(self.mods.values()))
        else:
            mods_str = ""

        self.setToolTip(self.FORMATTER_TOOL.format(teams=teams_str, observers=observers_str, mods=mods_str))

    def __ge__(self, other):
        """ Comparison operator used for item list sorting """
        return not self.__lt__(other)

    def __lt__(self, other):
        """ Comparison operator used for item list sorting """
        if not client.instance:
            return True  # If not initialized...

        # Friend games are on top
        if self.host_id == -1:
            self_is_friend = False
        else:
            self_is_friend = client.instance.players.is_friend(self.host_id)
        if other.host_id == -1:
            other_is_friend = False
        else:
            other_is_friend = client.instance.players.is_friend(other.host_id)
        if self_is_friend and not other_is_friend:
            return True
        if not self_is_friend and other_is_friend:
            return False

        # Sort Games
        # 0: By Player Count
        # 1: By avg. Player Rating
        # 2: By Map
        # 3: By Host
        # 4+: By Age = uid
        try:
            sort_by = self.listWidget().sortBy
        except AttributeError:
            sort_by = 99  # coopWidget has no .sortBy
        if sort_by == 0:
            return len(self.players) > len(other.players)
        elif sort_by == 1:
            return self.average_rating > other.average_rating
        elif sort_by == 2:
            return self.mapdisplayname.lower() < other.mapdisplayname.lower()
        elif sort_by == 3:
            return self.host.lower() < other.host.lower()
        else:
            # Default: by UID.
            return self.uid < other.uid

    @property
    def average_rating(self):
        return sum([p.rating_estimate() for p in self.players]) / max(len(self.players), 1)

    @property
    def deviation_rating(self):
        return int((sum([(self.average_rating - p.rating_estimate())**2 for p in self.players]) /
                    max(len(self.players), 1))**0.5)
