package postgres

import (
	"context"
	"database/sql"

	"github.com/pressly/goose/v3"
	"github.com/sysadminsmedia/homebox/backend/internal/data/displayids"
)

func init() { goose.AddMigrationContext(Up20260514120001, Down20260514120001) }
func Up20260514120001(ctx context.Context, tx *sql.Tx) error { return displayids.Install(ctx, tx, true) }
func Down20260514120001(_ context.Context, _ *sql.Tx) error { return nil }
