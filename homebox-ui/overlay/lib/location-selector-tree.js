/** @typedef {{ id: string, name: string, archived?: boolean, parent?: { id: string } | null }} LocationEntity */
/** @typedef {LocationEntity & { treeString: string, parentId: string | null, depth: number, hasChildren: boolean }} TreeLocation */

/**
 * @param {LocationEntity[]} rows
 * @param {{ excludeIds?: string[], currentLocation?: { id: string } | null }} [options]
 * @returns {TreeLocation[]}
 */
export function buildLocationTree(rows, options = {}) {
  const byId = new Map(rows.map(row => [row.id, row]));
  const excluded = new Set([...(options.excludeIds || []), ...(options.currentLocation ? [options.currentLocation.id] : [])]);
  const candidates = rows.filter(row => {
    if (row.archived) return false;
    const seen = new Set();
    /** @type {LocationEntity | undefined} */
    let current = row;
    while (current) {
      if (excluded.has(current.id) || seen.has(current.id)) return false;
      seen.add(current.id);
      current = current.parent?.id ? byId.get(current.parent.id) : undefined;
    }
    return true;
  });
  const candidateIds = new Set(candidates.map(row => row.id));
  const childrenByParent = new Map();
  const roots = [];
  for (const row of candidates) {
    const parentId = row.parent?.id;
    if (parentId && candidateIds.has(parentId)) {
      const children = childrenByParent.get(parentId) ?? [];
      children.push(row);
      childrenByParent.set(parentId, children);
    } else {
      roots.push(row);
    }
  }
  const ordered = [];
  const stack = [...roots].reverse();
  while (stack.length) {
    const row = stack.pop();
    if (!row) continue;
    ordered.push(row);
    const children = childrenByParent.get(row.id) ?? [];
    for (let index = children.length - 1; index >= 0; index--) stack.push(children[index]);
  }
  const childIds = new Set(childrenByParent.keys());
  return ordered.map(row => {
    const path = [], seen = new Set();
    /** @type {LocationEntity | undefined} */
    let current = row;
    while (current && !seen.has(current.id)) {
      seen.add(current.id);
      path.unshift(current.name);
      current = current.parent?.id ? byId.get(current.parent.id) : undefined;
    }
    let depth = 0, parentId = row.parent?.id;
    const ancestors = new Set([row.id]);
    while (parentId && candidateIds.has(parentId) && !ancestors.has(parentId)) {
      depth++;
      ancestors.add(parentId);
      parentId = byId.get(parentId)?.parent?.id;
    }
    return {
      ...row,
      treeString: path.join(" / "),
      parentId: row.parent?.id && candidateIds.has(row.parent.id) ? row.parent.id : null,
      depth,
      hasChildren: childIds.has(row.id),
    };
  });
}

/** @param {TreeLocation[]} locations @param {Set<string>} expandedIds @param {boolean} [searchMode] */
export function getVisibleLocationTree(locations, expandedIds, searchMode = false) {
  if (searchMode) return locations;
  const locationsById = new Map(locations.map(location => [location.id, location]));
  return locations.filter(location => {
    const seen = new Set([location.id]);
    let parentId = location.parentId;
    while (parentId) {
      if (!expandedIds.has(parentId) || seen.has(parentId)) return false;
      seen.add(parentId);
      parentId = locationsById.get(parentId)?.parentId ?? null;
    }
    return true;
  });
}

/** @param {Set<string>} expandedIds @param {string} locationId @returns {Set<string>} */
export function toggleLocationExpanded(expandedIds, locationId) {
  const next = new Set(expandedIds);
  if (next.has(locationId)) next.delete(locationId);
  else next.add(locationId);
  return next;
}

/** @param {TreeLocation[]} locations */
export function getDuplicateLocationNames(locations) {
  const counts = new Map();
  for (const location of locations) counts.set(location.name, (counts.get(location.name) ?? 0) + 1);
  return new Set([...counts].filter(([, count]) => count > 1).map(([name]) => name));
}

/** @param {TreeLocation[]} locations @param {string | undefined} selectedId @param {string} [fallback] */
export function getLocationLabel(locations, selectedId, fallback = "") {
  const selected = locations.find(location => location.id === selectedId);
  if (!selected) return fallback;
  return getDuplicateLocationNames(locations).has(selected.name) ? selected.treeString : selected.name;
}
