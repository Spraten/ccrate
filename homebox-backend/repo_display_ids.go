package repo

import (
	"context"
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"github.com/google/uuid"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/entity"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/group"
)

var displayIDSeparators = regexp.MustCompile(`[^A-Z0-9]+`)

// displayIDSegment converts a type or location name into a readable identifier
// segment while preserving word boundaries and removing punctuation.
func displayIDSegment(value string) string {
	value = strings.ToUpper(strings.TrimSpace(value))
	value = displayIDSeparators.ReplaceAllString(value, "-")
	return strings.Trim(value, "-")
}

func formatDisplayID(typeName string, locationPath []string, assetID AssetID, entityID uuid.UUID) string {
	segments := make([]string, 0, len(locationPath)+2)
	if name := displayIDSegment(typeName); name != "" {
		segments = append(segments, name)
	}
	for _, part := range locationPath {
		if name := displayIDSegment(part); name != "" {
			segments = append(segments, name)
		}
	}
	if len(locationPath) == 0 {
		segments = append(segments, "UNLOCATED")
	}
	// Keep the native identifier separate from the readable type/location path.
	// The A marker makes it clear that this trailing number is the item's native
	// AssetID, not another storage location segment.
	if assetID > 0 {
		segments = append(segments, "A"+strconv.FormatInt(int64(assetID), 10))
	} else {
		compactUUID := strings.ReplaceAll(entityID.String(), "-", "")
		segments = append(segments, "U"+compactUUID[:8])
	}
	return strings.Join(segments, "-")
}

func isDisplayIDSearch(value string) bool {
	value = strings.ToUpper(strings.TrimSpace(value))
	if strings.Count(value, "-") < 2 || value == "" || strings.HasPrefix(value, "-") || strings.HasSuffix(value, "-") {
		return false
	}
	for _, r := range value {
		if !(r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || r == '-') {
			return false
		}
	}
	for _, segment := range strings.Split(value, "-") {
		if segment == "" {
			return false
		}
	}
	return true
}

// populateDisplayIDs fills the derived display ID using the complete current
// parent chain. Ancestor reads are batched once per depth and always scoped to
// the requesting group; no generated ID is persisted or used as native identity.
func (r *EntityRepository) populateDisplayIDs(ctx context.Context, gid uuid.UUID, items []EntitySummary) error {
	if len(items) == 0 {
		return nil
	}
	ancestors := make(map[uuid.UUID]EntitySummary)
	frontier := make(map[uuid.UUID]struct{})
	for _, item := range items {
		if item.Parent != nil {
			frontier[item.Parent.ID] = struct{}{}
		}
	}
	for len(frontier) > 0 {
		ids := make([]uuid.UUID, 0, len(frontier))
		for id := range frontier {
			if _, loaded := ancestors[id]; !loaded {
				ids = append(ids, id)
			}
		}
		if len(ids) == 0 {
			break
		}
		parents, err := r.db.Entity.Query().
			Where(entity.IDIn(ids...), entity.HasGroupWith(group.ID(gid))).
			WithParent().WithEntityType().All(ctx)
		if err != nil {
			return fmt.Errorf("load display ID location path: %w", err)
		}
		frontier = make(map[uuid.UUID]struct{})
		for _, parent := range parents {
			ancestors[parent.ID] = mapEntitySummary(parent)
			if parent.Edges.Parent != nil {
				frontier[parent.Edges.Parent.ID] = struct{}{}
			}
		}
	}

	var attach func(*EntitySummary, map[uuid.UUID]bool)
	attach = func(item *EntitySummary, visited map[uuid.UUID]bool) {
		if item == nil || item.Parent == nil || visited[item.ID] {
			return
		}
		visited[item.ID] = true
		if full, ok := ancestors[item.Parent.ID]; ok {
			parent := full
			item.Parent = &parent
			attach(item.Parent, visited)
		}
	}

	for i := range items {
		attach(&items[i], make(map[uuid.UUID]bool))
		path := make([]string, 0, 4)
		visited := make(map[uuid.UUID]bool)
		for parent := items[i].Parent; parent != nil && !visited[parent.ID]; parent = parent.Parent {
			visited[parent.ID] = true
			path = append(path, parent.Name)
		}
		for left, right := 0, len(path)-1; left < right; left, right = left+1, right-1 {
			path[left], path[right] = path[right], path[left]
		}
		typeName := ""
		if items[i].EntityType != nil {
			typeName = items[i].EntityType.Name
		}
		items[i].DisplayID = formatDisplayID(typeName, path, items[i].AssetID, items[i].ID)
	}
	return nil
}
