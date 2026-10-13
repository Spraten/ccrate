package postgres

import (
	"context"
	"database/sql"

	"github.com/pressly/goose/v3"
	"github.com/sysadminsmedia/homebox/backend/internal/data/shortcodes"
)

func init() { goose.AddMigrationContext(Up20260513120001, Down20260513120001) }

func Up20260513120001(ctx context.Context, tx *sql.Tx) error {
	return shortcodes.Install(ctx, tx, true)
}

func Down20260513120001(_ context.Context, _ *sql.Tx) error { return nil }
