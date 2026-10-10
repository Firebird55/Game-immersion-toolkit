// Authored scene references, independent of version-specific table field names.
export function sceneAssetPaths(value, category) {
  if (!['galgame', 'comic'].includes(category)) throw new Error('Unknown scene category');
  const namespace = category === 'comic' ? 'Data/ScriptConfig/Comic/' : 'Data/ScriptConfig/Perform/Data/GalGame/';
  const paths = new Set();
  const visit = entry => {
    if (typeof entry === 'string') {
      if (!entry.toLowerCase().startsWith(namespace.toLowerCase()) || !entry.toLowerCase().endsWith('.asset')) return;
      const segments = entry.split('/');
      if (segments.some(segment => !segment || segment === '.' || segment === '..' || !/^[A-Za-z0-9_.-]+$/.test(segment))) return;
      paths.add(`assets/napresources/${entry}`.toLowerCase());
    } else if (Array.isArray(entry)) {
      entry.forEach(visit);
    } else if (entry && typeof entry === 'object') {
      Object.values(entry).forEach(visit);
    }
  };
  visit(value);
  return [...paths].sort();
}
