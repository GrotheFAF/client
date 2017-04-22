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
        clip = QtCore.QRectF(0, 0, option.rect.width()-iconsize.width() - 10 - 5, option.rect.height())
        html.drawContents(painter, clip)

        painter.restore()

    def sizeHint(self, option, index, *args, **kwargs):
        clip = index.model().data(index, QtCore.Qt.UserRole)
        self.initStyleOption(option, index)
        html = QtGui.QTextDocument()
        html.setHtml(option.text)
        html.setTextWidth(240)
        if clip:
            return QtCore.QSize(215, clip.height)
        else:
            return QtCore.QSize(215, 35)


class ReplayItem(QtGui.QTreeWidgetItem):

    FORMATTER_REPLAY = unicode(util.readfile("replays/formatters/replay.qthtml"))

    def __init__(self, uid, parent, *args):
        QtGui.QTreeWidgetItem.__init__(self, *args)

        self.uid = uid
        self.parent = parent
        self.height = 70
        self.viewtext = None
        self.viewtextPlayer = None
        self.mapname = None
        self.mapdisplayname = None
        self.icon = None
        self.title = None
        self.host = None
        self.mod = None
        self.moddisplayname = None

        self.startDate = None
        self.duration = None
        self.live_delay = False

        self.moreInfo = False
        self.replayInfo = False
        self.spoiled = False
        self.url = "{}/faf/vault/replay_vault/replay.php?id={}".format(Settings.get('content/host'), self.uid)

        self.teams = {}
        self.access = None

        self.options = []
        # self.players = []
        self.playercount = 0
        self.biggestTeam = 0
        self.winner = None
        self.teamWin = None

        self.setHidden(True)
        self.extraInfoWidth = 0  # panel with more information
        self.extraInfoHeight = 0  # panel with more information

    def update(self, message):
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
        self.mapdisplayname = maps.get_display_name(self.mapname)

        self.icon = maps.preview(self.mapname)
        if not self.icon:
            client.instance.downloader.download_map(self.mapname, self, True)
            self.icon = util.icon("games/unknown_map.png")

        if self.mod in mods:
            self.moddisplayname = mods[self.mod].name 
        else:
            self.moddisplayname = self.mod

        self.viewtext = self.FORMATTER_REPLAY.format(time=starthour, name=self.title, map=self.mapdisplayname,
                                                     duration=self.duration, mod=self.moddisplayname)

    def info_players(self, players):
        """ processes information from the server about a replay into readable extra information for the user,
                also calls method to show the information """

        self.moreInfo = True
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

        if self.playercount == len(self.teams):  # some kind of FFA
            self.teams = {}
            scores = {}
            team = 1
            for player in players:  # player -> team (1)
                if team not in self.teams:
                    self.teams[team] = [player]
                else:
                    self.teams[team].append(player)

        if len(self.teams) == 1 or len(self.teams) == len(players):  # it's FFA
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

        teams = ""
        winner_html = ""

        self.spoiled = not self.parent.spoilerCheckbox.isChecked()

        i = 0
        for team in self.teams:
            if team != -1:
                i += 1

                if len(self.teams[team]) > self.biggestTeam:  # for height of Infobox
                    self.biggestTeam = len(self.teams[team])

                players = ""
                for player in self.teams[team]:
                    alignment, player_icon, player_label, player_score = self.generate_player_html(i, player)

                    if self.winner is not None and player["score"] == self.winner["score"] and self.spoiled:
                        winner_html += "<tr>%s%s%s</tr>" % (player_score, player_icon, player_label)
                    elif alignment == "left":
                        players += "<tr>%s%s%s</tr>" % (player_score, player_icon, player_label)
                    else:  # alignment == "right"
                        players += "<tr>%s%s%s</tr>" % (player_label, player_icon, player_score)

                if self.spoiled:
                    if self.winner is not None:  # FFA in rows: Win ... Lose ...
                        if "playing" in self.duration:
                            teams += "<tr><td colspan='3' align='center' valign='middle'><font size='+2'>Playing" \
                                     "</font></td></tr>%s%s" % (winner_html, players)
                        else:
                            teams += "<tr><td colspan='3' align='center' valign='middle'><font size='+2'>Win</font>" \
                                     "</td></tr>%s<tr><td colspan=3 align='center' valign='middle'><font size='+2'>" \
                                     "Lose</font></td></tr>%s" % (winner_html, players)
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

        self.replayInfo = "<h2 align='center'>Replay UID : %s</h2><table border='0' cellpadding='0' cellspacing='5'" \
                          " align='center'><tbody>%s</tbody></table>" % (self.uid, teams)

        if self.isSelected():
            self.parent.replayInfos.clear()
            self.resize()
            self.parent.replayInfos.setHtml(self.replayInfo)

    def generate_player_html(self, i, player):
        if i == 2 and len(self.teams) == 2:
            align = "right"
        else:
            align = "left"

        label = "<td align='%s' valign='middle' width='130'>%s (%s)</td>" % (align, player["name"], player["rating"])

        icon_url = os.path.join(util.COMMON_DIR, "replays/%s.png" % self.retrieve_faction(player, self.mod))

        icon = "<td width='40'><img src='file:///%s' width='40' height='20'></td>" % icon_url

        if self.spoiled and not self.mod == "ladder1v1":
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
            if self.extraInfoWidth == 0 or self.extraInfoHeight == 0:
                if len(self.teams) == 1:  # ladder, FFA
                    self.extraInfoWidth = 275
                    self.extraInfoHeight = 75 + (self.playercount + 1) * 25  # + 1 -> second title
                elif len(self.teams) == 2:  # Team vs Team
                    self.extraInfoWidth = 500
                    self.extraInfoHeight = 75 + self.biggestTeam * 22
                else:  # FAF
                    self.extraInfoWidth = 275
                    self.extraInfoHeight = 75 + (self.playercount + len(self.teams)) * 25

            self.parent.replayInfos.setMinimumWidth(self.extraInfoWidth)
            self.parent.replayInfos.setMaximumWidth(600)

            self.parent.replayInfos.setMinimumHeight(self.extraInfoHeight)
            self.parent.replayInfos.setMaximumHeight(self.extraInfoHeight)

    def pressed(self, item):
        menu = QtGui.QMenu(self.parent)
        action_download = QtGui.QAction("Download replay", menu)
        action_download.triggered.connect(self.download_replay)
        menu.addAction(action_download)
        menu.popup(QtGui.QCursor.pos())

    def download_replay(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(self.url))

    def display(self, column):
        if column == 0:
            return self.viewtext
        if column == 1:
            return self.viewtext

    def data(self, column, role):
        if role == QtCore.Qt.DisplayRole:
            return self.display(column)
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
