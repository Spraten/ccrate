package sqlite3

import (
	"context"
	"database/sql"

	"github.com/pressly/goose/v3"
	"github.com/sysadminsmedia/homebox/backend/internal/data/shortcodes"
)

func init() { goose.AddMigrationContext(Up20260513120000, Down20260513120000) }

func Up20260513120000(ctx context.Context, tx *sql.Tx) error {
	return shortcodes.Install(ctx, tx, false)
}

func Down20260513120000(_ context.Context, _ *sql.Tx) error { return nil }
