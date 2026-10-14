package displayids

import (
	"context"
	"database/sql"
	"fmt"
)

// Install adds the indexed base key and backfills existing entities. Final IDs
// remain dynamic so writes never need to renumber unrelated collision families.
func Install(ctx context.Context, tx *sql.Tx, postgres bool) error {
	var present int
	columnQuery := `SELECT COUNT(*) FROM pragma_table_info('entities') WHERE name = 'display_id_base'`
	if postgres {
		columnQuery = `SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'entities' AND column_name = 'display_id_base'`
	}
	if err := tx.QueryRowContext(ctx, columnQuery).Scan(&present); err != nil { return err }
	if present == 0 {
		if _, err := tx.ExecContext(ctx, `ALTER TABLE entities ADD COLUMN display_id_base text NOT NULL DEFAULT ''`); err != nil { return fmt.Errorf("add display ID base: %w", err) }
	}
	if _, err := tx.ExecContext(ctx, `CREATE INDEX IF NOT EXISTS entity_display_id_base_group_idx ON entities(group_entities, display_id_base)`); err != nil { return fmt.Errorf("index display ID bases: %w", err) }
	rows, err := tx.QueryContext(ctx, `SELECT e.id, e.group_entities, e.name, e.entity_children, et.name FROM entities e JOIN entity_types et ON et.id=e.entity_type_entities ORDER BY e.group_entities, e.id`)
	if err != nil { return fmt.Errorf("read display ID bases: %w", err) }
	type row struct { id, group, name, parent, typ string }
	var all []row
	for rows.Next() { var r row; var parent sql.NullString; if err := rows.Scan(&r.id,&r.group,&r.name,&parent,&r.typ); err != nil { rows.Close(); return err }; r.parent=parent.String; all=append(all,r) }
	if err := rows.Err(); err != nil { rows.Close(); return err }; if err := rows.Close(); err != nil { return err }
	byID:=make(map[string]row,len(all)); for _,r:=range all { byID[r.id]=r }
	update:=`UPDATE entities SET display_id_base=? WHERE id=?`; if postgres { update=`UPDATE entities SET display_id_base=$1 WHERE id=$2` }
	for _,r:=range all { path:=[]string{}; seen:=map[string]bool{r.id:true}; parent:=r.parent; for parent!="" && !seen[parent] { seen[parent]=true; p,ok:=byID[parent]; if !ok || p.group!=r.group { break }; path=append(path,p.name); parent=p.parent }; for i,j:=0,len(path)-1;i<j;i,j=i+1,j-1 { path[i],path[j]=path[j],path[i] }; if _,err:=tx.ExecContext(ctx,update,Base(r.typ,path),r.id); err!=nil { return fmt.Errorf("backfill display ID base %s: %w",r.id,err) } }
	return nil
}
