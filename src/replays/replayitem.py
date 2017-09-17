import os
import time

import util
import client
from PyQt4 import QtCore, QtGui

from config import Settings
from fa import maps
from games.moditem import mods


class ReplayItemDelegate(QtGui.QStyledItemDelegate):

    def __init__(self, *args, **kwargs):
        QtGui.QStyledItemDelegate.__init__(self, *args, **kwargs)

    def paint(self, painter, option, index, *args, **kwargs):
        self.initStyleOption(option, index)

        painter.save()

        html = QtGui.QTextDocument()
        html.setHtml(option.text)

        icon = QtGui.QIcon(option.icon)
        iconsize = icon.actualSize(option.rect.size())

        # clear icon and text before letting the control draw itself because we're rendering these parts ourselves
        option.icon = QtGui.QIcon()        
        option.text = ""  
        option.widget.style().drawControl(QtGui.QStyle.CE_ItemViewItem, option, painter, option.widget)

        # Shadow
        # painter.fillRect(option.rect.left()+8-1, option.rect.top()+8-1, iconsize.width(), iconsize.height(),
        #                  QtGui.QColor("#202020"))

        # Icon
        icon.paint(painter, option.rect.adjusted(5-2, -2, 0, 0), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        # Frame around the icon
#        pen = QtGui.QPen()
#        pen.setWidth(1)
#        pen.setBrush(QtGui.QColor("#303030"))
#        pen.setCapStyle(QtCore.Qt.RoundCap)
#        painter.setPen(pen)
#        painter.drawRect(option.rect.left()+5-2, option.rect.top()+5-2, iconsize.width(), iconsize.height())

        # Description
        painter.translate(option.rect.left() + iconsize.width() + 10, option.rect.top() + 10)
        clip = QtCore.QRectF(0, 0, option.rect.width()-iconsize.width() - 10 - 5, option.rect.height() - 10)
        html.drawContents(painter, clip)

        painter.restore()

    def sizeHint(self, option, index, *args, **kwargs):
        # width onlineTree = 550
        if index.model().data(index, QtCore.Qt.UserRole):  # Replay
            return QtCore.QSize(0, 70)
        else:  # Date
            return QtCore.QSize(0, 35)


class ReplayItem(QtGui.QTreeWidgetItem):

    def __init__(self, uid, parent, *args):
        QtGui.QTreeWidgetItem.__init__(self, *args)

        self.uid = uid
        self.parent = parent
        self.viewtext = None
        self.mapname = None
        self.mapdisplayname = None
        self.icon = None
        self.title = None
        self.host = None
        self.mod = None
        self.moddisplayname = None
        self.url = "{}/faf/vault/replay_vault/replay.php?id={}".format(Settings.get('content/host'), self.uid)

        self.startDate = None
        self.duration = None
        self.live_delay = False
        self.setHidden(True)

        self.detail_info = False  # detail replay info was read from server
        self.teams = {}
        self.playercount = 0
        self.biggestTeam = 0
        self.winner = None
        self.teamWin = None

        self.detail_info_html = ""  # html text for replayInfos
        self.detail_info_spoiled_html = ""  # html text for replayInfos
        self.detail_info_width = 0  # width of replayInfos
        self.detail_info_height = 0  # height of replayInfos

    def update(self, message, formatter):
        """ Updates this item from the message dictionary supplied """

        self.title = message["name"]
        self.mapname = message["map"]
        if message['end'] == 4294967295:  # = FFFF FFFF (year 2106) aka still playing
            seconds = time.time()-message['start']
            if seconds > 86400:  # more than 24 hours
                self.duration = "<font color='darkgrey'>end time<br />&nbsp;missing</font>"
            elif seconds > 7200:  # more than 2 hours
                self.duration = time.strftime('%H:%M:%S', time.gmtime(seconds)) + "<br />?playing?"
            elif seconds < 300:  # less than 5 minutes
                self.duration = time.strftime('%H:%M:%S', time.gmtime(seconds)) + "<br />&nbsp;" \
                                                                                  "<font color='darkred'>playing</font>"
                self.live_delay = True
            else:
                self.duration = time.strftime('%H:%M:%S', time.gmtime(seconds)) + "<br />&nbsp;playing"
        else:
            self.duration = time.strftime('%H:%M:%S', time.gmtime(message["duration"]))
        starthour = time.strftime("%H:%M", time.localtime(message['start']))
        self.startDate = time.strftime("%Y-%m-%d", time.localtime(message['start']))
        self.mod = message["mod"]

        # Map preview code
        if self.mapname:
            self.mapdisplayname = str(maps.get_display_name(self.mapname))

            self.icon = maps.preview(self.mapname)
            if not self.icon:
                client.instance.downloader.download_map(self.mapname, self, True)
                self.icon = util.icon("games/unknown_map.png")
        else:
            self.mapdisplayname = "{unknown}"
            self.icon = util.icon("games/unknown_map.png")

        if self.mod in mods:
            self.moddisplayname = mods[self.mod].name 
        else:
            self.moddisplayname = self.mod

        self.viewtext = formatter.format(time=starthour, name=self.title, map=self.mapdisplayname,
                                         duration=self.duration, mod=self.moddisplayname)

    def info_players(self, players):
        """ processes information from the server about a replay into readable extra information for the user,
                also calls method to show the information """

        self.detail_info = True
        self.playercount = len(players)
        mvpscore = 0
        mvp = None
        scores = {}

        for player in players:  # player highscore
            if "score" in player:
                if player["score"] > mvpscore:
                    mvp = player
                    mvpscore = player["score"]

        for player in players:  # player -> teams & player_score -> teamscore
            if self.mod == "phantomx" or self.mod == "murderparty":  # get ffa like into one team
                team = 1
            else:
                team = int(player["team"])

            if "score" in player:
                if team in scores:
                    scores[team] = scores[team] + player["score"]
                else:
                    scores[team] = player["score"]
            if team not in self.teams:
                self.teams[team] = [player]
            else:
                self.teams[team].append(player)

        if self.playercount > 2 and self.playercount == len(self.teams):  # some kind of FFA
            # redo teams with all players in team (1)
            self.teams = {}
            scores = {}
            team = 1
            for player in players:  # player -> team (1)
                if team not in self.teams:
                    self.teams[team] = [player]
                else:
                    self.teams[team].append(player)

        if len(self.teams) == 1 or self.playercount > 2 and self.playercount == len(self.teams):  # it's FFA
            self.winner = mvp
        elif len(scores) > 0:  # team highscore
            mvt = 0
            for team in scores:
                if scores[team] > mvt:
                    self.teamWin = team
                    mvt = scores[team]

        self.generate_info_players_html()

    def generate_info_players_html(self):
        """  Creates the ui and extra information about a replay,
             Either teamWin or winner must be set if the replay is to be spoiled """

        spoiled = not self.parent.spoiler_free

        # check if we done that, been there... then we don't do it again.
        if spoiled and self.detail_info_spoiled_html == "" or not spoiled and self.detail_info_html == "":
            teams = ""
            winner_html = ""
            i = 0
            for team in self.teams:
                if team != -1:
                    i += 1

                    if len(self.teams[team]) > self.biggestTeam:  # for height of Infobox
                        self.biggestTeam = len(self.teams[team])

                    players = ""
                    for player in self.teams[team]:
                        alignment, player_icon, player_label, player_score = self.generate_player_html(i, player, spoiled)

                        if self.winner is not None and player["score"] == self.winner["score"] and spoiled:
                            winner_html += "<tr>%s%s%s</tr>" % (player_score, player_icon, player_label)
                        elif alignment == "left":
                            players += "<tr>%s%s%s</tr>" % (player_score, player_icon, player_label)
                        else:  # alignment == "right"
                            players += "<tr>%s%s%s</tr>" % (player_label, player_icon, player_score)

                    if spoiled:
                        if self.winner is not None:  # FFA in rows: Win ... Lose ...
                            if "playing" in self.duration:
                                teams += "<tr><td colspan='3' align='center' valign='middle'><font size='+2'>Playing" \
                                         "</font></td></tr>%s%s" % (winner_html, players)
                            else:
                                teams += "<tr><td colspan='3' align='center' valign='middle'><font size='+2'>Win" \
                                         "</font></td></tr>%s<tr><td colspan=3 align='center' valign='middle'>" \
                                         "<font size='+2'>Lose</font></td></tr>%s" % (winner_html, players)
                        else:
                            if "playing" in self.duration:
                                team_title = "Playing"
                            elif self.teamWin == team:
                                team_title = "Win"
                            else:
                                team_title = "Lose"

                            if len(self.teams) == 2:  # pack team in <table>
                                teams += "<td><table border=0><tr><td colspan='3' align='center' valign='middle'>" \
                                         "<font size='+2'>%s</font></td></tr>%s</table></td>" % (team_title, players)
                            else:  # just one row
                                teams += "<tr><td colspan='3' align='center' valign='middle'>" \
                                         "<font size='+2'>%s</font></td></tr>%s" % (team_title, players)
                    else:
                        if len(self.teams) == 2:  # pack team in <table>
                            teams += "<td><table border=0><tr><td colspan='3' align='center' valign='middle'>" \
                                         "<font size='+2'>&nbsp;</font></td></tr>%s</table></td>" % players
                        else:  # just one row
                            if i == 1:  # extra (empty) line between uid and players
                                teams += "<tr><td colspan='3' align='center' valign='middle'>" \
                                         "<font size='+2'>&nbsp;</font></td></tr>"
                            teams += players

                    if len(self.teams) == 2 and i == 1:  # add the 'VS'
                        teams += "<td align='center' valign='middle' height='100%'>" \
                                 "<font color='black' size='+4'>VS</font></td>"

            if len(self.teams) == 2:  # prepare the package to 'fit in' with its <td>s
                teams = "<tr>%s</tr>" % teams

            info_html = "<h2 align='center'>Replay UID : %s</h2><table border='0' cellpadding='0' " \
                        "cellspacing='5' align='center'><tbody>%s</tbody></table>" % (self.uid, teams)

            if spoiled:
                self.detail_info_spoiled_html = info_html
            else:
                self.detail_info_html = info_html

        self.parent.replayInfos.clear()

        if not self:
            return

        if self.isSelected():
            self.resize()
            if spoiled:
                self.parent.replayInfos.setHtml(self.detail_info_spoiled_html)
            else:
                self.parent.replayInfos.setHtml(self.detail_info_html)

    def generate_player_html(self, i, player, spoiled):
        place = ["F", "R", "B", "A"]  # Start positions on Seton's Clutch
        if i == 2 and len(self.teams) == 2:
            align = "right"
        else:
            align = "left"

        label = "<td align='%s' valign='middle' width='130'>%s (%s)</td>" % (align, player["name"], player["rating"])

        icon_url = os.path.join(util.COMMON_DIR, "replays/%s.png" % self.retrieve_faction(player, self.mod))

        icon = "<td width='40'><img src='file:///%s' width='40' height='20'></td>" % icon_url

        if spoiled:  # and not self.mod == "ladder1v1":
            if self.mapname == "scmp_009":  # Seton's Clutch - add positions
                if align == "right":
                    score = "<td align='left' valign='middle' width='25'>%s %s</td>" % (
                        place[int(0.5 * (player["place"])-1)], player["score"])
                else:
                    score = "<td align='right' valign='middle' width='25'>%s %s</td>" % (
                        player["score"], place[int(0.5*(player["place"]-1))])
            else:
                score = "<td align='center' valign='middle' width='20'>%s</td>" % player["score"]
        else:  # no score for ladder
            score = "<td align='center' valign='middle' width='20'> </td>"

        return align, icon, label, score

    @staticmethod
    def retrieve_faction(player, mod):
        if "faction" in player:
            if player["faction"] == 1:
                faction = "UEF"
            elif player["faction"] == 2:
                faction = "Aeon"
            elif player["faction"] == 3:
                faction = "Cybran"
            elif player["faction"] == 4:
                faction = "Seraphim"
            elif player["faction"] == 5:
                if mod == "nomads":
                    faction = "Nomads"
                else:
                    faction = "Random"
            elif player["faction"] == 6:
                if mod == "nomads":
                    faction = "Random"
                else:
                    faction = "Broken"
            else:
                faction = "Broken"
        else:
            faction = "Missing"
        return faction

    def resize(self):
        if self.isSelected():
            if self.detail_info_width == 0 or self.detail_info_height == 0:
                if len(self.teams) == 1:  # ladder, FFA
                    self.detail_info_width = 275
                    self.detail_info_height = 75 + (self.playercount + 1) * 25  # + 1 -> second title
                elif len(self.teams) == 2:  # Team vs Team
                    self.detail_info_width = 500
                    self.detail_info_height = 75 + self.biggestTeam * 22
                else:  # FAF
                    self.detail_info_width = 275
                    self.detail_info_height = 75 + (self.playercount + len(self.teams)) * 25

            self.parent.replayInfos.setMinimumWidth(self.detail_info_width)
            self.parent.replayInfos.setMaximumWidth(600)

            self.parent.replayInfos.setMinimumHeight(self.detail_info_height)
            self.parent.replayInfos.setMaximumHeight(self.detail_info_height)

    def pressed(self):
        menu = QtGui.QMenu(self.parent)
        action_download = QtGui.QAction("Download replay", menu)
        action_download.triggered.connect(self.download_replay)
        menu.addAction(action_download)
        menu.popup(QtGui.QCursor.pos())

    def download_replay(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(self.url))

    def data(self, column, role):
        if role == QtCore.Qt.DisplayRole:
            return self.viewtext
        elif role == QtCore.Qt.UserRole:
            return self
        return super(ReplayItem, self).data(column, role)

    def __ge__(self, other):
        """  Comparison operator used for item list sorting """
        return not self.__lt__(other)

    def __lt__(self, other):
        """ Comparison operator used for item list sorting """
        # Default: uid
        return self.uid < other.uid
