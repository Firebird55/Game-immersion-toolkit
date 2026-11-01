"""Portable source/profile and owned lifecycle fixtures; no native execution."""
import ast, copy, ctypes as c, difflib, hashlib, importlib.util, io, json, os, shutil, stat, struct, sys, tarfile, tempfile, types, unittest, xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
R=Path(__file__).resolve().parents[2];O=R
spec=importlib.util.spec_from_file_location('owned_mp3_contract',R/'scripts/replay-mp3-codec.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BASELINE={'ASR_inputs': ['packaging/asr/sherpa-reference.json', 'packaging/asr/tts-off-python-symbols.patch', 'packaging/asr/SHERPA-LICENSE.txt', 'packaging/asr/SHERPA-PATCH-NOTICE.txt', 'packaging/asr/cmake-compilerid-instance-location.patch', 'packaging/asr/CMAKE-LICENSE.rst', 'packaging/asr/CMAKE-MODULE-PATCH-NOTICE.txt', 'scripts/reference-asr.py', 'scripts/build-reference-asr.ps1', 'scripts/probe-reference-asr.py', 'packaging/runtime-bundle/python-supplier.json', 'packaging/build-tools/cmake-4.4.5-windows-x64.json', 'scripts/pinned-build-cmake.py', 'backend/windows_preparation_process.py', 'LICENSE'], 'FF_inputs': ['packaging/codecs/ffmpeg-opus-replay.json', 'scripts/replay-game-codec.py', 'scripts/build-game-codec-replay.ps1', 'scripts/fixtures/game-codec-replay.c', 'backend/codec_fixture.py', 'LICENSE', 'scripts/pinned-build-cmake.py', 'packaging/build-tools/cmake-4.4.5-windows-x64.json', 'packaging/codecs/patches/ffmpeg-9.0.2-makedef-private-stdout.patch', 'packaging/codecs/FFMPEG-BUILD-RECIPES-LICENSE.txt'], 'files': {'LICENSE': {'bytes': 1492, 'sha256': '1d2f36f13b16b401e4bbf81e955ea185d50c6b5de281d89915e240138b7bb396'}, 'backend/codec_fixture.py': {'bytes': 1326, 'sha256': '4c1c9c1d1285c772bf77a614b802f3f788eeac2474d35dc1c65f40dd8fbc6874'}, 'backend/tests/test_game_codec_replay.py': {'bytes': 94869, 'sha256': 'd72a6eec02a1370d54794a1b3dfc10d96714daa90d536980d7ac48a268127a51'}, 'backend/windows_preparation_process.py': {'bytes': 25651, 'sha256': '24a6995cc1d4d9260a9afe3049fbdf5d927cfddcfd405095ebcd49674e7234d0'}, 'packaging/asr/CMAKE-LICENSE.rst': {'bytes': 1526, 'sha256': 'cd944d878806fee998ef3f88ca41ec060ae198bd8ba615e284f7d8d90c25593e'}, 'packaging/asr/CMAKE-MODULE-PATCH-NOTICE.txt': {'bytes': 1415, 'sha256': 'ab6e4b31bcff5a59eca98a867a90f7ee391f70055034070b96eb2fd48c878a6c'}, 'packaging/asr/SHERPA-LICENSE.txt': {'bytes': 11358, 'sha256': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'}, 'packaging/asr/SHERPA-PATCH-NOTICE.txt': {'bytes': 1678, 'sha256': '475fb78d29421db814106b80b075f1b05803ff180bfa860d8dd92a86291c5246'}, 'packaging/asr/cmake-compilerid-instance-location.patch': {'bytes': 1926, 'sha256': 'd1b339d100492a16e8733dc7c44e2580b1905e09e117a9cf4b585455980fa656'}, 'packaging/asr/sherpa-reference.json': {'bytes': 15976, 'sha256': '6cfb8624fb036941ac8579ff069a5841f856a0f0244c6cd0b0ce12912cf2c642'}, 'packaging/asr/tts-off-python-symbols.patch': {'bytes': 672, 'sha256': '39018d88283dffd50436dbc833ae038543398b59dc9269e45b6ed717eea0caee'}, 'packaging/build-tools/cmake-4.4.5-windows-x64.json': {'bytes': 2808, 'sha256': 'b65df3fa12af3f05ec0e87a793b1c8fd4f930b5f41d2473559c5f681f2a07ffa'}, 'packaging/codecs/FFMPEG-BUILD-RECIPES-LICENSE.txt': {'bytes': 5993, 'sha256': 'eb89bd307353f5e14b392e7b3b1307e31681d7258bba8b8777965a4362e5bd07'}, 'packaging/codecs/ffmpeg-opus-replay.json': {'bytes': 12450, 'sha256': '3baa0a0d1e30a5e149213ddf1eb071d776fbe687f9302ff834fdeaee3a55ed99'}, 'packaging/codecs/patches/ffmpeg-9.0.2-makedef-private-stdout.patch': {'bytes': 1551, 'sha256': '5306d015bbb01949b7f09c753a5a23cd5abae4816e889f536ba27b8ac139419c'}, 'packaging/runtime-bundle/python-supplier.json': {'bytes': 1003, 'sha256': 'a330444faed50bcb9107435c55d84bcc5042b323a08685b4e01159bbbb20ec67'}, 'scripts/build-game-codec-replay.ps1': {'bytes': 33615, 'sha256': '0e128a3aa60d52d065f2e7a3f594886e578f2a3f7f7eaafed1346b34c189971b'}, 'scripts/build-reference-asr.ps1': {'bytes': 4329, 'sha256': '06253afaa97503ff56819c7a38a04c646829f15f069e5fe13ecda8e5eca8169d'}, 'scripts/fixtures/game-codec-replay.c': {'bytes': 7567, 'sha256': 'e0a4ef9acd2843630728cf14da48894da62b9aaef0088115ac500b9d6a19528d'}, 'scripts/pinned-build-cmake.py': {'bytes': 14670, 'sha256': '2e57ff0270f3d97fda1cee9ffe05ef43a9b23c466b1903544957a8a96b190464'}, 'scripts/probe-reference-asr.py': {'bytes': 9668, 'sha256': '48082ddd200cad40515298b67392f0aa7000eb275e9a57d8609f16820a19018f'}, 'scripts/reference-asr.py': {'bytes': 147556, 'sha256': '58d403bc29e8b0c64d4583039780abf4ff4de37d320a60b1db3f8c37a31ba24c'}, 'scripts/replay-game-codec.py': {'bytes': 52758, 'sha256': '41a578f87ff9fccc776a5807dfc1e292c5356d523052aa203947458c61099d6a'}}, 'head': '0f9353137bdc8c57adbe275b4d245a6a1f136796', 'scope': 'Exact Git bytes; overlay additions are a draft, not source-clean0f evidence'}
APPROVED_PROPOSAL=b'PROPOSAL ONLY \xe2\x80\x94 additional original MP3 recipe portions, not yet approved\nDate: 2026-11-01\n\nSuggested owner decision: provide an additional BSD-3-Clause option only for original Firebird55-controlled portions in these four exact draft revisions, plus later bounded notice/source-delivery wiring. The ordinary repository LICENSE remains an alternative. This proposal grants nothing until explicitly approved.\n\npackaging/codecs/ffmpeg-mp3-replay.json\n  LF bytes: 15933\n  SHA256: 8274d8842d05596f49f644f313dd0f885b19b37240fa21dc877fd3b3ff36f4e4\nscripts/replay-mp3-codec.py\n  LF bytes: 48280\n  SHA256: 615ea978748aa692381bb592628743fbf4b9a4c9ad449be51d929c796a3f4db7\nscripts/build-mp3-codec-replay.ps1\n  LF bytes: 35311\n  SHA256: a0d6f92af1bf7e7377b6eafba902f1c16e120bbee7edd770dcfc76e46676d638\nscripts/fixtures/mp3-codec-origin.c\n  LF bytes: 1571\n  SHA256: c26d6d6c5285c73934fbe214d528b8efea2d5596a65cb8ab57578eb93f1853c3\n\nScope limits:\n- Existing authorized BSD6 portions remain covered by their existing notice. No historical artifact or grant is rewritten.\n- The LAME property patch is derived upstream material and remains subject to the upstream project license; this proposal grants no upstream copyright, asset or patent rights.\n- Tests, this review, .gitattributes, runtime adapters and all future functional changes outside the four exact revisions remain outside this additional option.\n- The exact unchanged backend/windows_preparation_process.py (25651 LF bytes, SHA256 24a6995cc1d4d9260a9afe3049fbdf5d927cfddcfd405095ebcd49674e7234d0) is an additional ordinary-license build dependency, outside these four revisions. Its full LICENSE (1492 LF bytes, SHA256 1d2f36f13b16b401e4bbf81e955ea185d50c6b5de281d89915e240138b7bb396) is already retained once among the original ten inputs. No additional option is inferred for it; source/relinking compatibility remains pending.\n- No source-delivery/relinking compatibility, native/runtime/production/Win11/global/R19 or distribution approval follows.\n- The FFT provenance question remains open; no automatic GPL classification or upstream relicensing is asserted.\n\nIf approved, retain this exact decision as a new standalone notice, retain all complete standard terms below, and bind actual final raw/LF copies separately to avoid circular hash pins. Do not extend the old BSD6 notice by inference.\n\nSTANDARD BSD-3-CLAUSE TERMS\n\nCopyright (c) 2026 Firebird55\n\nRedistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:\n\n1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.\n\n2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.\n\n3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.\n\nTHIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.\n'
APPROVED_BASELINES={'packaging/codecs/ffmpeg-mp3-replay.json': {'bytes': 15933, 'sha256': '8274d8842d05596f49f644f313dd0f885b19b37240fa21dc877fd3b3ff36f4e4'}, 'scripts/replay-mp3-codec.py': {'bytes': 48280, 'sha256': '615ea978748aa692381bb592628743fbf4b9a4c9ad449be51d929c796a3f4db7'}, 'scripts/build-mp3-codec-replay.ps1': {'bytes': 35311, 'sha256': 'a0d6f92af1bf7e7377b6eafba902f1c16e120bbee7edd770dcfc76e46676d638'}, 'scripts/fixtures/mp3-codec-origin.c': {'bytes': 1571, 'sha256': 'c26d6d6c5285c73934fbe214d528b8efea2d5596a65cb8ab57578eb93f1853c3'}}
SUPPLEMENTAL_PROPOSAL=b'PROPOSAL ONLY \xe2\x80\x94 supplemental option for one exact corrected MP3 recipe\nDate: 2026-11-01\n\nNo additional grant takes effect until the owner explicitly approves this proposal. The existing four-revision BSD option and all historical snapshots remain unchanged.\n\nRequested decision: additionally permit the original Firebird55-controlled portions in only this exact corrected baseline under the standard BSD-3-Clause terms below, without an extra visible-credit/link condition for that route. Include only necessary notice and source-delivery processing applying this decision. The ordinary repository LICENSE remains an alternative.\n\nscripts/build-mp3-codec-replay.ps1\n  Proposed baseline LF bytes: 35311\n  Proposed baseline SHA256: 1b0cc7746a84d6152ddc0bb48c6857213d05c7cad68f05b2a537e0346a0ceb64\n  Exact local copy: build-mp3-codec-replay.ps1\n\nThe only functional difference from the previously approved baseline a0d6f92af1bf7e7377b6eafba902f1c16e120bbee7edd770dcfc76e46676d638 is one literal argument: /p:PlatformToolset=v180 becomes /p:PlatformToolset=v145. All other original bytes are identical. The current notice-wired proposed copy is 35342 bytes, SHA256 195f7ebb732729382478660a15de94cff14b630778925629e7ccdb820110cb69, retained separately as license-wired-build-mp3-codec-replay.ps1. correction.diff and REVIEW.json show the complete change and preserved boundaries.\n\nReason: Windows run41311329210 attempt2 reached build-lame and failed with MSBuild diagnostic MSB8020. Microsoft documents v145 as the VS2026 platform toolset; v180 is a C++ targets-directory generation and is not the selected platform toolset. This changes no pinned compiler/SDK version, target architecture, source archive, upstream patch, runtime resolver or native-process criterion. The corrected recipe has not been built yet.\n\nPrimary sources reviewed 2026-11-01:\nhttps://learn.microsoft.com/en-us/cpp/overview/what-s-new-for-msvc?view=msvc-170\nhttps://learn.microsoft.com/en-us/visualstudio/msbuild/errors/msb8020\nhttps://learn.microsoft.com/en-us/cpp/build/reference/msbuild-visual-cpp-overview?view=msvc-180\n\nNo helper, other project file, upstream/FFT/patent right or later functional edit is included. General project and third-party terms stay intact. Complete source/relinking, durable delivery, maintenance, exact output, runtime/distribution/production, Windows11 and R19 gates remain open. No installer, release, merge or PR59 change is proposed.\n\nSTANDARD BSD-3-CLAUSE TERMS\n\nCopyright (c) 2026 Firebird55\n\nRedistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:\n\n1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.\n\n2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.\n\n3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.\n\nTHIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.\n'
SUPPLEMENTAL_BASELINES={'scripts/build-mp3-codec-replay.ps1': {'bytes': 35311, 'sha256': '1b0cc7746a84d6152ddc0bb48c6857213d05c7cad68f05b2a537e0346a0ceb64'}}
ORIGINAL_FUNCTION_AST={'bootstrap_regular': 'c441beb9cfaf794f6b1325b28b1e49000075f3a0796c3641d02f5bdf30fd130a', 'inputs': '550695e75f0455fcfaff733e47147bfa3b7066ce121aff8a7858e964df1bef32', 'project_names': '5de0fa5c802ef2fdb668dd7254d61a879861367fcd85fbd1b46862201df3fdd6', 'project_bytes': '3fcc11c7f304fe9afd472ca286ba3b49c229b1eedbf79071db291b36ef95a7eb', 'patch_lame': '5d7caa4f50648c93c9096fc6b012eda9ed5a78e366bb8b72708aac069a189c8e', 'acquire': '5552f9fe80922d18367d4304d936f0e26d86669dfa1ad193f20daf576e0bf12a', 'validate_inputs': '2bcf15d697c75efe518597374c014b7681bcbd524b2a38dbecd960beff3b7eb7', 'verify_lame_work': '7335d0fe7b9d77b17e4ba0ec072fec0848fbb97b1d64495f0cc7ac34cb308676', 'copy_regular': '4c87e2c59d776fcf149ecc56a7ccb0326b76f9b3e1fdbb816a684873d674035b', 'install_lame': '2df195309ff14d29fff2b55b633a67ac1edb55262587d8baaceba41215245239', 'verify_lame_install': 'd2693bce8eb57caa26330533dece854189f841f6c3fe9cbd3f01aa51456091cf', 'tone': '07bd9d2c23094bb043fb85c2c81e3ca4fe089f37736e6b8043f14eeb7bfb650b', 'check_tone': '25b5955a842b92753956b668aca2e2353c6a43460cfa73ef478445f0ac334582', 'bounded_media_bytes': '3164d1e24731715020d7e9082ad94bbaccdcdf145a852cd046eb199196fb40a8', 'publish_encoded': 'c458a16ab7664a200dd165303cba4f3deba0b10305bc0ec1cb01bd7ac2177965', 'failure': '89e9e4b98dfa145bfe6b43696dcb8aa0caa2dd6cedbf085360c31ff0d49a57a0', 'preflight_failure': 'd888e4411fd2fd1eb44760bca72d7543760b699d93e33a65165171085cb2789f', 'owned_primitive': 'b4541202d788689d83c6a4103993e56fd8a286cf6f4181003e1225c998f2204e', 'split_cli_input': 'ecec90d9a65d01b0d855c769aa3472b80f1c596a8007eec5bab25ae4e34f7185', 'owned_cli_attempt': 'b5199c617f85d213dfe1bd2f15bf1e43fdde491ac6db03100fda9f221d46332f', 'hold_cli_owner_failure': 'da251012c5afcf4bbf86bf8495d86a974e1f09daf36ebaf7765b01b3c2d84629', 'retained_probe_work': '1adc848c81881263b7e6d463b91763178c7f839a5e425bee5eea8fcec5efa7a1', 'native_run': 'e18db6079898a9ca7ab092ee9024165ea3531817665256e27f612da9a47b3932', 'finish': 'd872d0fb262bf48de26b98edae6c309c7397ad89947ed26868fdb37875100f8b', 'main': '282061ae07e99a5abb51479e3a7cb15af82c8bb626999f5b19d980c363f38722'}
ORIGINAL_CLASS_AST=['f459d9ba539a627cf6e56664c632b9d7043ef04054aa246dc119654284658aa4', '58c64926e1ded6ec0e02f2e1712ed61fed148bcbb7694f7db3b816b12fe023fe', 'b72be9c51317e8fe73a6514bc4bb5a8fd61cbcdda1f114032e357c3a8c7ba679', '895c3411cf22e55140bae8143dae27ae6c80ad713ea4f049bae04b0d465c3b75', 'e91f03e9068e9a03bd78e51ff58c28b4d938ebc427aff650780b14472a2d01d1', 'bd87e4d3ebe15f5700db6deb719102d528f19fcd22000863140f9fdf6e2dd8ca', 'bb88d9c2df1fd58f2c45d24f510202f3ec3d8be607325f9e8bced69f1393b096']
ORIGINAL_PS_BODY={'bytes': 35219, 'sha256': 'a658db17388f85845849b6f8f0e8ccf7f4c49db23862901496bc4163463ff806'}
ORIGINAL_C_BODY={'bytes': 1402, 'sha256': '02da88a9f90322b617e66a31b0876075769b76970b96f5221e3c317b7f463d7a'}
ORIGINAL_FUNCTIONAL_PROFILE='ea2733d6b16b106f067cf9707228c09703650fc707dfe0247db73908952c93e3'
class Contracts(unittest.TestCase):
 def test_baseline_ten_and_asr_fifteen_bytes_remain_exact(self):
  d=BASELINE;self.assertEqual(len(d['FF_inputs']),10);self.assertEqual(len(d['ASR_inputs']),15)
  for n,v in d['files'].items():
   with self.subTest(n=n):
    raw=(R/n).read_bytes();self.assertIn(v,(m.record(raw),m.record(raw.replace(b'\r\n',b'\n'))))
 def test_fixed_options_keep_original_recipe_and_add_required_cli_dependencies(self):
  p=m.policy();self.assertEqual(p['audio_cli_overrides'],m.OVERRIDES)
  self.assertIn('--enable-w32threads',m.OVERRIDES);self.assertIn('--enable-avfilter',m.OVERRIDES)
  for change in (lambda x:x['audio_cli_overrides'].append('--enable-gpl'),lambda x:x['audio_cli_overrides'].remove('--enable-w32threads'),lambda x:x['host'].update(compiler_version='0.0.0.0'),lambda x:x['sources'][2].update(version='3.100'),lambda x:x['build_recipe_license']['supplemental_approval']['approved_baselines'].update({'scripts/future.py':{'bytes':1,'sha256':'0'*64}}),lambda x:x['build_recipe_license']['supplemental_approval']['approval_proposal'].update(sha256='0'*64)):
   bad=copy.deepcopy(p);change(bad)
   with patch.object(m.base,'recipe_json',return_value=bad),self.assertRaises(ValueError):m.policy()
 def test_ordinary_crlf_checkout_preserves_exact_canonical_helper_and_profile_binding(self):
  # Explicit LF and already-CRLF source forms must produce one identical CRLF fixture.
  raw_preserved={m.base.BSD_GRANT,m.base.VARIANT_PATCH,m.MP3_GRANT,m.policy()['lame_variant']['patch']['path']}
  for source_is_crlf in (False,True):
   with self.subTest(source_is_crlf=source_is_crlf),tempfile.TemporaryDirectory() as name:
    root=Path(name).resolve()
    for n in m.PROJECT_INPUTS:
     original=(O/n).read_bytes();lf=original.replace(b'\r\n',b'\n')
     source=original if n in raw_preserved else (lf.replace(b'\n',b'\r\n') if source_is_crlf else lf)
     data=source if n in raw_preserved else source.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
     dest=root/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    spec=importlib.util.spec_from_file_location('owned_crlf_draft',root/'scripts/replay-mp3-codec.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    self.assertEqual(module.policy()['audio_cli_overrides'],m.OVERRIDES)
    helper=(root/'scripts/replay-game-codec.py').read_bytes();lf=(O/'scripts/replay-game-codec.py').read_bytes().replace(b'\r\n',b'\n')
    self.assertEqual(helper,lf.replace(b'\n',b'\r\n'));self.assertEqual(helper.replace(b'\r\n',b'\n'),lf);self.assertIn(b'\r\n',helper);self.assertNotIn(b'\r\r\n',helper)
 def test_real_lame_guard_patch_changes_only_the_two_original_conditions(self):
  p=copy.deepcopy(m.policy());archive=os.environ.get('R19_MP3_ARCHIVE')
  if archive:
   data=Path(archive).read_bytes();self.assertEqual(m.record(data),{k:p['sources'][2][k] for k in ('bytes','sha256')})
   with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as source:original=source.extractfile('lame-4.0/vc_solution/vs2019_libmpg123_config.props').read()
   raw=(R/p['lame_variant']['patch']['path']).read_bytes()
  else:
   # Owned XML and private fixture identities; the real archive is checked
   # in memory after explicit acquisition, before any native compilation.
   original=('<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">'+''.join('<ItemDefinitionGroup><PreLinkEvent><Command Condition="!Exists(\'$(Mpg123Path)libmpg123-0.lib\') And \'$(Platform)\' == \''+arch+'\'">authored command</Command></PreLinkEvent></ItemDefinitionGroup>' for arch in ('Win32','x64'))+'</Project>\n').encode()
   modified=original.replace(b'Condition="!Exists',b'Condition="\'$(HaveMpg123)\' == \'true\' And !Exists')
   raw=''.join(difflib.unified_diff(original.decode().splitlines(True),modified.decode().splitlines(True),fromfile='a/vc_solution/vs2019_libmpg123_config.props',tofile='b/vc_solution/vs2019_libmpg123_config.props')).encode()
   p['lame_variant'].update(preimage=m.record(original),postimage=m.record(modified));p['lame_variant']['patch'].update(m.record(raw))
  new=m.patch_lame(original,raw,p);self.assertEqual(m.record(new),p['lame_variant']['postimage']);self.assertEqual(new.count(b"'$(HaveMpg123)' == 'true' And !Exists"),2);self.assertEqual(new.replace(b"'$(HaveMpg123)' == 'true' And !Exists",b'!Exists'),original)
  root=ET.fromstring(new);ns={'m':'http://schemas.microsoft.com/developer/msbuild/2003'};commands=root.findall('m:ItemDefinitionGroup/m:PreLinkEvent/m:Command',ns);self.assertEqual(len(commands),2)
  for command in commands:self.assertTrue(command.attrib['Condition'].startswith("'$(HaveMpg123)' == 'true' And "))
  for a,b in ((original+b'wrong',raw),(original,raw+b'wrong'),(new,raw)):
   with self.subTest(change=(len(a),len(b))),self.assertRaises(ValueError):m.patch_lame(a,b,p)
 def test_acquisition_rejects_wrong_bytes_without_partial_output_or_native_tools(self):
  with tempfile.TemporaryDirectory() as name:
   target=Path(name).resolve()/'fresh'
   with patch.object(m.urllib.request,'urlopen',return_value=io.BytesIO(b'authored wrong source bytes')),self.assertRaises(ValueError):m.acquire(target,include_tools=False)
   self.assertFalse(target.exists())
   with patch.object(m.sys,'platform','darwin'),patch.object(m.urllib.request,'urlopen',side_effect=AssertionError('No native tool acquisition allowed')),self.assertRaises(ValueError):m.acquire(target)
 def test_generated_config_is_exact_and_no_other_source_change_is_accepted(self):
  with tempfile.TemporaryDirectory() as name:
   r=Path(name).resolve();w=r/'lame-build-source';w.mkdir();(w/'source.c').write_bytes(b'authored source');(w/'configMS.h').write_bytes(b'authored config')
   original=r/'upstream/lame-4.0';original.mkdir(parents=True);(original/'configMS.h').write_bytes(b'authored config')
   before=m.base.inventory(w);m.write(r/'LAME-WORKING-INPUTS.json',before);p={'lame_working_source_tree':m.base.tree_identity(before)}
   m.verify_lame_work(r,p,False)
   with self.assertRaises(ValueError):m.verify_lame_work(r,p,True)
   (w/'config.h').write_bytes(b'authored config');m.verify_lame_work(r,p,True)
   for file in ('config.h','source.c'):
    old=(w/file).read_bytes();(w/file).write_bytes(b'tampered')
    with self.subTest(file=file),self.assertRaises(ValueError):m.verify_lame_work(r,p,True)
    (w/file).write_bytes(old)
   (w/'unknown').write_bytes(b'private')
   with self.assertRaises(ValueError):m.verify_lame_work(r,p,True)
   installed=r/'out/lame';installed.mkdir(parents=True);(installed/'owned.lib').write_bytes(b'authored library control fixture');m.write(r/'LAME-INSTALLED.json',m.base.inventory(installed));m.verify_lame_install(r)
   (installed/'owned.lib').write_bytes(b'tampered')
   with self.assertRaises(ValueError):m.verify_lame_install(r)

 def test_unknown_sourcekit_member_refused_before_its_metadata_or_content(self):
  with tempfile.TemporaryDirectory() as name:
   r=Path(name).resolve();(r/'upstream').mkdir();(r/'upstream/source.c').write_bytes(b'authored source');before=m.base.inventory(r/'upstream');m.write(r/'PREPARED-SOURCE.json',before)
   kit=r/'source-review';kit.mkdir();unknown=kit/'unknown-private';unknown.write_bytes(b'never read')
   p={'original_source_tree':m.base.tree_identity(before),'sources':[],'original_recipes':[]}
   rawstat=Path.lstat;rawleafstat=Path.stat;rawopen=Path.open
   def ls(path,*a,**kw):
    if path==unknown:raise AssertionError('Unknown leaf metadata read')
    return rawstat(path,*a,**kw)
   def st(path,*a,**kw):
    if path==unknown:raise AssertionError('Unknown leaf stat read')
    return rawleafstat(path,*a,**kw)
   def op(path,*a,**kw):
    if path==unknown:raise AssertionError('Unknown leaf content read')
    return rawopen(path,*a,**kw)
   with patch.object(m,'policy',return_value=p),patch.object(Path,'lstat',ls),patch.object(Path,'stat',st),patch.object(Path,'open',op),self.assertRaises(ValueError):m.verify_sources(r)
 def test_atomic_publication_contract_rejects_bad_owned_callback_results(self):
  # These callbacks are authored control fixtures, not a native MP3 proof.
  with tempfile.TemporaryDirectory() as name:
   previous=Path(name).resolve()/'voice.mp3';previous.write_bytes(b'old complete')
   good=lambda p:p.write_bytes(b'ID3'+b'fixture-control-only'*20)
   m.publish_encoded(good,lambda p:m.tone(440),previous,440);saved=previous.read_bytes()
   def badfile(p):p.write_bytes(b'RIFF'+bytes(200))
   def raises(p):raise ValueError('owned failure')
   for run,decode in ((badfile,lambda p:m.tone(440)),(raises,lambda p:m.tone(440)),(good,lambda p:m.tone(880)),(good,lambda p:bytes(105840)),(good,lambda p:b'odd')):
    with self.subTest(run=run),self.assertRaises(ValueError):m.publish_encoded(run,decode,previous,440)
    self.assertEqual(previous.read_bytes(),saved)
   previous.unlink();previous.symlink_to(Path(name).resolve()/'linked-output')
   with patch.object(m,'check_tone',side_effect=AssertionError('No linked-output conversion allowed')),self.assertRaises(ValueError):m.publish_encoded(good,lambda p:m.tone(440),previous,440)
 def test_ps_caller_defers_candidate_creation_to_real_staging_and_existing_output_is_refused(self):
  # Source contract only for the unavailable PS engine; execute the real called
  # Python command on authored inert native-file fixtures, without preparation.
  caller=(O/'scripts/build-mp3-codec-replay.ps1').read_text().split("$candidate = Join-Path $OutputRoot 'candidate'",1)[1].split('foreach ($notice',1)[0]
  lines=[line.strip() for line in caller.splitlines() if line.strip() and not line.lstrip().startswith('#')]
  self.assertEqual(lines,["Invoke-Build 'observe-and-package' $pythonExe @('-I','-B',(Join-Path $PSScriptRoot 'replay-mp3-codec.py'),", "'stage-candidate','--output',$OutputRoot)"])
  with tempfile.TemporaryDirectory() as name:
   root=Path(name).resolve();prefix=root/'out/ffmpeg-vs-64/bin';prefix.mkdir(parents=True);lame=root/'out/lame/bin';lame.mkdir(parents=True)
   expected={n:('authored inert '+n).encode() for n in (*m.FF_DLLS,'ffmpeg.exe','libmp3lame.dll')}
   for n,data in expected.items():((lame if n=='libmp3lame.dll' else prefix)/n).write_bytes(data)
   with patch.object(m,'verify_sources',return_value={}),patch.object(m,'verify_lame_install',return_value={}),patch.object(sys,'argv',['replay-mp3-codec.py','stage-candidate','--output',str(root)]):m.main()
   candidate=root/'candidate';expected_records={n:m.record(b) for n,b in expected.items()};expected_records['notices/project/MP3-BUILD-RECIPES-LICENSE.txt']=m.record((O/m.MP3_GRANT).read_bytes());self.assertEqual(m.base.inventory(candidate),expected_records)
   before=m.base.inventory(candidate)
   with patch.object(m,'verify_sources',return_value={}),patch.object(m,'verify_lame_install',return_value={}),patch.object(m,'copy_regular',side_effect=AssertionError('Existing candidate must not be copied over')),self.assertRaises(ValueError):m.stage_candidate(root)
   self.assertEqual(m.base.inventory(candidate),before)
  with tempfile.TemporaryDirectory() as name:
   root=Path(name).resolve();prefix=root/'out/ffmpeg-vs-64/bin';prefix.mkdir(parents=True);(prefix/'unapproved.exe').write_bytes(b'inert unknown fixture')
   with patch.object(m,'verify_sources',return_value={}),patch.object(m,'verify_lame_install',return_value={}),self.assertRaises(ValueError):m.stage_candidate(root)
   self.assertFalse((root/'candidate').exists())
 def test_authored_pcm_identity_accepts_only_the_expected_bounded_signal(self):
  for freq in (440,880):
   m.check_tone(m.tone(freq),freq)
   with self.assertRaises(ValueError):m.check_tone(m.tone(freq),880 if freq==440 else 440)
  for raw in (b'',bytes(1024),m.tone(440)*2):
   with self.subTest(size=len(raw)),self.assertRaises(ValueError):m.check_tone(raw,440)
 def test_copy_refuses_linked_parent_without_reading_descendant(self):
  with tempfile.TemporaryDirectory() as name:
   r=Path(name).resolve();(r/'outside').mkdir();(r/'outside/value').write_bytes(b'private');(r/'link').symlink_to(r/'outside',target_is_directory=True);source=r/'link/value';old=Path.lstat
   def guard(path,*a,**kw):
    if path==source:raise AssertionError('Descendant metadata traversed linked parent')
    return old(path,*a,**kw)
   with patch.object(Path,'lstat',guard),self.assertRaises(ValueError):m.copy_regular(source,r/'dest')
   self.assertFalse((r/'dest').exists())
 def test_failure_projection_keeps_only_fixed_categories_and_excludes_old_phase(self):
  with tempfile.TemporaryDirectory() as name:
   r=Path(name).resolve();log=r/'private.log';old=b'error C1083: old-phase\n';log.write_bytes(old+b'private/path error LNK1104: cannot open SECRET-model\n')
   with patch.dict(os.environ,{'GITHUB_SHA':'0'*40}):m.failure(r,'build-lame',2,log,len(old))
   d=m.base.recipe_json(r/'FAILED-STAGE.json');self.assertEqual(d['diagnostic_codes'],['LNK1104']);self.assertNotIn('C1083',d['diagnostic_codes']);self.assertNotIn('SECRET',json.dumps(d));self.assertFalse(d['source_delivery_approved']);self.assertFalse((r/'MP3-DRAFT-RECEIPT.json').exists())
 def test_native_finish_is_unavailable_here_before_any_source_or_tool_operation(self):
  with patch.object(m.sys,'platform','darwin'),patch.object(m,'verify_sources',side_effect=AssertionError('No native action permitted')),self.assertRaises(ValueError):m.finish(Path('/unopened'),Path('/unopened'))
 def test_native_capture_cleanup_attempts_wait_even_when_poll_or_kill_fails(self):
  class Process:
   returncode=1
   def __init__(self):self.waits=0;self.kills=0
   def poll(self):raise OSError('private process failure')
   def kill(self):self.kills+=1;raise OSError('private kill failure')
   def wait(self,timeout):self.waits+=1
  p=Process()
  with patch.object(m.subprocess,'Popen',return_value=p),self.assertRaises(OSError):m.native_run(['not executed'],'.',{})
  self.assertEqual((p.kills,p.waits),(1,1));held=m.RETAINED_CLI_OWNERS.pop();self.assertIs(held['process'],p);held['stdout'].close();held['stderr'].close()
 def test_private_native_capture_caps_deadline_and_reap_with_owned_process_doubles(self):
  class Process:
   def __init__(self,mode):self.mode=mode;self.kills=0;self.waits=0;self.returncode=0 if mode!='deadline' else None
   def poll(self):return self.returncode
   def kill(self):self.kills+=1;self.returncode=1
   def wait(self,timeout):self.waits+=1
  for mode in ('success','stdout-oversize','stderr-oversize','deadline'):
   p=Process(mode)
   def start(*a,**kw):
    kw['stdout'].write(b'known' if mode!='stdout-oversize' else b'PRIVATE'*6000)
    if mode=='stderr-oversize':kw['stderr'].write(b'SECRET'*6000)
    return p
   with self.subTest(mode=mode),patch.object(m.subprocess,'Popen',side_effect=start),patch.object(m.time,'monotonic',side_effect=[0,21]):
    if mode=='success':self.assertEqual(m.native_run(['not executed'],'.',{}),b'known')
    else:
     with self.assertRaises(ValueError) as e:m.native_run(['not executed'],'.',{})
     self.assertNotIn('PRIVATE',str(e.exception));self.assertNotIn('SECRET',str(e.exception))
   self.assertEqual(p.waits,1);self.assertEqual(p.kills,int(mode=='deadline'))
 def test_new_functional_work_has_no_borrowed_bsd_or_runtime_approval(self):
  b=m.license_boundary();self.assertIn('Additional BSD-3-Clause option only for four approved',b['new_functional_license']);self.assertEqual(b['additional_original_mp3_grant'],m.MP3_PROJECT_LICENSE);self.assertEqual(len(b['new_functional_inputs']),5)
  for k in ('source_delivery_approved','runtime_collection_allowed','production_execution_allowed','r19_complete'):self.assertIs(b[k],False)
  self.assertEqual(b['original_unchanged_base_grant'],m.base.PROJECT_LICENSE)

class Grant(unittest.TestCase):
 def test_effective_notice_retains_exact_approved_baselines_and_complete_standard_terms(self):
  proposal=APPROVED_PROPOSAL;self.assertEqual(m.record(proposal),{'bytes':3840,'sha256':'3adc6e4775f8bb5f53e2d63ec031eec8222c80c319fc0c268906d1533b80601c'});notice=(O/m.MP3_GRANT).read_bytes();self.assertEqual(m.record(notice),{k:m.MP3_PROJECT_LICENSE['grant'][k] for k in ('bytes','sha256')});prefix=notice[:4588];self.assertEqual(m.record(prefix),{'bytes':4588,'sha256':'f470deb41e0feea5f564b739e79c1378e457d6a7a6512f4c71a9e39958c476d1'});self.assertEqual(prefix.split(b'STANDARD BSD-3-CLAUSE TERMS\n\n')[1],proposal.split(b'STANDARD BSD-3-CLAUSE TERMS\n\n')[1]);self.assertNotIn(b'extra visible credit',notice)
  supplemental=notice[4588:];self.assertEqual(m.record(SUPPLEMENTAL_PROPOSAL),{'bytes':3932,'sha256':'02c220c6a8c1808cec6baefc91c416c33dbd09613193da908edd481c90167938'});self.assertEqual(supplemental.split(b'STANDARD BSD-3-CLAUSE TERMS\n\n')[1],SUPPLEMENTAL_PROPOSAL.split(b'STANDARD BSD-3-CLAUSE TERMS\n\n')[1]);self.assertEqual(m.MP3_SUPPLEMENTAL_BASELINES,SUPPLEMENTAL_BASELINES);self.assertEqual(m.MP3_PROJECT_LICENSE['schema'],'proxy-r19-mp3-recipe-additional-license-v2');self.assertEqual(m.MP3_PROJECT_LICENSE['supplemental_approval']['approved_baselines'],SUPPLEMENTAL_BASELINES);self.assertIn(b'1b0cc7746a84d6152ddc0bb48c6857213d05c7cad68f05b2a537e0346a0ceb64',supplemental)
  for n,row in m.MP3_APPROVED_BASELINES.items():
   with self.subTest(path=n):self.assertEqual(APPROVED_BASELINES[n],row);self.assertIn(row['sha256'].encode(),notice)
  self.assertEqual(len(m.MP3_APPROVED_BASELINES),4);self.assertNotIn('backend/windows_preparation_process.py',m.MP3_APPROVED_BASELINES);self.assertEqual(m.record((R/m.base.BSD_GRANT).read_bytes()),BASELINE['files'][m.base.BSD_GRANT])
 def test_all_functional_AST_flags_process_controller_and_upstream_bytes_are_preserved(self):
  tree=ast.parse((R/'scripts/replay-mp3-codec.py').read_bytes());dump=lambda n:ast.dump(n,include_attributes=False);digest=lambda n:m.sha(dump(n).encode());functions={n.name:digest(n) for n in tree.body if isinstance(n,ast.FunctionDef)}
  for name,value in ORIGINAL_FUNCTION_AST.items():self.assertEqual(functions[name],value,name)
  self.assertEqual([digest(n) for n in tree.body if isinstance(n,ast.ClassDef)],ORIGINAL_CLASS_AST)
  body=(R/'scripts/build-mp3-codec-replay.ps1').read_bytes().replace(b'\r\n',b'\n');self.assertEqual(m.record(body),{'bytes':35342,'sha256':'195f7ebb732729382478660a15de94cff14b630778925629e7ccdb820110cb69'});self.assertEqual(body.count(b'/p:PlatformToolset=v145'),1);self.assertEqual(m.record(body.replace(b'/p:PlatformToolset=v145',b'/p:PlatformToolset=v180').split(b'\n',1)[1]),ORIGINAL_PS_BODY)
  self.assertEqual(m.record((R/'scripts/fixtures/mp3-codec-origin.c').read_bytes().replace(b'\r\n',b'\n').split(b'#include',1)[1]),ORIGINAL_C_BODY)
  profile=copy.deepcopy(m.policy());profile.pop('build_recipe_license');profile.pop('scope');profile['adaptations'].pop();profile['licensing_boundary'].pop('project_orchestration');profile['cli_child']['owned_primitive'].pop('license');self.assertEqual(m.sha(m.canonical(profile)),ORIGINAL_FUNCTIONAL_PROFILE)
  for name in m.DEPENDENCY_INPUTS+(m.base.BSD_GRANT,m.policy()['lame_variant']['patch']['path']):self.assertIn(BASELINE['files'].get(name,{'bytes':1295,'sha256':'018f5857359aee56d54fa84e0e87118d15c56b2e4e19f44389bafc6ea7d4f293'}),(m.record((R/name).read_bytes()),m.record((R/name).read_bytes().replace(b'\r\n',b'\n'))))
 def test_final_copy_inventory_separates_raw_and_LF_without_expanding_grant(self):
  files={n:b.replace(b'\r\n',b'\n') for n,b in m.project_bytes().items()};a=m.mp3_copy_inventory(files,m.policy());win={n:b if n in (m.MP3_GRANT,m.base.BSD_GRANT,m.base.VARIANT_PATCH,m.policy()['lame_variant']['patch']['path']) else b.replace(b'\n',b'\r\n') for n,b in files.items()};b=m.mp3_copy_inventory(win,m.policy());self.assertEqual(set(a['copies']),set(m.MP3_APPROVED_BASELINES));self.assertEqual(a['approved_baselines'],m.MP3_APPROVED_BASELINES);self.assertEqual(a['supplemental_approved_baselines'],SUPPLEMENTAL_BASELINES);self.assertEqual(a['schema'],'proxy-r19-mp3-final-bsd-copies-v2')
  for n in a['copies']:
   with self.subTest(path=n):self.assertEqual(a['copies'][n]['canonical_lf'],b['copies'][n]['canonical_lf']);self.assertNotEqual(a['copies'][n]['raw'],b['copies'][n]['raw'])
  for name in ('source_delivery_approved','runtime_collection_allowed','production_execution_allowed','r19_complete'):self.assertIs(a[name],False)
  for bad in (dict(files,**{m.MP3_GRANT:files[m.MP3_GRANT]+b'changed'}),dict(files,**{'scripts/replay-mp3-codec.py':b'bad\rtext'})):
   with self.assertRaises(ValueError):m.mp3_copy_inventory(bad,m.policy())
 def test_toy_source_kit_strict_notices_copies_and_unknown_member_before_read(self):
  # One inert authored supplier text, no real archive source preparation.
  p={'sources':[{'filename':'authored-source.txt','bytes':8,'sha256':m.sha(b'authored')}],'original_recipes':[],'build_recipe_license':m.MP3_PROJECT_LICENSE};files=m.project_bytes()
  with tempfile.TemporaryDirectory() as name:
   kit=Path(name).resolve();(kit/'original-inputs').mkdir();(kit/'original-inputs/authored-source.txt').write_bytes(b'authored')
   for n,b in files.items():dest=kit/'project-orchestration'/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
   data={'BASE-BSD-COPIES.json':m.base.bsd_copy_inventory({n:files[n] for n in m.base.PROJECT_INPUTS},m.base.policy()),'FUNCTIONAL-LICENSE-BOUNDARY.json':m.license_boundary(),'MP3-BSD-COPIES.json':m.mp3_copy_inventory(files,p)}
   for n,d in data.items():m.write(kit/n,d)
   m.verify_source_kit(kit,p,files)
   for leaf,mutate in [('MP3-BSD-COPIES.json',lambda d:d['copies']['scripts/replay-mp3-codec.py']['raw'].update(bytes=1)),('MP3-BSD-COPIES.json',lambda d:d.update(production_execution_allowed=0)),('FUNCTIONAL-LICENSE-BOUNDARY.json',lambda d:d['additional_original_mp3_grant'].update(identifier='MIT'))]:
    bad=copy.deepcopy(data[leaf]);mutate(bad);m.write(kit/leaf,bad)
    with self.subTest(leaf=leaf),self.assertRaises(ValueError):m.verify_source_kit(kit,p,files)
    m.write(kit/leaf,data[leaf])
   notice=kit/'project-orchestration'/m.MP3_GRANT;notice.write_bytes(b'tampered')
   with self.assertRaises(ValueError):m.verify_source_kit(kit,p,files)
   notice.write_bytes(files[m.MP3_GRANT]);unknown=kit/'private-extra';unknown.write_bytes(b'private');ls=Path.lstat;op=Path.open
   def no_stat(path,*a,**kw):
    if path==unknown:raise AssertionError('Unknown member metadata read')
    return ls(path,*a,**kw)
   def no_open(path,*a,**kw):
    if path==unknown:raise AssertionError('Unknown member contents read')
    return op(path,*a,**kw)
   with patch.object(Path,'lstat',no_stat),patch.object(Path,'open',no_open),self.assertRaises(ValueError):m.verify_source_kit(kit,p,files)

if __name__=='__main__':unittest.main()
