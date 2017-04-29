from functools import partial
import random

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
import time
import util
from games.gameitem import GameItem, GameItemDelegate
from games.moditem import ModItem, mod_invisible
from games.hostgamewidget import HostGameWidget
from fa.factions import Factions
import fa
import client
import notifications as ns
from config import Settings

import logging

logger = logging.getLogger(__name__)

FormClass, BaseClass = util.load_ui_type("games/games.ui")


class GamesWidget(FormClass, BaseClass):

    hide_private_games = Settings.persisted_property("play/hidePrivateGames", default_value=False, key_type=bool)
    sort_games_index = Settings.persisted_property("play/sortGames", default_value=0, key_type=int)  # by player count
    sub_factions = Settings.persisted_property("play/subFactions", default_value=[False, False, False, False])

    def __init__(self, *args, **kwargs):
        BaseClass.__init__(self, *args, **kwargs)

        self.setupUi(self)

        client.instance.gamesTab.layout().addWidget(self)

        self.mods = {}

        # Dictionary containing our actual games.
        self.games = {}

        # Ranked search UI
        self._ranked_icons = {
            Factions.UEF: self.rankedUEF,
            Factions.CYBRAN: self.rankedCybran,
            Factions.AEON: self.rankedAeon,
            Factions.SERAPHIM: self.rankedSeraphim
        }
        self.rankedUEF.setIcon(util.icon("games/automatch/uef.png"))
        self.rankedCybran.setIcon(util.icon("games/automatch/cybran.png"))
        self.rankedAeon.setIcon(util.icon("games/automatch/aeon.png"))
        self.rankedSeraphim.setIcon(util.icon("games/automatch/seraphim.png"))

        Settings.set("play/subFactions", self.sub_factions)  # needs one write before self.sub_factions... work

        # Fixup ini file type loss
        self.sub_factions = [True if x == 'true' else False for x in self.sub_factions]

        self.searchProgress.hide()

        # Ranked search state variables
        self.searching = False
        self.race = None
        self.ispassworded = False

        self.gameitem_counter = 0  # test
        self.games_ignored_counter = 0  # test

        self.generate_select_subset()

        client.instance.lobby_info.modInfo.connect(self.process_modinfo)
        client.instance.lobby_info.gameInfo.connect(self.process_gameinfo)
        client.instance.lobby_connection.disconnected.connect(self.clear_games)

        client.instance.gameEnter.connect(self.stop_search_ranked)
        client.instance.viewingReplay.connect(self.stop_search_ranked)

        self.gameList.setItemDelegate(GameItemDelegate(self))
        self.gameList.itemDoubleClicked.connect(self.game_doubleclicked)
        self.gameList.itemSelectionChanged.connect(self.game_selection_changed)
        self.selected_game = None
        self.gameList.sortBy = self.sort_games_index  # Default Sorting is By Players count

        self.sortGamesComboBox.addItems(['By Players', 'By avg. Player Rating', 'By Map', 'By Host', 'By Age'])
        self.sortGamesComboBox.currentIndexChanged.connect(self.sortgamescombo_changed)
        self.sortGamesComboBox.setCurrentIndex(self.sort_games_index)

        self.hideGamesWithPw.stateChanged.connect(self.toggle_private_games)
        self.hideGamesWithPw.setChecked(self.hide_private_games)

        self.modList.itemDoubleClicked.connect(self.hostgame_clicked)

        self.update_playbutton()

    @QtCore.pyqtSlot(dict)
    def process_modinfo(self, message):
        """
        Slot that interprets and propagates mod_info messages into the mod list
        """
        mod = message['name']
        old_mod = self.mods.get(mod, None)
        self.mods[mod] = ModItem(message)

        if old_mod:
            if mod in mod_invisible:
                del mod_invisible[mod]
            for i in range(0, self.modList.count()):
                if self.modList.item(i) == old_mod:
                    self.modList.takeItem(i)
                    continue

        if message["publish"]:
            self.modList.addItem(self.mods[mod])
        else:
            mod_invisible[mod] = self.mods[mod]

        client.instance.replays.modList.addItem(message["name"])

    @QtCore.pyqtSlot(int)
    def toggle_private_games(self, state):
        self.hide_private_games = state

        for game in [self.games[game] for game in self.games
                     if self.games[game].state == 'open' and self.games[game].password_protected]:
            game.setHidden(state == Qt.Checked)

    def select_faction(self, enabled, faction=0):
        if len(self.sub_factions) < faction:
            return

        logger.debug('select_faction: selected was {}'.format(self.sub_factions))
        self.sub_factions[faction-1] = enabled

        Settings.set("play/subFactions", self.sub_factions)

        if self.searching:
            self.stop_search_ranked()

        self.update_playbutton()

    def start_subrandom_ranked_search(self):
        """
        This is a wrapper around startRankedSearch where a faction will be chosen based on the selected checkboxes
        """
        if self.searching:
            self.stop_search_ranked()
        else:
            faction_subset = []

            if self.rankedUEF.isChecked():
                faction_subset.append("uef")
            if self.rankedCybran.isChecked():
                faction_subset.append("cybran")
            if self.rankedAeon.isChecked():
                faction_subset.append("aeon")
            if self.rankedSeraphim.isChecked():
                faction_subset.append("seraphim")

            l = len(faction_subset)
            if l in [0, 4]:
                self.start_search_ranked(Factions.RANDOM)
            else:
                # chooses a random factionstring from faction_subset and converts it to a Faction
                self.start_search_ranked(Factions.from_name(faction_subset[random.randint(0, l - 1)]))

    def generate_select_subset(self):
        if self.searching:  # you cannot search for a match while changing/creating the UI
            self.stop_search_ranked()

        self.rankedPlay.clicked.connect(self.start_subrandom_ranked_search)
        self.rankedPlay.show()
        self.labelRankedHint.show()
        self.labelGameInfo.hide()
        for faction, icon in self._ranked_icons.items():
            try:
                icon.clicked.disconnect()
            except TypeError:
                pass

            icon.setChecked(self.sub_factions[faction.value-1])
            icon.clicked.connect(partial(self.select_faction, factionID=faction.value))

    @QtCore.pyqtSlot()
    def clear_games(self):
        self.games = {}
        self.gameList.clear()

    @QtCore.pyqtSlot(dict)
    def process_gameinfo(self, message):
        """
        Slot that interprets and propagates game_info messages into GameItems
        """
        uid = message["uid"]

        if uid not in self.games:
            if message['state'] == 'playing':  # game already started before client start
                if time.time() - message['launched_at'] > 12*3600:  # ignore stale games (>12 hours)
                    self.games_ignored_counter += 1  # test
                    return

            self.games[uid] = GameItem(uid)
            self.gameList.addItem(self.games[uid])
            self.gameitem_counter += 1  # test
            self.games[uid].update(message)

            if message['state'] == 'open' and not message['password_protected']:
                client.instance.notificationSystem.on_event(ns.Notifications.NEW_GAME, message)
        else:
            # if there is a game selected and the message-game was the selected
            if self.selected_game and self.selected_game.uid == uid:
                if self.games[uid].state == "open" and message['state'] != "open":  # game started or host closed
                    self.selected_game = None  # clear selected
                    self.labelGameInfo.hide()  # hide GameInfo

            self.games[uid].update(message)

            # if there is a game selected and the message-game was the selected
            if self.selected_game and self.selected_game.uid == uid:
                self.game_selection_changed()  # update GameInfo of selected game

        # Hide private games
        if self.hideGamesWithPw.isChecked() and message['state'] == 'open' and message['password_protected']:
            self.games[uid].setHidden(True)

        # Special case: removal of a game that has ended
        if message['state'] == "closed":
            if uid in self.games:
                self.gameList.takeItem(self.gameList.row(self.games[uid]))
                del self.games[uid]
                self.gameitem_counter -= 1  # test
            else:  # an ignored game get closed after >12 hours?
                self.games_ignored_counter -= 1  # test

    def update_playbutton(self):
        if self.searching:
            s = "Stop search"
        else:
            c = self.sub_factions.count(True)
            if c in [0, 4]:  # all or none selected
                s = "Play as random!"
            else:
                s = "Play!"

        self.rankedPlay.setText(s)

    def start_search_ranked(self, race):
        if race == Factions.RANDOM:
            race = Factions.get_random_faction()

        if fa.instance.running():
            QtGui.QMessageBox.information(client.instance, "ForgedAllianceForever.exe", "FA is already running.",
                                          QtGui.QMessageBox.Ok)
            self.stop_search_ranked()
            return

        if not fa.check.check("ladder1v1"):
            self.stop_search_ranked()
            logger.error("Can't play ranked without successfully updating Forged Alliance.")
            return

        if self.searching:
            logger.info("Switching Ranked Search to Race " + str(race))
            self.race = race
            client.instance.lobby_connection.send(dict(command="game_matchmaking", mod="ladder1v1", state="settings",
                                                       faction=self.race.value))
        else:
            # Experimental UPnP Mapper - mappings are removed on app exit
            if client.instance.useUPnP:
                client.instance.lobby_connection.set_upnp(self.client.gamePort)

            logger.info("Starting Ranked Search as " + str(race) + ", port: " + str(client.instance.gamePort))
            self.searching = True
            self.race = race
            self.searchProgress.setVisible(True)
            self.labelAutomatch.setText("Searching...")
            self.update_playbutton()
            client.instance.search_ranked(faction=self.race.value)

    @QtCore.pyqtSlot()
    def stop_search_ranked(self):
        if self.searching:
            logger.debug("Stopping Ranked Search")
            client.instance.lobby_connection.send(dict(command="game_matchmaking", mod="ladder1v1", state="stop"))
            self.searching = False
            client.instance.game_session.stop_listen()

        self.update_playbutton()
        self.searchProgress.setVisible(False)
        self.labelAutomatch.setText("1 vs 1 Automatch")

    @QtCore.pyqtSlot(QtGui.QListWidgetItem)
    def game_doubleclicked(self, item):
        """
        Slot that attempts to join a game.
        """
        if not fa.instance.available():
            return

        self.stop_search_ranked()  # Actually a workaround

        if not fa.check.game(client.instance):
            return

        if fa.check.check(item.mod, mapname=item.mapname, version=None, sim_mods=item.mods):
            if item.password_protected:
                passw, ok = QtGui.QInputDialog.getText(
                    client.instance, "Passworded game", "Enter password :", QtGui.QLineEdit.Normal, "")
                if ok:
                    client.instance.join_game(uid=item.uid, password=passw)
            else:
                client.instance.join_game(uid=item.uid)

    @QtCore.pyqtSlot(QtGui.QListWidget)
    def game_selection_changed(self):
        if self.gameList.selectedItems():
            for game_item in self.gameList.selectedItems():
                self.selected_game = game_item
            info_str = self.selected_game.toolTip()  # yeah I know, dirty dirty dirty
            self.labelGameInfo.setText(info_str.replace("width='135'", "width='94'").replace('acing="5"', 'acing="0"').
                                       replace("size='+5'", "size='+2'"))
            self.labelGameInfo.show()
        else:  # we get here on client shutdown
            self.selected_game = None
            self.labelGameInfo.hide()

    @QtCore.pyqtSlot(QtGui.QListWidgetItem)
    def hostgame_clicked(self, item):
        """
        Hosting a game event
        """
        if not fa.instance.available():
            return

        self.stop_search_ranked()

        hostgamewidget = HostGameWidget(self, item)
        # Abort if the client cancelled the host game dialogue.
        if hostgamewidget.exec_() != 1:
            return

    def sortgamescombo_changed(self, index):
        self.sort_games_index = index
        self.gameList.sortBy = index
        self.gameList.sortItems()
