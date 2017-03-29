
from PyQt4 import QtCore, QtGui
from PyQt4.QtNetwork import QNetworkAccessManager, QNetworkRequest

import base64
import zlib
import os
import util
import client


class PlayerAvatar(QtGui.QDialog):
    def __init__(self, users=[], idavatar=0, *args, **kwargs):
        QtGui.QDialog.__init__(self, *args, **kwargs)

        self.users = users
        self.checkBox = {}
        self.idavatar = idavatar

        self.setStyleSheet(client.instance.styleSheet())

        self.grid = QtGui.QGridLayout(self)
        self.userlist = None

        self.removeButton = QtGui.QPushButton("&Remove users")
        self.grid.addWidget(self.removeButton, 1, 0)

        self.removeButton.clicked.connect(self.remove_them)

        self.setWindowTitle("Users using this avatar")
        self.resize(480, 320)         

    def process_list(self, users, idavatar):
        self.checkBox = {}
        self.users = users
        self.idavatar = idavatar
        self.userlist = self.create_user_selection()
        self.grid.addWidget(self.userlist, 0, 0)

    def remove_them(self):
        for user in self.checkBox:
            if self.checkBox[user].checkState() == 2:
                client.instance.lobby_connection.send(dict(command="admin", action="remove_avatar",
                                                           iduser=user, idavatar=self.idavatar))
        self.close()

    def create_user_selection(self):
        group_box = QtGui.QGroupBox("Select the users you want to remove this avatar :")
        vbox = QtGui.QVBoxLayout()

        for user in self.users:
            self.checkBox[user["iduser"]] = QtGui.QCheckBox(user["login"])
            vbox.addWidget(self.checkBox[user["iduser"]])

        vbox.addStretch(1)
        group_box.setLayout(vbox)

        return group_box


class AvatarWidget(QtGui.QDialog):
    def __init__(self, user, personal=False, *args, **kwargs):

        QtGui.QDialog.__init__(self, *args, **kwargs)

        self.user = user
        self.personal = personal

        self.setStyleSheet(client.instance.styleSheet())
        self.setWindowTitle("Avatar manager")

        self.group_layout = QtGui.QVBoxLayout(self)
        self.listAvatars = QtGui.QListWidget()

        self.listAvatars.setWrapping(1)
        self.listAvatars.setSpacing(5)
        self.listAvatars.setResizeMode(1)

        self.group_layout.addWidget(self.listAvatars)

        if not self.personal:
            self.addAvatarButton = QtGui.QPushButton("Add/Edit avatar")
            self.addAvatarButton.clicked.connect(self.add_avatar)
            self.group_layout.addWidget(self.addAvatarButton)

        self.item = []
        client.instance.lobby_info.avatarList.connect(self.do_avatar_list)
        client.instance.lobby_info.playerAvatarList.connect(self.do_player_avatar_list)

        self.playerList = PlayerAvatar()

        self.nams = {}
        self.avatars = {}

        self.finished.connect(self.cleaning)

    def showEvent(self, event):
        client.instance.request_avatars(self.personal)

    def add_avatar(self):

        options = QtGui.QFileDialog.Options()       
        options |= QtGui.QFileDialog.DontUseNativeDialog

        filename = QtGui.QFileDialog.getOpenFileName(self, "Select the PNG file", "", "png Files (*.png)", options)
        if filename:
            # check the properties of that file
            pixmap = QtGui.QPixmap(filename)
            if pixmap.height() == 20 and pixmap.width() == 40:

                text, ok = QtGui.QInputDialog.getText(self, "Avatar description",
                                                            "Please enter the tooltip :", QtGui.QLineEdit.Normal, "")

                if ok and text != '':

                    png_file = QtCore.QFile(filename)
                    png_file.open(QtCore.QIODevice.ReadOnly)
                    file_data = base64.b64encode(zlib.compress(png_file.readAll()))
                    png_file.close()

                    client.instance.lobby_connection.send(dict(command="avatar", action="upload_avatar",
                                                               name=os.path.basename(filename),
                                                               description=text, file=file_data))

            else:
                QtGui.QMessageBox.warning(self, "Bad image", "The image must be in png, format is 40x20 !", 0x0400)

    def finish_request(self, reply):

        if reply.url().toString() in self.avatars:
            img = QtGui.QImage()
            img.loadFromData(reply.readAll())
            pix = QtGui.QPixmap(img)
            self.avatars[reply.url().toString()].setIcon(QtGui.QIcon(pix))   
            self.avatars[reply.url().toString()].setIconSize(pix.rect().size())     

            util.addrespix(reply.url().toString(), QtGui.QPixmap(img))

    def clicked(self):
        self.doit(None)
        self.close()

    def create_connect(self, x):
        return lambda: self.doit(x)

    def doit(self, val):
        if self.personal:
            client.instance.lobby_connection.send(dict(command="avatar", action="select", avatar=val))
            self.close()

        else:
            if self.user is None:
                client.instance.lobby_connection.send(dict(command="admin", action="list_avatar_users", avatar=val))
            else:
                client.instance.lobby_connection.send(dict(command="admin", action="add_avatar", user=self.user, avatar=val))
                self.close()

    def do_player_avatar_list(self, message):
        self.playerList = PlayerAvatar()
        player_avatar_list = message["player_avatar_list"]
        id_avatar = message["avatar_id"]
        self.playerList.process_list(player_avatar_list, id_avatar)
        self.playerList.show()

    def do_avatar_list(self, avatars):
        self.listAvatars.clear()
        button = QtGui.QPushButton()
        self.avatars["None"] = button

        item = QtGui.QListWidgetItem()
        item.setSizeHint(QtCore.QSize(40, 20))

        self.item.append(item)

        self.listAvatars.addItem(item)
        self.listAvatars.setItemWidget(item, button)

        button.clicked.connect(self.clicked)

        for avatar in avatars:

            avatar_pix = util.respix(avatar["url"])
            button = QtGui.QPushButton()

            button.clicked.connect(self.create_connect(avatar["url"]))

            item = QtGui.QListWidgetItem()
            item.setSizeHint(QtCore.QSize(40, 20))
            self.item.append(item)

            self.listAvatars.addItem(item)

            button.setToolTip(avatar["tooltip"])
            url = QtCore.QUrl(avatar["url"])            
            self.avatars[avatar["url"]] = button

            self.listAvatars.setItemWidget(item, self.avatars[avatar["url"]])

            if not avatar_pix:
                self.nams[url] = QNetworkAccessManager(button)
                self.nams[url].finished.connect(self.finish_request)
                self.nams[url].get(QNetworkRequest(url))
            else:
                self.avatars[avatar["url"]].setIcon(QtGui.QIcon(avatar_pix))
                self.avatars[avatar["url"]].setIconSize(avatar_pix.rect().size())

    def cleaning(self):
        if self != client.instance.avatarAdmin:
            client.instance.lobby_info.avatarList.disconnect(self.do_avatar_list)
            client.instance.lobby_info.playerAvatarList.disconnect(self.do_player_avatar_list)
