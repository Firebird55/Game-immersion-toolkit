"""Authored source-stage inputs, copied unchanged from the NTE owner fixtures.

Original helper definitions: test_nte_updater_source.py at ed9117fe.
No original publisher software, library approval or game content is included.
"""
import hashlib
import io
import json
from xml.etree import ElementTree as E
from zipfile import ZIP_STORED, ZipFile

from backend import nte_updater_source as source
from backend.tests.test_nte_original_updater import authored_sdk


def packed(name, data):
    output = io.BytesIO()
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        archive.writestr(name, data)
    return output.getvalue()


class Originals:
    def __init__(self, version='1.2.3.4', sdk=None):
        self.version, self.requests = version, []
        self.base = source.VERSION_URL.rsplit('/', 1)[0]
        self.product = version + '_1'
        self.manifest_url = self.base + '/' + self.product + '/AllFiles.xml'
        self.version_body = ('[VERSION]\nVersion='+version+'\nFileListURL='+self.manifest_url+'\n').encode()
        self.root = E.Element('All_Files')
        E.SubElement(self.root, 'ProductVersion', Version=self.product)
        E.SubElement(self.root, 'Url', BaseUrl=self.base)
        configuration = json.dumps({'appId': 'authored-demo',
            'gameResUrl': ['https://ntecdn1.perfectworld.com/clientRes'], 'branchName': 'PC_100'}).encode()
        self.bodies = {}
        self.add('/PatcherSDK_x64.dll', sdk or authored_sdk())
        self.add('/ResFilesM/123/PatcherConfig/PatcherConfig.json', configuration)

    def add(self, path, body):
        archive = packed(path.rsplit('/', 1)[1], body)
        self.bodies[self.base+'/'+self.product+path+'.zip'] = archive
        E.SubElement(self.root, 'File', Path=path, Size=str(len(body)), Checksum=hashlib.md5(body).hexdigest(),
                     ZipSize=str(len(archive)), ZipChecksum=hashlib.md5(archive).hexdigest())

    def fetch(self, url, *, limit):
        self.requests.append(url)
        if url == source.VERSION_URL: result = self.version_body
        elif url == self.manifest_url: result = E.tostring(self.root)
        else: result = self.bodies[url]
        assert len(result) <= limit
        return result
