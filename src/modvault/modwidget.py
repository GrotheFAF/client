
from PyQt4 import QtCore, QtGui

from util import strtodate, datetostr, now
import util
import client

FormClass, BaseClass = util.load_ui_type("modvault/mod.ui")


class ModWidget(FormClass, BaseClass):
    def __init__(self, parent, mod, *args, **kwargs):
        BaseClass.__init__(self, *args, **kwargs)

        self.setupUi(self)
        self.parent = parent

        self.setStyleSheet(client.instance.styleSheet())
        
        self.setWindowTitle(mod.name)

        self.mod = mod

        self.Title.setText(mod.name)
        self.Description.setText(mod.description)

        if mod.is_ui_mod:
            modtext = "UI mod\n"
        else:
            modtext = ""

        self.Info.setText(modtext + "By %s\nUploaded %s" % (mod.author, str(mod.date)))
        if mod.thumbnail is None:
            self.Picture.setPixmap(util.pix_map("games/unknown_map.png"))
        else:
            self.Picture.setPixmap(mod.thumbnail.pixmap(100, 100))

        # self.Comments.setItemDelegate(CommentItemDelegate(self))
        # self.BugReports.setItemDelegate(CommentItemDelegate(self))

        self.tabWidget.setEnabled(False)

        if self.mod.uid in self.parent.uids:
            self.DownloadButton.setText("Remove Mod")
        self.DownloadButton.clicked.connect(self.download)

        # self.likeButton.clicked.connect(self.like)
        # self.LineComment.returnPressed.connect(self.add_comment)
        # self.LineBugReport.returnPressed.connect(self.add_bug_report)

        # for item in mod.comments:
        #    comment = CommentItem(self,item["uid"])
        #    comment.update(item)
        #    self.Comments.addItem(comment)
        # for item in mod.bugreports:
        #    comment = CommentItem(self,item["uid"])
        #    comment.update(item)
        #    self.BugReports.addItem(comment)

        self.likeButton.setEnabled(False)
        self.LineComment.setEnabled(False)
        self.LineBugReport.setEnabled(False)

    @QtCore.pyqtSlot()
    def download(self):
        if self.mod.uid not in self.parent.uids:
            self.parent.download_mod(self.mod)
            self.done(1)
        else:
            show = QtGui.QMessageBox.question(client.instance, "Delete Mod", "Are you sure you want to delete this mod?"
                                              , QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
            if show == QtGui.QMessageBox.Yes:
                self.parent.remove_mod(self.mod)
                self.done(1)

    @QtCore.pyqtSlot()
    def add_comment(self):
        if self.LineComment.text() == "":
            return
        comment = {"author": client.instance.login, "text": self.LineComment.text(),
                   "date": datetostr(now()), "uid": "%s-%s" % (self.mod.uid, str(len(self.mod.bugreports)
                                                                                 + len(self.mod.comments)).zfill(3))}

        client.instance.lobby_connection.send(dict(command="modvault", type="addcomment", moduid=self.mod.uid, comment=comment))
        c = CommentItem(self, comment["uid"])
        c.update(comment)
        self.Comments.addItem(c)
        self.mod.comments.append(comment)
        self.LineComment.setText("")

    @QtCore.pyqtSlot()
    def add_bug_report(self):
        if self.LineBugReport.text() == "":
            return
        bugreport = {"author": client.instance.login, "text": self.LineBugReport.text(),
                     "date": datetostr(now()), "uid": "%s-%s" % (self.mod.uid, str(len(self.mod.bugreports) +
                                                                                   len(self.mod.comments)).zfill(3))}

        client.instance.lobby_connection.send(dict(command="modvault", type="addbugreport", moduid=self.mod.uid, bugreport=bugreport))
        c = CommentItem(self, bugreport["uid"])
        c.update(bugreport)
        self.BugReports.addItem(c)
        self.mod.bugreports.append(bugreport)
        self.LineBugReport.setText("")

    @QtCore.pyqtSlot()
    def like(self):  # the server should determine if the user hasn't already clicked the like button for this mod.
        client.instance.lobby_connection.send(dict(command="modvault", type="like", uid=self.mod.uid))
        self.likeButton.setEnabled(False)


class CommentItemDelegate(QtGui.QStyledItemDelegate):
    TEXTWIDTH = 350
    TEXTHEIGHT = 60

    def __init__(self, *args, **kwargs):
        QtGui.QStyledItemDelegate.__init__(self, *args, **kwargs)

    def paint(self, painter, option, index, *args, **kwargs):
        self.initStyleOption(option, index)

        painter.save()
        
        html = QtGui.QTextDocument()
        html.setHtml(option.text)

        option.text = ""  
        option.widget.style().drawControl(QtGui.QStyle.CE_ItemViewItem, option, painter, option.widget)

        # Description
        painter.translate(option.rect.left() + 10, option.rect.top()+10)
        clip = QtCore.QRectF(0, 0, option.rect.width(), option.rect.height())
        html.drawContents(painter, clip)

        painter.restore()

    def sizeHint(self, option, index, *args, **kwargs):
        self.initStyleOption(option, index)

        html = QtGui.QTextDocument()
        html.setHtml(option.text)
        html.setTextWidth(self.TEXTWIDTH)
        return QtCore.QSize(self.TEXTWIDTH, self.TEXTHEIGHT)


class CommentItem(QtGui.QListWidgetItem):
    FORMATTER_COMMENT = unicode(util.readfile("modvault/comment.qthtml"))

    def __init__(self, uid, *args):
        QtGui.QListWidgetItem.__init__(self, *args)

        self.uid = uid
        self.text = ""
        self.author = ""
        self.date = None

    def update(self, dic):
        self.text = dic["text"]
        self.author = dic["author"]
        self.date = strtodate(dic["date"])
        self.setText(self.FORMATTER_COMMENT.format(text=self.text, author=self.author, date=str(self.date)))

    def __ge__(self, other):
        return self.date > other.date

    def __lt__(self, other):
        return self.date <= other.date
