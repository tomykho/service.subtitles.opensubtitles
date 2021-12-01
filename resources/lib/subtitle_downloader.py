# -*- coding: utf-8 -*-

import os
import shutil
import sys
import uuid
import struct

import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from resources.lib.data_collector import get_language_data, get_media_data, get_file_path, convert_language, \
    clean_feature_release_name
from resources.lib.exceptions import AuthenticationError, ConfigurationError, DownloadLimitExceeded, ProviderError, \
    ServiceUnavailable, TooManyRequests
from resources.lib.file_operations import get_file_data
from resources.lib.os.provider import OpenSubtitlesProvider
from resources.lib.utilities import get_params, log, error

__addon__ = xbmcaddon.Addon()
__scriptid__ = __addon__.getAddonInfo("id")

__profile__ = xbmcvfs.translatePath(__addon__.getAddonInfo("profile"))
__temp__ = xbmcvfs.translatePath(os.path.join(__profile__, "temp", ""))

if xbmcvfs.exists(__temp__):
    shutil.rmtree(__temp__)
xbmcvfs.mkdirs(__temp__)


class SubtitleDownloader:

    def __init__(self):

        self.api_key = __addon__.getSetting("APIKey")
        self.username = __addon__.getSetting("OSuser")
        self.password = __addon__.getSetting("OSpass")

        log(__name__, sys.argv)

        self.sub_format = "srt"
        self.handle = int(sys.argv[1])
        self.params = get_params()
        self.query = {}
        self.subtitles = {}
        self.file = {}

        try:
            self.open_subtitles = OpenSubtitlesProvider(self.api_key, self.username, self.password)
        except ConfigurationError as e:
            error(__name__, 32002, e)

    def handle_action(self):
        log(__name__, "action '%s' called" % self.params["action"])
        if self.params["action"] == "manualsearch":
            self.search(self.params['searchstring'])
        elif self.params["action"] == "search":
            self.search()
        elif self.params["action"] == "download":
            self.download()

    def search(self, query=""):
        file_data = get_file_data(get_file_path())
        language_data = get_language_data(self.params)
        # if there's query passed we use it, don't try to pull media data from VideoPlayer
        if query:
            media_data = {"query": query}
        else:
            media_data = get_media_data()
        self.query = {**media_data, **file_data, **language_data}

        if not self.query['temp']:
            file_path = self.query['file_original_path']
            rar = self.query['rar']
            hash = self.hashFile(file_path, rar)
            self.query['moviehash'] = hash

        try:
            self.subtitles = self.open_subtitles.search_subtitles(self.query)
        # TODO handle errors individually. Get clear error messages to the user
        except (TooManyRequests, ServiceUnavailable, ProviderError, ValueError) as e:
            error(__name__, 32001, e)

        if self.subtitles and len(self.subtitles):
            log(__name__, len(self.subtitles))
            self.list_subtitles()
        else:
            # TODO retry using guessit???
            log(__name__, "No subtitle found")

    def download(self):
        try:
            self.file = self.open_subtitles.download_subtitle(
                {"file_id": self.params["id"], "sub_format": self.sub_format})
        # TODO handle errors individually. Get clear error messages to the user
        except AuthenticationError as e:
            error(__name__, 32003, e)
        except DownloadLimitExceeded as e:
            error(__name__, 32004, e)
        except (TooManyRequests, ServiceUnavailable, ProviderError, ValueError) as e:
            error(__name__, 32001, e)

        subtitle_path = os.path.join(__temp__, f"{str(uuid.uuid4())}.{self.sub_format}")

        tmp_file = open(subtitle_path, "w" + "b")
        tmp_file.write(self.file["content"])
        tmp_file.close()

        list_item = xbmcgui.ListItem(label=subtitle_path)
        xbmcplugin.addDirectoryItem(handle=self.handle, url=subtitle_path, listitem=list_item, isFolder=False)

        return

        """old code"""
        # subs = Download(params["ID"], params["link"], params["format"])
        # for sub in subs:
        #    listitem = xbmcgui.ListItem(label=sub)
        #    xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=sub, listitem=listitem, isFolder=False)

    def list_subtitles(self):
        """TODO rewrite using new data. do not forget Series/Episodes"""
        x = 0
        for subtitle in self.subtitles:
            x += 1
            if x > 10:
                return
            attributes = subtitle["attributes"]
            language = convert_language(attributes["language"], True)
            log(__name__, attributes)
            clean_name = clean_feature_release_name(attributes["feature_details"]["title"], attributes["release"],
                                                    attributes["feature_details"]["movie_name"])
            list_item = xbmcgui.ListItem(label=language,
                                         label2=clean_name)
            list_item.setArt({
                "icon": str(int(round(float(attributes["ratings"]) / 2))),
                "thumb": attributes["language"]})
            list_item.setProperty("sync", "true" if attributes.get("moviehash_match", False) else "false")
            list_item.setProperty("hearing_imp", "true" if attributes["hearing_impaired"] else "false")
            """TODO take care of multiple cds id&id or something"""
            url = f"plugin://{__scriptid__}/?action=download&id={attributes['files'][0]['file_id']}"

            xbmcplugin.addDirectoryItem(handle=self.handle, url=url, listitem=list_item, isFolder=False)
        xbmcplugin.endOfDirectory(self.handle)

    def hashFile(self, file_path, rar):
        if rar:
            return self.OpensubtitlesHashRar(file_path)

        log( __name__,"Hash Standard file")
        longlongformat = 'q'  # long long
        bytesize = struct.calcsize(longlongformat)
        print(file_path)
        f = xbmcvfs.File(file_path)

        filesize = f.size()
        print(filesize)
        hash = filesize

        if filesize < 65536 * 2:
            return "SizeError"

        buffer = f.read(65536)
        f.seek(max(0,filesize-65536),0)
        buffer += f.read(65536)
        f.close()
        for x in range((65536/bytesize)*2):
            size = x*bytesize
            (l_value,)= struct.unpack(longlongformat, buffer[size:size+bytesize])
            hash += l_value
            hash = hash & 0xFFFFFFFFFFFFFFFF

        returnHash = "%016x" % hash
        return returnHash

    def OpensubtitlesHashRar(self, firsrarfile):
        log( __name__,"Hash Rar file")
        f = xbmcvfs.File(firsrarfile)
        a=f.read(4)
        if a!='Rar!':
            raise Exception('ERROR: This is not rar file.')
        seek=0
        for i in range(4):
            f.seek(max(0,seek),0)
            a=f.read(100)
            type,flag,size=struct.unpack( '<BHH', a[2:2+5])
            if 0x74==type:
                if 0x30!=struct.unpack( '<B', a[25:25+1])[0]:
                    raise Exception('Bad compression method! Work only for "store".')
                s_partiizebodystart=seek+size
                s_partiizebody,s_unpacksize=struct.unpack( '<II', a[7:7+2*4])
                if (flag & 0x0100):
                    s_unpacksize=(struct.unpack( '<I', a[36:36+4])[0] <<32 )+s_unpacksize
                    log( __name__ , 'Hash untested for files biger that 2gb. May work or may generate bad hash.')
                lastrarfile=getlastsplit(firsrarfile,(s_unpacksize-1)/s_partiizebody)
                hash=addfilehash(firsrarfile,s_unpacksize,s_partiizebodystart)
                hash=addfilehash(lastrarfile,hash,(s_unpacksize%s_partiizebody)+s_partiizebodystart-65536)
                f.close()
                return (s_unpacksize,"%016x" % hash )
            seek+=size
        raise Exception('ERROR: Not Body part in rar file.')

    def getlastsplit(firsrarfile,x):
        if firsrarfile[-3:]=='001':
            return firsrarfile[:-3]+('%03d' %(x+1))
        if firsrarfile[-11:-6]=='.part':
            return firsrarfile[0:-6]+('%02d' % (x+1))+firsrarfile[-4:]
        if firsrarfile[-10:-5]=='.part':
            return firsrarfile[0:-5]+('%1d' % (x+1))+firsrarfile[-4:]
        return firsrarfile[0:-2]+('%02d' %(x-1) )

    def addfilehash(name,hash,seek):
        f = xbmcvfs.File(name)
        f.seek(max(0,seek),0)
        for i in range(8192):
            hash+=struct.unpack('<q', f.read(8))[0]
            hash =hash & 0xffffffffffffffff
        f.close()
        return hash

    def normalizeString(str):
        return unicodedata.normalize('NFKD', str)
