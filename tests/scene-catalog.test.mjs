import assert from 'node:assert/strict';
import test from 'node:test';
import { sceneAssetPaths } from '../scripts/scene-catalog.mjs';

test('comic and dialogue references use their authored namespaces across table field changes', () => {
  const table = { changingKey: [{ otherKey: 'Data/ScriptConfig/Comic/Test_Comic.asset' },
    { nested: ['Data/ScriptConfig/Perform/Data/GalGame/Test.asset', 'data/scriptconfig/comic/test_comic.asset'] }] };
  assert.deepEqual(sceneAssetPaths(table, 'comic'), ['assets/napresources/data/scriptconfig/comic/test_comic.asset']);
  assert.deepEqual(sceneAssetPaths(table, 'galgame'), ['assets/napresources/data/scriptconfig/perform/data/galgame/test.asset']);
});

test('unrelated strings and unsafe resource paths cannot enter the scene lookup', () => {
  assert.deepEqual(sceneAssetPaths([
    'Data/ScriptConfig/Comic/../Other.asset', 'Data/ScriptConfig/Comic/./Other.asset',
    'Data/ScriptConfig/Comic//Other.asset', 'Data/ScriptConfig/Comic/Other.asset?url',
    'Data/ScriptConfig/ComicExtra/Other.asset', 'Data/ScriptConfig/Comic/C:\\Other.asset',
    'https://example.invalid/Data/ScriptConfig/Comic/Other.asset',
    'Data/ScriptConfig/Perform/Data/GalGame/Comic.asset', null, 123,
  ], 'comic'), []);
  assert.throws(() => sceneAssetPaths({}, 'guess'), /Unknown scene category/);
});
