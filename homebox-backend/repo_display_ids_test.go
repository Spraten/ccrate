package repo

import (
	"context"
	"strconv"
	"testing"

	"github.com/google/uuid"
	"github.com/stretchr/testify/require"
)

func TestFormatDisplayIDUsesTypeAndFullLocationPath(t *testing.T) {
	got := formatDisplayID("Bin", []string{"D", "GC", "C", "1"}, 17, uuid.Nil)
	if got != "BIN-D-GC-C-1-A17" {
		t.Fatalf("formatDisplayID() = %q, want BIN-D-GC-C-1-A17", got)
	}
}

func TestFormatDisplayIDNormalizesWordsAndPunctuation(t *testing.T) {
	got := formatDisplayID("Hand Tools", []string{"Garage / Cabinet", "Drawer #2"}, 17, uuid.Nil)
	if got != "HAND-TOOLS-GARAGE-CABINET-DRAWER-2-A17" {
		t.Fatalf("formatDisplayID() = %q", got)
	}
}

func TestFormatDisplayIDMarksUnassignedLocation(t *testing.T) {
	got := formatDisplayID("Tool", nil, 24, uuid.Nil)
	if got != "TOOL-UNLOCATED-A24" {
		t.Fatalf("formatDisplayID() = %q, want TOOL-UNLOCATED-A24", got)
	}
}

func TestFormatDisplayIDUsesUUIDSuffixWhenNativeAssetIDIsUnassigned(t *testing.T) {
	id := uuid.MustParse("812ab7d2-5040-4b2b-9182-60f5ec674efe")
	got := formatDisplayID("Tool", []string{"Drawer"}, 0, id)
	if got != "TOOL-DRAWER-U812AB7D2" {
		t.Fatalf("formatDisplayID() = %q, want TOOL-DRAWER-U812AB7D2", got)
	}
}

func TestIsDisplayIDSearchTreatsTrailingLocationNumberAsPath(t *testing.T) {
	for _, value := range []string{"BIN-D-GC-C-1", "bin-d-gc-c-1"} {
		if !isDisplayIDSearch(value) {
			t.Errorf("isDisplayIDSearch(%q) = false, want true", value)
		}
	}
	for _, value := range []string{"123456", "A drawer", "BIN--1", "-BIN-D-C", "BIN-D-C-"} {
		if isDisplayIDSearch(value) {
			t.Errorf("isDisplayIDSearch(%q) = true, want false", value)
		}
	}
}

func TestEntityDisplayIDChangesWithTypeAndLocationButKeepsNativeIDs(t *testing.T) {
	ctx := context.Background()
	groupID := tGroup.ID
	locationType := useContainerEntityType(t)
	makeLocation := func(name string, parent uuid.UUID) EntityOut {
		out, err := tRepos.Entities.Create(ctx, groupID, EntityCreate{
			Name: name, ParentID: parent, EntityTypeID: locationType.ID,
		})
		require.NoError(t, err)
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
	assetID++
	require.NoError(t, tRepos.Entities.SetAssetID(ctx, groupID, item.ID, assetID))
	item, err = tRepos.Entities.GetOneByGroup(ctx, groupID, item.ID)
	require.NoError(t, err)
	require.Equal(t, formatDisplayID("Bin", []string{"D", "GC", "C", "1"}, assetID, item.ID), item.DisplayID)
	originalUUID, originalAssetID, originalShortCode := item.ID, item.AssetID, item.ShortCode
	require.NotEqual(t, AssetID(1), originalAssetID, "the terminal 1 is the storage path segment, not the native asset ID")
	require.NotEmpty(t, originalShortCode)
	require.Contains(t, item.DisplayID, "-A"+strconv.FormatInt(int64(originalAssetID), 10))

	duplicateRoot := makeLocation("D", uuid.Nil)
	duplicateMid := makeLocation("GC", duplicateRoot.ID)
	duplicateColumn := makeLocation("C", duplicateMid.ID)
	duplicateSlot := makeLocation("1", duplicateColumn.ID)
	duplicateItem, err := tRepos.Entities.Create(ctx, groupID, EntityCreate{
		Name: "Heat shrink duplicate path", ParentID: duplicateSlot.ID, EntityTypeID: binType.ID,
	})
	require.NoError(t, err)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, duplicateItem.ID) })
	duplicateAssetID := assetID + 1
	require.NoError(t, tRepos.Entities.SetAssetID(ctx, groupID, duplicateItem.ID, duplicateAssetID))
	duplicateItem, err = tRepos.Entities.GetOneByGroup(ctx, groupID, duplicateItem.ID)
	require.NoError(t, err)
	require.NotEqual(t, item.DisplayID, duplicateItem.DisplayID)
	for _, candidate := range []EntityOut{item, duplicateItem} {
		search, err := tRepos.Entities.QueryByGroup(ctx, groupID, EntityQuery{
			Page: -1, PageSize: -1, Search: candidate.DisplayID,
		})
		require.NoError(t, err)
		require.Len(t, search.Items, 1)
		require.Equal(t, candidate.ID, search.Items[0].ID)
	}

	updated, err := tRepos.Entities.UpdateByGroup(ctx, groupID, EntityUpdate{
		ID: item.ID, Name: item.Name, ParentID: other.ID, EntityTypeID: drawerType.ID,
		AssetID: item.AssetID, ModelNumber: item.ModelNumber, Manufacturer: item.Manufacturer,
		Description: item.Description, Quantity: item.Quantity, Insured: item.Insured,
		Archived: item.Archived, SerialNumber: item.SerialNumber, Barcode: &item.Barcode,
	})
	require.NoError(t, err)
	require.Equal(t, formatDisplayID("Drawer", []string{"E"}, assetID, item.ID), updated.DisplayID)
	require.NotEqual(t, item.DisplayID, updated.DisplayID)
	require.Equal(t, originalUUID, updated.ID)
	require.Equal(t, originalAssetID, updated.AssetID)
	require.Equal(t, originalShortCode, updated.ShortCode)

	search, err := tRepos.Entities.QueryByGroup(ctx, groupID, EntityQuery{
		Page: -1, PageSize: -1, Search: updated.DisplayID,
	})
	require.NoError(t, err)
	require.Len(t, search.Items, 1)
	require.Equal(t, updated.ID, search.Items[0].ID)
	require.Equal(t, updated.DisplayID, search.Items[0].DisplayID)
}
