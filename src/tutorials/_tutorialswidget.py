from PyQt4 import QtCore, QtGui
from PyQt4.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
import client
import util
import os
import fa
from tutorials.tutorialitem import TutorialItem, TutorialItemDelegate

import logging
logger = logging.getLogger(__name__)

FormClass, BaseClass = util.load_ui_type("tutorials/tutorials.ui")


class TutorialsWidget(FormClass, BaseClass):
    def __init__(self, *args, **kwargs):
        BaseClass.__init__(self, *args, **kwargs)        
        
        self.setupUi(self)

        client.instance.tutorialsTab.layout().addWidget(self)
        
        self.sections = {}
        self.tutorials = {}

        client.instance.lobby_info.tutorialsInfo.connect(self.process_tutorial_info)

        logger.info("Tutorials instantiated.")

    def finish_replay(self, reply):
        if reply.error() != QNetworkReply.NoError:
            QtGui.QMessageBox.warning(self, "Network Error", reply.errorString(), QtGui.QMessageBox.Ok)
        else:
            filename = os.path.join(util.CACHE_DIR, str("tutorial.fafreplay"))
            replay = QtCore.QFile(filename)
            replay.open(QtCore.QIODevice.WriteOnly | QtCore.QIODevice.Text)
            replay.write(reply.readAll())
            replay.close()

            fa.replay(filename, True)

    def tutorial_clicked(self, item):

        self.nam = QNetworkAccessManager()
        self.nam.finished.connect(self.finish_replay)
        self.nam.get(QNetworkRequest(QtCore.QUrl(item.url)))            

    def process_tutorial_info(self, message):
        """
        Two type here : section or tutorials.
        Sections are defining the different types of tutorials
        """
        
        logger.debug("Processing TutorialInfo")
        
        if "section" in message:
            section = message["section"]
            desc = message["description"]

            area = util.load_ui("tutorials/tutorialarea.ui")
            tab_index = self.addTab(area, section)
            self.setTabToolTip(tab_index, desc)

            # Set up the List that contains the tutorial items
            area.listWidget.setItemDelegate(TutorialItemDelegate(self))
            area.listWidget.itemDoubleClicked.connect(self.tutorial_clicked)

            self.sections[section] = area.listWidget

        elif "tutorial" in message:
            tutorial = message["tutorial"]
            section = message["tutorial_section"]

            if section in self.sections:
                self.tutorials[tutorial] = TutorialItem(tutorial)
                self.tutorials[tutorial].update(message)

                self.sections[section].addItem(self.tutorials[tutorial]) 
