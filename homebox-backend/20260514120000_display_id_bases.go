package sqlite3

import (
	"context"
	"database/sql"

	"github.com/pressly/goose/v3"
	"github.com/sysadminsmedia/homebox/backend/internal/data/displayids"
)

func init() { goose.AddMigrationContext(Up20260514120000, Down20260514120000) }
func Up20260514120000(ctx context.Context, tx *sql.Tx) error { return displayids.Install(ctx, tx, false) }
func Down20260514120000(_ context.Context, _ *sql.Tx) error { return nil }
