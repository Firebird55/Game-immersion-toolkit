"""Authored trust/publication fixtures; not actual FFmpeg/Windows acceptance."""
import importlib.util
from contextlib import contextmanager, ExitStack
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

# Original FFmpeg 9.0.2 makedef fixture, including its complete ISC-style notice.
# Runs only against authored shell stubs; never an actual compiler/library tool.
ORIGINAL_MAKEDEF = rb'''#!/bin/sh

# Copyright (c) 2013, Derek Buitenhuis
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

# mktemp isn't POSIX, so supply an implementation
mktemp() {
    echo "${2%%XXX*}.${HOSTNAME}.${UID}.$$"
}

if [ $# -lt 2 ]; then
    echo "Usage: makedef <version_script> <objects>" >&2
    exit 0
fi

vscript=$1
shift

if [ ! -f "$vscript" ]; then
    echo "Version script does not exist" >&2
    exit 1
fi

for object in "$@"; do
    case "$object" in
    @*)
        object="${object#@}"
        ;;
    esac
    if [ ! -f "$object" ]; then
        echo "Object does not exist: ${object}" >&2
        exit 1
    fi
done

# Create a lib temporarily to dump symbols from.
# It's just much easier to do it this way
libname=$(mktemp -u "library").lib

trap 'rm -f -- $libname' EXIT

if [ -n "$AR" ]; then
    $AR rcs ${libname} $@ >/dev/null
else
    machine_flag=""
    case "$LDFLAGS" in
    *"machine:arm64ec"*)
        machine_flag="-machine:arm64ec"
        ;;
    esac
    lib.exe ${machine_flag} -out:${libname} $@ >/dev/null
fi
if [ $? != 0 ]; then
    echo "Could not create temporary library." >&2
    exit 1
fi

IFS='
'

prefix="$EXTERN_PREFIX"

started=0
regex="none"

for line in $(cat ${vscript} | tr '\t' ' '); do
    # We only care about global symbols
    echo "${line}" | grep -q '^ \+global:'
    if [ $? = 0 ]; then
        started=1
        line=$(echo "${line}" | sed -e 's/^ \{1,\}global: *//')
    else
        echo "${line}" | grep -q '^ \+local:'
        if [ $? = 0 ]; then
            started=0
        fi
    fi

    if [ ${started} = 0 ]; then
        continue
    fi

    # Handle multiple symbols on one line
    IFS=';'

    # Work around stupid expansion to filenames
    line=$(echo "${line}" | sed -e 's/\*/.\\+/g')
    for exp in ${line}; do
        # Remove leading and trailing whitespace
        exp=$(echo "${exp}" | sed -e 's/^ *//' -e 's/ *$//')

        if [ "${regex}" = "none" ]; then
            regex="${exp}"
        else
            regex="${regex};${exp}"
        fi
    done

    IFS='
'
done

if [ -n "$NM" ]; then
    # Use eval, since NM="nm -g"
    dump=$(eval "$NM --defined-only -g ${libname}" |
              grep -v : |
              grep -v ^$ |
              cut -d' ' -f3 |
              sed -e "s/^${prefix}//" -e "s/^#//" |
              grep -v '\$entry_thunk' |
              grep -v '\$exit_thunk')
else
    member=1
    case "$LDFLAGS" in
    *"machine:arm64ec"*)
        member=32
        ;;
    esac
    dump=$(dumpbin.exe -linkermember:${member} ${libname} |
              sed -e '/public symbols/,$!d' -e '/^ \{1,\}Summary/,$d' -e 's/^[[:space:]]*[0-9A-Fa-f]\{1,\}[[:space:]]\{1,\}//' -e "s/^${prefix}//" -e 's/^#//' |
              tail -n +2 |
              grep -v '\$entry_thunk' |
              grep -v '\$exit_thunk')
fi

rm ${libname}

IFS=';'
list=""
for exp in ${regex}; do
    list="${list}"'
'$(echo "${dump}" |
          grep "^${exp}" |
          sed -e 's/^/    /')
done

echo "EXPORTS"
echo "${list}" | sort | uniq | tail -n +2
'''

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('game_codec_replay', ROOT / 'scripts/replay-game-codec.py')
replay = importlib.util.module_from_spec(spec); spec.loader.exec_module(replay)


class ReplayTrustTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.inputs = self.root / 'inputs'; self.inputs.mkdir()
        self.project = self.root / 'project'; self.project.mkdir()
        for name in replay.PROJECT_INPUTS:
            path = self.project / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('authored project fixture')

    def fixture(self, extra=None, source_bytes=b'authored source', notice=b'original authored notice'):
        archive = self.inputs / 'owned.tar.xz'
        with tarfile.open(archive, 'w:xz') as tar:
            for name, raw in [('owned-1/COPYING', notice), ('owned-1/own.c', source_bytes)]:
                entry = tarfile.TarInfo(name); entry.size = len(raw); tar.addfile(entry, io.BytesIO(raw))
            if extra: tar.addfile(extra)
        options = b'# Original authored options\n--disable-everything\n--enable-libopus\n'
        (self.inputs / 'vgmstream-ffmpeg_options.txt').write_bytes(options)
        pin = {'sources': [{'component': 'owned', 'root': 'owned-1', 'filename': archive.name,
                           'sha256': replay.digest(archive.read_bytes())}],
            'original_recipes': [{'filename': 'vgmstream-ffmpeg_options.txt', 'path': 'options',
                                  'download': 'https://example.invalid/original', 'sha256': replay.digest(options)}],
            'notices': [{'component': 'owned', 'path': 'COPYING', 'sha256': replay.digest(b'original authored notice')}],
            'build_tools': [], 'adaptations': ['authored fixture only'], 'licensing_boundary': {'approved': False}}
        return pin

    def prepare(self, pin, output):
        with patch.object(replay, 'policy', return_value=pin), patch.object(replay, 'ROOT', self.project):
            replay.prepare(self.inputs, output)

    def diagnostic_fixture(self):
        pin = self.fixture(); variant = json.loads(json.dumps(replay.policy()['diagnostic_variant']))
        variant['source_member'] = 'owned-1/compat/windows/makedef'
        patch_bytes = (ROOT / replay.VARIANT_PATCH).read_bytes()
        (self.project / replay.VARIANT_PATCH).write_bytes(patch_bytes)
        modified = replay.instrument_makedef(ORIGINAL_MAKEDEF, patch_bytes, variant)
        members = {'owned-1/COPYING': b'original authored notice', 'owned-1/own.c': b'authored source',
                   variant['source_member']: ORIGINAL_MAKEDEF}
        with tarfile.open(self.inputs / 'owned.tar.xz', 'w:xz') as tar:
            for name, raw in members.items():
                entry = tarfile.TarInfo(name); entry.size = len(raw); tar.addfile(entry, io.BytesIO(raw))
        pin['sources'][0].update(component='ffmpeg', bytes=(self.inputs / 'owned.tar.xz').stat().st_size,
            sha256=replay.digest((self.inputs / 'owned.tar.xz').read_bytes()))
        for record in pin['original_recipes']: record['bytes'] = (self.inputs / record['filename']).stat().st_size
        pin['notices'][0]['component'] = 'ffmpeg'
        before = {name: {'bytes': len(raw), 'sha256': replay.digest(raw)} for name, raw in members.items()}
        variant['original_tree'] = replay.tree_identity(before)
        before[variant['source_member']] = {'bytes': len(modified), 'sha256': replay.digest(modified)}
        variant['modified_tree'] = replay.tree_identity(before)
        pin['diagnostic_variant'] = variant
        return pin, modified

    def diagnostic_observation(self, pin, output):
        with patch.object(replay, 'policy', return_value=pin), patch.object(replay, 'ROOT', self.project):
            return replay.makedef_diagnostics(output)

    @contextmanager
    def forbid_link_descendant_access(self, boundary):
        counts = {name: 0 for name in ('stat', 'lstat', 'open', 'iterdir', 'scandir', 'listdir')}
        def guarded(name, original):
            def call(path, *args, **kwargs):
                value = Path(path).absolute() if not isinstance(path, int) else None
                nofollow_boundary = name == 'lstat' or name == 'stat' and kwargs.get('follow_symlinks') is False
                if value is not None and (boundary in value.parents or value == boundary and not nofollow_boundary):
                    counts[name] += 1
                    raise AssertionError('Linked descendant metadata/content/enumeration must not be accessed.')
                return original(path, *args, **kwargs)
            return call
        with ExitStack() as stack:
            for name in ('stat', 'lstat', 'open', 'iterdir'):
                stack.enter_context(patch.object(Path, name, guarded(name, getattr(Path, name))))
            for name in ('scandir', 'listdir'):
                stack.enter_context(patch.object(os, name, guarded(name, getattr(os, name))))
            yield counts
        self.assertEqual(counts, dict.fromkeys(counts, 0))

    def test_parent_symlink_refuses_before_descendant_stat_lstat_open_or_enumeration(self):
        outside = self.root / 'outside'; outside.mkdir(); (outside / 'stdout.log').write_bytes(b'private sentinel')
        link = self.root / 'linked-parent'
        try: link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError): self.skipTest('Authored directory symlink unavailable on this host')
        with self.forbid_link_descendant_access(link):
            for action in (lambda: replay.no_links(link / 'stdout.log'),
                    lambda: replay.bound_bytes(link / 'stdout.log', {'bytes': 16, 'sha256': 'a'*64}),
                    lambda: replay.inventory(link), lambda: replay.inventory(self.root)):
                with self.assertRaises(ValueError): action()
        pin, _ = self.diagnostic_fixture(); output = self.root / 'variant'; self.prepare(pin, output)
        parent = output / 'ffmpeg-build'; parent.symlink_to(outside, target_is_directory=True)
        with self.forbid_link_descendant_access(parent):
            report = self.diagnostic_observation(pin, output)
        self.assertEqual(report['status'], 'unavailable'); self.assertEqual(report['reason'], 'source-binding')
        self.assertNotIn('outside', json.dumps(report))

    def test_windows_reparse_attribute_refuses_before_any_descendant_access(self):
        parent = self.root / 'authored-reparse'; parent.mkdir(); (parent / 'stdout.log').write_bytes(b'private sentinel')
        original = Path.lstat
        def reparse(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == parent: return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info
        with patch.object(Path, 'lstat', reparse), self.forbid_link_descendant_access(parent):
            for action in (lambda: replay.no_links(parent / 'stdout.log'),
                    lambda: replay.bound_bytes(parent / 'stdout.log', {'bytes': 16, 'sha256': 'a'*64}),
                    lambda: replay.inventory(parent), lambda: replay.inventory(self.root)):
                with self.assertRaises(ValueError): action()

    def test_missing_output_suffix_stops_metadata_walk_and_preserves_fresh_prepare_and_acquire(self):
        missing = self.root / 'fresh-parent'
        with self.forbid_link_descendant_access(missing):
            self.assertIsNone(replay.no_links(missing / 'child' / 'leaf'))
        pin = self.fixture(); output = missing / 'prepared'; self.prepare(pin, output)
        self.assertTrue((output / 'upstream/owned-1/own.c').is_file())
        acquired = self.root / 'fresh-acquire-parent' / 'inputs'
        with patch.object(replay, 'policy', return_value={'sources': [], 'original_recipes': [], 'build_tools': []}):
            replay.acquire(acquired)  # Empty authored input set; no network access.
        self.assertTrue(acquired.is_dir())

    def test_config_branch_stdout_and_bound_inputs_require_regular_files_before_open(self):
        pin, _ = self.diagnostic_fixture(); output = self.root / 'variant'; self.prepare(pin, output)
        config = output / 'ffmpeg-build/ffbuild/config.mak'; config.parent.mkdir(parents=True)
        config.write_bytes(b'RESPONSE_FILES=yes\n')
        role = output / 'PRIVATE-MAKEDEF/avutil'; role.mkdir()
        branch = role / 'branch-state'; branch.write_bytes(b'empty\n')
        stdout = role / 'stdout.log'; stdout.write_bytes(b'authored stdout')
        original_open = Path.open
        for target in (config, branch, stdout):
            for kind in ('directory', 'fifo') if hasattr(os, 'mkfifo') else ('directory',):
                with self.subTest(input=target.name, kind=kind):
                    prior = target.read_bytes(); target.unlink()
                    if kind == 'directory': target.mkdir()
                    else: os.mkfifo(target)
                    def no_open(path, *args, **kwargs):
                        if path == target: raise AssertionError('Non-regular diagnostic input must not be opened.')
                        return original_open(path, *args, **kwargs)
                    with patch.object(Path, 'open', no_open):
                        with self.assertRaises(ValueError): replay.bound_bytes(target, {'bytes': 1, 'sha256': 'a'*64})
                        report = self.diagnostic_observation(pin, output)
                    self.assertEqual(report['status'], 'unavailable')
                    self.assertFalse(report['r19_complete']); self.assertEqual(report['components'], [])
                    if kind == 'directory': target.rmdir()
                    else: target.unlink()
                    target.write_bytes(prior)

    def makedef_shell_fixture(self):
        pin, modified = self.diagnostic_fixture()
        original = self.root / 'original-makedef'; original.write_bytes(ORIGINAL_MAKEDEF)
        instrumented = self.root / 'instrumented-makedef'; instrumented.write_bytes(modified)
        tools = self.root / 'authored-shell-tools'; tools.mkdir()
        library = tools / 'lib.exe'
        library.write_text('''#!/bin/sh
printf '%s\\n' "$@" >"$R19_TEST_ARGS"
for argument; do
    case "$argument" in -out:*) output=${argument#-out:} ;; esac
done
printf 'authored library bytes' >"$output"
cat "$output" >"$R19_TEST_EFFECT"
printf 'LIB : fatal error LNK1104: private-object --private-argv\\n'
exit "$R19_TEST_EXIT"
''')
        dump = tools / 'dumpbin.exe'
        dump.write_text("#!/bin/sh\nprintf '1 public symbols\\n  1 owned_export\\n   Summary\\n'\n")
        library.chmod(0o755); dump.chmod(0o755)
        for role in replay.MAKEDEF_ROLES:
            version = self.root / ('lib' + role) / ('lib' + role + '.ver')
            version.parent.mkdir(); version.write_text('VERSION {\n    global: owned_export;\n    local: *;\n};\n')
        (self.root / 'owned.rsp').write_text('authored-object.o\n')
        private = self.root / 'PRIVATE-MAKEDEF'; private.mkdir()
        environment = dict(os.environ)
        for name in ('AR', 'NM', 'LDFLAGS', 'EXTERN_PREFIX', 'ENV', 'BASH_ENV'):
            environment.pop(name, None)
        environment.update(PATH=str(tools) + os.pathsep + environment.get('PATH', ''),
            R19_MAKEDEF_LOG_ROOT=private.as_posix(), R19_TEST_EXIT='0',
            R19_TEST_ARGS=(self.root / 'arguments').as_posix(),
            R19_TEST_EFFECT=(self.root / 'effect').as_posix(),
            R19_TEST_ORIGINAL=original.as_posix(), R19_TEST_INSTRUMENTED=instrumented.as_posix())
        return pin, instrumented, private, environment

    @unittest.skipUnless(shutil.which('sh'), 'Authored original/variant shell behavior requires a POSIX shell')
    def test_original_and_instrumented_makedef_have_identical_lib_argv_exit_and_library_effects(self):
        _, _, private, environment = self.makedef_shell_fixture()
        harness = '''
(
    export R19_TEST_ARGS="$R19_TEST_BASE_ARGS" R19_TEST_EFFECT="$R19_TEST_BASE_EFFECT"
    set -- libavutil/libavutil.ver @owned.rsp
    . "$R19_TEST_ORIGINAL"
) >baseline.def 2>baseline.err
original_status=$?
(
    export R19_TEST_ARGS="$R19_TEST_VARIANT_ARGS" R19_TEST_EFFECT="$R19_TEST_VARIANT_EFFECT"
    set -- libavutil/libavutil.ver @owned.rsp
    . "$R19_TEST_INSTRUMENTED"
) >variant.def 2>variant.err
variant_status=$?
printf '%s %s\\n' "$original_status" "$variant_status"
'''
        for exit_code, expected in ((0, b'0 0\n'), (7, b'1 1\n')):
            with self.subTest(authored_library_exit=exit_code):
                environment.update(R19_TEST_EXIT=str(exit_code),
                    R19_TEST_BASE_ARGS=(self.root / 'baseline.args').as_posix(),
                    R19_TEST_VARIANT_ARGS=(self.root / 'variant.args').as_posix(),
                    R19_TEST_BASE_EFFECT=(self.root / 'baseline.effect').as_posix(),
                    R19_TEST_VARIANT_EFFECT=(self.root / 'variant.effect').as_posix())
                result = subprocess.run([shutil.which('sh'), '-c', harness], cwd=self.root,
                    env=environment, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0); self.assertEqual(result.stdout.replace(b'\r\n', b'\n'), expected)
                self.assertEqual((self.root / 'baseline.args').read_bytes(), (self.root / 'variant.args').read_bytes())
                self.assertEqual((self.root / 'baseline.effect').read_bytes(), (self.root / 'variant.effect').read_bytes())
                self.assertEqual((self.root / 'baseline.def').read_bytes(), (self.root / 'variant.def').read_bytes())
                self.assertEqual((self.root / 'baseline.err').read_bytes(), (self.root / 'variant.err').read_bytes())
                self.assertEqual(list(self.root.glob('*.lib')), [])  # Original EXIT cleanup still ran.
                self.assertIn(b'LNK1104', (private / 'avutil/stdout.log').read_bytes())
                self.assertEqual((private / 'avutil/branch-state').read_bytes(), b'empty\n')
                shutil.rmtree(private / 'avutil')

    @unittest.skipUnless(shutil.which('sh'), 'Authored concurrent/guard shell behavior requires a POSIX shell')
    def test_instrumented_makedef_owns_roles_atomically_and_refuses_duplicate_unknown_or_nonempty_ar(self):
        _, instrumented, private, environment = self.makedef_shell_fixture()
        from concurrent.futures import ThreadPoolExecutor
        def invoke(role, env):
            return subprocess.run([shutil.which('sh'), str(instrumented),
                'lib' + role + '/lib' + role + '.ver', '@owned.rsp'],
                cwd=self.root, env=env, capture_output=True, timeout=10)
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = []
            for role in replay.MAKEDEF_ROLES:
                env = dict(environment, R19_TEST_ARGS=(self.root / (role + '.args')).as_posix(),
                           R19_TEST_EFFECT=(self.root / (role + '.effect')).as_posix())
                jobs.append(pool.submit(invoke, role, env))
            self.assertEqual([job.result().returncode for job in jobs], [0, 0, 0, 0])
        for role in replay.MAKEDEF_ROLES:
            self.assertEqual((private / role / 'branch-state').read_bytes(), b'empty\n')
            self.assertIn(b'LNK1104', (private / role / 'stdout.log').read_bytes())
        shutil.rmtree(private / 'avutil')
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(invoke, 'avutil', environment) for _ in range(2)]
            self.assertEqual(sorted(job.result().returncode for job in jobs), [0, 1])
        before = (private / 'avutil/stdout.log').read_bytes()
        self.assertEqual(invoke('avutil', environment).returncode, 1)
        self.assertTrue((private / 'unavailable-duplicate-role').is_dir())
        self.assertEqual((private / 'avutil/stdout.log').read_bytes(), before)
        unknown = self.root / 'libprivate-source'; unknown.mkdir(); (unknown / 'libprivate-source.ver').write_text('authored')
        self.assertEqual(invoke('private-source', environment).returncode, 1)
        self.assertTrue((private / 'unavailable-unknown-role').is_dir())
        shutil.rmtree(private / 'avutil')
        self.assertEqual(invoke('avutil', dict(environment, AR='private-tool-name --private-argument')).returncode, 1)
        self.assertEqual((private / 'avutil/branch-state').read_bytes(), b'nonempty\n')
        self.assertFalse((private / 'avutil/stdout.log').exists())
        self.assertEqual(list(self.root.glob('*.lib')), [])

    def test_exact_diagnostic_variant_retains_original_script_notice_archive_and_both_source_identities(self):
        pin, modified = self.diagnostic_fixture(); output = self.root / 'variant'; self.prepare(pin, output)
        kit = output / 'source-review'
        self.assertEqual((kit / 'diagnostic-variant/ORIGINAL-makedef').read_bytes(), ORIGINAL_MAKEDEF)
        self.assertEqual((kit / 'diagnostic-variant/MODIFIED-makedef').read_bytes(), modified)
        self.assertEqual((kit / 'original-inputs/owned.tar.xz').read_bytes(), (self.inputs / 'owned.tar.xz').read_bytes())
        self.assertTrue(modified.startswith(ORIGINAL_MAKEDEF.split(b'# mktemp')[0]))
        self.assertEqual((output / 'upstream' / pin['diagnostic_variant']['source_member']).read_bytes(), modified)
        self.assertEqual(replay.tree_identity(json.loads((output / 'ORIGINAL-SOURCE.json').read_text())),
                         pin['diagnostic_variant']['original_tree'])
        self.assertEqual(replay.tree_identity(json.loads((output / 'PREPARED-SOURCE.json').read_text())),
                         pin['diagnostic_variant']['modified_tree'])
        receipt = json.loads((kit / 'DIAGNOSTIC-VARIANT.json').read_text())
        self.assertEqual(receipt, replay.variant_receipt(pin)); self.assertIn('diagnostic-makedef-', receipt['identity'])
        self.assertFalse(receipt['source_delivery_approved']); self.assertFalse(receipt['runtime_collection_allowed'])
        self.assertFalse(receipt['r19_complete']); self.assertIn(replay.VARIANT_PATCH, replay.PROJECT_INPUTS)
        with patch.object(replay, 'policy', return_value=pin), patch.object(replay, 'ROOT', self.project):
            replay.verify_sources(output)
        for relative in ('upstream/owned-1/own.c', 'source-review/original-inputs/owned.tar.xz',
                         'source-review/project-orchestration/' + replay.VARIANT_PATCH,
                         'source-review/diagnostic-variant/ORIGINAL-makedef',
                         'source-review/diagnostic-variant/MODIFIED-makedef', 'DIAGNOSTIC-VARIANT.json',
                         'ORIGINAL-SOURCE.json', 'PREPARED-SOURCE.json'):
            path = output / relative; before = path.read_bytes(); path.write_bytes(before + b'changed')
            with patch.object(replay, 'policy', return_value=pin), patch.object(replay, 'ROOT', self.project), self.assertRaises(ValueError):
                replay.verify_sources(output)
            path.write_bytes(before)
        self.assertFalse((output / 'source-review.zip').exists())
        self.assertFalse((output / 'REPLAY-RECEIPT.json').exists())

    def test_diagnostic_patch_preimage_patch_postimage_and_hunk_changes_never_fall_back(self):
        pin, _ = self.diagnostic_fixture(); original = ORIGINAL_MAKEDEF
        exact_patch = (self.project / replay.VARIANT_PATCH).read_bytes()
        for case in ('preimage', 'patch', 'postimage', 'malformed-hunk', 'unsupported-file'):
            with self.subTest(case=case):
                variant = json.loads(json.dumps(pin['diagnostic_variant'])); raw = exact_patch
                source = original + b'changed' if case == 'preimage' else original
                if case == 'patch': raw += b'changed'
                if case == 'postimage': variant['postimage']['sha256'] = 'a'*64
                if case == 'malformed-hunk': raw = raw.replace(b'@@ ', b'@@ invalid ', 1)
                if case == 'unsupported-file': raw = raw.replace(b'a/compat/windows/makedef', b'a/private-source', 1)
                if case in ('malformed-hunk', 'unsupported-file'):
                    variant['patch'].update(bytes=len(raw), sha256=replay.digest(raw))
                with self.assertRaises(ValueError): replay.instrument_makedef(source, raw, variant)
        pin['diagnostic_variant']['patch']['sha256'] = 'a'*64
        output = self.root / 'rejected'
        with self.assertRaises(ValueError): self.prepare(pin, output)
        self.assertFalse(output.exists())

    def test_private_makedef_projection_is_source_bound_bounded_and_has_only_fixed_roles_and_codes(self):
        pin, _ = self.diagnostic_fixture(); output = self.root / 'variant'; self.prepare(pin, output)
        config = output / 'ffmpeg-build/ffbuild/config.mak'; config.parent.mkdir(parents=True)
        config.write_bytes(b'RESPONSE_FILES=yes\n')
        role = output / 'PRIVATE-MAKEDEF/avutil'; role.mkdir()
        (role / 'branch-state').write_bytes(b'empty\n')
        raw = b'LIB : fatal error LNK1104: C:\\private-profile\\object-name --private-argv\nerror LNK9999: private-model\n'
        (role / 'stdout.log').write_bytes(raw)
        report = self.diagnostic_observation(pin, output)
        self.assertEqual(report['status'], 'observed-noncausal'); self.assertEqual(report['response_files'], 'yes')
        self.assertEqual(report['archiver_environment'], 'empty')
        self.assertEqual(report['components'], [{'role': 'avutil', 'archiver_environment': 'empty',
            'diagnostic_codes': ['LNK1104'], 'diagnostic_categories': ['linker-error', 'unclassified-linker-code']}])
        for marker in ('private-profile', 'object-name', 'private-argv', 'private-model', 'LNK9999', replay.digest(raw), str(output)):
            self.assertNotIn(marker, json.dumps(report))
        private_log = output / 'PRIVATE-BUILD.log'; private_log.write_bytes(b'Could not create temporary library.\n')
        with patch.object(replay, 'policy', return_value=pin), patch.object(replay, 'ROOT', self.project):
            failure = replay.failure(output, 'build-ffmpeg', 2, private_log, 0, include_makedef=True)
        self.assertEqual(failure['makedef_diagnostics'], report); self.assertEqual(failure['status'], 'failed')
        self.assertFalse(failure['r19_complete']); self.assertFalse(failure['production_execution_allowed'])
        for case, expected in (('unknown', 'unexpected-layout'), ('duplicate', 'duplicate-role'),
                ('nonempty', 'nonempty-ar'), ('malformed-branch', 'unsupported-branch'),
                ('oversize', 'oversized-input'), ('response', 'unsupported-response-files'), ('duplicate-response', 'unsupported-response-files')):
            with self.subTest(case=case):
                extra = None
                if case in ('unknown', 'duplicate'):
                    extra = output / 'PRIVATE-MAKEDEF' / ('private-path-secret' if case == 'unknown' else 'unavailable-duplicate-role')
                    extra.mkdir()
                if case == 'nonempty': (role / 'branch-state').write_bytes(b'nonempty\n')
                if case == 'malformed-branch': (role / 'branch-state').write_bytes(b'empty\nprivate-path')
                if case == 'oversize': (role / 'stdout.log').write_bytes(b'x' * (2*1024*1024+1))
                if case == 'response': config.write_bytes(b'RESPONSE_FILES=yes private-path\n')
                if case == 'duplicate-response': config.write_bytes(b'RESPONSE_FILES=yes\nRESPONSE_FILES=no\n')
                refused = self.diagnostic_observation(pin, output)
                self.assertEqual(refused['status'], 'unavailable'); self.assertEqual(refused['reason'], expected)
                self.assertEqual(refused['components'], [])
                if case == 'nonempty': self.assertEqual(refused['archiver_environment'], 'nonempty')
                self.assertNotIn('private-path', json.dumps(refused)); self.assertFalse(refused['r19_complete'])
                if extra: extra.rmdir()
                (role / 'branch-state').write_bytes(b'empty\n'); (role / 'stdout.log').write_bytes(raw)
                config.write_bytes(b'RESPONSE_FILES=yes\n')
        with patch.object(replay, 'verify_sources', side_effect=OSError('private exception C:\\profile-secret')):
            refused = replay.makedef_diagnostics(output)
        self.assertEqual(refused['reason'], 'source-binding'); self.assertNotIn('profile-secret', json.dumps(refused))
        self.assertFalse((output / 'REPLAY-RECEIPT.json').exists())

    def test_exact_originals_and_notices_retained_without_binary_or_source_approval(self):
        pin = self.fixture(); output = self.root / 'experiment'; self.prepare(pin, output)
        self.assertEqual((output / 'upstream/owned-1/own.c').read_bytes(), b'authored source')
        self.assertEqual((output / 'source-review/original-inputs/owned.tar.xz').read_bytes(),
                         (self.inputs / 'owned.tar.xz').read_bytes())
        boundary = json.loads((output / 'source-review/BOUNDARY.json').read_text())
        self.assertFalse(boundary['source_delivery_approved']); self.assertFalse(boundary['runtime_collection_allowed'])
        self.assertEqual(json.loads((output / 'ORIGINAL-OPTIONS.json').read_text()),
                         ['--disable-everything', '--enable-libopus'])
        with patch.object(replay, 'policy', return_value=pin): replay.verify_sources(output)
        (output / 'upstream/owned-1/own.c').write_bytes(b'changed')
        with patch.object(replay, 'policy', return_value=pin), self.assertRaisesRegex(ValueError, 'changed the original'):
            replay.verify_sources(output)

    def test_changed_input_notice_or_existing_output_never_overwritten(self):
        for changed in ('hash', 'notice', 'existing'):
            with self.subTest(changed=changed):
                pin = self.fixture(notice=b'damaged' if changed == 'notice' else b'original authored notice')
                output = self.root / ('experiment-' + changed)
                if changed == 'hash': (self.inputs / 'owned.tar.xz').write_bytes(b'wrong')
                if changed == 'existing': output.mkdir(); (output / 'prior').write_bytes(b'preserved')
                with self.assertRaises(ValueError): self.prepare(pin, output)
                if changed == 'existing': self.assertEqual((output / 'prior').read_bytes(), b'preserved')
                else: self.assertFalse(output.exists())

    def test_links_traversal_native_aliases_and_devices_reject_before_output(self):
        for kind in ('traversal', 'symlink', 'hardlink', 'alias', 'native', 'device'):
            with self.subTest(kind=kind):
                entry = tarfile.TarInfo({'traversal': '../outside', 'alias': 'owned-1/copying',
                    'native': 'owned-1/prebuilt.dll'}.get(kind, 'owned-1/other'))
                if kind in ('symlink', 'hardlink'):
                    entry.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
                    entry.linkname = '../../outside'
                if kind == 'device': entry.type = tarfile.CHRTYPE
                pin = self.fixture(extra=entry); output = self.root / ('experiment-' + kind)
                with self.assertRaises(ValueError): self.prepare(pin, output)
                self.assertFalse(output.exists())

    def test_no_unreviewed_licensing_or_protocol_configuration_changes(self):
        output = self.root / 'experiment'; self.prepare(self.fixture(), output)
        exact = '--disable-everything --enable-libopus --target-os=win64 --toolchain=msvc --arch=x86_64 --prefix=/c/r19-game-codec-replay/out/ffmpeg-vs-64'
        replay.validate_configuration(output, exact)
        for change in (' --enable-gpl', ' --enable-protocol=file', ' --enable-ffmpeg', ' --enable-version3'):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay.validate_configuration(output, exact + change)
        with self.assertRaises(ValueError): replay.original_options(b'--enable-libopus\n--enable-gpl')
        with self.assertRaises(ValueError): replay.original_options(b'--enable-libopus; touch injected')

    def test_decode_failure_partial_pcm_and_deadline_retain_previous_output_and_cleanup(self):
        output = self.root / 'complete.pcm'; output.write_bytes(b'previous')
        def failed(pending): pending.write_bytes(b'partial'); return SimpleNamespace(returncode=1)
        def wrong(pending): pending.write_bytes(b'partial'); return SimpleNamespace(returncode=0)
        def timeout(pending):
            pending.write_bytes(b'partial')
            raise replay.subprocess.TimeoutExpired('authored-child', 1)
        for run, exception in ((failed, ValueError), (wrong, ValueError), (timeout, replay.subprocess.TimeoutExpired)):
            with self.subTest(run=run.__name__), self.assertRaises(exception):
                replay.publish_attempt(run, self.root, output, b'complete')
            self.assertEqual(output.read_bytes(), b'previous')
            self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['complete.pcm', 'inputs', 'project'])
        def success(pending): pending.write_bytes(b'complete'); return SimpleNamespace(returncode=0)
        replay.publish_attempt(success, self.root, output, b'complete')
        self.assertEqual(output.read_bytes(), b'complete')

    def test_module_observation_rejects_foreign_and_ambiguous_paths_without_leaking_them(self):
        candidate = self.root / 'candidate'; candidate.mkdir()
        lines = []
        for name in replay.DLLS:
            (candidate / name).write_bytes(b'owned DLL fixture')
            lines.append('module\t' + name + '\t' + str(candidate / name))
        result = replay.sanitized_modules(lines, candidate)
        self.assertEqual(set(result), set(replay.DLLS))
        self.assertNotIn(str(self.root), json.dumps(result))
        for bad in (lines[:-1], lines + lines[:1], [lines[0].replace(str(candidate), str(self.root / 'private-profile'))] + lines[1:]):
            with self.assertRaises(ValueError) as error: replay.sanitized_modules(bad, candidate)
            self.assertNotIn(str(self.root), str(error.exception))

    def test_authored_pe_normal_and_delay_imports_and_malformed_inputs(self):
        raw = bytearray(2048); raw[:2] = b'MZ'; struct.pack_into('<I', raw, 60, 128)
        raw[128:132] = b'PE\0\0'; struct.pack_into('<HH', raw, 132, 0x8664, 1)
        struct.pack_into('<H', raw, 148, 240); struct.pack_into('<H', raw, 152, 0x20b)
        struct.pack_into('<IIII', raw, 152+240+8, 1024, 4096, 1024, 512)
        struct.pack_into('<II', raw, 152+112+8, 4096, 40)
        struct.pack_into('<II', raw, 152+112+13*8, 4160, 64)
        struct.pack_into('<IIIII', raw, 512, 1, 0, 0, 4296, 0)
        struct.pack_into('<IIIIIIII', raw, 576, 1, 4328, 0, 0, 0, 0, 0, 0)
        raw[712:725] = b'KERNEL32.dll\0'; raw[744:756] = b'fixture.dll\0'
        self.assertEqual(replay.pe_imports(bytes(raw)), {'imports': ['KERNEL32.dll'], 'delay_imports': ['fixture.dll']})
        for damaged in (b'not PE', bytes(raw[:520]), bytes(raw[:152])+b'\0\0'+bytes(raw[154:])):
            with self.assertRaises(ValueError): replay.pe_imports(damaged)

    def test_failure_receipt_exposes_only_allowlisted_codes_categories_and_numeric_exit(self):
        log = self.root / 'private.log'
        private = str(self.root / 'private-user' / 'credentials-fixture')
        log.write_text(private + '\nauthored-secret-never-publish\ncompiler command --private-argument\n'
            'own.c(5): fatal error C1083: private include file ' + private + '\n'
            'LINK : error LNK2019: private symbol\nproject : error MSB8020: private toolset\n'
            'error C9999: unapproved numeric token\nwarning C2065: non-error warning\n'
            'CMake Error at ' + private + '\nCould not find a package configuration file provided by private package\n')
        with patch.dict(replay.os.environ, {'GITHUB_SHA': 'a'*40}):
            report = replay.failure(self.root, 'build-opus', -1073741515, log, 0)
        self.assertEqual(report['exit_code'], -1073741515)
        self.assertEqual(report['diagnostic_codes'], ['C1083', 'LNK2019', 'MSB8020'])
        self.assertEqual(report['diagnostic_categories'], ['cmake-error', 'cmake-package-discovery',
                         'compiler-error', 'linker-error', 'msbuild-error', 'unclassified-compiler-code'])
        self.assertEqual(report['source_commit'], 'a'*40)
        serialized = json.dumps(report)
        for marker in (private, str(self.root), 'authored-secret', '--private-argument', 'C9999', 'C2065'):
            self.assertNotIn(marker, serialized)
        self.assertEqual(json.loads((self.root / 'FAILED-STAGE.json').read_text()), report)
        self.assertEqual(report['status'], 'failed'); self.assertFalse(report['r19_complete'])
        self.assertFalse(report['runtime_collection_allowed']); self.assertFalse(report['source_delivery_approved'])
        self.assertFalse(report['production_execution_allowed']); self.assertFalse(report['raw_log_published'])
        self.assertFalse((self.root / 'REPLAY-RECEIPT.json').exists())

    def test_failure_diagnosis_excludes_prior_successful_command_and_bounds_private_log(self):
        log = self.root / 'private.log'
        earlier = (b'CMake Error at earlier private path\nfatal error C1083: earlier successful try-compile\n'
            b'cl : Command line error D8016: earlier option\nerror C9999: earlier unknown code\n'
            b'prior.asm:1: error: earlier assembly\nmake: *** [earlier-target] Error 2\n')
        log.write_bytes(earlier + b'error lnk2019: current private symbol\n')
        report = replay.failure(self.root, 'compile-probe', 1, log, len(earlier))
        self.assertEqual(report['diagnostic_codes'], ['LNK2019'])
        self.assertEqual(report['diagnostic_categories'], ['linker-error'])
        self.assertFalse(report['log_truncated'])
        log.write_bytes(earlier + b'current.asm:65: error: outside retained tail\n'
            b'error D8016: outside retained tail\nerror LNK9999: outside retained tail\n'
            + b'private padding\n'*100 + b'error C2143: current private symbol\n')
        with patch.object(replay, 'FAILURE_LOG_LIMIT', 100):
            report = replay.failure(self.root, 'compile-probe', 2, log, len(earlier))
        self.assertTrue(report['log_truncated'])
        self.assertEqual(report['diagnostic_codes'], ['C2143'])
        self.assertEqual(report['diagnostic_categories'], ['compiler-error'])

    def test_actual_two_mib_cut_never_reinterprets_partial_line_or_code_boundary(self):
        log = self.root / 'private.log'
        for prefix, fragment in ((b'prefix ', b'Object does not exist: private-marker '),
                                 (b'prefix t', b'error C1001: private-marker ')):
            with self.subTest(fragment=fragment):
                tail = fragment + b'x' * (2 * 1024 * 1024 - len(fragment))
                log.write_bytes(prefix + tail)
                with patch.object(replay, 'FAILURE_LOG_LIMIT', len(prefix + tail)):
                    whole = replay.failure(self.root, 'build-ffmpeg', 2, log, 0)
                self.assertFalse(whole['log_truncated'])
                self.assertEqual(whole['diagnostic_categories'], ['unclassified-command-failure'])
                report = replay.failure(self.root, 'build-ffmpeg', 2, log, 0)
                self.assertTrue(report['log_truncated'])
                self.assertEqual(report['diagnostic_codes'], [])
                self.assertEqual(report['diagnostic_categories'], ['unclassified-command-failure'])
                self.assertNotIn('private-marker', json.dumps(report))

    def test_truncated_fragment_discards_to_newline_without_reading_prior_phase(self):
        log = self.root / 'private.log'
        earlier = b'error C1083: earlier phase\nmake: *** [earlier-target] Error 2\n'
        current = b'error LNK2019: current private symbol\r\n'
        # A complete line at the exact command offset is retained without truncation.
        log.write_bytes(earlier + current)
        report = replay.failure(self.root, 'build-ffmpeg', 2, log, len(earlier))
        self.assertFalse(report['log_truncated'])
        self.assertEqual(report['diagnostic_codes'], ['LNK2019'])
        self.assertEqual(report['diagnostic_categories'], ['linker-error'])
        for newline in (b'\n', b'\r\n'):
            with self.subTest(newline=newline):
                fragment = b'Object does not exist: private-marker '
                padding = b'x' * (2 * 1024 * 1024 - len(fragment + newline + current))
                log.write_bytes(earlier + b'prefix ' + fragment + padding + newline + current)
                report = replay.failure(self.root, 'build-ffmpeg', 2, log, len(earlier))
                self.assertTrue(report['log_truncated'])
                self.assertEqual(report['diagnostic_codes'], ['LNK2019'])
                self.assertEqual(report['diagnostic_categories'], ['linker-error'])
                self.assertFalse(report['r19_complete'])
                self.assertNotIn('private-marker', json.dumps(report))
        self.assertFalse((self.root / 'REPLAY-RECEIPT.json').exists())

    def test_primary_make_shell_nasm_and_original_makedef_formats_publish_only_fixed_categories(self):
        private = r'C:\private-profile\source-model-secret --private-argument'
        cases = (
            ('make: *** [ffbuild/common.mak:81: ' + private + '] Error 2\n',
             ['make-fatal-error', 'make-recipe-error']),
            ('make[1]: *** [private-target] Error 127\r\n', ['make-fatal-error', 'make-recipe-error']),
            ("make: *** No rule to make target '" + private + "', needed by 'private-target'. Stop.\n",
             ['make-fatal-error', 'make-no-rule']),
            ('/bin/sh: line 1: ' + private + ': command not found\n', ['shell-command-not-found']),
            ('bash: ' + private + ': cannot execute binary file: Exec format error\n', ['shell-cannot-execute']),
            ('/usr/bin/bash: line 2: ' + private + ': cannot execute: required file not found\n', ['shell-cannot-execute']),
            ('sh: ' + private + ': Permission denied\n', ['shell-permission-denied']),
            (private + '.asm:65: error: parser: instruction expected\n', ['nasm-assembly-error']),
            (private + '.asm(65) : error: parser: instruction expected\r\n', ['nasm-assembly-error']),
            (private + '.asm:65: fatal: private macro failure\n', ['nasm-assembly-error']),
            ("nasm: fatal: unable to open input file '" + private + "' No such file or directory\n",
             ['nasm-invocation-error']),
            ('nasm: error: unrecognised option private-option\n', ['nasm-invocation-error']),
            ('Version script does not exist\n', ['ffmpeg-makedef-missing-version-script']),
            ('Object does not exist: ' + private + '\n', ['ffmpeg-makedef-missing-object']),
            ('Could not create temporary library.\n', ['ffmpeg-makedef-temporary-library']),
        )
        log = self.root / 'private.log'
        for diagnostic, categories in cases:
            with self.subTest(categories=categories):
                log.write_text(diagnostic + 'private source/model text, argv and target remain private\n')
                report = replay.failure(self.root, 'build-ffmpeg', 2, log, 0)
                self.assertEqual(report['diagnostic_codes'], [])
                self.assertEqual(report['diagnostic_categories'], categories)
                serialized = json.dumps(report)
                for marker in (private, 'private-profile', 'private-target', 'source-model-secret',
                               '--private-argument', 'private-option', 'private macro', diagnostic.strip()):
                    self.assertNotIn(marker, serialized)
                self.assertFalse(report['raw_log_published']); self.assertFalse(report['r19_complete'])
                self.assertFalse((self.root / 'REPLAY-RECEIPT.json').exists())

    def test_known_msvc_command_line_codes_and_unknown_families_never_echo_unapproved_tokens(self):
        log = self.root / 'private.log'
        known = ('C1001', 'D8016', 'D8021', 'D8022', 'D8027', 'D8036',
                 'D8037', 'D8045', 'D8048', 'D8049')
        for code in known:
            with self.subTest(code=code):
                log.write_text('cl : Command line error ' + code + ': private-source --secret-argv\n'
                               if code.startswith('D') else
                               'private.c(4): fatal error C1001: INTERNAL COMPILER ERROR(private-source, line 1)\n')
                report = replay.failure(self.root, 'build-ffmpeg', 2, log, 0)
                self.assertEqual(report['diagnostic_codes'], [code])
                self.assertEqual(report['diagnostic_categories'], [
                    'compiler-command-line-error' if code.startswith('D') else 'compiler-error'])
                self.assertNotIn('private-source', json.dumps(report))
                self.assertNotIn('--secret-argv', json.dumps(report))
        log.write_text('private.c: error C9999: model text\nLINK : fatal error LNK9999: private symbol\n'
            'project : error MSB9999: private target\ncl : Command line error D8999: private argv\n')
        report = replay.failure(self.root, 'build-ffmpeg', 2, log, 0)
        self.assertEqual(report['diagnostic_codes'], [])
        self.assertEqual(report['diagnostic_categories'], ['unclassified-command-line-code',
            'unclassified-compiler-code', 'unclassified-linker-code', 'unclassified-msbuild-code'])
        for marker in ('C9999', 'LNK9999', 'MSB9999', 'D8999', 'model text', 'private'):
            self.assertNotIn(marker, json.dumps(report))

    def test_warning_ignored_make_and_plain_private_text_are_not_error_families(self):
        log = self.root / 'private.log'
        log.write_text('own.c(1): warning C1001: private warning\ncl : Command line warning D9025: private option\n'
            'make: [private-target] Error 2 (ignored)\nprivate.asm:65: warning: private warning\n'
            'nasm: warning: private warning\nmodel says shell-command-not-found\n'
            'argv --flag=C1001 --private=unclassified-compiler-code\n'
            'prefix Object does not exist: private\nprefix make: *** [private] Error 2\n')
        report = replay.failure(self.root, 'build-ffmpeg', 2, log, 0)
        self.assertEqual(report['diagnostic_codes'], [])
        self.assertEqual(report['diagnostic_categories'], ['unclassified-command-failure'])
        log.write_text('Version script does not exist\nCould not create temporary library.\n')
        report = replay.failure(self.root, 'build-opus', 2, log, 0)
        self.assertEqual(report['diagnostic_categories'], ['unclassified-command-failure'])

    def test_unknown_failure_is_fixed_category_and_invalid_stage_or_exit_never_writes(self):
        log = self.root / 'private.log'; log.write_text(
            'private-secret-marker error C9999: unknown code\ncould NOT find private-tool-without-CMake-error\n')
        with patch.dict(replay.os.environ, {'GITHUB_SHA': 'private-invalid-commit'}):
            report = replay.failure(self.root, 'check-shell', 4294967295, log, 0)
        self.assertIsNone(report['source_commit']); self.assertEqual(report['exit_code'], 4294967295)
        self.assertEqual(report['diagnostic_codes'], [])
        self.assertEqual(report['diagnostic_categories'], ['unclassified-compiler-code'])
        (self.root / 'FAILED-STAGE.json').unlink()
        for phase, code, offset in [('private-phase', 1, 0), ('build-opus', 0, 0),
                ('build-opus', True, 0), ('build-opus', 2**32, 0), ('build-opus', 1, -1),
                ('build-opus', 1, 10000)]:
            with self.subTest(phase=phase, code=code, offset=offset), self.assertRaises(ValueError):
                replay.failure(self.root, phase, code, log, offset)
            self.assertFalse((self.root / 'FAILED-STAGE.json').exists())
        self.assertFalse((self.root / 'REPLAY-RECEIPT.json').exists())

    def test_preflight_mismatch_binds_numeric_resources_source_manifest_and_both_tool_bytes(self):
        output = self.root / 'preflight'; observed = {
            'cmake': {'version': '4.4.4', 'bytes': 1234567, 'sha256': 'a'*64},
            'cl': {'file_version': '14.51.36260.0', 'product_version': '19.51.36260.0',
                   'bytes': 987654, 'sha256': 'b'*64}}
        with patch.dict(replay.os.environ, {'GITHUB_SHA': 'c'*40}):
            report = replay.preflight_failure(output, observed)
        self.assertEqual(report['schema'], 'proxy-r19-game-codec-replay-preflight-failure-v1')
        self.assertEqual(report['status'], 'failed'); self.assertEqual(report['phase'], 'preflight-tool-version')
        self.assertEqual(report['source_commit'], 'c'*40)
        self.assertEqual(report['input_manifest']['sha256'], replay.digest(replay.PIN.read_bytes()))
        self.assertEqual(report['input_manifest']['bytes'], len(replay.PIN.read_bytes()))
        self.assertEqual(report['expected_versions'], {'cmake': '4.4.5', 'compiler': '19.51.36260.0'})
        self.assertEqual(report['observed_tools'], observed)
        self.assertEqual(report['mismatch_fields'], ['cmake-version', 'cl-file-resource-version'])
        self.assertNotIn(str(self.root), json.dumps(report))
        for gate in ('raw_log_published', 'native_codec_built', 'native_codec_executed', 'runtime_collection_allowed',
                     'production_execution_allowed', 'source_delivery_approved', 'r19_complete'):
            self.assertFalse(report[gate])
        self.assertEqual(json.loads((output / 'FAILED-STAGE.json').read_text()), report)
        self.assertEqual(sorted(p.name for p in output.iterdir()), ['FAILED-STAGE.json'])

    def test_preflight_never_overwrites_or_creates_output_without_numeric_source_bound_mismatch(self):
        base = {'cmake': {'version': '4.4.5', 'bytes': 100, 'sha256': 'a'*64},
                'cl': {'file_version': '19.51.36260.0', 'product_version': '14.51.36260.0',
                       'bytes': 200, 'sha256': 'b'*64}}
        for case in ('matching', 'raw-version', 'raw-product-version', 'extra-path', 'boolean-bytes', 'bad-hash', 'invalid-source'):
            with self.subTest(case=case):
                observed = json.loads(json.dumps(base)); output = self.root / case
                if case != 'matching': observed['cmake']['version'] = '4.4.4'
                if case == 'raw-version': observed['cmake']['version'] = '4.4.4 private-marker'
                if case == 'raw-product-version': observed['cl']['product_version'] = 'private-marker'
                if case == 'extra-path': observed['cmake']['path'] = 'private-marker'
                if case == 'boolean-bytes': observed['cl']['bytes'] = True
                if case == 'bad-hash': observed['cl']['sha256'] = 'private-marker'
                with patch.dict(replay.os.environ, {'GITHUB_SHA': 'private-marker' if case == 'invalid-source' else 'c'*40}), self.assertRaises(ValueError):
                    replay.preflight_failure(output, observed)
                self.assertFalse(output.exists())
        output = self.root / 'existing'; output.mkdir(); (output / 'prior').write_bytes(b'preserved')
        with self.assertRaises(ValueError): replay.preflight_failure(output, base)
        self.assertEqual((output / 'prior').read_bytes(), b'preserved')
        self.assertFalse((output / 'FAILED-STAGE.json').exists())

    def test_preflight_native_data_reader_rejects_duplicate_keys_and_oversized_input(self):
        self.assertEqual(replay.read_preflight_observation(io.BytesIO(b'{"cmake": {}, "cl": {}}')),
                         {'cmake': {}, 'cl': {}})
        for raw in (b'{"cmake": {}, "cmake": {}}', b' '*8193):
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                replay.read_preflight_observation(io.BytesIO(raw))

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell path-selection contract requires pwsh')
    def test_explicit_tool_selection_ignores_competing_path_matches_and_rejects_ambient_python(self):
        pinned_root = self.root / 'pinned-cmake'
        canonical = pinned_root / 'cmake-4.4.5-windows-x86_64/bin/cmake.exe'
        selected_python = self.root / 'selected-python/python.exe'
        for path in (canonical, selected_python, self.root / 'competing/cmake.exe',
                     self.root / 'competing/python.exe'):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'authored non-executed tool fixture')
        contract = self.root / 'selection-contract.ps1'
        contract.write_text('''param($SourcePath, $PinnedCMakeRoot, $SelectedPython, $ExpectedCMake)
$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($SourcePath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Build script has parse errors.' }
$definition = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-ReplayExecutables'}, $true)
if (-not $definition) { throw 'Explicit executable selector is unavailable.' }
. ([ScriptBlock]::Create($definition.Extent.Text))
function Get-Command { throw 'Ambient tool discovery must never execute.' }
$value = Get-ReplayExecutables -PinnedCMakeRoot $PinnedCMakeRoot -PythonPath $SelectedPython
if ($value.CMake -ne $ExpectedCMake -or $value.Python -ne $SelectedPython -or
    $value.CMake -isnot [string] -or $value.Python -isnot [string]) { throw 'Explicit tool selection differed.' }
foreach ($bad in @('python', 'relative/python.exe', (Join-Path $PinnedCMakeRoot 'missing.exe'), $PinnedCMakeRoot)) {
    $rejected = $false
    try { Get-ReplayExecutables -PinnedCMakeRoot $PinnedCMakeRoot -PythonPath $bad | Out-Null }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Invalid explicit Python path was accepted.' }
}
$value | ConvertTo-Json -Compress
''', encoding='utf-8')
        result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-File', str(contract),
            str(ROOT / 'scripts/build-game-codec-replay.ps1'), str(pinned_root),
            str(selected_python), str(canonical)], check=True, capture_output=True, text=True, timeout=20)
        self.assertEqual(json.loads(result.stdout), {'CMake': str(canonical), 'Python': str(selected_python)})

    @unittest.skipUnless(shutil.which('pwsh'), 'Actual process environment deletion contract requires pwsh')
    def test_process_environment_deletion_removes_empty_and_nonempty_keys_before_inputs(self):
        contract = self.root / 'process-environment-contract.ps1'
        contract.write_text(r'''param($SourcePath)
$ErrorActionPreference = 'Stop'
try {
    $tokens=$null; $errors=$null
    $ast=[Management.Automation.Language.Parser]::ParseFile($SourcePath,[ref]$tokens,[ref]$errors)
    if ($errors) { throw 'parse' }
    $definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Remove-ReplayProcessEnvironment'},$true)
    if (-not $definition) { throw 'missing function' }
    . ([scriptblock]::Create($definition.Extent.Text))
    $empty='R19_AUTHORED_EMPTY'; $nonempty='R19_AUTHORED_NONEMPTY'; $absent='R19_AUTHORED_ABSENT'
    [Environment]::SetEnvironmentVariable($empty,'','Process')
    [Environment]::SetEnvironmentVariable($nonempty,'private-value-never-publish','Process')
    [Environment]::SetEnvironmentVariable($absent,[NullString]::Value,'Process')
    $before=[Environment]::GetEnvironmentVariables('Process')
    if (-not $before.Contains($empty) -or $before[$empty] -ne '' -or
        -not $before.Contains($nonempty) -or $before.Contains($absent)) { throw 'authored precondition' }
    Remove-ReplayProcessEnvironment -Names @($empty,$nonempty,$absent)
    $after=[Environment]::GetEnvironmentVariables('Process')
    foreach ($name in @($empty,$nonempty,$absent)) {
        if ($after.Contains($name) -or $null -ne [Environment]::GetEnvironmentVariable($name,'Process')) { throw 'key retained' }
    }
    Remove-ReplayProcessEnvironment -Names @($empty,$nonempty,$absent)
    $rejected=$false
    try { Remove-ReplayProcessEnvironment -Names @('private=profile-secret') }
    catch { if ($_.Exception.Message -eq 'Build process environment deletion failed.') { $rejected=$true } }
    if (-not $rejected) { throw 'failure projection' }
    @{removed_empty=$true;removed_nonempty=$true;absent_idempotent=$true;failure_is_fixed=$true} | ConvertTo-Json -Compress
} catch { [Console]::Error.WriteLine('Authored process environment deletion contract failed.'); exit 1 }
''', encoding='utf-8')
        result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-File', str(contract),
            str(ROOT / 'scripts/build-game-codec-replay.ps1')], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, 'Authored process environment deletion contract failed.')
        self.assertEqual(json.loads(result.stdout), {'removed_empty': True, 'removed_nonempty': True,
                         'absent_idempotent': True, 'failure_is_fixed': True})
        self.assertNotIn('private-value', result.stdout); self.assertNotIn('profile-secret', result.stdout)

    @unittest.skipUnless(shutil.which('make') and shutil.which('sh'), 'Authored stdin export regression requires local GNU make and sh')
    def test_authored_makefile_exports_initially_empty_ar_but_keeps_unset_ar_absent(self):
        make = shutil.which('make')
        version = subprocess.run([make, '--version'], capture_output=True, timeout=5)
        if version.returncode or not version.stdout.startswith(b'GNU Make'):
            self.skipTest('Local make is not GNU make; no tool substitution or installation')
        recipe = (b'.PHONY: probe\nAR = authored-make-value\nprobe:\n'
                  b'\t@if test "$${AR+x}" != x; then printf "absent\\n"; '
                  b'elif test "$$AR" = authored-make-value; then printf "present-nonempty\\n"; '
                  b'else printf "unexpected-present-value\\n"; fi\n')
        for state, expected in (('unset', b'absent\n'), ('empty', b'present-nonempty\n')):
            with self.subTest(initial_state=state):
                env = dict(os.environ)
                for key in ('AR', 'MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS', 'MAKEFILES', 'ENV', 'BASH_ENV'):
                    env.pop(key, None)
                if state == 'empty': env['AR'] = ''
                result = subprocess.run([make, '--no-print-directory', '-f', '-',
                    'SHELL=' + shutil.which('sh'), 'probe'], input=recipe, env=env,
                    capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, 'Authored make export regression failed.')
                self.assertEqual(result.stdout.replace(b'\r\n', b'\n'), expected)

    @unittest.skipUnless(shutil.which('pwsh'), 'Host-image policy contract requires pwsh')
    def test_host_image_policy_requires_explicit_versions_without_rolling_or_wildcard_fallback(self):
        contract = self.root / 'host-image-contract.ps1'
        contract.write_text(r'''param($SourcePath)
$ErrorActionPreference = 'Stop'
try {
    $tokens=$null; $errors=$null
    $ast=[Management.Automation.Language.Parser]::ParseFile($SourcePath,[ref]$tokens,[ref]$errors)
    if ($errors) { throw 'parse' }
    $definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Assert-ReviewedHostImage'},$true)
    if (-not $definition) { throw 'missing function' }
    . ([scriptblock]::Create($definition.Extent.Text))
    $reviewed=@('20261021.278.1','20261030.294.1')
    foreach ($version in $reviewed) { Assert-ReviewedHostImage $true 'win25-vs2026' $version $reviewed }
    $cases=@(
        @{windows=$false;os='win25-vs2026';actual=$reviewed[0];versions=$reviewed},
        @{windows=$true;os='private path';actual=$reviewed[0];versions=$reviewed},
        @{windows=$true;os='win25-vs2026';actual='20261101.1.1';versions=$reviewed},
        @{windows=$true;os='win25-vs2026';actual=($reviewed[0]+"`n");versions=$reviewed},
        @{windows=$true;os='win25-vs2026';actual=$reviewed[0];versions=@()},
        @{windows=$true;os='win25-vs2026';actual=$reviewed[0];versions=@($reviewed[0],$reviewed[0])},
        @{windows=$true;os='win25-vs2026';actual=$reviewed[0];versions=@($reviewed[0],'202610*.1.1')},
        @{windows=$true;os='win25-vs2026';actual=$reviewed[0];versions=@($reviewed[0],($reviewed[1]+"`n"))},
        @{windows=$true;os='win25-vs2026';actual=$reviewed[0];versions=@($reviewed[0],$reviewed[1],'20261101.1.1')})
    foreach ($case in $cases) {
        $rejected=$false
        try { Assert-ReviewedHostImage $case.windows $case.os $case.actual $case.versions }
        catch { if ($_.Exception.Message -eq 'Exact reviewed hosted image unavailable; no moving-image substitution.') { $rejected=$true } }
        if (-not $rejected) { throw 'policy boundary' }
    }
    @{accepted=2;rejected=$cases.Count} | ConvertTo-Json -Compress
} catch { [Console]::Error.WriteLine('Authored host-image boundary failed.'); exit 1 }
''', encoding='utf-8')
        result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-File', str(contract),
            str(ROOT / 'scripts/build-game-codec-replay.ps1')], check=False, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, 'Authored host-image boundary failed; no native input is prepared.')
        self.assertEqual(json.loads(result.stdout), {'accepted': 2, 'rejected': 9})

    @unittest.skipUnless(shutil.which('pwsh') and shutil.which('cmd.exe'),
                         'Compiler activation quoting contract requires Windows pwsh/cmd')
    def test_compiler_activation_handles_spaced_batch_paths_and_never_exports_failed_or_foreign_values(self):
        tools = self.root / 'authored VC tools with spaces'; tools.mkdir()
        success = tools / 'vcvarsall.bat'
        success.write_text('''@echo off
if not "%~1"=="x64" exit /b 61
if not "%~2"=="10.0.26100.0" exit /b 62
rem Unquoted equals is a batch-parameter delimiter; preserve the exact raw call too.
if not "%~3"=="-vcvars_ver" exit /b 63
if not "%~4"=="14.51.36231" exit /b 64
if not "%~5"=="" exit /b 65
if not "%*"=="x64 10.0.26100.0 -vcvars_ver=14.51.36231" exit /b 66
set "INCLUDE=authored include"
set "LIB=authored lib"
set "VCToolsInstallDir=authored toolset"
set "WindowsSdkDir=authored SDK"
set "WindowsSDKVersion=10.0.26100.0"
set "FOREIGN_PRIVATE_FIXTURE=private-stdout-marker"
exit /b 0
''', encoding='utf-8')
        failed = tools / 'failing vcvarsall.bat'
        failed.write_text('@echo off\nset "INCLUDE=partial value"\necho private-stdout-marker\nexit /b 7\n', encoding='utf-8')
        contract = self.root / 'activation-contract.ps1'
        contract.write_text('''param($SourcePath, $SuccessBatch, $FailedBatch, $ProfileParent)
$ErrorActionPreference = 'Stop'
$contractPhase = 'parse'; $activationExit = $null
try {
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($SourcePath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Build script has parse errors.' }
$definition = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-CompilerEnvironment'}, $true)
if (-not $definition) { throw 'Compiler environment activation function unavailable.' }
. ([ScriptBlock]::Create($definition.Extent.Text))
$beforeInclude = $env:INCLUDE
$fixtureProfile = Join-Path $ProfileParent 'profile with spaces'
$failedProfile = Join-Path $ProfileParent 'failed profile with spaces'
New-Item -ItemType Directory -Path $fixtureProfile, $failedProfile | Out-Null
$contractPhase = 'successful-activation'
$value = Get-CompilerEnvironment -ActivationRoot $fixtureProfile -VcvarsPath $SuccessBatch -SdkVersion '10.0.26100.0' -ToolsetVersion '14.51.36231'
$contractPhase = 'successful-projection'
if ($value.Count -ne 5 -or $value.INCLUDE -ne 'authored include' -or $value.LIB -ne 'authored lib' -or
    $value.VCToolsInstallDir -ne 'authored toolset' -or $value.WindowsSdkDir -ne 'authored SDK' -or
    $value.WindowsSDKVersion -ne '10.0.26100.0') { throw 'Authored activation arguments or allowlist differed.' }
$failedAsExpected = $false
$contractPhase = 'failed-activation'
try { Get-CompilerEnvironment -ActivationRoot $failedProfile -VcvarsPath $FailedBatch -SdkVersion '10.0.26100.0' -ToolsetVersion '14.51.36231' | Out-Null }
catch {
    if ($_.Exception.Message -match '^Exact compiler/SDK activation failed; exit code (-?[0-9]{1,10})\\.$') {
        $activationExit = [long]$Matches[1]
        if ($activationExit -eq 7) { $failedAsExpected = $true }
    }
}
$contractPhase = 'failed-projection'
if (-not $failedAsExpected -or $env:INCLUDE -ne $beforeInclude) { throw 'Failed activation exported partial environment.' }
$value | ConvertTo-Json -Compress
} catch {
    if ($_.Exception.Message -match '^Exact compiler/SDK activation failed; exit code (-?[0-9]{1,10})\\.$') {
        $activationExit = [long]$Matches[1]
    }
    [Console]::Error.WriteLine((@{schema='authored-activation-contract-failure-v1'; phase=$contractPhase;
        activation_exit=$activationExit} | ConvertTo-Json -Compress))
    exit 1
}
''', encoding='utf-8')
        result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-File', str(contract),
            str(ROOT / 'scripts/build-game-codec-replay.ps1'), str(success), str(failed), str(self.root)],
            check=False, capture_output=True, text=True, timeout=20)
        if result.returncode:
            # The wrapper emits only fixed phase labels and an optional numeric exit.
            try: diagnosis = json.loads(result.stderr)
            except (ValueError, TypeError): self.fail('Authored activation contract failed without safe diagnostics.')
            self.assertEqual(set(diagnosis), {'schema', 'phase', 'activation_exit'})
            self.assertEqual(diagnosis['schema'], 'authored-activation-contract-failure-v1')
            self.assertIn(diagnosis['phase'], {'parse', 'successful-activation', 'successful-projection',
                                             'failed-activation', 'failed-projection'})
            self.assertTrue(diagnosis['activation_exit'] is None or type(diagnosis['activation_exit']) is int)
            self.fail('Authored activation contract failed: ' + json.dumps(diagnosis, sort_keys=True))
        self.assertEqual(json.loads(result.stdout), {'INCLUDE': 'authored include', 'LIB': 'authored lib',
            'VCToolsInstallDir': 'authored toolset', 'WindowsSdkDir': 'authored SDK', 'WindowsSDKVersion': '10.0.26100.0'})
        self.assertNotIn('private-stdout-marker', result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('pwsh') and shutil.which('cmd.exe'),
                         'Compiler search-path behavior contract requires Windows pwsh/cmd')
    def test_search_path_failure_is_bounded_source_bound_and_strips_arbitrary_paths_and_exceptions(self):
        contract = self.root / 'search-contract.ps1'
        contract.write_text('''param($SourcePath, $FixtureRoot, $ManifestPath)
$ErrorActionPreference = 'Stop'
$contractPhase = 'parse'
try {
    $tokens = $null; $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($SourcePath, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw 'parse' }
    foreach ($name in @('Get-CompilerSearchObservation','Write-CompilerSearchFailure','Write-ToolIdentity')) {
        $definition = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name}, $true)
        if (-not $definition) { throw 'missing function' }
        . ([ScriptBlock]::Create($definition.Extent.Text))
    }
    $contractPhase = 'observations'
    $include = Join-Path $FixtureRoot 'private-personal-marker/include'
    $library = Join-Path $FixtureRoot 'private-personal-marker/library'
    $auxiliary = Join-Path $FixtureRoot 'private-personal-marker/auxiliary/VS/include'
    $unknown = Join-Path $FixtureRoot 'private-personal-marker/arbitrary-account'
    $netfxParent = Join-Path $FixtureRoot 'private-personal-marker/NETFXSDK'
    $netfxInclude = Join-Path $netfxParent '4.8.1/Include/um'
    $netfxLib = Join-Path $netfxParent '4.8.1/Lib/um/x64'
    New-Item -ItemType Directory -Path $include, $library, $auxiliary, $unknown | Out-Null
    New-Item -ItemType Directory -Path $netfxInclude, $netfxLib -Force | Out-Null
    $roots = [ordered]@{'msvc-include'=$include; 'msvc-lib-x64'=$library; 'vc-auxiliary-include'=$auxiliary;
        'netfx-other'=$netfxParent; 'private-role-marker'=$unknown}
    $goodInclude = Get-CompilerSearchObservation 'INCLUDE' ($include + ';') @($include) $roots
    $goodLib = Get-CompilerSearchObservation 'LIB' $library @($library) $roots
    if ($goodInclude.entries[0].disposition -ne 'accepted' -or $goodInclude.entry_count -ne 1 -or
        $goodLib.entries[0].disposition -ne 'accepted') { throw 'valid roots rejected' }
    $badInclude = Get-CompilerSearchObservation 'INCLUDE' ($include + ';' + $auxiliary + ';' + $unknown) @($include) $roots
    if ($badInclude.entries[1].component_role -ne 'vc-auxiliary-include' -or
        $badInclude.entries[1].disposition -ne 'outside-declared-roots' -or
        $badInclude.entries[2].component_role -ne 'unclassified' -or
        $badInclude.entries[2].disposition -ne 'outside-declared-roots') { throw 'diagnostic role bypassed admission' }
    $missing = Get-CompilerSearchObservation 'INCLUDE' (Join-Path $include 'missing') @($include) $roots
    if ($missing.entries[0].exists -ne $false -or $missing.entries[0].disposition -ne 'missing-directory') { throw 'missing path accepted' }
    $empty = Get-CompilerSearchObservation 'INCLUDE' ($include + ';;' + $include) @($include) $roots
    $relative = Get-CompilerSearchObservation 'LIB' 'private-relative-marker' @($library) $roots
    if ($empty.entries[1].disposition -ne 'empty-entry' -or $relative.entries[0].disposition -ne 'invalid-entry') { throw 'ambient path accepted' }
    $unavailable = Get-CompilerSearchObservation 'INCLUDE' '' @($include) $roots
    $oversized = Get-CompilerSearchObservation 'INCLUDE' ('p' * 32768) @($include) $roots
    $many = Get-CompilerSearchObservation 'INCLUDE' ((1..65 | ForEach-Object { $include }) -join ';') @($include) $roots
    if ($unavailable.state -ne 'unavailable' -or $oversized.state -ne 'value-limit' -or
        $oversized.entry_count -ne 0 -or $many.state -ne 'entry-limit' -or $many.entry_count -ne 64) { throw 'observation bound failed' }
    function Test-Path { throw 'private-exception-marker from arbitrary account path' }
    try { $fault = Get-CompilerSearchObservation 'INCLUDE' $include @($include) $roots }
    finally { Remove-Item Function:Test-Path }
    if ($fault.entries[0].disposition -ne 'inspection-error' -or $null -ne $fault.entries[0].exists) { throw 'exception exposed or admitted' }
    $contractPhase = 'numeric-netfx'
    $numericInclude = Get-CompilerSearchObservation 'INCLUDE' $netfxInclude @($include) $roots
    $numericLib = Get-CompilerSearchObservation 'LIB' $netfxLib @($library) $roots
    if ($numericInclude.entries[0].netfx_sdk_version -ne '4.8.1' -or
        $numericInclude.entries[0].netfx_search_role -ne 'include-um' -or
        $numericLib.entries[0].netfx_sdk_version -ne '4.8.1' -or
        $numericLib.entries[0].netfx_search_role -ne 'lib-um-x64' -or
        $numericInclude.entries[0].disposition -ne 'outside-declared-roots' -or
        $numericLib.entries[0].disposition -ne 'outside-declared-roots') { throw 'numeric observation bypassed admission' }
    foreach ($version in @('4.8','4.8.1.2')) {
        $value = Get-CompilerSearchObservation 'INCLUDE' (Join-Path $netfxParent ($version + '/Include/um')) @($include) $roots
        if ($value.entries[0].netfx_sdk_version -ne $version -or $value.entries[0].netfx_search_role -ne 'include-um') { throw 'numeric version inferred or pinned' }
    }
    foreach ($relative in @('4.8-private/Include/um','4/Include/um','4.8.1.2.3/Include/um',
        '1234567.8/Include/um','4.8.1/Include/um/private-suffix','private-child/4.8.1/Include/um',
        '../NETFXSDK-sibling/4.8.1/Include/um',"4.8.1/Include/um`n")) {
        $value = Get-CompilerSearchObservation 'INCLUDE' (Join-Path $netfxParent $relative) @($include) $roots
        if ($null -ne $value.entries[0].netfx_sdk_version -or $null -ne $value.entries[0].netfx_search_role -or
            $value.entries[0].disposition -eq 'accepted') { throw 'arbitrary path exposed or admitted' }
    }
    $contractPhase = 'vc-auxiliary-seal'
    $admitted = Get-CompilerSearchObservation 'INCLUDE' $auxiliary @($include, $auxiliary) $roots
    if ($admitted.entries[0].disposition -ne 'accepted') { throw 'explicit observed header root rejected' }
    $header = Join-Path $auxiliary 'authored-header.h'
    [IO.File]::WriteAllText($header, 'authored before')
    $toolRoots = [ordered]@{'vc-auxiliary'=[IO.Path]::GetFullPath((Join-Path $auxiliary '../..'))}
    $tar = $vswhere = $pythonExe = Join-Path $FixtureRoot 'authored-nonexecuted-tool.exe'
    [IO.File]::WriteAllText($tar, 'authored non-executable bytes; hash only')
    $pin = [pscustomobject]@{host=[pscustomobject]@{compiler_version='19.51.36260.0';toolset_directory='14.51.36231';sdk_version='10.0.26100.0';cmake_version='4.4.5'}}
    $instance = [pscustomobject]@{installationVersion='18.0.0.0'}
    $before = Join-Path $FixtureRoot 'authored-tool-seal-before.json'
    $after = Join-Path $FixtureRoot 'authored-tool-seal-after.json'
    $savedComSpec = $env:ComSpec
    try {
        $env:ComSpec = $tar
        Write-ToolIdentity $before
        [IO.File]::WriteAllText($header, 'authored changed after')
        Write-ToolIdentity $after
    } finally { $env:ComSpec = $savedComSpec }
    $beforeTree = (Get-Content -LiteralPath $before -Raw | ConvertFrom-Json).trees.'vc-auxiliary'
    $afterTree = (Get-Content -LiteralPath $after -Raw | ConvertFrom-Json).trees.'vc-auxiliary'
    $beforeHash = $beforeTree.'VS/include/authored-header.h'.sha256
    $afterHash = $afterTree.'VS/include/authored-header.h'.sha256
    if ($beforeHash -cnotmatch '^[a-f0-9]{64}$' -or $afterHash -eq $beforeHash -or
        $afterHash -ne (Get-FileHash -LiteralPath $header -Algorithm SHA256).Hash.ToLowerInvariant()) { throw 'observed auxiliary header omitted from seal' }
    $contractPhase = 'projection'
    $badInclude = Get-CompilerSearchObservation 'INCLUDE' ($include + ';' + $auxiliary + ';' + $unknown + ';' + $netfxInclude) @($include, $auxiliary) $roots
    $badLib = Get-CompilerSearchObservation 'LIB' ($library + ';' + $netfxLib) @($library) $roots
    $badInclude['private_object_field'] = 'private-extra-marker'
    $badInclude.entries[0]['raw_path'] = $include
    $destination = Join-Path $FixtureRoot 'failed-receipt'
    Write-CompilerSearchFailure $destination $ManifestPath ('a' * 40) @($badInclude, $badLib)
    $report = Get-Content -LiteralPath (Join-Path $destination 'FAILED-STAGE.json') -Raw | ConvertFrom-Json
    if (@(Get-ChildItem -LiteralPath $destination).Count -ne 1) { throw 'unexpected publication' }
    $contractPhase = 'fail-closed'
    $rejected = $false
    try { Write-CompilerSearchFailure $destination $ManifestPath ('a' * 40) @($badInclude, $goodLib) }
    catch { if ($_.Exception.Message -eq 'Safe compiler search-path failure receipt could not be recorded.') { $rejected = $true } }
    if (-not $rejected) { throw 'existing receipt overwritten' }
    foreach ($case in @('matching','source','source-lf','role','exception','bound','numeric','numeric-lf','suffix','missing-pair')) {
        $out = Join-Path $FixtureRoot ('invalid-' + $case)
        $source = 'a' * 40; $manifest = $ManifestPath; $item = $badInclude
        if ($case -eq 'matching') { $item = $goodInclude }
        if ($case -eq 'source') { $source = 'private-source-marker' }
        if ($case -eq 'source-lf') { $source = ('a' * 40) + "`n" }
        if ($case -eq 'role') { $item = Get-CompilerSearchObservation 'INCLUDE' $auxiliary @($include) $roots; $item.entries[0].component_role = 'private-role-marker' }
        if ($case -eq 'exception') { $manifest = Join-Path $FixtureRoot 'private-missing-manifest-marker' }
        if ($case -eq 'bound') { $item = Get-CompilerSearchObservation 'INCLUDE' $auxiliary @($include) $roots; $item.entry_count = 65 }
        if ($case -in @('numeric','numeric-lf','suffix','missing-pair')) {
            $item = Get-CompilerSearchObservation 'INCLUDE' $netfxInclude @($include) $roots
            if ($case -eq 'numeric') { $item.entries[0].netfx_sdk_version = '4.8.1 private-version-marker' }
            if ($case -eq 'numeric-lf') { $item.entries[0].netfx_sdk_version = "4.8.1`n" }
            if ($case -eq 'suffix') { $item.entries[0].netfx_search_role = 'private-suffix-marker' }
            if ($case -eq 'missing-pair') { $item.entries[0].netfx_search_role = $null }
        }
        $rejected = $false
        try { Write-CompilerSearchFailure $out $manifest $source @($item, $goodLib) }
        catch { if ($_.Exception.Message -eq 'Safe compiler search-path failure receipt could not be recorded.') { $rejected = $true } }
        if (-not $rejected -or (Test-Path -LiteralPath $out)) { throw 'invalid receipt published' }
    }
    $report | ConvertTo-Json -Depth 7 -Compress
} catch {
    [Console]::Error.WriteLine((@{schema='authored-search-contract-failure-v1'; phase=$contractPhase} | ConvertTo-Json -Compress))
    exit 1
}
''', encoding='utf-8')
        result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-File', str(contract),
            str(ROOT / 'scripts/build-game-codec-replay.ps1'), str(self.root), str(replay.PIN)],
            check=False, capture_output=True, text=True, timeout=20)
        if result.returncode:
            try: diagnosis = json.loads(result.stderr)
            except (ValueError, TypeError): self.fail('Authored search-path contract failed without safe diagnostics.')
            self.assertEqual(set(diagnosis), {'schema', 'phase'})
            self.assertEqual(diagnosis['schema'], 'authored-search-contract-failure-v1')
            self.assertIn(diagnosis['phase'], {'parse', 'observations', 'numeric-netfx', 'vc-auxiliary-seal', 'projection', 'fail-closed'})
            self.fail('Authored search-path contract failed: ' + json.dumps(diagnosis, sort_keys=True))
        report = json.loads(result.stdout)
        self.assertEqual(report['schema'], 'proxy-r19-game-codec-replay-toolchain-preflight-failure-v2')
        self.assertEqual(report['phase'], 'preflight-compiler-search-path'); self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['source_commit'], 'a'*40)
        self.assertEqual(report['input_manifest'], {'path': 'packaging/codecs/ffmpeg-opus-replay.json',
            'bytes': len(replay.PIN.read_bytes()), 'sha256': replay.digest(replay.PIN.read_bytes())})
        self.assertEqual(report['search_paths'][0], {'kind': 'INCLUDE', 'state': 'checked', 'entry_count': 4, 'entries': [
            {'component_role': 'msvc-include', 'exists': True, 'disposition': 'accepted', 'netfx_sdk_version': None, 'netfx_search_role': None},
            {'component_role': 'vc-auxiliary-include', 'exists': True, 'disposition': 'accepted', 'netfx_sdk_version': None, 'netfx_search_role': None},
            {'component_role': 'unclassified', 'exists': True, 'disposition': 'outside-declared-roots', 'netfx_sdk_version': None, 'netfx_search_role': None},
            {'component_role': 'netfx-other', 'exists': True, 'disposition': 'outside-declared-roots', 'netfx_sdk_version': '4.8.1', 'netfx_search_role': 'include-um'}]})
        self.assertEqual(report['search_paths'][1]['entries'][1], {'component_role': 'netfx-other', 'exists': True,
            'disposition': 'outside-declared-roots', 'netfx_sdk_version': '4.8.1', 'netfx_search_role': 'lib-um-x64'})
        for gate in ('raw_log_published', 'native_codec_built', 'native_codec_executed', 'runtime_collection_allowed',
                     'production_execution_allowed', 'source_delivery_approved', 'r19_complete'):
            self.assertIs(report[gate], False)
        serialized = result.stdout + result.stderr
        for private in (str(self.root), 'private-personal-marker', 'private-extra-marker', 'raw_path',
                        'private_object_field', 'private-relative-marker', 'private-exception-marker', 'private-role-marker',
                        'private-version-marker', 'private-suffix-marker'):
            self.assertNotIn(private, serialized)


if __name__ == '__main__': unittest.main()
