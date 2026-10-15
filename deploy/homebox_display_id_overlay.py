"""Small source transforms for materialized display-ID write maintenance."""


def patch_display_id_delete_paths(text: str) -> str:
    """Make entity deletes refresh orphaned child bases in the same transaction."""
    for name in ("DeleteByGroup", "DeleteContainerByGroup"):
        start = text.index(f"func (r *EntityRepository) {name}(")
        end = text.index("\nfunc ", start)
        body = text[start:end]
        body = body.replace(
            "\tdefer span.End()",
            "\tdefer span.End()\n\thierarchyWriteMu.Lock()\n\tdefer hierarchyWriteMu.Unlock()",
            1,
        )
        if name == "DeleteByGroup":
            target = '''\t_, deleteSpan := entityTracer().Start(ctx, "repo.EntityRepository.DeleteByGroup.entity")
\t_, err = r.db.Entity.
\t\tDelete().
\t\tWhere(
\t\t\tentity.ID(id),
\t\t\tentity.HasGroupWith(group.ID(gid)),
\t\t).Exec(ctx)'''
            replacement = '''\ttx, err := r.db.Tx(ctx)
\tif err != nil { return err }
\tcommitted := false
\tdefer func(){ if !committed { _ = tx.Rollback() } }()
\tchildren, err := tx.Entity.Query().Where(entity.HasGroupWith(group.ID(gid)),entity.HasParentWith(entity.ID(id))).All(ctx)
\tif err != nil { return err }
\t_, deleteSpan := entityTracer().Start(ctx, "repo.EntityRepository.DeleteByGroup.entity")
\t_, err = tx.Entity.Delete().Where(entity.ID(id),entity.HasGroupWith(group.ID(gid))).Exec(ctx)'''
            assert body.count(target) == 1
            body = body.replace(target, replacement, 1)
            success = "\tdeleteSpan.End()\n\n\tr.publishMutationEvent(gid)"
            assert body.count(success) == 1
            body = body.replace(
                success,
                "\tdeleteSpan.End()\n"
                "\tfor _, child := range children { if err := refreshDisplayIDBasesForSubtree(ctx,tx,gid,child.ID); err != nil { return err } }\n"
                "\tif err := tx.Commit(); err != nil { return err }\n"
                "\tcommitted = true\n\n\tr.publishMutationEvent(gid)",
                1,
            )
        else:
            target = '''\t_, err := r.db.Entity.Delete().Where(entity.ID(id), entity.HasGroupWith(group.ID(gid))).Exec(ctx)
\tif err != nil {
\t\trecordSpanError(span, err)
\t\treturn err
\t}'''
            replacement = '''\ttx, err := r.db.Tx(ctx)
\tif err != nil { return err }
\tcommitted := false
\tdefer func(){ if !committed { _ = tx.Rollback() } }()
\tchildren, err := tx.Entity.Query().Where(entity.HasGroupWith(group.ID(gid)),entity.HasParentWith(entity.ID(id))).All(ctx)
\tif err != nil { return err }
\t_, err = tx.Entity.Delete().Where(entity.ID(id),entity.HasGroupWith(group.ID(gid))).Exec(ctx)
\tif err != nil { recordSpanError(span,err); return err }
\tfor _, child := range children { if err := refreshDisplayIDBasesForSubtree(ctx,tx,gid,child.ID); err != nil { return err } }
\tif err := tx.Commit(); err != nil { return err }
\tcommitted = true'''
            assert body.count(target) == 1
            body = body.replace(target, replacement, 1)
        text = text[:start] + body + text[end:]
    return text
