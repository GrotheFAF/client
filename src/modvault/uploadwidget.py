
import tempfile
import zipfile
import os

from PyQt4 import QtCore, QtGui
import client
import modvault
import util

FormClass, BaseClass = util.load_ui_type("modvault/upload.ui")


class UploadModWidget(FormClass, BaseClass):
    def __init__(self, parent, mod_dir, modinfo, *args, **kwargs):
        BaseClass.__init__(self, *args, **kwargs)

        self.setupUi(self)
        self.parent = parent
        self.modinfo = modinfo
        self.mod_dir = mod_dir

        self.setStyleSheet(client.instance.styleSheet())

        self.setWindowTitle("Uploading Mod")

        self.Name.setText(modinfo.name)
        self.Version.setText(str(modinfo.version))
        if modinfo.ui_only:
            self.isUILabel.setText("is UI Only")
        else:
            self.isUILabel.setText("not UI Only")
        self.UID.setText(modinfo.uid)
        self.Description.setPlainText(modinfo.description)
        if modinfo.icon != "":
            self.IconURI.setText(modvault.icon_path_to_full(modinfo.icon))
            self.update_thumbnail()
        else:
            self.Thumbnail.setPixmap(util.pix_map("games/unknown_map.png"))
        self.UploadButton.pressed.connect(self.upload)

    @QtCore.pyqtSlot()
    def upload(self):
        n = self.Name.text()
        if any([(i in n) for i in '"<*>|?/\\:']):
            QtGui.QMessageBox.information(client.instance, "Invalid Name",
                                          "The mod name contains invalid characters: /\\<>|?:\"", 0x0400)
            return

        iconpath = modvault.icon_path_to_full(self.modinfo.icon)
        # the icon is in the game folder
        if iconpath != "" and os.path.commonprefix([os.path.normcase(self.mod_dir),
                                                    os.path.normcase(iconpath)]) == os.path.normcase(self.mod_dir):
            infolder = True
        else:
            infolder = False

        if iconpath != "" and not infolder:
            QtGui.QMessageBox.information(client.instance, "Invalid Icon File", "The file %s is not located inside the "
                                                                                "modfolder. Copy the icon file to your "
                                                                                "modfolder and change the mod_info.lua "
                                                                                "accordingly" % iconpath, 0x0400)
            return

        try:
            temp = tempfile.NamedTemporaryFile(mode='w+b', suffix=".zip", delete=False)
            zipped = zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED)
            zipdir(self.mod_dir, zipped, os.path.basename(self.mod_dir))
            zipped.close()
            temp.flush()
        except:
            QtGui.QMessageBox.critical(client.instance, "Mod uploading error",
                                       "Something went wrong zipping the mod files.", 0x0400)
            return

        qfile = QtCore.QFile(temp.name)

        # The server should check again if there is already a mod with this name or UID.
        client.instance.lobby_connection.write_to_server("UPLOAD_MOD", "%s.v%04d.zip" % (self.modinfo.name,
                                                                                         self.modinfo.version),
                                                         self.modinfo.to_dict(), qfile)

    @QtCore.pyqtSlot()
    def update_thumbnail(self):
        iconfilename = modvault.icon_path_to_full(self.modinfo.icon)
        if iconfilename == "":
            return False
        if os.path.splitext(iconfilename)[1].lower() == ".dds":
            old = iconfilename
            iconfilename = os.path.join(self.mod_dir, os.path.splitext(os.path.basename(iconfilename))[0] + ".png")
            succes = modvault.generate_thumbnail(old, iconfilename)
            if not succes:
                QtGui.QMessageBox.information(client.instance, "Invalid Icon File",
                                              "Because FAF can't read DDS files, it tried to convert it to a png. This"
                                              " failed. Try something else", 0x0400)
                return False
        try:
            self.Thumbnail.setPixmap(util.pix_map(iconfilename, False))
        except:
            QtGui.QMessageBox.information(client.instance, "Invalid Icon File",
                                          "This was not a valid icon file. Please pick a png or jpeg", 0x0400)
            return False
        self.modinfo.thumbnail = modvault.full_path_to_icon(iconfilename)
        self.IconURI.setText(iconfilename)
        return True
    

# from http://stackoverflow.com/questions/1855095/how-to-create-a-zip-archive-of-a-directory-in-python
def zipdir(path, zipf, fname):
    """ zips the entire directory path to zipf. Every file in the zipfile starts with fname.
        So if path is "/foo/bar/hello" and fname is "test" then every file in zipf is of the form "/test/*.*" """
    path = os.path.normcase(path)
    if path[-1] in r'\/':
        path = path[:-1]
    for root, dirs, files in os.walk(path):
        for f in files:
            name = os.path.join(os.path.normcase(root), f)
            n = name[len(os.path.commonprefix([name, path])):]
            if n[0] == "\\":
                n = n[1:]
            zipf.write(name, os.path.join(fname, n))
