

from PyQt4 import QtCore, QtGui, QtWebKit
import util
from stats import mapstat
from config import Settings
import client
import time

import logging
logger = logging.getLogger(__name__)

ANTIFLOOD = 0.1

FormClass, BaseClass = util.load_ui_type("stats/stats.ui")


class StatsWidget(BaseClass, FormClass):

    # signals
    laddermaplist = QtCore.pyqtSignal(dict)
    laddermapstat = QtCore.pyqtSignal(dict)

    def __init__(self):
        super(BaseClass, self).__init__()

        self.setupUi(self)

        client.instance.ladderTab.layout().addWidget(self)
        
        client.instance.lobby_info.statsInfo.connect(self.process_stats_infos)

        self.webview = QtWebKit.QWebView()
        
        self.LadderRatings.layout().addWidget(self.webview)
        
        self.loaded = False
        client.instance.showLadder.connect(self.updating)
        self.webview.loadFinished.connect(self.webview.show)
        self.leagues.currentChanged.connect(self.league_update)
        self.pagesDivisions = {}
        self.pagesDivisionsResults = {}
        self.pagesAllLeagues = {}
        
        self.floodtimer = time.time()
        
        self.currentLeague = 0
        self.currentDivision = 0

        self.FORMATTER_LADDER = unicode(util.readfile("stats/formatters/ladder.qthtml"))
        self.FORMATTER_LADDER_HEADER = unicode(util.readfile("stats/formatters/ladder_header.qthtml"))

        util.set_stylesheet(self.leagues, "stats/formatters/style.css")
    
        # setup other tabs
        self.mapstat = mapstat.LadderMapStat(self)

    @QtCore.pyqtSlot(int)
    def league_update(self, index):
        self.currentLeague = index + 1
        league_tab = self.leagues.widget(index).findChild(QtGui.QTabWidget, "league"+str(index))
        if league_tab:
            if league_tab.currentIndex() == 0:
                if time.time() - self.floodtimer > ANTIFLOOD:
                    self.floodtimer = time.time() 
                    client.instance.statsServer.send(dict(command="stats", type="league_table", league=self.currentLeague))

    @QtCore.pyqtSlot(int)
    def divisions_update(self, index):
        if index == 0:
            if time.time() - self.floodtimer > ANTIFLOOD:
                self.floodtimer = time.time()
                client.instance.statsServer.send(dict(command="stats", type="league_table", league=self.currentLeague))
        
        elif index == 1:
            tab = self.currentLeague - 1
            if tab not in self.pagesDivisions:
                    client.instance.statsServer.send(dict(command="stats", type="divisions", league=self.currentLeague))
        
    @QtCore.pyqtSlot(int)
    def division_update(self, index):
        if time.time() - self.floodtimer > ANTIFLOOD:
            self.floodtimer = time.time()
            client.instance.statsServer.send(dict(command="stats", type="division_table", league=self.currentLeague, division=index))

    def create_divisions_tabs(self, divisions):
        user_division = ""
        me = client.instance.me
        if me.league is not None:  # was me.division, but no there there
            user_division = me.league[1]  # ? [0]=league and [1]=division

        pages = QtGui.QTabWidget()

        found_division = False

        for division in divisions:
            name = division["division"]
            index = division["number"]
            league = division["league"]
            widget = QtGui.QTextBrowser()
            
            if league not in self.pagesDivisionsResults:
                self.pagesDivisionsResults[league] = {}

            self.pagesDivisionsResults[league][index] = widget 

            pages.insertTab(index, widget, name)

            if name == user_division:
                found_division = True
                pages.setCurrentIndex(index)
                client.instance.statsServer.send(dict(command="stats", type="division_table", league=league, division=index))

        if not found_division:
            client.instance.statsServer.send(dict(command="stats", type="division_table", league=league, division=0))

        pages.currentChanged.connect(self.division_update)
        return pages

    def create_results(self, values, table):

        formatter = self.FORMATTER_LADDER
        formatter_header = self.FORMATTER_LADDER_HEADER
        glist = []
        append = glist.append
        # append("<table style='color:#3D3D3D' cellspacing='0' cellpadding='4' width='100%' height='100%'><tbody>")
        append("<style> .maintbl { color: #3D3D3D; }</style>")  # style option
        append("<table class='maintbl' cellspacing='0' cellpadding='4'><tbody>")  # style option
        append(formatter_header.format(rank="rank", name="name", score="score", color="#92C1E4"))

        for val in values:
            rank = val["rank"]
            name = val["name"]
            score = str(val["score"])
            if client.instance.login == name:
                append(formatter.format(rank=str(rank), name=name, score=score, color="#6CF"))
            elif rank % 2 == 0:
                append(formatter.format(rank=str(rank), name=name, score=str(val["score"]), color="#F1F1F1"))
            else:
                append(formatter.format(rank=str(rank), name=name, score=str(val["score"]), color="#D8D8D8"))

        append("</tbody></table>")
        html = "".join(glist)

        table.setHtml(html)
        
        table.verticalScrollBar().setValue(table.verticalScrollBar().minimum())
        return table

    @QtCore.pyqtSlot(dict)
    def process_stats_infos(self, message):

        type_stat = message["type"]
        if type_stat == "divisions":
            self.currentLeague = message["league"]
            tab = self.currentLeague - 1

            if tab not in self.pagesDivisions:
                self.pagesDivisions[tab] = self.create_divisions_tabs(message["values"])
                league_tab = self.leagues.widget(tab).findChild(QtGui.QTabWidget, "league"+str(tab))
                league_tab.widget(1).layout().addWidget(self.pagesDivisions[tab])

        elif type_stat == "division_table":
            self.currentLeague = message["league"]
            self.currentDivision = message["division"]

            if self.currentLeague in self.pagesDivisionsResults:
                if self.currentDivision in self.pagesDivisionsResults[self.currentLeague]:
                    self.create_results(message["values"], self.pagesDivisionsResults[self.currentLeague][self.currentDivision])
                    
        elif type_stat == "league_table":
            self.currentLeague = message["league"]
            tab = self.currentLeague - 1
            if tab not in self.pagesAllLeagues:
                table = QtGui.QTextBrowser()
                self.pagesAllLeagues[tab] = self.create_results(message["values"], table)
                league_tab = self.leagues.widget(tab).findChild(QtGui.QTabWidget, "league"+str(tab))
                league_tab.currentChanged.connect(self.divisions_update)
                league_tab.widget(0).layout().addWidget(self.pagesAllLeagues[tab])

        elif type == "ladder_maps":  # from old HardlySofly commit
            self.laddermaplist.emit(message)

        elif type_stat == "ladder_map_stat":
            self.laddermapstat.emit(message)

    @QtCore.pyqtSlot()
    def updating(self):
        # Don't display things when we're not logged in
        # FIXME - one day we'll have more obvious points of entry
        if self.client.state != client.ClientState.LOGGED_IN:
            return

        client.instance.statsServer.send(dict(command="stats", type="ladder_maps", mapid=0))  # from old HardlySofly commit +.statsServer

        me = client.instance.players[client.instance.login]
        if me.league is not None:
            self.leagues.setCurrentIndex(me.league - 1)
        else:
            self.leagues.setCurrentIndex(5)  # -> 5 = direct to Ladder Ratings

        if self.loaded:
            return

        self.loaded = True
        
        self.webview.setVisible(False)

        # If a local theme CSS exists, skin the WebView with it
        if util.themeurl("ladder/style.css"):
            self.webview.settings().setUserStyleSheetUrl(util.themeurl("ladder/style.css"))

        self.webview.setUrl(QtCore.QUrl("{}/faf/leaderboards/read-leader.php?board=1v1&username={}".
                                        format(Settings.get('content/host'), me.login)))
