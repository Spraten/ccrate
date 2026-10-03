# Feature

Native workshop map

## Problem

A location name alone does not show where a shelf sits in the workshop.

## User Goal

Find or scan an asset and see its exact native shelf highlighted on a room map.

## User Experience

Show on map follows native parents. A configured shelf is highlighted in amber, with a full text path and accessible location buttons. An unplaced shelf is honestly identified as unplaced; a mapped ancestor is described as an area, not an exact shelf.

## Current Homebox Behavior

Native location entities, parent hierarchy and text custom fields are supported; no workshop geometry was found.

## Proposed Behavior

Store versioned room dimensions and object placement on native location custom fields. Admin places locations with touch steppers; no physical layout is assumed.

## Scope

Room configuration, manual grid positioning, resize, native rename, object types, placement removal, exact-shelf lookup and location contents.

## Out of Scope

Physical room surveying, automatic routing, free rotation/dragging and duplicate visual representations are future editor refinements. Native location creation/management is the next feature.

## User Decisions

DEC 018 delegates recommendations; DEC 021 chooses native fields and a simple touch grid. Geometry supports a version and rotation key for future evolution; current rotation is zero.

## Data Model

Native Workshop map room JSON text field: version, width, height. Native Workshop map object JSON text field: version, room_id, x, y, width, height, rotation, type. Native names, IDs and hierarchy remain authoritative.

## API Changes

Companion GET /api/map?entity=..., POST /map/room, /map/object, /map/remove. No upstream API changes.

## Homebox Integration

Supported native GET/PUT. Full update payload preserves entity metadata, fields, parent and tags. Placement removal deletes only its native geometry field.

## UI Changes

Show on map, location contents view, Admin workshop map editor, touch room size/name, column/row/width/height steppers, object type and confirmed removal.

## Hardware Dependencies

800x480 touchscreen. Diagram fits the viewport; large location buttons also support interaction with small visual objects.

## Security Considerations

Map changes require approved open setup Admin and same-origin POST. Native UUID/group API boundaries apply. JSON and names are rendered through safe text APIs.

## Offline Considerations

Local SVG and native fields only; no external maps, fonts or images.

## Failure Modes

Invalid/newer map formats are flagged for Homebox review. Bounds, native room ancestry and active location status are validated. Shrinking a room past placed objects is rejected. Visual removal never deletes a native location.

## Logging / Diagnostics

Native metadata holds the layout. docs/map-integration-results.json records tested behavior; work/map-screen.png captures the synthetic test layout.

## Implementation Steps

Create native field preservation helper, validate versioned geometry and hierarchy, add map lookup, implement touch editor, verify real Homebox updates and browser rendering.

## Unit Tests

Nine map tests pass: metadata preservation, exact shelf, safe placement removal, bounds/wrong room, room shrink, corrupt fields, location/archive guards, numeric types and duplicate fields. Total suite is 60 passing tests.

## Integration Tests

Real Homebox/Pi touch test configures a room, places/resizes two shelves, finds an asset with the exact shelf highlighted, confirms the map fits 800x480, and removes placement without altering the native location or asset. No browser errors.

## Hardware Tests

Pi native Chromium tested at the actual display size; physical workshop positions must be entered by the operator.

## User Acceptance Tests

Actual room layout and uncoached map use are still pending. Test screenshots clearly identify synthetic fixtures.

## Upgrade / Migration Considerations

No new companion database table. Geometry version is 1; unsupported versions fail safely. Homebox backup/export includes the fields.

## Rollback Plan

Revert source; keep or remove geometry fields through supported native editing. Preserve native backups before changing a real layout.

## Definition of Done

Native-field-backed map lookup and touchscreen placement are integration-tested. Real layout configuration, native location creation/labels and further editor refinements remain in the overall plan.
