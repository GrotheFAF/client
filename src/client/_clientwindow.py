from functools import partial

from PyQt4.QtCore import QUrl
from PyQt4.QtGui import QLabel

import config
import connectivity
from config import Settings
import chat
from client.player import Player
from client.players import Players
from client.connection import LobbyInfo, ServerConnection, \
        Dispatcher, ConnectionState, ServerReconnecter
from client.updater import ClientUpdater, GithubUpdateChecker
from client.theme_menu import ThemeMenu
import fa
from connectivity.helper import ConnectivityHelper
from fa import GameSession
from fa.factions import Factions
from fa.maps import getUserMapsFolder
from modvault.utils import MODFOLDER
from ui.status_logo import StatusLogo
from client.login import LoginWidget

"""
Created on Dec 1, 2011

@author: thygrrr
"""

from PyQt4 import QtCore, QtGui, QtWebKit

from client import ClientState, LOBBY_HOST, LOBBY_PORT, LOCAL_REPLAY_PORT

import logging

logger = logging.getLogger(__name__)

import util
import secondaryServer

import json
import replays

import time
import client
import notifications as ns

FormClass, BaseClass = util.load_ui_type("client/client.ui")


class MousePosition(object):
    def __init__(self):
        self.onLeftEdge = False
        self.onRightEdge = False
        self.onTopEdge = False
        self.onBottomEdge = False

        self.onTopLeftEdge = False
        self.onBottomLeftEdge = False
        self.onTopRightEdge = False
        self.onBottomRightEdge = False

        self.onEdges = False

        self.cursorShapeChange = False
        self.warning_buttons = dict()

    def compute_mouse_position(self, pos):
        self.onLeftEdge = pos.x() < 8
        self.onRightEdge = pos.x() > client.instance.size().width() - 8
        self.onTopEdge = pos.y() < 8
        self.onBottomEdge = pos.y() > client.instance.size().height() - 8

        self.onTopLeftEdge = self.onTopEdge and self.onLeftEdge
        self.onBottomLeftEdge = self.onBottomEdge and self.onLeftEdge
        self.onTopRightEdge = self.onTopEdge and self.onRightEdge
        self.onBottomRightEdge = self.onBottomEdge and self.onRightEdge

        self.onEdges = self.onLeftEdge or self.onRightEdge or self.onTopEdge or self.onBottomEdge

    def reset_to_false(self):
        self.onLeftEdge = False
        self.onRightEdge = False
        self.onTopEdge = False
        self.onBottomEdge = False
        self.cursorShapeChange = False

    def is_on_edge(self):
        return self.onEdges


class ClientWindow(FormClass, BaseClass):
    """
    This is the main lobby client that manages the FAF-related connection and data,
    in particular players, games, ranking, etc.
    Its UI also houses all the other UIs for the sub-modules.
    """

    topWidget = QtGui.QWidget()

    state_changed = QtCore.pyqtSignal(object)
    authorized = QtCore.pyqtSignal(object)

    # These signals notify connected modules of game state changes (i.e. reasons why FA is launched)
    viewingReplay = QtCore.pyqtSignal(QtCore.QUrl)

    # Game state controls
    gameEnter = QtCore.pyqtSignal()
    gameExit = QtCore.pyqtSignal()

    # These signals propagate important client state changes to other modules
    usersUpdated = QtCore.pyqtSignal(list)
    localBroadcast = QtCore.pyqtSignal(str, str)
    autoJoin = QtCore.pyqtSignal(list)
    channelsUpdated = QtCore.pyqtSignal(list)

    # These signals are emitted whenever a certain tab is activated
    showReplays = QtCore.pyqtSignal()
    showMaps = QtCore.pyqtSignal()
    showGames = QtCore.pyqtSignal()
    showTourneys = QtCore.pyqtSignal()
    showLadder = QtCore.pyqtSignal()
    showChat = QtCore.pyqtSignal()
    showMods = QtCore.pyqtSignal()
    showCoop = QtCore.pyqtSignal()

    matchmakerInfo = QtCore.pyqtSignal(dict)

    remember = Settings.persisted_property('user/remember', key_type=bool, default_value=True)
    login = Settings.persisted_property('user/login', persist_if=lambda self: self.remember)
    password = Settings.persisted_property('user/password', persist_if=lambda self: self.remember)

    gamelogs = Settings.persisted_property('game/logs', key_type=bool, default_value=True)
    useUPnP = Settings.persisted_property('game/upnp', key_type=bool, default_value=True)
    gamePort = Settings.persisted_property('game/port', key_type=int, default_value=6112)

    def __init__(self, *args, **kwargs):
        BaseClass.__init__(self, *args, **kwargs)

        logger.debug("Client instantiating")

        # Hook to Qt's application management system
        QtGui.QApplication.instance().aboutToQuit.connect(self.cleanup)

        self.uniqueId = None

        self.sendFile = False
        self.progress = QtGui.QProgressDialog()
        self.progress.setMinimum(0)
        self.progress.setMaximum(0)
        self.warning_buttons = {}

        # Tray icon
        self.tray = QtGui.QSystemTrayIcon()
        self.tray.setIcon(util.icon("client/tray_icon.png"))
        self.tray.show()

        self._state = ClientState.NONE
        self.session = None

        # This dictates whether we login automatically in the beginning or
        # after a disconnect. We turn it on if we're sure we have correct
        # credentials and want to use them (if we were remembered or after
        # login) and turn it off if we're getting fresh credentials or
        # encounter a serious server error.
        self._autorelogin = self.remember

        self.lobby_dispatch = Dispatcher()
        self.lobby_connection = ServerConnection(LOBBY_HOST, LOBBY_PORT, self.lobby_dispatch.dispatch)
        self.lobby_connection.state_changed.connect(self.on_connection_state_changed)
        self.lobby_reconnecter = ServerReconnecter(self.lobby_connection)
        self.lobby_info = LobbyInfo(self.lobby_dispatch)
        self.lobby_info.gameInfo.connect(self.fill_in_session_info)

        self.lobby_dispatch["session"] = self.handle_session
        self.lobby_dispatch["registration_response"] = self.handle_registration_response
        self.lobby_dispatch["game_launch"] = self.handle_game_launch
        self.lobby_dispatch["matchmaker_info"] = self.handle_matchmaker_info
        self.lobby_dispatch["social"] = self.handle_social
        self.lobby_dispatch["player_info"] = self.handle_player_info
        self.lobby_dispatch["notice"] = self.handle_notice
        self.lobby_dispatch["invalid"] = self.handle_invalid
        self.lobby_dispatch["update"] = self.handle_update
        self.lobby_dispatch["welcome"] = self.handle_welcome
        self.lobby_dispatch["authentication_failed"] = self.handle_authentication_failed

        # Process used to run Forged Alliance (managed in module fa)
        fa.instance.started.connect(self.started_fa)
        fa.instance.finished.connect(self.finished_fa)
        fa.instance.error.connect(self.error_fa)
        self.lobby_info.gameInfo.connect(fa.instance.process_game_info)

        # Local Replay Server
        self.replayServer = fa.replayserver.ReplayServer(self)

        # GameSession
        self.game_session = None  # type: GameSession

        # ConnectivityTest
        self.connectivity = None  # type: ConnectivityHelper

        # stat server
        self.statsServer = secondaryServer.SecondaryServer("Statistic", 11002, self.lobby_dispatch)

        # create user interface (main window) and load theme
        self.setupUi(self)
        util.set_stylesheet(self, "client/client.css")

        self.setWindowTitle("FA Forever " + util.VERSION_STRING)

        # Frameless
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowSystemMenuHint | QtCore.Qt.WindowMinimizeButtonHint)

        self.rubberBand = QtGui.QRubberBand(QtGui.QRubberBand.Rectangle)

        self.MousePosition = MousePosition()
        self.installEventFilter(self)

        self.minimize = QtGui.QToolButton(self)
        self.minimize.setIcon(util.icon("client/minimize-button.png"))

        self.maximize = QtGui.QToolButton(self)
        self.maximize.setIcon(util.icon("client/maximize-button.png"))

        close = QtGui.QToolButton(self)
        close.setIcon(util.icon("client/close-button.png"))

        self.minimize.setMinimumHeight(10)
        close.setMinimumHeight(10)
        self.maximize.setMinimumHeight(10)

        close.setIconSize(QtCore.QSize(22, 22))
        self.minimize.setIconSize(QtCore.QSize(22, 22))
        self.maximize.setIconSize(QtCore.QSize(22, 22))

        close.setProperty("windowControlBtn", True)
        self.maximize.setProperty("windowControlBtn", True)
        self.minimize.setProperty("windowControlBtn", True)

        self.logo = StatusLogo(self)
        self.logo.disconnect_requested.connect(self.disconnect)
        self.logo.reconnect_requested.connect(self.reconnect)
        self.logo.about_dialog_requested.connect(self.link_about)
        self.logo.connectivity_dialog_requested.connect(self.connectivity_dialog)

        self.menu = self.menuBar()
        self.topLayout.addWidget(self.logo)
        title_label = QLabel("FA Forever" if not config.is_beta() else "FA Forever BETA")
        title_label.setProperty('titleLabel', True)
        self.topLayout.addWidget(title_label)
        self.topLayout.addStretch(500)
        self.topLayout.addWidget(self.menu)
        self.topLayout.addWidget(self.minimize)
        self.topLayout.addWidget(self.maximize)
        self.topLayout.addWidget(close)
        self.topLayout.setSpacing(0)
        self.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Fixed)
        self.maxNormal = False

        close.clicked.connect(self.close)
        self.minimize.clicked.connect(self.show_small)
        self.maximize.clicked.connect(self.show_max_restore)

        self.moving = False
        self.dragging = False
        self.draggingHover = False
        self.offset = None
        self.curSize = None

        size_grip = QtGui.QSizeGrip(self)
        self.mainGridLayout.addWidget(size_grip, 2, 2)

        # Wire all important signals
        self.mainTabs.currentChanged.connect(self.main_tab_changed)
        self.topTabs.currentChanged.connect(self.vault_tab_changed)

        # Handy reference to the Player object representing the logged-in user.
        self.me = None  # FIXME: Move it elsewhere

        # Players known to the client, contains the player_info messages sent by the server
        self.players = Players(self.me)
        self.urls = {}

        self.power = 0  # current user power
        self.id = 0
        # Initialize the Menu Bar according to settings etc.
        self.init_menus()

        # Load the icons for the tabs
        self.mainTabs.setTabIcon(self.mainTabs.indexOf(self.whatNewTab), util.icon("client/feed.png"))
        self.mainTabs.setTabIcon(self.mainTabs.indexOf(self.chatTab), util.icon("client/chat.png"))
        self.mainTabs.setTabIcon(self.mainTabs.indexOf(self.gamesTab), util.icon("client/games.png"))
        self.mainTabs.setTabIcon(self.mainTabs.indexOf(self.coopTab), util.icon("client/coop.png"))
        self.mainTabs.setTabIcon(self.mainTabs.indexOf(self.vaultsTab), util.icon("client/mods.png"))
        self.mainTabs.setTabIcon(self.mainTabs.indexOf(self.ladderTab), util.icon("client/ladder.png"))
        self.mainTabs.setTabIcon(self.mainTabs.indexOf(self.tourneyTab), util.icon("client/tourney.png"))
        self.mainTabs.setTabIcon(self.mainTabs.indexOf(self.unitdbTab), util.icon("client/twitch.png"))
        self.mainTabs.setTabIcon(self.mainTabs.indexOf(self.replaysTab), util.icon("client/replays.png"))
        self.mainTabs.setTabIcon(self.mainTabs.indexOf(self.tutorialsTab), util.icon("client/tutorials.png"))

        QtWebKit.QWebSettings.globalSettings().setAttribute(QtWebKit.QWebSettings.PluginsEnabled, True)

        # for moderator
        self.modMenu = None

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value
        client.instance.stateLabel.setText(str(self.state))  # TESTING-IO Grothe
        self.state_changed.emit(value)

    def on_connection_state_changed(self, state):
        if self.state == ClientState.SHUTDOWN:
            return

        if state == ConnectionState.CONNECTED:
            self.on_connected()
            self.state = ClientState.CONNECTED
        elif state == ConnectionState.DISCONNECTED:
            self.on_disconnected()
            self.state = ClientState.DISCONNECTED
        elif state == ConnectionState.CONNECTING:
            self.state = ClientState.CONNECTING

    def on_connected(self):
        # Enable reconnect in case we used to explicitly stay offline
        self.lobby_reconnecter.enabled = True
        self.lobby_connection.send(dict(command="ask_session", version=config.VERSION, user_agent="faf-client"))

    def on_disconnected(self):
        logger.warn("Disconnected from lobby server.")
        self.clear_players()

    @QtCore.pyqtSlot(bool)
    def on_action_savegamelogs_toggled(self, value):
        self.gamelogs = value

    @QtCore.pyqtSlot(bool)
    def on_action_auto_download_mods_toggled(self, value):
        Settings.set('mods/autodownload', value is True)

    @QtCore.pyqtSlot(bool)
    def on_action_auto_download_maps_toggled(self, value):
        Settings.set('maps/autodownload', value is True)

    def eventFilter(self, obj, event):  # Qt Event handler
        if event.type() == QtCore.QEvent.HoverMove:
            self.draggingHover = self.dragging
            if self.dragging:
                self.resize_widget(self.mapToGlobal(event.pos()))
            else:
                if not self.maxNormal:
                    self.MousePosition.compute_mouse_position(event.pos())
                else:
                    self.MousePosition.reset_to_false()
            self.update_cursor_shape(event.pos())

        return False

    def update_cursor_shape(self, pos):
        if self.MousePosition.onTopLeftEdge or self.MousePosition.onBottomRightEdge:
            self.MousePosition.cursorShapeChange = True
            self.setCursor(QtCore.Qt.SizeFDiagCursor)
        elif self.MousePosition.onTopRightEdge or self.MousePosition.onBottomLeftEdge:
            self.setCursor(QtCore.Qt.SizeBDiagCursor)
            self.MousePosition.cursorShapeChange = True
        elif self.MousePosition.onLeftEdge or self.MousePosition.onRightEdge:
            self.setCursor(QtCore.Qt.SizeHorCursor)
            self.MousePosition.cursorShapeChange = True
        elif self.MousePosition.onTopEdge or self.MousePosition.onBottomEdge:
            self.setCursor(QtCore.Qt.SizeVerCursor)
            self.MousePosition.cursorShapeChange = True
        else:
            if self.MousePosition.cursorShapeChange:
                self.unsetCursor()
                self.MousePosition.cursorShapeChange = False

    def show_small(self):
        self.showMinimized()

    def show_max_restore(self):
        if self.maxNormal:
            self.maxNormal = False
            if self.curSize:
                self.setGeometry(self.curSize)

        else:
            self.maxNormal = True
            self.curSize = self.geometry()
            self.setGeometry(QtGui.QDesktopWidget().availableGeometry(self))

    def mouseDoubleClickEvent(self, event):  # Qt Event handler
        self.show_max_restore()

    def mouseReleaseEvent(self, event):  # Qt Event handler
        self.dragging = False
        self.moving = False
        if self.rubberBand.isVisible():
            self.maxNormal = True
            self.curSize = self.geometry()
            self.setGeometry(self.rubberBand.geometry())
            self.rubberBand.hide()
            # self.show_max_restore()

    def mousePressEvent(self, event):  # Qt Event handler
        if event.button() == QtCore.Qt.LeftButton:
            if self.MousePosition.is_on_edge() and not self.maxNormal:
                self.dragging = True
                return
            else:
                self.dragging = False

            self.moving = True
            self.offset = event.pos()

    def mouseMoveEvent(self, event):  # Qt Event handler
        if self.dragging and not self.draggingHover:
            self.resize_widget(event.globalPos())

        elif self.moving and self.offset is not None:
            desktop = QtGui.QDesktopWidget().availableGeometry(self)
            if event.globalPos().y() == 0:
                self.rubberBand.setGeometry(desktop)
                self.rubberBand.show()
            elif event.globalPos().x() == 0:
                desktop.setRight(desktop.right() / 2.0)
                self.rubberBand.setGeometry(desktop)
                self.rubberBand.show()
            elif event.globalPos().x() == desktop.right():
                desktop.setRight(desktop.right() / 2.0)
                desktop.moveLeft(desktop.right())
                self.rubberBand.setGeometry(desktop)
                self.rubberBand.show()

            else:
                self.rubberBand.hide()
                if self.maxNormal:
                    self.show_max_restore()

            self.move(event.globalPos() - self.offset)

    def resize_widget(self, global_mouse_pos):
        if global_mouse_pos.y() == 0:
            self.rubberBand.setGeometry(QtGui.QDesktopWidget().availableGeometry(self))
            self.rubberBand.show()
        else:
            self.rubberBand.hide()

        orig_rect = self.frameGeometry()

        left, top, right, bottom = orig_rect.getCoords()
        min_width = self.minimumWidth()
        min_height = self.minimumHeight()
        if self.MousePosition.onTopLeftEdge:
            left = global_mouse_pos.x()
            top = global_mouse_pos.y()

        elif self.MousePosition.onBottomLeftEdge:
            left = global_mouse_pos.x()
            bottom = global_mouse_pos.y()
        elif self.MousePosition.onTopRightEdge:
            right = global_mouse_pos.x()
            top = global_mouse_pos.y()
        elif self.MousePosition.onBottomRightEdge:
            right = global_mouse_pos.x()
            bottom = global_mouse_pos.y()
        elif self.MousePosition.onLeftEdge:
            left = global_mouse_pos.x()
        elif self.MousePosition.onRightEdge:
            right = global_mouse_pos.x()
        elif self.MousePosition.onTopEdge:
            top = global_mouse_pos.y()
        elif self.MousePosition.onBottomEdge:
            bottom = global_mouse_pos.y()

        new_rect = QtCore.QRect(QtCore.QPoint(left, top), QtCore.QPoint(right, bottom))
        if new_rect.isValid():
            if min_width > new_rect.width():
                if left != orig_rect.left():
                    new_rect.setLeft(orig_rect.left())
                else:
                    new_rect.setRight(orig_rect.right())
            if min_height > new_rect.height():
                if top != orig_rect.top():
                    new_rect.setTop(orig_rect.top())
                else:
                    new_rect.setBottom(orig_rect.bottom())

            self.setGeometry(new_rect)

    def setup(self):
        import chat
        import tourneys
        import stats
        import vault
        import games
        import tutorials
        import downloadManager
        import modvault
        import coop
        import news
        from chat._avatarWidget import AvatarWidget

        # download manager
        self.downloader = downloadManager.DownloadManager(self)

        self.load_settings()

        # Initialize chat
        self.chat = chat.ChatWidget(self)
        # Color table used by the following method
        # CAVEAT: This will break if the theme is loaded after the client package is imported
        chat.CHAT_COLORS = json.loads(util.readfile("client/colors.json"))

        # build main window with the now active client
        self.news = news.NewsWidget()
        self.ladder = stats.StatsWidget()
        self.games = games.GamesWidget()
        self.tourneys = tourneys.TournamentsWidget()
        self.vault = vault.MapVault()
        self.modvault = modvault.ModVault()
        self.replays = replays.ReplaysWidget(self.lobby_dispatch)
        self.tutorials = tutorials.TutorialsWidget()
        self.Coop = coop.CoopWidget()
        self.notificationSystem = ns.Notifications()

        # set menu states
        self.actionNsEnabled.setChecked(self.notificationSystem.settings.enabled)

        # Other windows
        self.avatarAdmin = self.avatarSelection = AvatarWidget(None)

        # warning setup
        self.warning = QtGui.QHBoxLayout()

        # units database (ex. live streams)
        # old unitDB
        self.unitdbWebView.setUrl(QtCore.QUrl("http://direct.faforever.com/faf/unitsDB"))
        # spookys unitDB (will be moved to site)
        # self.unitdbWebView.setUrl(QtCore.QUrl("http://spooky.github.io/unitdb/#/"))

        self.warnPlayer = QtGui.QLabel(self)
        self.warnPlayer.setText(
            "A player of your skill level is currently searching for a 1v1 game. Click a faction to join! ")
        self.warnPlayer.setAlignment(QtCore.Qt.AlignHCenter)
        self.warnPlayer.setAlignment(QtCore.Qt.AlignVCenter)
        self.warnPlayer.setProperty("warning", True)
        self.warning.addStretch()
        self.warning.addWidget(self.warnPlayer)

        def add_warning_button(faction):
            button = QtGui.QToolButton(self)
            button.setIconSize(QtCore.QSize(40, 20))
            # button.setMaximumSize(25, 25)
            button.setIcon(util.icon("replays/%s.png" % faction.to_name()))
            button.clicked.connect(partial(self.games.start_search_ranked, faction))
            self.warning.addWidget(button)
            return button

        self.warning_buttons = {faction: add_warning_button(faction) for faction in Factions}

        self.warning.addStretch()

        self.mainGridLayout.addLayout(self.warning, 2, 0)
        self.warning_hide()

        self._client_updater = ClientUpdater()
        self.github_updater = GithubUpdateChecker()
        self.github_updater.update_found.connect(self.github_update)
        self.github_updater.start()

    def warning_hide(self):
        """
        hide the warning bar for matchmaker
        """
        self.warnPlayer.hide()
        for i in self.warning_buttons.values():
            i.hide()

    def warning_show(self):
        """
        show the warning bar for matchmaker
        """
        self.warnPlayer.show()
        for i in self.warning_buttons.values():
            i.show()

    def reconnect(self):
        self.lobby_reconnecter.enabled = True
        self.lobby_connection.do_connect()

    def disconnect(self):
        "Used when the user explicitly demanded to stay offline."
        self.lobby_reconnecter.enabled = False
        self.lobby_connection.disconnect()
        self.chat.disconnect()

    @QtCore.pyqtSlot(dict)
    def github_update(self, update):
        logger.info('Got github update')
        version = update['name']
        prerelease = update['prerelease']
        assets = update['assets']
        url = update['html_url']
        download_url = None
        for asset in assets:
            if '.msi' in asset['browser_download_url']:
                download_url = asset['browser_download_url']
        if download_url is not None:
            self._client_updater.exec_(download_url, prerelease, url)

    @QtCore.pyqtSlot()
    def cleanup(self):
        """
        Perform cleanup before the UI closes
        """
        self.state = ClientState.SHUTDOWN

        self.progress.setWindowTitle("FAF is shutting down")
        self.progress.setMinimum(0)
        self.progress.setMaximum(0)
        self.progress.setValue(0)
        self.progress.setCancelButton(None)
        self.progress.show()

        # Important: If a game is running, offer to terminate it gently
        self.progress.setLabelText("Closing ForgedAllianceForever.exe")
        if fa.instance.running():
            fa.instance.close()

        # Terminate Lobby Server connection
        self.lobby_reconnecter.enabled = False
        if self.lobby_connection.socket_connected():
            self.progress.setLabelText("Closing main connection.")
            self.lobby_connection.disconnect()

        # Clear UPnP Mappings...
        if self.useUPnP:
            self.progress.setLabelText("Removing UPnP port mappings")
            fa.upnp.remove_port_mappings()

        # Terminate local ReplayServer
        if self.replayServer:
            self.progress.setLabelText("Terminating local replay server")
            self.replayServer.close()
            self.replayServer = None

        # Clean up Chat
        if self.chat:
            self.progress.setLabelText("Disconnecting from IRC")
            self.chat.disconnect()
            self.chat = None

        # Get rid of the Tray icon
        if self.tray:
            self.progress.setLabelText("Removing System Tray icon")
            self.tray.deleteLater()
            self.tray = None

        # Terminate UI
        if self.isVisible():
            self.progress.setLabelText("Closing main window")
            self.close()

        self.progress.close()

    def closeEvent(self, event):  # Qt Event handler
        logger.info("Close Event for Application Main Window")
        self.save_window()

        if fa.instance.running():
            if QtGui.QMessageBox.question(client.instance, "Are you sure?",
                                          "Seems like you still have Forged Alliance running!<br/><b>Close anyway?</b>",
                                          QtGui.QMessageBox.Yes, QtGui.QMessageBox.No) == QtGui.QMessageBox.No:
                event.ignore()
                return

        return QtGui.QMainWindow.closeEvent(client.instance, event)

    def init_menus(self):
        self.actionLink_account_to_Steam.triggered.connect(partial(self.open_url, Settings.get("STEAMLINK_URL")))
        self.actionLinkWebsite.triggered.connect(partial(self.open_url, Settings.get("WEBSITE_URL")))
        self.actionLinkWiki.triggered.connect(partial(self.open_url, Settings.get("WIKI_URL")))
        self.actionLinkForums.triggered.connect(partial(self.open_url, Settings.get("FORUMS_URL")))
        self.actionLinkUnitDB.triggered.connect(partial(self.open_url, Settings.get("UNITDB_URL")))
        self.actionLinkGitHub.triggered.connect(partial(self.open_url, Settings.get("GITHUB_URL")))

        self.actionNsSettings.triggered.connect(lambda: self.notificationSystem.on_show_settings())
        self.actionNsEnabled.triggered.connect(lambda enabled: self.notificationSystem.set_notification_enabled(enabled))

        self.actionWiki.triggered.connect(partial(self.open_url, Settings.get("WIKI_URL")))
        self.actionReportBug.triggered.connect(partial(self.open_url, Settings.get("TICKET_URL")))
        self.actionShowLogs.triggered.connect(self.link_show_logs)
        self.actionTechSupport.triggered.connect(partial(self.open_url, Settings.get("SUPPORT_URL")))
        self.actionAbout.triggered.connect(self.link_about)

        self.actionClearCache.triggered.connect(self.clear_cache)
        self.actionClearSettings.triggered.connect(self.clear_settings)
        self.actionClearGameFiles.triggered.connect(self.clear_game_files)

        self.actionSetGamePath.triggered.connect(self.switch_path)
        self.actionSetGamePort.triggered.connect(self.switch_port)

        self.actionShowMapsDir.triggered.connect(lambda: util.showDirInFileBrowser(getUserMapsFolder()))
        self.actionShowModsDir.triggered.connect(lambda: util.showDirInFileBrowser(MODFOLDER))
        self.actionShowReplaysDir.triggered.connect(lambda: util.showDirInFileBrowser(util.REPLAY_DIR))
        # if game.prefs doesn't exist: show_dir -> empty folder / show_file -> 'file doesn't exist' message
        self.actionShowGamePrefs.triggered.connect(lambda: util.showDirInFileBrowser(util.LOCALFOLDER))
        #self.actionShowGamePrefs.triggered.connect(lambda: util.showFileInFileBrowser(util.PREFSFILENAME))

        # Toggle-Options
        self.actionSetAutoLogin.triggered.connect(self.update_options)
        self.actionSetAutoLogin.setChecked(self.remember)
        self.actionSetAutoDownloadMods.toggled.connect(self.on_action_auto_download_mods_toggled)
        self.actionSetAutoDownloadMods.setChecked(Settings.get('mods/autodownload', key_type=bool, default=False))
        self.actionSetAutoDownloadMaps.toggled.connect(self.on_action_auto_download_maps_toggled)
        self.actionSetAutoDownloadMaps.setChecked(Settings.get('maps/autodownload', key_type=bool, default=False))
        self.actionSetSoundEffects.triggered.connect(self.update_options)
        self.actionSetOpenGames.triggered.connect(self.update_options)
        self.actionSetJoinsParts.triggered.connect(self.update_options)
        self.actionSetLiveReplays.triggered.connect(self.update_options)
        self.actionSaveGamelogs.toggled.connect(self.on_action_savegamelogs_toggled)
        self.actionSaveGamelogs.setChecked(self.gamelogs)
        self.actionColoredNicknames.triggered.connect(self.update_options)
        self.actionFriendsOnTop.triggered.connect(self.update_options)

        self._menuThemeHandler = ThemeMenu(self.menuTheme)
        self._menuThemeHandler.setup(util.list_themes())
        self._menuThemeHandler.themeSelected.connect(lambda theme: util.set_theme(theme, True))

    @QtCore.pyqtSlot()
    def update_options(self):
        self.remember = self.actionSetAutoLogin.isChecked()
        self.soundeffects = self.actionSetSoundEffects.isChecked()
        self.opengames = self.actionSetOpenGames.isChecked()
        self.joinsparts = self.actionSetJoinsParts.isChecked()
        self.livereplays = self.actionSetLiveReplays.isChecked()

        self.gamelogs = self.actionSaveGamelogs.isChecked()
        self.players.coloredNicknames = self.actionColoredNicknames.isChecked()
        self.friendsontop = self.actionFriendsOnTop.isChecked()

        self.save_chat()

    @QtCore.pyqtSlot()
    def switch_path(self):
        fa.wizards.Wizard(self).exec_()

    @QtCore.pyqtSlot()
    def switch_port(self):
        import loginwizards
        loginwizards.GameSettingsWizard(self).exec_()

    @QtCore.pyqtSlot()
    def clear_settings(self):
        result = QtGui.QMessageBox.question(client.instance, "Clear Settings",
                                            "Are you sure you wish to clear all settings, login info, etc. used by "
                                            "this program?", QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
        if result == QtGui.QMessageBox.Yes:
            util.settings.clear()
            util.settings.sync()
            QtGui.QMessageBox.information(client.instance, "Restart Needed", "FAF will quit now.", "Quit")
            QtGui.QApplication.quit()

    @QtCore.pyqtSlot()
    def clear_game_files(self):
        util.clear_directory(util.BIN_DIR)
        util.clear_directory(util.GAMEDATA_DIR)

    @QtCore.pyqtSlot()
    def clear_cache(self):
        changed = util.clear_directory(util.CACHE_DIR)
        if changed:
            QtGui.QMessageBox.information(client.instance, "Restart Needed", "FAF will quit now.", "Quit")
            QtGui.QApplication.quit()

    # Clear the online users lists
    def clear_players(self):
        oldplayers = self.players.keys()
        self.players = Players(self.me)
        self.urls = {}
        self.usersUpdated.emit(oldplayers)

    @QtCore.pyqtSlot(str)
    def open_url(self, url):
        QtGui.QDesktopServices.openUrl(QUrl(url))

    @QtCore.pyqtSlot()
    def link_show_logs(self):
        util.show_dir_in_file_browser(util.LOG_DIR)

    @QtCore.pyqtSlot()
    def connectivity_dialog(self):
        dialog = connectivity.ConnectivityDialog(self.connectivity)
        dialog.exec_()

    @QtCore.pyqtSlot()
    def link_about(self):
        dialog = util.load_ui("client/about.ui")
        dialog.version_label.setText("Version: {}".format(util.VERSION_STRING))
        dialog.exec_()

    def save_window(self):
        util.settings.beginGroup("window")
        util.settings.setValue("geometry", self.saveGeometry())
        util.settings.endGroup()

    def save_chat(self):
        util.settings.beginGroup("chat")
        util.settings.setValue("soundeffects", self.soundeffects)
        util.settings.setValue("livereplays", self.livereplays)
        util.settings.setValue("opengames", self.opengames)
        util.settings.setValue("joinsparts", self.joinsparts)
        util.settings.setValue("coloredNicknames", self.players.coloredNicknames)
        util.settings.setValue("friendsontop", self.friendsontop)
        util.settings.endGroup()

    def load_settings(self):
        self.load_chat()
        # Load settings
        util.settings.beginGroup("window")
        geometry = util.settings.value("geometry", None)
        if geometry:
            self.restoreGeometry(geometry)
        util.settings.endGroup()

        util.settings.beginGroup("ForgedAlliance")
        util.settings.endGroup()

    def load_chat(self):
        try:
            util.settings.beginGroup("chat")
            self.soundeffects = (util.settings.value("soundeffects", "true") == "true")
            self.opengames = (util.settings.value("opengames", "true") == "true")
            self.joinsparts = (util.settings.value("joinsparts", "false") == "true")
            self.livereplays = (util.settings.value("livereplays", "true") == "true")
            self.players.coloredNicknames = (util.settings.value("coloredNicknames", "false") == "true")
            self.friendsontop = (util.settings.value("friendsontop", "false") == "true")

            util.settings.endGroup()
            self.actionColoredNicknames.setChecked(self.players.coloredNicknames)
            self.actionFriendsOnTop.setChecked(self.friendsontop)
            self.actionSetSoundEffects.setChecked(self.soundeffects)
            self.actionSetLiveReplays.setChecked(self.livereplays)
            self.actionSetOpenGames.setChecked(self.opengames)
            self.actionSetJoinsParts.setChecked(self.joinsparts)
        except:
            pass

    def do_connect(self):
        if not self.replayServer.do_listen(LOCAL_REPLAY_PORT):
            return False

        self.lobby_connection.do_connect()
        return True

    def set_remember(self, remember):
        self.remember = remember
        self.actionSetAutoLogin.setChecked(self.remember) # FIXME - option updating is silly

    def get_creds_and_login(self):
        # Try to autologin, or show login widget if we fail or can't do that.
        if self._autorelogin and self.password and self.login:
            if self.send_login(self.login, self.password):
                return

        self.show_login_widget()

    def show_login_widget(self):
        login_widget = LoginWidget(self.login, self.remember)
        login_widget.finished.connect(self.on_widget_login_data)
        login_widget.rejected.connect(self.on_widget_no_login)
        login_widget.remember.connect(self.set_remember)
        login_widget.exec_()

    def on_widget_login_data(self, login, password):
        self.login = login
        self.password = password

        if self.send_login(login, password):
            return
        self.show_login_widget()

    def on_widget_no_login(self):
        self.disconnect()

    def send_login(self, login, password):
        # Send login data once we have the creds.
        self._autorelogin = False  # Fresh credentials
        if config.is_beta():    # Replace for develop here to not clobber the real pass
            password = util.password_hash("foo")
        self.uniqueId = util.unique_id(self.login, self.session)
        if not self.uniqueId:
            QtGui.QMessageBox.critical(self, "Failed to calculate UID",
                                       "Failed to calculate your unique ID"
                                       " (a part of our smurf prevention system).</br>"
                                       "Please report this to the tech support forum!", "Very Sad!")
            return False
        self.lobby_connection.send(dict(command="hello",
                       login=login,
                       password=password,
                       unique_id=self.uniqueId,
                       session=self.session))
        return True

    @staticmethod
    def get_color(name):
        return chat.get_color(name)

    @QtCore.pyqtSlot()
    def started_fa(self):
        """
        Slot hooked up to fa.instance when the process has launched.
        It will notify other modules through the signal gameEnter().
        """
        logger.info("FA has launched in an attached process.")
        self.gameEnter.emit()

    @QtCore.pyqtSlot(int)
    def finished_fa(self, exit_code):
        """
        Slot hooked up to fa.instance when the process has ended.
        It will notify other modules through the signal gameExit().
        """
        if not exit_code:
            logger.info("FA has finished with exit code: " + str(exit_code))
        else:
            logger.warn("FA has finished with exit code: " + str(exit_code))
        self.gameExit.emit()

    @QtCore.pyqtSlot(int)
    def error_fa(self, error_code):
        """
        Slot hooked up to fa.instance when the process has failed to start.
        """
        logger.error("FA has died with error: " + fa.instance.errorString())
        if error_code == 0:
            logger.error("FA has failed to start")
            QtGui.QMessageBox.critical(client.instance, "Error from FA", "FA has failed to start.", "Sad!")
        elif error_code == 1:
            logger.error("FA has crashed or killed after starting")
        else:
            text = "FA has failed to start with error code: " + str(error_code)
            logger.error(text)
            QtGui.QMessageBox.critical(client.instance, "Error from FA", text, QtGui.QMessageBox.Ok)
        self.gameExit.emit()

    @QtCore.pyqtSlot(int)
    def main_tab_changed(self, index):
        """
        The main visible tab (module) of the client's UI has changed.
        In this case, other modules may want to load some data or cease
        particularly CPU-intensive interactive functionality.
        LATER: This can be rewritten as a simple Signal that each module can then individually connect to.
        """
        new_tab = self.mainTabs.widget(index)
        if new_tab is self.gamesTab:
            self.showGames.emit()

        if new_tab is self.chatTab:
            self.showChat.emit()

        if new_tab is self.replaysTab:
            self.showReplays.emit()

        if new_tab is self.ladderTab:
            self.showLadder.emit()

        if new_tab is self.tourneyTab:
            self.showTourneys.emit()

        if new_tab is self.coopTab:
            self.showCoop.emit()

    @QtCore.pyqtSlot(int)
    def vault_tab_changed(self, index):
        new_tab = self.topTabs.widget(index)

        if new_tab is self.mapsTab:
            self.showMaps.emit()

        if new_tab is self.modsTab:
            self.showMods.emit()

    @QtCore.pyqtSlot()
    def join_game_from_url(self, url):
        """
        Tries to join the game at the given URL
        """
        logger.debug("joinGameFromURL: " + url.toString())
        if fa.instance.available():
            add_mods = []
            try:
                modstr = url.queryItemValue("mods")
                add_mods = json.loads(modstr)  # should be a list
            except:
                logger.info("Couldn't load urlquery value 'mods'")
            if fa.check.game(self):
                uid, mod, map = url.queryItemValue('uid'), url.queryItemValue('mod'), url.queryItemValue('map')
                if fa.check.check(mod, map, sim_mods=add_mods):
                    self.join_game(uid)

    @QtCore.pyqtSlot()
    def forward_local_broadcast(self, source, message):
        self.localBroadcast.emit(source, message)

    def manage_power(self):
        """ update the interface accordingly to the power of the user """
        if self.power >= 1:
            if self.modMenu is None:
                self.modMenu = self.menu.addMenu("Administration")

            action_avatar = QtGui.QAction("Avatar manager", self.modMenu)
            action_avatar.triggered.connect(self.avatar_manager)
            self.modMenu.addAction(action_avatar)

            self.modMenu.addSeparator()

            actionLobbyKick = QtGui.QAction("Close player's FAF Client...", self.modMenu)
            actionLobbyKick.triggered.connect(lambda: util.userNameAction(self, 'Player to kick from Client (do not typo!)', lambda name: self.closeLobby(name)))
            self.modMenu.addAction(actionLobbyKick)

            actionCloseFA = QtGui.QAction("Close Player's Game...", self.modMenu)
            actionCloseFA.triggered.connect(lambda: util.userNameAction(self, 'Player to close FA (do not typo!)', lambda name: self.closeFA(name)))
            self.modMenu.addAction(actionCloseFA)

    def request_avatars(self, personal):
        if personal:
            self.lobby_connection.send(dict(command="avatar", action="list_avatar"))
        else:
            self.lobby_connection.send(dict(command="admin", action="requestavatars"))

    def join_channel(self, username, channel):
        """ Join users to a channel """
        self.lobby_connection.send(dict(command="admin", action="join_channel",
                                        user_ids=[self.players.get_id(username)], channel=channel))

    def close_fa(self, username):
        """ Close FA remotely """
        logger.info('closeFA for {}'.format(username))
        user_id = self.players.getID(username)
        if user_id != -1:
            self.lobby_connection.send(dict(command="admin", action="closeFA", user_id=user_id))

    def close_lobby(self, username):
        """ Close lobby remotely """
        logger.info('closeLobby for {}'.format(username))
        user_id = self.players.getID(username)
        if user_id != -1:
            self.lobby_connection.send(dict(command="admin", action="closelobby", user_id=user_id))

    def add_friend(self, friend_id):
        if friend_id in self.players:
            self.players.friends.add(friend_id)
            self.lobby_connection.send(dict(command="social_add", friend=friend_id))
            self.usersUpdated.emit([friend_id])

    def add_foe(self, foe_id):
        if foe_id in self.players:
            self.players.foes.add(foe_id)
            self.lobby_connection.send(dict(command="social_add", foe=foe_id))
            self.usersUpdated.emit([foe_id])

    def rem_friend(self, friend_id):
        if friend_id in self.players:
            self.players.friends.remove(friend_id)
            self.lobby_connection.send(dict(command="social_remove", friend=friend_id))
            self.usersUpdated.emit([friend_id])

    def rem_foe(self, foe_id):
        if foe_id in self.players:
            self.players.foes.remove(foe_id)
            self.lobby_connection.send(dict(command="social_remove", foe=foe_id))
            self.usersUpdated.emit([foe_id])

    def handle_session(self, message):
        # Getting here means our client is not outdated
        self._client_updater.notify_outdated(False)
        self.session = str(message['session'])
        self.get_creds_and_login()

    def handle_update(self, message):
        # Remove geometry settings prior to updating
        # could be incompatible with an updated client.
        Settings.remove('window/geometry')

        logger.warn("Server says we need an update")
        self.progress.close()
        self._client_updater.notify_outdated(True)

    def handle_welcome(self, message):
        self.state = ClientState.LOGGED_IN
        self._autorelogin = True
        self.id = message["id"]
        self.login = message["login"]
        self.me = Player(id=self.id, login=self.login)
        self.players[self.me.id] = self.me  # FIXME
        self.players.me = self.me  # FIXME
        logger.debug("Login success")

        util.crash.CRASH_REPORT_USER = self.login

        if self.useUPnP:
            self.lobby_connection.set_upnp(self.gamePort)

        self.update_options()

        self.authorized.emit(self.me)

        # Run an initial connectivity test and initialize a gamesession object
        # when done
        self.connectivity = ConnectivityHelper(self, self.gamePort)
        self.connectivity.connectivity_status_established.connect(self.initialize_game_session)
        self.connectivity.start_test()

    def initialize_game_session(self):
        self.game_session = GameSession(self.connectivity)

    def handle_registration_response(self, message):
        if message["result"] == "SUCCESS":
            return

        self.handle_notice({"style": "notice", "text": message["error"]})

    def search_ranked(self, faction):
        def request_launch():
            msg = {
                'command': 'game_matchmaking',
                'mod': 'ladder1v1',
                'state': 'start',
                'gameport': self.gamePort,
                'faction': faction
            }
            if self.connectivity.state == 'STUN':
                msg['relay_address'] = self.connectivity.relay_address
            self.lobby_connection.send(msg)
            self.game_session.ready.disconnect(request_launch)
        if self.game_session:
            self.game_session.ready.connect(request_launch)
            self.game_session.listen()

    def host_game(self, title, mod, visibility, mapname, password, is_rehost=False):
        def request_launch():
            msg = {
                'command': 'game_host',
                'title': title,
                'mod': mod,
                'visibility': visibility,
                'mapname': mapname,
                'password': password,
                'is_rehost': is_rehost
            }
            if self.connectivity.state == 'STUN':
                msg['relay_address'] = self.connectivity.relay_address
            self.lobby_connection.send(msg)
            self.game_session.ready.disconnect(request_launch)
        if self.game_session:
            self.game_session.game_password = password
            self.game_session.ready.connect(request_launch)
            self.game_session.listen()

    def join_game(self, uid, password=None):
        def request_launch():
            msg = {
                'command': 'game_join',
                'uid': uid,
                'gameport': self.gamePort
            }
            if password:
                msg['password'] = password
            if self.connectivity.state == "STUN":
                msg['relay_address'] = self.connectivity.relay_address
            self.lobby_connection.send(msg)
            self.game_session.ready.disconnect(request_launch)
        if self.game_session:
            self.game_session.game_password = password
            self.game_session.ready.connect(request_launch)
            self.game_session.listen()

    def handle_game_launch(self, message):
        if not self.game_session or not self.connectivity.is_ready:
            logger.error("Not ready for game launch")

        logger.info("Handling game_launch via JSON " + str(message))

        silent = False
        # Do some special things depending of the reason of the game launch.

        # HACK: Ideally, this comes from the server, too. LATER: search_ranked message
        arguments = []
        if message["mod"] == "ladder1v1":
            arguments.append('/' + Factions.to_name(self.games.race))
            # Player 1v1 rating
            arguments.append('/mean')
            arguments.append(str(self.me.ladder_rating_mean))
            arguments.append('/deviation')
            arguments.append(str(self.me.ladder_rating_deviation))
            arguments.append('/players 2')  # Always 2 players in 1v1 ladder
            arguments.append('/team 1')     # Always FFA team

            # Launch the auto lobby
            self.game_session.init_mode = 1

        else:
            # Player global rating
            arguments.append('/mean')
            arguments.append(str(self.me.rating_mean))
            arguments.append('/deviation')
            arguments.append(str(self.me.rating_deviation))
            if self.me.country is not None:
                arguments.append('/country ')
                arguments.append(self.me.country)

            # Launch the normal lobby
            self.game_session.init_mode = 0

        if self.me.clan is not None:
            arguments.append('/clan')
            arguments.append(self.me.clan)

        # Ensure we have the map
        if "mapname" in message:
            fa.check.map(message['mapname'], force=True, silent=silent)

        if "sim_mods" in message:
            fa.mods.check_mods(message['sim_mods'])

        # UPnP Mapper - mappings are removed on app exit
        if self.useUPnP:
            self.lobby_connection.set_upnp(self.gamePort)

        info = dict(uid=message['uid'], recorder=self.login, featured_mod=message['mod'], launched_at=time.time())

        self.game_session.game_uid = message['uid']

        fa.run(info, self.game_session.relay_port, arguments)

    def fill_in_session_info(self, message):
        if 'games' in message:
            return
        # sometimes we get the game_info message before a game session was created
        if self.game_session and message['uid'] == self.game_session.game_uid:
            self.game_session.game_map = message['mapname']
            self.game_session.game_mod = message['featured_mod']
            self.game_session.game_name = message['title']
            self.game_session.game_visibility = message['visibility']

    def handle_matchmaker_info(self, message):
        if not self.me:
            return
        if "action" in message:
            self.matchmakerInfo.emit(message)
        elif "queues" in message:
            if self.me.ladder_rating_deviation > 200 or self.games.searching:
                return
            key = 'boundary_80s' if self.me.ladder_rating_deviation < 100 else 'boundary_75s'
            show = False
            for q in message['queues']:
                if q['queue_name'] == 'ladder1v1':
                    mu = self.me.ladder_rating_mean
                    for min_q, max_q in q[key]:
                        if min_q < mu < max_q:
                            show = True
            if show:
                self.warning_show()
            else:
                self.warning_hide()

    def handle_social(self, message):
        if "friends" in message:
            self.players.friends = set(message["friends"])
            self.usersUpdated.emit(self.players.keys())

        if "foes" in message:
            self.players.foes = set(message["foes"])
            self.usersUpdated.emit(self.players.keys())

        if "channels" in message:
            # Add a delay to the notification system (insane cargo cult)
            self.notificationSystem.disabledStartup = False
            self.channelsUpdated.emit(message["channels"])

        if "autojoin" in message:
            self.autoJoin.emit(message["autojoin"])

        if "power" in message:
            self.power = message["power"]
            self.manage_power()

    def handle_player_info(self, message):
        players = message["players"]

        # Firstly, find yourself. Things get easier once "me" is assigned.
        for player in players:
            if player["id"] == self.id:
                self.me = Player(**player)

        for player in players:
            player_id = player["id"]
            new_player = Player(**player)

            self.players[player_id] = new_player
            self.usersUpdated.emit([player['login']])

            if self.me.clan is not None and new_player.clan == self.me.clan:
                self.players.clanlist.add(player['id'])

    def avatar_manager(self):
        self.request_avatars(0)
        self.avatarSelection.show()

    def handle_authentication_failed(self, message):
        QtGui.QMessageBox.warning(client.instance, "Authentication failed", message["text"], QtGui.QMessageBox.Ok)
        self._autorelogin = False
        self.get_creds_and_login()

    def handle_notice(self, message):
        if "text" in message:
            style = message.get('style', None)
            if style == "error":
                QtGui.QMessageBox.critical(client.instance, "Error from Server", message["text"], QtGui.QMessageBox.Ok)
            elif style == "warning":
                QtGui.QMessageBox.warning(client.instance, "Warning from Server", message["text"], QtGui.QMessageBox.Ok)
            elif style == "scores":
                self.tray.showMessage("Scores", message["text"], QtGui.QSystemTrayIcon.Information, 3500)
                self.localBroadcast.emit("Scores", message["text"])
            else:
                QtGui.QMessageBox.information(client.instance, "Notice from Server", message["text"], "Ok")

        if message["style"] == "kill":
            logger.info("Server has killed your Forged Alliance Process.")
            fa.instance.kill()

        if message["style"] == "kick":
            logger.info("Server has kicked you from the Lobby.")

        # This is part of the protocol - in this case we should not relogin automatically.
        if message["style"] in ["error", "kick"]:
            self._autorelogin = False

    @staticmethod
    def handle_invalid(self, message):
        # We did something wrong and the server will disconnect, let's not
        # reconnect and potentially cause the same error again and again
        self.lobby_reconnecter.enabled = False
        raise Exception(message)
