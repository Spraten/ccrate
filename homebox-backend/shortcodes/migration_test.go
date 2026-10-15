package shortcodes_test

import (
	"context"
	"database/sql"
	"path/filepath"
	"testing"

	"entgo.io/ent/dialect"
	entsql "entgo.io/ent/dialect/sql"
	"github.com/google/uuid"
	"github.com/pressly/goose/v3"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent"
	"github.com/sysadminsmedia/homebox/backend/internal/data/migrations"
	_ "github.com/sysadminsmedia/homebox/backend/internal/data/migrations/sqlite3"
	_ "github.com/sysadminsmedia/homebox/backend/pkgs/cgofreesqlite"
)

func TestGooseBackfillsOldItemsAndKeepsCodesAfterReopen(t *testing.T) {
	ctx := context.Background()
	path := filepath.Join(t.TempDir(), "old-homebox.db")
	db, err := sql.Open("sqlite3", path)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	gooseFS, err := migrations.Migrations("sqlite3")
	if err != nil {
		t.Fatal(err)
	}
	goose.SetBaseFS(gooseFS)
	if err := goose.SetDialect("sqlite3"); err != nil {
		t.Fatal(err)
	}
	if err := goose.UpToContext(ctx, db, "sqlite3", 20260512130000); err != nil {
		t.Fatalf("create old Homebox schema: %v", err)
	}
	client := ent.NewClient(ent.Driver(entsql.OpenDB(dialect.SQLite, db)))
	collection, err := client.Group.Create().SetName("Old collection").Save(ctx)
	if err != nil {
		t.Fatal(err)
	}
	itemType, err := client.EntityType.Create().SetName("Item").SetDescription("").SetIsLocation(false).SetGroupID(collection.ID).Save(ctx)
	if err != nil {
		t.Fatal(err)
	}
	locationType, err := client.EntityType.Create().SetName("Location").SetDescription("").SetIsLocation(true).SetGroupID(collection.ID).Save(ctx)
	if err != nil {
		t.Fatal(err)
	}
	items := []struct {
		id, name string
		asset    int64
		archived bool
		typeID   uuid.UUID
	}{
		{"00000000-0000-4000-8000-000000000001", "Old item", 41, false, itemType.ID},
		{"00000000-0000-4000-8000-000000000002", "Archived item", 42, true, itemType.ID},
		{"00000000-0000-4000-8000-000000000003", "Shelf", 43, false, locationType.ID},
	}
	for _, row := range items {
		_, err := client.Entity.Create().SetID(uuid.MustParse(row.id)).SetName(row.name).SetDescription("").SetGroupID(collection.ID).
			SetEntityTypeID(row.typeID).SetModelNumber("M-18").SetAssetID(row.asset).SetArchived(row.archived).Save(ctx)
		if err != nil {
			t.Fatal(err)
		}
	}
	if err := client.Close(); err != nil {
		t.Fatal(err)
	}
	db, err = sql.Open("sqlite3", path)
	if err != nil {
		t.Fatal(err)
	}
	if err := goose.UpContext(ctx, db, "sqlite3"); err != nil {
		t.Fatalf("apply registered short-code migration: %v", err)
	}

	assertCode := func(id, want string) {
		t.Helper()
		var got string
		if err := db.QueryRowContext(ctx, "SELECT short_code FROM entities WHERE id=?", id).Scan(&got); err != nil {
			t.Fatal(err)
		}
		if got != want {
			t.Fatalf("%s code = %q, want %q", id, got, want)
		}
	}
	assertCode(items[0].id, "M18-001")
	assertCode(items[1].id, "M18-002")
	var locationCode sql.NullString
	if err := db.QueryRowContext(ctx, "SELECT short_code FROM entities WHERE id=?", items[2].id).Scan(&locationCode); err != nil {
		t.Fatal(err)
	}
	if locationCode.Valid {
		t.Fatalf("location received short code %q", locationCode.String)
	}
	var assetID int
	if err := db.QueryRowContext(ctx, "SELECT asset_id FROM entities WHERE id=?", items[0].id).Scan(&assetID); err != nil {
		t.Fatal(err)
	}
	if assetID != 41 {
		t.Fatalf("migration changed native asset ID to %d", assetID)
	}

	if err := db.Close(); err != nil {
		t.Fatal(err)
	}
	db, err = sql.Open("sqlite3", path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	assertCode(items[0].id, "M18-001")
	if _, err := db.Exec("INSERT INTO entities(id,group_entities,entity_type_entities,model_number,name,short_code) VALUES (?,?,?,?,?,?)", uuid.New(), collection.ID, itemType.ID, "M-18", "Duplicate", "m18-001"); err == nil {
		t.Fatal("case-folded duplicate short code was accepted")
	}
}

func TestGooseBackfillSeedsExistingCodesAndDurableCountersBeforeAllocating(t *testing.T) {
	ctx := context.Background()
	path := filepath.Join(t.TempDir(), "partially-numbered-homebox.db")
	db, err := sql.Open("sqlite3", path)
	if err != nil { t.Fatal(err) }
	gooseFS, err := migrations.Migrations("sqlite3")
	if err != nil { t.Fatal(err) }
	goose.SetBaseFS(gooseFS)
	if err := goose.SetDialect("sqlite3"); err != nil { t.Fatal(err) }
	if err := goose.UpToContext(ctx, db, "sqlite3", 20260512130000); err != nil {
		t.Fatalf("create old Homebox schema: %v", err)
	}
	client := ent.NewClient(ent.Driver(entsql.OpenDB(dialect.SQLite, db)))
	collection, err := client.Group.Create().SetName("Partial collection").Save(ctx)
	if err != nil { t.Fatal(err) }
	itemType, err := client.EntityType.Create().SetName("Item").SetDescription("").SetIsLocation(false).SetGroupID(collection.ID).Save(ctx)
	if err != nil { t.Fatal(err) }
	items := []struct{ id, name, model string }{
		{"00000000-0000-4000-8000-000000000001", "Missing earlier row", "M-18"},
		{"00000000-0000-4000-8000-000000000002", "Existing row", "M-18"},
		{"00000000-0000-4000-8000-000000000003", "Deleted high sequence", "HIGH"},
	}
	for _, row := range items {
		_, err := client.Entity.Create().SetID(uuid.MustParse(row.id)).SetName(row.name).SetDescription("").SetGroupID(collection.ID).
			SetEntityTypeID(itemType.ID).SetModelNumber(row.model).Save(ctx)
		if err != nil { t.Fatal(err) }
	}
	if err := client.Close(); err != nil { t.Fatal(err) }
	db, err = sql.Open("sqlite3", path)
	if err != nil { t.Fatal(err) }
	if _, err := db.ExecContext(ctx, `ALTER TABLE entities ADD COLUMN short_code text NULL`); err != nil { t.Fatal(err) }
	if _, err := db.ExecContext(ctx, `CREATE TABLE item_shortcode_counters (
		group_id uuid NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
		prefix varchar(3) NOT NULL,
		next_number integer NOT NULL CHECK(next_number > 0),
		PRIMARY KEY(group_id,prefix))`); err != nil { t.Fatal(err) }
	if _, err := db.ExecContext(ctx, `UPDATE entities SET short_code='M18-001' WHERE id=?`, items[1].id); err != nil { t.Fatal(err) }
	if _, err := db.ExecContext(ctx, `INSERT INTO item_shortcode_counters(group_id,prefix,next_number) VALUES(?,?,?)`, collection.ID, "M18", 3); err != nil { t.Fatal(err) }
	if _, err := db.ExecContext(ctx, `INSERT INTO item_shortcode_counters(group_id,prefix,next_number) VALUES(?,?,?)`, collection.ID, "HIG", 1001); err != nil { t.Fatal(err) }
	if err := goose.UpContext(ctx, db, "sqlite3"); err != nil {
		t.Fatalf("apply registered short-code migration: %v", err)
	}
	for _, expected := range []struct{ id, code string }{
		{items[0].id, "M18-003"},
		{items[1].id, "M18-001"},
		{items[2].id, "HIG-1001"},
	} {
		var got string
		if err := db.QueryRowContext(ctx, `SELECT short_code FROM entities WHERE id=?`, expected.id).Scan(&got); err != nil { t.Fatal(err) }
		if got != expected.code { t.Errorf("%s code = %q, want %q", expected.id, got, expected.code) }
	}
	if err := db.Close(); err != nil { t.Fatal(err) }
}
