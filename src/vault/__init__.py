from PyQt4 import QtCore, QtGui
from PyQt4 import QtWebKit
from stat import *
import util
import logging
import os
from fa import maps
from vault import luaparser
import urllib2
import re
import client
from config import Settings

logger = logging.getLogger(__name__)


class FAFPage(QtWebKit.QWebPage):
    def __init__(self):
        super(QtWebKit.QWebPage, self).__init__()

    def userAgentForUrl(self, url):
        return "FAForever"


class MapVault(QtCore.QObject):
    def __init__(self, *args, **kwargs):
        QtCore.QObject.__init__(self, *args, **kwargs)

        logger.debug("Map Vault tab instantiating")

        self.ui = QtWebKit.QWebView()

        self.ui.setPage(FAFPage())

        self.ui.page().mainFrame().javaScriptWindowObjectCleared.connect(self.add_script)

        client.instance.mapsTab.layout().addWidget(self.ui)

        self.loaded = False
        client.instance.showMaps.connect(self.reload_view)
        self.ui.loadFinished.connect(self.ui.show)
        self.reload_view()

    @QtCore.pyqtSlot()
    def reload_view(self):
        if self.loaded:
            return
        self.loaded = True

        self.ui.setVisible(False)

#       If a local theme CSS exists, skin the WebView with it
        if util.themeurl("vault/style.css"):
            self.ui.settings().setUserStyleSheetUrl(
                util.themeurl("vault/style.css"))

        ROOT = Settings.get('content/host')

        url = QtCore.QUrl(ROOT)
        url.setPath("/faf/vault/maps.php")
        url.addQueryItem('username', client.instance.login)
        url.addQueryItem('pwdhash', client.instance.password)

        self.ui.setUrl(url)

    @QtCore.pyqtSlot()
    def add_script(self):
        frame = self.ui.page().mainFrame()
        frame.addToJavaScriptWindowObject("webVault", self)

    def __prepare_positions(self, positions, map_size):
        img_size = [256, 256]
        size = [int(map_size['0']), int(map_size['1'])]
        off_x = 0
        off_y = 0

        if size[1] > size[0]:
            img_size[0] = img_size[0]/2
            off_x = img_size[0]/2
        elif size[0] > size[1]:
            img_size[1] = img_size[1]/2
            off_y = img_size[1]/2

        cf_x = size[0]/img_size[0]
        cf_y = size[1]/img_size[1]

        regexp = re.compile(" \\d+\\.\\d*| \\d+")

        for postype in positions:
            for pos in positions[postype]:
                values = regexp.findall(positions[postype][pos])
                x = off_x + float(values[0].strip())/cf_x
                y = off_y + float(values[2].strip())/cf_y
                positions[postype][pos] = [int(x), int(y)]

    @QtCore.pyqtSlot()
    def upload_map(self):  # not used ?
        map_dir = QtGui.QFileDialog.getExistingDirectory(
            client.instance,
            "Select the map directory to upload",
            maps.get_user_maps_folder(),
            QtGui.QFileDialog.ShowDirsOnly)
        logger.debug("Uploading map from: " + map_dir)
        if map_dir != "":
            if maps.is_map_folder_valid(map_dir):
                os.chmod(map_dir, S_IWRITE)
                map_name = os.path.basename(map_dir)
                zip_name = map_name.lower()+".zip"

                scenariolua = luaparser.LuaParser(os.path.join(
                    map_dir,
                    maps.get_scenario_file(map_dir)))
                scenario_infos = scenariolua.parse({
                    'scenarioinfo>name': 'name', 'size': 'map_size',
                    'description': 'description',
                    'count:armies': 'max_players',
                    'map_version': 'version',
                    'type': 'map_type',
                    'teams>0>name': 'battle_type'
                    }, {'version': '1'})

                if scenariolua.error:
                    logger.debug("There were {} errors and {} warnings".format(
                        scenariolua.errors,
                        scenariolua.warnings
                        ))
                    logger.debug(scenariolua.errorMsg)
                    QtGui.QMessageBox.critical(
                        client.instance,
                        "Lua parsing error",
                        "{}\nMap uploading cancelled.".format(
                            scenariolua.errorMsg), QtGui.QMessageBox.Ok)
                else:
                    if scenariolua.warning:
                        uploadmap = QtGui.QMessageBox.question(
                            client.instance,
                            "Lua parsing warning",
                            "{}\nDo you want to upload the map?".format(
                                scenariolua.errorMsg),
                            QtGui.QMessageBox.Yes,
                            QtGui.QMessageBox.No)
                    else:
                        uploadmap = QtGui.QMessageBox.Yes
                    if uploadmap == QtGui.QMessageBox.Yes:
                        savelua = luaparser.LuaParser(os.path.join(
                            map_dir,
                            maps.get_save_file(map_dir)
                            ))
                        save_infos = savelua.parse({
                            'markers>mass*>position': 'mass:__parent__',
                            'markers>hydro*>position': 'hydro:__parent__',
                            'markers>army*>position': 'army:__parent__'})
                        if savelua.error or savelua.warning:
                            logger.debug("There were {} errors and {} warnings".format(
                                scenariolua.errors,
                                scenariolua.warnings
                                ))
                            logger.debug(scenariolua.errorMsg)

                        self.__prepare_positions(
                            save_infos,
                            scenario_infos["map_size"])

                        tmp_file = maps.process_map_folder_for_upload(
                            map_dir,
                            save_infos)
                        if not tmp_file:
                            QtGui.QMessageBox.critical(
                                client.instance,
                                "Map uploading error",
                                "Couldn't make previews for {}\n"
                                "Map uploading cancelled.".format(map_name), QtGui.QMessageBox.Ok)
                            return None

                        qfile = QtCore.QFile(tmp_file.name)
                        client.instance.lobby_connection.write_to_server("UPLOAD_MAP", zip_name, scenario_infos, qfile)

                        # removing temporary files
                        qfile.remove()
            else:
                QtGui.QMessageBox.information(
                    client.instance,
                    "Map selection",
                    "This folder doesn't contain valid map data.", QtGui.QMessageBox.Ok)

    @QtCore.pyqtSlot(str)
    def download_map(self, link):
        link = urllib2.unquote(link)
        name = maps.link2name(link)
        if not maps.is_map_available(name):
            maps.download_map(name)
            maps.exist_maps(True)
        else:
            show = QtGui.QMessageBox.question(
                client.instance,
                "Already got the Map",
                "Seems like you already have that map!<br/><b>Would you like to see it?</b>",
                QtGui.QMessageBox.Yes,
                QtGui.QMessageBox.No)
            if show == QtGui.QMessageBox.Yes:
                util.showDirInFileBrowser(maps.folder_for_map(name))
