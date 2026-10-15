package repo
import (
	"context"
	"fmt"
	"regexp"
	"strings"

	"github.com/google/uuid"
	"github.com/sysadminsmedia/homebox/backend/internal/data/displayids"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/entity"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/group"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/entitytype"
)

var displayIDSeparators = regexp.MustCompile(`[^A-Z0-9]+`)

func displayIDSegment(value string) string { return strings.Trim(displayIDSeparators.ReplaceAllString(strings.ToUpper(strings.TrimSpace(value)), "-"), "-") }
func formatDisplayID(typeName string, locationPath []string) string { return displayids.Base(typeName, locationPath) }

func isDisplayIDSearch(value string) bool {
	value = strings.ToUpper(strings.TrimSpace(value))
	if value == "" || strings.HasPrefix(value, "-") || strings.HasSuffix(value, "-") { return false }
	for _, r := range value { if !(r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || r == '-') { return false } }
	segments := strings.Split(value, "-")
	// A fully ASCII generated ID can collapse to one segment when Unicode
	// type or location names normalize away. The query path still combines
	// exact-ID matching with native text/barcode predicates.
	if len(segments) == 1 { return segments[0] != "" }
	if len(segments) < 2 { return false }
	for _, segment := range segments { if segment == "" { return false } }
	return true
}

func displayIDBaseFor(ctx context.Context, client *ent.Client, gid, typeID, parentID uuid.UUID) (string, error) {
	typeName := ""
	if typeID != uuid.Nil { typeInfo, err := client.EntityType.Get(ctx, typeID); if err != nil { return "", err }; typeName=typeInfo.Name }
	path:=[]string{}; seen:=map[uuid.UUID]bool{}
	for parentID!=uuid.Nil && !seen[parentID] {
		seen[parentID]=true
		parent,err:=client.Entity.Query().Where(entity.ID(parentID),entity.HasGroupWith(group.ID(gid))).WithParent().Only(ctx)
		if err!=nil { return "",err }
		path=append(path,parent.Name)
		if parent.Edges.Parent==nil { break }; parentID=parent.Edges.Parent.ID
	}
	for i,j:=0,len(path)-1;i<j;i,j=i+1,j-1 { path[i],path[j]=path[j],path[i] }
	return displayids.Base(typeName,path),nil
}

// refreshDisplayIDBasesForSubtree updates a changed entity and its descendants
// in the caller's transaction so indexed keys never lag a move or rename.
func refreshDisplayIDBasesForSubtree(ctx context.Context, tx *ent.Tx, gid, rootID uuid.UUID) error {
	return refreshDisplayIDBasesForRoots(ctx,tx,gid,[]uuid.UUID{rootID})
}

func refreshDisplayIDBasesForType(ctx context.Context, tx *ent.Tx, gid, typeID uuid.UUID) error {
	rows,err:=tx.Entity.Query().Where(entity.HasGroupWith(group.ID(gid)),entity.HasEntityTypeWith(entitytype.ID(typeID))).WithParent().All(ctx)
	if err!=nil { return fmt.Errorf("load entities for renamed type: %w",err) }
	matching:=map[uuid.UUID]bool{}; for _,row:=range rows { matching[row.ID]=true }
	roots:=make([]uuid.UUID,0,len(rows)); for _,row:=range rows { if row.Edges.Parent==nil||!matching[row.Edges.Parent.ID] { roots=append(roots,row.ID) } }
	return refreshDisplayIDBasesForRoots(ctx,tx,gid,roots)
}

// refreshDisplayIDBasesForRoots fetches each affected subtree and its ancestor
// chains once, then computes all keys in memory before writing within the tx.
func refreshDisplayIDBasesForRoots(ctx context.Context, tx *ent.Tx, gid uuid.UUID, roots []uuid.UUID) error {
	rows:=map[uuid.UUID]*ent.Entity{}
	frontier:=append([]uuid.UUID(nil),roots...)
	for len(frontier)>0 {
		ids:=make([]uuid.UUID,0,len(frontier)); for _,id:=range frontier { if rows[id]==nil { ids=append(ids,id) } }; frontier=nil
		if len(ids)==0 { break }
		batch,err:=tx.Entity.Query().Where(entity.IDIn(ids...),entity.HasGroupWith(group.ID(gid))).WithParent().WithEntityType().All(ctx)
		if err!=nil { return fmt.Errorf("load display ID subtree: %w",err) }
		for _,row:=range batch { rows[row.ID]=row }
		if len(batch)==0 { continue }
		children,err:=tx.Entity.Query().Where(entity.HasGroupWith(group.ID(gid)),entity.HasParentWith(entity.IDIn(ids...))).All(ctx)
		if err!=nil { return fmt.Errorf("load display ID descendants: %w",err) }
		for _,child:=range children { if rows[child.ID]==nil { frontier=append(frontier,child.ID) } }
	}
	// Load all ancestors not already in the descendant set in depth batches.
	frontier=nil; for _,row:=range rows { if row.Edges.Parent!=nil&&rows[row.Edges.Parent.ID]==nil { frontier=append(frontier,row.Edges.Parent.ID) } }
	ancestors:=map[uuid.UUID]*ent.Entity{}
	for len(frontier)>0 {
		ids:=make([]uuid.UUID,0,len(frontier)); for _,id:=range frontier { if ancestors[id]==nil { ids=append(ids,id) } }; frontier=nil; if len(ids)==0 { break }
		batch,err:=tx.Entity.Query().Where(entity.IDIn(ids...),entity.HasGroupWith(group.ID(gid))).WithParent().All(ctx)
		if err!=nil { return fmt.Errorf("load display ID ancestors: %w",err) }
		for _,row:=range batch { ancestors[row.ID]=row; if row.Edges.Parent!=nil&&rows[row.Edges.Parent.ID]==nil&&ancestors[row.Edges.Parent.ID]==nil { frontier=append(frontier,row.Edges.Parent.ID) } }
	}
	for id,row:=range rows {
		typeName:=""; if row.Edges.EntityType!=nil { typeName=row.Edges.EntityType.Name }
		path:=[]string{}; parent:=row.Edges.Parent; seen:=map[uuid.UUID]bool{id:true}
		for parent!=nil&&!seen[parent.ID] { seen[parent.ID]=true; path=append(path,parent.Name); next:=rows[parent.ID]; if next==nil { next=ancestors[parent.ID] }; if next==nil { break }; parent=next.Edges.Parent }
		for i,j:=0,len(path)-1;i<j;i,j=i+1,j-1 { path[i],path[j]=path[j],path[i] }
		if err:=tx.Entity.UpdateOneID(id).SetDisplayIDBase(displayids.Base(typeName,path)).Exec(ctx); err!=nil { return fmt.Errorf("refresh display ID base %s: %w",id,err) }
	}
	return nil
}

// populateDisplayIDs loads only indexed base families for the returned rows,
// then follows overlapping suffix interpretations until the component closes.
func (r *EntityRepository) populateDisplayIDs(ctx context.Context, gid uuid.UUID, items []EntitySummary) error {
	return r.populateDisplayIDsWithSeed(ctx, gid, items, nil)
}

func (r *EntityRepository) populateDisplayIDsWithSeed(ctx context.Context, gid uuid.UUID, items []EntitySummary, queriedBases []string) error {
	if len(items)==0 { return nil }
	bases:=map[string]bool{}; for _,item:=range items { if item.DisplayIDBase!="" { bases[item.DisplayIDBase]=true } }
	loaded:=map[uuid.UUID]EntitySummary{}
	loadedBases:=map[string]bool{}
	searched:=map[string]bool{}
	for _,base:=range queriedBases { searched[base]=true }
	if len(queriedBases)>0 { for _,item:=range items { loaded[item.ID]=item; loadedBases[item.DisplayIDBase]=true } }
	assigned:=map[string]string{}
	assignLoaded:=func() {
		entries:=make([]displayids.Entry,0,len(loaded)); for _,summary:=range loaded { entries=append(entries,displayids.Entry{ID:summary.ID.String(),AssetID:int64(summary.AssetID),Base:summary.DisplayIDBase}) }
		assigned=displayids.Assign(entries)
		bases=map[string]bool{}
		for _,id:=range assigned { for _,candidate:=range displayids.SearchBases(id) { if !loadedBases[candidate]&&!searched[candidate] { bases[candidate]=true } } }
	}
	if len(queriedBases)>0 { assignLoaded() }
	for len(bases)>0 {
		batch:=make([]string,0,len(bases)); for base:=range bases { if !searched[base] { batch=append(batch,base); searched[base]=true } }; bases=map[string]bool{}
		if len(batch)==0 { break }
		records,err:=r.db.Entity.Query().Where(entity.HasGroupWith(group.ID(gid)),entity.DisplayIDBaseIn(batch...)).WithParent().WithEntityType().All(ctx)
		if err!=nil { return fmt.Errorf("load display ID collision families: %w",err) }
		for _,record:=range records { summary:=mapEntitySummary(record); loaded[summary.ID]=summary; loadedBases[summary.DisplayIDBase]=true }
		assignLoaded()
	}
	ancestors:=map[uuid.UUID]EntitySummary{}; frontier:=map[uuid.UUID]bool{}
	for _,item:=range items { if item.Parent!=nil { frontier[item.Parent.ID]=true } }
	for len(frontier)>0 {
		ids:=make([]uuid.UUID,0,len(frontier)); for id:=range frontier { if _,ok:=ancestors[id]; !ok { ids=append(ids,id) } }; frontier=map[uuid.UUID]bool{}; if len(ids)==0 { break }
		parents,err:=r.db.Entity.Query().Where(entity.IDIn(ids...),entity.HasGroupWith(group.ID(gid))).WithParent().WithEntityType().All(ctx)
		if err!=nil { return fmt.Errorf("load display ID location ancestors: %w",err) }
		for _,row:=range parents { summary:=mapEntitySummary(row); ancestors[row.ID]=summary; if summary.Parent!=nil { frontier[summary.Parent.ID]=true } }
	}
	var attach func(*EntitySummary,map[uuid.UUID]bool)
	attach=func(item *EntitySummary,seen map[uuid.UUID]bool) { if item==nil||item.Parent==nil||seen[item.ID] { return }; seen[item.ID]=true; if full,ok:=ancestors[item.Parent.ID]; ok { parent:=full; item.Parent=&parent; attach(item.Parent,seen) } }
	for i:=range items { items[i].DisplayID=assigned[items[i].ID.String()]; attach(&items[i],map[uuid.UUID]bool{}) }
	return nil
}

// findDisplayIDSearchMatch resolves an exact generated ID from only the
// indexed candidate base families and their collision-closure families.
func (r *EntityRepository) findDisplayIDSearchMatch(ctx context.Context, gid uuid.UUID, displayID string) (uuid.UUID, bool, error) {
	bases := displayids.SearchBases(displayID)
	records, err := r.db.Entity.Query().Where(
		entity.HasGroupWith(group.ID(gid)),
		entity.DisplayIDBaseIn(bases...),
	).WithParent().WithEntityType().All(ctx)
	if err != nil {
		return uuid.Nil, false, fmt.Errorf("load exact display ID candidate families: %w", err)
	}
	items := make([]EntitySummary, 0, len(records))
	for _, record := range records {
		items = append(items, mapEntitySummary(record))
	}
	if err := r.populateDisplayIDsWithSeed(ctx, gid, items, bases); err != nil {
		return uuid.Nil, false, err
	}
	for _, item := range items {
		if strings.EqualFold(item.DisplayID, displayID) {
			return item.ID, true, nil
		}
	}
	return uuid.Nil, false, nil
}
