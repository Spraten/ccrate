package repo

import (
	"context"
	"fmt"
	"sync"
	"testing"

	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/entityfield"
	"github.com/stretchr/testify/require"
)

func TestItemShortCodesAreScopedStableAndFreshForDuplicates(t *testing.T) {
	ctx := context.Background()
	itemType := useItemEntityType(t)
	first, err := tRepos.Entities.Create(ctx, tGroup.ID, EntityCreate{Name: "M18 Drill", ModelNumber: "m-18", EntityTypeID: itemType.ID})
	require.NoError(t, err)
	require.Equal(t, "M18-001", first.ShortCode)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, first.ID) })

	duplicate, err := tRepos.Entities.Duplicate(ctx, tGroup.ID, first.ID, DuplicateOptions{})
	require.NoError(t, err)
	require.Equal(t, "M18-002", duplicate.ShortCode)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, duplicate.ID) })

	updated, err := tRepos.Entities.UpdateByGroup(ctx, tGroup.ID, EntityUpdate{
		ID: first.ID, Name: "Renamed drill", ModelNumber: "NEW-MODEL", EntityTypeID: itemType.ID,
	})
	require.NoError(t, err)
	require.Equal(t, "M18-001", updated.ShortCode)

	require.NoError(t, tRepos.Entities.Delete(ctx, first.ID))
	next, err := tRepos.Entities.Create(ctx, tGroup.ID, EntityCreate{Name: "Another M18 drill", ModelNumber: "M18", EntityTypeID: itemType.ID})
	require.NoError(t, err)
	require.Equal(t, "M18-003", next.ShortCode)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, next.ID) })
}

func TestItemShortCodeSurvivesEntityTypeTransitions(t *testing.T) {
	ctx := context.Background()
	locationType := useContainerEntityType(t)
	itemType := useItemEntityType(t)
	location, err := tRepos.Entities.Create(ctx, tGroup.ID, EntityCreate{
		Name: "Shelf A", EntityTypeID: locationType.ID,
	})
	require.NoError(t, err)
	require.Empty(t, location.ShortCode)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, location.ID) })

	item, err := tRepos.Entities.UpdateByGroup(ctx, tGroup.ID, EntityUpdate{
		ID: location.ID, Name: location.Name, EntityTypeID: itemType.ID,
	})
	require.NoError(t, err)
	require.Equal(t, "SHE-001", item.ShortCode)

	asLocation, err := tRepos.Entities.UpdateByGroup(ctx, tGroup.ID, EntityUpdate{
		ID: item.ID, Name: item.Name, EntityTypeID: locationType.ID,
	})
	require.NoError(t, err)
	require.Equal(t, item.ShortCode, asLocation.ShortCode)

	asItem, err := tRepos.Entities.UpdateByGroup(ctx, tGroup.ID, EntityUpdate{
		ID: item.ID, Name: item.Name, EntityTypeID: itemType.ID,
	})
	require.NoError(t, err)
	require.Equal(t, item.ShortCode, asItem.ShortCode)
}

func TestPatchToItemAllocatesShortCodeFromPersistedModelAndName(t *testing.T) {
	ctx := context.Background()
	locationType := useContainerEntityType(t)
	itemType := useItemEntityType(t)
	location, err := tRepos.Entities.Create(ctx, tGroup.ID, EntityCreate{
		Name: "Impact Driver", ModelNumber: "P2I-18", EntityTypeID: locationType.ID,
	})
	require.NoError(t, err)
	require.Empty(t, location.ShortCode)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, location.ID) })

	err = tRepos.Entities.Patch(ctx, tGroup.ID, location.ID, EntityPatch{EntityTypeID: itemType.ID})
	require.NoError(t, err)
	item, err := tRepos.Entities.GetOneByGroup(ctx, tGroup.ID, location.ID)
	require.NoError(t, err)
	require.Equal(t, "P2I-001", item.ShortCode)
}

func TestItemShortCodeCounterRollsBackWithCreateTransaction(t *testing.T) {
	ctx := context.Background()
	tx, err := tClient.Tx(ctx)
	require.NoError(t, err)
	code, err := allocateShortCode(ctx, tx, tGroup.ID, "ROLLBACK", "Widget")
	require.NoError(t, err)
	require.Equal(t, "ROL-001", code)
	require.NoError(t, tx.Rollback())

	itemType := useItemEntityType(t)
	item, err := tRepos.Entities.Create(ctx, tGroup.ID, EntityCreate{Name: "Widget", ModelNumber: "ROLLBACK", EntityTypeID: itemType.ID})
	require.NoError(t, err)
	require.Equal(t, "ROL-001", item.ShortCode)
	t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, item.ID) })
}

func TestConcurrentItemShortCodeAllocationDoesNotCollide(t *testing.T) {
	const count = 12
	ctx := context.Background()
	itemType := useItemEntityType(t)
	results := make(chan EntityOut, count)
	errors := make(chan error, count)
	var workers sync.WaitGroup
	for i := 0; i < count; i++ {
		workers.Add(1)
		go func(i int) {
			defer workers.Done()
			item, err := tRepos.Entities.Create(ctx, tGroup.ID, EntityCreate{
				Name: fmt.Sprintf("Concurrent %d", i), ModelNumber: "CC1", EntityTypeID: itemType.ID,
			})
			if err != nil {
				errors <- err
				return
			}
			results <- item
		}(i)
	}
	workers.Wait()
	close(results)
	close(errors)
	for err := range errors {
		require.NoError(t, err)
	}
	codes := make(map[string]bool, count)
	for item := range results {
		require.True(t, len(item.ShortCode) >= 7)
		require.Equal(t, "CC1-", item.ShortCode[:4])
		require.False(t, codes[item.ShortCode], "duplicate code %s", item.ShortCode)
		codes[item.ShortCode] = true
		t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, item.ID) })
	}
	require.Len(t, codes, count)
}

func TestItemShortCodeCounterExpandsPastThreeDigits(t *testing.T) {
	ctx := context.Background()
	_, err := tClient.Sql().ExecContext(ctx,
		"INSERT INTO item_shortcode_counters(group_id,prefix,next_number) VALUES(?,?,1000)", tGroup.ID, "THR")
	require.NoError(t, err)
	tx, err := tClient.Tx(ctx)
	require.NoError(t, err)
	code, err := allocateShortCode(ctx, tx, tGroup.ID, "THR", "Widget")
	require.NoError(t, err)
	require.NoError(t, tx.Commit())
	require.Equal(t, "THR-1000", code)
}

func TestGetByShortCodeDetectsPaddedSerialCollision(t *testing.T) {
	ctx := context.Background()
	itemType := useItemEntityType(t)
	owner, err := tRepos.Entities.Create(ctx, tGroup.ID, EntityCreate{Name: "Code owner", ModelNumber: "COL", EntityTypeID: itemType.ID})
	require.NoError(t, err)
	other, err := tRepos.Entities.Create(ctx, tGroup.ID, EntityCreate{Name: "Serial collision", ModelNumber: "OTH", EntityTypeID: itemType.ID})
	require.NoError(t, err)
	for _, item := range []EntityOut{owner, other} {
		t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, item.ID) })
	}
	require.NoError(t, tClient.Entity.UpdateOneID(other.ID).SetSerialNumber("X" + owner.ShortCode + "X").Exec(ctx))
	resolved, err := tRepos.Entities.GetByShortCode(ctx, tGroup.ID, owner.ShortCode)
	require.NoError(t, err)
	require.Equal(t, owner.ID, resolved.ID, "substring-only serial is not a collision")
	require.NoError(t, tClient.Entity.UpdateOneID(other.ID).SetSerialNumber("  " + owner.ShortCode + "  ").Exec(ctx))

	_, err = tRepos.Entities.GetByShortCode(ctx, tGroup.ID, owner.ShortCode)
	require.ErrorContains(t, err, "short code is ambiguous")
}

func TestGetByShortCodeDetectsPaddedManufacturerQRCodeCollision(t *testing.T) {
	ctx := context.Background()
	itemType := useItemEntityType(t)
	owner, err := tRepos.Entities.Create(ctx, tGroup.ID, EntityCreate{Name: "Code owner", ModelNumber: "COL", EntityTypeID: itemType.ID})
	require.NoError(t, err)
	other, err := tRepos.Entities.Create(ctx, tGroup.ID, EntityCreate{Name: "QR collision", ModelNumber: "OTH", EntityTypeID: itemType.ID})
	require.NoError(t, err)
	for _, item := range []EntityOut{owner, other} {
		t.Cleanup(func() { _ = tRepos.Entities.Delete(ctx, item.ID) })
	}
	_, err = tClient.EntityField.Create().SetEntityID(other.ID).SetName("Manufacturer QR code").
		SetType(entityfield.Type("text")).SetTextValue("  " + owner.ShortCode + "  ").Save(ctx)
	require.NoError(t, err)

	_, err = tRepos.Entities.GetByShortCode(ctx, tGroup.ID, owner.ShortCode)
	require.ErrorContains(t, err, "short code is ambiguous")
}
