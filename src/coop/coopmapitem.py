from PyQt4 import QtCore, QtGui
import util


class CoopMapItemDelegate(QtGui.QStyledItemDelegate):
    
    def __init__(self, *args, **kwargs):
        QtGui.QStyledItemDelegate.__init__(self, *args, **kwargs)
        
    def paint(self, painter, option, index, *args, **kwargs):
        self.initStyleOption(option, index)
                
        painter.save()
        
        html = QtGui.QTextDocument()
        text_option = QtGui.QTextOption()
        text_option.setWrapMode(QtGui.QTextOption.WordWrap)
        html.setDefaultTextOption(text_option)

        html.setTextWidth(option.rect.width())
        html.setHtml(option.text)

#        icon = QtGui.QIcon(option.icon)
#        iconsize = icon.actualSize(option.rect.size())
#        
#        # clear icon and text before letting the control draw itself because we're rendering these parts ourselves
#        option.icon = QtGui.QIcon()        
        option.text = ""  
        option.widget.style().drawControl(QtGui.QStyle.CE_ItemViewItem, option, painter, option.widget)
#        
#        # Icon
#        icon.paint(painter, option.rect.adjusted(5-2, -2, 0, 0), QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
#
#        # Description
        painter.translate(option.rect.left(), option.rect.top())
        clip = QtCore.QRectF(0, 0, option.rect.width(), option.rect.height())
        html.drawContents(painter, clip)
  
        painter.restore()

    def sizeHint(self, option, index, *args, **kwargs):
        self.initStyleOption(option, index)
        html = QtGui.QTextDocument()
        text_option = QtGui.QTextOption()
        text_option.setWrapMode(QtGui.QTextOption.WordWrap)
        html.setTextWidth(option.rect.width())
        html.setDefaultTextOption(text_option)
        html.setHtml(option.text)

        return QtCore.QSize(int(html.size().width()) + 10, int(html.size().height() + 10))        


class CoopMapItem(QtGui.QTreeWidgetItem):

    FORMATTER_COOP = util.readfile("coop/formatters/coop.qthtml")

    def __init__(self, uid, *args):
        QtGui.QTreeWidgetItem.__init__(self, *args)

        self.uid = uid
        self.viewtext = None
        self.name = None
        self.description = None
        self.mapUrl = None
        self.options = []
        self.mod = None
        self.setHidden(True)

    def update(self, message):
        """
        Updates this item from the message dictionary supplied
        """

        self.name = message["name"]
        self.mapUrl = message["filename"]
        self.description = message["description"]
        self.mod = message["featured_mod"]

#        self.icon = maps.preview(self.mapname)
#        if not self.icon:
#            client.instance.downloader.download_map(self.mapname, self, True)
#            self.icon = util.icon("games/unknown_map.png")        
#        self.setIcon(0, self.icon)
        self.viewtext = self.FORMATTER_COOP.format(name=self.name, description=self.description)

    def display(self, column):
        if column == 0:
            return self.viewtext
        if column == 1:
            return self.viewtext   
 
    def data(self, column, role):
        if role == QtCore.Qt.DisplayRole:
            return self.display(column)  
        elif role == QtCore.Qt.UserRole:
            return self
        return super(CoopMapItem, self).data(column, role)

    def __ge__(self, other):
        """ Comparison operator used for item list sorting """
        return not self.__lt__(other)

    def __lt__(self, other):
        """ Comparison operator used for item list sorting """
        # Default: uid
        return self.uid > other.uid
