
from PyQt4 import QtCore, QtGui
import util
import secondaryServer
import client
from tourneys.tourneyitem import TourneyItem, TourneyItemDelegate


FormClass, BaseClass = util.load_ui_type("tournaments/tournaments.ui")


class TournamentsWidget(FormClass, BaseClass):
    """ list and manage the main tournament lister """
    
    def __init__(self, *args, **kwargs):
        BaseClass.__init__(self, *args, **kwargs)        
        
        self.setupUi(self)

        client.instance.tourneyTab.layout().addWidget(self)
        
        # tournament server
        #self.tourneyServer = secondaryServer.SecondaryServer("Tournament", 11001, self)
        #self.tourneyServer.set_invisible()

        # Dictionary containing our actual tournaments.
        self.tourneys = {}

        self.tourneyList.setItemDelegate(TourneyItemDelegate(self))

        self.tourneyList.itemDoubleClicked.connect(self.tourney_doubleclicked)

        self.tourneysTab = {}

        # Special stylesheet
        util.set_stylesheet(self, "tournaments/formatters/style.css")

        #self.updateTimer = QtCore.QTimer(self)
        #self.updateTimer.timeout.connect(self.update_tournaments)
        #self.updateTimer.start(600000)

    def showEvent(self, event):  # Qt QShowEvent ?
        #self.update_tournaments()
        return BaseClass.showEvent(self, event)

    def update_tournaments(self):
        self.tourneyServer.send(dict(command="get_tournaments"))

    @QtCore.pyqtSlot(QtGui.QListWidgetItem)
    def tourney_doubleclicked(self, item):
        """
        Slot that attempts to join or leave a tournament.
        """
        if client.instance.login not in item.playersname:
            reply = QtGui.QMessageBox.question(client.instance, "Register",
                                               "Do you want to register to this tournament ?",
                                               QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
            if reply == QtGui.QMessageBox.Yes:
                self.tourneyServer.send(dict(command="add_participant", uid=item.uid, login=client.instance.login))

        else:
            reply = QtGui.QMessageBox.question(client.instance, "Register",
                                               "Do you want to leave this tournament ?",
                                               QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
            if reply == QtGui.QMessageBox.Yes:   
                self.tourneyServer.send(dict(command="remove_participant", uid=item.uid, login=client.instance.login))

    def handle_tournaments_info(self, message):
        # self.tourneyList.clear()
        tournaments = message["data"]
        for uid in tournaments:
            if uid not in self.tourneys:
                self.tourneys[uid] = TourneyItem(self, uid)
                self.tourneyList.addItem(self.tourneys[uid])
                self.tourneys[uid].update(tournaments[uid])
            else:
                self.tourneys[uid].update(tournaments[uid])
