"""Ordinary project LICENSE. Fixed MP3 metadata verifier, never a native runner.

This provenance wiring is outside the four-file additional BSD option. Broad
producer inventories stay private. Only the explicit verified projection leaves
this module; no hash of the original private producer JSON is published.
"""
import hashlib, importlib.util, json, os, re, stat, sys
from pathlib import Path, PurePosixPath

BASE = '0f9353137bdc8c57adbe275b4d245a6a1f136796'
FLAGS = dict(source_delivery_approved=False, runtime_collection_allowed=False,
             production_execution_allowed=False, r19_complete=False,
             native_windows_11_acceptance='unavailable', installer='not-built')
PUBLIC_LIMIT = 256 * 1024
CONFIGURE_LOG_LIMIT = 1024 * 1024  # Two fixed files, at most 2MiB total.
CONFIGURE_SCHEMA = 'proxy-r19-mp3-ci-configure-failure-v2'
CONFIGURE_SCOPE = 'private-log-observations-not-cause'
CONFIGURE_LOGS = (('configure-log', 'ffmpeg-build/ffbuild/config.log'),
                  ('cumulative-build-output', 'PRIVATE-BUILD.log'))
CONFIGURE_FATAL = {
    b'C compiler test failed.': 'compiler-test-failed',
    b'ERROR: libmp3lame >= 3.98.3 not found': 'libmp3lame-check-failed',
    b'ERROR: opus not found using pkg-config': 'opus-pkg-config-check-failed',
}
CONFIGURE_STATIC_NOTE = b'Note: When building a static binary, add --pkg-config-flags="--static".'
_CONFIGURE_READERS = []  # Actual streams/errors only; never serialized or retried.
OBSERVE_SCHEMA = 'proxy-r19-mp3-ci-observe-failure-v2'
OBSERVE_SCOPE = 'cumulative-private-tail-signature-not-current-command-or-cause'
OBSERVE_DRIVER_LF_SHA256 = 'ccb841c155ecd17ef67ad26a59d7621ac1c3097940ce7e050dd2cbac5b36cb89'
OBSERVE_FRAME_RANGES = {'stage_candidate': [256, 264], 'finish_native': [677, 740], 'main': [742, 750]}
# Fixed reviewed literals and source locations, never learned from future messages.
OBSERVE_PREDICATES = {
    'original-source-changed': ('Original supplier sources changed.', 'verify_sources', 221, 231, 225, ('stage-candidate', 'finish-native')),
    'project-inputs-changed': ('Draft inputs changed after preparation.', 'verify_sources', 221, 231, 228, ('stage-candidate', 'finish-native')),
    'staged-output-not-fresh': ('Fresh staged output required.', 'copy_regular', 233, 236, 235, ('stage-candidate',)),
    'lame-installation-changed': ('Selected LAME header/import/library output changed.', 'verify_lame_install', 248, 254, 253, ('stage-candidate', 'finish-native')),
    'candidate-not-fresh': ('Candidate staging must be fresh.', 'stage_candidate', 256, 264, 258, ('stage-candidate',)),
    'installed-native-closure': ('Unexpected installed executable/DLL closure.', 'stage_candidate', 256, 264, 260, ('stage-candidate',)),
    'decoded-duration': ('Decoded duration outside authored delay tolerance.', 'check_tone', 270, 278, 271, ('finish-native',)),
    'decoded-signal': ('Wrong authored signal or silent output.', 'check_tone', 270, 278, 278, ('finish-native',)),
    'encoded-container': ('Encoded MPEG audio container missing.', 'publish_encoded', 287, 299, 297, ('finish-native',)),
    'windows-host-required': ('Actual Windows build/probe required; draft has no native pass.', 'finish_native', 677, 740, 678, ('finish-native',)),
    'selected-tools-changed': ('Selected supplier tools changed.', 'finish_native', 677, 740, 681, ('finish-native',)),
    'candidate-set-differs': ('Exact MP3 candidate set differs.', 'finish_native', 677, 740, 685, ('finish-native',)),
    'project-notice-differs': ('Candidate MP3 BSD notice differs.', 'finish_native', 677, 740, 686, ('finish-native',)),
    'candidate-notice-differs': ('Candidate notice bytes differ.', 'finish_native', 677, 740, 688, ('finish-native',)),
    'foreign-native-origin': ('Foreign native origin.', 'finish_native', 677, 740, 698, ('finish-native',)),
    'codec-version-configuration': ('Actual codec/version/configuration differs.', 'finish_native', 677, 740, 703, ('finish-native',)),
    'malformed-input-published': ('Malformed input unexpectedly published.', 'finish_native', 677, 740, 720, ('finish-native',)),
    'previous-output-replaced': ('Failure replaced previous output.', 'finish_native', 677, 740, 721, ('finish-native',)),
    'candidate-inputs-changed': ('Native probes modified candidate inputs.', 'finish_native', 677, 740, 722, ('finish-native',)),
    'lame-probe-installation-changed': ('Selected LAME installation changed during probes.', 'finish_native', 677, 740, 723, ('finish-native',)),
}
OBSERVE_FRAME = re.compile(rb'  File "([^"\r\n]+)", line ([1-9][0-9]{0,5}), in ([A-Za-z_][A-Za-z0-9_]*|<module>|<lambda>)\Z')
OBSERVE_STATES = {'missing','not-observed','truncated-block','unknown','conflicting','known-signature'}
CMAKE_KNOWN = {'executable': {'path': 'cmake-4.4.5-windows-x86_64/bin/cmake.exe', 'bytes': 13465672, 'sha256': '84935c0b7cb09c140de0d3b042d4e93e5fac4e6371e75bf28eae3d841f79dfb3'}, 'notices': [{'path': 'cmake-4.4.5-windows-x86_64/doc/cmake/LICENSE.rst', 'bytes': 1526, 'sha256': 'cd944d878806fee998ef3f88ca41ec060ae198bd8ba615e284f7d8d90c25593e'}, {'path': 'cmake-4.4.5-windows-x86_64/doc/cmake/cmsys/Copyright.txt', 'bytes': 1851, 'sha256': '0998690e8dc877e5d9d79d852f85630ba42b4061962baefc9651675ecf972082'}, {'path': 'cmake-4.4.5-windows-x86_64/doc/cmake/cmzlib/Copyright.txt', 'bytes': 1063, 'sha256': 'd5bbd7748a19e3fed6ea31242e8de9814e69a0125ae7758a7491057d5fe76f34'}], 'archive': {'filename': 'cmake-4.4.5-windows-x86_64.zip', 'root': 'cmake-4.4.5-windows-x86_64', 'bytes': 54412232, 'sha256': '326c826486d46a23cf9d5a1c9ee3a567d427bdd02c4a34071937a2a675cff004', 'entries': 8979, 'regular_files': 8817, 'expanded_bytes': 143317490}}
HEX = re.compile(r'[a-f0-9]{64}\Z')
SHA = lambda b: hashlib.sha256(b).hexdigest()
record = lambda b: dict(bytes=len(b), sha256=SHA(b))
serialized = lambda v: (json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)+'\n').encode()


def require(condition):
    if not condition:
        raise ValueError('MP3 metadata unavailable.')


def keys(value, expected):
    require(type(value) is dict and set(value) == set(expected))


def byte_record(value):
    keys(value, ('bytes', 'sha256'))
    require(type(value['bytes']) is int and 0 <= value['bytes'] <= 512*1024*1024)
    require(type(value['sha256']) is str and HEX.fullmatch(value['sha256']))


def relative(value):
    require(type(value) is str and 0 < len(value) <= 512 and '\\' not in value and ':' not in value)
    require(str(PurePosixPath(value)) == value and not value.startswith('/') and not set(PurePosixPath(value).parts)&{'.','..'})
    require(all(ord(c) >= 32 and ord(c) != 127 for c in value))


def file_map(value, expected=None, cap=16000):
    require(type(value) is dict and 0 < len(value) <= cap)
    if expected is not None:
        require(set(value) == set(expected))
    require(len(value) == len({n.casefold() for n in value}))
    for n, row in value.items():
        relative(n); byte_record(row)


def checked_flags(value):
    for n, expected in FLAGS.items():
        require(type(value.get(n)) is type(expected) and value[n] == expected)


def unique(items):
    value = {}
    for k, v in items:
        require(k not in value); value[k] = v
    return value


def read_json(module, path, limit=64*1024*1024):
    info = module.base.regular_file(path)
    require(info.st_size <= limit)
    with path.open('rb') as f:
        raw = f.read(limit+1)
    require(len(raw) == info.st_size and len(raw) <= limit)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _v: require(False))


def configure_log_tail(module, path):
    # no_links is root-first and stops at a missing suffix; no leaf metadata or
    # content is inspected through an unreviewed/link ancestor.
    held = dict(stream=None, errors=[], close_confirmed=False)
    _CONFIGURE_READERS.append(held)
    data = None; truncated = False
    try:
        info = module.base.no_links(path)
        if info is not None:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
            stream = path.open('rb'); held['stream'] = stream
            opened = os.fstat(stream.fileno())
            identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink, item.st_size, item.st_mtime_ns)
            require(identity(opened) == identity(info))
            start = max(0, opened.st_size-CONFIGURE_LOG_LIMIT)
            stream.seek(start)
            data = stream.read(CONFIGURE_LOG_LIMIT)
            require(type(data) is bytes and len(data) == opened.st_size-start and len(data) <= CONFIGURE_LOG_LIMIT)
            require(identity(os.fstat(stream.fileno())) == identity(opened))
            truncated = start > 0
            if truncated:
                data = data.partition(b'\n')[2]  # Never classify the cut-off first line.
    except BaseException as error:
        held['errors'].append(error)
    if held['stream'] is not None:
        try:
            held['stream'].close()
            held['close_confirmed'] = True
        except BaseException as error:
            held['errors'].append(error)
    if held['errors']:
        require(False)  # Keep actual reader/errors privately, including a closed failed reader.
    _CONFIGURE_READERS.remove(held)
    return data, truncated


def checked_configure_context(value, module):
    keys(value, ('scope', 'logs')); require(value['scope'] == CONFIGURE_SCOPE)
    require(type(value['logs']) is list and len(value['logs']) == 2)
    labels = set(CONFIGURE_FATAL.values())
    for row, (role, _path) in zip(value['logs'], CONFIGURE_LOGS):
        keys(row, ('role', 'state', 'truncated', 'terminal', 'fatal_templates', 'probe_codes'))
        require(row['role'] == role and row['state'] in ('read', 'missing') and type(row['truncated']) is bool)
        for name, allowed in (('fatal_templates', labels), ('probe_codes', module.base.ERROR_CODES)):
            entries = row[name]
            require(type(entries) is list and len(entries) <= 64 and all(type(v) is str and v in allowed for v in entries)
                    and entries == sorted(set(entries)))
        terminal = row['terminal']
        require(type(terminal) is str and terminal in labels|{'missing', 'not-observed', 'unknown', 'conflicting', 'not-attributed'})
        if row['state'] == 'missing':
            require(terminal == 'missing' and not row['truncated'] and not row['fatal_templates'] and not row['probe_codes'])
        elif role == 'cumulative-build-output':
            require(terminal == 'not-attributed')
        else:
            require(terminal != 'missing' and terminal != 'not-attributed')
            if len(row['fatal_templates']) > 1: require(terminal == 'conflicting')
            else: require(terminal != 'conflicting')
            if terminal in labels: require(row['fatal_templates'] == [terminal])
            if terminal == 'not-observed': require(not row['fatal_templates'])
    return value


def configure_context(module, output):
    require(not _CONFIGURE_READERS)  # No second observation after retained uncertainty.
    logs = []
    for role, relative_path in CONFIGURE_LOGS:
        data, truncated = configure_log_tail(module, output/relative_path)
        row = dict(role=role, state='missing' if data is None else 'read', truncated=truncated,
                   terminal='missing', fatal_templates=[], probe_codes=[])
        if data is not None:
            # Only complete ASCII literal lines are matched. No decoding,
            # unescaping, arbitrary dependency names or regex capture is emitted.
            lines = [line[:-1] if line.endswith(b'\r') else line for line in data.split(b'\n')[:-1]]
            row['fatal_templates'] = sorted({CONFIGURE_FATAL[line] for line in lines if line in CONFIGURE_FATAL})
            # Match only the shared recognizer's fixed compiler-code format.
            # Its general category regexes are unnecessary for this projection.
            codes = {code.upper() for code in re.findall(
                r'\berror[ \t]+((?:C|D|LNK|MSB)[0-9]{4})[ \t]*:',
                b'\n'.join(lines).decode('utf-8', errors='replace'), flags=re.IGNORECASE)}
            row['probe_codes'] = sorted(codes & module.base.ERROR_CODES)
            complete = [line for line in lines if line.strip(b' \t')]
            if role == 'cumulative-build-output': row['terminal'] = 'not-attributed'
            elif len(row['fatal_templates']) > 1: row['terminal'] = 'conflicting'
            elif complete and complete[-1] in CONFIGURE_FATAL: row['terminal'] = CONFIGURE_FATAL[complete[-1]]
            elif (len(complete) >= 2 and complete[-1] == CONFIGURE_STATIC_NOTE and
                  complete[-2] == b'ERROR: opus not found using pkg-config'):
                row['terminal'] = 'opus-pkg-config-check-failed'
            else: row['terminal'] = 'unknown' if complete else 'not-observed'
            if role == 'configure-log' and data.split(b'\n')[-1].strip(b' \t\r') and row['terminal'] != 'conflicting':
                row['terminal'] = 'unknown'  # An incomplete trailing line cannot establish a terminal template.
        logs.append(row)
    return checked_configure_context(dict(scope=CONFIGURE_SCOPE, logs=logs), module)


def checked_observe_context(value):
    keys(value, ('scope','state','tail_truncated','error_family','observed_controller_signature','predicate'))
    require(type(value['scope']) is str and value['scope'] == OBSERVE_SCOPE and type(value['state']) is str and value['state'] in OBSERVE_STATES
            and type(value['tail_truncated']) is bool)
    optional = [value[n] for n in ('error_family','observed_controller_signature','predicate')]
    if value['state'] == 'known-signature':
        require(type(value['error_family']) is str and value['error_family'] == 'ValueError' and type(value['predicate']) is str
                and value['predicate'] in OBSERVE_PREDICATES and type(value['observed_controller_signature']) is str
                and value['observed_controller_signature'] in OBSERVE_PREDICATES[value['predicate']][5])
    else:
        require(all(v is None for v in optional))
        if value['state'] == 'missing': require(value['tail_truncated'] is False)
    return value


def observe_signature(data, truncated, driver_path):
    """Recognize bounded cumulative text, never authenticate execution or cause."""
    require((data is None or type(data) is bytes and len(data) <= CONFIGURE_LOG_LIMIT)
            and type(truncated) is bool and type(driver_path) is str)
    value = dict(scope=OBSERVE_SCOPE, state='missing' if data is None else 'not-observed',
                 tail_truncated=truncated, error_family=None, observed_controller_signature=None, predicate=None)
    if data is None: return checked_observe_context(value)
    header = b'Traceback (most recent call last):'
    chain_lines = {b'During handling of the above exception, another exception occurred:',
                   b'The above exception was the direct cause of the following exception:'}
    active = False; frames = []; terminal = None; predicate = None
    block_bytes = block_lines = 0; malformed = overflow = after_terminal = conflict = chained = False
    for raw in data.split(b'\n')[:-1]:
        line = raw[:-1] if raw.endswith(b'\r') else raw
        if line == header:
            conflict = active and terminal is None
            active = True; frames = []; terminal = None; predicate = None
            block_bytes = len(raw)+1; block_lines = 1
            malformed = overflow = after_terminal = False
            continue
        if not active: continue
        block_bytes += len(raw)+1; block_lines += 1
        if len(raw)+1 > 4096 or block_bytes > 32768 or block_lines > 128:
            overflow = True; frames = []; continue
        if overflow: continue
        if terminal is not None:
            if line.strip():
                if line in chain_lines: chained = True
                elif line.startswith(b'ValueError: '): conflict = True
                else: after_terminal = True
            continue
        match = OBSERVE_FRAME.fullmatch(line)
        if match:
            try: frames.append((match[1].decode('utf-8'), int(match[2]), match[3].decode('ascii')))
            except UnicodeError: malformed = True
        elif line.startswith(b'    ') and frames:
            pass  # Source/caret rows are discarded, never interpreted as errors.
        elif line.startswith(b'ValueError: '):
            terminal = 'ValueError'
            for label, row in OBSERVE_PREDICATES.items():
                if line == b'ValueError: '+row[0].encode('utf-8'): predicate = label; break
        else:
            malformed = True
            if line and not line.startswith(b' '): terminal = 'unknown'
    if not active: return checked_observe_context(value)
    if overflow or data and not data.endswith(b'\n'): value['state'] = 'truncated-block'
    elif conflict or chained: value['state'] = 'conflicting'
    elif malformed or after_terminal or terminal != 'ValueError' or predicate is None: value['state'] = 'unknown'
    else:
        row = OBSERVE_PREDICATES[predicate]
        selected = [(line, name) for path, line, name in frames if path == driver_path]
        def has_frame(name):
            lower, upper = OBSERVE_FRAME_RANGES[name]
            return any(function == name and lower <= line <= upper for line, function in selected)
        signatures = [label for label, function in [('stage-candidate','stage_candidate'),('finish-native','finish_native')] if has_frame(function)]
        final = frames[-1] if frames else None
        if (has_frame('main') and len(signatures) == 1 and signatures[0] in row[5]
                and final == (driver_path, row[4], row[1]) and row[2] <= row[4] <= row[3]):
            value.update(state='known-signature',error_family='ValueError',observed_controller_signature=signatures[0],predicate=predicate)
        else: value['state'] = 'conflicting' if len(signatures) > 1 else 'unknown'
    return checked_observe_context(value)


def observe_context(module, output):
    require(not _CONFIGURE_READERS)
    # Bind this finite catalogue before reading any private log. Paths parsed
    # from a traceback never reach filesystem operations.
    module.policy(); project_inputs(module)
    require(SHA(module.base.recipe_bytes(module._DRIVER).replace(b'\r\n',b'\n')) == OBSERVE_DRIVER_LF_SHA256)
    data, truncated = configure_log_tail(module, output/'PRIVATE-BUILD.log')
    return observe_signature(data, truncated, str(module._DRIVER))


def collect_failure(module, output, head):
    items = []
    for name in ('FAILED-STAGE.json', 'FAILED-CLI-OWNERSHIP.json'):
        if module.base.no_links(output/name) is not None:
            raw = read_json(module, output/name, 65536)
            value = projected_failure(raw, module, head)
            items.append((raw, value))
    require(len(items) == 1)
    raw, value = items[0]
    if raw['schema'] == 'proxy-r19-mp3-draft-failure-v1' and raw['phase'] == 'configure-ffmpeg':
        require(type(head) is str and re.fullmatch(r'[a-f0-9]{40}', head) and raw['source_commit'] == head)
        value['details']['configure_observation'] = configure_context(module, output)
        value['schema'] = CONFIGURE_SCHEMA
    elif raw['schema'] == 'proxy-r19-mp3-draft-failure-v1' and raw['phase'] == 'observe-and-package':
        require(type(head) is str and re.fullmatch(r'[a-f0-9]{40}', head) and raw['source_commit'] == head)
        value['details']['observe_observation'] = observe_context(module, output)
        value['schema'] = OBSERVE_SCHEMA
    return value


def load_controller(root):
    # Guard before the loader opens a source; no shared helper modifications.
    for name in ('scripts/replay-mp3-codec.py', 'scripts/replay-game-codec.py'):
        path = root/name
        for item in (*reversed(path.parents), path):
            info = item.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info,'st_file_attributes',0)&0x400)
            require(stat.S_ISREG(info.st_mode) if item == path else stat.S_ISDIR(info.st_mode))
    spec = importlib.util.spec_from_file_location('exact_mp3_observation', root/'scripts/replay-mp3-codec.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def project_inputs(module):
    files = module.project_bytes(); require(len(files) == 17)
    result = {}
    for n, raw in files.items():
        lf = raw.replace(b'\r\n', b'\n'); require(b'\r' not in lf and b'\0' not in lf)
        result[n] = dict(raw=record(raw), canonical_lf=record(lf))
    return result


def tool_summary(tools, pin):
    keys(tools, ('image_os','image_version','compiler','visual_studio_version','toolset','sdk','cmake','trees','individual'))
    require(tools['image_os'] == 'win25-vs2026' and tools['image_version'] in pin['host']['image_versions'])
    for actual, name in [('compiler','compiler_version'),('toolset','toolset_directory'),('sdk','sdk_version'),('cmake','cmake_version')]:
        require(type(tools[actual]) is str and tools[actual] == pin['host'][name])
    require(type(tools['visual_studio_version']) is str and re.fullmatch(r'18\.[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}',tools['visual_studio_version']))
    required = {'msvc-bin','msvc-include','msvc-lib-x64','sdk-bin-x64','sdk-include','sdk-ucrt-x64','sdk-um-x64','cmake','msbuild','vc-auxiliary','isolated-msys-bin'}
    optional = {'msvc-atlmfc-include','msvc-atlmfc-lib-x64','netfx-sdk-include','netfx-sdk-lib-x64'}
    require(type(tools['trees']) is dict and required <= set(tools['trees']) <= required|optional)
    for tree in tools['trees'].values(): file_map(tree, cap=100000)
    keys(tools['individual'], ('windows-tar','vswhere','cmd','python'))
    for row in tools['individual'].values(): byte_record(row)
    byte_record(tools['trees']['msvc-bin']['cl.exe'])
    # Known selected executable records only; no private tree/individual-map hash.
    return {**{k:tools[k] for k in ('image_os','image_version','compiler','visual_studio_version','toolset','sdk','cmake')},
            'compiler_executable':tools['trees']['msvc-bin']['cl.exe'],
            'observer_python':tools['individual']['python'],
            'seal_comparison':'exact-before-after-private-tree-comparison',
            'unbound_prerequisites':pin['host']['unbound_prerequisites']}


def cmake_shape(value):
    keys(value, ('schema','name','version','platform','scope','policy_sha256','archive','executable','notices','tree_sha256','regular_files','directories','runtime_collection_allowed','production_execution_allowed','source_delivery_approved','native_payload_in_source_review','native_windows_11_acceptance','r19_complete','operation'))
    require(value['schema']=='proxy-pinned-build-cmake-v1' and value['name']=='CMake' and value['version']=='4.4.5' and value['platform']=='win-x64' and value['operation']=='verified')
    require(value['scope']=='build-host-only; static byte verification, not native execution')
    require(HEX.fullmatch(value['policy_sha256']) and HEX.fullmatch(value['tree_sha256']))
    keys(value['archive'], ('filename','root','bytes','sha256','entries','regular_files','expanded_bytes'))
    require(value['archive']['filename']=='cmake-4.4.5-windows-x86_64.zip' and value['archive']['root']=='cmake-4.4.5-windows-x86_64')
    require(value['archive']['sha256']=='326c826486d46a23cf9d5a1c9ee3a567d427bdd02c4a34071937a2a675cff004')
    for k in ('bytes','entries','regular_files','expanded_bytes'): require(type(value['archive'][k]) is int and value['archive'][k]>0)
    keys(value['executable'], ('path','bytes','sha256')); relative(value['executable']['path']); byte_record({k:value['executable'][k] for k in ('bytes','sha256')})
    require(type(value['notices']) is list and 0<len(value['notices'])<=8)
    for n in value['notices']:
        keys(n, ('path','bytes','sha256')); relative(n['path']); byte_record({k:n[k] for k in ('bytes','sha256')})
    for k in ('regular_files','directories'): require(type(value[k]) is int and value[k]>0)
    for k in ('runtime_collection_allowed','production_execution_allowed','source_delivery_approved','native_payload_in_source_review','r19_complete'): require(value[k] is False)
    require(value['native_windows_11_acceptance']=='unavailable')
    require(all(serialized(value[n])==serialized(want) for n,want in CMAKE_KNOWN.items()))
    require(value['regular_files']==8817 and value['directories']==163)


def projected_native(raw, context, pin, module):
    fields = {'schema','status','source_commit','draft_base_commit','source_binding_scope','identity','source_correspondence','native_imports','loaded_origins','origin_scope','cli_child_origins','cli_scope','authored_two_tones','malformed_input','ordinary_voiced_mobile_export','runtime_integration','fft_provenance',*FLAGS}
    keys(raw, fields); checked_flags(raw)
    require(raw['schema']=='proxy-r19-mp3-functional-draft-native-v1' and raw['status']=='quarantined-build-host-probe-passed')
    require(raw['source_commit'] is None and raw['draft_base_commit']==BASE and raw['source_binding_scope']=='ignored functional draft plus exact input cohort; not clean0f evidence')
    require(type(raw['identity']) is str and re.fullmatch(r'quarantined-mp3-[a-f0-9]{64}',raw['identity']))
    cc=raw['source_correspondence']; keys(cc, context['correspondence'])
    # Equality is canonical/type-exact, including every known private inventory.
    require(serialized(cc)==serialized(context['correspondence']))
    file_map(cc['project_inputs'], [n for n in context['project_inputs']]); file_map(cc['source_review_files'], module.source_kit_names(pin))
    file_map(cc['original_sources']); file_map(cc['lame_working_inputs']); file_map(cc['lame_installed'], cap=1024)
    require(module.base.tree_identity(cc['original_sources'])==pin['original_source_tree'] and module.base.tree_identity(cc['lame_working_inputs'])==pin['lame_working_source_tree'])
    tools=tool_summary(cc['build_tools'],pin); cmake_shape(cc['cmake_supplier'])
    candidate=cc['candidate_files']; expected={*module.DLLS,'ffmpeg.exe','mp3-codec-origin.exe','notices/project/MP3-BUILD-RECIPES-LICENSE.txt'}|{'notices/'+n['component']+'/'+n['path'] for n in pin['notices']};file_map(candidate,expected)
    require(raw['native_imports']==context['native_imports']);keys(raw['native_imports'],set(module.DLLS)|{'ffmpeg.exe','mp3-codec-origin.exe'})
    for value in raw['native_imports'].values():
        keys(value, ('imports','delay_imports'))
        for names in value.values():require(type(names) is list and len(names)<=256 and all(type(n) is str and re.fullmatch(r'[A-Za-z0-9_.-]{1,255}',n) for n in names))
    keys(raw['loaded_origins'],module.DLLS)
    for n,row in raw['loaded_origins'].items():
        keys(row, ('origin','bytes','sha256'));require(row['origin']=='quarantined-candidate-observer-process' and {k:row[k] for k in ('bytes','sha256')}==candidate[n])
    require(raw['origin_scope']=='supplementary observer plus four real CLI creation-handle censuses')
    require(raw['cli_scope']=='two stable live snapshots during each authored encode/decode only; not all possible CLI paths')
    ops=raw['cli_child_origins'];require(type(ops) is list and len(ops)==4)
    for op,name in zip(ops, ('encode-440','decode-440','encode-880','decode-880')):
        keys(op, ('operation','loaded_native','scope'));require(op['operation']==name and op['scope']=='two stable snapshots of this live CLI operation only')
        rows=op['loaded_native'];require(type(rows) is list and 0<len(rows)<=128);seen=set();apps=set()
        for row in rows:
            keys(row, ('origin','file','bytes','sha256'));byte_record({k:row[k] for k in ('bytes','sha256')});require(0<row['bytes']<=64*1024*1024)
            require(type(row['file']) is str and (row['origin'],row['file'].casefold()) not in seen);seen.add((row['origin'],row['file'].casefold()))
            if row['origin']=='application':
                require(row['file'] in {*module.DLLS,'ffmpeg.exe'} and {k:row[k] for k in ('bytes','sha256')}==candidate[row['file']]);apps.add(row['file'])
            else:require(row['origin']=='windows-system-observed' and row['file'] in pin['cli_child']['system_module_allowlist'])
        require(apps==set(module.DLLS)|{'ffmpeg.exe'})
    require(raw['authored_two_tones']=='actual CLI encode/decode and forbidden-other-tone check passed')
    require(raw['malformed_input']=='rejected; previous complete output preserved' and raw['ordinary_voiced_mobile_export']=='not-run' and raw['runtime_integration']=='not-implemented' and raw['fft_provenance']=='unresolved')
    require(raw['identity']=='quarantined-mp3-'+SHA(module.canonical(cc)))
    out={'schema':'proxy-r19-mp3-ci-native-observation-v1','status':'validated-controller-native-passed',
         'source_commit':None,'draft_base_commit':BASE,'source_binding_scope':raw['source_binding_scope'],
         'project_inputs':context['project_inputs'],'source_review_files':cc['source_review_files'],
         'original_source_tree':pin['original_source_tree'],'derived_lame_tree':pin['lame_working_source_tree'],
         'source_inputs':{r['filename']:{k:r[k] for k in ('bytes','sha256')} for r in module.inputs(pin,False)},
         'project_license':cc['mp3_project_license'],'final_four_copies':cc['mp3_project_copies'],
         'candidate_files':candidate,'generated_configuration':cc['ffmpeg_generated'],
         'tool_observation':tools,'cmake_supplier':cc['cmake_supplier'],
         'native_imports':raw['native_imports'],'observer_loaded_origins':raw['loaded_origins'],
         'cli_child_origins':ops,'cli_scope':raw['cli_scope'],'authored_two_tones':raw['authored_two_tones'],
         'malformed_input':raw['malformed_input'],'ordinary_voiced_mobile_export':'not-run','runtime_integration':'not-implemented','fft_provenance':'unresolved',**FLAGS}
    require(len(serialized(out))<=PUBLIC_LIMIT);return out


def collect_native(module, root, cmake_root):
    pin=module.verify_sources(root,True);module.verify_lame_install(root)
    tools=read_json(module,root/'BUILD-TOOLS.json');require(serialized(tools)==serialized(read_json(module,root/'BUILD-TOOLS-AFTER.json')))
    spec=importlib.util.spec_from_file_location('exact_cmake_observer',module.ROOT/'scripts/pinned-build-cmake.py');cm=importlib.util.module_from_spec(spec);spec.loader.exec_module(cm);supplier=cm.verify(cmake_root)
    expected={*module.DLLS,'ffmpeg.exe','mp3-codec-origin.exe','notices/project/MP3-BUILD-RECIPES-LICENSE.txt'}|{'notices/'+n['component']+'/'+n['path'] for n in pin['notices']}
    module.base.check_named_tree(root/'candidate',expected);candidate=module.base.inventory(root/'candidate')
    config=root/'ffmpeg-build/ffbuild';module.base.check_named_tree(config,{*module.base.PUBLIC_FFMPEG_GENERATED,'config.log'})
    generated={n:record(module.base.recipe_bytes(config/n)) for n in module.base.PUBLIC_FFMPEG_GENERATED}
    cc=dict(sources=pin['sources'],original_recipes=pin['original_recipes'],notices=pin['notices'],project_inputs=read_json(module,root/'PROJECT-INPUTS.json'),mp3_project_license=module.MP3_PROJECT_LICENSE,mp3_project_copies=read_json(module,root/'source-review/MP3-BSD-COPIES.json'),source_review_files=module.base.inventory(root/'source-review'),original_sources=read_json(module,root/'PREPARED-SOURCE.json'),lame_working_inputs=read_json(module,root/'LAME-WORKING-INPUTS.json'),lame_installed=read_json(module,root/'LAME-INSTALLED.json'),build_tools=tools,cmake_supplier=supplier,ffmpeg_generated=generated,candidate_files=candidate)
    imports={n:module.base.pe_imports(module.base.bound_bytes(root/'candidate'/n,candidate[n])) for n in (*module.DLLS,'ffmpeg.exe','mp3-codec-origin.exe')}
    context=dict(correspondence=cc,project_inputs=project_inputs(module),native_imports=imports)
    return projected_native(read_json(module,root/'MP3-DRAFT-RECEIPT.json'),context,pin,module)


def projected_failure(raw, module, head):
    require(type(raw) is dict);checked_flags(raw);require(raw.get('status')=='failed')
    basic={'schema','status','phase','source_commit',*FLAGS};schema=raw.get('schema');details={}
    if schema=='proxy-r19-mp3-draft-failure-v1':
        keys(raw,basic|{'exit_code','profile_manifest','diagnostic_codes','diagnostic_categories','log_truncated','raw_log_published'})
        require(raw['phase'] in module.PHASES and type(raw['exit_code']) is int and raw['exit_code']!=0 and -(2**31)<=raw['exit_code']<2**32 and type(raw['log_truncated']) is bool and raw['raw_log_published'] is False)
        categories=set(module.base.CMAKE_CATEGORIES)|set(module.base.TOOL_CATEGORIES)|set(module.base.MAKEDEF_CATEGORIES)|{'unclassified-command-failure'}|{n for pair in module.base.ERROR_FAMILIES.values() for n in pair}
        for name,allowed in [('diagnostic_codes',module.base.ERROR_CODES),('diagnostic_categories',categories)]:require(type(raw[name]) is list and len(raw[name])<=64 and len(set(raw[name]))==len(raw[name]) and all(type(n) is str and n in allowed for n in raw[name]))
        require(raw['profile_manifest']==record(module.base.recipe_bytes(module.PIN)))
        details={k:raw[k] for k in ('exit_code','diagnostic_codes','diagnostic_categories','log_truncated')}
    elif schema=='proxy-r19-mp3-cli-cleanup-refusal-v1':
        keys(raw,basic|{'category','draft_base_commit','profile_manifest','project_inputs'})
        require(raw['phase']=='authored-cli-ownership' and raw['category']=='cleanup-unconfirmed' and raw['draft_base_commit']==BASE)
        require(raw['profile_manifest']==record(module.base.recipe_bytes(module.PIN)) and raw['project_inputs']=={n:row['raw'] for n,row in project_inputs(module).items()});details={'category':'cleanup-unconfirmed'}
    elif schema=='proxy-r19-mp3-draft-preflight-failure-v1':
        keys(raw,basic|{'draft_base_commit','input_manifest','expected_versions','observed_tools','mismatch_fields','cl_product_resource_role','raw_log_published','native_codec_built','native_codec_executed'})
        require(raw['phase']=='preflight-tool-version' and raw['draft_base_commit']==BASE and raw['raw_log_published'] is raw['native_codec_built'] is raw['native_codec_executed'] is False)
        require(raw['input_manifest']=={'path':'packaging/codecs/ffmpeg-mp3-replay.json',**record(module.base.recipe_bytes(module.PIN))})
        require(raw['expected_versions']=={'cmake':module.policy()['host']['cmake_version'],'compiler':module.policy()['host']['compiler_version']})
        keys(raw['observed_tools'],('cmake','cl'))
        for name,fields in [('cmake',('version',)),('cl',('file_version','product_version'))]:
            row=raw['observed_tools'][name];keys(row,(*fields,'bytes','sha256'));byte_record({k:row[k] for k in ('bytes','sha256')})
            for field in fields:require(type(row[field]) is str and re.fullmatch(r'[0-9]{1,6}(?:\.[0-9]{1,6}){'+('2' if name=='cmake' else '3')+'}',row[field]))
        mismatches=[]
        if raw['observed_tools']['cmake']['version']!=raw['expected_versions']['cmake']:mismatches.append('cmake-version')
        if raw['observed_tools']['cl']['file_version']!=raw['expected_versions']['compiler']:mismatches.append('cl-file-resource-version')
        require(mismatches and raw['mismatch_fields']==mismatches and raw['cl_product_resource_role']=='observation-only; compiler identification is not inferred from resource versions')
        details={k:raw[k] for k in ('expected_versions','observed_tools','mismatch_fields')}
    elif schema=='proxy-r19-mp3-codec-replay-toolchain-preflight-failure-v2':
        keys(raw,basic|{'input_manifest','search_paths','raw_log_published','native_codec_built','native_codec_executed'})
        require(raw['phase']=='preflight-compiler-search-path' and raw['raw_log_published'] is raw['native_codec_built'] is raw['native_codec_executed'] is False)
        require(raw['input_manifest']=={'path':'packaging/codecs/ffmpeg-mp3-replay.json',**record(module.base.recipe_bytes(module.PIN))})
        rows=raw['search_paths'];require(type(rows) is list and len(rows)==2);seen=set();failed=False
        roles={'unclassified','msvc-include','msvc-atlmfc-include','sdk-include','netfx-include','msvc-lib-x64','msvc-atlmfc-lib-x64','sdk-ucrt-lib-x64','sdk-um-lib-x64','netfx-lib-x64','vc-auxiliary-include','netfx-other','sdk-other','msvc-other'}
        for row in rows:
            keys(row,('kind','state','entry_count','entries'));require(row['kind'] in ('INCLUDE','LIB') and row['kind'] not in seen);seen.add(row['kind'])
            require(row['state'] in ('checked','unavailable','value-limit','entry-limit') and type(row['entry_count']) is int and 0<=row['entry_count']<=64 and type(row['entries']) is list and len(row['entries'])==row['entry_count'])
            require((row['state']!='checked' or row['entry_count']>0) and (row['state'] not in ('unavailable','value-limit') or row['entry_count']==0) and (row['state']!='entry-limit' or row['entry_count']==64));failed|=row['state']!='checked'
            for entry in row['entries']:
                keys(entry,('component_role','exists','disposition','netfx_sdk_version','netfx_search_role'))
                require(entry['component_role'] in roles and (entry['exists'] is None or type(entry['exists']) is bool) and entry['disposition'] in ('accepted','outside-declared-roots','missing-directory','empty-entry','invalid-entry','inspection-error'))
                require((entry['disposition']!='accepted' or entry['exists'] is True) and (entry['disposition']!='missing-directory' or entry['exists'] is False))
                require((entry['netfx_sdk_version'] is None)==(entry['netfx_search_role'] is None))
                if entry['netfx_sdk_version'] is not None:require(entry['component_role'] in ('netfx-include','netfx-lib-x64','netfx-other') and type(entry['netfx_sdk_version']) is str and re.fullmatch(r'[0-9]{1,6}(?:\.[0-9]{1,6}){1,3}',entry['netfx_sdk_version']) and entry['netfx_search_role'] in ('include-um','lib-um-x64'))
                failed|=entry['disposition']!='accepted'
        require(failed);details={'search_paths':rows}
    else:
        # Other private schemas cannot become an approximate public diagnosis.
        require(False)
    require(raw['source_commit'] is None or raw['source_commit']==head)
    return dict(schema='proxy-r19-mp3-ci-failure-v1',status='failed',producer_schema=schema,phase=raw['phase'],controller_source_commit=raw['source_commit'],draft_base_commit=BASE,details=details,**FLAGS)


def public_native_shape(module,value):
    pin=module.policy();expected={'schema','status','source_commit','draft_base_commit','source_binding_scope','project_inputs','source_review_files','original_source_tree','derived_lame_tree','source_inputs','project_license','final_four_copies','candidate_files','generated_configuration','tool_observation','cmake_supplier','native_imports','observer_loaded_origins','cli_child_origins','cli_scope','authored_two_tones','malformed_input','ordinary_voiced_mobile_export','runtime_integration','fft_provenance',*FLAGS}
    keys(value,expected);checked_flags(value)
    require(value['schema']=='proxy-r19-mp3-ci-native-observation-v1' and value['status']=='validated-controller-native-passed' and value['source_commit'] is None and value['draft_base_commit']==BASE and value['source_binding_scope']=='ignored functional draft plus exact input cohort; not clean0f evidence')
    require(serialized(value['project_inputs'])==serialized(project_inputs(module)))
    require(value['original_source_tree']==pin['original_source_tree'] and value['derived_lame_tree']==pin['lame_working_source_tree'])
    require(value['source_inputs']=={r['filename']:{k:r[k] for k in ('bytes','sha256')} for r in module.inputs(pin,False)})
    file_map(value['source_review_files'],module.source_kit_names(pin));file_map(value['generated_configuration'],module.base.PUBLIC_FFMPEG_GENERATED)
    for n,row in value['project_inputs'].items():require(value['source_review_files']['project-orchestration/'+n]==row['raw'])
    for n,row in value['source_inputs'].items():require(value['source_review_files']['original-inputs/'+n]==row)
    require(serialized(value['project_license'])==serialized(module.MP3_PROJECT_LICENSE) and serialized(value['final_four_copies'])==serialized(module.mp3_copy_inventory(module.project_bytes(),pin)))
    names={*module.DLLS,'ffmpeg.exe','mp3-codec-origin.exe','notices/project/MP3-BUILD-RECIPES-LICENSE.txt'}|{'notices/'+n['component']+'/'+n['path'] for n in pin['notices']};candidate=value['candidate_files'];file_map(candidate,names)
    for n in pin['notices']:require(candidate['notices/'+n['component']+'/'+n['path']]=={k:n[k] for k in ('bytes','sha256')})
    require(candidate['notices/project/MP3-BUILD-RECIPES-LICENSE.txt']=={k:module.MP3_PROJECT_LICENSE['grant'][k] for k in ('bytes','sha256')})
    tool=value['tool_observation'];keys(tool,('image_os','image_version','compiler','visual_studio_version','toolset','sdk','cmake','compiler_executable','observer_python','seal_comparison','unbound_prerequisites'))
    require(tool['image_os']=='win25-vs2026' and tool['image_version'] in pin['host']['image_versions'] and tool['seal_comparison']=='exact-before-after-private-tree-comparison' and tool['unbound_prerequisites']==pin['host']['unbound_prerequisites'])
    for actual,name in [('compiler','compiler_version'),('toolset','toolset_directory'),('sdk','sdk_version'),('cmake','cmake_version')]:require(tool[actual]==pin['host'][name])
    require(type(tool['visual_studio_version']) is str and re.fullmatch(r'18\.[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}',tool['visual_studio_version']));byte_record(tool['compiler_executable']);byte_record(tool['observer_python']);cmake_shape(value['cmake_supplier'])
    require(value['cmake_supplier']['policy_sha256']==value['project_inputs']['packaging/build-tools/cmake-4.4.5-windows-x64.json']['raw']['sha256'])
    keys(value['native_imports'],set(module.DLLS)|{'ffmpeg.exe','mp3-codec-origin.exe'})
    for row in value['native_imports'].values():
        keys(row,('imports','delay_imports'))
        for names in row.values():require(type(names) is list and len(names)<=256 and all(type(n) is str and re.fullmatch(r'[A-Za-z0-9_.-]{1,255}',n) for n in names))
    keys(value['observer_loaded_origins'],module.DLLS)
    for n,row in value['observer_loaded_origins'].items():keys(row,('origin','bytes','sha256'));require(row['origin']=='quarantined-candidate-observer-process' and {k:row[k] for k in ('bytes','sha256')}==candidate[n])
    ops=value['cli_child_origins'];require(type(ops) is list and len(ops)==4)
    for op,name in zip(ops,('encode-440','decode-440','encode-880','decode-880')):
        keys(op,('operation','loaded_native','scope'));require(op['operation']==name and op['scope']=='two stable snapshots of this live CLI operation only');rows=op['loaded_native'];require(type(rows) is list and 0<len(rows)<=128);seen=set();apps=set()
        for row in rows:
            keys(row,('origin','file','bytes','sha256'));byte_record({k:row[k] for k in ('bytes','sha256')});require(0<row['bytes']<=64*1024*1024 and type(row['file']) is str and (row['origin'],row['file'].casefold()) not in seen);seen.add((row['origin'],row['file'].casefold()))
            if row['origin']=='application':require(row['file'] in {*module.DLLS,'ffmpeg.exe'} and {k:row[k] for k in ('bytes','sha256')}==candidate[row['file']]);apps.add(row['file'])
            else:require(row['origin']=='windows-system-observed' and row['file'] in pin['cli_child']['system_module_allowlist'])
        require(apps==set(module.DLLS)|{'ffmpeg.exe'})
    require(value['cli_scope']=='two stable live snapshots during each authored encode/decode only; not all possible CLI paths' and value['authored_two_tones']=='actual CLI encode/decode and forbidden-other-tone check passed' and value['malformed_input']=='rejected; previous complete output preserved' and value['ordinary_voiced_mobile_export']=='not-run' and value['runtime_integration']=='not-implemented' and value['fft_provenance']=='unresolved')


def public_failure_shape(module,value,head):
    keys(value,('schema','status','producer_schema','phase','controller_source_commit','draft_base_commit','details',*FLAGS));checked_flags(value)
    require(value['schema'] in ('proxy-r19-mp3-ci-failure-v1', CONFIGURE_SCHEMA, OBSERVE_SCHEMA) and value['status']=='failed' and value['draft_base_commit']==BASE)
    # Rebuild only a closed private-schema object, then reuse its exact projector.
    schema=value['producer_schema'];details=value['details'];raw={'schema':schema,'status':'failed','phase':value['phase'],'source_commit':value['controller_source_commit'],**FLAGS}
    manifest=record(module.base.recipe_bytes(module.PIN))
    if value['schema'] == CONFIGURE_SCHEMA:
        require(schema == 'proxy-r19-mp3-draft-failure-v1' and value['phase'] == 'configure-ffmpeg'
                and type(head) is str and re.fullmatch(r'[a-f0-9]{40}', head) and value['controller_source_commit'] == head)
        keys(details, ('exit_code','diagnostic_codes','diagnostic_categories','log_truncated','configure_observation'))
        checked_configure_context(details['configure_observation'], module)
        details = {n:v for n,v in details.items() if n != 'configure_observation'}
    if value['schema'] == OBSERVE_SCHEMA:
        require(schema == 'proxy-r19-mp3-draft-failure-v1' and value['phase'] == 'observe-and-package'
                and type(head) is str and re.fullmatch(r'[a-f0-9]{40}', head) and value['controller_source_commit'] == head)
        keys(details, ('exit_code','diagnostic_codes','diagnostic_categories','log_truncated','observe_observation'))
        checked_observe_context(details['observe_observation'])
        details = {n:v for n,v in details.items() if n != 'observe_observation'}
    if schema=='proxy-r19-mp3-draft-failure-v1':keys(details,('exit_code','diagnostic_codes','diagnostic_categories','log_truncated'));raw.update(details,profile_manifest=manifest,raw_log_published=False)
    elif schema=='proxy-r19-mp3-cli-cleanup-refusal-v1':keys(details,('category',));raw.update(details,draft_base_commit=BASE,profile_manifest=manifest,project_inputs={n:r['raw'] for n,r in project_inputs(module).items()})
    elif schema=='proxy-r19-mp3-draft-preflight-failure-v1':
        keys(details,('expected_versions','observed_tools','mismatch_fields'));raw.update(details,draft_base_commit=BASE,input_manifest={'path':'packaging/codecs/ffmpeg-mp3-replay.json',**manifest},cl_product_resource_role='observation-only; compiler identification is not inferred from resource versions',raw_log_published=False,native_codec_built=False,native_codec_executed=False)
    elif schema=='proxy-r19-mp3-codec-replay-toolchain-preflight-failure-v2':keys(details,('search_paths',));raw.update(details,input_manifest={'path':'packaging/codecs/ffmpeg-mp3-replay.json',**manifest},raw_log_published=False,native_codec_built=False,native_codec_executed=False)
    else:require(False)
    projected = projected_failure(raw,module,head)
    if value['schema'] == CONFIGURE_SCHEMA:
        projected['schema'] = CONFIGURE_SCHEMA
        projected['details']['configure_observation'] = value['details']['configure_observation']
    if value['schema'] == OBSERVE_SCHEMA:
        projected['schema'] = OBSERVE_SCHEMA
        projected['details']['observe_observation'] = value['details']['observe_observation']
    require(serialized(projected)==serialized(value))


def publication_values(module,values):
    require(not _CONFIGURE_READERS)
    require(type(values) is dict)
    success=set(values)=={'MP3-DRAFT-RECEIPT.json','MP3-CI-BINDING.json'}
    require(success or set(values)=={'MP3-FAILURE.json','MP3-CI-BINDING.json'})
    name='MP3-DRAFT-RECEIPT.json' if success else 'MP3-FAILURE.json';value=values[name];binding=values['MP3-CI-BINDING.json']
    keys(binding,('schema','status','source_commit','source_hash','source_before_after','run_id','run_attempt','controller_source_commit','draft_base_commit','project_inputs','native_receipt','private_original_receipt_hash_published',*FLAGS));checked_flags(binding)
    require(binding['schema']=='proxy-r19-mp3-ci-binding-v1' and binding['status']==('source-bound-native-observation' if success else 'source-bound-failed-observation') and type(binding['source_commit']) is str and re.fullmatch(r'[a-f0-9]{40}',binding['source_commit']) and type(binding['source_hash']) is str and HEX.fullmatch(binding['source_hash']))
    require(binding['source_before_after']=='equal-verified' and binding['draft_base_commit']==BASE and binding['private_original_receipt_hash_published'] is False)
    require(type(binding['run_id']) is str and re.fullmatch(r'[1-9][0-9]{0,19}',binding['run_id']) and type(binding['run_attempt']) is str and re.fullmatch(r'[1-9][0-9]{0,5}',binding['run_attempt']))
    require(serialized(binding['project_inputs'])==serialized(project_inputs(module)))
    require(binding['native_receipt']=={'file':name,**record(serialized(value))})
    checked_flags(value)
    if success:
        public_native_shape(module,value);require(binding['controller_source_commit'] is None)
    else:
        public_failure_shape(module,value,binding['source_commit']);require(value['controller_source_commit']==binding['controller_source_commit'])
    return name


def guarded_directory(module,base):
    directory=base/'output/checks/r19-mp3-published';module.base.no_links(directory)
    for parent in (base/'output',base/'output/checks',directory):
        info=module.base.no_links(parent)
        if info is None:parent.mkdir()
        else:require(stat.S_ISDIR(info.st_mode))
    return directory


def source_state(module,base,value=None):
    directory=guarded_directory(module,base);path=directory/'PRIVATE-SOURCE-START.json'
    if value is None:return read_json(module,path,PUBLIC_LIMIT)
    keys(value,('schema','source','project_inputs'));require(value['schema']=='proxy-r19-mp3-ci-start-v1' and serialized(value['project_inputs'])==serialized(project_inputs(module)))
    require(module.base.no_links(path) is None)
    with path.open('xb') as f:f.write(serialized(value))
    require(read_json(module,path,PUBLIC_LIMIT)==value)
    return 'START_WRITTEN'


def read_pair(module,base,values):
    publication_values(module,values);directory=guarded_directory(module,base)
    require({p.name for p in directory.iterdir()} <= set(values)|{'PRIVATE-SOURCE-START.json'})
    for n,v in values.items():
        data=serialized(v);info=module.base.regular_file(directory/n);require(info.st_nlink==1 and info.st_size==len(data) and len(data)<=PUBLIC_LIMIT)
        with (directory/n).open('rb') as stream:require(stream.read(len(data)+1)==data)
    return 'PAIR_VERIFIED'


def publish_pair(module, base, values):
    publication_values(module,values);directory=guarded_directory(module,base)
    require({p.name for p in directory.iterdir()} <= {'PRIVATE-SOURCE-START.json'})
    for n in values:require(module.base.no_links(directory/n) is None)
    held={n:serialized(v) for n,v in values.items()};require(sum(map(len,held.values()))<=2*PUBLIC_LIMIT)
    for n,data in held.items():
        require(len(data)<=PUBLIC_LIMIT);module.base.no_links(directory/n)
        with (directory/n).open('xb') as stream:stream.write(data)
    for n,data in held.items():
        info=module.base.regular_file(directory/n);require(info.st_nlink==1 and info.st_size==len(data))
        with (directory/n).open('rb') as stream:require(stream.read(len(data)+1)==data)
    return 'PAIR_WRITTEN'


def main():
    command,root,*args=sys.argv[1:];root=Path(root).absolute();module=load_controller(root)
    if command=='snapshot':
        require(sys.version_info[:3]==(3,12,10));value={'schema':'proxy-r19-mp3-project-inputs-v1','project_inputs':project_inputs(module)}
    elif command=='observe':value=collect_native(module,Path(args[0]),Path(args[1]))
    elif command=='failure':value=collect_failure(module,Path(args[0]),args[1])
    elif command in ('save-start','publish','read-pair'):
        data=sys.stdin.buffer.read(2*PUBLIC_LIMIT+1);require(len(data)<=2*PUBLIC_LIMIT);value=json.loads(data,object_pairs_hook=unique);require(type(value) is dict)
        if command=='save-start':print(source_state(module,root,value))
        elif command=='publish':print(publish_pair(module,root,value))
        else:print(read_pair(module,root,value))
        return
    elif command=='read-start':value=source_state(module,root)
    else:require(False)
    raw=serialized(value);require(len(raw)<=PUBLIC_LIMIT);sys.stdout.buffer.write(raw)

if __name__=='__main__':
    try:main()
    except BaseException:
        # No traceback, exception text, argv, raw path, log or original hash.
        sys.stdout.write('{"schema":"proxy-r19-mp3-observer-failure-v1","status":"failed","reason":"unavailable"}\n');sys.exit(1)
