"""The lock uses webrtcvad-wheels, whose import remains webrtcvad.

The generic contrib hook requests the distinct webrtcvad distribution's
metadata. Never install that other distribution just to satisfy a build hook.
"""
from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata('webrtcvad-wheels')
hiddenimports = ['_webrtcvad']
