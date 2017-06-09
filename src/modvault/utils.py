import os
import sys
import urllib2
import re
import shutil

from PyQt4 import QtCore, QtGui

from util import PREFSFILENAME
import util
import logging
from vault import luaparser

import cStringIO
import zipfile
from config import Settings

logger = logging.getLogger(__name__)

MODFOLDER = os.path.join(util.PERSONAL_DIR, "My Games", "Gas Powered Games", "Supreme Commander Forged Alliance", "Mods")
MODVAULT_DOWNLOAD_ROOT = "{}/faf/vault/".format(Settings.get('content/host'))

# This is a global list that should be kept intact. So it should be cleared using installed_mods[:] = []
installed_mods = []

# mods selected by user, are not overwritten by temporary mods selected when joining game
selected_mods = Settings.get('play/mods', default=[])


class ModInfo(object):
    def __init__(self, **kwargs):
        self.name = "Not filled in"
        self.version = 0
        self.folder = ""
        self.__dict__.update(kwargs)

    def set_folder(self, localfolder):
        self.localfolder = localfolder
        self.absfolder = os.path.join(MODFOLDER, localfolder)
        self.mod_info = os.path.join(self.absfolder, "mod_info.lua")

    def update(self):
        self.set_folder(self.localfolder)
        if isinstance(self.version, int):
            self.totalname = "%s v%d" % (self.name, self.version)
        elif isinstance(self.version, float):
            s = str(self.version).rstrip("0")
            self.totalname = "%s v%s" % (self.name, s)
        else:
            raise TypeError("version is not an int or float")

    def to_dict(self):
        out = {}
        for k, v in list(self.__dict__.items()):
            if isinstance(v, (str, int, float)) and not k[0] == '_':
                out[k] = v
        return out

    def __str__(self):
        return '%s in "%s"' % (self.totalname, self.localfolder)


def get_all_mod_folders():  # returns a list of names of installed mods
        mods = []
        if os.path.isdir(MODFOLDER):
            mods = os.listdir(MODFOLDER)
        return mods


def get_installed_mods():
    installed_mods[:] = []
    for f in get_all_mod_folders():
        mod_info = None
        if os.path.isdir(os.path.join(MODFOLDER, f)):
            try:
                mod_info = get_mod_info_from_folder(f)
            except:
                continue
        else:
            try:
                mod_info = get_mod_info_from_zip(f)
            except:
                continue
        if mod_info:
            installed_mods.append(mod_info)
    logger.debug("getting installed mods. Count: %d" % len(installed_mods))
    return installed_mods


def mod_to_filename(mod):
    return mod.absfolder


def is_mod_folder_valid(folder):
    return os.path.exists(os.path.join(folder, "mod_info.lua"))


def icon_path_to_full(path):
    """
    Converts a path supplied in the icon field of mod_info with an absolute path to that file.
    So "/mods/modname/data/icons/icon.dds" becomes
    "C:\Users\user\Documents\My Games\Gas Powered Games\Supreme Commander Forged Alliance\Mods\modname\data\icons\icon.dds"
    """
    if not (path.startswith("/mods") or path.startswith("mods")):
        logger.info("Something went wrong parsing the path %s" % path)
        return ""
    return os.path.join(MODFOLDER, os.path.normpath(path[5+int(path[0] == "/"):]))  # yay for dirty hacks


def full_path_to_icon(path):
    p = os.path.normpath(os.path.abspath(path))
    return p[len(MODFOLDER)-5:].replace('\\', '/')


def get_icon(name):
    img = os.path.join(util.CACHE_DIR, name)
    if os.path.isfile(img):
        logger.log(5, "Using cached preview image for: " + name)
        return img
    return None


def get_mod_info(modinfofile):
    modinfo = modinfofile.parse({"name": "name", "uid": "uid", "version": "version", "author": "author",
                                 "description": "description", "ui_only": "ui_only", "icon": "icon"},
                                {"version": "1", "ui_only": "false", "description": "", "icon": "", "author": ""})
    modinfo["ui_only"] = (modinfo["ui_only"] == 'true')
    if "uid" not in modinfo:
        logger.warn("Couldn't find uid for mod %s" % modinfo["name"])
        return None
    # modinfo["uid"] = modinfo["uid"].lower()
    try:
        modinfo["version"] = int(modinfo["version"])
    except:
        try:
            modinfo["version"] = float(modinfo["version"])
        except:
            modinfo["version"] = 0
            logger.warn("Couldn't find version for mod %s" % modinfo["name"])
    return modinfofile, modinfo


def parse_mod_info(folder):
    if not is_mod_folder_valid(folder):
        return None
    modinfofile = luaparser.LuaParser(os.path.join(folder, "mod_info.lua"))
    return get_mod_info(modinfofile)

modCache = {}


def get_mod_info_from_zip(zfile):
    """get the mod info from a zip file"""
    if zfile in modCache:
        return modCache[zfile]
    
    r = None
    if zipfile.is_zipfile(os.path.join(MODFOLDER, zfile)):
        zip = zipfile.ZipFile(os.path.join(MODFOLDER, zfile), "r", zipfile.ZIP_DEFLATED)
        if zip.testzip() is None:
            for member in zip.namelist():
                filename = os.path.basename(member)
                if not filename:
                    continue
                if filename == "mod_info.lua":
                    modinfofile = luaparser.LuaParser("mod_info.lua")
                    modinfofile.is_zip = True
                    modinfofile.zip = zip
                    r = get_mod_info(modinfofile)
    if r is None:
        logger.debug("mod_info.lua not found in zip file %s" % zfile)
        return None
    f, info = r
    if f.error:
        logger.debug("Error in parsing mod_info.lua in %s" % zfile)
        return None
    m = ModInfo(**info)
    m.set_folder(zfile)
    m.update()
    modCache[zfile] = m
    return m


def get_mod_info_from_folder(modfolder):  # modfolder must be local to MODFOLDER
    if modfolder in modCache:
        return modCache[modfolder]

    r = parse_mod_info(os.path.join(MODFOLDER, modfolder))
    if r is None:
        logger.debug("mod_info.lua not found in %s folder" % modfolder)
        return None
    f, info = r
    if f.error:
        logger.debug("Error in parsing %s/mod_info.lua" % modfolder)
        return None
    m = ModInfo(**info)
    m.set_folder(modfolder)
    m.update()
    modCache[modfolder] = m
    return m


def get_active_mods(uimods=None, temporary=True):  # returns a list of ModInfo's containing information of the mods
    """uimods:
        None - return all active mods
        True - only return active UI Mods
        False - only return active non-UI Mods
       temporary:
        read from game.prefs and not from settings
    """
    active_mods = []
    try:
        if not os.path.exists(PREFSFILENAME):
            logger.info("No game.prefs file found")
            return []
        if temporary:
            l = luaparser.LuaParser(PREFSFILENAME)
            l.loweringKeys = False
            modlist = l.parse({"active_mods": "active_mods"}, {"active_mods": {}})["active_mods"]
            if l.error:
                logger.info("Error in reading the game.prefs file")
                return []
            uids = [uid for uid, b in list(modlist.items()) if b == 'true']
            # logger.debug("Active mods detected: %s" % str(uids))
        else:
            uids = selected_mods[:]

        allmods = []
        for m in installed_mods:
            if (uimods and m.ui_only) or (not uimods and not m.ui_only) or uimods is None:
                allmods.append(m)
        active_mods = [m for m in allmods if m.uid in uids]
        # logger.debug("Allmods uids: %s\n\nActive mods uids: %s\n" % (", ".join([mod.uid for mod in allmods]), ", ".join([mod.uid for mod in allmods])))
        return active_mods
    except:
        return []


def set_active_mods(mods, keepuimods=True, temporary=True):  # uimods works the same as in get_active_mods
    """
    keepuimods:
        None: Replace all active mods with 'mods'
        True: Keep the UI mods already activated activated
        False: Keep only the non-UI mods that were activated activated
        So set it True if you want to set gameplay mods, and False if you want to set UI mods.
    temporary:
        Set this when mods are activated due to joining a game.
    """
    if keepuimods is not None:
        keep_these_mods = get_active_mods(keepuimods)  # returns the active UI mods if True, the active non-ui mods if False
    else:
        keep_these_mods = []
    allmods = keep_these_mods + mods
    logger.debug('setting active Mods: {}'.format([mod.uid for mod in allmods]))
    s = "active_mods = {\n"
    for mod in allmods:
        s += "['%s'] = true,\n" % str(mod.uid)
    s += "}"

    if not temporary:
        logger.debug('selected_mods was: {}'.format(Settings.get('play/mods')))
        selected_mods = list([str(mod.uid) for mods in allmods])
        logger.debug('Writing selected_mods: {}'.format(selected_mods))
        Settings.set('play/mods', selected_mods)
        logger.debug('selected_mods written: {}'.format(Settings.get('play/mods')))

    try:
        f = open(PREFSFILENAME, 'r')
        data = f.read()
    except:
        logger.info("Couldn't read the game.prefs file")
        return False
    else:
        f.close()

    if re.search("active_mods\s*=\s*{.*?}", data, re.S):
        data = re.sub("active_mods\s*=\s*{.*?}", s, data, 1, re.S)
    else:
        data += "\n" + s

    try:
        f = open(PREFSFILENAME, 'w')
        f.write(data)
    except:
        logger.info("Couldn't write to the game.prefs file")
        return False
    else:
        f.close()

    return True


def update_mod_info(mod, info):  # should probably not be used.
    """
    Updates a mod_info.lua file with new data.
    Because those files can be random lua this function can fail if the file is complicated enough
    If every value however is on a seperate line, this should work.
    """
    logger.warn("update_mod_info called. Probably not a good idea")
    fname = mod.mod_info
    try:
        f = open(fname, 'r')
        data = f.read()
    except:
        logger.info("Something went wrong reading %s" % fname)
        return False
    else:
        f.close()

    for k, v in list(info.items()):
        if type(v) in (bool, int):
            val = str(v).lower()
        if type(v) in (unicode, str):
            val = '"' + v.replace('"', '\\"') + '"'
        if re.search(r'^\s*'+k, data, re.M):
            data = re.sub(r'^\s*' + k + r'\s*=.*$', "%s = %s" % (k, val), data, 1, re.M)
        else:
            if data[-1] != '\n':
                data += '\n'
            data += "%s = %s" % (k, val)
    try:
        f = open(fname, 'w')
        f.write(data)
    except:
        logger.info("Something went wrong writing to %s" % fname)
        return False
    else:
        f.close()
        
    return True


def generate_thumbnail(sourcename, destname):
    """Given a dds file, generates a png file (or whatever the extension of dest is"""
    logger.debug("Creating png thumnail for %s to %s" % (sourcename, destname))

    try:
        img = bytearray()
        buf = bytearray(16)
        file = open(sourcename, "rb")
        file.seek(128)  # skip header
        while file.readinto(buf):
            img += buf[:3] + buf[4:7] + buf[8:11] + buf[12:15]
        file.close()

        size = int((len(img)/3) ** (1.0/2))
        image_file = QtGui.QImage(img, size, size, QtGui.QImage.Format_RGB888).rgbSwapped().\
            scaled(100, 100, transformMode=QtCore.Qt.SmoothTransformation)
        image_file.save(destname)
    except IOError:
        return False

    if os.path.isfile(destname):
        return True
    else:
        return False


def download_mod(item):  # most of this function is stolen from fa.maps.download_map
    if isinstance(item, str):
        link = MODVAULT_DOWNLOAD_ROOT + urllib2.quote(item)
        logger.debug("Getting mod from: " + link)
    else:
        link = item.link
        logger.debug("Getting mod from: " + link)
        link = urllib2.quote(link, "http://")

    progress = QtGui.QProgressDialog()
    progress.setCancelButtonText("Cancel")
    progress.setWindowFlags(QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowTitleHint)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    
    try:
        req = urllib2.Request(link, headers={'User-Agent': "FAF Client"})
        zipwebfile = urllib2.urlopen(req)

        meta = zipwebfile.info()
        file_size = int(meta.getheaders("Content-Length")[0])
        progress.setMinimum(0)
        progress.setMaximum(file_size)
        progress.setModal(1)
        progress.setWindowTitle("Downloading Mod")
        progress.setLabelText(link)
    
        progress.show()

        # Download the file as a series of 8 KiB chunks, then uncompress it.
        output = cStringIO.StringIO()
        file_size_dl = 0
        block_sz = 8192       

        while progress.isVisible():
            read_buffer = zipwebfile.read(block_sz)
            if not read_buffer:
                break
            file_size_dl += len(read_buffer)
            output.write(read_buffer)
            progress.setValue(file_size_dl)
    
        progress.close()
        
        if file_size_dl == file_size:
            zfile = zipfile.ZipFile(output)
            dirname = zfile.namelist()[0].split('/', 1)[0]
            if os.path.exists(os.path.join(MODFOLDER, dirname)):
                oldmod = get_mod_info_from_folder(dirname)
                result = QtGui.QMessageBox.question(None, "Modfolder already exists",
                                                    "The mod is to be downloaded to the folder '%s'. This folder "
                                                    "already exists and contains <b>%s</b>. Do you want to overwrite "
                                                    "this mod?" % (dirname, oldmod.totalname),
                                                    QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
                if result == QtGui.QMessageBox.No:
                    return False
                remove_mod(oldmod)
            zfile.extractall(MODFOLDER)
            logger.debug("Successfully downloaded and extracted mod from: " + link)
            return True
        else:    
            logger.warn("Mod download cancelled for: " + link)
            return False

    except:
        logger.warn("Mod download or extraction failed for: " + link)        
        if sys.exc_info()[0] is urllib2.HTTPError:
            logger.warning("ModVault download failed with HTTPError, mod probably not in vault (or broken).")
            QtGui.QMessageBox.information(None, "Mod not downloadable",
                                          "<b>This mod was not found in the vault (or is broken).</b><br/>"
                                          "You need to get it from somewhere else in order to use it.",
                                          QtGui.QMessageBox.Ok)
        else:                
            logger.error("Download Exception", exc_info=sys.exc_info())
            QtGui.QMessageBox.information(None, "Mod installation failed",
                                          "<b>This mod could not be installed (please report this map or bug).</b>",
                                          QtGui.QMessageBox.Ok)
        return False


def remove_mod(mod):
    logger.debug("removing mod %s" % mod.name)
    for m in get_installed_mods():
        if m.uid == mod.uid:
            real = m
            break
    else:
        logger.debug("Can't remove mod. Mod not found.")
        return False
    shutil.rmtree(real.absfolder)
    if real.localfolder in modCache:
        del modCache[real.localfolder]
    installed_mods.remove(real)
    return True
    # we don't update the installed mods, because the operating system takes
    # some time registering the deleted folder.
