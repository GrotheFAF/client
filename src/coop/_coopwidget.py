from PyQt4 import QtCore, QtGui
from fa.replay import replay
from fa.wizards import WizardSC
import util

from PyQt4.QtNetwork import QNetworkAccessManager, QNetworkRequest

from games.gameitem import GameItem, GameItemDelegate
from coop.coopmapitem import CoopMapItem, CoopMapItemDelegate
from games.hostgamewidget import HostGameWidget
import fa
import client
import os

import logging
logger = logging.getLogger(__name__)


FormClass, BaseClass = util.load_ui_type("coop/coop.ui")


class CoopWidget(FormClass, BaseClass):

    FORMATTER_COOP = util.readfile("coop/formatters/coop.qthtml")

    def __init__(self, *args, **kwargs):
        
        BaseClass.__init__(self, *args, **kwargs)        
        
        self.setupUi(self)

        client.instance.coopTab.layout().addWidget(self)
        
        # Dictionary containing our actual games.
        self.games = {}
        
        # Ranked search UI
        self.ispassworded = False
        self.loaded = False
        
        self.coop = {}
        self.cooptypes = {}
        
        self.options = []
        
        client.instance.showCoop.connect(self.coop_changed)
        client.instance.lobby_info.coopInfo.connect(self.process_coop_info)
        client.instance.lobby_info.gameInfo.connect(self.process_game_info)
        self.coopList.header().setResizeMode(0, QtGui.QHeaderView.ResizeToContents)
        self.coopList.setItemDelegate(CoopMapItemDelegate(self))

        self.gameList.setItemDelegate(GameItemDelegate(self))
        self.gameList.itemDoubleClicked.connect(self.game_doubleclicked)

        self.coopList.itemDoubleClicked.connect(self.coop_list_doubleclicked)
        self.coopList.itemClicked.connect(self.coop_list_clicked)
        
        client.instance.lobby_info.coopLeaderBoard.connect(self.process_leaderboard_infos)
        self.tabLeaderWidget.currentChanged.connect(self.ask_leaderboard)
        
        self.linkButton.clicked.connect(self.link_vanilla)
        self.leaderBoard.setVisible(0)
        self.FORMATTER_LADDER = util.readfile("coop/formatters/ladder.qthtml")
        self.FORMATTER_LADDER_HEADER = util.readfile("coop/formatters/ladder_header.qthtml")

        util.set_stylesheet(self.leaderBoard, "coop/formatters/style.css")

        self.leaderBoardTextGeneral.anchorClicked.connect(self.open_url)
        self.leaderBoardTextOne.anchorClicked.connect(self.open_url)
        self.leaderBoardTextTwo.anchorClicked.connect(self.open_url)
        self.leaderBoardTextThree.anchorClicked.connect(self.open_url)
        self.leaderBoardTextFour.anchorClicked.connect(self.open_url)

        self.replayDownload = QNetworkAccessManager()
        self.replayDownload.finished.connect(self.finish_request)

        self.selectedItem = None

    @QtCore.pyqtSlot(QtCore.QUrl)
    def open_url(self, url):
        self.replayDownload.get(QNetworkRequest(url))

    @staticmethod
    def finish_request(reply):
        faf_replay = QtCore.QFile(os.path.join(util.CACHE_DIR, "temp.fafreplay"))
        faf_replay.open(QtCore.QIODevice.WriteOnly | QtCore.QIODevice.Truncate)                
        faf_replay.write(reply.readAll())
        faf_replay.flush()
        faf_replay.close()  
        replay(os.path.join(util.CACHE_DIR, "temp.fafreplay"))
        
    def process_leaderboard_infos(self, message):
        """ Process leaderboard """

        values = message["leaderboard"]
        table = message["table"]
        if table == 0:
            w = self.leaderBoardTextGeneral
        elif table == 1:
            w = self.leaderBoardTextOne
        elif table == 2:
            w = self.leaderBoardTextTwo
        elif table == 3:
            w = self.leaderBoardTextThree
        elif table == 4:
            w = self.leaderBoardTextFour
        else:
            w = self.leaderBoardTextGeneral

        doc = QtGui.QTextDocument()
        doc.addResource(3, QtCore.QUrl("style.css"), self.leaderBoard.styleSheet())
        html = "<html><head><link rel='stylesheet' type='text/css' href='style.css'></head><body>"
        
        if self.selectedItem:
            html += '<p class="division" align="center">'+self.selectedItem.name+'</p><hr/>'
        html += "<table class='players' cellspacing='0' cellpadding='0' width='630' height='100%'>"

        formatter = self.FORMATTER_LADDER
        formatter_header = self.FORMATTER_LADDER_HEADER
        cursor = w.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        w.setTextCursor(cursor) 
        color = "lime"
        line = formatter_header.format(rank="rank", names="names", time="time", color=color)
        html += line
        rank = 1
        for val in values:
            # val = values[uid]
            players = ", ".join(val["players"]) 
            num_players = str(len(val["players"]))
            timing = val["time"]
            gameuid = str(val["gameuid"])
            if val["secondary"] == 1:
                secondary = "Yes"
            else:
                secondary = "No"
            if rank % 2 == 0:
                line = formatter.format(rank=str(rank), numplayers=num_players, gameuid=gameuid, players=players,
                                        objectives=secondary, timing=timing, type="even")
            else:
                line = formatter.format(rank=str(rank), numplayers=num_players, gameuid=gameuid, players=players,
                                        objectives=secondary, timing=timing, type="")
            
            rank = rank + 1
            
            html += line

        html += "</tbody></table></body></html>"

        doc.setHtml(html)
        w.setDocument(doc)
        
        self.leaderBoard.setVisible(True)
    
    @QtCore.pyqtSlot()
    def link_vanilla(self):
        WizardSC(self).exec_()

    def coop_changed(self):
        if not self.loaded:
            client.instance.lobby_connection.send(dict(command="coop_list"))
            self.loaded = True

    def ask_leaderboard(self):
        """ 
        ask the server for stats
        """
        if self.selectedItem:
            client.instance.statsServer.send(dict(command="coop_stats", mission=self.selectedItem.uid,
                                                  type=self.tabLeaderWidget.currentIndex()))

    def coop_list_clicked(self, item):
        """
        Hosting a coop event
        """
        if not hasattr(item, "mapUrl"):
            if item.isExpanded():
                item.setExpanded(False)
            else:
                item.setExpanded(True)
            return

        if item != self.selectedItem: 
            self.selectedItem = item
            client.instance.statsServer.send(dict(command="coop_stats", mission=item.uid,
                                                  type=self.tabLeaderWidget.currentIndex()))

    def coop_list_doubleclicked(self, item):
        """
        Hosting a coop event
        """
        if not hasattr(item, "mapUrl"):
            return
        
        if not fa.instance.available():
            return
            
        client.instance.games.stop_search_ranked()
        
        # A simple Hosting dialog.
        if fa.check.check("coop"):
            hostgamewidget = HostGameWidget(self, item, is_coop=True)
            hostgamewidget.exec_()

    @QtCore.pyqtSlot(dict)
    def process_coop_info(self, message):
        """
        Slot that interprets and propagates coop_info messages into the coop list 
        """
        uid = message["uid"]

        if uid not in self.coop:
            type_coop = message["type"]
            
            if type_coop not in self.cooptypes:
                root_item = QtGui.QTreeWidgetItem()
                self.coopList.addTopLevelItem(root_item)
                root_item.setText(0, "<font color='white' size=+3>%s</font>" % type_coop)
                self.cooptypes[type_coop] = root_item
                root_item.setExpanded(False)
            else:
                root_item = self.cooptypes[type_coop]

            item_coop = CoopMapItem(uid)
            item_coop.update(message, self.FORMATTER_COOP)

            root_item.addChild(item_coop)

            self.coop[uid] = item_coop

    @QtCore.pyqtSlot(dict)
    def process_game_info(self, message):
        """
        Slot that interprets and propagates game_info messages into GameItems 
        """
        uid = message["uid"]
        if message["featured_mod"] == "coop":
            if 'max_players' in message:
                message["max_players"] = 4

            if uid not in self.games:
                self.games[uid] = GameItem(uid)
                self.gameList.addItem(self.games[uid])
            self.games[uid].update(message)

            if message['state'] == "open":
                # force the display.
                self.games[uid].setHidden(False)    

        # Special case: removal of a game that has ended
        if message['state'] == "closed":
            if uid in self.games:
                self.gameList.takeItem(self.gameList.row(self.games[uid]))
                del self.games[uid]    
            return

    @QtCore.pyqtSlot(QtGui.QListWidgetItem)
    def game_doubleclicked(self, item):
        """
        Slot that attempts to join a game.
        """
        if not fa.instance.available():
            return

        if not fa.check.check(item.mod, item.mapname, None, item.mods):
            return

        if item.password_protected:
            passw, ok = QtGui.QInputDialog.getText(client.instance, "Passworded game", "Enter password :",
                                                   QtGui.QLineEdit.Normal, "")
            if ok:
                client.instance.join_game(uid=item.uid, password=passw)
        else:
            client.instance.join_game(uid=item.uid)
