// Original format software: named native declarations, serialized field order,
// AssetPath layout and the publisher's typed config importer. No assets or keys.
import {readOdinEntries} from './zzz-dialogue.mjs';
import {unityObjects} from './cinematic-links.mjs';

// Foundation.AssetPathConstants.AUTO_META_CONFIG_PATH, read from its original
// initializer. This is a public resource identity, not cryptographic material.
export const AUTO_META_CONFIG_ASSET = 1610532460454092920n;
const utf8 = new TextDecoder('utf-8', {fatal:true});
const scalarFields = new Set(['abilityRegistryConfigPath', 'graphRegistryConfigPath',
  'levelGroupRegistryConfigPath', 'voSeqRegistryConfigPath']);
// Frozen serialized declaration schema; entries and array lengths come from
// each newly selected publisher config, without any per-scene list.
export const AUTO_CONFIG_FIELDS = `
  postprocessColorAdjustmentsPathes postprocessColorAdjustmentsPathes_NewVersion postprocessDepthOfFieldPathes
  postprocessDepthOfFieldPathes_NewVersion postprocessFXColorCorrectionPathes postprocessFXColorCorrectionPathes_NewVersion
  postprocessGaussianBlurPathes postprocessGaussianBlurPathes_NewVersion postprocessGlitchPathes
  postprocessGlitchPathes_NewVersion postprocessRadialBlurPathes postprocessRadialBlurPathes_NewVersion
  postprocessScreenEffectsPathes postprocessScreenEffectsPathes_NewVersion postprocessVignettePathes
  postprocessVignettePathes_NewVersion postprocessCharacterColorCorrectionPathes postprocessCharacterColorCorrectionPathes_NewVersion
  postprocessChromaticAberrationPathes postprocessChromaticAberrationPathes_NewVersion postprocessDirectionalBlurPathes
  postprocessDirectionalBlurPathes_NewVersion postprocessFilmGrainPathes postprocessFilmGrainPathes_NewVersion
  postprocessLensDistortionPathes postprocessLensDistortionPathes_NewVersion postprocessNapBloomPathes
  postprocessNapBloomPathes_NewVersion postprocessFXFogPathes postprocessFXFogPathes_NewVersion
  postprocessOldCRTPathes postprocessOldCRTPathes_NewVersion postprocessDistortionPathes
  postprocessDistortionPathes_NewVersion postprocessVREffectsPathes postprocessVREffectsPathes_NewVersion
  postprocessLensDirtPathes postprocessLensDirtPathes_NewVersion postprocessMotionBlurPathes
  postprocessMotionBlurPathes_NewVersion postprocessCharacterIgnisFatuusPathes postprocessCharacterIgnisFatuusPathes_NewVersion
  postprocessMonsterIgnisFatuusPathes postprocessMonsterIgnisFatuusPathes_NewVersion postprocessUnsharpMaskPathes
  postprocessUnsharpMaskPathes_NewVersion postprocessColorLookupPathes postprocessColorLookupPathes_NewVersion
  postprocessFXComicDotPathes postprocessFXComicDotPathes_NewVersion postprocessAutoExposurePathes
  postprocessAutoExposurePathes_NewVersion postprocessScreenSpaceAmbientOcclusionPathes postprocessScreenSpaceAmbientOcclusionPathes_NewVersion
  postprocessAmplifyOcclusionPathes postprocessAmplifyOcclusionPathes_NewVersion postprocessCausticsPathes
  postprocessCausticsPathes_NewVersion postprocessChannelMixerPathes postprocessChannelMixerPathes_NewVersion
  postprocessCharacterVolumeProxyPathes postprocessCharacterVolumeProxyPathes_NewVersion postprocessColorCurvesPathes
  postprocessColorCurvesPathes_NewVersion postprocessCullingPathes postprocessCullingPathes_NewVersion
  postprocessLiftGammaGainPathes postprocessLiftGammaGainPathes_NewVersion postprocessLightingPathes
  postprocessLightingPathes_NewVersion postprocessNapCapsuleAOLightingPathes postprocessNapCapsuleAOLightingPathes_NewVersion
  postprocessNapContactShadowPathes postprocessNapContactShadowPathes_NewVersion postprocessPaniniProjectionPathes
  postprocessPaniniProjectionPathes_NewVersion postprocessPartialBlurPathes postprocessPartialBlurPathes_NewVersion
  postprocessScreenSpacePlanarReflectionPathes postprocessScreenSpacePlanarReflectionPathes_NewVersion postprocessScreenSpaceReflectionPathes
  postprocessScreenSpaceReflectionPathes_NewVersion postprocessShadowsMidtonesHighlightsPathes postprocessShadowsMidtonesHighlightsPathes_NewVersion
  postprocessSplitToningPathes postprocessSplitToningPathes_NewVersion postprocessTonemappingPathes
  postprocessTonemappingPathes_NewVersion postprocessWhiteBalancePathes postprocessWhiteBalancePathes_NewVersion
  shaderCustomFogPathes abilityRegistryConfigPath graphRegistryConfigPath
  levelGroupRegistryConfigPath voSeqRegistryConfigPath dynamicObjectRegistryPathes
  logicMovementDataPathes logicRotationDataPathes animationCurveLibraryPaths
  timelineDataPathes timelineDataExtraPathes languageVideoDataPaths
  noiseDataPathes cameraScreenOffsetPathes cameraShakePathes
  cameraZoomPathes cameraStretchPathes cameraLockTargetPathes
  cameraCutScenePathes cameraCutsceneGroupPathes lockTargetPathes
  entitySkillPathes interactEntryPathes sharedAnimEventsPathes
  commonAnimEventsPathes timeSlowPathes windFieldPathes
  dropItemEffectPathes levelDesignAssetPathes levelGlobalAIPathes
  levelGlobalCounterstrokePathes levelReviveConfigPathes hitDataPathes
  glitchEffectPathes vignettePathes radialBlurPathes
  gaussianBlurPathes depthOfFieldPathes screenEffectsPathes
  lensDistortionPathes chromaticAberrationPathes runStatePathes
  effectLODDataConfigPaths colorAdjustmentsPathes fXColorCorrectionsPathes
  filmGrainPathes avatarColorCorrectionsPathes materialPropertyModifierPathes
  materialPropertyModifierPathes_New araTrailConfigPathes flowCanvasConfigPathes
  teamEntityConfigPathes uiAvatarShowSettingsPaths uiBuddyShowSettingsPaths
  galGameAvatarShowSettingsPaths scriptableAnimationV2Paths gamepadRumblePaths
  realtimeQTEConfigPaths overShoulderCameraConfigPaths avatarLayoutCameraConfigPaths
  globalSoundActionPaths npcCrowdJsonPaths npcCrowdAssetSoPaths
  npcCrowdAnimationSoPaths textureConfigPaths cameraOverrideTrackPaths
  cameraBangbooAdjustmentPaths chessboardPluginRegistryPathes chessboardEntityRegistryPaths
  dynamicOverrideWeatherPaths bigSceneCommonSkillPaths bigSceneGroupEntityPriorityPaths
  dynamicCheckTreePaths GroupChallengeConfigRegistryPaths LevelWeatherPaths
  CinemaSingleBeatMapConfigPath SurfGameItemDataConfigPaths GraphInteractConfigPaths
  AbilityTargetDataConfigPaths simpleMoveConfigPaths SlideRopeCameraConfigPaths
  SlideRopeLockCameraConfigPaths SlideRopePatternConfigPaths HighLightAirCombatConfigPaths
  HighLightAirCombatCameraConfigPaths
`.trim().split(/\s+/);

function objectReader(bytes) {
  let p = 0;
  const need = count => { if (!Number.isSafeInteger(count) || count < 0 || p + count > bytes.length) throw Error('Truncated ZZZ presentation configuration'); };
  const integer = () => { need(4); const value = bytes.readUInt32LE(p); p += 4; return value; };
  const string = () => {
    const size = integer(); if (size > 4096) throw Error('ZZZ configuration string exceeds bounds');
    need(size); const value = utf8.decode(bytes.subarray(p, p + size)); p = Math.ceil((p + size) / 4) * 4; need(0); return value;
  };
  const zero = count => { need(count); if (bytes.subarray(p, p + count).some(byte => byte)) throw Error('Unsupported inherited ZZZ serialization data'); p += count; };
  const path = () => { const name = string(); need(8); const hash = bytes.readBigUInt64LE(p); p += 8; return {path:name, hash:hash.toString()}; };
  need(28); p = 28; const name = string();
  return {integer, string, zero, path, name, get position() { return p; },
    seek(value) { if (!Number.isSafeInteger(value) || value < p || value > bytes.length) throw Error('Invalid ZZZ configuration boundary'); p = value; }};
}

export function autoPresentationConfig(bytes) {
  const r = objectReader(bytes);
  if (r.name !== 'NewAutoConfigMetaConfig') throw Error('Unexpected ZZZ presentation root');
  // Empty inherited Sirenix SerializationData: format, byte vector and its
  // references/prefab/node fields. This object uses Unity-serialized AssetPaths.
  r.zero(40);
  const fields = Object.create(null);
  for (const name of AUTO_CONFIG_FIELDS) {
    if (scalarFields.has(name)) fields[name] = r.path();
    else {
      const count = r.integer(); if (count > 100000) throw Error('ZZZ configuration array exceeds bounds');
      fields[name] = Array.from({length:count}, () => r.path());
    }
  }
  if (r.position !== bytes.length) throw Error('Changed ZZZ auto-config schema');
  return fields;
}

export function typedPresentationObjects(cab, expected) {
  const objects = unityObjects(Buffer.from(cab)), found = [];
  for (const object of objects.values()) {
    if (object.kind !== 114 || object.bytes.length < 32) continue;
    const bytes = object.bytes;
    if (bytes.readInt32LE(16) !== 0) continue;
    const script = objects.get(bytes.readBigInt64LE(20).toString());
    if (!script || script.kind !== 115) continue;
    const length = script.bytes.readUInt32LE(0), start = Math.ceil((4 + length) / 4) * 4 + 20;
    if (start + 4 > script.bytes.length) throw Error('Truncated ZZZ MonoScript');
    const size = script.bytes.readUInt32LE(start), end = start + 4 + size;
    if (end > script.bytes.length) throw Error('Truncated ZZZ MonoScript class');
    const type = utf8.decode(script.bytes.subarray(start + 4, end));
    let p = Math.ceil(end / 4) * 4;
    const scriptString = () => { if (p + 4 > script.bytes.length) throw Error('Truncated ZZZ MonoScript identity');
      const length = script.bytes.readUInt32LE(p); p += 4;
      if (length > 1024 || p + length > script.bytes.length) throw Error('Invalid ZZZ MonoScript identity');
      const value = utf8.decode(script.bytes.subarray(p, p + length)); p = Math.ceil((p + length) / 4) * 4; return value; };
    const namespace = scriptString(), assembly = scriptString();
    if (expected.has(type) && namespace === 'MoleMole' && assembly === 'Logic.dll') found.push({type, bytes});
  }
  return found;
}

export function presentationDictionary(bytes, kind) {
  const r = objectReader(bytes);
  if (r.integer() !== 0) throw Error('Unsupported ZZZ presentation serialization format');
  const size = r.integer(), start = r.position, end = start + size;
  if (!size || size > 32 * 1024 * 1024 || end > bytes.length) throw Error('Invalid ZZZ presentation payload');
  const decoded = readOdinEntries(bytes.subarray(0, end), start, {numbers:true});
  const itemType = kind === 'timeline' ? 'TimelineData' : 'LanguageVideo';
  const rootName = kind === 'timeline' ? 'timelineDatas' : 'configVideos';
  if (decoded.end !== end || decoded.root?.name !== rootName ||
      decoded.root.type !== `System.Collections.Generic.Dictionary\`2[[System.String, mscorlib],[MoleMole.${itemType}, Logic]], mscorlib`) throw Error('Changed ZZZ presentation dictionary');
  r.seek(Math.ceil(end / 4) * 4); r.zero(32);
  const priority = kind === 'timeline' ? (r.integer() | 0) : 0;
  if (r.position !== bytes.length) throw Error('Trailing ZZZ presentation configuration');
  const entries = [], keys = new Set();
  for (const node of decoded.nodes) if (Object.hasOwn(node.fields, '$k') && node.fields.$v?.type &&
      new RegExp(`^MoleMole\\.(?:${kind === 'timeline' ? 'RuntimeTimelineData|ChatPlusTimelineData|TimelineData' : 'LanguageVideo'}), Logic$`).test(node.fields.$v.type)) {
    const key = node.fields.$k;
    if (typeof key !== 'string' || key.length > 2048 || keys.has(key)) throw Error('Invalid or duplicate ZZZ presentation key');
    keys.add(key); const fields = node.fields.$v.fields;
    if (kind === 'timeline') {
      const paths = Object.fromEntries(['_resPath', '_audioResPath', 'timelineResPath', 'timelineResPathFemale'].map(name => {
        const value = fields[name]; if (value !== null && typeof value !== 'string' || typeof value === 'string' && value.length > 2048) throw Error('Invalid authored ZZZ timeline path');
        return [name, value || ''];
      }));
      entries.push({key, priority, type:node.fields.$v.type, paths});
    } else entries.push({key, fields});
  }
  if (entries.length !== decoded.root.arrayLength) throw Error('Incomplete ZZZ presentation dictionary entries');
  return {priority, entries};
}

export function timelineOwners(entries, keys) {
  const wanted = new Set(keys), selected = new Map(), conflicts = new Set();
  const binding = row => JSON.stringify([row.type, ...['_resPath', '_audioResPath', 'timelineResPath', 'timelineResPathFemale'].map(name => row.paths[name])]);
  for (const row of entries) {
    if (!wanted.has(row.key)) continue;
    const old = selected.get(row.key);
    // Original importer sorts ascending and inserts only absent keys. Equal
    // priorities use an unstable sort, so conflicting bindings stay unresolved.
    if (!old || row.priority < old.priority) { selected.set(row.key, row); conflicts.delete(row.key); }
    else if (row.priority === old.priority && binding(row) !== binding(old)) conflicts.add(row.key);
  }
  const owners = [...selected.values()].filter(row => !conflicts.has(row.key));
  return {owners, coverage:{configured_keys:wanted.size, original_owners:owners.length,
    unresolved_keys:[...wanted].filter(key => !selected.has(key)).sort(),
    ambiguous_equal_priority_keys:[...conflicts].sort(), current_use:'unclassified',
    subtitle_audio_acquisition:'not-implemented'}};
}
