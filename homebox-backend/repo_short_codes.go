package repo

import (
	"context"
	"fmt"
	"strings"

	"entgo.io/ent/dialect"
	"github.com/google/uuid"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/entity"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/entityfield"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/entitytype"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/group"
	"github.com/sysadminsmedia/homebox/backend/internal/data/shortcodes"
	"github.com/sysadminsmedia/homebox/backend/internal/sys/validate"
)

func allocateShortCode(ctx context.Context, tx *ent.Tx, gid uuid.UUID, modelNumber, name string) (string, error) {
	prefix := shortcodes.Prefix(modelNumber, name)
	query := `INSERT INTO item_shortcode_counters (group_id, prefix, next_number) VALUES (?, ?, 2)
		ON CONFLICT (group_id, prefix) DO UPDATE SET next_number = item_shortcode_counters.next_number + 1
		RETURNING next_number - 1`
	if tx.Dialect() == dialect.Postgres {
		query = `INSERT INTO item_shortcode_counters (group_id, prefix, next_number) VALUES ($1, $2, 2)
			ON CONFLICT (group_id, prefix) DO UPDATE SET next_number = item_shortcode_counters.next_number + 1
			RETURNING next_number - 1`
	}
	var number int64
	if err := tx.QueryRowContext(ctx, query, []any{gid, prefix}, &number); err != nil {
		return "", err
	}
	return fmt.Sprintf("%s-%03d", prefix, number), nil
}

// GetByShortCode resolves only active items in the caller's collection.
func (r *EntityRepository) GetByShortCode(ctx context.Context, gid uuid.UUID, code string) (EntityOut, error) {
	code = strings.ToUpper(strings.TrimSpace(code))
	if len(code) < 7 || code[3] != '-' {
		return EntityOut{}, validate.NewRequestError(fmt.Errorf("invalid short code"), 400)
	}
	for i, c := range code {
		if i == 3 {
			continue
		}
		if i < 3 && !(c >= 'A' && c <= 'Z' || c >= '0' && c <= '9') || i > 3 && !(c >= '0' && c <= '9') {
			return EntityOut{}, validate.NewRequestError(fmt.Errorf("invalid short code"), 400)
		}
	}
	items, err := r.db.Entity.Query().Where(
		entity.HasGroupWith(group.ID(gid)),
		entity.Archived(false),
		entity.HasEntityTypeWith(entitytype.IsLocation(false)),
		entity.Or(
			entity.ShortCodeEqualFold(code),
			entity.SerialNumberEqualFold(code),
			entity.HasFieldsWith(entityfield.And(entityfield.Name("Manufacturer QR code"), entityfield.TextValueEqualFold(code))),
		),
	).WithFields().All(ctx)
	if err != nil {
		return EntityOut{}, err
	}
	owners := make(map[uuid.UUID]*ent.Entity)
	for _, candidate := range items {
		shortCodeMatch := candidate.ShortCode != nil && strings.EqualFold(*candidate.ShortCode, code)
		metadataMatch := strings.EqualFold(candidate.SerialNumber, code)
		for _, field := range candidate.Edges.Fields {
			if field.Name == "Manufacturer QR code" && strings.EqualFold(field.TextValue, code) {
				metadataMatch = true
			}
		}
		if shortCodeMatch || metadataMatch {
			owners[candidate.ID] = candidate
		}
	}
	if len(owners) == 0 {
		return EntityOut{}, validate.NewRequestError(fmt.Errorf("short code not found"), 404)
	}
	if len(owners) > 1 {
		return EntityOut{}, validate.NewRequestError(fmt.Errorf("short code is ambiguous"), 409)
	}
	var item *ent.Entity
	for _, candidate := range owners {
		item = candidate
	}
	return r.GetOneByGroup(ctx, gid, item.ID)
}
