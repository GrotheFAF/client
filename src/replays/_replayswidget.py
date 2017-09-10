

from PyQt4 import QtCore, QtGui, QtNetwork
from PyQt4.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from fa.replay import replay
from config import Settings
import util
import os
import fa
import time
import client
import json

import logging
logger = logging.getLogger(__name__)

LIVEREPLAY_DELAY = 5  # livereplay delay in minutes
LIVEREPLAY_DELAY_TIME = LIVEREPLAY_DELAY * 60  # livereplay delay for time() (in seconds)

from replays.replayitem import ReplayItem, ReplayItemDelegate

# Replays uses the new Inheritance Based UI creation pattern
# This allows us to do all sorts of awesome stuff by overriding methods etc.

FormClass, BaseClass = util.load_ui_type("replays/replays.ui")


class LiveReplayItem(QtGui.QTreeWidgetItem):
    def __init__(self, time):
        QtGui.QTreeWidgetItem.__init__(self)
        self.launched_at = time

    def __lt__(self, other):
        return self.launched_at < other.launched_at

    def __le__(self, other):
        return self.launched_at <= other.launched_at

    def __gt__(self, other):
        return self.launched_at > other.launched_at

    def __ge__(self, other):
        return self.launched_at >= other.launched_at


class ReplaysWidget(BaseClass, FormClass):
    SOCKET = 11002
    HOST = "lobby.faforever.com"

    FORMATTER_REPLAY = util.readfile("replays/formatters/replay.qthtml")

    # connect to save/restore persistence settings for checkboxes & search parameters
    automatic = Settings.persisted_property("replay/automatic", default_value=False, key_type=bool)
    spoiler_free = Settings.persisted_property("replay/spoilerFree", default_value=True, key_type=bool)
    no_zero_duration = Settings.persisted_property("replay/noZeroDuration", default_value=False, key_type=bool)

    def __init__(self, dispatcher):
        super(BaseClass, self).__init__()

        self.setupUi(self)

        # self.replayVault.setVisible(False)
        self._dispatcher = dispatcher
        client.instance.replaysTab.layout().addWidget(self)

        client.instance.lobby_info.gameInfo.connect(self.process_game_info)
        client.instance.lobby_info.replayVault.connect(self.replay_vault)
        
        self.online_replays = {}
        self.onlineTree.setItemDelegate(ReplayItemDelegate(self))
        self.replayDownload = QNetworkAccessManager()
        self.replayDownload.finished.connect(self.finish_request)

        # sending request to replay vault
        self.searchButton.pressed.connect(self.search_vault)
        self.playerName.returnPressed.connect(self.search_vault)
        self.mapName.returnPressed.connect(self.search_vault)

        self.automaticCheckbox.stateChanged.connect(self.automatic_checkbox_change)
        self.spoilerCheckbox.stateChanged.connect(self.spoiler_checkbox_change)
        self.zeroCheckbox.stateChanged.connect(self.zero_checkbox_change)
        self.RefreshResetButton.pressed.connect(self.reset_refresh_pressed)

        self.myTree.itemDoubleClicked.connect(self.mytree_doubleclicked)
        self.myTree.itemPressed.connect(self.mytree_pressed)
        self.myTree.header().setResizeMode(0, QtGui.QHeaderView.ResizeToContents)
        self.myTree.header().setResizeMode(1, QtGui.QHeaderView.ResizeToContents)
        self.myTree.header().setResizeMode(2, QtGui.QHeaderView.Stretch)
        self.myTree.header().setResizeMode(3, QtGui.QHeaderView.ResizeToContents)
        self.mytree_modification_time = 0
        self.mytree_current_path = util.REPLAY_DIR

        self.liveTree.itemDoubleClicked.connect(self.livetree_doubleclicked)
        self.liveTree.itemPressed.connect(self.livetree_pressed)
        self.liveTree.header().setResizeMode(0, QtGui.QHeaderView.ResizeToContents)
        self.liveTree.header().setResizeMode(1, QtGui.QHeaderView.Stretch)
        self.liveTree.header().setResizeMode(2, QtGui.QHeaderView.ResizeToContents)

        self.games = {}

        self.onlineTree.itemDoubleClicked.connect(self.onlinetree_doubleclicked)
        self.onlineTree.itemPressed.connect(self.onlinetree_clicked)
        self.selected_replay = None

        # replay vault connection to server
        self.searching = False
        self.blockSize = 0
        self.replayVaultSocket = QtNetwork.QTcpSocket()
        self.replayVaultSocket.error.connect(self.handle_server_error)
        self.replayVaultSocket.readyRead.connect(self.read_data_from_server)
        self.replayVaultSocket.disconnected.connect(self.disconnected)
        self.replayVaultSocket.error.connect(self.errored)

        # restore persistent checkbox settings
        self.automaticCheckbox.setChecked(self.automatic)
        self.spoilerCheckbox.setChecked(self.spoiler_free)
        self.zeroCheckbox.setChecked(self.no_zero_duration)

        logger.info("Replays Widget instantiated.")

    def search_vault(self):
        """ search for some replays """
        self.searching = True
        self.connect_to_replayvault()
        self.send(dict(command="search", rating=self.minRating.value(), map=self.mapName.text(),
                       player=self.playerName.text(), mod=self.modList.currentText()))
        self.onlineTree.clear()

    def reload_view(self):
        if not self.searching:  # something else is already in the pipe from search_vault
            if self.automatic or self.online_replays == {}:  # refresh on Tap change or only the first time
                self.connect_to_replayvault()
                self.send(dict(command="list"))

    @staticmethod
    def finish_request(reply):
        if reply.error() != QNetworkReply.NoError:
            QtGui.QMessageBox.warning(client.instance, "Network Error", reply.errorString(), QtGui.QMessageBox.Ok)
        else:
            faf_replay = QtCore.QFile(os.path.join(util.CACHE_DIR, "temp.fafreplay"))
            faf_replay.open(QtCore.QIODevice.WriteOnly | QtCore.QIODevice.Truncate)
            faf_replay.write(reply.readAll())
            faf_replay.flush()
            faf_replay.close()
            replay(os.path.join(util.CACHE_DIR, "temp.fafreplay"))

    def onlinetree_clicked(self, item):
        if QtGui.QApplication.mouseButtons() == QtCore.Qt.RightButton:
            if type(item.parent) == ReplaysWidget:
                item.pressed()
        else:
            self.selected_replay = item
            if hasattr(item, "detail_info"):  # check we are not clicking on a date-item
                if not item.detail_info:
                    self.connect_to_replayvault()
                    self.send(dict(command="info_replay", uid=item.uid))
                else:
                    item.generate_info_players_html()
            else:  # we clear it
                self.replayInfos.clear()

    def onlinetree_doubleclicked(self, item):
        if hasattr(item, "duration") and hasattr(item, "url"):
            if "playing" in item.duration and "?playing?" not in item.duration:  # live game will not be in vault
                if item.uid in client.instance.games.games:  # still running
                    game = client.instance.games.games[item.uid]
                    for player in game.players:  # find a player ...
                        if player.login in client.instance.urls:  # ... still online/in game
                            if time.time() - game.launched_at > LIVEREPLAY_DELAY_TIME:  # live game over 5min
                                replay(client.instance.urls[player.login])  # join live game
                            return
                else:  # game ended - so start replay
                    if QtGui.QMessageBox.question(client.instance, "Live Game ended", "Want to try the Replay?",
                                                  QtGui.QMessageBox.Yes,
                                                  QtGui.QMessageBox.No) == QtGui.QMessageBox.Yes:
                        self.replayDownload.get(QNetworkRequest(QtCore.QUrl(item.url)))
            else:  # start replay
                self.replayDownload.get(QNetworkRequest(QtCore.QUrl(item.url)))

    def automatic_checkbox_change(self, state):
        self.automatic = state  # save state .. no magic

    def spoiler_checkbox_change(self, state):
        self.spoiler_free = state  # save state .. no magic
        if self.selected_replay:  # if something is selected in the tree to the left
            if type(self.selected_replay) == ReplayItem:  # and if it is a game
                self.selected_replay.generate_info_players_html()  # then we redo it
            else:  # we clear it
                self.replayInfos.clear()

    def zero_checkbox_change(self, state):
        self.no_zero_duration = state  # save state .. no magic

    def reset_refresh_pressed(self):  # reset search parameter and reload recent Replays List
        self.connect_to_replayvault()
        self.send(dict(command="list"))
        self.playerName.setText("")
        self.mapName.setText("")
        self.modList.setCurrentIndex(0)  # "All"
        self.minRating.setValue(0)

    def replay_vault(self, message):
        action = message["action"]
        self.searchInfoLabel.clear()
        if action == "info_replay":
            uid = message["uid"]
            if uid in self.online_replays:
                self.online_replays[uid].info_players(message["players"])
        elif action in ("list_recents", "search_result"):
            self.online_replays = {}
            replays_msg = message["replays"]
            for replay_msg in replays_msg:
                uid = replay_msg["id"]
                if uid not in self.online_replays:
                    self.online_replays[uid] = ReplayItem(uid, self)
                self.online_replays[uid].update(replay_msg, self.FORMATTER_REPLAY)

            self.update_onlinetree()
            self.replayInfos.clear()
            if action == "list_recents":
                self.RefreshResetButton.setText("Refresh Recent List")
            elif action == "search_result":
                self.searching = False
                self.RefreshResetButton.setText("Reset Search to Recent")

    def showEvent(self, event):  # QtGui.QShowEvent
        self.update_mytree(self.mytree_current_path)
        self.reload_view()
        return BaseClass.showEvent(self, event)

    def update_onlinetree(self):
        self.selected_replay = None  # clear because won't be part of the new tree
        self.replayInfos.clear()
        self.onlineTree.clear()
        buckets = {}
        for uid in self.online_replays:
            # on zeroCheckBox do not add corrupted/early desync or other zero time replays
            if not (self.no_zero_duration and self.online_replays[uid].duration == "00:00:00"):
                bucket = buckets.setdefault(self.online_replays[uid].startDate, [])
                bucket.append(self.online_replays[uid])

        for bucket_key in list(buckets.keys()):
            item = QtGui.QTreeWidgetItem()
            self.onlineTree.addTopLevelItem(item)

            item.setIcon(0, util.icon("replays/bucket.png"))
            item.setText(0, "<font color='white'>" + bucket_key + "</font>")
            item.setText(1, "<font color='white'>" + str(len(buckets[bucket_key])) + " replays</font>")

            for online_replay in buckets[bucket_key]:
                item.addChild(online_replay)
                online_replay.setFirstColumnSpanned(True)
                online_replay.setIcon(0, online_replay.icon)

            item.setExpanded(True)

    @staticmethod
    def load_local_cache():
        cache_fname = os.path.join(util.CACHE_DIR, "local_replays_metadata")
        cache = {}
        if os.path.exists(cache_fname):
            with open(cache_fname, "rt") as fh:
                for line in fh:
                    filename, metadata = line.split(':', 1)
                    cache[filename] = metadata
        return cache

    @staticmethod
    def save_local_cache(cache_hit, cache_add):
        with open(os.path.join(util.CACHE_DIR, "local_replays_metadata"), "wt") as fh:
            for filename, metadata in cache_hit.items():
                fh.write(filename + ":" + metadata)
            for filename, metadata in cache_add.items():
                fh.write(filename + ":" + metadata)

    def update_mytree(self, replay_dir):

        if self.mytree_current_path == replay_dir:  # same folder again
            modification_time = os.path.getmtime(replay_dir)
            if self.mytree_modification_time < modification_time:  # anything changed?
                self.mytree_modification_time = modification_time
            else:  # nothing changed -> don't redo
                return
        else:  # changed folder - so make it new
            self.mytree_current_path = replay_dir

        self.setCursor(QtCore.Qt.WaitCursor)  # this might take longer ...
        self.myTree.clear()

        if replay_dir != util.REPLAY_DIR:  # option to go up again
            item = QtGui.QTreeWidgetItem()
            item.setIcon(0, util.icon("replays/open_folder.png"))
            item.setText(0, "folder up")  # sorting trick
            item.setForeground(0, QtGui.QColor(client.instance.get_color("default")))
            item.setText(1, "..")
            item.filename = os.path.split(replay_dir)[0]  # save path with item
            item.setText(2, str(item.filename))
            item.setForeground(2, QtGui.QColor(client.instance.get_color("default")))
            self.myTree.addTopLevelItem(item)

        # We put the replays into buckets by day first, then we add them to the treewidget.
        buckets = {}

        cache = self.load_local_cache()
        cache_add = {}
        cache_hit = {}
        # Iterate
        for infile in os.listdir(replay_dir):
            if infile.endswith(".scfareplay"):
                bucket = buckets.setdefault("legacy", [])

                item = QtGui.QTreeWidgetItem()
                item.setText(1, infile)
                item.filename = os.path.join(replay_dir, infile)
                item.setIcon(0, util.icon("replays/replay.png"))
                item.setForeground(0, QtGui.QColor(client.instance.get_color("default")))

                bucket.append(item)

            elif infile.endswith(".fafreplay"):
                item = QtGui.QTreeWidgetItem()
                try:
                    item.filename = os.path.join(replay_dir, infile)
                    basename = os.path.basename(item.filename)
                    if basename in cache:
                        oneline = cache[basename]
                        cache_hit[basename] = oneline
                    else:
                        with open(item.filename, "rt") as fh:
                            oneline = fh.readline()
                            cache_add[basename] = oneline

                    item.info = json.loads(oneline)

                    # Parse replayinfo into data
                    if item.info.get('complete', False):
                        # 'game_time' is 'launched_at' for older replays (if that fails maybe 'game_end' is there)
                        t = item.info.get('launched_at', item.info.get('game_time', item.info.get('game_end')))
                        if t is None:
                            game_date = 'date missing'
                            game_hour = '--:--'
                        else:
                            game_date = time.strftime("%Y-%m-%d", time.localtime(t))
                            game_hour = time.strftime("%H:%M", time.localtime(t))

                        bucket = buckets.setdefault(game_date, [])

                        icon = fa.maps.preview(item.info['mapname'])
                        if icon:
                            item.setIcon(0, icon)
                        else:
                            client.instance.downloader.download_map(item.info['mapname'], item, True)
                            item.setIcon(0, util.icon("games/unknown_map.png"))
                        item.setToolTip(0, fa.maps.get_display_name(item.info['mapname']))
                        item.setText(0, game_hour)
                        item.setForeground(0, QtGui.QColor(client.instance.get_color("default")))

                        item.setText(1, item.info['title'])
                        item.setToolTip(1, infile)

                        # Hacky way to quickly assemble a list of all the players, but including the observers
                        playerlist = []
                        for _, players in list(item.info['teams'].items()):
                            playerlist.extend(players)
                        item.setText(2, ", ".join(playerlist))
                        item.setToolTip(2, ", ".join(playerlist))

                        # Add additional info
                        item.setText(3, item.info['featured_mod'])
                        item.setTextAlignment(3, QtCore.Qt.AlignCenter)
                        recorder_color = client.instance.players.get_user_color(item.info.get('recorder', ""))
                        item.setForeground(1, QtGui.QColor(recorder_color))
                    else:
                        bucket = buckets.setdefault("incomplete", [])
                        item.setIcon(0, util.icon("replays/replay.png"))
                        item.setText(1, infile)
                        item.setText(2, "(replay doesn't have complete metadata)")
                        item.setForeground(1, QtGui.QColor("yellow"))

                except Exception as ex:
                    bucket = buckets.setdefault("broken", [])
                    item.setIcon(0, util.icon("replays/broken.png"))
                    item.setText(1, infile)
                    item.setForeground(1, QtGui.QColor("red"))
                    item.setText(2, "(replay parse error)")
                    item.setForeground(2, QtGui.QColor("gray"))
                    logger.exception("Exception parsing replay {}: {}".format(infile, ex))

                bucket.append(item)

            elif os.path.isdir(os.path.join(replay_dir, infile)):  # we found a directory ...

                item = QtGui.QTreeWidgetItem()
                item.setIcon(0, util.icon("replays/closed_folder.png"))
                item.setText(0, "folder :")  # sorting trick
                item.setForeground(0, QtGui.QColor(client.instance.get_color("default")))
                item.setText(1, infile)
                item.filename = os.path.join(replay_dir, infile)  # save path with item
                i = len(os.listdir(item.filename))  # get number of files
                if i == 1:
                    item.setText(3, "(1 file)")
                else:
                    item.setText(3, "(" + str(i) + " files)")
                self.myTree.addTopLevelItem(item)

        if len(cache_add) > 10 or len(cache) - len(cache_hit) > 10:
            self.save_local_cache(cache_hit, cache_add)
        # Now, create a top level TreeWidgetItem for every bucket, and put the bucket's contents into them
        for bucket_key in list(buckets.keys()):
            item = QtGui.QTreeWidgetItem()

            if bucket_key == "broken":
                item.setForeground(0, QtGui.QColor("red"))
                item.setText(1, "(not watchable)")
                item.setForeground(1, QtGui.QColor(client.instance.get_color("default")))
            elif bucket_key == "incomplete":
                item.setForeground(0, QtGui.QColor("yellow"))
                item.setText(1, "(watchable)")
                item.setForeground(1, QtGui.QColor(client.instance.get_color("default")))
            elif bucket_key == "legacy":
                item.setForeground(0, QtGui.QColor(client.instance.get_color("default")))
                item.setForeground(1, QtGui.QColor(client.instance.get_color("default")))
                item.setText(1, "(old replay system)")
            else:
                item.setForeground(0, QtGui.QColor(client.instance.get_color("player")))

            item.setIcon(0, util.icon("replays/bucket.png"))
            if len(buckets[bucket_key]) == 1:
                item.setText(3, "1 replay")
            else:
                item.setText(3, str(len(buckets[bucket_key])) + " replays")
            item.setText(0, bucket_key)
            item.setForeground(3, QtGui.QColor(client.instance.get_color("default")))

            self.myTree.addTopLevelItem(item)  # add replay bucket

            for my_replay in buckets[bucket_key]:  # add replays into bucket
                item.addChild(my_replay)

        self.unsetCursor()  # undo the WaitCursor

    def display_replay(self):
        for uid in self.games:
            item = self.games[uid]
            if item.isHidden():
                if time.time() - item.launched_at > LIVEREPLAY_DELAY_TIME:
                    item.setHidden(False)

    @QtCore.pyqtSlot(dict)
    def process_game_info(self, info):
        if info['state'] == "playing":
            if info['uid'] in self.games:
                # Updating an existing item
                item = self.games[info['uid']]

                item.takeChildren()  # Clear the children of this item before we're updating it
            else:
                # Creating a fresh item
                item = LiveReplayItem(info.get('launched_at', time.time()))
                self.games[info['uid']] = item

                self.liveTree.insertTopLevelItem(0, item)

                if LIVEREPLAY_DELAY_TIME > time.time() - item.launched_at:
                    item.setHidden(True)
                    # to get the delay right on client start, subtract the already passed game time
                    delay_time = LIVEREPLAY_DELAY_TIME - (time.time() - item.launched_at)
                    QtCore.QTimer().singleShot(delay_time*1000, self.display_replay)
                    # The delay is there because we have a delay in the livereplay server

            # For debugging purposes, format our tooltip for the top level items
            # so it contains a human-readable representation of the info dictionary
            tip = ""
            for key in list(info.keys()):
                try:
                    tip += "'" + str(key) + "' : '" + str(info[key]) + "'<br/>"
                except:
                    tip += "'" + key + "' : '" + info[key] + "'<br/>"

            if item.toolTip(1) != tip:
                item.setToolTip(1, tip)

            icon = fa.maps.preview(info['mapname'])
            item.setToolTip(0, fa.maps.get_display_name(info['mapname']))
            if not icon:
                client.instance.downloader.download_map(info['mapname'], item, True)
                icon = util.icon("games/unknown_map.png")

            item.setText(0, str(info['uid']) + time.strftime("  -  %Y-%m-%d - %H:%M", time.localtime(item.launched_at)))
            item.setForeground(0, QtGui.QColor(client.instance.get_color("default")))

            if info['featured_mod'] == "coop":  # no map icons for coop
                item.setIcon(0, util.icon("games/unknown_map.png"))
            else:
                item.setIcon(0, icon)
            if info['featured_mod'] == "ladder1v1":
                item.setText(1, info['title'])
            else:
                item.setText(1, info['title'] + "    -    [host: " + info['host'] + "]")
            item.setForeground(1, QtGui.QColor(client.instance.get_color("player")))

            item.setText(2, info['featured_mod'])
            item.setTextAlignment(2, QtCore.Qt.AlignCenter)

            if not info['teams']:
                item.setDisabled(True)

            # This game is the game the player is currently in
            mygame = False

            # Create player entries for all the live players in a match
            for team in info['teams']:
                if team == "-1":  # skip observers, they don't seem to stream livereplays
                    continue

                for name in info['teams'][team]:
                    playeritem = QtGui.QTreeWidgetItem()
                    playeritem.setText(0, name)

                    playerid = client.instance.players.get_id(name)

                    url = QtCore.QUrl()
                    url.setScheme("faflive")
                    url.setHost("lobby.faforever.com")
                    url.setPath(str(info["uid"]) + "/" + name + ".SCFAreplay")
                    url.addQueryItem("map", info["mapname"])
                    url.addQueryItem("mod", info["featured_mod"])

                    playeritem.url = url
                    if client.instance.login == name:
                        mygame = True
                        item.setForeground(1, QtGui.QColor(client.instance.get_color("self")))
                        playeritem.setForeground(0, QtGui.QColor(client.instance.get_color("self")))
                        playeritem.setToolTip(0, url.toString())
                        playeritem.setIcon(0, util.icon("replays/replay.png"))
                    elif client.instance.players.is_friend(playerid):
                        if not mygame:
                            item.setForeground(1, QtGui.QColor(client.instance.get_color("friend")))
                        playeritem.setForeground(0, QtGui.QColor(client.instance.get_color("friend")))
                        playeritem.setToolTip(0, url.toString())
                        playeritem.setIcon(0, util.icon("replays/replay.png"))
                    elif client.instance.players.is_player(playerid):
                        playeritem.setForeground(0, QtGui.QColor(client.instance.get_color("player")))
                        playeritem.setToolTip(0, url.toString())
                        playeritem.setIcon(0, util.icon("replays/replay.png"))
                    else:
                        playeritem.setForeground(0, QtGui.QColor(client.instance.get_color("default")))
                        playeritem.setDisabled(True)

                    item.addChild(playeritem)
        elif info['state'] == "closed":
            if info['uid'] in self.games:
                self.liveTree.takeTopLevelItem(self.liveTree.indexOfTopLevelItem(self.games[info['uid']]))

    @QtCore.pyqtSlot(QtGui.QTreeWidgetItem)
    def livetree_pressed(self, item):
        if QtGui.QApplication.mouseButtons() != QtCore.Qt.RightButton:
            return

        if self.liveTree.indexOfTopLevelItem(item) != -1:
            item.setExpanded(True)
            return

        menu = QtGui.QMenu(self.liveTree)

        # Actions for Games and Replays
        action_replay = QtGui.QAction("Replay in FA", menu)
        action_link = QtGui.QAction("Copy Link", menu)

        # Adding to menu
        menu.addAction(action_replay)
        menu.addAction(action_link)

        # Triggers
        action_replay.triggered.connect(lambda: self.livetree_doubleclicked(item, 0))
        action_link.triggered.connect(lambda: QtGui.QApplication.clipboard().setText(item.toolTip(0)))

        # Adding to menu
        menu.addAction(action_replay)
        menu.addAction(action_link)

        # Finally: Show the popup
        menu.popup(QtGui.QCursor.pos())

    @QtCore.pyqtSlot(QtGui.QListWidgetItem)
    def mytree_pressed(self, item):
        if QtGui.QApplication.mouseButtons() != QtCore.Qt.RightButton:
            return

        if item.isDisabled():
            return

        if self.myTree.indexOfTopLevelItem(item) != -1:
            return

        menu = QtGui.QMenu(self.myTree)

        # Actions for Games and Replays
        action_replay = QtGui.QAction("Replay", menu)
        action_explorer = QtGui.QAction("Show in Explorer", menu)

        # Adding to menu
        menu.addAction(action_replay)
        menu.addAction(action_explorer)

        # Triggers
        action_replay.triggered.connect(lambda: self.mytree_doubleclicked(item, 0))
        action_explorer.triggered.connect(lambda: util.show_file_in_file_browser(item.filename))

        # Adding to menu
        menu.addAction(action_replay)
        menu.addAction(action_explorer)

        # Finally: Show the popup
        menu.popup(QtGui.QCursor.pos())

    @QtCore.pyqtSlot(QtGui.QTreeWidgetItem, int)
    def mytree_doubleclicked(self, item):
        if item.isDisabled():
            return

        if self.myTree.indexOfTopLevelItem(item) != -1:  # [TopLevel]Bucket
            if hasattr(item, "filename"):  # is directory
                if os.path.isdir(item.filename):
                    self.update_mytree(item.filename)  # show content of that directory
        else:  # inside a [TopLevel]Bucket
            replay(item.filename)

    @QtCore.pyqtSlot(QtGui.QTreeWidgetItem, int)
    def livetree_doubleclicked(self, item):
        """ This slot launches a live replay from eligible items in liveTree """

        if item.isDisabled():
            return

        if self.liveTree.indexOfTopLevelItem(item) == -1:
            # Notify other modules that we're watching a replay
            client.instance.viewingReplay.emit(item.url)
            replay(item.url)

    def connect_to_replayvault(self):
        """ connect to the replay vault server """
        self.searchInfoLabel.setText("Searching...")

        if self.replayVaultSocket.state() != QtNetwork.QAbstractSocket.ConnectedState and \
           self.replayVaultSocket.state() != QtNetwork.QAbstractSocket.ConnectingState:
            self.replayVaultSocket.connectToHost(self.HOST, self.SOCKET)

    def send(self, message):
        client.instance.RserverS.setText("S")  # TESTING-IO Grothe
        data = json.dumps(message)
        logger.debug("Outgoing JSON Message: " + data)
        self.write_to_server(data)
        client.instance.RserverS.setText("s")  # TESTING-IO Grothe

    @QtCore.pyqtSlot()
    def read_data_from_server(self):
        client.instance.RserverS.setText("-")  # TESTING-IO Grothe
        client.instance.RserverR.setText("R")  # TESTING-IO Grothe
        ins = QtCore.QDataStream(self.replayVaultSocket)
        ins.setVersion(QtCore.QDataStream.Qt_4_2)

        while not ins.atEnd():
            if self.blockSize == 0:
                if self.replayVaultSocket.bytesAvailable() < 4:
                    return
                self.blockSize = ins.readUInt32()
            if self.replayVaultSocket.bytesAvailable() < self.blockSize:
                return

            action = ins.readQString()
            self.process(action)
            self.blockSize = 0
        client.instance.RserverR.setText("-")  # TESTING-IO Grothe

    def process(self, action):
        logger.debug("Replay Vault Server: " + action)
        self.receive_json(action)

    def receive_json(self, data_string):
        """ A fairly pythonic way to process received strings as JSON messages. """

        try:
            message = json.loads(data_string)
            self._dispatcher.dispatch(message)
        except ValueError as e:
            logger.error("Error decoding json ")
            logger.error(e)

        self.replayVaultSocket.disconnectFromHost()

    def write_to_server(self, action, *args):
        logger.debug(("write_to_server(" + action + ", [" + ', '.join(args) + "])"))

        block = QtCore.QByteArray()
        out = QtCore.QDataStream(block, QtCore.QIODevice.ReadWrite)
        out.setVersion(QtCore.QDataStream.Qt_4_2)
        out.writeUInt32(0)
        out.writeQString(action)

        for arg in args:
            if type(arg) is int:
                out.writeInt(arg)
            elif isinstance(arg, str):
                out.writeQString(arg)
            elif type(arg) is float:
                out.writeFloat(arg)
            elif type(arg) is list:
                out.writeQVariantList(arg)
            else:
                logger.warn("Uninterpreted Data Type: " + str(type(arg)) + " of value: " + str(arg))
                out.writeQString(str(arg))

        out.device().seek(0)
        out.writeUInt32(block.size() - 4)

        self.bytesToSend = block.size() - 4
        self.replayVaultSocket.write(block)

    def handle_server_error(self, socket_error):
        self.searchInfoLabel.setText("Server Error")
        if socket_error == QtNetwork.QAbstractSocket.RemoteHostClosedError:
            logger.info("Replay Server down: The server is down for maintenance, please try later.")

        elif socket_error == QtNetwork.QAbstractSocket.HostNotFoundError:
            logger.info("Connection to Host lost. Please check the host name and port settings.")

        elif socket_error == QtNetwork.QAbstractSocket.ConnectionRefusedError:
            logger.info("The connection was refused by the peer.")
        else:
            logger.info("The following error occurred: %s." % self.replayVaultSocket.errorString())

    @QtCore.pyqtSlot()
    def disconnected(self):
        logger.debug("Disconnected from server")

    @QtCore.pyqtSlot(QtNetwork.QAbstractSocket.SocketError)
    def errored(self):
        logger.error("TCP Error " + self.replayVaultSocket.errorString())
