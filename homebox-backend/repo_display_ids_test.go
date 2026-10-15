package repo

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/stretchr/testify/require"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/entity"
)

// BenchmarkDisplayIDCollisionFamily5K measures returned-page population and
// exact generated-ID lookup against a 5,000-item collision family. Run with
// go test -run '^$' -bench BenchmarkDisplayIDCollisionFamily5K -benchmem.
func BenchmarkDisplayIDCollisionFamily5K(b *testing.B) {
	ctx, gid := context.Background(), tGroup.ID
	const population = 5000
	ids := make([]uuid.UUID, 0, population)
	var rootID, middleID, columnID, leafID, itemTypeID uuid.UUID
	b.Cleanup(func() {
		for start := 0; start < len(ids); start += 500 {
			end := start + 500
			if end > len(ids) {
				end = len(ids)
			}
			_, _ = tClient.Entity.Delete().Where(entity.IDIn(ids[start:end]...)).Exec(ctx)
		}
		for _, id := range []uuid.UUID{leafID, columnID, middleID, rootID} {
			if id != uuid.Nil {
				_ = tRepos.Entities.DeleteContainerByGroup(ctx, gid, id)
			}
		}
		if itemTypeID != uuid.Nil {
			_ = tRepos.EntityTypes.Delete(ctx, gid, itemTypeID)
		}
	})
	locationType, err := tRepos.EntityTypes.GetDefault(ctx, gid, true)
	if err != nil {
		b.Fatal(err)
	}
	root, err := tRepos.Entities.CreateContainer(ctx, gid, EntityCreate{Name: "D", EntityTypeID: locationType.ID})
	if err != nil {
		b.Fatal(err)
	}
	rootID = root.ID
	middle, err := tRepos.Entities.CreateContainer(ctx, gid, EntityCreate{Name: "GC", ParentID: root.ID, EntityTypeID: locationType.ID})
	if err != nil {
		b.Fatal(err)
	}
	middleID = middle.ID
	column, err := tRepos.Entities.CreateContainer(ctx, gid, EntityCreate{Name: "C", ParentID: middle.ID, EntityTypeID: locationType.ID})
	if err != nil {
		b.Fatal(err)
	}
	columnID = column.ID
	leaf, err := tRepos.Entities.CreateContainer(ctx, gid, EntityCreate{Name: "1", ParentID: column.ID, EntityTypeID: locationType.ID})
	if err != nil {
		b.Fatal(err)
	}
	leafID = leaf.ID
	itemType, err := tRepos.EntityTypes.Create(ctx, gid, EntityTypeCreate{Name: "Bin"})
	if err != nil {
		b.Fatal(err)
	}
	itemTypeID = itemType.ID
	builders := make([]*ent.EntityCreate, population)
	for i := range builders {
		id := uuid.New()
		ids = append(ids, id)
		builders[i] = tClient.Entity.Create().
			SetID(id).SetName("Synthetic bin").SetDescription("").
			SetGroupID(gid).SetEntityTypeID(itemType.ID).SetParentID(leaf.ID).
			SetDisplayIDBase("BIN-D-GC-C-1").SetAssetID(int64(i + 1))
	}
	for start := 0; start < len(builders); start += 500 {
		end := start + 500
		if end > len(builders) {
			end = len(builders)
		}
		if _, err := tClient.Entity.CreateBulk(builders[start:end]...).Save(ctx); err != nil {
			b.Fatal(err)
		}
	}
	pageRecords, err := tClient.Entity.Query().Where(entity.IDIn(ids[:50]...)).WithParent().WithEntityType().All(ctx)
	if err != nil {
		b.Fatal(err)
	}
	page := make([]EntitySummary, 0, len(pageRecords))
	for _, record := range pageRecords {
		page = append(page, mapEntitySummary(record))
	}
	target := "BIN-D-GC-C-1-5000"
	b.Run("page_population_50_of_5000", func(b *testing.B) {
		b.ReportAllocs()
		b.ReportMetric(population, "entities/family")
		b.ReportMetric(float64(len(page)), "entities/page")
		for i := 0; i < b.N; i++ {
			items := append([]EntitySummary(nil), page...)
			if err := tRepos.Entities.populateDisplayIDs(ctx, gid, items); err != nil {
				b.Fatal(err)
			}
		}
	})
	b.Run("exact_generated_id_lookup", func(b *testing.B) {
		b.ReportAllocs()
		b.ReportMetric(population, "entities/family")
		for i := 0; i < b.N; i++ {
			if _, found, err := tRepos.Entities.findDisplayIDSearchMatch(ctx, gid, target); err != nil || !found {
				b.Fatalf("exact lookup found=%v err=%v", found, err)
			}
		}
	})
}

func TestFormatDisplayIDUsesTypeAndFullLocationPath(t *testing.T) {
	got := formatDisplayID("Bin", []string{"D", "GC", "C", "1"})
	if got != "BIN-D-GC-C-1" {
		t.Fatalf("formatDisplayID() = %q", got)
	}
}

func TestFormatDisplayIDNormalizesWordsAndPunctuation(t *testing.T) {
	got := formatDisplayID("Hand Tools", []string{"Garage / Cabinet", "Drawer #2"})
	if got != "HAND-TOOLS-GARAGE-CABINET-DRAWER-2" {
		t.Fatalf("formatDisplayID() = %q", got)
	}
}

func TestFormatDisplayIDMarksUnassignedLocation(t *testing.T) {
	got := formatDisplayID("Tool", nil)
	if got != "TOOL-UNLOCATED" {
		t.Fatalf("formatDisplayID() = %q", got)
	}
}

func TestIsDisplayIDSearchTreatsTrailingLocationNumberAsPath(t *testing.T) {
	for _, value := range []string{"BIN-D-GC-C-1", "bin-d-gc-c-1", "PART-SABC-123", "BIN", "D", "PART", "123456"} {
		if !isDisplayIDSearch(value) {
			t.Errorf("isDisplayIDSearch(%q) = false, want true", value)
		}
	}
	for _, value := range []string{"A drawer", "BIN--1", "-BIN-D-C", "BIN-D-C-", "12 34 56"} {
		if isDisplayIDSearch(value) {
			t.Errorf("isDisplayIDSearch(%q) = true, want false", value)
		}
	}
	if !isDisplayIDSearch("UNKNOWN") || !isDisplayIDSearch("UNLOCATED") {
		t.Fatal("generated one-segment sentinels should be display-ID searches")
	}
}

func TestEntityDisplayIDChangesWithTypeAndLocationButKeepsNativeIDs(t *testing.T) {
	ctx := context.Background()
	groupID := tGroup.ID
	locationType := useContainerEntityType(t)
	makeLocation := func(name string, parent uuid.UUID) EntityOut {
		out, err := tRepos.Entities.CreateContainer(ctx, groupID, EntityCreate{
			Name: name, ParentID: parent, EntityTypeID: locationType.ID,
		})
		require.NoError(t, err)
		require.NotEmpty(t, out.DisplayID)
		detail, err := tRepos.Entities.GetContainerByGroup(ctx, groupID, out.ID)
		require.NoError(t, err)
		require.Equal(t, out.DisplayID, detail.DisplayID)
		t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, out.ID) })
		return out
	}
	root := makeLocation("D", uuid.Nil)
	mid := makeLocation("GC", root.ID)
	column := makeLocation("C", mid.ID)
	slot := makeLocation("1", column.ID)
	other := makeLocation("E", uuid.Nil)

	binType, err := tRepos.EntityTypes.Create(ctx, groupID, EntityTypeCreate{Name: "Bin"})
	require.NoError(t, err)
	drawerType, err := tRepos.EntityTypes.Create(ctx, groupID, EntityTypeCreate{Name: "Drawer"})
	require.NoError(t, err)

	item, err := tRepos.Entities.Create(ctx, groupID, EntityCreate{
		Name: "Heat shrink", ParentID: slot.ID, EntityTypeID: binType.ID,
		ModelNumber: "ET1001",
	})
	require.NoError(t, err)
	assetID, err := tRepos.Entities.GetHighestAssetID(ctx, groupID)
	require.NoError(t, err)
	assetID += 41
	require.NoError(t, tRepos.Entities.SetAssetID(ctx, groupID, item.ID, assetID))
	item, err = tRepos.Entities.GetOneByGroup(ctx, groupID, item.ID)
	require.NoError(t, err)
	require.Equal(t, "BIN-D-GC-C-1", item.DisplayID)
	originalUUID, originalAssetID, originalShortCode := item.ID, item.AssetID, item.ShortCode
	require.NotEqual(t, AssetID(1), originalAssetID, "the terminal 1 is the storage path segment, not the native asset ID")
	require.NotEmpty(t, originalShortCode)

	duplicateRoot := makeLocation("D", uuid.Nil)
	duplicateMid := makeLocation("GC", duplicateRoot.ID)
	duplicateColumn := makeLocation("C", duplicateMid.ID)
	duplicateSlot := makeLocation("1", duplicateColumn.ID)
	duplicateItem, err := tRepos.Entities.Create(ctx, groupID, EntityCreate{
		Name: "Heat shrink duplicate path", ParentID: duplicateSlot.ID, EntityTypeID: binType.ID,
	})
	require.NoError(t, err)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, duplicateItem.ID) })
	duplicateAssetID := assetID
	require.NoError(t, tRepos.Entities.SetAssetID(ctx, groupID, duplicateItem.ID, duplicateAssetID))
	duplicateItem, err = tRepos.Entities.GetOneByGroup(ctx, groupID, duplicateItem.ID)
	require.NoError(t, err)
	item, err = tRepos.Entities.GetOneByGroup(ctx, groupID, item.ID)
	require.NoError(t, err)
	require.NotEqual(t, item.ShortCode, duplicateItem.ShortCode, "short codes are unique within a group")
	require.ElementsMatch(t, []string{"BIN-D-GC-C-1-1", "BIN-D-GC-C-1-2"}, []string{item.DisplayID, duplicateItem.DisplayID})
	for _, candidate := range []EntityOut{item, duplicateItem} {
		search, err := tRepos.Entities.QueryByGroup(ctx, groupID, EntityQuery{
			Page: -1, PageSize: -1, Search: candidate.DisplayID,
		})
		require.NoError(t, err)
		require.Len(t, search.Items, 1)
		require.Equal(t, candidate.ID, search.Items[0].ID)
	}

	ordinaryItem, err := tRepos.Entities.Create(ctx, groupID, EntityCreate{
		Name: "Ordinary part", Barcode: "PART-SABC-123", ParentID: slot.ID, EntityTypeID: binType.ID,
	})
	require.NoError(t, err)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, ordinaryItem.ID) })
	search, err := tRepos.Entities.QueryByGroup(ctx, groupID, EntityQuery{
		Page: -1, PageSize: -1, Search: " PART-SABC-123 ",
	})
	require.NoError(t, err)
	foundOrdinaryMatch := false
	for _, candidate := range search.Items {
		if candidate.ID == ordinaryItem.ID {
			foundOrdinaryMatch = true
			break
		}
	}
	require.True(t, foundOrdinaryMatch, "a code-shaped ordinary name must remain searchable alongside exact display-ID matching")
	require.NoError(t, tRepos.Entities.DeleteByGroup(ctx, groupID, ordinaryItem.ID))

	updated, err := tRepos.Entities.UpdateByGroup(ctx, groupID, EntityUpdate{
		ID: item.ID, Name: item.Name, ParentID: other.ID, EntityTypeID: drawerType.ID,
		AssetID: item.AssetID, ModelNumber: item.ModelNumber, Manufacturer: item.Manufacturer,
		Description: item.Description, Quantity: item.Quantity, Insured: item.Insured,
		Archived: item.Archived, SerialNumber: item.SerialNumber, Barcode: &item.Barcode,
	})
	require.NoError(t, err)
	require.Equal(t, "DRAWER-E", updated.DisplayID)
	require.NotEqual(t, item.DisplayID, updated.DisplayID)
	duplicateItem, err = tRepos.Entities.GetOneByGroup(ctx, groupID, duplicateItem.ID)
	require.NoError(t, err)
	require.Equal(t, "BIN-D-GC-C-1", duplicateItem.DisplayID, "the remaining item drops its counter when the collision is removed")
	require.Equal(t, originalUUID, updated.ID)
	require.Equal(t, originalAssetID, updated.AssetID)
	require.Equal(t, originalShortCode, updated.ShortCode)

	search, err = tRepos.Entities.QueryByGroup(ctx, groupID, EntityQuery{
		Page: -1, PageSize: -1, Search: updated.DisplayID,
	})
	require.NoError(t, err)
	require.Len(t, search.Items, 1)
	require.Equal(t, updated.ID, search.Items[0].ID)
	require.Equal(t, updated.DisplayID, search.Items[0].DisplayID)
}

func TestDisplayIDBaseRefreshesAfterTypeRename(t *testing.T) {
	ctx, gid := context.Background(), tGroup.ID
	locationType := useContainerEntityType(t)
	loc, err := tRepos.Entities.CreateContainer(ctx, gid, EntityCreate{Name:"D",EntityTypeID:locationType.ID})
	require.NoError(t,err)
	typeInfo, err := tRepos.EntityTypes.Create(ctx,gid,EntityTypeCreate{Name:"Bin"})
	require.NoError(t,err)
	item, err := tRepos.Entities.Create(ctx,gid,EntityCreate{Name:"Item",ParentID:loc.ID,EntityTypeID:typeInfo.ID})
	require.NoError(t,err)
	t.Cleanup(func(){ _=tRepos.Entities.Delete(ctx,item.ID); _=tRepos.Entities.DeleteContainerByGroup(ctx,gid,loc.ID) })
	require.Equal(t,"BIN-D",item.DisplayID)
	_,err=tRepos.EntityTypes.Update(ctx,gid,EntityTypeUpdate{ID:typeInfo.ID,Name:"New Bin",IsLocation:false,Icon:typeInfo.Icon})
	require.NoError(t,err)
	item,err=tRepos.Entities.GetOneByGroup(ctx,gid,item.ID)
	require.NoError(t,err)
	require.Equal(t,"NEW-BIN-D",item.DisplayID)
}

func TestEntityTypeRenameSerializesWithConcurrentAssetCreate(t *testing.T) {
	ctx, gid := context.Background(), tGroup.ID
	locationType := useContainerEntityType(t)
	location, err := tRepos.Entities.CreateContainer(ctx, gid, EntityCreate{Name:"D", EntityTypeID:locationType.ID})
	require.NoError(t, err)
	typeInfo, err := tRepos.EntityTypes.Create(ctx, gid, EntityTypeCreate{Name:"Bin"})
	require.NoError(t, err)
	existing, err := tRepos.Entities.Create(ctx, gid, EntityCreate{Name:"Existing", ParentID:location.ID, EntityTypeID:typeInfo.ID})
	require.NoError(t, err)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, existing.ID); _ = tRepos.Entities.DeleteContainerByGroup(ctx, gid, location.ID) })

	hierarchyWriteMu.Lock()
	locked := true
	defer func() { if locked { hierarchyWriteMu.Unlock() } }()
	updateStarted := make(chan struct{})
	updateDone := make(chan error, 1)
	go func() {
		close(updateStarted)
		_, err := tRepos.EntityTypes.Update(ctx, gid, EntityTypeUpdate{ID:typeInfo.ID, Name:"New Bin", IsLocation:false, Icon:typeInfo.Icon})
		updateDone <- err
	}()
	createStarted := make(chan struct{})
	createDone := make(chan struct { item EntityOut; err error }, 1)
	go func() {
		close(createStarted)
		item, err := tRepos.Entities.Create(ctx, gid, EntityCreate{Name:"Created During Rename", ParentID:location.ID, EntityTypeID:typeInfo.ID})
		createDone <- struct { item EntityOut; err error }{item, err}
	}()
	<-updateStarted
	<-createStarted
	select {
	case err := <-updateDone:
		t.Fatalf("type rename passed hierarchy lock: %v", err)
	case <-time.After(30 * time.Millisecond):
	}
	select {
	case result := <-createDone:
		t.Fatalf("asset create passed hierarchy lock: %v", result.err)
	case <-time.After(30 * time.Millisecond):
	}
	hierarchyWriteMu.Unlock()
	locked = false
	require.NoError(t, <-updateDone)
	created := <-createDone
	require.NoError(t, created.err)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, created.item.ID) })

	displayIDs := make([]string, 0, 2)
	for _, id := range []uuid.UUID{existing.ID, created.item.ID} {
		item, err := tRepos.Entities.GetOneByGroup(ctx, gid, id)
		require.NoError(t, err)
		require.Equal(t, "NEW-BIN-D", item.DisplayIDBase)
		displayIDs = append(displayIDs, item.DisplayID)
	}
	require.ElementsMatch(t, []string{"NEW-BIN-D-1", "NEW-BIN-D-2"}, displayIDs)
}

func TestDisplayIDBasesRefreshWhenDeletingLocationParent(t *testing.T) {
	ctx, gid := context.Background(), tGroup.ID
	locationType := useContainerEntityType(t)
	root,err:=tRepos.Entities.CreateContainer(ctx,gid,EntityCreate{Name:"D",EntityTypeID:locationType.ID}); require.NoError(t,err)
	child,err:=tRepos.Entities.CreateContainer(ctx,gid,EntityCreate{Name:"C",ParentID:root.ID,EntityTypeID:locationType.ID}); require.NoError(t,err)
	itemType,err:=tRepos.EntityTypes.Create(ctx,gid,EntityTypeCreate{Name:"Bin"}); require.NoError(t,err)
	item,err:=tRepos.Entities.Create(ctx,gid,EntityCreate{Name:"Item",ParentID:child.ID,EntityTypeID:itemType.ID}); require.NoError(t,err)
	t.Cleanup(func(){ _=tRepos.Entities.Delete(ctx,item.ID); _=tRepos.Entities.DeleteContainerByGroup(ctx,gid,child.ID) })
	require.Equal(t,"BIN-D-C",item.DisplayID)
	require.NoError(t,tRepos.Entities.DeleteContainerByGroup(ctx,gid,root.ID))
	item,err=tRepos.Entities.GetOneByGroup(ctx,gid,item.ID); require.NoError(t,err)
	require.Equal(t,"BIN-C",item.DisplayID)
}

func TestUpdateContainerRejectsCycleBeforeRefreshingDisplayIDs(t *testing.T) {
	ctx,gid:=context.Background(),tGroup.ID
	locationType:=useContainerEntityType(t)
	root,err:=tRepos.Entities.CreateContainer(ctx,gid,EntityCreate{Name:"A",EntityTypeID:locationType.ID}); require.NoError(t,err)
	child,err:=tRepos.Entities.CreateContainer(ctx,gid,EntityCreate{Name:"B",ParentID:root.ID,EntityTypeID:locationType.ID}); require.NoError(t,err)
	t.Cleanup(func(){ _=tRepos.Entities.DeleteContainerByGroup(ctx,gid,child.ID); _=tRepos.Entities.DeleteContainerByGroup(ctx,gid,root.ID) })
	_,err=tRepos.Entities.UpdateContainer(ctx,gid,root.ID,EntityUpdate{Name:"A",ParentID:child.ID})
	require.Error(t,err)
}

func TestDisplayIDBaseFallbackForUnicodeOnlyNames(t *testing.T) {
	ctx,gid:=context.Background(),tGroup.ID
	locationType:=useContainerEntityType(t)
	loc,err:=tRepos.Entities.CreateContainer(ctx,gid,EntityCreate{Name:"部屋",EntityTypeID:locationType.ID}); require.NoError(t,err)
	typeInfo,err:=tRepos.EntityTypes.Create(ctx,gid,EntityTypeCreate{Name:"物品"}); require.NoError(t,err)
	item,err:=tRepos.Entities.Create(ctx,gid,EntityCreate{Name:"工具",ParentID:loc.ID,EntityTypeID:typeInfo.ID}); require.NoError(t,err)
	t.Cleanup(func(){ _=tRepos.Entities.Delete(ctx,item.ID); _=tRepos.Entities.DeleteContainerByGroup(ctx,gid,loc.ID) })
	require.Equal(t,"UNKNOWN",item.DisplayID)
	search,err:=tRepos.Entities.QueryByGroup(ctx,gid,EntityQuery{Page:-1,PageSize:-1,Search:"UNKNOWN"}); require.NoError(t,err); require.Len(t,search.Items,1); require.Equal(t,item.ID,search.Items[0].ID)
	unlocated,err:=tRepos.Entities.Create(ctx,gid,EntityCreate{Name:"Unassigned",EntityTypeID:typeInfo.ID}); require.NoError(t,err)
	t.Cleanup(func(){ _=tRepos.Entities.Delete(ctx,unlocated.ID) })
	require.Equal(t,"UNLOCATED",unlocated.DisplayID)
	search,err=tRepos.Entities.QueryByGroup(ctx,gid,EntityQuery{Page:-1,PageSize:-1,Search:"UNLOCATED"}); require.NoError(t,err); require.Len(t,search.Items,1); require.Equal(t,unlocated.ID,search.Items[0].ID)
}

func TestMixedUnicodeDisplayIDBasesRemainSearchable(t *testing.T) {
	ctx, gid := context.Background(), tGroup.ID
	locationType := useContainerEntityType(t)
	unicodeLocation, err := tRepos.Entities.CreateContainer(ctx, gid, EntityCreate{Name: "部屋", EntityTypeID: locationType.ID})
	require.NoError(t, err)
	typeWithASCII, err := tRepos.EntityTypes.Create(ctx, gid, EntityTypeCreate{Name: "Bin"})
	require.NoError(t, err)
	binItem, err := tRepos.Entities.Create(ctx, gid, EntityCreate{Name: "Unicode path", ParentID: unicodeLocation.ID, EntityTypeID: typeWithASCII.ID})
	require.NoError(t, err)
	locationWithASCII, err := tRepos.Entities.CreateContainer(ctx, gid, EntityCreate{Name: "D", EntityTypeID: locationType.ID})
	require.NoError(t, err)
	typeWithUnicode, err := tRepos.EntityTypes.Create(ctx, gid, EntityTypeCreate{Name: "物品"})
	require.NoError(t, err)
	locationItem, err := tRepos.Entities.Create(ctx, gid, EntityCreate{Name: "Hammer", ParentID: locationWithASCII.ID, EntityTypeID: typeWithUnicode.ID})
	require.NoError(t, err)
	t.Cleanup(func() {
		_ = tRepos.Entities.Delete(ctx, binItem.ID)
		_ = tRepos.Entities.Delete(ctx, locationItem.ID)
		_ = tRepos.Entities.DeleteContainerByGroup(ctx, gid, unicodeLocation.ID)
		_ = tRepos.Entities.DeleteContainerByGroup(ctx, gid, locationWithASCII.ID)
	})
	require.Equal(t, "BIN", binItem.DisplayID)
	require.Equal(t, "D", locationItem.DisplayID)
	for _, item := range []EntityOut{binItem, locationItem} {
		result, err := tRepos.Entities.QueryByGroup(ctx, gid, EntityQuery{Page: -1, PageSize: -1, Search: item.DisplayID})
		require.NoError(t, err)
		found := false
		for _, candidate := range result.Items {
			if candidate.ID == item.ID {
				found = true
				break
			}
		}
		require.True(t, found, "exact search for generated display ID %q should include the item", item.DisplayID)
	}
}

func TestUnicodeOnlyCollisionIDsSearchFromSingleEntityReads(t *testing.T) {
	ctx, gid := context.Background(), tGroup.ID
	locationType := useContainerEntityType(t)
	location, err := tRepos.Entities.CreateContainer(ctx, gid, EntityCreate{Name:"部屋", EntityTypeID:locationType.ID})
	require.NoError(t, err)
	typeInfo, err := tRepos.EntityTypes.Create(ctx, gid, EntityTypeCreate{Name:"物品"})
	require.NoError(t, err)
	first, err := tRepos.Entities.Create(ctx, gid, EntityCreate{Name:"工具一", ParentID:location.ID, EntityTypeID:typeInfo.ID})
	require.NoError(t, err)
	second, err := tRepos.Entities.Create(ctx, gid, EntityCreate{Name:"工具二", ParentID:location.ID, EntityTypeID:typeInfo.ID})
	require.NoError(t, err)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, first.ID); _ = tRepos.Entities.Delete(ctx, second.ID); _ = tRepos.Entities.DeleteContainerByGroup(ctx, gid, location.ID) })

	first, err = tRepos.Entities.GetOneByGroup(ctx, gid, first.ID)
	require.NoError(t, err)
	second, err = tRepos.Entities.GetOneByGroup(ctx, gid, second.ID)
	require.NoError(t, err)
	require.ElementsMatch(t, []string{"UNKNOWN-1", "UNKNOWN-2"}, []string{first.DisplayID, second.DisplayID})
	for _, item := range []EntityOut{first, second} {
		result, err := tRepos.Entities.QueryByGroup(ctx, gid, EntityQuery{Page:-1, PageSize:-1, Search:item.DisplayID})
		require.NoError(t, err)
		require.Len(t, result.Items, 1)
		require.Equal(t, item.ID, result.Items[0].ID)
		require.Equal(t, item.DisplayID, result.Items[0].DisplayID)
	}
}

func TestCodeShapedSearchCombinesOrdinaryAndExactDisplayIDWithPagination(t *testing.T) {
	ctx, gid := context.Background(), tGroup.ID
	locationType := useContainerEntityType(t)
	root, err := tRepos.Entities.CreateContainer(ctx, gid, EntityCreate{Name:"SABC", EntityTypeID:locationType.ID})
	require.NoError(t, err)
	leaf, err := tRepos.Entities.CreateContainer(ctx, gid, EntityCreate{Name:"123", ParentID:root.ID, EntityTypeID:locationType.ID})
	require.NoError(t, err)
	typeInfo, err := tRepos.EntityTypes.Create(ctx, gid, EntityTypeCreate{Name:"PART"})
	require.NoError(t, err)
	exact, err := tRepos.Entities.Create(ctx, gid, EntityCreate{Name:"Exact display ID", ParentID:leaf.ID, EntityTypeID:typeInfo.ID})
	require.NoError(t, err)
	ordinary, err := tRepos.Entities.Create(ctx, gid, EntityCreate{Name:"Ordinary barcode match", Barcode:"PART-SABC-123", EntityTypeID:typeInfo.ID})
	require.NoError(t, err)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, exact.ID); _ = tRepos.Entities.Delete(ctx, ordinary.ID); _ = tRepos.Entities.DeleteContainerByGroup(ctx, gid, leaf.ID); _ = tRepos.Entities.DeleteContainerByGroup(ctx, gid, root.ID) })
	require.Equal(t, "PART-SABC-123", exact.DisplayID)

	firstPage, err := tRepos.Entities.QueryByGroup(ctx, gid, EntityQuery{Page:1, PageSize:1, Search:"PART-SABC-123"})
	require.NoError(t, err)
	secondPage, err := tRepos.Entities.QueryByGroup(ctx, gid, EntityQuery{Page:2, PageSize:1, Search:"PART-SABC-123"})
	require.NoError(t, err)
	require.Equal(t, 2, firstPage.Total)
	require.Equal(t, 2, secondPage.Total)
	require.Len(t, firstPage.Items, 1)
	require.Len(t, secondPage.Items, 1)
	require.ElementsMatch(t, []uuid.UUID{exact.ID, ordinary.ID}, []uuid.UUID{firstPage.Items[0].ID, secondPage.Items[0].ID})
}

func TestSingleEntityReadsCloseCrossBaseCollisionFamilies(t *testing.T) {
	ctx,gid:=context.Background(),tGroup.ID
	locationType:=useContainerEntityType(t)
	makeLocation:=func(name string,parent uuid.UUID) EntityOut { out,err:=tRepos.Entities.CreateContainer(ctx,gid,EntityCreate{Name:name,ParentID:parent,EntityTypeID:locationType.ID}); require.NoError(t,err); return out }
	root:=makeLocation("D",uuid.Nil); middle:=makeLocation("C",root.ID); leaf:=makeLocation("1",middle.ID); deeper:=makeLocation("1",leaf.ID)
	typeInfo,err:=tRepos.EntityTypes.Create(ctx,gid,EntityTypeCreate{Name:"Bin"}); require.NoError(t,err)
	first,err:=tRepos.Entities.Create(ctx,gid,EntityCreate{Name:"First",ParentID:leaf.ID,EntityTypeID:typeInfo.ID}); require.NoError(t,err)
	second,err:=tRepos.Entities.Create(ctx,gid,EntityCreate{Name:"Second",ParentID:leaf.ID,EntityTypeID:typeInfo.ID}); require.NoError(t,err)
	natural,err:=tRepos.Entities.Create(ctx,gid,EntityCreate{Name:"Natural",ParentID:deeper.ID,EntityTypeID:typeInfo.ID}); require.NoError(t,err)
	t.Cleanup(func(){ _=tRepos.Entities.Delete(ctx,first.ID); _=tRepos.Entities.Delete(ctx,second.ID); _=tRepos.Entities.Delete(ctx,natural.ID); _=tRepos.Entities.DeleteContainerByGroup(ctx,gid,deeper.ID); _=tRepos.Entities.DeleteContainerByGroup(ctx,gid,leaf.ID); _=tRepos.Entities.DeleteContainerByGroup(ctx,gid,middle.ID); _=tRepos.Entities.DeleteContainerByGroup(ctx,gid,root.ID) })
	first,err=tRepos.Entities.GetOneByGroup(ctx,gid,first.ID); require.NoError(t,err)
	natural,err=tRepos.Entities.GetOneByGroup(ctx,gid,natural.ID); require.NoError(t,err)
	second,err=tRepos.Entities.GetOneByGroup(ctx,gid,second.ID); require.NoError(t,err)
	require.ElementsMatch(t,[]string{"BIN-D-C-1-1-1","BIN-D-C-1-2","BIN-D-C-1-1-2"},[]string{first.DisplayID,second.DisplayID,natural.DisplayID})
	for _,item:=range []EntityOut{first,second,natural} { result,err:=tRepos.Entities.QueryByGroup(ctx,gid,EntityQuery{Page:-1,PageSize:-1,Search:item.DisplayID}); require.NoError(t,err); require.Len(t,result.Items,1); require.Equal(t,item.ID,result.Items[0].ID) }
}

func TestExactDisplayIDLookupReadsOverlappingSeedFamiliesOnce(t *testing.T) {
	ctx, gid := context.Background(), tGroup.ID
	typeInfo, err := tRepos.EntityTypes.Create(ctx, gid, EntityTypeCreate{Name: "Lookup Test"})
	require.NoError(t, err)
	const base = "LOOKUP-1"
	ids := make([]uuid.UUID, 0, 3)
	create := func(assetID int64, displayIDBase string) uuid.UUID {
		item, err := tClient.Entity.Create().
			SetName("Lookup test item").SetDescription("").
			SetGroupID(gid).SetEntityTypeID(typeInfo.ID).
			SetAssetID(assetID).SetDisplayIDBase(displayIDBase).Save(ctx)
		require.NoError(t, err)
		ids = append(ids, item.ID)
		return item.ID
	}
	create(1, base)
	create(2, base)
	exactID := create(3, base+"-1")
	t.Cleanup(func() {
		for _, id := range ids {
			_ = tRepos.Entities.Delete(ctx, id)
		}
		_ = tRepos.EntityTypes.Delete(ctx, gid, typeInfo.ID)
	})

	queryClient, err := ent.Open("sqlite3", "file:ent?mode=memory&cache=shared&_fk=1&_time_format=sqlite")
	require.NoError(t, err)
	defer queryClient.Close()
	entityQueries := 0
	queryClient.Entity.Intercept(ent.InterceptFunc(func(next ent.Querier) ent.Querier {
		return ent.QuerierFunc(func(ctx context.Context, query ent.Query) (ent.Value, error) {
			if _, ok := query.(*ent.EntityQuery); ok {
				entityQueries++
			}
			return next.Query(ctx, query)
		})
	}))
	originalEntityClient := tClient.Entity
	tClient.Entity = queryClient.Entity
	defer func() { tClient.Entity = originalEntityClient }()

	matchedID, found, err := tRepos.Entities.findDisplayIDSearchMatch(ctx, gid, base+"-1-2")
	require.NoError(t, err)
	require.True(t, found)
	require.Equal(t, exactID, matchedID)
	require.Equal(t, 2, entityQueries, "exact lookup should read the overlapping seed families once, plus the newly discovered closure family")
}
