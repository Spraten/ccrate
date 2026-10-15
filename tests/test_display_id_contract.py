import pathlib
import importlib.util
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class DisplayIDContractTests(unittest.TestCase):
    def test_docker_backend_builder_copies_its_display_id_overlay_dependency(self):
        dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('deploy/homebox_display_id_overlay.py', dockerfile)

    def test_display_id_contains_only_type_and_full_storage_path(self):
        source = (ROOT / 'homebox-backend/repo_display_ids.go').read_text(encoding='utf-8')
        helper = (ROOT / 'homebox-backend/displayids/display_id.go').read_text(encoding='utf-8')
        self.assertIn('return strings.Join(segments, "-")', helper)
        self.assertNotIn('"A"+strconv.FormatInt', source)
        self.assertNotIn('"S"+code', source)
        self.assertNotIn('"U"+compactUUID', source)

    def test_entity_type_update_serializes_with_hierarchy_writes(self):
        builder = (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8')
        tests = (ROOT / 'homebox-backend/repo_display_ids_test.go').read_text(encoding='utf-8')
        update = builder[builder.index("type_start=type_text.index('func (r *EntityTypeRepository) Update('") : builder.index("type_source.write_text(type_text)")]
        self.assertIn('hierarchyWriteMu.Lock()', update)
        self.assertIn('TestEntityTypeRenameSerializesWithConcurrentAssetCreate', tests)

    def test_backend_builder_inserts_short_code_into_template_entity_builder(self):
        builder = (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8')
        self.assertIn(
            'SetWarrantyDetails(data.WarrantyDetails)\n\tentityBuilder.SetDisplayIDBase(displayIDBase)\n\tif shortCode != "" { entityBuilder.SetShortCode(shortCode) }\n\tif barcode != "" {',
            builder,
        )

    def test_backend_builder_keeps_existing_model_number_field(self):
        builder = (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8')
        self.assertNotIn('ModelNumber  string    `json:"modelNumber"`', builder)

    def test_backend_builder_preserves_normalized_barcode_on_item_create(self):
        builder = (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8')
        self.assertIn('if barcode != "" { q.SetBarcode(barcode) }', builder)
        self.assertIn('.SetManufacturer(data.Manufacturer)', builder)

    def test_backend_builder_does_not_duplicate_template_metadata_handling(self):
        builder = (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8')
        self.assertNotIn('modelNumber := template.DefaultModelNumber', builder)

    def test_backend_derives_full_path_and_keeps_native_identity_separate(self):
        source = (ROOT / 'homebox-backend/repo_display_ids.go').read_text(encoding='utf-8')
        tests = (ROOT / 'homebox-backend/repo_display_ids_test.go').read_text(encoding='utf-8')
        builder = (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8')
        self.assertIn('displayids.Assign(entries)', source)
        self.assertIn('func isDisplayIDSearch(value string) bool', source)
        self.assertIn('WithParent().WithEntityType()', source)
        self.assertIn('entity.HasGroupWith(group.ID(gid))', source)
        self.assertIn("r.GetOneByGroup(ctx, gid, result.ID)", builder)
        self.assertIn("r.GetOneByGroup(ctx, gid, newEntityID)", builder)
        self.assertIn('BIN-D-GC-C-1', tests)
        self.assertNotIn('TestFormatDisplayIDUsesUUIDSuffixWhenNativeAssetIDIsUnassigned', tests)
        self.assertIn('BIN-D-GC-C-1-1', tests)
        self.assertIn('BIN-D-GC-C-1-2', tests)
        self.assertIn('a deterministic collision counter is added only when multiple assets share the same base path', builder)
        self.assertIn('duplicateAssetID := assetID', tests)
        self.assertIn('require.NotEqual(t, item.ShortCode, duplicateItem.ShortCode', tests)
        self.assertIn('PART-SABC-123', tests)
        self.assertIn('displayIDOrdinarySearch = q.Search', builder)
        self.assertIn('entity.Barcode(strings.TrimSpace(displayIDOrdinarySearch))', builder)
        self.assertIn('r.findDisplayIDSearchMatch(ctx, gid, displayIDSearch)', builder)
        self.assertNotIn('ordinaryQB.All(ctx)', builder)
        self.assertNotIn('ordinaryIDs', builder)
        self.assertNotIn('IDIn(ordinaryIDs...)', builder)
        self.assertIn('func (r *EntityRepository) findDisplayIDSearchMatch', (ROOT / 'homebox-backend/repo_display_ids.go').read_text(encoding='utf-8'))
        self.assertIn('originalUUID, originalAssetID, originalShortCode', tests)
        self.assertIn("schemas[name]['properties']['displayId']", builder)

    def test_bounded_display_id_family_index_and_search_closure_are_staged(self):
        source = (ROOT / 'homebox-backend/repo_display_ids.go').read_text(encoding='utf-8')
        helper = (ROOT / 'homebox-backend/displayids/display_id.go').read_text(encoding='utf-8')
        migration = (ROOT / 'homebox-backend/displayids/migration.go').read_text(encoding='utf-8')
        builder = (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8')
        self.assertIn('entity.DisplayIDBaseIn(batch...)', source)
        self.assertIn('searched:=map[string]bool{}', source)
        self.assertIn('loadedBases:=map[string]bool{}', source)
        self.assertIn('displayids.SearchBases(id)', source)
        self.assertNotIn('displayIDBaseFor(ctx,tx.Client()', source)
        self.assertIn('func SearchBases', helper)
        self.assertIn('for len(segments) > 1', helper)
        self.assertIn('entity_display_id_base_group_idx', migration)
        self.assertIn('field.String("display_id_base").Default("")', builder)
        self.assertIn('20260514120000_display_id_bases.go', builder)
        self.assertIn('displayIDBaseFor(ctx, r.db, gid, data.EntityTypeID, data.ParentID)', builder)
        self.assertIn('refreshDisplayIDBasesForSubtree(ctx, shortCodeTx, gid, data.ID)', builder)
        self.assertIn('refreshDisplayIDBasesForSubtree(ctx, tx, gid, id)', builder)
        self.assertIn('func refreshDisplayIDBasesForSubtree', source)
        self.assertIn('entity.HasParentWith(entity.IDIn(ids...))', source)
        self.assertNotIn('Where(entity.HasGroupWith(group.ID(gid))).WithParent().WithEntityType().All(ctx)', source)
        self.assertIn('displayIDBaseFor(ctx, r.db, gid, typeID, data.ParentID)', (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8'))
        self.assertIn('refreshDisplayIDBasesForSubtree(ctx, tx, gid, id)', (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8'))
        self.assertIn('refreshDisplayIDBasesForType(ctx, tx, gid, data.ID)', (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8'))
        self.assertIn('validateHierarchyParent(ctx,gid,id,data.ParentID)', (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8'))
        self.assertIn('GetContainerByGroup(ctx, groupID, out.ID)', (ROOT / 'homebox-backend/repo_display_ids_test.go').read_text(encoding='utf-8'))
        self.assertIn('func refreshDisplayIDBasesForRoots', source)
        self.assertIn('UNKNOWN', helper)
        self.assertIn('TestUnicodeOnlyCollisionIDsSearchFromSingleEntityReads', (ROOT / 'homebox-backend/repo_display_ids_test.go').read_text(encoding='utf-8'))
        self.assertIn('TestCodeShapedSearchCombinesOrdinaryAndExactDisplayIDWithPagination', (ROOT / 'homebox-backend/repo_display_ids_test.go').read_text(encoding='utf-8'))
        self.assertIn('entity.DisplayIDBaseIn(bases...)', source)
        query_block = builder[builder.index("ordinary_anchor="):builder.index("page_anchor=")]
        self.assertIn('findDisplayIDSearchMatch(ctx, gid, displayIDSearch)', query_block)
        self.assertLess(query_block.index('findDisplayIDSearchMatch'), query_block.rindex('QueryByGroup.count'))
        self.assertNotIn('ordinaryQB.All(ctx)', builder)
        self.assertNotIn('displayIDOrdinaryMatches', builder)
        self.assertIn('refreshDisplayIDBasesForType', source)
        self.assertIn('displayItems := []EntitySummary{out.EntitySummary}', (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8'))
        self.assertIn('UNKNOWN is used if every type and path name normalizes to an empty segment', (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8'))
        self.assertIn('TestDisplayIDBaseRefreshesAfterTypeRename', (ROOT / 'homebox-backend/repo_display_ids_test.go').read_text(encoding='utf-8'))
        self.assertIn('TestDisplayIDBasesRefreshWhenDeletingLocationParent', (ROOT / 'homebox-backend/repo_display_ids_test.go').read_text(encoding='utf-8'))
        self.assertIn('TestUpdateContainerRejectsCycleBeforeRefreshingDisplayIDs', (ROOT / 'homebox-backend/repo_display_ids_test.go').read_text(encoding='utf-8'))
        self.assertIn('patch_display_id_delete_paths(text)', (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8'))
        self.assertNotIn('delete_body.count(close)', (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8'))

    def test_delete_overlay_runs_against_materialized_entity_source(self):
        source_path = ROOT / 'work/homebox-source-patched/backend/internal/data/repo/repo_entities.go'
        if not source_path.exists():
            self.skipTest('pinned source is not materialized in this checkout')
        module_path = ROOT / 'deploy/homebox_display_id_overlay.py'
        spec = importlib.util.spec_from_file_location('homebox_display_id_overlay', module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        patched = module.patch_display_id_delete_paths(source_path.read_text(encoding='utf-8'))
        for name in ('DeleteByGroup', 'DeleteContainerByGroup'):
            start = patched.index(f'func (r *EntityRepository) {name}(')
            end = patched.index('\nfunc ', start)
            body = patched[start:end]
            self.assertIn('children, err := tx.Entity.Query()', body)
            self.assertIn('refreshDisplayIDBasesForSubtree', body)
            self.assertIn('tx.Commit()', body)

    def test_item_details_search_and_label_designer_use_display_id(self):
        backend = (ROOT / 'deploy/build-homebox-backend.py').read_text(encoding='utf-8')
        details = (ROOT / 'deploy/build-homebox-ui.py').read_text(encoding='utf-8')
        designer = (ROOT / 'homebox-ui/overlay/components/Workshop/LabelDesigner.vue').read_text(encoding='utf-8')
        editor = (ROOT / 'label-ui/src/editor-host.ts').read_text(encoding='utf-8')
        label_backend = (ROOT / 'ops/label_layouts.py').read_text(encoding='utf-8')
        label_tool = (ROOT / 'label-ui/patches/0002-label-editor-controls.patch').read_text(encoding='utf-8')
        self.assertIn('isDisplayIDSearch(q.Search)', backend)
        self.assertNotIn('q.AssetID = id', backend)
        self.assertIn('r.findDisplayIDSearchMatch(ctx, gid, displayIDSearch)', backend)
        self.assertIn('if q.Page != -1 || q.PageSize != -1 {', backend)
        self.assertIn('item.displayId', details)
        self.assertIn('display_id: props.selectedItem.displayId || ""', designer)
        self.assertIn('display_id: nextDisplayId', editor)
        self.assertIn("'display_id':display_id", label_backend)
        self.assertIn("'item_display_id':entity.get('displayId','')", label_backend)
        self.assertIn("entity.get('displayId')!=ticket.get('item_display_id')", (ROOT / 'ops/labels.py').read_text(encoding='utf-8'))
        self.assertIn("createText(place, '{{display_id}}')", label_tool)


if __name__ == '__main__':
    unittest.main()
