#!/usr/bin/env python3
"""Stage a pinned native backend with flexible hierarchy fixes; never deploy it."""
import pathlib,shutil,subprocess,os,json,hashlib,re
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
BUILD=ROOT/'work/homebox-backend-build'
shutil.copytree(ROOT/'upstream/homebox/backend',BUILD,dirs_exist_ok=True)
source=BUILD/'internal/data/repo/repo_entities.go';text=source.read_text()
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
go=pathlib.Path((ROOT/'work/toolchains/go-path.txt').read_text().strip())/'bin/go'
env=dict(os.environ,CGO_ENABLED='0',GOTOOLCHAIN='local',GOPATH=str(ROOT/'work/toolchains/go-cache'),GOCACHE=str(ROOT/'work/toolchains/go-build-cache'))
subprocess.run([str(go.with_name('gofmt')),'-w',str(source),str(source.parent/'repo_hierarchy.go'),str(controller),str(docs),str(users),str(profile_repo),str(profile_controller),str(routes),str(groups)],check=True)
pin=subprocess.check_output(['git','-C',str(ROOT/'upstream/homebox'),'rev-parse','HEAD'],text=True).strip()
flags='-s -w -X main.version=0.26.2-caci.2 -X main.commit='+pin+'+hierarchy+members -X main.date='+datetime.now(timezone.utc).isoformat()
subprocess.run([str(go),'build','-mod=readonly','-p','2','-trimpath','-ldflags',flags,'-o',str(BUILD/'homebox'),'./app/api'],cwd=BUILD,env=env,check=True)
receipt={'upstream':pin,'hierarchy_source_sha256':hashlib.sha256((ROOT/'homebox-backend/repo_hierarchy.go').read_bytes()).hexdigest(),'member_sources_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'homebox-backend/repo_member_profiles.go',ROOT/'homebox-backend/v1_ctrl_member_profiles.go')},'binary_sha256':hashlib.sha256((BUILD/'homebox').read_bytes()).hexdigest(),'version':'0.26.2-caci.2','deployed':False}
(BUILD/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
