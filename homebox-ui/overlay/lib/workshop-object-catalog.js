const asset = (id) => `/workshop/objects/${id}.svg`;

export const workshopObjectPresets = [
  { id: 'four-tier-rack', kind: 'Rack', name: 'Four-tier rack', category: 'Shelves', width: 4, depth: 2, asset: asset('four-tier-rack') },
  { id: 'heavy-shelf', kind: 'Rack', name: 'Heavy-duty shelf', category: 'Shelves', width: 6, depth: 2.5, asset: asset('heavy-shelf') },
  { id: 'wire-rack', kind: 'Rack', name: 'Wire storage rack', category: 'Shelves', width: 3, depth: 1.5, asset: asset('wire-rack') },
  { id: 'wall-cabinet', kind: 'Cabinet', name: 'Wall cabinet', category: 'Cabinets', width: 3, depth: 1, asset: asset('wall-cabinet') },
  { id: 'base-cabinet', kind: 'Cabinet', name: 'Base cabinet', category: 'Cabinets', width: 4, depth: 2, asset: asset('base-cabinet') },
  { id: 'tall-cabinet', kind: 'Cabinet', name: 'Tall cabinet', category: 'Cabinets', width: 3, depth: 2, asset: asset('tall-cabinet') },
  { id: 'tool-cabinet', kind: 'Cabinet', name: 'Tool cabinet', category: 'Cabinets', width: 3, depth: 2, asset: asset('tool-cabinet') },
  { id: 'drawer-unit', kind: 'Drawer', name: 'Five-drawer unit', category: 'Drawers', width: 2, depth: 2, asset: asset('drawer-unit') },
  { id: 'parts-drawers', kind: 'Drawer', name: 'Small-parts drawers', category: 'Drawers', width: 2, depth: 1, asset: asset('parts-drawers') },
  { id: 'rolling-drawers', kind: 'Drawer', name: 'Rolling drawer chest', category: 'Drawers', width: 3, depth: 2, asset: asset('rolling-drawers') },
  { id: 'open-tote', kind: 'Bin', name: 'Open tote', category: 'Bins', width: 2, depth: 1.5, asset: asset('open-tote') },
  { id: 'stacking-bin', kind: 'Bin', name: 'Stacking bin', category: 'Bins', width: 1.5, depth: 1, asset: asset('stacking-bin') },
  { id: 'parts-bin', kind: 'Bin', name: 'Small-parts bin', category: 'Bins', width: 1, depth: 0.75, asset: asset('parts-bin') },
  { id: 'parts-crate', kind: 'Crate', name: 'Parts crate', category: 'Bins', width: 2, depth: 1.5, asset: asset('parts-crate') },
  { id: 'assembly-table', kind: 'Table', name: 'Assembly table', category: 'Work surfaces', width: 6, depth: 3, asset: asset('assembly-table') },
  { id: 'workbench', kind: 'Workbench', name: 'Workshop bench', category: 'Work surfaces', width: 8, depth: 3, asset: asset('workbench') },
  { id: 'mobile-bench', kind: 'Workbench', name: 'Mobile workbench', category: 'Work surfaces', width: 4, depth: 2, asset: asset('mobile-bench') },
  { id: 'partition-wall', kind: 'Wall', name: 'Partition wall', category: 'Structure', width: 8, depth: 0.5, asset: asset('partition-wall') },
  { id: 'support-post', kind: 'Wall', name: 'Support post', category: 'Structure', width: 0.75, depth: 0.75, asset: asset('support-post') },
  { id: '3d-printer', kind: 'Misc', name: '3D printer', category: 'Machines', width: 2, depth: 2, asset: asset('3d-printer') },
  { id: 'benchtop-cnc', kind: 'Misc', name: 'Benchtop CNC', category: 'Machines', width: 4, depth: 3, asset: asset('benchtop-cnc') },
  { id: 'floor-cnc', kind: 'Misc', name: 'Floor CNC mill', category: 'Machines', width: 6, depth: 5, asset: asset('floor-cnc') },
];

const byDrawing = new Map(workshopObjectPresets.map((preset) => [`${preset.kind}\0${preset.name.toLocaleLowerCase()}`, preset]));

export function workshopPresetForDrawing(drawing) {
  if (!drawing || typeof drawing.kind !== 'string' || typeof drawing.name !== 'string') return null;
  return byDrawing.get(`${drawing.kind}\0${drawing.name.trim().toLocaleLowerCase()}`) || null;
}
