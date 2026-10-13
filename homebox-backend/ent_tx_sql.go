package ent

import (
	"context"
	"database/sql"

	entsql "entgo.io/ent/dialect/sql"
)

// Dialect exposes the underlying transaction dialect to native repository helpers.
func (tx *Tx) Dialect() string { return tx.config.driver.Dialect() }

// QueryRowContext scans one row returned from the current transaction.
func (tx *Tx) QueryRowContext(ctx context.Context, query string, args []any, dest ...any) error {
	rows := &entsql.Rows{}
	if err := tx.config.driver.Query(ctx, query, args, rows); err != nil {
		return err
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return err
		}
		return sql.ErrNoRows
	}
	return rows.Scan(dest...)
}
