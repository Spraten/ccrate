package shortcodes

import (
	"context"
	"database/sql"
	"fmt"
	"strconv"
	"strings"
)

func Install(ctx context.Context, tx *sql.Tx, postgres bool) error {
	var columns string
	if postgres {
		columns = `SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'entities' AND column_name = 'short_code'`
	} else {
		columns = `SELECT COUNT(*) FROM pragma_table_info('entities') WHERE name = 'short_code'`
	}
	var present int
	if err := tx.QueryRowContext(ctx, columns).Scan(&present); err != nil {
		return err
	}
	if present == 0 {
		if _, err := tx.ExecContext(ctx, `ALTER TABLE entities ADD COLUMN short_code text NULL`); err != nil {
			return fmt.Errorf("add short_code column: %w", err)
		}
	}
	var create, index string
	if postgres {
		create = `CREATE TABLE IF NOT EXISTS item_shortcode_counters (
			group_id uuid NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
			prefix varchar(3) NOT NULL,
			next_number bigint NOT NULL CHECK (next_number > 0),
			PRIMARY KEY (group_id, prefix))`
		index = `CREATE UNIQUE INDEX IF NOT EXISTS entity_short_code_group_unique ON entities(group_entities, lower(short_code)) WHERE short_code IS NOT NULL`
	} else {
		create = `CREATE TABLE IF NOT EXISTS item_shortcode_counters (
			group_id uuid NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
			prefix varchar(3) NOT NULL,
			next_number integer NOT NULL CHECK (next_number > 0),
			PRIMARY KEY (group_id, prefix))`
		index = `CREATE UNIQUE INDEX IF NOT EXISTS entity_short_code_group_unique ON entities(group_entities, short_code COLLATE NOCASE) WHERE short_code IS NOT NULL`
	}
	if _, err := tx.ExecContext(ctx, create); err != nil {
		return fmt.Errorf("create short code counters: %w", err)
	}
	if _, err := tx.ExecContext(ctx, index); err != nil {
		return fmt.Errorf("create short code unique index: %w", err)
	}
	rows, err := tx.QueryContext(ctx, `SELECT e.id, e.group_entities, e.model_number, e.name, e.short_code
		FROM entities e LEFT JOIN entity_types t ON t.id = e.entity_type_entities
		WHERE COALESCE(t.is_location, false) = false ORDER BY e.group_entities, e.id`)
	if err != nil {
		return fmt.Errorf("read items for short code backfill: %w", err)
	}
	type key struct{ group, prefix string }
	counts := map[key]int64{}
	type record struct{ id, group, model, name, code string }
	var records []record
	for rows.Next() {
		var row record
		var model, code sql.NullString
		if err := rows.Scan(&row.id, &row.group, &model, &row.name, &code); err != nil {
			rows.Close()
			return fmt.Errorf("read item for short code backfill: %w", err)
		}
		row.model = model.String
		row.code = code.String
		records = append(records, row)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return fmt.Errorf("read items for short code backfill: %w", err)
	}
	if err := rows.Close(); err != nil {
		return err
	}
	for _, row := range records {
		code := row.code
		prefix := Prefix(row.model, row.name)
		if code == "" {
			k := key{row.group, prefix}
			counts[k]++
			code = fmt.Sprintf("%s-%03d", prefix, counts[k])
			update := `UPDATE entities SET short_code = ? WHERE id = ? AND short_code IS NULL`
			if postgres {
				update = `UPDATE entities SET short_code = $1 WHERE id = $2 AND short_code IS NULL`
			}
			if _, err := tx.ExecContext(ctx, update, code, row.id); err != nil {
				return fmt.Errorf("assign short code for %s: %w", row.id, err)
			}
			continue
		}
		parts := strings.SplitN(code, "-", 2)
		if len(parts) == 2 && len(parts[0]) == 3 {
			if number, err := strconv.ParseInt(parts[1], 10, 64); err == nil && number > counts[key{row.group, parts[0]}] {
				counts[key{row.group, parts[0]}] = number
			}
		}
	}
	for k, number := range counts {
		if postgres {
			_, err = tx.ExecContext(ctx, `INSERT INTO item_shortcode_counters(group_id, prefix, next_number) VALUES ($1,$2,$3) ON CONFLICT (group_id,prefix) DO UPDATE SET next_number = GREATEST(item_shortcode_counters.next_number, EXCLUDED.next_number)`, k.group, k.prefix, number+1)
		} else {
			_, err = tx.ExecContext(ctx, `INSERT INTO item_shortcode_counters(group_id, prefix, next_number) VALUES (?,?,?) ON CONFLICT (group_id,prefix) DO UPDATE SET next_number = MAX(item_shortcode_counters.next_number, excluded.next_number)`, k.group, k.prefix, number+1)
		}
		if err != nil {
			return fmt.Errorf("seed short code counter for %s: %w", k.prefix, err)
		}
	}
	return nil
}
