# Task 1 report: collection-scoped item metadata

## Delivered

- Added `ops/item_metadata.py` with additive SQLite tables for per-item field notes, normalized unordered relations, and request-key replay protection. Each write is transactional and collection-scoped.
- Added authenticated metadata GET and POST routes in `ops/desktop_api.py`. Native item identities are resolved through the authenticated collection Homebox client before writes; locations are rejected. The read model omits inaccessible targets' identifiers and details while retaining their relation.
- Added local SQLite and authenticated API fixture coverage in `tests/test_item_metadata.py` and `tests/test_desktop_api_item_metadata.py`.

## Verification

Commands run:

- `PYTHONPATH=ops:kiosk python -m unittest discover -s tests -p 'test_item_metadata.py' -v` — 3 tests passed.
- `PYTHONPATH=ops:kiosk python -m unittest discover -s tests -p 'test_desktop_api_item_metadata.py' -v` — 22 tests passed (2 metadata API tests plus 20 existing equipment catalog tests discovered through the reused fixture module).
- `git diff --check` — passed.

The requested pre-implementation red run was not performed: implementation was already underway before the test file was added. The post-implementation focused suites pass.

## Review notes

No known functional concern remains in the task scope. API tests reuse the equipment catalog fixture, so discovery also picks up that fixture module's test class; all of those tests passed in the final focused command. No operational Homebox instance was used.

## Review fix round 1

- Field-name uniqueness is now checked against every normalized input name before empty notes are omitted, so an empty `x` followed by nonempty `X` is rejected. Added a regression assertion.
- The isolated Homebox API fixture can now represent an entity belonging to a different collection. Added coverage proving that foreign entities are rejected for GET, field-note writes, and both related-item write endpoints (including when the foreign entity is the second relation endpoint), with no metadata persisted.
- The historical pre-implementation failing run remains unreconstructable and is not claimed; the process limitation above remains accurate.

Exact focused results after fixes:

- `PYTHONPATH=ops:kiosk python -m unittest discover -s tests -p 'test_item_metadata.py' -v` — 3 tests passed.
- `PYTHONPATH=ops:kiosk python -m unittest discover -s tests -p 'test_desktop_api_item_metadata.py' -v` — 23 tests passed (3 metadata API tests and 20 existing equipment catalog fixture tests).

## Fix round 1 literal verification output

Command: `PYTHONPATH=ops:kiosk python -m unittest discover -s tests -p 'test_item_metadata.py' -v`

```text
test_collection_isolation_and_request_replay_conflict (test_item_metadata.ItemMetadataTests.test_collection_isolation_and_request_replay_conflict) ... ok
test_notes_save_read_replay_and_normalized_uniqueness (test_item_metadata.ItemMetadataTests.test_notes_save_read_replay_and_normalized_uniqueness) ... ok
test_relations_are_symmetric_idempotent_and_removable (test_item_metadata.ItemMetadataTests.test_relations_are_symmetric_idempotent_and_removable) ... ok

----------------------------------------------------------------------
Ran 3 tests in 0.018s

OK
```

Command: `PYTHONPATH=ops:kiosk python -m unittest discover -s tests -p 'test_desktop_api_item_metadata.py' -v`

```text
test_assignment_retry_recovers_product_registration_committed_before_assignment (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_assignment_retry_recovers_product_registration_committed_before_assignment) ... ok
test_assignment_reused_key_with_another_item_conflicts_before_allocation (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_assignment_reused_key_with_another_item_conflicts_before_allocation) ... ok
test_assignment_seeds_from_archived_matching_records_without_rewriting_them (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_assignment_seeds_from_archived_matching_records_without_rewriting_them) ... ok
test_assignment_timeout_recovery_reuses_same_entity_and_does_not_create_product_again (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_assignment_timeout_recovery_reuses_same_entity_and_does_not_create_product_again) ... ok
test_explicit_product_group_is_part_of_persisted_product_identity (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_explicit_product_group_is_part_of_persisted_product_identity) ... ok
test_explicit_product_group_metadata_matches_existing_native_units (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_explicit_product_group_metadata_matches_existing_native_units) ... ok
test_id_mapping_caps_batch_and_ignores_foreign_or_malformed_uuids (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_id_mapping_caps_batch_and_ignores_foreign_or_malformed_uuids) ... ok
test_location_assignment_rejected_and_native_item_controls_product_identity (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_location_assignment_rejected_and_native_item_controls_product_identity) ... ok
test_member_can_save_list_and_archive_templates_scoped_to_collection (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_member_can_save_list_and_archive_templates_scoped_to_collection) ... ok
test_registration_retry_accepts_changed_inventory_matches (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_registration_retry_accepts_changed_inventory_matches) ... ok
test_same_explicit_product_group_overrides_metadata_differences (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_same_explicit_product_group_overrides_metadata_differences) ... ok
test_source_entity_is_refetched_and_only_shared_values_are_saved (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_source_entity_is_refetched_and_only_shared_values_are_saved) ... ok
test_template_assignment_group_identity_overrides_metadata_conflict (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_template_assignment_group_identity_overrides_metadata_conflict) ... ok
test_template_assignment_refreshes_members_added_after_template_save (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_template_assignment_refreshes_members_added_after_template_save) ... ok
test_template_assignment_rejects_native_metadata_conflict (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_template_assignment_rejects_native_metadata_conflict) ... ok
test_template_replay_conflict_and_resolution_are_scoped (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_template_replay_conflict_and_resolution_are_scoped) ... ok
test_template_photo_fallback_keeps_verified_attachment_owner_and_rejects_forged_owner (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_template_photo_fallback_keeps_verified_attachment_owner_and_rejects_forged_owner) ... ok
test_template_refresh_excludes_target_from_seed_and_allows_blank_metadata (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_template_refresh_excludes_target_from_seed_and_allows_blank_metadata) ... ok
test_template_replay_digest_ignores_newly_matching_native_members (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_template_replay_digest_ignores_newly_matching_native_members) ... ok
test_template_routes_reject_unknown_members_and_per_unit_fields (test_desktop_api_equipment_catalog.EquipmentCatalogApiTests.test_template_routes_reject_unknown_members_and_per_unit_fields) ... ok
test_foreign_collection_item_rejected_for_get_and_both_write_endpoints (test_desktop_api_item_metadata.ItemMetadataApiTests.test_foreign_collection_item_rejected_for_get_and_both_write_endpoints) ... ok
test_inaccessible_and_location_rejected_before_mutation (test_desktop_api_item_metadata.ItemMetadataApiTests.test_inaccessible_and_location_rejected_before_mutation) ... ok
test_member_notes_and_related_links_and_symmetric_removal (test_desktop_api_item_metadata.ItemMetadataApiTests.test_member_notes_and_related_links_and_symmetric_removal) ... ok

----------------------------------------------------------------------
Ran 23 tests in 0.253s

OK
```
