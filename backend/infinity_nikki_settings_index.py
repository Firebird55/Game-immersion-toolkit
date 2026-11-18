"""Native-compatible configuration indices and inert settings-member sizing."""
import re

from .game_data_protocol import GameDataError,GameDataPlan
from . import infinity_nikki_configuration_stage as configuration
from . import infinity_nikki_build_stage as build


def selection(provider,handle,ctx):
    """Verify this Global archive independently; never persist derived material."""
    from .infinity_nikki_pak import Archive
    from .infinity_nikki_pak_material import extract_default_pak_material
    receipt,artifact,_=configuration._retained(provider,handle,ctx)
    row=receipt['files'][0]
    configuration._check(row['name'].endswith('.pak'))
    path=configuration._path(ctx,row['sha256'],'data')
    pak=path.read_bytes()
    configuration._check(len(pak)>=221)
    if pak[-221:-205]!=bytes(16):
        raise GameDataError('publisher_dynamic_keychain_unresolved',
            'This configuration archive requires its current dynamic keychain. Existing data is retained.',409)
    build_receipt=build._read(ctx,artifact['build_handle']['receipt_sha256'])
    build_artifact=build._read(ctx,build_receipt['artifact_sha256'])
    sdk_receipt,_,_=build.sdk._retained(build_artifact['sdk_handle'],ctx)
    foundation=build._foundation()
    native_receipt=foundation._retained(sdk_receipt['native_handle'],ctx)
    native_path=foundation._path(ctx,native_receipt['module_sha256']+'.so')
    ctx.check()
    try:
        material=extract_default_pak_material(native_path.read_bytes(),expected_native_sha256=native_receipt['module_sha256'])
        archive=Archive(lambda at,size:pak[at:at+size],len(pak),material,
            crypto=foundation._crypto(provider.platform,provider.native))
    except ValueError as error:
        raise GameDataError('publisher_configuration_index_unresolved',
            'The current official configuration index or native parameter still needs verification. Existing data is retained.',409) from error
    ctx.check()
    # The original native config category determines the filename suffix. No
    # regional label, edition mapping or list of CustomConfig variants is used.
    pattern=r'X6Game/Config/(?:DefaultX6PackageSettings\.ini|Windows/(?:Custom/[A-Za-z0-9_-]+/)?WindowsX6PackageSettings\.ini)'
    paths=sorted(path for path in archive.locations if re.fullmatch(pattern,path))
    if not paths or len(paths)>256:
        raise GameDataError('publisher_configuration_members_unresolved',
            'The current configuration settings members still need verification.',409)
    entries=[archive.entry(path) for path in paths]
    decoded=sum(entry.expanded_bytes for entry in entries)
    configuration._check(0<decoded<=1024**2 and all(entry.expanded_bytes<=128*1024 for entry in entries))
    methods=sorted({archive.methods[entry.method] for entry in entries})
    return row,archive,paths,entries,decoded,methods


def plan_members(provider,handle,ctx):
    row,archive,paths,entries,decoded,methods=selection(provider,handle,ctx)
    from . import infinity_nikki_settings_stage
    compression=infinity_nikki_settings_stage.compression(provider,methods)
    if compression is not None:
        return infinity_nikki_settings_stage.begin(provider,handle,ctx,
            selected=(row,archive,paths,entries,decoded,methods),codec=compression)
    message=(f'The current native-compatible configuration indices verify {len(paths)} settings members '
        f'({decoded} decoded bytes; compression: {", ".join(methods)}). '
        'An owned host decoder and ordered settings/profile/keychain preparation are still required. '
        'No settings member has been decoded or language library activated.')
    # No source/PATH/Android fallback may substitute for the accepted capability.
    return GameDataPlan('global-settings-members-'+row['sha256'][:16],0,decoded,handle,
        stage='global-configuration-source',message=message)
