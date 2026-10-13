#!/usr/bin/env python3
"""Stage a pinned native backend with flexible hierarchy fixes; never deploy it."""
import pathlib,shutil,subprocess,os,json,hashlib,re
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
BUILD=ROOT/'work/homebox-backend-build'
shutil.copytree(ROOT/'upstream/homebox/backend',BUILD,dirs_exist_ok=True)
for source, destination in (
    (ROOT/'homebox-backend/shortcodes', BUILD/'internal/data/shortcodes'),
    (ROOT/'homebox-backend/repo_short_codes.go', BUILD/'internal/data/repo/repo_short_codes.go'),
    (ROOT/'homebox-backend/ent_tx_sql.go', BUILD/'internal/data/ent/short_code_tx.go'),
    (ROOT/'homebox-backend/v1_ctrl_item_short_codes.go', BUILD/'app/api/handlers/v1/v1_ctrl_item_short_codes.go'),
    (ROOT/'homebox-backend/20260513120000_item_short_codes.go', BUILD/'internal/data/migrations/sqlite3/20260513120000_item_short_codes.go'),
    (ROOT/'homebox-backend/20260513120001_item_short_codes.go', BUILD/'internal/data/migrations/postgres/20260513120001_item_short_codes.go'),
    (ROOT/'homebox-backend/repo_short_codes_test.go', BUILD/'internal/data/repo/repo_short_codes_test.go'),
):
    if source.is_dir(): shutil.copytree(source,destination,dirs_exist_ok=True)
    else: shutil.copy2(source,destination)
schema=BUILD/'internal/data/ent/schema/entity.go'; body=schema.read_text()
anchor='\t\tfield.String("import_ref").'
assert body.count(anchor)==1
body=body.replace(anchor,'\t\tfield.String("short_code").Optional().Nillable().MaxLen(32),\n'+anchor)
schema.write_text(body)
go=pathlib.Path((ROOT/'work/toolchains/go-path.txt').read_text().strip())/'bin/go'
env=dict(os.environ,CGO_ENABLED='0',GOTOOLCHAIN='local',GOPATH=str(ROOT/'work/toolchains/go-cache'),GOCACHE=str(ROOT/'work/toolchains/go-build-cache'))
subprocess.run([str(go),'generate','./internal/data/ent'],cwd=BUILD,env=env,check=True)
test_main=BUILD/'internal/data/repo/main_test.go';mb=test_main.read_text()
mb=mb.replace('"github.com/sysadminsmedia/homebox/backend/internal/data/ent"','"github.com/sysadminsmedia/homebox/backend/internal/data/ent"\n\t"github.com/sysadminsmedia/homebox/backend/internal/data/shortcodes"',1)
anchor='\terr = client.Schema.Create(context.Background())\n\tif err != nil {\n\t\tlog.Fatalf("failed creating schema resources: %v", err)\n\t}\n'
assert mb.count(anchor)==1
setup='''\tshortCodeTx, err := client.Sql().BeginTx(context.Background(), nil)
\tif err != nil { log.Fatalf("failed starting short-code test setup: %v", err) }
\tif err := shortcodes.Install(context.Background(), shortCodeTx, false); err != nil { log.Fatalf("failed setting up short-code counters: %v", err) }
\tif err := shortCodeTx.Commit(); err != nil { log.Fatalf("failed committing short-code test setup: %v", err) }
'''
mb=mb.replace(anchor,anchor+setup,1)
test_main.write_text(mb)
source=BUILD/'internal/data/repo/repo_entities.go';text=source.read_text()
text=text.replace('Name         string    `json:"name"         validate:"required,min=1,max=255"`','Name         string    `json:"name"         validate:"required,min=1,max=255"`\n\t\tModelNumber  string    `json:"modelNumber"`',1)
text=text.replace('Name        string    `json:"name"`\n\t\tDescription','Name        string    `json:"name"`\n\t\tShortCode   string    `json:"shortCode"`\n\t\tDescription',1)
# Add shortCode to the shared summary embedded by both list and detail DTOs.
summary=text.index('\tEntitySummary struct {')
name_line=text.index('\n',text.index('\t\tName ',summary))+1
if 'ShortCode' not in text[summary:text.index('\n\t}',summary)]:
    text=text[:name_line]+'\t\tShortCode   string    `json:"shortCode"`\n'+text[name_line:]
text=text.replace('Name:          e.Name,','Name:          e.Name,\n\t\tShortCode:     lo.FromPtrOr(e.ShortCode, ""),',1)
text=text.replace('entity.SerialNumberContainsFold(q.Search),','entity.SerialNumberContainsFold(q.Search),\n\t\t\t\tentity.ShortCodeContainsFold(q.Search),',1)
# Ordinary creation allocates inside the same transaction as the item insert.
start=text.index('\tq := r.db.Entity.Create().',text.index('func (r *EntityRepository) Create('))
end=text.index('\n\tspan.SetAttributes(attribute.String("entity.id"',start)
replacement='''	if data.EntityTypeID == uuid.Nil {
		etID, err := r.resolveDefaultEntityType(ctx, gid, false)
		if err != nil { recordSpanError(span, err); return EntityOut{}, err }
		data.EntityTypeID = etID
	}
	typeInfo, err := r.db.EntityType.Get(ctx, data.EntityTypeID)
	if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	tx, err := r.db.Tx(ctx)
	if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	committed := false
	defer func() { if !committed { _ = tx.Rollback() } }()
	shortCode := ""
	if !typeInfo.IsLocation {
		shortCode, err = allocateShortCode(ctx, tx, gid, data.ModelNumber, data.Name)
		if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	}
	q := tx.Entity.Create().SetImportRef(data.ImportRef).SetName(data.Name).SetQuantity(data.Quantity).
		SetDescription(data.Description).SetGroupID(gid).SetAssetID(int64(data.AssetID)).
		SetEntityTypeID(data.EntityTypeID).SetModelNumber(data.ModelNumber)
	if shortCode != "" { q.SetShortCode(shortCode) }
	if data.ParentID != uuid.Nil { q.SetParentID(data.ParentID) }
	if len(data.TagIDs) > 0 { q.AddTagIDs(data.TagIDs...) }
	result, err := q.Save(ctx)
	if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	if err := tx.Commit(); err != nil { recordSpanError(span, err); return EntityOut{}, err }
	committed = true
'''
text=text[:start]+replacement+text[end:]
# Template creation follows the same allocator and keeps its default model number.
anchor='''	// Create entity with all template data
	newEntityID := uuid.New()'''
assert text.count(anchor)==1
text=text.replace(anchor,'''\t// Create entity with all template data
	newEntityID := uuid.New()
	typeInfo, err := tx.EntityType.Get(ctx, data.EntityTypeID)
	if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	shortCode := ""
	if !typeInfo.IsLocation {
		shortCode, err = allocateShortCode(ctx, tx, gid, data.ModelNumber, data.Name)
		if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	}''',1)
anchor='''		SetWarrantyDetails(data.WarrantyDetails)

	if data.ParentID != uuid.Nil {'''
assert text.count(anchor)==1
text=text.replace(anchor,'''\t\tSetWarrantyDetails(data.WarrantyDetails)
	if shortCode != "" { entityBuilder.SetShortCode(shortCode) }

	if data.ParentID != uuid.Nil {''',1)
# Duplicate records receive fresh codes while preserving their model hint.
anchor='''	newEntityID := uuid.New()
	span.SetAttributes(
		attribute.String("entity.new_id", newEntityID.String()),'''
assert text.count(anchor)==1
text=text.replace(anchor,'''\tnewEntityID := uuid.New()
	shortCode := ""
	if originalEntity.EntityType == nil || !originalEntity.EntityType.IsLocation {
		shortCode, err = allocateShortCode(ctx, tx, gid, originalEntity.ModelNumber, options.CopyPrefix+originalEntity.Name)
		if err != nil { recordSpanError(span, err); return EntityOut{}, err }
	}
	span.SetAttributes(
		attribute.String("entity.new_id", newEntityID.String()),''',1)
anchor='''		SetSyncChildEntityLocations(originalEntity.SyncChildEntityLocations)

	// Skip Set on zero dates'''
assert text.count(anchor)==1
text=text.replace(anchor,'''\t\tSetSyncChildEntityLocations(originalEntity.SyncChildEntityLocations)
	if shortCode != "" { entityBuilder.SetShortCode(shortCode) }

	// Skip Set on zero dates''',1)
template_controller=BUILD/'app/api/handlers/v1/v1_ctrl_entity_templates.go';tb=template_controller.read_text()
tb=tb.replace('Name        string    `json:"name"         validate:"required,min=1,max=255"`','Name        string    `json:"name"         validate:"required,min=1,max=255"`\n\tModelNumber *string   `json:"modelNumber"`',1)
anchor='''		// Create entity with all template data in a single transaction
		return ctrl.repo.Entities.CreateFromTemplate'''
assert tb.count(anchor)==1
tb=tb.replace(anchor,'''\t\t// Create entity with all template data in a single transaction
		modelNumber := template.DefaultModelNumber
		if body.ModelNumber != nil { modelNumber = *body.ModelNumber }
		return ctrl.repo.Entities.CreateFromTemplate''',1)
tb=tb.replace('ModelNumber:      template.DefaultModelNumber,','ModelNumber:      modelNumber,',1)
template_controller.write_text(tb)
# CSV imports allocate from the row's model number when a new native item is made.
service=BUILD/'internal/core/services/service_entities.go';sb=service.read_text()
anchor='''\t\t\tnewEntity := repo.EntityCreate{
				ImportRef:   row.ImportRef,
				Name:        row.Name,'''
assert sb.count(anchor)==1
sb=sb.replace(anchor,'''\t\t\tnewEntity := repo.EntityCreate{
				ImportRef:   row.ImportRef,
				Name:        row.Name,
				ModelNumber: row.ModelNumber,''',1)
service.write_text(sb)
# Preserve the API, metadata and tenant checks; guard every parent-changing path.
for name,node,returned in [('Create','uuid.Nil','EntityOut{}, err'),('CreateFromTemplate','uuid.Nil','EntityOut{}, err'),('UpdateByGroup','data.ID','EntityOut{}, err'),('Patch','id','err')]:
    match=re.search(r'^func \(r \*EntityRepository\) '+name+r'\([^\n]+\{',text,re.M);assert match,name
    start=match.end();end=text.find('\nfunc ',start);end=len(text) if end<0 else end
    body=text[start:end];anchor='\tif err := assertEntityTypeInGroup(ctx, r.db.EntityType, gid, data.EntityTypeID); err != nil {';assert body.count(anchor)==1,name
    guard=f'\tif err := r.validateHierarchyParent(ctx, gid, {node}, data.ParentID); err != nil {{\n\t\trecordSpanError(span, err)\n\t\treturn {returned}\n\t}}\n'
    body=body.replace(anchor,guard+anchor)
    text=text[:start]+'\n\thierarchyWriteMu.Lock()\n\tdefer hierarchyWriteMu.Unlock()\n'+body+text[end:]
start=text.index('\tif data.SyncChildEntityLocations {');end=text.index('\n\t_, execSpan :=',start)
text=text[:start]+'\t// Descendants keep their parent edges and follow this container naturally.\n'+text[end:]
start=text.index('func patchSyncChildLocations(');end=text.index('\nfunc ',start)
header=text[start:text.index('{',start)+1]
text=text[:start]+header+'\n\t// One native parent edge already preserves each child inside its container.\n\treturn nil\n}\n'+text[end:]
start=text.index('func (r *EntityRepository) Tree(');end=text.index('\nfunc ConvertEntitiesToTree(',start)
header=text[start:text.index('{',start)+1]
text=text[:start]+header+'\n\treturn r.hierarchyTree(ctx, gid, tq.WithItems)\n}\n'+text[end:]
# An explicit optional PATCH field distinguishes clearing a parent from omitting it.
start=text.index('\tEntityPatch struct {');end=text.index('\n\t}',start)
text=text[:end]+'\n\t\tClearParent bool `json:"clearParent,omitempty"`'+text[end:]
start=text.index('func (r *EntityRepository) Patch(');end=text.index('\nfunc ',start)
body=text[start:end]
anchor='\tif data.ParentID != uuid.Nil {\n\t\tq.SetParentID(data.ParentID)\n\t}'
assert body.count(anchor)==1
body=body.replace(anchor, '\tif data.ClearParent {\n\t\tq.ClearParent()\n\t} else if data.ParentID != uuid.Nil {\n\t\tq.SetParentID(data.ParentID)\n\t}')
guard='\tif data.ClearParent && data.ParentID != uuid.Nil { return hierarchyError("Choose a parent or clear it, not both") }\n'
body=body.replace('\tctx, span :=',guard+'\tctx, span :=',1)
text=text[:start]+body+text[end:]
# Preserve ancestor types and tenant boundaries; UNION stops legacy cycles.
start=text.index('func (r *EntityRepository) PathForEntity(');end=text.index('\nfunc ',start)
body=text[start:end]
body=body.replace('UNION ALL','UNION').replace('JOIN entity_path ep ON e.id = ep.entity_children','JOIN entity_path ep ON e.id = ep.entity_children\n\t\tWHERE e.group_entities = $2')
body=body.replace('SELECT id, name\n\t  FROM entity_path', "SELECT ep.id, ep.name, CASE WHEN et.is_location THEN 'location' ELSE 'item' END\n\t  FROM entity_path ep\n\t  JOIN entities e ON e.id = ep.id\n\t  JOIN entity_types et ON et.id = e.entity_type_entities")
body=body.replace('\t\tentry.Type = EntityPathTypeLocation\n','').replace('rows.Scan(&entry.ID, &entry.Name)', 'rows.Scan(&entry.ID, &entry.Name, &entry.Type)')
text=text[:start]+body+text[end:]
source.write_text(text)
# Native, password-free member profiles reuse the existing user/settings tables.
users=BUILD/'internal/data/repo/repo_users.go';body=users.read_text()
anchor='\t\tID    uuid.UUID `json:"id"`\n\t}'
assert body.count(anchor)==1
body=body.replace(anchor,'\t\tID    uuid.UUID `json:"id"`\n\t\tAvatar string `json:"avatar,omitempty"`\n\t}')
start=body.index('func mapUserSummary(');end=body.index('\nfunc ',start)
part=body[start:end].replace('Email: user.Email,','Email: memberPublicEmail(user),\n\t\tAvatar: memberProfileString(user,"avatar"),')
body=body[:start]+part+body[end:]
anchor='func (r *UserRepository) SetSettings(ctx context.Context, uid uuid.UUID, settings map[string]interface{}) error {'
assert body.count(anchor)==1
body=body.replace(anchor,anchor+'''\n\tmemberProfileMu.Lock(); defer memberProfileMu.Unlock()
\tcurrent, err := r.db.User.Get(ctx,uid); if err != nil { return err }
\tcopy := map[string]interface{}{}; for key,value := range settings { if key != memberProfileKey { copy[key] = value } }
\tif profile,ok := current.Settings[memberProfileKey]; ok { copy[memberProfileKey] = profile }
\tsettings = copy
''')
# The added lookup introduces err earlier in this one method.
start=body.index(anchor);end=body.index('\nfunc ',start)
part=body[start:end].replace('err := r.db.User.UpdateOneID(uid).SetSettings(settings).Exec(ctx)','err = r.db.User.UpdateOneID(uid).SetSettings(settings).Exec(ctx)')
body=body[:start]+part+body[end:]
anchor='err := r.db.User.UpdateOneID(id).SetDefaultGroupID(groupID).Exec(ctx)'
assert body.count(anchor)==1
body=body.replace(anchor,'q := r.db.User.UpdateOneID(id)\n\tif groupID == uuid.Nil { q.ClearDefaultGroupID() } else { q.SetDefaultGroupID(groupID) }\n\terr := q.Exec(ctx)')
users.write_text(body)
profile_repo=users.parent/'repo_member_profiles.go'
shutil.copy2(ROOT/'homebox-backend/repo_member_profiles.go',profile_repo)
profile_controller=BUILD/'app/api/handlers/v1/v1_ctrl_member_profiles.go'
shutil.copy2(ROOT/'homebox-backend/v1_ctrl_member_profiles.go',profile_controller)
routes=BUILD/'app/api/routes.go';body=routes.read_text()
anchor='\t\tr.Get("/entities", chain.ToHandlerFunc(v1Ctrl.HandleEntitiesGetAll(), userMW...))'
assert body.count(anchor)==1
body=body.replace(anchor,anchor+'\n\t\tr.Get("/entities/short-code/{code}", chain.ToHandlerFunc(v1Ctrl.HandleEntityByShortCode(), userMW...))',1)
anchor='\t\tr.Get("/groups/members", chain.ToHandlerFunc(v1Ctrl.HandleGroupMembersGetAll(), userMW...))'
assert body.count(anchor)==1
body=body.replace(anchor,anchor+'''\n\t\tr.Get("/groups/members/administration", chain.ToHandlerFunc(v1Ctrl.HandleMemberAdministration(), userMW...))
\t\tr.Post("/groups/members", chain.ToHandlerFunc(v1Ctrl.HandleBadgeMemberCreate(), userMW...))
\t\tr.Get("/groups/members/{user_id}/profile", chain.ToHandlerFunc(v1Ctrl.HandleMemberProfileGet(), userMW...))
\t\tr.Put("/groups/members/{user_id}/profile", chain.ToHandlerFunc(v1Ctrl.HandleMemberProfileUpdate(), userMW...))''')
routes.write_text(body)
groups=BUILD/'app/api/handlers/v1/v1_ctrl_group.go';body=groups.read_text()
start=body.index('func (ctrl *V1Controller) HandleGroupMemberRemove()');end=body.index('\n// HandleGroupInvitationsDelete',start)
part=body[start:end];anchor='\t\tauth := services.NewContext(r.Context())'
part=part.replace(anchor,anchor+'''\n\t\tif err := ctrl.requireMemberAdministrator(auth); err != nil { return nil,err }
\t\towner,err := ctrl.repo.Groups.IsOwnerOf(auth,userID,auth.GID); if err != nil { return nil,err }
\t\tif owner { return nil,validate.NewRequestError(errors.New("Collection owners cannot be removed here"),http.StatusBadRequest) }
''',1)
groups.write_text(body[:start]+part+body[end:])
# ponytail: repeated ancestor walks fit a workshop; use a shared visited-state
# closure if large, deep inventories make hierarchy reads costly.
shutil.copy2(ROOT/'homebox-backend/repo_hierarchy.go',source.parent/'repo_hierarchy.go')
# Template creation has its own HTTP validator; its parent must also be optional.
controller=BUILD/'app/api/handlers/v1/v1_ctrl_entity_templates.go'
body=controller.read_text();anchor='`json:"parentId"     validate:"required"`';assert body.count(anchor)==1
controller.write_text(body.replace(anchor,'`json:"parentId"     extensions:"x-nullable"`'))
# Keep the published JSON API contract consistent with these native extensions.
def patch_contract(document):
    schemas=document.get('definitions') or document['components']['schemas']
    for name in ('repo.EntitySummary','repo.EntityOut'):
        schemas[name]['properties']['shortCode']={'type':'string','description':'Stable native item short code; empty for locations.'}
    schemas['repo.EntityCreate']['properties']['modelNumber']={'type':'string','description':'Optional model number used when assigning the new item short code.'}
    schemas['v1.EntityTemplateCreateItemRequest']['properties']['modelNumber']={'type':'string','description':'Optional model number override; omitted preserves the template default.'}
    template=schemas['v1.EntityTemplateCreateItemRequest']
    template['required']=[field for field in template.get('required',[]) if field!='parentId']
    template['properties']['parentId']['x-nullable']=True
    schemas['repo.EntityPatch']['properties']['clearParent']={'type':'boolean','description':'Clear the optional parent. Cannot be combined with parentId.'}
    schemas['repo.UserSummary']['properties']['avatar']={'type':'string','description':'Optional local PNG/JPEG profile picture; absent uses the generated avatar.'}
    schemas['v1.BadgeMemberCreate']={'type':'object','required':['requestKey','name'],'properties':{'requestKey':{'type':'string','format':'uuid','description':'Stable UUID v4 confirmation key, also the new native user ID.'},'name':{'type':'string','maxLength':255},'email':{'type':'string','description':'Optional contact email. No password or PIN is set.'}}}
    fields={key:{'type':'string'} for key in ('name','email','avatar','notes','updatedAt')}
    schemas['repo.MemberProfileUpdate']={'type':'object','required':['name','updatedAt'],'properties':fields}
    schemas['repo.MemberProfile']={'type':'object','properties':dict(fields,id={'type':'string','format':'uuid'},mode={'type':'string','enum':['badge-only','web-account']},editable={'type':'boolean'},protected={'type':'boolean'})}
    definitions='definitions' in document
    def reference(name):return {'$ref':('#/definitions/' if definitions else '#/components/schemas/')+name}
    def response(name,status='200'):
        value={'description':'Native collection member profile'}
        value.update({'schema':reference(name)} if definitions else {'content':{'application/json':{'schema':reference(name)}}})
        return {status:value,'403':{'description':'Requires ownership of the active collection'},'409':{'description':'Confirmation conflict or stale profile'}}
    create={'summary':'Create a native badge-only member by name','tags':['Group'],'security':[{'Bearer':[]}],'responses':response('repo.MemberProfile','201')}
    update={'summary':'Edit a member profile in its primary collection','tags':['Group'],'security':[{'Bearer':[]}],'responses':response('repo.MemberProfile')}
    path_parameter={'name':'user_id','in':'path','required':True}
    path_parameter.update({'type':'string'} if definitions else {'schema':{'type':'string','format':'uuid'}})
    if definitions:
        create['parameters']=[{'name':'payload','in':'body','required':True,'schema':reference('v1.BadgeMemberCreate')}]
        update['parameters']=[path_parameter,{'name':'payload','in':'body','required':True,'schema':reference('repo.MemberProfileUpdate')}]
    else:
        for operation,body in ((create,'v1.BadgeMemberCreate'),(update,'repo.MemberProfileUpdate')):operation['requestBody']={'required':True,'content':{'application/json':{'schema':reference(body)}}}
        update['parameters']=[path_parameter]
    document['paths']['/v1/groups/members']['post']=create
    document['paths']['/v1/groups/members/{user_id}/profile']={'get':{'summary':'Read an authorized member profile','tags':['Group'],'parameters':[path_parameter],'security':[{'Bearer':[]}],'responses':response('repo.MemberProfile')},'put':update}
    document['paths']['/v1/groups/members/administration']={'get':{'summary':'Check active collection ownership for account management','tags':['Group'],'security':[{'Bearer':[]}],'responses':{'200':{'description':'canManage reports the native per-collection ownership check'}}}}
    code_parameter={'name':'code','in':'path','required':True}
    code_parameter.update({'type':'string'} if definitions else {'schema':{'type':'string'}})
    code_ref=reference('repo.EntityOut')
    code_response={'description':'Exact active item in the authenticated collection'}
    code_response.update({'schema':code_ref} if definitions else {'content':{'application/json':{'schema':code_ref}}})
    document['paths']['/v1/entities/short-code/{code}']={'get':{'summary':'Resolve an item short code exactly','tags':['Entities'],'parameters':[code_parameter],'security':[{'Bearer':[]}],'responses':{'200':code_response,'400':{'description':'Invalid short-code format'},'404':{'description':'No active item matches the code'},'409':{'description':'The code conflicts with another native item identifier'}}}}
    return document
for name in ('swagger.json','openapi-3.json'):
    path=BUILD/'app/api/static/docs'/name
    path.write_text(json.dumps(patch_contract(json.loads(path.read_text())),indent=2)+'\n')
docs=BUILD/'app/api/static/docs/docs.go';body=docs.read_text()
start=body.index('const docTemplate = `')+len('const docTemplate = `');end=body.index('`',start)
raw=body[start:end].replace('{{ marshal .Schemes }}','"__CACI_SCHEMES__"')
raw=json.dumps(patch_contract(json.loads(raw)),indent=2).replace('"__CACI_SCHEMES__"','{{ marshal .Schemes }}').replace('`',r'\u0060')
docs.write_text(body[:start]+raw+body[end:])
# Embed the current verified frontend; the public gateway selects its own release.
shutil.copytree(ROOT/'work/homebox-ui-current',BUILD/'app/api/static/public',dirs_exist_ok=True)
subprocess.run([str(go.with_name('gofmt')),'-w',str(schema),str(source),str(source.parent/'repo_hierarchy.go'),str(controller),str(docs),str(users),str(profile_repo),str(profile_controller),str(routes),str(groups),str(service),str(BUILD/'internal/data/repo/repo_short_codes.go'),str(BUILD/'internal/data/repo/repo_short_codes_test.go'),str(BUILD/'internal/data/ent/short_code_tx.go'),str(BUILD/'internal/data/shortcodes/migration_test.go'),str(BUILD/'app/api/handlers/v1/v1_ctrl_item_short_codes.go')],check=True)
pin=subprocess.check_output(['git','-C',str(ROOT/'upstream/homebox'),'rev-parse','HEAD'],text=True).strip()
flags='-s -w -X main.version=0.26.2-caci.2-shortcodes -X main.commit='+pin+'+hierarchy+members+shortcodes -X main.date='+datetime.now(timezone.utc).isoformat()
subprocess.run([str(go),'build','-mod=readonly','-p','2','-trimpath','-ldflags',flags,'-o',str(BUILD/'homebox'),'./app/api'],cwd=BUILD,env=env,check=True)
receipt={'upstream':pin,'hierarchy_source_sha256':hashlib.sha256((ROOT/'homebox-backend/repo_hierarchy.go').read_bytes()).hexdigest(),'member_sources_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'homebox-backend/repo_member_profiles.go',ROOT/'homebox-backend/v1_ctrl_member_profiles.go')},'short_code_sources_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'homebox-backend/repo_short_codes.go',ROOT/'homebox-backend/ent_tx_sql.go',ROOT/'homebox-backend/v1_ctrl_item_short_codes.go',ROOT/'homebox-backend/shortcodes/short_code.go',ROOT/'homebox-backend/shortcodes/migration.go',ROOT/'homebox-backend/20260513120000_item_short_codes.go',ROOT/'homebox-backend/20260513120001_item_short_codes.go')},'binary_sha256':hashlib.sha256((BUILD/'homebox').read_bytes()).hexdigest(),'version':'0.26.2-caci.2-shortcodes','deployed':False}
(BUILD/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
