#!/usr/bin/env python3
"""Stage a pinned native backend with flexible hierarchy fixes; never deploy it."""
import pathlib,shutil,subprocess,os,json,hashlib,re
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
BUILD=ROOT/'work/homebox-backend-build'
from homebox_patchset import load_patchset, materialize, source_commit, source_tree_digest
from homebox_display_id_overlay import patch_display_id_delete_paths
NATIVE_SOURCE=materialize(ROOT)
shutil.copytree(NATIVE_SOURCE/'backend',BUILD,dirs_exist_ok=True)
for source, destination in (
    (ROOT/'homebox-backend/shortcodes', BUILD/'internal/data/shortcodes'),
    (ROOT/'homebox-backend/displayids', BUILD/'internal/data/displayids'),
    (ROOT/'homebox-backend/repo_short_codes.go', BUILD/'internal/data/repo/repo_short_codes.go'),
    (ROOT/'homebox-backend/ent_tx_sql.go', BUILD/'internal/data/ent/short_code_tx.go'),
    (ROOT/'homebox-backend/v1_ctrl_item_short_codes.go', BUILD/'app/api/handlers/v1/v1_ctrl_item_short_codes.go'),
    (ROOT/'homebox-backend/20260513120000_item_short_codes.go', BUILD/'internal/data/migrations/sqlite3/20260513120000_item_short_codes.go'),
    (ROOT/'homebox-backend/20260513120001_item_short_codes.go', BUILD/'internal/data/migrations/postgres/20260513120001_item_short_codes.go'),
    (ROOT/'homebox-backend/20260514120000_display_id_bases.go', BUILD/'internal/data/migrations/sqlite3/20260514120000_display_id_bases.go'),
    (ROOT/'homebox-backend/20260514120001_display_id_bases.go', BUILD/'internal/data/migrations/postgres/20260514120001_display_id_bases.go'),
    (ROOT/'homebox-backend/repo_short_codes_test.go', BUILD/'internal/data/repo/repo_short_codes_test.go'),
    (ROOT/'homebox-backend/repo_display_ids.go', BUILD/'internal/data/repo/repo_display_ids.go'),
    (ROOT/'homebox-backend/repo_display_ids_test.go', BUILD/'internal/data/repo/repo_display_ids_test.go'),
):
    if source.is_dir(): shutil.copytree(source,destination,dirs_exist_ok=True)
    else: shutil.copy2(source,destination)
schema=BUILD/'internal/data/ent/schema/entity.go'; body=schema.read_text()
anchor='\t\tfield.String("import_ref").'
assert body.count(anchor)==1
body=body.replace(anchor,'\t\tfield.String("short_code").Optional().Nillable().MaxLen(32),\n'+anchor)
anchor='\t\tfield.String("short_code").Optional().Nillable().MaxLen(32),\n'
assert body.count(anchor)==1
body=body.replace(anchor,anchor+'\t\tfield.String("display_id_base").Default(""),\n')
schema.write_text(body)
go=pathlib.Path((ROOT/'work/toolchains/go-path.txt').read_text().strip())/'bin/go'
env=dict(os.environ,CGO_ENABLED='0',GOTOOLCHAIN='local',GOPATH=str(ROOT/'work/toolchains/go-cache'),GOCACHE=str(ROOT/'work/toolchains/go-build-cache'))
subprocess.run([str(go),'generate','./internal/data/ent'],cwd=BUILD,env=env,check=True)
test_main=BUILD/'internal/data/repo/main_test.go';mb=test_main.read_text()
mb=mb.replace('"github.com/sysadminsmedia/homebox/backend/internal/data/ent"','"github.com/sysadminsmedia/homebox/backend/internal/data/ent"\n\t"github.com/sysadminsmedia/homebox/backend/internal/data/shortcodes"\n\t"github.com/sysadminsmedia/homebox/backend/internal/data/displayids"',1)
anchor='\terr = client.Schema.Create(context.Background())\n\tif err != nil {\n\t\tlog.Fatalf("failed creating schema resources: %v", err)\n\t}\n'
assert mb.count(anchor)==1
setup='''\tshortCodeTx, err := client.Sql().BeginTx(context.Background(), nil)
\tif err != nil { log.Fatalf("failed starting short-code test setup: %v", err) }
\tif err := shortcodes.Install(context.Background(), shortCodeTx, false); err != nil { log.Fatalf("failed setting up short-code counters: %v", err) }
\tif err := shortCodeTx.Commit(); err != nil { log.Fatalf("failed committing short-code test setup: %v", err) }
'''
mb=mb.replace(anchor,anchor+setup,1)
setup='''\tdisplayIDTx, err := client.Sql().BeginTx(context.Background(), nil)
	if err != nil { log.Fatalf("failed starting display-ID test setup: %v", err) }
	if err := displayids.Install(context.Background(), displayIDTx, false); err != nil { log.Fatalf("failed setting up display-ID bases: %v", err) }
	if err := displayIDTx.Commit(); err != nil { log.Fatalf("failed committing display-ID test setup: %v", err) }
'''
# Install after Ent creates the schema and after the short-code integration migration.
test_setup_anchor='''\tif err := shortCodeTx.Commit(); err != nil { log.Fatalf("failed committing short-code test setup: %v", err) }
'''
assert mb.count(test_setup_anchor)==1
mb=mb.replace(test_setup_anchor,test_setup_anchor+setup,1)
test_main.write_text(mb)
source=BUILD/'internal/data/repo/repo_entities.go';text=source.read_text()
text=text.replace('Name        string    `json:"name"`\n\t\tDescription','Name        string    `json:"name"`\n\t\tShortCode   string    `json:"shortCode"`\n\t\tDescription',1)
# Add shortCode to the shared summary embedded by both list and detail DTOs.
summary=text.index('\tEntitySummary struct {')
name_line=text.index('\n',text.index('\t\tName ',summary))+1
if 'ShortCode' not in text[summary:text.index('\n\t}',summary)]:
    text=text[:name_line]+'\t\tShortCode   string    `json:"shortCode"`\n'+text[name_line:]
summary_end=text.index('\n\t}',summary)
if 'DisplayID' not in text[summary:summary_end]:
    name_line=text.index('\n',text.index('\t\tName ',summary))+1
    text=text[:name_line]+'\t\tDisplayID   string    `json:"displayId"`\n'+text[name_line:]
summary_end=text.index('\n\t}',summary)
if 'DisplayIDBase' not in text[summary:summary_end]:
    name_line=text.index('\n',text.index('\t\tName ',summary))+1
    text=text[:name_line]+'\t\tDisplayIDBase string `json:"-"`\n'+text[name_line:]
search_anchor='''\tif q.Search != "" {
		searchPredicates := []predicate.Entity{'''
assert text.count(search_anchor)==1
text=text.replace(search_anchor,'''\tdisplayIDSearch := ""
	displayIDOrdinarySearch := ""
	if q.AssetID.Nil() && isDisplayIDSearch(q.Search) {
		displayIDSearch = strings.ToUpper(strings.TrimSpace(q.Search))
		displayIDOrdinarySearch = q.Search
		q.Search = ""
	}
	if q.Search != "" {
		searchPredicates := []predicate.Entity{''',1)
ordinary_anchor='''\tcountCtx, countSpan := entityTracer().Start(ctx, "repo.EntityRepository.QueryByGroup.count")'''
assert text.count(ordinary_anchor)==1
text=text.replace(ordinary_anchor,'''\tif displayIDSearch != "" {
		ordinarySearch := entity.Or(
			entity.NameContainsFold(displayIDOrdinarySearch),
			entity.DescriptionContainsFold(displayIDOrdinarySearch),
			entity.SerialNumberContainsFold(displayIDOrdinarySearch),
			entity.ModelNumberContainsFold(displayIDOrdinarySearch),
			entity.ManufacturerContainsFold(displayIDOrdinarySearch),
			entity.NotesContainsFold(displayIDOrdinarySearch),
			entity.ShortCodeContainsFold(displayIDOrdinarySearch),
			entity.Barcode(strings.TrimSpace(displayIDOrdinarySearch)),
		)
		if exactID, found, err := r.findDisplayIDSearchMatch(ctx, gid, displayIDSearch); err != nil {
			recordSpanError(span, err)
			return PaginationResult[EntitySummary]{}, err
		} else if found {
			ordinarySearch = entity.Or(ordinarySearch, entity.ID(exactID))
		}
		qb = qb.Where(ordinarySearch)
	}
	countCtx, countSpan := entityTracer().Start(ctx, "repo.EntityRepository.QueryByGroup.count")''',1)
page_anchor='''\tif q.Page != -1 || q.PageSize != -1 {'''
assert text.count(page_anchor)==1
text=text.replace(page_anchor,'''\tif q.Page != -1 || q.PageSize != -1 {''',1)
anchor='''\tfetchSpan.SetAttributes(attribute.Int("query.results.count", len(entities)))'''
assert text.count(anchor)==1
text=text.replace(anchor,'''\tif err := r.populateDisplayIDs(fetchCtx, gid, entities); err != nil {
		recordSpanError(fetchSpan, err)
		fetchSpan.End()
		recordSpanError(span, err)
		return PaginationResult[EntitySummary]{}, err
	}
	fetchSpan.SetAttributes(attribute.Int("query.results.count", len(entities)))''',1)
# Asset-code lookup is used by label selection and must return the same derived ID.
asset_anchor='''\tspan.SetAttributes(attribute.Int("query.results.count", len(entities)))
	return PaginationResult[EntitySummary]{
		Page:     page,'''
assert text.count(asset_anchor)==1
text=text.replace(asset_anchor,'''\tif err := r.populateDisplayIDs(ctx, gid, entities); err != nil {
		recordSpanError(span, err)
		return PaginationResult[EntitySummary]{}, err
	}
	span.SetAttributes(attribute.Int("query.results.count", len(entities)))
	return PaginationResult[EntitySummary]{
		Page:     page,''',1)
# Detail and write responses expose the full path. Keep internal transaction reads
# alone; their callers may still be before commit.
detail_anchor='''\tout, err := r.getOne(ctx, entity.ID(id), entity.HasGroupWith(group.ID(gid)))
	recordSpanError(span, err)
	return out, err
}

func entityQuerySpanAttrs'''
assert text.count(detail_anchor)==1
text=text.replace(detail_anchor,'''\tout, err := r.getOne(ctx, entity.ID(id), entity.HasGroupWith(group.ID(gid)))
	recordSpanError(span, err)
	if err == nil {
		displayItems := []EntitySummary{out.EntitySummary}
		if displayErr := r.populateDisplayIDs(ctx, gid, displayItems); displayErr != nil {
			return EntityOut{}, displayErr
		}
		out.EntitySummary = displayItems[0]
		out.Parent = displayItems[0].Parent
	}
	return out, err
}

func entityQuerySpanAttrs''',1)
# Write responses use the tenant-scoped detail mapper so newly created and
# moved items immediately include their current derived display ID.
for old, new in (
    ('r.GetOne(ctx, result.ID)', 'r.GetOneByGroup(ctx, gid, result.ID)'),
    ('r.GetOne(ctx, newEntityID)', 'r.GetOneByGroup(ctx, gid, newEntityID)'),
    ('r.GetOne(ctx, data.ID)', 'r.GetOneByGroup(ctx, gid, data.ID)'),
    ('r.GetOne(ctx, id)', 'r.GetOneByGroup(ctx, gid, id)'),
):
    text=text.replace(old, new)
text=text.replace('Name:          e.Name,','Name:          e.Name,\n\t\tDisplayIDBase: e.DisplayIDBase,\n\t\tShortCode:     lo.FromPtrOr(e.ShortCode, ""),',1)
text=text.replace('entity.SerialNumberContainsFold(q.Search),','entity.SerialNumberContainsFold(q.Search),\n\t\t\t\tentity.ShortCodeContainsFold(q.Search),',1)
# Ordinary creation allocates inside the same transaction as the item insert.
start=text.index('\tq := r.db.Entity.Create().',text.index('func (r *EntityRepository) Create('))
end=text.index('\n\tspan.SetAttributes(attribute.String("entity.id"',start)
replacement='''	if data.EntityTypeID == uuid.Nil {
		etID, err := r.resolveDefaultEntityType(ctx, gid, false)
		if err != nil { recordSpanError(span, err); return EntityOut{}, err }
		data.EntityTypeID = etID
	}
	typeInfo, err := r.db.EntityType.Get(ctx, data.EntityTypeID)
	if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	displayIDBase, err := displayIDBaseFor(ctx, r.db, gid, data.EntityTypeID, data.ParentID)
	if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	tx, err := r.db.Tx(ctx)
	if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	committed := false
	defer func() { if !committed { _ = tx.Rollback() } }()
	shortCode := ""
	if !typeInfo.IsLocation {
		shortCode, err = allocateShortCode(ctx, tx, gid, data.ModelNumber, data.Name)
		if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	}
	q := tx.Entity.Create().SetImportRef(data.ImportRef).SetName(data.Name).SetQuantity(data.Quantity).
		SetDescription(data.Description).SetGroupID(gid).SetAssetID(int64(data.AssetID)).
		SetEntityTypeID(data.EntityTypeID).SetManufacturer(data.Manufacturer).SetModelNumber(data.ModelNumber).SetDisplayIDBase(displayIDBase)
	if barcode != "" { q.SetBarcode(barcode) }
	if shortCode != "" { q.SetShortCode(shortCode) }
	if data.ParentID != uuid.Nil { q.SetParentID(data.ParentID) }
	if len(data.TagIDs) > 0 { q.AddTagIDs(data.TagIDs...) }
	result, err := q.Save(ctx)
	if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	if err := tx.Commit(); err != nil { recordSpanError(span, err); return EntityOut{}, err }
	committed = true
'''
text=text[:start]+replacement+text[end:]
# Template creation follows the same allocator and keeps its default model number.
anchor='''	// Create entity with all template data
	newEntityID := uuid.New()'''
assert text.count(anchor)==1
text=text.replace(anchor,'''\t// Create entity with all template data
	newEntityID := uuid.New()
	displayIDBase, err := displayIDBaseFor(ctx, r.db, gid, data.EntityTypeID, data.ParentID)
	if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	typeInfo, err := tx.EntityType.Get(ctx, data.EntityTypeID)
	if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	shortCode := ""
	if !typeInfo.IsLocation {
		shortCode, err = allocateShortCode(ctx, tx, gid, data.ModelNumber, data.Name)
		if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	}''',1)
anchor='''		SetWarrantyDetails(data.WarrantyDetails)
	if barcode != "" {'''
assert text.count(anchor)==1
text=text.replace(anchor,'''\t\tSetWarrantyDetails(data.WarrantyDetails)
	entityBuilder.SetDisplayIDBase(displayIDBase)
	if shortCode != "" { entityBuilder.SetShortCode(shortCode) }
	if barcode != "" {''',1)
# Duplicate records receive fresh codes while preserving their model hint.
anchor='''	newEntityID := uuid.New()
	span.SetAttributes(
		attribute.String("entity.new_id", newEntityID.String()),'''
assert text.count(anchor)==1
text=text.replace(anchor,'''\tnewEntityID := uuid.New()
	displayIDBase := ""
	if originalEntity.EntityType != nil {
		parentID := uuid.Nil
		if originalEntity.Parent != nil { parentID = originalEntity.Parent.ID }
		displayIDBase, err = displayIDBaseFor(ctx, r.db, gid, originalEntity.EntityType.ID, parentID)
		if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	}
	shortCode := ""
	if originalEntity.EntityType == nil || !originalEntity.EntityType.IsLocation {
		shortCode, err = allocateShortCode(ctx, tx, gid, originalEntity.ModelNumber, options.CopyPrefix+originalEntity.Name)
		if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	}
	span.SetAttributes(
		attribute.String("entity.new_id", newEntityID.String()),''',1)
anchor='''		SetSyncChildEntityLocations(originalEntity.SyncChildEntityLocations)

	// Skip Set on zero dates'''
assert text.count(anchor)==1
text=text.replace(anchor,'''\t\tSetSyncChildEntityLocations(originalEntity.SyncChildEntityLocations)
	if displayIDBase != "" { entityBuilder.SetDisplayIDBase(displayIDBase) }
	if shortCode != "" { entityBuilder.SetShortCode(shortCode) }

	// Skip Set on zero dates''',1)
# CSV imports allocate from the row's model number when a new native item is made.
service=BUILD/'internal/core/services/service_entities.go';sb=service.read_text()
anchor='''\t\t\tnewEntity := repo.EntityCreate{
				ImportRef:   row.ImportRef,
				Name:        row.Name,'''
assert sb.count(anchor)==1
sb=sb.replace(anchor,'''\t\t\tnewEntity := repo.EntityCreate{
				ImportRef:   row.ImportRef,
				Name:        row.Name,
				ModelNumber: row.ModelNumber,''',1)
service.write_text(sb)
# Preserve the API, metadata and tenant checks; guard every parent-changing path.
for name,node,returned in [('Create','uuid.Nil','EntityOut{}, err'),('CreateFromTemplate','uuid.Nil','EntityOut{}, err'),('UpdateByGroup','data.ID','EntityOut{}, err'),('Patch','id','err')]:
    match=re.search(r'^func \(r \*EntityRepository\) '+name+r'\([^\n]+\{',text,re.M);assert match,name
    start=match.end();end=text.find('\nfunc ',start);end=len(text) if end<0 else end
    body=text[start:end];anchor='\tif err := assertEntityTypeInGroup(ctx, r.db.EntityType, gid, data.EntityTypeID); err != nil {';assert body.count(anchor)==1,name
    guard=f'\tif err := r.validateHierarchyParent(ctx, gid, {node}, data.ParentID); err != nil {{\n\t\trecordSpanError(span, err)\n\t\treturn {returned}\n\t}}\n'
    body=body.replace(anchor,guard+anchor)
    text=text[:start]+'\n\thierarchyWriteMu.Lock()\n\tdefer hierarchyWriteMu.Unlock()\n'+body+text[end:]
start=text.index('\tif data.SyncChildEntityLocations {');end=text.index('\n\t_, execSpan :=',start)
text=text[:start]+'\t// Descendants keep their parent edges and follow this container naturally.\n'+text[end:]
start=text.index('func patchSyncChildLocations(');end=text.index('\nfunc ',start)
header=text[start:text.index('{',start)+1]
text=text[:start]+header+'\n\t// One native parent edge already preserves each child inside its container.\n\treturn nil\n}\n'+text[end:]
start=text.index('func (r *EntityRepository) Tree(');end=text.index('\nfunc ConvertEntitiesToTree(',start)
header=text[start:text.index('{',start)+1]
text=text[:start]+header+'\n\treturn r.hierarchyTree(ctx, gid, tq.WithItems)\n}\n'+text[end:]
# An explicit optional PATCH field distinguishes clearing a parent from omitting it.
start=text.index('\tEntityPatch struct {');end=text.index('\n\t}',start)
text=text[:end]+'\n\t\tClearParent bool `json:"clearParent,omitempty"`'+text[end:]
start=text.index('func (r *EntityRepository) Patch(');end=text.index('\nfunc ',start)
body=text[start:end]
anchor='\tif data.ParentID != uuid.Nil {\n\t\tq.SetParentID(data.ParentID)\n\t}'
assert body.count(anchor)==1
body=body.replace(anchor, '\tif data.ClearParent {\n\t\tq.ClearParent()\n\t} else if data.ParentID != uuid.Nil {\n\t\tq.SetParentID(data.ParentID)\n\t}')
guard='\tif data.ClearParent && data.ParentID != uuid.Nil { return hierarchyError("Choose a parent or clear it, not both") }\n'
body=body.replace('\tctx, span :=',guard+'\tctx, span :=',1)
text=text[:start]+body+text[end:]
# Preserve ancestor types and tenant boundaries; UNION stops legacy cycles.
start=text.index('func (r *EntityRepository) PathForEntity(');end=text.index('\nfunc ',start)
body=text[start:end]
body=body.replace('UNION ALL','UNION').replace('JOIN entity_path ep ON e.id = ep.entity_children','JOIN entity_path ep ON e.id = ep.entity_children\n\t\tWHERE e.group_entities = $2')
body=body.replace('SELECT id, name\n\t  FROM entity_path', "SELECT ep.id, ep.name, CASE WHEN et.is_location THEN 'location' ELSE 'item' END\n\t  FROM entity_path ep\n\t  JOIN entities e ON e.id = ep.id\n\t  JOIN entity_types et ON et.id = e.entity_type_entities")
body=body.replace('\t\tentry.Type = EntityPathTypeLocation\n','').replace('rows.Scan(&entry.ID, &entry.Name)', 'rows.Scan(&entry.ID, &entry.Name, &entry.Type)')
text=text[:start]+body+text[end:]
# Allocate a missing native code atomically when an entity becomes an item.
# The existing update keeps its validation and lifecycle fields; move its
# entity update into the same Ent transaction as the counter allocation.
start=text.index('func (r *EntityRepository) UpdateByGroup(')
end=text.index('\nfunc ',start)
body=text[start:end]
anchor='''\tq := r.db.Entity.Update().Where(entity.ID(data.ID), entity.HasGroupWith(group.ID(gid))).'''
assert body.count(anchor)==1
setup='''\tshortCodeTx, err := r.db.Tx(ctx)
\tif err != nil { recordSpanError(span, err); return EntityOut{}, err }
\tshortCodeTxCommitted := false
\tdefer func() { if !shortCodeTxCommitted { _ = shortCodeTx.Rollback() } }()
\tcurrent, err := shortCodeTx.Entity.Query().Where(entity.ID(data.ID), entity.HasGroupWith(group.ID(gid))).Only(ctx)
\tif err != nil { recordSpanError(span, err); return EntityOut{}, err }
\ttargetTypeID := data.EntityTypeID
\tif targetTypeID == uuid.Nil {
\t\tcurrentType, err := current.QueryEntityType().Only(ctx)
\t\tif err != nil { recordSpanError(span, err); return EntityOut{}, err }
\t\ttargetTypeID = currentType.ID
\t}
\ttargetType, err := shortCodeTx.EntityType.Get(ctx, targetTypeID)
\tif err != nil { recordSpanError(span, err); return EntityOut{}, err }
\tshortCode := ""
\tif !targetType.IsLocation && (current.ShortCode == nil || *current.ShortCode == "") {
\t\tshortCode, err = allocateShortCode(ctx, shortCodeTx, gid, data.ModelNumber, data.Name)
\t\tif err != nil { recordSpanError(span, err); return EntityOut{}, err }
\t}
\tq := shortCodeTx.Entity.Update().Where(entity.ID(data.ID), entity.HasGroupWith(group.ID(gid))).'''
body=body.replace(anchor,setup,1)
anchor='''\t\tSetSyncChildEntityLocations(data.SyncChildEntityLocations)
'''
assert body.count(anchor)==1
body=body.replace(anchor,anchor+'''\tif shortCode != "" { q.SetShortCode(shortCode) }
''',1)
# Error logging is slightly different across pinned upstream revisions; insert
# commit after the exact q.Exec error block found in the checked-out source.
exec_start=body.index('err = q.Exec(ctx)')
exec_close=body.index('\n\texecSpan.End()',exec_start)
block=body[exec_start:exec_close]
assert block.rstrip().endswith('}')
body=body[:exec_close]+'''\n\tif err := shortCodeTx.Commit(); err != nil {
\t\trecordSpanError(span, err)
\t\treturn EntityOut{}, err
\t}
\tshortCodeTxCommitted = true'''+body[exec_close:]
refresh='''\tif err := refreshDisplayIDBasesForSubtree(ctx, shortCodeTx, gid, data.ID); err != nil {
		recordSpanError(span, err)
		return EntityOut{}, err
	}
'''
body=body.replace('\tif err := shortCodeTx.Commit();',refresh+'\tif err := shortCodeTx.Commit();',1)
text=text[:start]+body+text[end:]
# Patch already owns an Ent transaction. When it changes an uncoded location
# into an item, allocate from the persisted model/name in that same transaction.
start=text.index('func (r *EntityRepository) Patch(')
end=text.index('\nfunc ',start)
body=text[start:end]
anchor='''\tq := tx.Entity.Update().
		Where(
			entity.ID(id),
			entity.HasGroupWith(group.ID(gid)),
		)

	if data.ImportRef != nil {'''
assert body.count(anchor)==1
replacement='''	current, err := tx.Entity.Query().Where(entity.ID(id), entity.HasGroupWith(group.ID(gid))).Only(ctx)
	if err != nil { recordSpanError(span, err); return err }
	targetTypeID := data.EntityTypeID
	if targetTypeID == uuid.Nil {
		currentType, err := current.QueryEntityType().Only(ctx)
		if err != nil { recordSpanError(span, err); return err }
		targetTypeID = currentType.ID
	}
	targetType, err := tx.EntityType.Get(ctx, targetTypeID)
	if err != nil { recordSpanError(span, err); return err }
	shortCode := ""
	if !targetType.IsLocation && (current.ShortCode == nil || *current.ShortCode == "") {
		shortCode, err = allocateShortCode(ctx, tx, gid, current.ModelNumber, current.Name)
		if err != nil { recordSpanError(span, err); return err }
	}
	q := tx.Entity.Update().
		Where(
			entity.ID(id),
			entity.HasGroupWith(group.ID(gid)),
		)

	if shortCode != "" { q.SetShortCode(shortCode) }

	if data.ImportRef != nil {'''
body=body.replace(anchor,replacement,1)
text=text[:start]+body+text[end:]
# Recompute the changed item and all descendant path keys before Patch commits.
start=text.index('func (r *EntityRepository) Patch(')
end=text.index('\nfunc ',start)
body=text[start:end]
commit='\tif err := tx.Commit(); err != nil {'
if commit in body:
    body=body.replace(commit,'\tif err := refreshDisplayIDBasesForSubtree(ctx, tx, gid, id); err != nil { recordSpanError(span, err); return err }\n'+commit,1)
text=text[:start]+body+text[end:]
# Location creation and moves maintain the persisted display-ID key too.
start=text.index('func (r *EntityRepository) CreateContainer(')
end=text.index('\nfunc ',start)
body=text[start:end]
save='\tresult, err := q.Save(ctx)'
assert body.count(save)==1
body=body.replace(save,'''\ttypeID := data.EntityTypeID
\tif typeID == uuid.Nil { resolvedTypeID, resolveErr := r.resolveDefaultEntityType(ctx, gid, true); if resolveErr != nil { return EntityOut{}, resolveErr }; typeID = resolvedTypeID }
\tbase, err := displayIDBaseFor(ctx, r.db, gid, typeID, data.ParentID)
\tif err != nil { recordSpanError(span, err); return EntityOut{}, err }
\tq.SetDisplayIDBase(base)
'''+save,1)
text=text[:start]+body+text[end:]
start=text.index('func (r *EntityRepository) UpdateContainer(')
end=text.index('\nfunc ',start)
body=text[start:end]
body=body.replace('\tdefer span.End()','''\tdefer span.End()
	hierarchyWriteMu.Lock()
	defer hierarchyWriteMu.Unlock()
\ttx, err := r.db.Tx(ctx)
\tif err != nil { recordSpanError(span, err); return EntityOut{}, err }
\tcommitted := false
\tdefer func(){ if !committed { _ = tx.Rollback() } }()''',1)
body=body.replace('q := r.db.Entity.Update().','q := tx.Entity.Update().',1)
hierarchy_anchor='\tq := tx.Entity.Update().'
assert body.count(hierarchy_anchor)==1
body=body.replace(hierarchy_anchor,'''\tif err := r.validateHierarchyParent(ctx,gid,id,data.ParentID); err != nil { recordSpanError(span,err); return EntityOut{},err }
'''+hierarchy_anchor,1)
body=body.replace('''\t_, err := q.Save(ctx)
\tif err != nil {
\t\trecordSpanError(span, err)
\t\treturn EntityOut{}, err
\t}
''','''\t_, err = q.Save(ctx)
\tif err != nil { recordSpanError(span, err); return EntityOut{}, err }
\tif err := refreshDisplayIDBasesForSubtree(ctx, tx, gid, id); err != nil { recordSpanError(span, err); return EntityOut{}, err }
\tif err := tx.Commit(); err != nil { recordSpanError(span, err); return EntityOut{}, err }
\tcommitted = true
''',1)
text=text[:start]+body+text[end:]
for name in ('CreateContainer','Duplicate'):
    match=re.search(r'^func \(r \*EntityRepository\) '+name+r'\([^\n]+\{',text,re.M)
    assert match,name
    text=text[:match.end()]+'\n\thierarchyWriteMu.Lock()\n\tdefer hierarchyWriteMu.Unlock()'+text[match.end():]
source.write_text(text)
type_source=BUILD/'internal/data/repo/repo_entity_types.go'; type_text=type_source.read_text()
type_start=type_text.index('func (r *EntityTypeRepository) Update(')
type_end=type_text.index('\nfunc ',type_start)
type_body=type_text[type_start:type_end]
type_header_end=type_body.index('{')+1
type_body=type_body[:type_header_end]+'\n\thierarchyWriteMu.Lock()\n\tdefer hierarchyWriteMu.Unlock()'+type_body[type_header_end:]
type_anchor='\tq := r.db.EntityType.Update().'
assert type_body.count(type_anchor)==1
type_body=type_body.replace(type_anchor,'''\ttx, err := r.db.Tx(ctx)
\tif err != nil { return EntityTypeSummary{}, err }
\tcommitted := false
\tdefer func(){ if !committed { _ = tx.Rollback() } }()
\tq := tx.EntityType.Update().''',1)
type_save='''\t_, err := q.Save(ctx)
\tif err != nil {
\t\treturn EntityTypeSummary{}, err
\t}
'''
assert type_body.count(type_save)==1
type_body=type_body.replace(type_save,'''\t_, err = q.Save(ctx)
\tif err != nil { return EntityTypeSummary{}, err }
\tif err := refreshDisplayIDBasesForType(ctx, tx, gid, data.ID); err != nil { return EntityTypeSummary{}, err }
\tif err := tx.Commit(); err != nil { return EntityTypeSummary{}, err }
\tcommitted = true
''',1)
type_text=type_text[:type_start]+type_body+type_text[type_end:]
type_source.write_text(type_text)
# Container detail/create responses use the same derived ID population path.
get_container_start=text.index('func (r *EntityRepository) GetContainerByGroup(')
get_container_end=text.index('\nfunc ',get_container_start)
get_container_body=text[get_container_start:get_container_end]
get_container_anchor='\tspan.SetAttributes(attribute.Int("entity.children.count", len(out.Children)))'
assert get_container_body.count(get_container_anchor)==1
get_container_body=get_container_body.replace(get_container_anchor,'''\tdisplayItems := []EntitySummary{out.EntitySummary}
	if err := r.populateDisplayIDs(ctx, gid, displayItems); err != nil { recordSpanError(span, err); return EntityOut{}, err }
	out.EntitySummary = displayItems[0]
	out.Parent = displayItems[0].Parent
'''+get_container_anchor,1)
text=text[:get_container_start]+get_container_body+text[get_container_end:]
create_container_start=text.index('func (r *EntityRepository) CreateContainer(')
create_container_end=text.index('\nfunc ',create_container_start)
create_container_body=text[create_container_start:create_container_end]
create_return='\treturn mapEntityOut(result), nil'
assert create_container_body.count(create_return)==1
create_container_body=create_container_body.replace(create_return,'''\tout := mapEntityOut(result)
	displayItems := []EntitySummary{out.EntitySummary}
	if err := r.populateDisplayIDs(ctx, gid, displayItems); err != nil { recordSpanError(span, err); return EntityOut{}, err }
	out.EntitySummary = displayItems[0]
	return out, nil''',1)
text=text[:create_container_start]+create_container_body+text[create_container_end:]
text=patch_display_id_delete_paths(text)
source.write_text(text)
# Native, password-free member profiles reuse the existing user/settings tables.
users=BUILD/'internal/data/repo/repo_users.go';body=users.read_text()
anchor='\t\tID    uuid.UUID `json:"id"`\n\t}'
assert body.count(anchor)==1
body=body.replace(anchor,'\t\tID    uuid.UUID `json:"id"`\n\t\tAvatar string `json:"avatar,omitempty"`\n\t}')
start=body.index('func mapUserSummary(');end=body.index('\nfunc ',start)
part=body[start:end].replace('Email: user.Email,','Email: memberPublicEmail(user),\n\t\tAvatar: memberProfileString(user,"avatar"),')
body=body[:start]+part+body[end:]
anchor='func (r *UserRepository) SetSettings(ctx context.Context, uid uuid.UUID, settings map[string]interface{}) error {'
assert body.count(anchor)==1
body=body.replace(anchor,anchor+'''\n\tmemberProfileMu.Lock(); defer memberProfileMu.Unlock()
\tcurrent, err := r.db.User.Get(ctx,uid); if err != nil { return err }
\tcopy := map[string]interface{}{}; for key,value := range settings { if key != memberProfileKey { copy[key] = value } }
\tif profile,ok := current.Settings[memberProfileKey]; ok { copy[memberProfileKey] = profile }
\tsettings = copy
''')
# The added lookup introduces err earlier in this one method.
start=body.index(anchor);end=body.index('\nfunc ',start)
part=body[start:end].replace('err := r.db.User.UpdateOneID(uid).SetSettings(settings).Exec(ctx)','err = r.db.User.UpdateOneID(uid).SetSettings(settings).Exec(ctx)')
body=body[:start]+part+body[end:]
anchor='err := r.db.User.UpdateOneID(id).SetDefaultGroupID(groupID).Exec(ctx)'
assert body.count(anchor)==1
body=body.replace(anchor,'q := r.db.User.UpdateOneID(id)\n\tif groupID == uuid.Nil { q.ClearDefaultGroupID() } else { q.SetDefaultGroupID(groupID) }\n\terr := q.Exec(ctx)')
users.write_text(body)
profile_repo=users.parent/'repo_member_profiles.go'
shutil.copy2(ROOT/'homebox-backend/repo_member_profiles.go',profile_repo)
profile_controller=BUILD/'app/api/handlers/v1/v1_ctrl_member_profiles.go'
shutil.copy2(ROOT/'homebox-backend/v1_ctrl_member_profiles.go',profile_controller)
routes=BUILD/'app/api/routes.go';body=routes.read_text()
anchor='\t\tr.Get("/entities", chain.ToHandlerFunc(v1Ctrl.HandleEntitiesGetAll(), userMW...))'
assert body.count(anchor)==1
body=body.replace(anchor,anchor+'\n\t\tr.Get("/entities/short-code/{code}", chain.ToHandlerFunc(v1Ctrl.HandleEntityByShortCode(), userMW...))',1)
anchor='\t\tr.Get("/groups/members", chain.ToHandlerFunc(v1Ctrl.HandleGroupMembersGetAll(), userMW...))'
assert body.count(anchor)==1
body=body.replace(anchor,anchor+'''\n\t\tr.Get("/groups/members/administration", chain.ToHandlerFunc(v1Ctrl.HandleMemberAdministration(), userMW...))
\t\tr.Post("/groups/members", chain.ToHandlerFunc(v1Ctrl.HandleBadgeMemberCreate(), userMW...))
\t\tr.Get("/groups/members/{user_id}/profile", chain.ToHandlerFunc(v1Ctrl.HandleMemberProfileGet(), userMW...))
\t\tr.Put("/groups/members/{user_id}/profile", chain.ToHandlerFunc(v1Ctrl.HandleMemberProfileUpdate(), userMW...))''')
routes.write_text(body)
groups=BUILD/'app/api/handlers/v1/v1_ctrl_group.go';body=groups.read_text()
start=body.index('func (ctrl *V1Controller) HandleGroupMemberRemove()');end=body.index('\n// HandleGroupInvitationsDelete',start)
part=body[start:end];anchor='\t\tauth := services.NewContext(r.Context())'
part=part.replace(anchor,anchor+'''\n\t\tif err := ctrl.requireMemberAdministrator(auth); err != nil { return nil,err }
\t\towner,err := ctrl.repo.Groups.IsOwnerOf(auth,userID,auth.GID); if err != nil { return nil,err }
\t\tif owner { return nil,validate.NewRequestError(errors.New("Collection owners cannot be removed here"),http.StatusBadRequest) }
''',1)
groups.write_text(body[:start]+part+body[end:])
# ponytail: repeated ancestor walks fit a workshop; use a shared visited-state
# closure if large, deep inventories make hierarchy reads costly.
shutil.copy2(ROOT/'homebox-backend/repo_hierarchy.go',source.parent/'repo_hierarchy.go')
# Template creation has its own HTTP validator; its parent must also be optional.
controller=BUILD/'app/api/handlers/v1/v1_ctrl_entity_templates.go'
body=controller.read_text();anchor='`json:"parentId"     validate:"required"`';assert body.count(anchor)==1
controller.write_text(body.replace(anchor,'`json:"parentId"     extensions:"x-nullable"`'))
# Keep the published JSON API contract consistent with these native extensions.
def patch_contract(document):
    schemas=document.get('definitions') or document['components']['schemas']
    for name in ('repo.EntitySummary','repo.EntityOut'):
        schemas[name]['properties']['displayId']={'type':'string','description':'Generated from item type and full current storage path; a deterministic collision counter is added only when multiple assets share the same base path. UNKNOWN is used if every type and path name normalizes to an empty segment. The path changes when the item moves; native identifiers remain stable.'}
        schemas[name]['properties']['shortCode']={'type':'string','description':'Stable native item short code; empty for locations.'}
    schemas['repo.EntityCreate']['properties']['modelNumber']={'type':'string','description':'Optional model number used when assigning the new item short code.'}
    schemas['v1.EntityTemplateCreateItemRequest']['properties']['modelNumber']={'type':'string','description':'Optional model number override; omitted preserves the template default.'}
    template=schemas['v1.EntityTemplateCreateItemRequest']
    template['required']=[field for field in template.get('required',[]) if field!='parentId']
    template['properties']['parentId']['x-nullable']=True
    schemas['repo.EntityPatch']['properties']['clearParent']={'type':'boolean','description':'Clear the optional parent. Cannot be combined with parentId.'}
    schemas['repo.UserSummary']['properties']['avatar']={'type':'string','description':'Optional local PNG/JPEG profile picture; absent uses the generated avatar.'}
    schemas['v1.BadgeMemberCreate']={'type':'object','required':['requestKey','name'],'properties':{'requestKey':{'type':'string','format':'uuid','description':'Stable UUID v4 confirmation key, also the new native user ID.'},'name':{'type':'string','maxLength':255},'email':{'type':'string','description':'Optional contact email. No password or PIN is set.'}}}
    fields={key:{'type':'string'} for key in ('name','email','avatar','notes','updatedAt')}
    schemas['repo.MemberProfileUpdate']={'type':'object','required':['name','updatedAt'],'properties':fields}
    schemas['repo.MemberProfile']={'type':'object','properties':dict(fields,id={'type':'string','format':'uuid'},mode={'type':'string','enum':['badge-only','web-account']},editable={'type':'boolean'},protected={'type':'boolean'})}
    definitions='definitions' in document
    def reference(name):return {'$ref':('#/definitions/' if definitions else '#/components/schemas/')+name}
    def response(name,status='200'):
        value={'description':'Native collection member profile'}
        value.update({'schema':reference(name)} if definitions else {'content':{'application/json':{'schema':reference(name)}}})
        return {status:value,'403':{'description':'Requires ownership of the active collection'},'409':{'description':'Confirmation conflict or stale profile'}}
    create={'summary':'Create a native badge-only member by name','tags':['Group'],'security':[{'Bearer':[]}],'responses':response('repo.MemberProfile','201')}
    update={'summary':'Edit a member profile in its primary collection','tags':['Group'],'security':[{'Bearer':[]}],'responses':response('repo.MemberProfile')}
    path_parameter={'name':'user_id','in':'path','required':True}
    path_parameter.update({'type':'string'} if definitions else {'schema':{'type':'string','format':'uuid'}})
    if definitions:
        create['parameters']=[{'name':'payload','in':'body','required':True,'schema':reference('v1.BadgeMemberCreate')}]
        update['parameters']=[path_parameter,{'name':'payload','in':'body','required':True,'schema':reference('repo.MemberProfileUpdate')}]
    else:
        for operation,body in ((create,'v1.BadgeMemberCreate'),(update,'repo.MemberProfileUpdate')):operation['requestBody']={'required':True,'content':{'application/json':{'schema':reference(body)}}}
        update['parameters']=[path_parameter]
    document['paths']['/v1/groups/members']['post']=create
    document['paths']['/v1/groups/members/{user_id}/profile']={'get':{'summary':'Read an authorized member profile','tags':['Group'],'parameters':[path_parameter],'security':[{'Bearer':[]}],'responses':response('repo.MemberProfile')},'put':update}
    document['paths']['/v1/groups/members/administration']={'get':{'summary':'Check active collection ownership for account management','tags':['Group'],'security':[{'Bearer':[]}],'responses':{'200':{'description':'canManage reports the native per-collection ownership check'}}}}
    code_parameter={'name':'code','in':'path','required':True}
    code_parameter.update({'type':'string'} if definitions else {'schema':{'type':'string'}})
    code_ref=reference('repo.EntityOut')
    code_response={'description':'Exact active item in the authenticated collection'}
    code_response.update({'schema':code_ref} if definitions else {'content':{'application/json':{'schema':code_ref}}})
    document['paths']['/v1/entities/short-code/{code}']={'get':{'summary':'Resolve an item short code exactly','tags':['Entities'],'parameters':[code_parameter],'security':[{'Bearer':[]}],'responses':{'200':code_response,'400':{'description':'Invalid short-code format'},'404':{'description':'No active item matches the code'},'409':{'description':'The code conflicts with another native item identifier'}}}}
    return document
for name in ('swagger.json','openapi-3.json'):
    path=BUILD/'app/api/static/docs'/name
    path.write_text(json.dumps(patch_contract(json.loads(path.read_text())),indent=2)+'\n')
docs=BUILD/'app/api/static/docs/docs.go';body=docs.read_text()
start=body.index('const docTemplate = `')+len('const docTemplate = `');end=body.index('`',start)
raw=body[start:end].replace('{{ marshal .Schemes }}','"__CACI_SCHEMES__"')
raw=json.dumps(patch_contract(json.loads(raw)),indent=2).replace('"__CACI_SCHEMES__"','{{ marshal .Schemes }}').replace('`',r'\u0060')
docs.write_text(body[:start]+raw+body[end:])
# Embed the current verified frontend; the public gateway selects its own release.
shutil.copytree(ROOT/'work/homebox-ui-current',BUILD/'app/api/static/public',dirs_exist_ok=True)
subprocess.run([str(go.with_name('gofmt')),'-w',str(schema),str(source),str(source.parent/'repo_hierarchy.go'),str(type_source),str(BUILD/'internal/data/repo/repo_display_ids.go'),str(BUILD/'internal/data/repo/repo_display_ids_test.go'),str(BUILD/'internal/data/displayids/display_id.go'),str(BUILD/'internal/data/displayids/display_id_test.go'),str(BUILD/'internal/data/displayids/migration.go'),str(BUILD/'internal/data/migrations/sqlite3/20260514120000_display_id_bases.go'),str(BUILD/'internal/data/migrations/postgres/20260514120001_display_id_bases.go'),str(controller),str(docs),str(users),str(profile_repo),str(profile_controller),str(routes),str(groups),str(service),str(BUILD/'internal/data/repo/repo_short_codes.go'),str(BUILD/'internal/data/repo/repo_short_codes_test.go'),str(BUILD/'internal/data/ent/short_code_tx.go'),str(BUILD/'internal/data/shortcodes/migration_test.go'),str(BUILD/'app/api/handlers/v1/v1_ctrl_item_short_codes.go')],check=True)
pin=source_commit(ROOT/'upstream/homebox')
patch_base,_,patchset_sha256=load_patchset(ROOT)
if patch_base!=pin:raise ValueError('Homebox patchset source pin mismatch during backend build')
flags='-s -w -X main.version=0.26.2-caci.2-shortcodes -X main.commit='+pin+'+hierarchy+members+shortcodes -X main.date='+datetime.now(timezone.utc).isoformat()
subprocess.run([str(go),'build','-mod=readonly','-p','2','-trimpath','-ldflags',flags,'-o',str(BUILD/'homebox'),'./app/api'],cwd=BUILD,env=env,check=True)
receipt={'upstream':pin,'patchset_sha256':patchset_sha256,'backend_overlay_sha256':source_tree_digest(ROOT/'homebox-backend'),'backend_builder_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'frontend_sha256':source_tree_digest(ROOT/'work/homebox-ui-current'),'hierarchy_source_sha256':hashlib.sha256((ROOT/'homebox-backend/repo_hierarchy.go').read_bytes()).hexdigest(),'member_sources_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'homebox-backend/repo_member_profiles.go',ROOT/'homebox-backend/v1_ctrl_member_profiles.go')},'short_code_sources_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'homebox-backend/repo_short_codes.go',ROOT/'homebox-backend/ent_tx_sql.go',ROOT/'homebox-backend/v1_ctrl_item_short_codes.go',ROOT/'homebox-backend/shortcodes/short_code.go',ROOT/'homebox-backend/shortcodes/migration.go',ROOT/'homebox-backend/20260513120000_item_short_codes.go',ROOT/'homebox-backend/20260513120001_item_short_codes.go')},'binary_sha256':hashlib.sha256((BUILD/'homebox').read_bytes()).hexdigest(),'version':'0.26.2-caci.2-shortcodes','deployed':False}
(BUILD/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
