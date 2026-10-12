package repo

import (
    "context"
    "fmt"
    "net/http"
    "sort"
    "strings"
    "sync"

    "github.com/google/uuid"
    "github.com/sysadminsmedia/homebox/backend/internal/data/ent/entity"
    "github.com/sysadminsmedia/homebox/backend/internal/data/ent/group"
    "github.com/sysadminsmedia/homebox/backend/internal/sys/validate"
)

// ponytail: one hierarchy writer prevents concurrent A->B / B->A cycles.
// Use per-group locks if write contention becomes material.
var hierarchyWriteMu sync.Mutex

func hierarchyError(message string) error {
    return validate.NewRequestError(fmt.Errorf("%s", message), http.StatusBadRequest)
}

func (r *EntityRepository) validateHierarchyParent(ctx context.Context, gid, id, parentID uuid.UUID) error {
    seen := map[uuid.UUID]bool{}
    if id != uuid.Nil { seen[id] = true }
    immediate := true
    for parentID != uuid.Nil {
        if seen[parentID] { return hierarchyError("An item or location cannot be placed inside itself or its descendants") }
        seen[parentID] = true
        parent, err := r.db.Entity.Query().Where(entity.ID(parentID), entity.HasGroupWith(group.ID(gid))).WithParent().Only(ctx)
        if err != nil { return err }
        if immediate && parent.Archived { return hierarchyError("Choose an active parent item or location") }
        immediate = false
        parentID = uuid.Nil
        if parent.Edges.Parent != nil { parentID = parent.Edges.Parent.ID }
    }
    return nil
}

// The merged native entity model has one parent edge. Children inherit their
// container's path; moving the container must never reparent its contents.
func (r *EntityRepository) hierarchyTree(ctx context.Context, gid uuid.UUID, withItems bool) ([]TreeItem, error) {
    records, err := r.db.Entity.Query().Where(entity.HasGroupWith(group.ID(gid))).WithParent().WithEntityType().All(ctx)
    if err != nil { return nil, err }
    parents := map[uuid.UUID]uuid.UUID{}
    names := map[uuid.UUID]string{}
    kinds := map[uuid.UUID]string{}
    included := map[uuid.UUID]bool{}
    for _, record := range records {
        names[record.ID] = record.Name
        kinds[record.ID] = "item"
        if record.Edges.EntityType != nil && record.Edges.EntityType.IsLocation { kinds[record.ID] = "location" }
        if record.Edges.Parent != nil { parents[record.ID] = record.Edges.Parent.ID }
        if withItems || kinds[record.ID] == "location" { included[record.ID] = true }
    }
    // The locations view also needs item ancestors of locations. Otherwise a
    // shelf inside a box disappears from the locations tree.
    for id := range included {
        seen := map[uuid.UUID]bool{}
        for current := id; current != uuid.Nil; current = parents[current] {
            if seen[current] { return nil, hierarchyError("The saved hierarchy contains a cycle; clear a parent to repair it") }
            seen[current] = true
            if _, exists := names[current]; !exists { break }
            included[current] = true
        }
    }
    nodes := map[uuid.UUID]*TreeItem{}
    for id := range included { nodes[id] = &TreeItem{ID: id, Name: names[id], Type: kinds[id], Children: []*TreeItem{}} }
    roots := []*TreeItem{}
    for id, node := range nodes {
        if parent := nodes[parents[id]]; parent != nil { parent.Children = append(parent.Children, node) } else { roots = append(roots, node) }
    }
    order := func(items []*TreeItem) {
        sort.Slice(items, func(i, j int) bool {
            if items[i].Type != items[j].Type { return items[i].Type == "location" }
            a, b := strings.ToLower(items[i].Name), strings.ToLower(items[j].Name)
            if a != b { return a < b }
            return items[i].ID.String() < items[j].ID.String()
        })
    }
    order(roots)
    for _, node := range nodes { order(node.Children) }
    result := make([]TreeItem, 0, len(roots))
    for _, node := range roots { result = append(result, *node) }
    return result, nil
}
