from PyQt4 import QtCore, QtGui, QtWebKit

import webbrowser
import util
import client
from .newsitem import NewsItem, NewsItemDelegate
from .newsmanager import NewsManager

import base64

import logging

logger = logging.getLogger(__name__)


class Hider(QtCore.QObject):
    """
    Hides a widget by blocking its paint event. This is useful if a
    widget is in a layout that you do not want to change when the
    widget is hidden.
    """
    def __init__(self, parent=None):
        super(Hider, self).__init__(parent)

    def eventFilter(self, obj, ev):
        return ev.type() == QtCore.QEvent.Paint

    def hide(self, widget):
        widget.installEventFilter(self)
        widget.update()

    def unhide(self, widget):
        widget.removeEventFilter(self)
        widget.update()

    def hideWidget(self, sender):
        if sender.isWidgetType():
            self.hide(sender)

FormClass, BaseClass = util.load_ui_type("news/news.ui")


class NewsWidget(FormClass, BaseClass):
    CSS = util.read_stylesheet('news/news_webview.css')

    HTML = unicode(util.readfile('news/news_webview_frame.html'))

    def __init__(self, *args, **kwargs):
        BaseClass.__init__(self, *args, **kwargs)

        self.setupUi(self)

        client.instance.whatNewTab.layout().addWidget(self)

        self.newsManager = NewsManager(self)

        self.newsWebView.settings().setUserStyleSheetUrl(QtCore.QUrl(
                'data:text/css;charset=utf-8;base64,' + base64.b64encode(self.CSS)
            ))
        # open all links in external browser
        self.newsWebView.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
        self.newsWebView.page().linkClicked.connect(self.link_clicked)

        # hide webview until loaded to avoid FOUC
        self.hider = Hider()
        self.hider.hide(self.newsWebView)
        self.newsWebView.loadFinished.connect(self.load_finished)

        self.newsList.setIconSize(QtCore.QSize(0, 0))
        self.newsList.setItemDelegate(NewsItemDelegate(self))
        self.newsList.currentItemChanged.connect(self.item_changed)

    def add_news(self, news_post):
        news_item = NewsItem(news_post, self.newsList)

    def item_changed(self, current, previous):
        self.newsWebView.setHtml(self.HTML.format(title=current.newsPost['title'], content=current.newsPost['body'],))

    @staticmethod
    def link_clicked(url):
        webbrowser.open(url.toString())

    def load_finished(self, ok):
        self.hider.unhide(self.newsWebView)
        self.newsWebView.loadFinished.disconnect(self.load_finished)
