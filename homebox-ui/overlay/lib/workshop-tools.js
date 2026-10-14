import { mountLabelDesigner, exportReviewedPaper } from "./label-editor.js";
import { workshopObjectPresets, workshopPresetForDrawing } from "./workshop-object-catalog.js";
import { labelPrintFailure, pendingLabelPrint } from "./label-print-recovery.js";
const labelQueues = new Map();
// Established workshop workflows hosted by C-Crate's native layout.
export function mountWorkshopTools(root, initialPage, workshop, navigate, notify, /** @type {{entityId:string|null,drawingId:string|null,roomId:string|null}} */ initialSelection={entityId:null,drawingId:null,roomId:null}, /** @type {(workspace:any,status?:string)=>any} */ labelWorkspaceChanged=(workspace)=>workspace) {
let disposed=false;
let suppressPlannerClick=false;
const listeners=[];
function listen(name, fn){window.addEventListener(name,fn);listeners.push([name,fn]);}
// Native C-Crate owns inventory and authentication. This page holds no credentials.
const pages=[['loans','Loans & notes',false],['workshop','Workshop & storage',false],['checkout-cart','Checkout cart',false],['imports','Imports',true],['labels','Label queue',true],['recovery','Recovery',true],['system','System',true]];
const view=root.querySelector('#view'),dialog=root.querySelector('#dialog'),dialogBody=root.querySelector('#dialog-body');
let context=workshop.context.value,current=initialPage,routeVersion=0,dialogEpoch=0,itemTabVersion=0,busy=false,dialogDirty=false,dialogCommit=false,activeItem=null,layoutState=null,layoutDraft=null,layoutDirty=false,layoutSelected=initialSelection.drawingId||null,importBatch=null,importSelectionRevision=0,plannerInspectorInputRevision=0,plannerInspectorCommittedRevision=0;
let workshopView=null,workshopViewAvailable=false,workshopViewError='',workshopEntityId=initialSelection.entityId||null,includeNested=false,workshopViewAcrossRooms=false,browseMode='browse',workshopReadToken=0,workshopSearchRows=null,workshopSearchText='',workshopSearchIdentity=null,workshopSearchOwner=null,workshopSearchToken=0,workshopSearchRenderPending=false,workshopFilter='all',workshopOverlays=false,workshopSelectedStatus=null,workshopRefreshSkipped=false,roomSelectionUnsupported=false,deferredWorkshopSelection=null,workshopSelectionGeneration=0,workshopSelectionFlushQueued=false,acrossRoomRouteSelection=null;
let equipment=[],locations=[],parents=[],loans=[],members=[],badges=[],types=[],equipmentQuery='',equipmentFilter='',selection=new Set(),labelSelection=new Set(),labelEditor=null,labelEditorDirty=false,labelEditorBusy=false,labelReviews=null,labelReviewIds=[],labelTemplates=[],labelWorkspace=null;
let shelfCheck=null,shelfHistory=[],shelfLocationId=null,shelfToken=0,shelfNotesDraft='',shelfNotesDirty=false,shelfStartUncertain=null;
let activeRoomId=initialSelection.roomId||null,selectedDrawingByRoom={},roomUndo=new Map(),roomRedo=new Map(),plannerZoom=1,plannerPan={x:0,y:0},plannerSnap=true,plannerGrid=true,pendingPaletteKind=null,pendingPaletteName=null,pendingPalettePreset=null,plannerCanvasObserver=null,coverageOpen=false,layoutUncertain=null,roomChooserMessage='',layoutSaveError='',plannerEditError='',roomSettingsShown=false,plannerShowTools=false,plannerShowInspector=false,plannerTabToken=null;
const plannerPendingInspectorLabels=new Set();
const clone=v=>JSON.parse(JSON.stringify(v));
function uuid(){if(typeof crypto.randomUUID==='function')return crypto.randomUUID();const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;const s=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');return [s.slice(0,8),s.slice(8,12),s.slice(12,16),s.slice(16,20),s.slice(20)].join('-')}
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined&&text!==null)n.textContent=String(text);if(cls)n.className=cls;return n}
function button(text,fn,cls=''){const b=node('button',text,cls);b.type='button';b.onclick=event=>Promise.resolve().then(()=>fn(event)).catch(error=>report(error));return b}
function link(text,path){const a=node('a',text,'button');a.href=path;return a}
function panel(...content){const p=node('section',null,'panel');p.append(...content.filter(Boolean));return p}
function message(text,cls='notice'){return node('div',text,cls)}
function shelfPath(path){return Array.isArray(path)&&path.length?path.map(part=>part?.name||part?.code||part?.id).filter(Boolean).join(' / '):'Unknown path'}
function shelfChangeReview(check){const review=panel(),changes=Array.isArray(check.changes)?check.changes:Object.entries(check.changes||{}).map(([kind,value])=>({kind,items:value?.items||[]})),items=changes.flatMap(change=>(change.items||[]).map(item=>({kind:change.kind,item}))).filter(row=>['added','removed','changed','renamed','observed','location','location_renamed'].includes(row.kind));review.setAttribute('aria-label','Inventory changes since the original snapshot');review.append(node('h2','Changed inventory'));if(!items.length)review.append(node('p','No inventory changes recorded.'));for(const {kind,item} of items){const before=item.before||(kind==='removed'?item:{}),after=item.after||(kind==='added'?item:{}),name=item.name||after.name||before.name||item.id||'Inventory record',line=node('p',name+' Â· '+kind.replaceAll('_',' '));if(before.quantity!==undefined||after.quantity!==undefined)line.append(document.createTextNode(' Â· quantity '+(before.quantity??'unknown')+' â†’ '+(after.quantity??'unknown')));if(before.path||after.path)line.append(document.createTextNode(' Â· path '+shelfPath(before.path)+' â†’ '+shelfPath(after.path)));if(before.custody||after.custody)line.append(document.createTextNode(' Â· custody '+(before.custody?.checked_out?'Checked out':'Available/unknown')+' â†’ '+(after.custody?.checked_out?'Checked out':'Available/unknown')));review.append(line)}const pending=panel(),inventory=[...(check.original_snapshot?.items||[]),...Object.values(check.groups||{}).flat()],names=new Map(inventory.map(item=>[item.id||item.entity_id,item.name||item.id||item.entity_id]));pending.setAttribute('aria-label','Pending native operations');pending.append(node('h2','Pending native operations'));if(!(check.pending_operations||[]).length)pending.append(node('p','No pending native operations.'));for(const operation of check.pending_operations||[]){const action=operation.name||operation.action?.replaceAll('_',' ')||operation.operation||operation.id||'Native operation',assets=operation.assets?.map(id=>names.get(id)||id).join(', ');pending.append(node('p',action+' Â· '+(operation.status||'status unknown')+(operation.id?' Â· operation '+operation.id:'')+(assets?' Â· equipment '+assets:'')+(operation.message||operation.reason?' Â· '+(operation.message||operation.reason):'')))}return [review,pending]}
function title(name,description,action){const row=node('div',null,'title'),copy=node('div');copy.append(node('h1',name),node('p',description));row.append(copy);if(action)row.append(action);view.append(row)}
function actions(...content){const row=node('div',null,'right');row.append(...content.filter(Boolean));return row}
function tag(text,kind=''){return node('span',text,'tag '+kind)}
function field(parent,label,value='',kind='text',onchange){const wrap=node('label',label,'field'),input=node(kind==='textarea'?'textarea':'input');if(kind!=='textarea')input.type=kind;input.value=value??'';input.setAttribute('aria-label',label);if(kind==='textarea')input.maxLength=1000;input.oninput=()=>{dialogDirty=true;if(onchange)onchange(input.value)};wrap.append(input);parent.append(wrap);return input}
function select(parent,label,choices,value,onchange){const wrap=node('label',label),input=node('select');input.setAttribute('aria-label',label);input.disabled=!!layoutUncertain;for(const [id,name] of choices)input.append(new Option(name,id));input.value=value??'';input.onchange=()=>{dialogDirty=true;if(onchange)onchange(input.value)};wrap.append(input);parent.append(wrap);return input}
function checkbox(parent,label,checked,onchange){const wrap=node('label'),input=node('input');input.type='checkbox';input.checked=checked;input.setAttribute('aria-label',label);input.onchange=()=>{dialogDirty=true;onchange?.(input.checked)};wrap.append(input,document.createTextNode(label));parent.append(wrap);return input}
function table(headers,rows){const wrap=node('div',null,'table-wrap'),t=node('table'),head=node('thead'),hr=node('tr'),body=node('tbody');headers.forEach(h=>hr.append(node('th',h)));head.append(hr);for(const row of rows){const tr=node('tr');for(const value of row){const td=node('td');if(value instanceof Node)td.append(value);else td.textContent=value??'';tr.append(td)}body.append(tr)}if(!rows.length){const td=node('td','No records to show.','empty');td.colSpan=headers.length;body.append(td)}t.append(head,body);wrap.append(t);return wrap}
function toast(text){notify(text)}
function report(error){const parent=dialog.open?dialogBody:view;parent.querySelector('.error')?.remove();const box=message(error.message||String(error),'error');box.setAttribute('role','alert');parent.append(box)}
function timestamp(value){if(!value)return 'Time unavailable';const date=new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value)?value:String(value).replace(' ','T')+'Z');if(Number.isNaN(date.getTime()))return 'Time unavailable';return new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',timeZoneName:'short'}).format(date)}
function manager(){return !!context?.manager}
function canEditPlan(){return manager()&&current==='workshop'&&browseMode==='edit'&&!busy&&!layoutUncertain}
function captureUi(){return {identity:context?.identity,route:routeVersion,dialog:dialogEpoch}}
function uiCurrent(token){return token.identity===context?.identity&&token.route===routeVersion&&token.dialog===dialogEpoch}
function scope(){return context?`${context.group.id}:${context.user.id}`:''}
function pending(){try{return JSON.parse(localStorage.getItem('workshop-pending:'+scope())||'[]')}catch{return []}}
function savePending(rows){localStorage.setItem('workshop-pending:'+scope(),JSON.stringify(rows))}
function removePending(key){savePending(pending().filter(p=>p.key!==key))}
function shelfOrderMarker(key,subject){if(typeof key!=='string'||typeof subject!=='string'||!subject)return null;const storageKey='workshop-order:'+scope()+':'+subject;try{const marker=JSON.parse(localStorage.getItem(storageKey)||'null');return marker?.status==='pending'&&marker.request_key===key&&marker.entity_id===subject?{storageKey,marker}:null}catch{return null}}
function clearShelfOrderMarker(key,subject){const saved=shelfOrderMarker(key,subject);if(saved)localStorage.removeItem(saved.storageKey)}
async function api(path,data,identity=context?.identity){if(disposed)throw Error('Page closed.');const result=await workshop.request(path,data,identity);if(disposed)throw Error('Page closed.');return result}
function shelfCurrent(token,identity,owner){return !disposed&&token===shelfToken&&identity===context?.identity&&owner===scope()}
function shelfHasUnsavedDraft(){return shelfNotesDirty||!!view.querySelector('[aria-label="Scan or enter asset code"]')?.value||!!view.querySelector('[aria-label="Visual equipment"]')?.value||!!view.querySelector('[aria-label="Observed quantity"]')?.value||!!view.querySelector('[aria-label="Visual quantity"]')?.value}
function shelfQuantity(input){const value=input.valueAsNumber;if(!Number.isSafeInteger(value)||value<0)throw Error('Enter a whole number of 0 or greater.');return value}
async function openShelfCheck(locationId=null,checkId=null){
  if(shelfHasUnsavedDraft()&&!window.confirm('This shelf check has unsaved notes or tallies. Refreshing or reopening will discard them. Continue?'))return;
  const token=++shelfToken,identity=context?.identity,owner=scope();shelfLocationId=locationId||shelfCheck?.location_id||null;
  if(checkId){shelfCheck=await api('workshop/checks/get?id='+encodeURIComponent(checkId),undefined,identity);if(shelfCheck?.location_id)shelfHistory=await api('workshop/checks/list?location_id='+encodeURIComponent(shelfCheck.location_id),undefined,identity)}
  else if(locationId){shelfHistory=await api('workshop/checks/list?location_id='+encodeURIComponent(locationId),undefined,identity);shelfCheck=shelfHistory.find(row=>row.state==='draft')||null}
  if(!shelfCurrent(token,identity,owner))return;
  shelfNotesDraft=shelfCheck?.notes||'';shelfNotesDirty=false;current='shelf-check';routeVersion++;renderShelfCheck(token);
}
async function recoverShelfCheck(requestKey){
  const pendingRow=pending().find(row=>row.key===requestKey&&row.path==='workshop/checks/start'&&row.identity===context?.identity&&row.group_id===context?.group.id&&row.user_id===context?.user.id);
  if(!pendingRow)throw Error('This shelf-check request is not available in the current account and collection.');
  const token=++shelfToken,identity=context?.identity,owner=scope(),result=await api('workshop/checks/request',{request_key:requestKey},identity);
  if(!shelfCurrent(token,identity,owner))return;
  if(result.status==='completed'&&result.action==='start'&&result.result?.id){workshop.forget(requestKey);await openShelfCheck(result.result.location_id,result.result.id);return}
  if(result.status==='not_started'){
    const body=node('div',null,'form');body.append(message('No check was started. Your request will not be repeated automatically. Confirm explicitly to start one now.','attention'),actions(button('Keep pending',()=>closeDialog(true)),button('Confirm a new shelf check',async()=>{if(!shelfCurrent(token,identity,owner))return;workshop.forget(requestKey);closeDialog(true);await beginShelfCheck(pendingRow.subject,false)},'main')));openDialog('Check start was not found',body);return;
  }
  throw Error('The saved shelf-check result is still uncertain. No request was repeated.');
}
async function beginShelfCheck(locationId,includeNested=false){
  if(!manager()||!locationId)throw Error('Choose a native storage location and sign in as a manager.');
  const token=++shelfToken,identity=context?.identity,owner=scope(),request_key=uuid();shelfLocationId=locationId;shelfStartUncertain=request_key;
  let check;
  try{check=await write('workshop/checks/start',{location_id:locationId,include_nested:includeNested,request_key},'Start shelf check',locationId)}
  catch(error){if(shelfCurrent(token,identity,owner)){const row=pending().find(p=>p.key===request_key);if(!row){const rows=pending();rows.push({key:request_key,path:'workshop/checks/start',label:'Start shelf check',subject:locationId,at:new Date().toISOString(),identity,group_id:context.group.id,user_id:context.user.id});savePending(rows)}shelfCheck=null;shelfStartUncertain=request_key;current='recovery';routeVersion++;await recoveryPage(routeVersion);view.prepend(message('The start reply was not confirmed. Check the saved request before starting again.','attention'));}throw error}
  if(!shelfCurrent(token,identity,owner))return;
  shelfCheck=check;shelfStartUncertain=null;workshop.forget(request_key);await openShelfCheck(locationId,check.id);
}
function renderShelfCheck(token=shelfToken){
  if(disposed||token!==shelfToken)return;view.replaceChildren();const check=shelfCheck;
  title(check?.location?.name||check?.original_snapshot?.location?.name||'Shelf check','Frozen scope and observation history are stored with the check. Refresh before finishing to review current inventory.',button('Refresh check',()=>openShelfCheck(shelfLocationId,check?.id)));
  if(!check){const place=locations.find(row=>row.id===shelfLocationId);view.append(panel(node('p','Start a read-only snapshot for '+(place?.name||shelfLocationId||'this storage location')+'.'),checkbox(view,'Include nested contents',false,()=>{}),button('Start shelf check',()=>beginShelfCheck(shelfLocationId,view.querySelector('[aria-label="Include nested contents"]')?.checked),'main')));return}
  const editable=!!check.can_edit&&check.state==='draft'&&!shelfStartUncertain;
  view.append(message('Revision '+check.revision+' Â· '+(check.include_nested?'Nested contents':'Direct contents')+' Â· Frozen at '+timestamp(check.started_at)+(check.point_in_time?' Â· Completed point-in-time comparison':''),'notice'));
  if(check.suspended_reason)view.append(message(check.suspended_reason,'attention'));
  const snapshot=check.reviewed_snapshot||check.original_snapshot||{},rowsByGroup=check.groups||{};
  const contents=panel(node('h2',check.include_nested?'Nested contents':'Direct contents'));contents.classList.add('shelf-check-groups');
  const names={observed_here:'Observed here',not_observed:'Not observed',checked_out:'Checked out',unexpected_here:'Unexpected here'};
  for(const key of ['observed_here','not_observed','checked_out','unexpected_here']){const rows=rowsByGroup[key]||[],group=node('section',null,'shelf-check-group');group.append(node('h3',names[key]));for(const row of rows){const line=node('p',(row.name||row.entity_id)+' Â· expected '+(row.expected_quantity??'unknown')+' Â· observed '+(row.observed_quantity??'not recorded')+(row.custody_conflict?' Â· Checkout conflict':''));if(key==='unexpected_here'||row.original_path||row.current_path)line.append(document.createTextNode(' Â· original path '+shelfPath(row.original_path)+' Â· current path '+shelfPath(row.current_path||row.path)));group.append(line)}if(!rows.length)group.append(node('p','No records.'));contents.append(group)}
  view.append(...shelfChangeReview(check));
  view.append(contents);
  if(editable){const observation=node('div',null,'form'),code=field(observation,'Scan or enter asset code'),quantity=field(observation,'Observed quantity','','number');quantity.min='0';quantity.step='1';quantity.required=true;let selected=null;
    const resolved=node('div');observation.append(resolved,button('Resolve code',async()=>{const result=await api('workshop/checks/resolve',{id:check.id,raw:code.value});resolved.replaceChildren(node('p',result.message||'Choose an eligible record.'));for(const candidate of result.candidates||[])resolved.append(button(candidate.name+' Â· '+candidate.path.map(item=>item.name).join(' / '),()=>{selected=candidate.id;resolved.dataset.entityId=selected}));if(result.entity_id){selected=result.entity_id;resolved.dataset.entityId=selected}}),button('Save scan observation',async()=>{if(!selected)throw Error('Resolve a native equipment record first.');shelfCheck=await write('workshop/checks/observe',{id:check.id,revision:shelfCheck.revision,entity_id:selected,method:'scan',observed_quantity:shelfQuantity(quantity),request_key:uuid()},'Save shelf observation',check.id);renderShelfCheck()},'main'));
    const visual=node('div',null,'form'),asset=select(visual,'Visual equipment',[['','Choose equipment'],...(snapshot.items||[]).map(item=>[item.id,item.name+' Â· '+item.path.map(part=>part.name).join(' / ')])],'',value=>selected=value),tally=field(visual,'Visual quantity','','number');tally.min='0';tally.step='1';tally.required=true;visual.append(button('Save visual observation',async()=>{if(!asset.value)throw Error('Choose equipment first.');shelfCheck=await write('workshop/checks/observe',{id:check.id,revision:shelfCheck.revision,entity_id:asset.value,method:'visual',observed_quantity:shelfQuantity(tally),request_key:uuid()},'Save visual observation',check.id);renderShelfCheck()},'main'));
    const notes=field(view,'Observation notes',shelfNotesDraft,'textarea',value=>{shelfNotesDraft=value;shelfNotesDirty=true});notes.oninput=()=>{shelfNotesDraft=notes.value;shelfNotesDirty=true};view.append(panel(node('h2','Scan observation'),observation),panel(node('h2','Visual observation'),visual),actions(button('Save notes',async()=>{shelfCheck=await write('workshop/checks/notes',{id:check.id,revision:shelfCheck.revision,notes:shelfNotesDraft,request_key:uuid()},'Save shelf-check notes',check.id);shelfNotesDirty=false;renderShelfCheck()},'main')));
    view.append(actions(button('Refresh review',async()=>{if(shelfHasUnsavedDraft()&&!window.confirm('This shelf check has unsaved notes or tallies. Refreshing will discard them. Continue?'))return;shelfCheck=await write('workshop/checks/refresh',{id:check.id,revision:shelfCheck.revision,request_key:uuid()},'Refresh shelf-check review',check.id);renderShelfCheck()}),button('Finish check',async()=>{if(shelfNotesDirty&&!window.confirm('Notes have unsaved edits. Finish without saving them?'))return;if(!window.confirm('Finish this shelf check using the current reviewed snapshot?'))return;shelfCheck=await write('workshop/checks/finish',{id:check.id,revision:shelfCheck.revision,review_fingerprint:check.review_fingerprint,request_key:uuid()},'Finish shelf check',check.id);shelfHistory=await api('workshop/checks/list?location_id='+encodeURIComponent(shelfLocationId));renderShelfCheck()},'main'),button('Cancel check',async()=>{if(!window.confirm('Cancel this shelf check?'))return;shelfCheck=await write('workshop/checks/cancel',{id:check.id,revision:check.revision,confirmed:true,reason:'Cancelled by manager',request_key:uuid()},'Cancel shelf check',check.id);shelfHistory=await api('workshop/checks/list?location_id='+encodeURIComponent(shelfLocationId));renderShelfCheck()})));
  }else if(check.state==='draft'&&manager())view.append(actions(button('Confirm cancellation',async()=>{if(!window.confirm('Cancel this check on behalf of its owner?'))return;shelfCheck=await write('workshop/checks/cancel',{id:check.id,revision:check.revision,confirmed:true,reason:'Confirmed by another manager',request_key:uuid()},'Cancel shelf check',check.id);shelfHistory=await api('workshop/checks/list?location_id='+encodeURIComponent(shelfLocationId));renderShelfCheck()})));
  view.append(node('p','This comparison records facts at the last review time. Inventory can change independently.','sub'));
  if(shelfLocationId&&shelfHistory.length){const history=panel(node('h2','Shelf-check history'));history.classList.add('shelf-check-history');for(const row of shelfHistory)history.append(button((row.state==='completed'?'Completed':row.state==='cancelled'?'Cancelled':'Draft')+' Â· '+timestamp(row.started_at)+' Â· '+row.actor_label,()=>openShelfCheck(shelfLocationId,row.id)));view.append(history)}
}
function signedOut(){plannerCanvasObserver?.disconnect();plannerCanvasObserver=null;if(layoutDraft&&(layoutDirty||layoutUncertain))persistPlannerSession();const oldScope=scope();if(oldScope)labelQueues.delete(oldScope);labelEditor?.dispose();labelEditor=null;labelEditorDirty=labelEditorBusy=false;labelSelection.clear();labelReviews=null;labelReviewIds=[];labelWorkspace=null;labelWorkspaceChanged(null,'Your account, collection or management access changed. Open C-Crate again and check your account and collection.');context=null;routeVersion++;workshopReadToken++;workshopSearchToken++;workshopSearchRows=null;workshopSearchIdentity=null;workshopSearchOwner=null;workshopSearchText='';workshopSearchRenderPending=false;acrossRoomRouteSelection=null;dialogEpoch++;if(dialog.open)dialog.close();dialogBody.replaceChildren();layoutDraft=null;layoutDirty=false;layoutUncertain=null;importBatch=null;workshopViewAvailable=false;view.replaceChildren(message('Your account, collection or management access changed. Open C-Crate again and check your account and collection.'));}
async function refreshContext(){const previous=context?.identity,next=await workshop.refresh();if(previous!==context?.identity)throw Error('Your sign-in changed while its status was checked.');if(context&&(next.identity!==context.identity||next.manager!==context.manager)){signedOut();throw Error('Your C-Crate account, session or workshop permission changed. Check your sign-in before continuing.')}context=next;return next}
function scheduleWorkshopSelection(){if(workshopSelectionFlushQueued||!deferredWorkshopSelection)return;workshopSelectionFlushQueued=true;setTimeout(()=>{workshopSelectionFlushQueued=false;const pending=deferredWorkshopSelection;if(!pending)return;if(pending.identity!==context?.identity||current!=='workshop'){if(deferredWorkshopSelection===pending)deferredWorkshopSelection=null;return}if(busy)return;if(deferredWorkshopSelection!==pending||pending.generation!==workshopSelectionGeneration){scheduleWorkshopSelection();return}deferredWorkshopSelection=null;updateWorkshopSelection(pending.selection).catch(report)},0)}
function deferWorkshopSelection(selection){const generation=++workshopSelectionGeneration;if(acrossRoomRouteSelection?.entityId===selection.entityId&&acrossRoomRouteSelection.identity===context?.identity&&acrossRoomRouteSelection.owner===scope())acrossRoomRouteSelection.generation=generation;deferredWorkshopSelection={selection,identity:context?.identity,generation};scheduleWorkshopSelection()}
async function write(path,data,label,subject=''){if(busy)throw Error('Wait for confirmation to finish.');busy=true;dialogCommit=true;const frozen=Array.from(root.querySelectorAll('button:not([data-queue-stop]),input,select,textarea')).map(c=>[c,c.disabled]);frozen.forEach(([c])=>c.disabled=true);try{return await workshop.write(path,data,label,subject)}finally{busy=false;dialogCommit=false;frozen.forEach(([c,disabled])=>c.disabled=disabled);if(workshopSearchRenderPending){workshopSearchRenderPending=false;renderWorkshopSearchRows()}scheduleWorkshopSelection()}}
function openDialog(name,...content){if(dialog.open)dialog.close();dialogEpoch++;itemTabVersion++;dialogDirty=false;root.querySelector('#dialog-title').textContent=name;dialogBody.replaceChildren(...content.filter(Boolean));dialog.showModal()}
function closeDialog(force=false){if(dialogCommit&&!force){toast('Wait for confirmation to finish.');return false}if(dialogDirty&&!force&&!window.confirm('Discard these unsaved edits?'))return false;dialogDirty=false;dialogEpoch++;itemTabVersion++;dialog.close();dialogBody.replaceChildren();return true}
root.querySelector('#dialog-close').onclick=()=>closeDialog();dialog.addEventListener('cancel',e=>{e.preventDefault();closeDialog()});
function renderNav(){}
function pendingBanner(){const rows=pending();if(initialPage==='labels'&&labelWorkspace){labelWorkspace.pendingActions=rows.length;return}if(rows.length){const box=message(`${rows.length} action${rows.length===1?' has':'s have'} an unconfirmed result. Saved request identities prevent accidental duplicate creation or printing.`,'attention pending-banner');box.append(button('Check saved actions',()=>go('recovery')));view.prepend(box)}}
async function go(page,push=true){if(disposed)return;if(page!==initialPage){navigate(page==='people'?'/collection/members':page==='equipment'?'/items':'/workshop/'+(page==='workshop'?'map':page));return;}if(!context){signedOut();return}if(busy||labelEditorBusy){toast('Wait for confirmation to finish.');return}if((layoutDirty||layoutUncertain||labelEditorDirty)&&!window.confirm('Discard these unsaved edits?'))return;if(page!=='workshop'&&(layoutDirty||layoutUncertain))persistPlannerSession();if(dialog.open&&!closeDialog())return;if(pages.find(p=>p[0]===page)?.[2]&&!manager()){toast('This area requires Workshop manager permission.');throw Error('This area requires Workshop manager permission.')}current=pages.some(p=>p[0]===page)?page:initialPage;renderNav();const revision=++routeVersion;view.replaceChildren(node('p','Loadingâ€¦','spinner'));try{await refreshContext();if(revision!==routeVersion)return;view.replaceChildren();await ({overview:overview,equipment:equipmentPage,loans:loansPage,people:peoplePage,workshop:workshopPage,'checkout-cart':checkoutCartPage,imports:importsPage,labels:labelsPage,recovery:recoveryPage,system:systemPage})[current](revision);if(revision!==routeVersion)return;pendingBanner();view.focus({preventScroll:true})}catch(error){if(revision===routeVersion){view.replaceChildren();if(current==='labels'){labelWorkspace=null;labelWorkspaceChanged(null,'Could not load labels: '+(error.message||String(error)));toast('Could not load labels: '+(error.message||String(error)))}else{title('Could not load this page',error.message);view.append(button('Try loading again',()=>go(current,false),'main'),link('Open CACI-Create','/'))}}}}
listen('storage',()=>{if(context)refreshContext().catch(report)});
listen('focus',()=>{if(context&&!busy)refreshContext().then(()=>{if(current==='workshop'&&!document.hidden)return refreshWorkshopView(workshopEntityId,includeNested)}).catch(report)});
listen('beforeunload',e=>{if(layoutDirty||layoutUncertain||dialogDirty||busy||shelfNotesDirty||labelEditorDirty||labelEditorBusy){e.preventDefault();e.returnValue=''}});
const contextTimer=setInterval(()=>{if(context&&!busy)refreshContext().then(()=>{if(current==='workshop'&&!document.hidden)return refreshWorkshopView(workshopEntityId,includeNested)}).catch(()=>{})},30000);
async function inventoryData(){const identity=context?.identity;const values=await Promise.all([api('equipment'),api('locations'),api('loans')]);if(identity!==context?.identity)return;[equipment,locations,loans]=values;parents=[...locations,...equipment];}
function itemName(id){return equipment.find(e=>e.id===id)?.name||id}
function address(id){const parts=[],seen=new Set();let e=parents.find(e=>e.id===id);while(e&&!seen.has(e.id)){seen.add(e.id);parts.unshift(e.code||e.name);e=parents.find(p=>p.id===(e.parent_id||e.parent?.id))}return parts.join(' / ')||'Not assigned'}
function nativeNamePath(row){const parts=[],seen=new Set();let current=parents.find(item=>item.id===row.id)||row;while(current&&!seen.has(current.id)){seen.add(current.id);parts.unshift(current.name||'Unnamed native record');const parentId=current.parent_id||current.parent?.id;current=parentId?parents.find(item=>item.id===parentId):null}return parts.join(' / ')||row.name||'Unnamed native record'}
function held(id){return loans.find(l=>l.entity_id===id)}
function equipmentBlocker(item){return item.blocker||item.checkout_blocker||''}
function checkoutCartStatus(id){const item=equipment.find(row=>row.id===id);if(!item)return {item:null,reason:'Unavailable in this collection'};if(item.archived)return {item,reason:'Archived'};if(held(id))return {item,reason:'Checked out'};const blocker=equipmentBlocker(item);if(blocker)return {item,reason:blocker};if(item.quantity!==1)return {item,reason:'This workflow requires an individually tracked asset (quantity 1)'};if(item.condition!=='Ready')return {item,reason:'Condition: '+(item.condition||'Unreviewed')};return {item,reason:''}}
function checkoutCartReady(items){return items.length>0&&items.every(id=>!checkoutCartStatus(id).reason)}
function checkoutCartReadyItems(items){return items.filter(id=>!checkoutCartStatus(id).reason)}
async function loadCheckoutCart(){const identity=context?.identity,owner=scope(),cart=await api('checkout-cart',undefined,identity);if(identity!==context?.identity||owner!==scope())throw Error('The signed-in account changed. Reload the cart before continuing.');if(!cart||!Number.isSafeInteger(cart.revision)||cart.revision<0||!Array.isArray(cart.items))throw Error('The saved cart response is invalid. Refresh the cart before continuing.');return cart}
async function saveCheckoutCart(items,revision){if(busy)throw Error('Wait for confirmation to finish.');if(!Array.isArray(items)||items.length>50||new Set(items).size!==items.length)throw Error('Select up to 50 distinct equipment items.');const identity=context?.identity,owner=scope();busy=true;try{const cart=await api('checkout-cart',{items,revision,request_key:uuid()},identity);if(identity!==context?.identity||owner!==scope())throw Error('The signed-in account changed. Reload the cart before continuing.');return cart}finally{busy=false}}
async function checkoutCartPage(revision){await inventoryData();if(revision!==routeVersion)return;let state=await loadCheckoutCart();if(revision!==routeVersion)return;title('Checkout cart','Saved to your C-Crate account and collection. Finish checkout at the kiosk, where availability is checked again.',button('Refresh cart',()=>go('checkout-cart',false)));view.append(message('This cart does not reserve equipment or change custody. Checkout is completed at the kiosk after the borrower scans their badge and verifies the equipment.'));const content=node('div'),search=node('input');search.type='search';search.placeholder='Find equipment to addâ€¦';search.setAttribute('aria-label','Find equipment to add');view.append(search,content);
  async function update(items){state=await saveCheckoutCart(items,state.revision);paint()}
  function paint(){content.replaceChildren();const ready=checkoutCartReady(state.items),invalid=state.items.some(id=>checkoutCartStatus(id).reason);content.append(message(ready?'Every saved item is currently available for kiosk checkout. The kiosk will check availability again.':state.items.length?'Remove blocked or unavailable items before checkout at the kiosk.':'Your saved cart is empty. Add equipment below.','notice'));content.append(panel(node('h2','Saved items'),table(['Equipment','Asset code','Current availability','Action'],state.items.map(id=>{const status=checkoutCartStatus(id),item=status.item;return [item?.name||'Unavailable equipment Â· '+id,item?.assetId||'',status.reason||'Ready for kiosk checkout',button('Remove',()=>update(state.items.filter(value=>value!==id)))]}))));if(invalid)content.append(button('Remove unavailable or blocked items',()=>update(checkoutCartReadyItems(state.items)),'main'));const matches=equipment.filter(item=>!state.items.includes(item.id)&&[item.name,item.assetId].join(' ').toLowerCase().includes(search.value.toLowerCase()));content.append(panel(node('h2','Add equipment'),table(['Equipment','Asset code','Current availability','Action'],matches.map(item=>{const status=checkoutCartStatus(item.id),add=button('Add',()=>update([...state.items,item.id]));add.disabled=!!status.reason||state.items.length>=50;return [item.name,item.assetId||'',status.reason||'Ready',add]}))))}
  search.oninput=paint;paint()}
async function overview(revision){await inventoryData();const recover=manager()?await api('recovery'):[];if(revision!==routeVersion)return;title('Workshop overview','Start with equipment in use and work needing attention.');if(recover.length)view.append(message(`${recover.length} interrupted operation${recover.length===1?' needs':'s need'} review. Inspect saved outcomes before repeating changes or prints.`,'attention'));const split=node('div',null,'two'),loanPanel=panel(node('h2','Equipment in use')),reviewPanel=panel(node('h2','Before the next checkout'));for(const row of loans.slice(0,6)){const p=node('p');p.append(button(row.entity_name||itemName(row.entity_id),()=>showItem(row.entity_id,'loan')),node('small',row.borrower,'sub'));loanPanel.append(p)}if(!loans.length)loanPanel.append(node('p','No equipment is currently checked out.'));loanPanel.append(button('All loans & notes',()=>go('loans')));for(const e of equipment.filter(e=>e.blocker||e.condition&&e.condition!=='Ready').slice(0,6)){const p=node('p');p.append(button(e.name,()=>showItem(e.id)),node('small',e.blocker||e.condition,'sub'));reviewPanel.append(p)}reviewPanel.append(button('Browse equipment',()=>go('equipment')));split.append(loanPanel,reviewPanel);view.append(split)}
async function equipmentPage(revision){await inventoryData();if(revision!==routeVersion)return;title('Equipment','Native C-Crate inventory with borrowing and return context.',link('Manage inventory in C-Crate','/'));const tools=node('div',null,'tools'),search=node('input');search.setAttribute('aria-label','Search equipment');search.placeholder='Search name, asset code, storageâ€¦';search.value=equipmentQuery;search.oninput=()=>{equipmentQuery=search.value;paintEquipment()};tools.append(search);const controls=node('div',null,'toolbar'),filter=node('select');filter.setAttribute('aria-label','Equipment filter');for(const [v,n] of [['','All equipment'],['available','Available'],['loan','Checked out'],['blocked','Needs review'],['archived','Archived']])filter.append(new Option(n,v));filter.value=equipmentFilter;filter.onchange=()=>{equipmentFilter=filter.value;paintEquipment()};controls.append(filter,node('span',selection.size+' selected','count'));controls.querySelector('span').id='selection-count';if(manager())controls.append(button('Queue selected labels',()=>{if(!selection.size)throw Error('Select equipment first.');labelSelection=new Set(selection);go('labels')}));controls.append(button('Clear selection',()=>{selection.clear();paintEquipment()}));tools.append(controls);view.append(tools,node('div'));view.lastChild.id='equipment-table';paintEquipment()}
function paintEquipment(){const rows=equipment.filter(e=>(equipmentFilter==='archived'?e.archived:!e.archived)&&(equipmentFilter!=='loan'||held(e.id))&&(equipmentFilter!=='available'||!held(e.id)&&!equipmentBlocker(e))&&(equipmentFilter!=='blocked'||equipmentBlocker(e)||e.condition&&e.condition!=='Ready')&&[e.name,e.assetId,address(e.parent?.id)].join(' ').toLowerCase().includes(equipmentQuery.toLowerCase()));const body=rows.map(e=>{const cb=node('input');cb.type='checkbox';cb.checked=selection.has(e.id);cb.setAttribute('aria-label','Select '+e.name);cb.onchange=()=>{cb.checked?selection.add(e.id):selection.delete(e.id);root.querySelector('#selection-count').textContent=selection.size+' selected'};const name=node('div');name.append(button(e.name,()=>showItem(e.id),'name'),node('small',e.assetId,'sub'));const borrower=held(e.id),blocker=equipmentBlocker(e),custody=borrower?'With '+borrower.borrower:'Available',status=blocker?(borrower?custody+' Â· Blocked: '+blocker:'Blocked Â· '+blocker):custody;return [cb,name,address(e.parent?.id),tag(e.condition||'Unreviewed',e.condition==='Ready'&&!blocker?'ready':'warn'),tag(status,borrower?'loan':blocker?'warn':'')]});root.querySelector('#equipment-table').replaceChildren(table(['Select','Equipment','Assigned storage','Condition','Borrowing'],body));root.querySelector('#selection-count').textContent=selection.size+' selected'}
async function showItem(id,tab='summary'){navigate('/item/'+encodeURIComponent(id)+(tab==='summary'?'':'/loans'))}
async function itemTab(data,key){const target=root.querySelector('#item-content'),token=captureUi(),tabRevision=++itemTabVersion;if(!target)return;target.replaceChildren();dialogBody.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('active',b.textContent===({summary:'Summary',loan:'Loan',notes:'Return notes'})[key]));const e=data.entity;if(key==='summary'){target.append(node('p','Asset code: '+e.assetId),node('p','Assigned storage: '+address(e.parent?.id)),node('p','Condition: '+data.condition),node('p',data.blocker?'Checkout blocked: '+data.blocker:e.description||'No description'),link('Edit equipment in C-Crate','/item/'+encodeURIComponent(e.id)),link('Photos & maintenance in C-Crate','/item/'+encodeURIComponent(e.id)));if(manager())target.append(button('Review condition',()=>conditionDialog(data)),button('Preview equipment label',()=>previewLabel(e.id)));return}if(key==='loan'){const l=held(e.id);target.append(node('p',l?'Currently with '+l.borrower:'No current borrower.'),node('p','Assigned storage remains '+address(e.parent?.id)));if(l&&manager())target.append(button('Record administrative return',()=>returnDialog(e,l),'main'));return}const rows=await api('history?entity='+encodeURIComponent(e.id));if(!target.isConnected||!uiCurrent(token)||tabRevision!==itemTabVersion)return;const timeline=node('div',null,'timeline');for(const row of rows){for(const note of row.return_notes||[]){const a=node('article');a.append(node('p',note.text),node('small',note.author+' Â· '+timestamp(note.created_at)));timeline.append(a)}}if(!timeline.childNodes.length)timeline.append(node('p','No return notes recorded for this equipment.'));target.append(timeline)}
function conditionDialog(data){const form=node('div',null,'form');let state=data.condition;select(form,'Condition',data.states.map(v=>[v,v]),state,v=>state=v);form.append(node('p','Mark Ready only after physically checking the equipment.'),actions(button('Cancel',()=>closeDialog()),button('Confirm condition',async()=>{await write('condition',{entity_id:data.entity.id,state},'Change condition',data.entity.id);closeDialog(true);await go(current,false);toast('Condition saved in C-Crate.');},'main')));openDialog('Review condition: '+data.entity.name,form)}
async function loansPage(revision){await inventoryData();const historyRows=await api('history');if(revision!==routeVersion)return;title('Loans & notes','Current borrowing and the permanent return-note log.');const rows=loans.map(l=>[button(l.entity_name||itemName(l.entity_id),()=>showItem(l.entity_id,'loan')),l.borrower,address(equipment.find(e=>e.id===l.entity_id)?.parent?.id),manager()?button('Record return',()=>returnDialog(equipment.find(e=>e.id===l.entity_id)||{id:l.entity_id,name:l.entity_name},l)):'']);view.append(table(['Equipment','Borrower','Assigned storage','Action'],rows));const p=panel(node('h2','Return notes')),search=node('input');search.setAttribute('aria-label','Search return notes');search.placeholder='Search note, author, or equipmentâ€¦';const timeline=node('div',null,'timeline');p.append(search,timeline);function paint(){timeline.replaceChildren();let count=0;for(const row of historyRows){for(const n of row.return_notes||[]){const name=itemName(n.entity_id);if(![n.text,n.author,name].join(' ').toLowerCase().includes(search.value.toLowerCase()))continue;count++;const a=node('article');a.append(button(name,()=>showItem(n.entity_id,'notes')),node('p',n.text),node('small',n.author+' Â· '+timestamp(n.created_at)));timeline.append(a)}}if(!count)timeline.append(node('p','No return notes match.'))}search.oninput=paint;paint();view.append(p)}
async function returnDialog(e,loan){const token=captureUi();const [data,kit]=await Promise.all([api('entity?id='+e.id),api('kit?id='+e.id)]);if(!uiCurrent(token))return;const entities=kit.kit?kit.entities:[data.entity],form=node('div',null,'form'),notes={},verified=new Set();form.append(node('p','Borrower: '+loan.borrower),node('p','This return is attributed to signed-in manager '+context.user.name+'. Assigned storage and condition stay unchanged.'));for(const item of entities){form.append(node('h3',item.name));field(form,'Return note: '+item.name,'','textarea',v=>notes[item.id]=v);if(kit.kit)checkbox(form,'Physically verified: '+item.name,false,value=>value?verified.add(item.id):verified.delete(item.id))}form.append(actions(button('Cancel',()=>closeDialog()),button('Confirm administrative return',async()=>{if(kit.kit&&entities.some(item=>!verified.has(item.id)))throw Error('Verify every kit component before confirming.');await write('return',{targets:entities.map(item=>({entity_id:item.id,condition:null,destination_id:null,note:null,return_note:(notes[item.id]||'').trim()})),verified:[...verified],kit_versions:kit.versions||{}},'Administrative return',e.id);closeDialog(true);await go(current,false);toast('Return recorded with manager name and completion time.');},'main')));openDialog('Review administrative return',form)}
async function peoplePage(revision){[members,badges]=await Promise.all([api('people'),api('badges')]);if(revision!==routeVersion)return;title('People & badges','Native collection members and their personal kiosk badges.',button('Create invitation link',invitationDialog,'main'));view.append(message('Issue badges for the kiosk and allow staff to manage equipment from their computers. Users sign in to C-Crate with their own email and password.'));const search=node('input');search.setAttribute('aria-label','Search people');search.placeholder='Search name or emailâ€¦';const host=node('div');function paint(){host.replaceChildren(table(['Person','C-Crate email','Badge status','Actions'],members.filter(m=>[m.name,m.email].join(' ').toLowerCase().includes(search.value.toLowerCase())).map(m=>{const list=badges.filter(b=>b.user_id===m.id),active=list.filter(b=>!b.revoked),a=node('div',null,'toolbar');a.append(button('Issue badge',()=>issueBadgeDialog(m)));if(m.id!==context.user.id)a.append(button(m.workshop_manager?'Remove management access':'Allow management',()=>permissionDialog(m)));for(const b of active)a.append(button('Revoke badge',()=>revokeBadgeDialog(m,b)));return [m.name,m.email||'',active.length+' active Â· '+list.filter(b=>b.revoked).length+' revoked',a]})))}search.oninput=paint;paint();view.append(search,host)}
function permissionDialog(member){const enabled=!member.workshop_manager;openDialog((enabled?'Allow management for ':'Remove management access for ')+member.name,node('p',enabled?'This person can manage badges, labels, imports, storage and recovery using their own C-Crate account.':'This person will retain their C-Crate inventory account and kiosk badge.'),actions(button('Cancel',()=>closeDialog()),button('Confirm management access',async()=>{await write('permissions/set',{user_id:member.id,enabled},'Update management access',member.id);closeDialog(true);await go('people',false);toast('Management access updated.');},'main')))}
function invitationDialog(){const form=node('div');form.append(node('p','Create a single-use C-Crate invitation for '+context.group.name+'. Share the link with the person so they choose their own password. No email is sent automatically.'),actions(button('Cancel',()=>closeDialog()),button('Confirm invitation link',async()=>{const data=await write('invitation/create',{uses:1},'Create invitation');dialogDirty=false;dialogBody.replaceChildren(node('p',data.message||'Share this single-use link privately.'));if(data.join_url){const input=node('input');input.readOnly=true;input.value=new URL(data.join_url,location.origin).href;input.setAttribute('aria-label','Invitation link');dialogBody.append(input,button('Select link',()=>{input.select();toast('Copy the selected invitation link.')}))}else dialogBody.append(node('p','The link is available only in its initial response. Use native C-Crate invitation management if recovery is needed.'));},'main')));openDialog('Invite a C-Crate member',form)}
function issueBadgeDialog(member){openDialog('Issue badge for '+member.name,node('p','Owner: '+member.name+' Â· '+(member.email||'')),node('p','The QR code is shown once after issuance. Keep it private. Printing is a separate action.'),actions(button('Cancel',()=>closeDialog()),button('Confirm badge issuance',async()=>{const data=await write('badges/issue',{user_id:member.id},'Issue badge',member.id);dialogDirty=false;dialogBody.replaceChildren(node('p','Badge owner: '+member.name));if(data.qr&&data.code){const img=node('img');img.src=data.qr;img.alt='New personal badge for '+member.name;img.className='badge-qr';dialogBody.append(img,node('p','Destination: Pi label printer. Check printer stock before printing.'),button('Confirm: print one badge on Pi',async()=>{await write('badges/print',{badge_id:data.id,code:data.code},'Print badge',data.id);toast('Pi printer confirmed badge completion. Inspect the physical label.');},'main'))}else dialogBody.append(node('p',data.message||'Badge issued. Its private QR code cannot be recovered from a list.'));},'main')))}
function revokeBadgeDialog(member,badge){openDialog('Revoke badge for '+member.name,node('p','This badge will stop identifying '+member.name+'. Revocation also ends affected badge sessions.'),actions(button('Cancel',()=>closeDialog()),button('Confirm revocation',async()=>{await write('badges/revoke',{id:badge.id},'Revoke badge',badge.id);closeDialog(true);await go('people',false);toast('Badge revoked.');},'main')))}
async function labelsPage(revision){
  await inventoryData(); if(revision!==routeVersion)return;
  const key=scope(),identity=context?.identity; if(labelQueues.has(key))labelSelection=new Set(labelQueues.get(key)); else labelSelection=new Set();
  let reviewRevision=0,paperRevision=0,paperCurrent=()=>false;
  labelTemplates=await api('labels/templates',undefined,identity); if(revision!==routeVersion||identity!==context?.identity)return;
  const selection=[...labelSelection],items=equipment.filter(item=>!item.archived).map(item=>({id:item.id,name:item.name,assetId:item.assetId||'',shortCode:item.shortCode||'',displayId:item.displayId||''}));
  labelWorkspace={items,templates:labelTemplates,selectedIds:selection,templateId:labelTemplates[0]?.id||'',marginMm:10,gapMm:3,reviews:[],printedReviewIds:[],pages:[],paper:null,pendingActions:0,printError:'',printUncertain:false,printLocked:false,busy:false,actions:{}};
  labelWorkspace=labelWorkspaceChanged(labelWorkspace)||labelWorkspace;
  const workspace=labelWorkspace;
  let queueStopped=pendingLabelPrint(pending()),queueSending=false;
  workspace.printLocked=queueStopped;
  if(queueStopped){workspace.printUncertain=true;workspace.printError='A label print from an earlier session has no confirmed result. Check Recovery and inspect the physical label before retrying.'}
  function clearPaper(){paperRevision++;workspace.pages=[];workspace.paper=null;paperCurrent=()=>false;}
  function clearReviews(){reviewRevision++;labelReviews=null;labelReviewIds=[];workspace.reviews=[];workspace.printedReviewIds=[];clearPaper();}
  workspace.actions={
    select(ids){labelSelection=new Set(ids);workspace.selectedIds=[...ids];labelQueues.set(key,[...ids]);clearReviews()},
    template(id){workspace.templateId=id;clearReviews()},
    layout(margin,gap){workspace.marginMm=margin;workspace.gapMm=gap;clearPaper()},
    async review(){if(!labelSelection.size)throw Error('Select at least one item.');const chosen=labelTemplates.find(t=>t.id===workspace.templateId);if(!chosen)throw Error('Choose a label template.');const token=captureUi(),ids=Array.from(labelSelection),version=++reviewRevision;workspace.busy=true;try{const result=await api('labels/preview',{mode:'item',entity_ids:ids,template_id:chosen.id,template_revision:chosen.revision},identity);if(!uiCurrent(token)||identity!==context?.identity||version!==reviewRevision||ids.join('|')!==Array.from(labelSelection).join('|')||chosen.id!==workspace.templateId)return;const reviews=result.reviews|| (result.review_id?[result]:[]);if(reviews.length!==ids.length)throw Error('The complete label preview was not returned. Review the selected items again.');labelReviews=result;labelReviewIds=ids;workspace.reviews=reviews.map((row,index)=>({...row,entity_id:ids[index]}))}finally{workspace.busy=false}},
    printItem(entityId,reviewId){const version=reviewRevision,identityAtReview=context?.identity;let attempted=false;const currentRow=workspace.reviews.find(row=>row.entity_id===entityId&&row.review_id===reviewId);if(!labelReviews||!labelReviewIds.includes(entityId)||!currentRow||workspace.printedReviewIds.includes(reviewId))throw Error('Review the current selection again before printing.');if(queueStopped||queueSending)throw Error('This queue is stopped. Inspect Recovery before another print.');workspace.printError='';workspace.printUncertain=false;openDialog('Confirm Pi label print',node('p','Print the reviewed label for '+itemName(entityId)+' on the workshop Pi printer?'),actions(button('Cancel',()=>closeDialog()),button('Confirm one Pi print',async()=>{if(version!==reviewRevision||identityAtReview!==context?.identity)throw Error('Review the current selection again before printing.');if(attempted||workspace.printedReviewIds.includes(reviewId)||queueStopped||queueSending)throw Error('This label was already submitted or the queue stopped.');attempted=true;queueSending=true;workspace.busy=true;const requestKey=uuid();try{await write('labels/print',{entity_id:entityId,review_id:reviewId,request_key:requestKey},'Print item label',entityId);if(version!==reviewRevision||identityAtReview!==context?.identity)return;workspace.printedReviewIds.push(reviewId);workspace.printError='';closeDialog(true);toast('Pi printer confirmed this request. Inspect the physical label.')}catch(error){const state=labelPrintFailure(error,pending(),requestKey);queueStopped=state.locked;workspace.printLocked=state.locked;workspace.printUncertain=state.uncertain;workspace.printError=state.message;closeDialog(true);if(state.uncertain)toast('Print outcome is uncertain. Check Recovery and inspect the physical label before retrying.')}finally{queueSending=false;workspace.busy=false;workspace.pendingActions=pending().length}},'main')))},
    async compose(){const rows=labelReviews?.reviews||[];if(!rows.length)throw Error('Review the selected items first.');if(rows.some(r=>r.profile!=='letter'))throw Error('Paper sheets require Letter reviewed labels.');const ids=[...labelReviewIds],version=reviewRevision,token=captureUi(),paperVersion=++paperRevision,geometry={page_mm:[215.9,279.4],label_mm:[...(rows[0].label_mm||[])],margin_mm:workspace.marginMm,gap_mm:workspace.gapMm,cut_guides:true};if(geometry.label_mm.length!==2||rows.some(row=>row.label_mm?.join('|')!==geometry.label_mm.join('|')))throw Error('Reviewed labels have different physical dimensions. Review a matching template.');const isCurrent=()=>uiCurrent(token)&&identity===context?.identity&&version===reviewRevision&&paperVersion===paperRevision&&ids.join('|')===Array.from(labelSelection).join('|');paperCurrent=isCurrent;workspace.busy=true;try{const result=await api('labels/paper',{review_ids:rows.map(r=>r.review_id),geometry});if(!uiCurrent(token)||version!==reviewRevision||paperVersion!==paperRevision||ids.join('|')!==Array.from(labelSelection).join('|')||labelReviews?.reviews!==rows)return;workspace.paper=result;workspace.pages=result.pages||[]}finally{workspace.busy=false}},
    async printPages(){if(!workspace.paper?.pages?.length||!paperCurrent())throw Error('Compose the current reviewed sheet before printing.');workspace.busy=true;try{toast(await exportReviewedPaper('/workshop-api/label-assets/render.html',workspace.paper,'print',paperCurrent))}finally{workspace.busy=false}},
    async downloadPdf(){if(!workspace.paper?.pages?.length||!paperCurrent())throw Error('Compose the current reviewed sheet before downloading.');workspace.busy=true;try{toast(await exportReviewedPaper('/workshop-api/label-assets/render.html',workspace.paper,'pdf',paperCurrent))}finally{workspace.busy=false}},
    designer(handle){labelEditor=handle;},
    designerDirty(value){const saved=labelEditorDirty&&!value;labelEditorDirty=value;if(saved){const savedContext=context?.identity,saveToken=captureUi();api('labels/templates',undefined,identity).then(rows=>{if(!uiCurrent(saveToken)||savedContext!==context?.identity)return;labelTemplates=rows;workspace.templates=rows;workspace.templateId='';clearReviews()}).catch(error=>toast(error?.message||String(error)))}},
    designerBusy(value){labelEditorBusy=value;workspace.busy=value;if(!value)workspace.pendingActions=pending().length;},
    recovery(){navigate('/workshop/recovery')}
  };
  for(const name of ['review','printItem','compose','printPages','downloadPdf']){const action=workspace.actions[name];workspace.actions[name]=(...args)=>Promise.resolve().then(()=>action(...args)).catch(error=>toast(error?.message||String(error)))}
}
async function previewLabel(id){const token=captureUi(),name=itemName(id);const p=await api('labels/preview',{entity_id:id});if(!uiCurrent(token))return;const img=node('img');img.src=p.image;img.alt='Actual label preview for '+name;img.className='label-image';openDialog('Label preview',node('p',name),img,node('p','Loaded stock: '+(p.width||'?')+' Ã— '+(p.height||'?')+' pixels. Output is sent only after a separate print confirmation.'))}
function printDialog(items){const form=node('div'),progress=node('p'),completed=new Set();let uncertain=false;const confirm=button('Confirm print on Pi',async()=>{if(uncertain)throw Error('This queue is interrupted. Check Recovery before continuing.');try{for(const e of items.filter(item=>!completed.has(item.id))){progress.textContent='Printing '+e.name+'â€¦';await write('labels/print',{entity_id:e.id},'Print equipment label',e.id);completed.add(e.id);labelSelection.delete(e.id)}closeDialog(true);await go('labels',false);toast('Printer confirmed completion. Inspect the labels.');}catch(error){uncertain=true;confirm.disabled=true;confirm.textContent='Queue stopped â€” check Recovery';form.append(button('Open Recovery',()=>{closeDialog(true);go('recovery')}));throw error}},'main');form.append(node('p',items.length+' equipment labels will print on the Pi label printer.'),node('p',items.map(e=>e.name).join(', ')),node('p','Check stock and inspect physical output if an operation is interrupted.'),progress,actions(button('Cancel',()=>closeDialog()),confirm));openDialog('Confirm Pi print job',form)}
function plannerSessionKey(){if(!context)return'';const base=`workshop-room-draft:${scope()}`;if(!plannerTabToken){try{plannerTabToken=sessionStorage.getItem('workshop-room-draft-tab');if(!plannerTabToken){plannerTabToken=uuid();sessionStorage.setItem('workshop-room-draft-tab',plannerTabToken)}}catch{plannerTabToken=uuid()}}const key=`${base}:${plannerTabToken}`;if(!localStorage.getItem(key)){const legacy=localStorage.getItem(base);if(legacy){const claim=`${base}:migration`,owner=localStorage.getItem(claim);if(!owner||!localStorage.getItem(`${base}:${owner}`)){localStorage.setItem(claim,plannerTabToken);if(localStorage.getItem(claim)===plannerTabToken&&!localStorage.getItem(key)){localStorage.setItem(key,legacy);localStorage.removeItem(base);localStorage.removeItem(claim)}}}}return key}
function persistPlannerSession(){if(!context||!layoutDraft)return;try{localStorage.setItem(plannerSessionKey(),JSON.stringify({identity:context.identity,group_id:context.group.id,user_id:context.user.id,revision:layoutState?.revision??0,dirty:layoutDirty,document:layoutDraft,room_id:activeRoomId,drawing_id:layoutSelected,selectedDrawingByRoom,undo:Object.fromEntries(roomUndo),redo:Object.fromEntries(roomRedo),uncertain:layoutUncertain}))}catch{toast('The room draft could not be stored on this device. Save it before leaving this page.')}}
function removePlannerSession(){if(context)localStorage.removeItem(plannerSessionKey())}
function currentRoom(){return layoutDraft?.rooms.find(room=>room.id===activeRoomId)||null}
function roomIndex(roomId){return layoutDraft?.rooms.findIndex(room=>room.id===roomId)??-1}
function docDirty(){layoutDirty=!!layoutDraft&&JSON.stringify(layoutDraft)!==JSON.stringify(layoutState?.document||{version:2,rooms:[]});persistPlannerSession()}
function ensureRoomHistory(rooms){for(const room of rooms){if(!roomUndo.has(room.id))roomUndo.set(room.id,[]);if(!roomRedo.has(room.id))roomRedo.set(room.id,[])}}
function createEmptyRoom(){if(!canEditPlan())return;if(layoutDraft.rooms.length>=20)throw Error('A workshop plan can contain at most 20 rooms.');const room={id:uuid(),location_id:null,name:'New room',width:20,height:16,unit:'ft',approximate:false,objects:[]};layoutDraft.rooms.push(room);activeRoomId=room.id;layoutSelected=null;roomSettingsShown=false;selectedDrawingByRoom[room.id]=null;ensureRoomHistory([room]);docDirty();syncRoomUrl();workshopPaint()}
function clearWorkshopView(){plannerCanvasObserver?.disconnect();plannerCanvasObserver=null;const banner=view.querySelector('.pending-banner');view.replaceChildren();if(banner)view.append(banner)}
async function workshopPage(revision){
  layoutState=await api('workshop');
  if(revision!==routeVersion)return;
  locations=layoutState.locations||[];parents=layoutState.parents||locations;types=layoutState.types||[];
  const stored=(()=>{try{return JSON.parse(localStorage.getItem(plannerSessionKey())||'null')}catch{return null}})();
  const validStored=stored&&stored.identity===context.identity&&stored.group_id===context.group.id&&stored.user_id===context.user.id&&stored.document?.version===2&&Array.isArray(stored.document.rooms);
  const pendingSave=workshop.pending().find(row=>row.path==='workshop/save'&&row.identity===context.identity&&row.group_id===context.group.id&&row.user_id===context.user.id&&row.intent?.schema_version===2&&validStored&&(stored.uncertain?.key===row.key||stored.revision===row.intent.revision&&JSON.stringify(stored.document)===JSON.stringify(row.intent.document)));
  if(validStored&&stored.dirty)layoutState={...layoutState,revision:stored.revision};
  layoutDraft=validStored&&stored.dirty?clone(stored.document):clone(layoutState.document||{version:2,rooms:[]});
  layoutUncertain=validStored?stored.uncertain||null:null;
  if(pendingSave){layoutUncertain={key:pendingSave.key,revision:pendingSave.intent.revision,document:clone(pendingSave.intent.document)};if(!stored.dirty)layoutDraft=clone(pendingSave.intent.document)}
  selectedDrawingByRoom=validStored?stored.selectedDrawingByRoom||{}:{};
  const keepStoredHistory=validStored&&(stored.dirty||stored.revision===layoutState.revision);
  roomUndo=new Map(Object.entries(keepStoredHistory?stored.undo||{}:{}));roomRedo=new Map(Object.entries(keepStoredHistory?stored.redo||{}:{}));
  ensureRoomHistory(layoutDraft.rooms);
  const requestedRoom=initialSelection.roomId,remembered=validStored?stored.room_id:null,requestedDrawing=initialSelection.drawingId;
  activeRoomId=requestedRoom&&layoutDraft.rooms.some(room=>room.id===requestedRoom)?requestedRoom:requestedRoom?null:(remembered&&layoutDraft.rooms.some(room=>room.id===remembered)?remembered:null);
  if(!requestedRoom&&!activeRoomId&&requestedDrawing){const match=layoutDraft.rooms.find(room=>room.objects.some(object=>object.id===requestedDrawing));if(match)activeRoomId=match.id}
  if(!requestedRoom&&!activeRoomId&&layoutDraft.rooms.length)activeRoomId=layoutDraft.rooms[0].id;
  roomChooserMessage=requestedRoom&&!activeRoomId?'This room bookmark is no longer available. Choose a room to continue.':!requestedRoom&&requestedDrawing&&!layoutDraft.rooms.some(room=>room.objects.some(object=>object.id===requestedDrawing))?'This drawing bookmark is no longer available. Choose a room to continue.':'';
  layoutSelected=activeRoomId?(selectedDrawingByRoom[activeRoomId]||null):null;
  if(requestedDrawing){const targetRoom=layoutDraft.rooms.find(room=>room.objects.some(object=>object.id===requestedDrawing));if(targetRoom&&(!requestedRoom||targetRoom.id===requestedRoom)){activeRoomId=targetRoom.id;layoutSelected=requestedDrawing;selectedDrawingByRoom[targetRoom.id]=requestedDrawing;roomChooserMessage=''}else if(requestedRoom){layoutSelected=null;roomChooserMessage=targetRoom?'This drawing is not available in the requested room. Choose a drawing or room to continue.':'This drawing bookmark is no longer available.'}else{layoutSelected=null;roomChooserMessage='This drawing bookmark is no longer available.'}}
  if(activeRoomId&&layoutSelected&&!layoutDraft.rooms.find(room=>room.id===activeRoomId)?.objects.some(object=>object.id===layoutSelected)){layoutSelected=null;selectedDrawingByRoom[activeRoomId]=null}
  const bookmarkedDrawing=layoutDraft.rooms.find(room=>room.id===activeRoomId)?.objects.find(object=>object.id===layoutSelected);if(!workshopEntityId&&bookmarkedDrawing?.location_id)workshopEntityId=bookmarkedDrawing.location_id;
  docDirty();if(roomChooserMessage&&(requestedRoom||requestedDrawing)){workshopEntityId=null;workshopView=null;workshopViewAvailable=false;workshopViewError='';workshopSelectedStatus=null;workshopPaint();return}workshopPaint();await refreshWorkshopView(workshopEntityId,false)
}
async function refreshWorkshopView(entityId=null,nested=false,acrossRooms=workshopViewAcrossRooms){
  if(busy){workshopRefreshSkipped=true;return;}
  workshopViewAcrossRooms=!!acrossRooms;
  const requested=entityId||null,identity=context?.identity,token=++workshopReadToken;
  workshopEntityId=requested;includeNested=!!nested;
  try{
    const latestLayout=await api('workshop');
    if(token!==workshopReadToken||identity!==context?.identity||current!=='workshop')return;
    if(busy){workshopRefreshSkipped=true;return;}
    const previousState=layoutState,pendingInspectorEdit=plannerPendingInspectorLabels.size>0||plannerInspectorInputRevision!==plannerInspectorCommittedRevision||!!view.querySelector('.planner-inspector input:focus,.planner-inspector select:focus,.planner-inspector textarea:focus'),preserveDraft=layoutDirty||pendingInspectorEdit;
    if(!preserveDraft&&previousState&&latestLayout.revision!==previousState.revision){roomUndo.clear();roomRedo.clear()}
    layoutState=preserveDraft&&previousState?{...latestLayout,document:previousState.document,revision:previousState.revision}:latestLayout;
    layoutDraft=preserveDraft?layoutDraft:clone(latestLayout.document||{version:2,rooms:[]});
    locations=layoutState.locations||[];parents=layoutState.parents||locations;types=layoutState.types||[];
    const roomQuery=activeRoomId&&!acrossRooms?'&room_id='+encodeURIComponent(activeRoomId):'';
    const result=await api('workshop/view?id='+encodeURIComponent(requested||'')+'&nested='+(includeNested?'1':'0')+roomQuery,undefined,identity);
    if(token!==workshopReadToken||identity!==context?.identity||current!=='workshop')return;
    if(busy){workshopRefreshSkipped=true;return;}
    workshopSelectedStatus=result.selection_status??null;
    const selected=result.path?.at(-1),selectedRecord=parents.find(row=>row.id===requested),isSelectedLocation=!!selected?.is_location||!!selectedRecord?.isLocation||!!selectedRecord?.entityType?.isLocation;
    if(result.selection_status===undefined&&requested&&!isSelectedLocation&&!result.contents?.some(row=>row.id===requested)){
      const [detail,loanRows]=await Promise.all([api('entity?id='+encodeURIComponent(requested)),api('loans')]);
      if(token!==workshopReadToken||identity!==context?.identity||current!=='workshop')return;
      if(busy){workshopRefreshSkipped=true;return;}
      workshopSelectedStatus={entity:detail.entity,condition:detail.condition,blocker:detail.blocker,checked_out:loanRows.some(row=>row.entity_id===requested)};
    }
    workshopRefreshSkipped=false;workshopView=result;workshopViewAvailable=true;workshopViewError='';workshopEntityId=result.selection?.target_id||requested;
    if(browseMode==='edit'&&(layoutDirty||plannerPendingInspectorLabels.size>0||plannerInspectorInputRevision!==plannerInspectorCommittedRevision||view.querySelector('.planner-inspector input:focus,.planner-inspector select:focus,.planner-inspector textarea:focus')))return;
    const matches=result.selection?.matches||[],preferred=matches.find(row=>row.drawing_id===initialSelection.drawingId);
    if(preferred){layoutSelected=preferred.drawing_id;if(preferred.room_id&&layoutDraft.rooms.some(room=>room.id===preferred.room_id))activeRoomId=preferred.room_id}
    else if(matches.length===1){layoutSelected=matches[0].drawing_id;if(matches[0].room_id&&layoutDraft.rooms.some(room=>room.id===matches[0].room_id))activeRoomId=matches[0].room_id}
    else if(acrossRooms||requested){layoutSelected=null;if(activeRoomId)selectedDrawingByRoom[activeRoomId]=null}
    if(activeRoomId)selectedDrawingByRoom[activeRoomId]=layoutSelected;
    if(!preserveDraft)ensureRoomHistory(layoutDraft.rooms);
    repaintWorkshopPreservingInspectorInput();
  }catch(error){
    if(token!==workshopReadToken||identity!==context?.identity||current!=='workshop')return;
    if(busy){workshopRefreshSkipped=true;return;}
    workshopView=null;workshopViewAvailable=false;workshopSelectedStatus=null;workshopViewError=error.message||'Status unavailable';
    if(browseMode==='edit'&&(layoutDirty||plannerPendingInspectorLabels.size>0||plannerInspectorInputRevision!==plannerInspectorCommittedRevision||view.querySelector('.planner-inspector input:focus,.planner-inspector select:focus,.planner-inspector textarea:focus')))return;
    repaintWorkshopPreservingInspectorInput();
  }
}
function repaintWorkshopPreservingInspectorInput(){const active=document.activeElement,label=active?.closest?.('.planner-inspector [aria-label]')?.getAttribute('aria-label'),value=label&&'value'in active?active.value:null,start=label&&typeof active.selectionStart==='number'?active.selectionStart:null,end=label&&typeof active.selectionEnd==='number'?active.selectionEnd:null;workshopPaint();if(!label)return;const replacement=[...view.querySelectorAll('.planner-inspector [aria-label]')].find(control=>control.getAttribute('aria-label')===label);if(!replacement)return;if(value!==null)replacement.value=value;replacement.focus();if(start!==null&&typeof replacement.setSelectionRange==='function')replacement.setSelectionRange(start,end)}
async function selectWorkshopEntity(entityId,acrossRooms=false){
  if(disposed||busy||current!=='workshop'||!context||typeof entityId!=='string'||!entityId)return;
  workshopSelectionGeneration++;
  const identity=context.identity,owner=scope(),route=routeVersion,selectionGeneration=workshopSelectionGeneration,url=new URL(location.href),routeChanges=url.pathname==='/workshop/map'&&(url.searchParams.get('id')!==entityId||url.searchParams.has('drawing_id')),previousAcrossRooms=workshopViewAcrossRooms;
  acrossRoomRouteSelection=routeChanges&&acrossRooms?{entityId,identity,owner,generation:selectionGeneration}:null;
  if(routeChanges){
    if(acrossRooms)workshopViewAcrossRooms=true;
    url.searchParams.set('id',entityId);url.searchParams.delete('drawing_id');
    try{await navigate(url.pathname+url.search,true)}catch(error){if(acrossRoomRouteSelection?.entityId===entityId){acrossRoomRouteSelection=null;workshopViewAcrossRooms=previousAcrossRooms}throw error}
    if(disposed||current!=='workshop'||route!==routeVersion||context?.identity!==identity||scope()!==owner){if(acrossRoomRouteSelection?.entityId===entityId)acrossRoomRouteSelection=null;return}
    if(selectionGeneration===workshopSelectionGeneration)await updateWorkshopSelection({entityId,drawingId:null,roomId:initialSelection.roomId});
    return;
  }
  initialSelection.entityId=entityId;initialSelection.drawingId=null;
  if(disposed||current!=='workshop'||route!==routeVersion||context?.identity!==identity||scope()!==owner||selectionGeneration!==workshopSelectionGeneration){if(acrossRoomRouteSelection?.entityId===entityId)acrossRoomRouteSelection=null;return}
  await refreshWorkshopView(entityId,includeNested,acrossRooms||workshopViewAcrossRooms);
}
async function updateWorkshopSelection(next){const selection={entityId:next.entityId||null,drawingId:next.drawingId||null,roomId:next.roomId||null};if(busy||deferredWorkshopSelection){deferWorkshopSelection(selection);return}return applyWorkshopSelection(selection)}
function resolvePlannerBookmark(roomId,drawingId){const requestedRoom=roomId?roomById(roomId):null,targetRoom=drawingId?layoutDraft?.rooms.find(room=>room.objects.some(object=>object.id===drawingId)):null;if(roomId&&!requestedRoom)return{roomId:null,drawingId:null,message:'This room bookmark is no longer available. Choose a room to continue.'};if(drawingId&&!targetRoom)return{roomId:requestedRoom?.id||activeRoomId||layoutDraft?.rooms[0]?.id||null,drawingId:null,message:'This drawing bookmark is no longer available.'};if(targetRoom&&requestedRoom&&targetRoom.id!==requestedRoom.id)return{roomId:requestedRoom.id,drawingId:null,message:'This drawing is not available in the requested room. Choose a drawing or room to continue.'};const room=targetRoom||requestedRoom||roomById(activeRoomId)||layoutDraft?.rooms[0]||null;return{roomId:room?.id||null,drawingId:targetRoom?drawingId:null,message:''}}
async function applyWorkshopSelection(next){const entityId=next.entityId||null,drawingId=next.drawingId||null,roomId=next.roomId||null,entityChanged=entityId!==initialSelection.entityId,drawingChanged=drawingId!==initialSelection.drawingId,roomChanged=roomId!==initialSelection.roomId,routeScope=acrossRoomRouteSelection,acrossRooms=!!routeScope&&routeScope.entityId===entityId&&routeScope.identity===context?.identity&&routeScope.owner===scope()&&routeScope.generation===workshopSelectionGeneration;if(routeScope)acrossRoomRouteSelection=null;if(!entityChanged&&!drawingChanged&&!roomChanged)return;if(drawingChanged||roomChanged)workshopViewAcrossRooms=false;if(acrossRooms)workshopViewAcrossRooms=true;workshopSelectionGeneration++;if(activeRoomId&&layoutSelected)selectedDrawingByRoom[activeRoomId]=layoutSelected;const resolved=resolvePlannerBookmark(roomId,drawingId);activeRoomId=resolved.roomId;roomChooserMessage=resolved.message;if(resolved.drawingId){layoutSelected=resolved.drawingId;selectedDrawingByRoom[activeRoomId]=layoutSelected}else if(drawingId||roomChanged){layoutSelected=roomChanged&&!drawingId?(selectedDrawingByRoom[activeRoomId]||null):null;if(layoutSelected&&!roomById(activeRoomId)?.objects.some(object=>object.id===layoutSelected))layoutSelected=null}initialSelection.entityId=entityId;initialSelection.drawingId=drawingId;initialSelection.roomId=roomId;if(resolved.message){workshopEntityId=null;workshopView=null;workshopViewAvailable=false;workshopViewError='';workshopSelectedStatus=null;workshopPaint();return}const selectedObject=roomById(activeRoomId)?.objects.find(object=>object.id===layoutSelected),targetId=entityId||selectedObject?.location_id||null;if(targetId){workshopEntityId=targetId;await refreshWorkshopView(targetId,includeNested,workshopViewAcrossRooms);return}workshopEntityId=null;workshopView=null;workshopViewAvailable=false;workshopViewError='';workshopSelectedStatus=null;workshopPaint()}
function svgNode(tag,attrs,text){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs||{}))e.setAttribute(key,value);if(text)e.textContent=text;return e}
function roomById(id){return layoutDraft?.rooms.find(room=>room.id===id)||null}
function saveRoomHistory(roomId,snapshot){const stack=roomUndo.get(roomId)||[];stack.push({type:'snapshot',snapshot});if(stack.length>60)stack.shift();roomUndo.set(roomId,stack);roomRedo.set(roomId,[]);persistPlannerSession()}
function recordRoom(roomId=activeRoomId,snapshot=null){const room=roomById(roomId);if(room)saveRoomHistory(roomId,snapshot||clone(room))}
function markPlannerDirty(){docDirty();const status=view.querySelector('[data-room-save-state]');if(status)status.textContent=layoutUncertain?'Save result needs checking':layoutDirty?'Unsaved room changes':'All room changes saved';const save=view.querySelector('[aria-label="Save all room changes"]');if(save)save.disabled=!layoutDirty||!!layoutUncertain||!manager()}
function validateRoom(room){if(!room.name.trim()||room.name.length>120||room.width<4||room.width>200||room.height<4||room.height>200)throw Error('Use a room title and dimensions from 4 to 200 feet.');for(const object of room.objects){if(object.x<0||object.y<0||object.width<.1||object.height<.1||object.x+object.width>room.width||object.y+object.height>room.height)throw Error('Room dimensions must contain every drawing.')}}
const plannerKinds=['Wall','Bin','Crate','Drawer','Misc','Custom'];
function validateObject(room,object){if(!object.name.trim()||object.name.length>120||!([...layoutState.types,...plannerKinds].includes(object.kind))||![object.x,object.y,object.width,object.height].every(Number.isFinite)||object.width<.1||object.height<.1||object.x<0||object.y<0||object.x+object.width>room.width||object.y+object.height>room.height||![0,90,180,270].includes(o9ãKh‘éì¶»§q«^t]\›•[š]Îˆ	Ý\Ù\”ÜXÙSÛ•\ÙIÈJNÂˆ]\›‹˜\[™
Ý™Ó›ÙJ	Ü]	ËÈˆ	ÓHŒHŒIËš[ˆ	Û›Û™IËÝ›ÚÙNˆ	ÚÛ
˜\ŠKX›Ü™\ŠJIË	ÜÝ›ÚÙK]ÚY	ÎˆŒLˆJJNÂˆYœË˜\[™
]\›ŠNÂˆÛÛœÝX›Ý™T]\›\Ý™Ó›ÙJ	Ü]\›‰ËÚY‰Ü[›™\‹\Ýš\KXX›Ý™IËÚY‹ŒŒ‹ZYÚ‹ŒŒ‹]\›•[š]Î‰Ý\Ù\”ÜXÙSÛ•\ÙIßJNØX›Ý™T]\›‹˜\[™
Ý™Ó›ÙJ	Ü]	ËÙ‰ÓHŒLHŒŒ‰ËÝ›ÚÙN‰ÈÙ™™™™™‰Ë	ÜÝ›ÚÙK]ÚY	Î‹ŒKÜXÚ]N‹ŽJJNØÛÛœÝ™[ÝÔ]\›\Ý™Ó›ÙJ	Ü]\›‰ËÚY‰Ü[›™\‹\Ýš\KX™[ÝÉËÚY‹ŒŒ‹ZYÚ‹ŒŒ‹]\›•[š]Î‰Ý\Ù\”ÜXÙSÛ•\ÙIßJNØ™[ÝÔ]\›‹˜\[™
Ý™Ó›ÙJ	Ü]	ËÙ‰ÓHKŒHŒHŒMÈŒÈHŒˆKŒˆŒŽŒM‰ËÝ›ÚÙN‰ÈÌLLNÉË	ÜÝ›ÚÙK]ÚY	Î‹ŒÜXÚ]N‹ßJJNÙYœË˜\[™
X›Ý™T]\›‹™[ÝÔ]\›ŠNÜ[‹˜\[™
YœÊNÂˆ[‹˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÂˆˆNˆÚYˆ›ÛÛKÚYZYÚˆ›ÛÛKšZYÚˆš[ˆ[›™\‘ÜšYÈ	Ý\›
Ü[›™\‹YÜšY
IÈˆ	ÚÛ
˜\ŠKX˜XÚÙÜ›Ý[™
JIËˆÝ›ÚÙNˆ	ÚÛ
˜\ŠKY›Ü™YÜ›Ý[™
JIË	ÜÝ›ÚÙK]ÚY	ÎˆŒ‹ˆJJNÂˆ[‹˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÈˆNˆÚYˆ›ÛÛKÚYZYÚˆ›ÛÛKšZYÚš[ˆ	Ý˜[œÜ\™[	ËÝ›ÚÙNˆ	Û›Û™IË	Ù]K\›ÛÛK\Ý\™˜XÙIÎˆ	ÝYIÈJJNÂˆ›Üˆ
ÛÛœÝØš™XÝÙˆË‹‹œ›ÛÛK›Øš™XÝ×KœÛÜ

KŠOOŠK›^Y\OOIØ™[ÝÉÏÌŒJKJ‹›^Y\OOIØ™[ÝÉÏÌŒJJJHÂˆÛÛœÝÚ\RÚ[™JØš™XÝšÚ[™
ÉÈ	ÊÛØš™XÝ›˜[YJKÓÝÙ\Ø\ÙJ
KÚ[ÝY]OKÜÚ[Ÿ˜XÚËË\Ý
Ú\RÚ[™
OÉÜÚ[‰Î‹ÝX›_™[˜Ú\ÚËË\Ý
Ú\RÚ[™
OÉÝX›IÎ‹Øš[ŸÜ˜]_˜]Ù\ŸØXš[™]Ë\Ý
Ú\RÚ[™
OÉÜÝÜ˜YÙIÎ‹ÝØ[[\ŸÜÝÝXÝË\Ý
Ú\RÚ[™
OÉÜÝXÝ\™IÎ‹ÛXXÚ[™_š[\ŸÛ˜ËË\Ý
Ú\RÚ[™
OÉÛXXÚ[™IÎ‰ÛØš™XÝ	ÎÂˆÛÛœÝY˜][š[^ÜÚ[Ž‰ÈÐÐ‘Ñ‰ËX›N‰ÈÐÎPMŽIËÝÜ˜YÙN‰ÈÍPNP‘N	ËÝXÝ\™N‰ÈÌÍMÍÉËXXÚ[™N‰ÈÎPPMÐŒÉßVÜÚ[ÝY]W_
Øš™XÝ›ØØ][Û—ÚYÉÈÑÑNQŒÉÎ‰ÈÐÐ‘QLIÊNÂˆÛÛœÝÙ[XÝYX]ÚJÛÜšÜÚÜšY]ÏËœÙ[XÝ[ÛË›X]Ú\ß×JKœÛÛYJX]ÚO›X]Ú™˜]Ú[™×ÚYOO[Øš™XÝšY	‰Š[X]Úœ›ÛÛWÚYX]Úœ›ÛÛWÚYOOXXÝ]™T›ÛÛRY
JNÂˆÛÛœÝÙ[XÝY™YYÐ][[Û]ÛÜšÜÚÜÙ[XÝYÝ]\ÂˆÈÛÜšÜÚÜÙ[XÝYÝ]\Ë˜ÛÛ™][Û‰‰ÛÜšÜÚÜÙ[XÝYÝ]\Ë˜ÛÛ™][ÛˆOOIÔ™XYIßH]ÛÜšÜÚÜÙ[XÝYÝ]\Ë˜›ØÚÙ\‚ˆˆÛÜšÜÚÜšY]ÏË˜ÛÝ[ÏË›™YY×Ø][[ÛŒÂˆÛÛœÝ][[Û“Ý™\›^HHÛÜšÜÚÜÝ™\›^\È	‰ˆœ›ÝÜÙS[ÙHOOH	Øœ›ÝÜÙIÈ	‰ˆÛÜšÜÚÜšY]Ð]˜Z[X›H	‰‚ˆØš™XÝšYOO[^[Ý]Ù[XÝY	‰ˆÙ[XÝYX]Ú	‰ˆÙ[XÝY™YYÐ][[ÛŽÂˆÛÛœÝÜ›Ý\HÝ™Ó›ÙJ	ÙÉËÂˆ˜[œÙ›Ü›Nˆ˜[œÛ]J	ÛØš™XÝžH	ÛØš™XÝž_JX	Ù]K]ÛÜšÜÚÜY˜]Ú[™ÉÎˆØš™XÝšYˆ	Ù]K\›Ý][Û‰ÎˆØš™XÝœ›Ý][Û‹	Ù]K^	ÎˆØš™XÝž	Ù]K^IÎˆØš™XÝžKˆ	Ù]K]ÚY	ÎˆØš™XÝÚY	Ù]KZZYÚ	ÎˆØš™XÝšZYÚˆÛ\ÜÎˆ	ÛØš™XÝšYOOH^[Ý]Ù[XÝYÈ	Ú\Ë\Ù[XÝY	Èˆ	ÉßIÛØš™XÝ›ØØ][Û—ÚYÈ	Ú\Ë[[šÙY	Èˆ	Ú\ËY˜]Ú[™Ë[Û›IßXˆ	Ù]K[[šË\Ý]\ÉÎ›Øš™XÝ›ØØ][Û—ÚYÉÛ[šÙY	Î‰Ù˜]Ú[™Ë[Û›IËˆ›ÛNˆ	Ø]Û‰ËXš[™^ˆ	Ø\šXK[X™[	Îˆ	ÔÙ[XÝ	È
ÈØš™XÝ›˜[YKˆJNÂˆÛÛœÝÚ\HHÝ™Ó›ÙJ	ÙÉËÈ˜[œÙ›Ü›Nˆ›Ý]J	ÛØš™XÝœ›Ý][ÛŸH	ÛØš™XÝÚYÈŸH	ÛØš™XÝšZYÚÈŸJXJNÂˆÛÛœÝ™XÝHÝ™Ó›ÙJ	Ü™XÝ	ËÈžˆŒˆš[ˆ][[Û“Ý™\›^HÈ	ÚÛ
˜\ŠKY\ÝXÝ]™JJIÈˆØš™XÝ˜ÛÛÜŸY˜][š[	Ùš[[ÜXÚ]IÎ”Ýš[™ÊØš™XÝ›ÜXÚ]OÏÌJKˆÝ›ÚÙNˆØš™XÝšYOOH^[Ý]Ù[XÝYÈ	ÚÛ
˜\ŠK\š[X\žJJIÈˆÚ[ÝY]OOOIÜÝXÝ\™IÏÉÈÌŒŒÌÉÎ‰ÈÍLŒMIËˆ	ÜÝ›ÚÙK]ÚY	ÎˆØš™XÝšYOOH^[Ý]Ù[XÝYÈŒˆŒÍKˆ	Ù]K[Øš™XÝ\Ú\IÎœÚ[ÝY]KˆJNÂˆÛÛœÝ^HÝ™Ó›ÙJ	Ý^	ËÂˆˆØš™XÝÚYÈ‹NˆØš™XÝšZYÚÈ‹	Ý^X[˜ÚÜ‰Îˆ	ÛZYIËˆ	ÙÛZ[˜[X˜\Ù[[™IÎˆ	ÛZYIË	Ù›Û\Ú^™IÎˆŒËˆš[ˆ][[Û“Ý™\›^OÉÚÛ
˜\ŠKY\ÝXÝ]™KY›Ü™YÜ›Ý[™
JIÎ‰ÚÛ
˜\ŠKY›Ü™YÜ›Ý[™
JIËˆ	Ù]K]ÛÜšÜÚÜXØ\[Û‰Î‰ÝYIË	Ø\šXK[X™[	Î›Øš™XÝ›˜[YKˆKØš™XÝ›˜[YJNÂˆÛÛœÝØ\[Û˜XÚÚ[™Ï\Ý™Ó›ÙJ	Ü™XÝ	ËÞŒNŒÚYŒZYÚŒž‹Œš[˜][[Û“Ý™\›^OÉÚÛ
˜\ŠKY\ÝXÝ]™JJIÎ‰ÚÛ
˜\ŠKX˜XÚÙÜ›Ý[™
JIË	ÜÚ[\‹Y]™[ÉÎ‰Û›Û™IË	Ù]K]ÛÜšÜÚÜXØ\[Û‹X˜XÚÙ›Ü	Î‰ÝYIßJNÂˆÛÛœÝ™\Ù]\[›™\\ÛÜšÑ›Ü‘˜]Ú[™ÊØš™XÝ
K\ÛÜšÏ\™\Ù]ÜÝ™Ó›ÙJ	Ú[XYÙIËÜ™\Ù\™P\ÜXÝ˜][Î‰ÞZYSZYYY]	Ë	ÜÚ[\‹Y]™[ÉÎ‰Û›Û™IË	Ù]K]ÛÜšÜÚÜX\ÛÜšÉÎœ™\Ù]šY™YŽœ™\Ù]˜\ÜÙ]JN›[ÂˆÛÛœÝ^Y\”Ýš\O[Øš™XÝ›^Y\OOIØX›Ý™IßØš™XÝ›^Y\OOIØ™[ÝÉÏÜÝ™Ó›ÙJ	Ü™XÝ	ËÙš[˜\›
Ü[›™\‹\Ýš\KIÛØš™XÝ›^Y\ŸJX	ÜÚ[\‹Y]™[ÉÎ‰Û›Û™IË	Ù]K]ÛÜšÜÚÜ[^Y\‹\Ýš\IÎ›Øš™XÝ›^Y\ŸJN›[ÂˆÛÛœÝ]Z[Ï\Ý™Ó›ÙJ	ÙÉËÉÜÚ[\‹Y]™[ÉÎ‰Û›Û™IßJK[šÓX\šÙ\\Ý™Ó›ÙJ	ØÚ\˜ÛIËØÞ›Øš™XÝÚYKŒNÞN‹ŒNŽ‹ŒKš[›Øš™XÝ›ØØ][Û—ÚYÉÈÌ‘MÎQ	Î‰ÚÛ
˜\ŠKX˜XÚÙÜ›Ý[™
JIËÝ›ÚÙN›Øš™XÝ›ØØ][Û—ÚYÉÈÌQPÎIÎ‰ÈÍÌNÉË	ÜÝ›ÚÙK]ÚY	Î‹Œ	Ù]K[[šËZ[™XØ]Ü‰Î›Øš™XÝ›ØØ][Û—ÚYÉÛ[šÙY	Î‰Ù˜]Ú[™Ë[Û›IË	ÜÚ[\‹Y]™[ÉÎ‰Û›Û™IßJNÂˆÛÛœÝÙ]›ÛÝš[H

HOˆÂˆÛÛœÝ]X\\•\›[Øš™XÝœ›Ý][Û‰LNOOLš\ÝX[ÚY\]X\\•\›ÛØš™XÝšZYÚ›Øš™XÝÚYš\ÝX[ZYÚ\]X\\•\›ÛØš™XÝÚY›Øš™XÝšZYÚš\ÝX[JØš™XÝÚY]š\ÝX[ÚY
KÌ‹š\ÝX[OJØš™XÝšZYÚ]š\ÝX[ZYÚ
KÌŽÂˆ™XÝœÙ]]šX]J	Þ	ËÝš[™Êš\ÝX[
JNÂˆ™XÝœÙ]]šX]J	ÞIËÝš[™Êš\ÝX[JJNÂˆ™XÝœÙ]]šX]J	ÝÚY	ËÝš[™Êš\ÝX[ÚY
JNÂˆ™XÝœÙ]]šX]J	ÚZYÚ	ËÝš[™Êš\ÝX[ZYÚ
JNÂˆYŠ\ÛÜšÊ^Ø\ÛÜšËœÙ]]šX]J	Þ	ËÝš[™Êš\ÝX[
JNØ\ÛÜšËœÙ]]šX]J	ÞIËÝš[™Êš\ÝX[JJNØ\ÛÜšËœÙ]]šX]J	ÝÚY	ËÝš[™Êš\ÝX[ÚY
JNØ\ÛÜšËœÙ]]šX]J	ÚZYÚ	ËÝš[™Êš\ÝX[ZYÚ
JNØ\ÛÜšËœÙ]]šX]J	ÛÜXÚ]IËÝš[™ÊØš™XÝ›ÜXÚ]OÏÌJJ_BˆYŠ^Y\”Ýš\J^Û^Y\”Ýš\KœÙ]]šX]J	Þ	ËÝš[™Êš\ÝX[
JNÛ^Y\”Ýš\KœÙ]]šX]J	ÞIËÝš[™Êš\ÝX[JJNÛ^Y\”Ýš\KœÙ]]šX]J	ÝÚY	ËÝš[™Êš\ÝX[ÚY
JNÛ^Y\”Ýš\KœÙ]]šX]J	ÚZYÚ	ËÝš[™Êš\ÝX[ZYÚ
J_Bˆ^œÙ]]šX]J	Þ	ËÝš[™ÊØš™XÝÚYÈŠJNÂˆ^œÙ]]šX]J	ÞIËÝš[™ÊØš™XÝšZYÚÈŠJNÂˆÛÛœÝX]š^\[‹™Ù]ØÜ™Y[ÕJ
KØÜ™Y[”ØØ[O[X]š^ÓX]›Z[ŠX]š\Ý
X]š^˜KX]š^˜ŠKX]š\Ý
X]š^˜ËX]š^™
JNŒNÂˆÛÛœÝ›Û^[ÏSX]›X^
L‹X]›Z[ŠMØš™XÝÚY
œØÜ™Y[”ØØ[J‹ŒŽš\ÝX[ZYÚ
œØÜ™Y[”ØØ[J‹
JNÂˆÛÛœÝ›ÛÚ^™OY›Û^[ËÓX]›X^
ØÜ™Y[”ØØ[KŒJNÂˆ^œÙ]]šX]J	Ù›Û\Ú^™IËÝš[™Ê›ÛÚ^™JJNÂˆÛÛœÝX^Ø\[Û•ÚY[Øš™XÝÚY
‹Ž‹Ú\˜XÝ\œÏVË‹‹›Øš™XÝ›˜[YWNÛ]ÚÝÛ[Øš™XÝ›˜[YNÂˆ^^ÛÛ[\ÚÝÛŽÂˆYŠ^™Ù]ÛÛ\]Y^[™Ý

O›X^Ø\[Û•ÚY
^Û]ÛÝ[XÚ\˜XÝ\œË›[™ÝÝÚ[JÛÝ[ŒI‰^™Ù]ÛÛ\]Y^[™Ý

O›X^Ø\[Û•ÚY
^ØÛÝ[KNÜÚÝÛXÚ\˜XÝ\œËœÛXÙJÛÝ[LJKš›Ú[Š	ÉÊJÉø )‰ÎÝ^^ÛÛ[\ÚÝÛŸ_BˆÛÛœÝØ\[Û”Y[™ÏSX]›Z[Š›ÛÚ^™J‹ŒËØš™XÝÚY
‹ŒÊKØ\[Û•ÚYSX]›Z[ŠØš™XÝÚY
‹ŽM‹^™Ù]ÛÛ\]Y^[™Ý

JØØ\[Û”Y[™ÊŒŠKØ\[Û’ZYÚY›ÛÚ^™JŒKNÂˆØ\[Û˜XÚÚ[™ËœÙ]]šX]J	Þ	ËÝš[™ÊØš™XÝÚYÌ‹XØ\[Û•ÚYÌŠJNØØ\[Û˜XÚÚ[™ËœÙ]]šX]J	ÞIËÝš[™ÊØš™XÝšZYÚÌ‹XØ\[Û’ZYÚÌŠJNØØ\[Û˜XÚÚ[™ËœÙ]]šX]J	ÝÚY	ËÝš[™ÊØ\[Û•ÚY
JNØØ\[Û˜XÚÚ[™ËœÙ]]šX]J	ÚZYÚ	ËÝš[™ÊØ\[Û’ZYÚ
JNÂˆ[šÓX\šÙ\‹œÙ]]šX]J	ØÞ	ËÝš[™ÊØš™XÝÚYKŒN
JNÙÜ›Ý\™]\Ù]žHÝš[™ÊØš™XÝž
NÈÜ›Ý\™]\Ù]žHHÝš[™ÊØš™XÝžJNÂˆÜ›Ý\™]\Ù]ÚYHÝš[™ÊØš™XÝÚY
NÈÜ›Ý\™]\Ù]šZYÚHÝš[™ÊØš™XÝšZYÚ
NÂˆ]Z[Ëœ™\XÙPÚ[™[Š
NÂˆYŠÚ[ÝY]OOOIÜÚ[‰Ê^ÂˆÛÛœÝ[œÙ]SX]›Z[ŠŒL‹š\ÝX[ÚY
‹Œ
KTÝ\]š\ÝX[ZYÚÍÂˆ]Z[Ë˜\[™
Ý™Ó›ÙJ	Ü]	ËÙ˜H	Ýš\ÝX[
Ú[œÙ]H	Ýš\ÝX[_Hˆ	Ýš\ÝX[JÝš\ÝX[ZYÚHH	Ýš\ÝX[
Ýš\ÝX[ÚYZ[œÙ]H	Ýš\ÝX[_Hˆ	Ýš\ÝX[JÝš\ÝX[ZYÚHH	Ýš\ÝX[H	Ýš\ÝX[JÞTÝ\H	Ýš\ÝX[
Ýš\ÝX[ÚYHH	Ýš\ÝX[H	Ýš\ÝX[JÞTÝ\
ŒŸH	Ýš\ÝX[
Ýš\ÝX[ÚYHH	Ýš\ÝX[H	Ýš\ÝX[JÞTÝ\
ŒßH	Ýš\ÝX[
Ýš\ÝX[ÚYXš[‰Û›Û™IËÝ›ÚÙN‰ÈÍMÍÐIË	ÜÝ›ÚÙK]ÚY	Î“X]›Z[ŠŒËš\ÝX[ZYÚ
‹ŒÍJK	Ù]KY›ÛÝš[Y]Z[	Î‰ÝYIßJJNÂˆY[ÙHYŠÚ[ÝY]OOOIÝX›IÊ^ÂˆÛÛœÝYÏSX]›Z[ŠŒ‹š\ÝX[ÚY
‹ŒL‹š\ÝX[ZYÚ
‹ŒŠK[œÙ][YÊ‹MNÂˆ›ÜŠÛÛœÝÞWHÙˆÖÝš\ÝX[
Ú[œÙ]š\ÝX[JÚ[œÙ]KÝš\ÝX[
Ýš\ÝX[ÚYZ[œÙ][YËš\ÝX[JÚ[œÙ]KÝš\ÝX[
Ú[œÙ]š\ÝX[JÝš\ÝX[ZYÚZ[œÙ][Y×KÝš\ÝX[
Ýš\ÝX[ÚYZ[œÙ][YËš\ÝX[JÝš\ÝX[ZYÚZ[œÙ][Y×WJY]Z[Ë˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÞKÚY›YËZYÚ›YËž‹ŒKš[‰ÈÍ‘MÍ‰Ë	Ù]KY›ÛÝš[Y]Z[	Î‰ÝYIßJJNÂˆ]Z[Ë˜\[™
Ý™Ó›ÙJ	Ü]	ËÙ˜H	Ýš\ÝX[H	Ýš\ÝX[JÝš\ÝX[ZYÚ
‹ŒŒŸH	Ýš\ÝX[
Ýš\ÝX[ÚYHH	Ýš\ÝX[H	Ýš\ÝX[JÝš\ÝX[ZYÚ
‹ŒßH	Ýš\ÝX[
Ýš\ÝX[ÚYXÝ›ÚÙN‰ÈÐNÍMIË	ÜÝ›ÚÙK]ÚY	Î‹Œ	Ù]KY›ÛÝš[Y]Z[	Î‰ÝYIßJJNÂˆY[ÙHYŠÚ[ÝY]OOOIÜÝÜ˜YÙIÊ^Âˆ]Z[Ë˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÞš\ÝX[
Ýš\ÝX[ÚY
‹ŒL‹Nš\ÝX[JÝš\ÝX[ZYÚ
‹ŒL‹ÚYš\ÝX[ÚY
‹Í‹ZYÚš\ÝX[ZYÚ
‹Í‹ž‹Œ‹š[‰Û›Û™IËÝ›ÚÙN‰ÈÑNQIË	ÜÝ›ÚÙK]ÚY	Î“X]›Z[ŠŒKš\ÝX[ZYÚ
‹Œ
K	Ù]KY›ÛÝš[Y]Z[	Î‰ÝYIßJJNÂˆY[ÙHYŠÚ[ÝY]OOOIÛXXÚ[™IÊ^Âˆ]Z[Ë˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÞš\ÝX[
Ýš\ÝX[ÚY
‹MKNš\ÝX[JÝš\ÝX[ZYÚ
‹Œ‹ÚYš\ÝX[ÚY
‹ŒÌ‹ZYÚš\ÝX[ZYÚ
‹Kž‹ŒKš[‰ÈÍLÍŒM‰ËÝ›ÚÙN‰ÈÑÑQÉË	ÜÝ›ÚÙK]ÚY	Î‹Œ	Ù]KY›ÛÝš[Y]Z[	Î‰ÝYIßJJNÂˆBˆNÂˆØ\[Û”™Yœ™\Ú\œËœ\Ú


OOœÙ]›ÛÝš[

JNÂˆÚ\K˜\[™
™XÝ]Z[ÊNÂˆYŠ\ÛÜšÊ^Ø\ÛÜšË›Û™\œ›ÜJ
OO˜\ÛÜšËœ™[[Ý™J
NÜÚ\K˜\[™
\ÛÜšÊ_ZYŠ^Y\”Ýš\J\Ú\K˜\[™
^Y\”Ýš\JNÂˆÜ›Ý\˜\[™
Ú\KØ\[Û˜XÚÚ[™Ë^[šÓX\šÙ\ŠNÂˆÙ]›ÛÝš[

NÂˆYˆ
Øš™XÝšYOOH^[Ý]Ù[XÝY	‰ˆX[˜YÙ\Š
H	‰ˆœ›ÝÜÙS[ÙHOOH	ÙY]	ÊHÂˆÜ›Ý\˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÂˆˆØš™XÝÚYHŒŽNˆØš™XÝšZYÚHŒŽÚYˆŒŽZYÚˆŒŽˆš[ˆ	ÈÐM‘MIËÝ›ÚÙNˆ	ÚÛ
˜\ŠKX˜XÚÙÜ›Ý[™
JIË	ÜÝ›ÚÙK]ÚY	ÎˆŒˆ›ÛNˆ	Ø]Û‰ËXš[™^ˆ	Ø\šXK[X™[	Îˆ	Ô™\Ú^™H˜]Ú[™È[™IË	Ù]K\™\Ú^™KZ[™IÎˆ	ÝYIËˆJJNÂˆBˆ]˜YÈH[Âˆ]˜YÓ[Ý™YH˜[ÙNÂˆÜ›Ý\›Û˜ÛXÚÈH]™[OˆÂˆYˆ
˜YÓ[Ý™Y
HÈ˜YÓ[Ý™YH˜[ÙNÈ]™[œÝÜ›ÜYØ][ÛŠ
NÈ™]\›ŽÈBˆYˆ
[™[™Ô[]RÚ[™	‰ˆX[˜YÙ\Š
H	‰ˆœ›ÝÜÙS[ÙHOOH	ÙY]	ÊHÂˆÛÛœÝÚ[HÚ[›ÜŠ]™[
NÂˆY˜]Ú[™Ð]
[™[™Ô[]RÚ[™Ú[[™[™Ô[]S˜[Y_[™[™Ô[]RÚ[™[™[™Ô[]T™\Ù]
NÂˆ]™[œÝÜ›ÜYØ][ÛŠ
NÂˆ™]\›ŽÂˆBˆÙ[XÝ[›™\‘˜]Ú[™ÊØš™XÝ
NÂˆNÂˆÜ›Ý\›ÛšÙ^YÝÛˆH]™[OˆÂˆYˆ
]™[šÙ^HOOH	Ñ[\‰È]™[šÙ^HOOH	È	ÊHÂˆ]™[œ™]™[Y˜][

NÂˆÙ[XÝ[›™\‘˜]Ú[™ÊØš™XÝ
NÂˆ™]\›ŽÂˆBˆYˆ
Ø[‘Y][Š
H	‰ˆ
]™[˜Ý›Ù^H]™[›Y]RÙ^JH	‰ˆ]™[šÙ^KÓÝÙ\Ø\ÙJ
HOOH	Þ‰È	‰ˆVÉÒS”U	Ë	ÕVT‘PIË	ÔÑSPÕ	×Kš[˜ÛY\Ê]™[\™Ù]YÓ˜[YJJHÂˆ]™[œ™]™[Y˜][

NÂˆ]™[œÚYÙ^HÈ™YÔ›ÛÛJ
Hˆ[™Ô›ÛÛJ
NÂˆBˆNÂˆÜ›Ý\›ÛœÚ[\™ÝÛˆH]™[OˆÂˆYˆ
XØ[‘Y][Š
HY]™[š\Ôš[X\žJH™]\›ŽÂˆ]™[œÝÜ›ÜYØ][ÛŠ
NÂˆÙ[XÝ[›™\‘˜]Ú[™ÊØš™XÝ˜[ÙJNÂˆ˜YÈHÈÝ\ˆÚ[›ÜŠ]™[
K›ÛÛNˆÛÛ™J›ÛÛJKØš™XÝˆÛÛ™JØš™XÝ
K™\Ú^™Nˆ]™[\™Ù]™]\Ù]œ™\Ú^™R[™HOOH	ÝYIÈNÂˆÜ›Ý\œÙ]Ú[\Ø\\™J]™[œÚ[\’Y
NÂˆNÂˆÜ›Ý\›ÛœÚ[\›[Ý™HH]™[OˆÂˆYˆ
Y˜YÊH™]\›ŽÂˆYŠXØ[‘Y][Š
J^Û^[Ý]˜Yœ›ÛÛ\ÖÜ›ÛÛR[™^
›ÛÛKšY
WOY˜YËœ›ÛÛNÙ˜YÏ[[ÝÛÜšÜÚÜZ[

NÜ™]\›ŸBˆÛÛœÝÚ[HÚ[›ÜŠ]™[
KHÚ[žH˜YËœÝ\žHHÚ[žHH˜YËœÝ\žNÂˆYˆ
X]˜XœÊ
H
ÈX]˜XœÊJHHŒ
H˜YÓ[Ý™YHYNÂˆYˆ
Y˜YÓ[Ý™Y
H™]\›ŽÂˆÛÛœÝÛ˜\H˜[YHOˆ[›™\”Û˜\ÈX]œ›Ý[™
˜[YH
ˆ
HÈˆX]œ›Ý[™
˜[YH
ˆL
HÈLÂˆYˆ
˜YËœ™\Ú^™JHÂˆØš™XÝÚYHX]›X^
ŒKX]›Z[Š›ÛÛKÚYHØš™XÝžÛ˜\
˜YË›Øš™XÝÚY
È
JJNÂˆØš™XÝšZYÚHX]›X^
ŒKX]›Z[Š›ÛÛKšZYÚHØš™XÝžKÛ˜\
˜YË›Øš™XÝšZYÚ
ÈJJJNÂˆH[ÙHÂˆÛÛœÝX^\›ÛÛKÚY[Øš™XÝÚYX^O\›ÛÛKšZYÚ[Øš™XÝšZYÚÂˆØš™XÝžHX]›X^
X]›Z[Š[›™\”Û˜\ÓX]™›ÛÜŠX^

KÍ›X^Û˜\
˜YË›Øš™XÝž
È
JJNÂˆØš™XÝžHHX]›X^
X]›Z[Š[›™\”Û˜\ÓX]™›ÛÜŠX^J
KÍ›X^KÛ˜\
˜YË›Øš™XÝžH
ÈJJJNÂˆBˆÜ›Ý\œÙ]]šX]J	Ý˜[œÙ›Ü›IË˜[œÛ]J	ÛØš™XÝžH	ÛØš™XÝž_JX
NÂˆÜ›Ý\™]\Ù]žHÝš[™ÊØš™XÝž
NÈÜ›Ý\™]\Ù]žHHÝš[™ÊØš™XÝžJNÂˆÜ›Ý\™]\Ù]ÚYHÝš[™ÊØš™XÝÚY
NÈÜ›Ý\™]\Ù]šZYÚHÝš[™ÊØš™XÝšZYÚ
NÂˆÛÛœÝ[™HHÜ›Ý\œ]Y\žTÙ[XÝÜŠ	ÖÙ]K\™\Ú^™KZ[™WIÊNÂˆYˆ
[™JHÂˆ[™KœÙ]]šX]J	Þ	ËÝš[™ÊØš™XÝÚYHŒŽ
JNÂˆ[™KœÙ]]šX]J	ÞIËÝš[™ÊØš™XÝšZYÚHŒŽ
JNÂˆBˆÚ\KœÙ]]šX]J	Ý˜[œÙ›Ü›IË›Ý]J	ÛØš™XÝœ›Ý][ÛŸH	ÛØš™XÝÚYÈŸH	ÛØš™XÝšZYÚÈŸJX
NÂˆÙ]›ÛÝš[

NÂˆNÂˆÜ›Ý\›ÛœÚ[\\H

HOˆÂˆYŠ˜YÉ‰ˆXØ[‘Y][Š
J^Û^[Ý]˜Yœ›ÛÛ\ÖÜ›ÛÛR[™^
›ÛÛKšY
WOY˜YËœ›ÛÛNÙ˜YÏ[[ÝÛÜšÜÚÜZ[

NÜ™]\›ŸBˆYˆ
˜YÓ[Ý™Y	‰ˆ˜YÈ	‰ˆ”ÓÓ‹œÝš[™ÚYžJ›ÛÛJHOOR”ÓÓ‹œÝš[™ÚYžJ˜YËœ›ÛÛJJHÂˆØ]™T›ÛÛR\ÝÜžJ›ÛÛKšY˜YËœ›ÛÛJNÂˆX\šÔ[›™\‘\J
NÂˆÛÜšÜÚÜZ[

NÂˆBˆ˜YÈH[ÂˆNÂˆÜ›Ý\›ÛœÚ[\˜Ø[˜Ù[H

HOˆÂˆYˆ
˜YÊHÂˆ^[Ý]˜Yœ›ÛÛ\ÖÜ›ÛÛR[™^
›ÛÛKšY
WHH˜YËœ›ÛÛNÂˆÛÜšÜÚÜZ[

NÂˆBˆ˜YÈH[ÂˆNÂˆ[‹˜\[™
Ü›Ý\
NÂˆBˆ]˜XÚÙÜ›Ý[™[ˆH[Âˆ[‹›ÛšÙ^YÝÛˆH]™[OˆÈYŠ]™[šÙ^OOOIÑ\ØØ\IÉ‰˜Ø[˜Ù[[™[™Ô[]TXÙ[Y[

JH]™[œ™]™[Y˜][

NÈNÂˆ[‹›Û˜ÛXÚÈH]™[OˆÂˆYˆ
Ý\™\ÜÔ[›™\ÛXÚÊHÂˆÝ\™\ÜÔ[›™\ÛXÚÈH˜[ÙNÂˆ]™[œ™]™[Y˜][

NÂˆ]™[œÝÜ›ÜYØ][ÛŠ
NÂˆ™]\›ŽÂˆBˆYˆ
Y]™[\™Ù]˜ÛÜÙ\Ý
	ÖÙ]K]ÛÜšÜÚÜY˜]Ú[™×IÊH	‰ˆ[™[™Ô[]RÚ[™	‰ˆX[˜YÙ\Š
H	‰ˆœ›ÝÜÙS[ÙHOOH	ÙY]	ÊHÂˆY˜]Ú[™Ð]
[™[™Ô[]RÚ[™Ú[›ÜŠ]™[
K[™[™Ô[]S˜[Y_[™[™Ô[]RÚ[™[™[™Ô[]T™\Ù]
NÂˆBˆNÂˆÛÛœÝ[™˜XÚÙÜ›Ý[™[ˆH
]™[Ø[˜Ù[YY˜[ÙJHOˆÂˆYˆ
X˜XÚÙÜ›Ý[™[ˆ]™[œÚ[\’YOOH˜XÚÙÜ›Ý[™[‹œÚ[\’Y
H™]\›ŽÂˆÛÛœÝÙ\Ý\™HH˜XÚÙÜ›Ý[™[ŽÂˆ˜XÚÙÜ›Ý[™[ˆH[Âˆ[‹˜Û\ÜÓ\Ýœ™[[Ý™J	Ú\Ë\[›š[™ÉÊNÂˆYˆ
Ù\Ý\™K›[Ý™Y
HÝ\™\ÜÔ[›™\ÛXÚÈHYNÂˆYˆ
Ø[˜Ù[Y\[‹š\ÐÛÛ›™XÝYXÝ]™T›ÛÛRYOOHÙ\Ý\™Kœ›ÛÛRY[›™\–›ÛÛHOOHÙ\Ý\™Kž›ÛÛJHÂˆYˆ
[‹š\ÐÛÛ›™XÝY
H[‹œÙ]]šX]J	ÝšY]Ð›Þ	ËÙ\Ý\™KšY]Ð›Þ
NÂˆ™]\›ŽÂˆBˆYˆ
Ù\Ý\™K›[Ý™Y
H[›™\”[ˆHÙ\Ý\™K›™^[ŽÂˆNÂˆ[‹›ÛœÚ[\™ÝÛˆH]™[OˆÂˆYˆ
Y]™[š\Ôš[X\žH
]™[˜]ÛˆOOH	‰ˆ]™[˜]ÛˆOOHJH]™[\™Ù]˜ÛÜÙ\Ý
	ÖÙ]K]ÛÜšÜÚÜY˜]Ú[™×IÊJH™]\›ŽÂˆÝ\™\ÜÔ[›™\ÛXÚÈH˜[ÙNÂˆÛÛœÝ[™\œÙHH[‹™Ù]ØÜ™Y[ÕJ
OËš[™\œÙJ
NÂˆYˆ
Z[™\œÙJH™]\›ŽÂˆ]™[œ™]™[Y˜][

NÂˆÛÛœÝØÜ™Y[•Ô›ÛÛHH™]ÈÓSX]š^
Ú[™\œÙK˜K[™\œÙK˜‹[™\œÙK˜Ë[™\œÙK™[™\œÙK™K[™\œÙK™—JNÂˆÛÛœÝÝ\Ú[H™]ÈÓTÚ[
]™[˜ÛY[]™[˜ÛY[JK›X]š^˜[œÙ›Ü›JØÜ™Y[•Ô›ÛÛJNÂˆ˜XÚÙÜ›Ý[™[ˆHÂˆÚ[\’Y™]™[œÚ[\’YÝ\Ú[ØÜ™Y[•Ô›ÛÛKØÜ™Y[–™]™[˜ÛY[ØÜ™Y[–N™]™[˜ÛY[Kˆ[ŽžË‹‹œ[›™\”[ŸK™^[ŽžË‹‹œ[›™\”[ŸK›ÛÛRYœ›ÛÛKšY›ÛÛNœ[›™\–›ÛÛKˆÚYZYÚˆšY]Ð›Þœ[‹™Ù]]šX]J	ÝšY]Ð›Þ	ÊK[Ý™Y™˜[ÙKˆNÂˆ[‹˜Û\ÜÓ\Ý˜Y
	Ú\Ë\[›š[™ÉÊNÂˆ[‹œÙ]Ú[\Ø\\™J]™[œÚ[\’Y
NÂˆNÂˆ[‹›ÛœÚ[\›[Ý™HH]™[OˆÂˆYˆ
X˜XÚÙÜ›Ý[™[ˆ]™[œÚ[\’YOOH˜XÚÙÜ›Ý[™[‹œÚ[\’Y
H™]\›ŽÂˆYˆ
\[‹š\ÐÛÛ›™XÝYXÝ]™T›ÛÛRYOOH˜XÚÙÜ›Ý[™[‹œ›ÛÛRY[›™\–›ÛÛHOOH˜XÚÙÜ›Ý[™[‹ž›ÛÛJHÂˆ[™˜XÚÙÜ›Ý[™[Š]™[YJNÂˆ™]\›ŽÂˆBˆÛÛœÝÚ[\ˆH™]ÈÓTÚ[
]™[˜ÛY[]™[˜ÛY[JK›X]š^˜[œÙ›Ü›J˜XÚÙÜ›Ý[™[‹œØÜ™Y[•Ô›ÛÛJNÂˆÛÛœÝ\Ú[\‹žX˜XÚÙÜ›Ý[™[‹œÝ\Ú[žO\Ú[\‹žKX˜XÚÙÜ›Ý[™[‹œÝ\Ú[žNÂˆYˆ
X˜XÚÙÜ›Ý[™[‹›[Ý™Y	‰ˆX]š\Ý
]™[˜ÛY[X˜XÚÙÜ›Ý[™[‹œØÜ™Y[–]™[˜ÛY[KX˜XÚÙÜ›Ý[™[‹œØÜ™Y[–JOÊH™]\›ŽÂˆ˜XÚÙÜ›Ý[™[‹›[Ý™YHYNÂˆÝ\™\ÜÔ[›™\ÛXÚÈHYNÂˆ˜XÚÙÜ›Ý[™[‹›™^[^Þ˜˜XÚÙÜ›Ý[™[‹œ[‹žYN˜˜XÚÙÜ›Ý[™[‹œ[‹žKY_NÂˆ[‹œÙ]]šX]J	ÝšY]Ð›Þ	Ë	Ø˜XÚÙÜ›Ý[™[‹›™^[‹žH	Ø˜XÚÙÜ›Ý[™[‹›™^[‹ž_H	Ø˜XÚÙÜ›Ý[™[‹ÚYH	Ø˜XÚÙÜ›Ý[™[‹šZYÚX
NÂˆNÂˆ[‹›ÛœÚ[\\H]™[Oˆ[™˜XÚÙÜ›Ý[™[Š]™[
NÂˆ[‹›ÛœÚ[\˜Ø[˜Ù[H]™[Oˆ[™˜XÚÙÜ›Ý[™[Š]™[YJNÂˆ[‹›Û›ÜÝÚ[\˜Ø\\™HH]™[Oˆ[™˜XÚÙÜ›Ý[™[Š]™[YJNÂˆØ[˜\Ë˜\[™
[ŠNÂˆ[›™\Ø[˜\ÓØœÙ\™\[™]È™\Ú^™SØœÙ\™\Š

OO˜Ø\[Û”™Yœ™\Ú\œË™›Ü‘XXÚ
™Yœ™\ÚOœ™Yœ™\Ú

JJNÂˆ[›™\Ø[˜\ÓØœÙ\™\‹›ØœÙ\™J[ŠNÂˆ™\]Y\Ý[š[X][Û‘œ˜[YJ

OO˜Ø\[Û”™Yœ™\Ú\œË™›Ü‘XXÚ
™Yœ™\ÚOœ™Yœ™\Ú

JJNÂŸB™[˜Ý[Ûˆ›ÛÛR[œÜXÝÜŠ›ÛÛKØš™XÝ]Z[Ê^ÚYŠ\›ÛÛJ^Ù]Z[Ë˜\[™
›ÙJ	Ú‰Ë	Ô›ÛÛH]Z[ÉÊK›ÙJ	Ü	Ë›ÛÛPÚÛÜÙ\“Y\ÜØYÙ_	ÐÚÛÜÙHH›ÛÛHÜˆÜ™X]HÛ™HÈ™YÚ[‹‰ÊJNÚYŠœ›ÝÜÙS[ÙOOOIØœ›ÝÜÙIÉ‰ÛÜšÜÚÜšY]Ð]˜Z[X›I‰ÛÜšÜÚÜšY]ÏËœÙ[XÝ[ÛË\™Ù]ÚY
\[›™\“˜]]™R[œÜXÝÜŠÛØØ][Û—ÚYÛÜšÜÚÜ[]RYK]Z[ÊNÜ™]\›ŸZYŠX[˜YÙ\Š
I‰˜œ›ÝÜÙS[ÙOOOIÙY]	Ê^ÚYŠØš™XÝ	‰ˆ\›ÛÛTÙ][™ÜÔÚÝÛŠY˜]Ú[™ÑY][œÜXÝÜŠ›ÛÛKØš™XÝ]Z[ÊNÙ[Ù^Ü›ÛÛQY][œÜXÝÜŠ›ÛÛK]Z[ÊNÚYŠØš™XÝ	‰œ›ÛÛTÙ][™ÜÔÚÝÛŠY]Z[Ë˜\[™
]ÛŠ	Ñ˜]Ú[™ÈÙ][™ÜÉË

OOžÜ›ÛÛTÙ][™ÜÔÚÝÛY˜[ÙNÝÛÜšÜÚÜZ[

_JJ_ZYŠØš™XÝ	‰›Øš™XÝ›ØØ][Û—ÚY
Y]Z[Ë˜\[™
]ÛŠ	Ðœ›ÝÜÙH˜]]™HÝÜ˜YÙIË

OOžØœ›ÝÜÙS[ÙOIØœ›ÝÜÙIÎÜ›ÛÛTÙ][™ÜÔÚÝÛY˜[ÙNÜÙ[XÝ[›™\‘˜]Ú[™ÊØš™XÝ
_JJNÚYŠ^[Ý][˜Ù\Z[ŠY]Z[Ëœ]Y\žTÙ[XÝÜ[
	Ú[œ]Ù[XÝ]Û‰ÊK™›Ü‘XXÚ
ÛÛ›ÛO˜ÛÛ›Û™\ØX›Y]YJ_Y[ÙHYŠØš™XÝ
^Ù]Z[Ë˜\[™
›ÙJ	Ú‰ËØš™XÝ›˜[YJK›ÙJ	Ü	ËØš™XÝšÚ[™
ÉÈ0­È	ÊÛØš™XÝÚY
ÉÈ0åÈ	ÊÛØš™XÝšZYÚ
ÉÈ	ÊK›ÙJ	Ü	ËØš™XÝ›ØØ][Û—ÚYÉÓ[šÙY˜]]™HØØ][Ûˆ0­È	ÊØY™\ÜÊØš™XÝ›ØØ][Û—ÚY
N‰Ñ˜]Ú[™ÈÛ›H0­È›Ý[šÙYÈÝÜ˜YÙK‰ÊJNÜ[›™\“˜]]™R[œÜXÝÜŠØš™XÝ]Z[Ê_Y[Ù^Ù]Z[Ë˜\[™
›ÙJ	Ú‰Ë›ÛÛK›˜[YJK›ÙJ	Ü	Ë›ÛÛKÚY
ÉÈ0åÈ	ÊÜ›ÛÛKšZYÚ
ÉÈ	ÊÊ›ÛÛK˜\›Þ[X]OÉÈ0­È\›Þ[X]HYX\Ý\™[Y[ÉÎ‰ÉÊJK›ÙJ	Ü	Ë›ÛÛK›ØØ][Û—ÚYÉÓ˜]]™H›ÛÝ0­È	ÊØY™\ÜÊ›ÛÛK›ØØ][Û—ÚY
N‰Ó›È˜]]™HÝÜ˜YÙH›ÛÝ	ÊJNÚYŠ›ÛÛK›ØØ][Û—ÚY
Y]Z[Ë˜\[™
]ÛŠ	Ðœ›ÝÜÙH˜]]™H›ÛÝ	Ë

OOœ™Yœ™\ÚÛÜšÜÚÜšY]Ê›ÛÛK›ØØ][Û—ÚY˜[ÙJJJNÚYŠÛÜšÜÚÜšY]Ð]˜Z[X›I‰ÛÜšÜÚÜšY]ÏËœÙ[XÝ[ÛË\™Ù]ÚY
\[›™\“˜]]™R[œÜXÝÜŠÛØØ][Û—ÚYÛÜšÜÚÜ[]RYK]Z[Ë˜[ÙJNÚYŠÛÜšÜÚÜšY]ÏËœÙ[XÝ[ÛË›X]Ú\ÏË›[™ÝŒJ^ØÛÛœÝÚÛÜÙ\[›ÙJ	Ù]‰ÊNØÚÛÜÙ\‹œÙ]]šX]J	Ü›ÛIË	ÙÜ›Ý\	ÊNØÚÛÜÙ\‹œÙ]]šX]J	Ø\šXK[X™[	Ë	ÐÚÛÜÙHH›ÛÛIÊNØÚÛÜÙ\‹˜\[™
›ÙJ	ÚÉË	ÐÚÛÜÙHH›ÛÛH™\™\Ù[][Û‰ÊJNÙ›ÜŠÛÛœÝX]ÚÙˆÛÜšÜÚÜšY]ËœÙ[XÝ[Û‹›X]Ú\Ê^ØÛÛœÝ\™Ù]\›ÛÛPžRY
X]Úœ›ÛÛWÚY
K˜]Ú[™Ï]\™Ù]Ë›Øš™XÝË™š[™
›ÝÏOœ›ÝËšYOO[X]Ú™˜]Ú[™×ÚY
NÚYŠ˜]Ú[™ÊXÚÛÜÙ\‹˜\[™
]ÛŠ
\™Ù]›˜[Y_	Ô›ÛÛIÊJÉÈ0­È	ÊÙ˜]Ú[™Ë›˜[YJÉÈ0­È	ÊÛX]Ú›ØØ][Û—ÚY

OOžØÚÛÜÙT[›™\”™\™\Ù[][ÛŠ\™Ù]˜]Ú[™Ê_JJ_Y]Z[Ë˜\[™
ÚÛÜÙ\Š__ZYŠ[›™\‘Y]\œ›ÜŠ^ØÛÛœÝ\œ›Ü›Þ[Y\ÜØYÙJ[›™\‘Y]\œ›Ü‹	Ù\œ›Ü‰ÊNÙ\œ›Ü›ÞœÙ]]šX]J	Ü›ÛIË	Ø[\	ÊNÙ]Z[Ëœ™\[™
\œ›Ü›Þ
_ZYŠ›ÛÛS[šÕØ\›š[™Ê›ÛÛJJY]Z[Ë˜\[™
Y\ÜØYÙJ›ÛÛS[šÕØ\›š[™Ê›ÛÛJK	Ø][[Û‰ÊJ_B™[˜Ý[ÛˆÚÝÐÛÝ™\˜YÙJ\™[
^ØÛÛœÝÙXÝ[Û[›ÙJ	Ù]Z[ÉË[	Ü[›™\‹XÛÝ™\˜YÙIÊNÜÙXÝ[Û‹˜\[™
›ÙJ	ÜÝ[[X\žIË	ÔÚÝÈÚY\ˆ˜]]™HÛÝ™\˜YÙH[™ÙX\˜Ú	ÊJNÜZ[ÛÜšÜÚÜœ›ÝÜÙJÙXÝ[ÛŠNÜ\™[˜\[™
ÙXÝ[ÛŠ_B™[˜Ý[Ûˆ[›™\’Ú[™Ü›Ý\
Ú[™
^ØÛÛœÝ˜[YOZÚ[™ÓÝÙ\Ø\ÙJ
NÜ™]\›ˆÜÚ[Ÿ˜XÚßØXš[™]˜]Ù\‹Ë\Ý
˜[YJOÉÔÝÜ˜YÙIÎ‹Øš[ŸÜ˜]KË\Ý
˜[YJOÉÐš[œÉÎ‹ÝX›_™[˜Ú\ÚËË\Ý
˜[YJOÉÕÛÜšÈÝ\™˜XÙ\ÉÎ‹ÝØ[[\ŸÜÝÝXÝË\Ý
˜[YJOÉÔÝXÝ\™IÎ‹ÛXXÚ[™_š[\ŸÛ˜ËË\Ý
˜[YJOÉÓXXÚ[™\ÉÎ‰ÓÝ\‰ßB™[˜Ý[Ûˆ[›™\”[]RXÛÛŠÚ[™
^ØÛÛœÝ˜[YOZÚ[™ÓÝÙ\Ø\ÙJ
KÜ›Ý\\[›™\’Ú[™Ü›Ý\
Ú[™
KÝ™Ï\Ý™Ó›ÙJ	ÜÝ™ÉËÝšY]Ð›Þ‰Ì‰ËÛ\ÜÎ‰Ü[›™\‹[Øš™XÝZXÛÛ‰Ë	Ø\šXKZY[‰Î‰ÝYIË›ØÝ\ØX›N‰Ù˜[ÙIßJKš[YÜ›Ý\OOIÐš[œÉÏÉÈÍPNP‘N	Î™Ü›Ý\OOIÕÛÜšÈÝ\™˜XÙ\ÉÏÉÈÐÎPMŽIÎ™Ü›Ý\OOIÔÝXÝ\™IÏÉÈÌÍMÍÉÎ™Ü›Ý\OOIÓXXÚ[™\ÉÏÉÈÎPPMÐŒÉÎ‰ÈÐÐ‘Ñ‰ÎÜÝ™Ë˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÞ‹NKÚYL‹ZYÚŒÌ‹žŒËš[‰ÚÛ
˜\ŠK[]]Y
JIËÝ›ÚÙN‰ÚÛ
˜\ŠKX›Ü™\ŠJIßJJNÚYŠÜÚ[Ÿ˜XÚËË\Ý
˜[YJJ^Ù›ÜŠÛÛœÝHÙˆÌL‹ŒKÌJ\Ý™Ë˜\[™
Ý™Ó›ÙJ	Ü]	ËÙ˜HLÈ	Þ_HLHHMˆ	ÞKMHˆ	ÞJÌßHH	ÞKMHˆ	ÞJÌßXÝ›ÚÙN‰ÈÍŒÌMÎ	Ë	ÜÝ›ÚÙK]ÚY	ÎŒ‹Œ‹š[‰Û›Û™IßJJ_Y[ÙHYŠÝX›_™[˜Ú\ÚËË\Ý
˜[YJJ^ÜÝ™Ë˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÞŒLËNŒLËÚYŒÎZYÚËžŒKKš[Ý›ÚÙN‰ÈÍLÍŒMIßJKÝ™Ó›ÙJ	Ü]	ËÙ‰ÓHNŒˆÌÈHˆŒˆÌÉËÝ›ÚÙN‰ÈÍ‘MÍ‰Ë	ÜÝ›ÚÙK]ÚY	ÎŒßJJ_Y[ÙHYŠØØXš[™]˜]Ù\‹Ë\Ý
˜[YJJ^ÜÝ™Ë˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÞŒMNŒLÚYŒÍ‹ZYÚŒŒËžŒKš[‰ÈÐPPŽ	ËÝ›ÚÙN‰ÈÍLÍŒMIË	ÜÝ›ÚÙK]ÚY	ÎŒŸJKÝ™Ó›ÙJ	Ü]	ËÙ‰ÓHÌˆLHˆÌˆHHŒˆHÎHŒˆ	ËÝ›ÚÙN‰ÈÍLÍŒMIË	ÜÝ›ÚÙK]ÚY	ÎŒKŸJJ_Y[ÙHYŠØš[ŸÜ˜]KË\Ý
˜[YJJ^ÜÝ™Ë˜\[™
Ý™Ó›ÙJ	Ü]	ËÙ‰ÓHMˆLÈÌˆŒ‰Ëš[Ý›ÚÙN‰ÈÌÍÍNQIË	ÜÝ›ÚÙK]ÚY	ÎŒŸJKÝ™Ó›ÙJ	Ü]	ËÙ‰ÓHŒN	ËÝ›ÚÙN‰ÈÑNQIË	ÜÝ›ÚÙK]ÚY	ÎŒŸJJ_Y[ÙHYŠÝØ[[\ŸÜÝÝXÝË\Ý
˜[YJJ^ÜÝ™Ë˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÞŒMNŒL‹ÚYŒÍ‹ZYÚŒNš[‰ÈÌÍMÍÉËÝ›ÚÙN‰ÈÌŒŒÌÉË	ÜÝ›ÚÙK]ÚY	ÎŒŸJKÝ™Ó›ÙJ	Ü]	ËÙ‰ÓHNMˆˆHNˆ‰ËÝ›ÚÙN‰ÈÍÍÍÎ	Ë	ÜÝ›ÚÙK]ÚY	ÎŒK_JJ_Y[ÙHYŠÛXXÚ[™_š[\ŸÛ˜ËË\Ý
˜[YJJ^ÜÝ™Ë˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÞŒL‹NŒLKÚYZYÚŒŒ‹žŒËš[Ý›ÚÙN‰ÈÍLÍŒMIË	ÜÝ›ÚÙK]ÚY	ÎŒŸJKÝ™Ó›ÙJ	Ü™XÝ	ËÞŒNKNŒMKÚYŒNZYÚŒL‹žŒ‹š[‰ÈÍLŒM‰ßJKÝ™Ó›ÙJ	ØÚ\˜ÛIËØÞÞNŒMËŽŒ‹š[‰ÈÌÑLŽ	ßJJ_Y[ÙHÝ™Ë˜\[™
Ý™Ó›ÙJ	Ü™XÝ	ËÞŒM‹NŒL‹ÚYŒÌ‹ZYÚŒNžŒ‹š[Ý›ÚÙN‰ÈÍLÍŒMIË	ÜÝ›ÚÙK]ÚY	ÎŒŸJJNÜ™]\›ˆÝ™ßY[˜Ý[Ûˆ[›™\\ÛÜšÑ›Ü‘˜]Ú[™ÊØš™XÝ
^ØÛÛœÝ^XÝ]ÛÜšÜÚÜ™\Ù]›Ü‘˜]Ú[™ÊØš™XÝ
NÚYŠ^XÝ
\™]\›ˆ^XÝØÛÛœÝÚ[™TÝš[™ÊØš™XÝšÚ[™	ÉÊKÓÝÙ\Ø\ÙJ
KØ]YÛÜžOKÜ˜XÚßÚ[‹Ë\Ý
Ú[™
OÉÔÚ[™\ÉÎ‹ØØXš[™]Ë\Ý
Ú[™
OÉÐØXš[™]ÉÎ‹Ù˜]Ù\‹Ë\Ý
Ú[™
OÉÑ˜]Ù\œÉÎ‹Øš[ŸÜ˜]KË\Ý
Ú[™
OÉÐš[œÉÎ‹ÝX›_™[˜Ú\ÚËË\Ý
Ú[™
OÉÕÛÜšÈÝ\™˜XÙ\ÉÎ›[ÚYŠXØ]YÛÜžJ\™]\›ˆ[Ü™]\›ˆÛÜšÜÚÜØš™XÝ™\Ù]Ë™š[™
™\Ù]Oœ™\Ù]šÚ[™ÓÝÙ\Ø\ÙJ
OOOZÚ[™
_ÛÜšÜÚÜØš™XÝ™\Ù]Ë™š[™
™\Ù]Oœ™\Ù]˜Ø]YÛÜžOOOXØ]YÛÜžJ_[Y[˜Ý[ÛˆØ[˜Ù[[™[™Ô[]TXÙ[Y[

^ÚYŠ\[™[™Ô[]RÚ[™
\™]\›ˆ˜[ÙNÜ[™[™Ô[]RÚ[™[[Ü[™[™Ô[]S˜[YO[[Ü[™[™Ô[]T™\Ù][[ÝšY]Ëœ]Y\žTÙ[XÝÜ[
	Ëœ[›™\‹[Øš™XÝœ[›™\‹\™\Ù]XØ\™	ÊK™›Ü‘XXÚ
][OOžÚ][K˜Û\ÜÓ\Ýœ™[[Ý™J	ØXÝ]™IÊNÚ][KœÙ]]šX]J	Ø\šXK\™\ÜÙY	Ë	Ù˜[ÙIÊ_JNÝØ\Ý
	ÔXÙ[Y[Ø[˜Ù[Y‰ÊNÜ™]\›ˆY_Y[˜Ý[Ûˆ[›™\”™\Ù][]J[]K›ÝÜÊ^ØÛÛœÝ[™[[›ÙJ	Ù]‰Ë[	Ü[›™\‹\™\Ù]ÉÊKÜ›Ý\Ï[™]ÈX\

NÙ›ÜŠÛÛœÝ™\Ù]ÙˆÛÜšÜÚÜØš™XÝ™\Ù]Ê^ÚYŠYÜ›Ý\Ëš\Ê™\Ù]˜Ø]YÛÜžJJYÜ›Ý\ËœÙ]
™\Ù]˜Ø]YÛÜžK×JNÙÜ›Ý\Ë™Ù]
™\Ù]˜Ø]YÛÜžJKœ\Ú
™\Ù]
_Y›ÜŠÛÛœÝØØ]YÛÜžK™\Ù]×HÙˆÜ›Ý\Ê^ØÛÛœÝÙXÝ[Û[›ÙJ	Ù]Z[ÉË[	Ü[›™\‹[Øš™XÝYÜ›Ý\[›™\‹\™\Ù]YÜ›Ý\	ÊNÜÙXÝ[Û‹™]\Ù]œ™\Ù]Ø]YÛÜžOXØ]YÛÜžNÜÙXÝ[Û‹›Ü[]YNÜÙXÝ[Û‹˜\[™
›ÙJ	ÜÝ[[X\žIËØ]YÛÜžJJNÙ›ÜŠÛÛœÝ™\Ù]Ùˆ™\Ù]Ê^ØÛÛœÝYX]ÛŠ[

OOžÚYŠœ›ÝÜÙS[ÙHOOIÙY]	Ê]›ÝÈ\œ›ÜŠ	ÔÝÚ]ÚÈY]™Y›Ü™HY[™È˜]Ú[™ÜË‰ÊNÚYŠ^[Ý][˜Ù\Z[Š]›ÝÈ\œ›ÜŠ	ÐÚXÚÈHØ]™H™\Ý[™Y›Ü™HY][™Ë‰ÊNÜ[™[™Ô[]RÚ[™\™\Ù]šÚ[™Ü[™[™Ô[]S˜[YO\™\Ù]›˜[YNÜ[™[™Ô[]T™\Ù]\™\Ù]Ü[]Kœ]Y\žTÙ[XÝÜ[
	Ëœ[›™\‹[Øš™XÝœ[›™\‹\™\Ù]XØ\™	ÊK™›Ü‘XXÚ
][OOžØÛÛœÝXÝ]™OZ][OOOXYÚ][K˜Û\ÜÓ\ÝÙÙÛJ	ØXÝ]™IËXÝ]™JNÚ][KœÙ]]šX]J	Ø\šXK\™\ÜÙY	ËÝš[™ÊXÝ]™JJ_JNÝØ\Ý
	ÔÙ[XÝY	ÊÜ™\Ù]›˜[YJÉËˆÛXÚÈH[ˆÈXÙH]È™\ÜÈ\ØØ\HÈØ[˜Ù[‰ÊNÝšY]Ëœ]Y\žTÙ[XÝÜŠ	ÖÙ]K\[›™\‹XØ[˜\×IÊOË™›ØÝ\Ê
_K	Ü[›™\‹\™\Ù]XØ\™	ÊK\[›ÙJ	Ú[YÉË[	Ü[›™\‹\™\Ù]X\	ÊNØ\œÜ˜Ï\™\Ù]˜\ÜÙ]Ø\˜[IÉÎØ\œÙ]]šX]J	Ø\šXKZY[‰Ë	ÝYIÊNØ\›Û™\œ›ÜJ
OOžØÛÛœÝ˜[˜XÚÏ\[›™\”[]RXÛÛŠ™\Ù]›˜[YJNÙ˜[˜XÚË˜Û\ÜÓ\Ý˜Y
	Ü[›™\‹\™\Ù]X\	ÊNØ\œ™\XÙUÚ]
˜[˜XÚÊ_NØY™]\Ù]œ™\Ù]Y\™\Ù]šYØY™]\Ù]›Øš™XÝ˜[YO\™\Ù]›˜[YKÓÝÙ\Ø\ÙJ
NØYœÙ]]šX]J	Ø\šXK[X™[	Ë™\Ù]›˜[YJNØYœÙ]]šX]J	Ø\šXK\™\ÜÙY	ËÝš[™Ê[™[™Ô[]T™\Ù]ËšYOO\™\Ù]šY
JNØY™\ØX›YH[X[˜YÙ\Š
_œ›ÝÜÙS[ÙHOOIÙY]	ßH[^[Ý][˜Ù\Z[ŸJË‹‹›^[Ý]Ý]K\\Ë‹‹œ[›™\’Ú[™×Kš[˜ÛY\Ê™\Ù]šÚ[™
JNØY˜\[™
\›ÙJ	ÜÜ[‰Ë™\Ù]›˜[YK	Ü[›™\‹\™\Ù][˜[YIÊJNÜÙXÝ[Û‹˜\[™
Y
NÜ›ÝÜËœ\Ú
ÚÚ[™–Ü™\Ù]›˜[YK™\Ù]˜Ø]YÛÜžK™\Ù]šÚ[™Kš›Ú[Š	È	ÊKÓÝÙ\Ø\ÙJ
KYÙXÝ[ÛŸJ_\[™[˜\[™
ÙXÝ[ÛŠ_\™]\›ˆ[™[Y[˜Ý[ÛˆÛÜšÜÚÜZ[

^ØÛX\•ÛÜšÜÚÜšY]Ê
NÝ]J	ÕÛÜšÜÚÜ	ˆÝÜ˜YÙIË	ÔXÙH[™[œÜXÝ›ÛÛH˜]Ú[™ÜÈYØZ[œÝH˜]]™HÝÜ˜YÙH[‹‰ÊNÝšY]Ëœ]Y\žTÙ[XÝÜŠ	Ë]IÊOË˜Û\ÜÓ\Ý˜Y
	Ü[›™\‹\YÙK]]IÊNØÛÛœÝ›ÛÛ\Ï[^[Ý]˜YËœ›ÛÛ\ß×KÙ[XÝYXÝ\œ™[›ÛÛJ
KØš™XÝ\Ù[XÝYË›Øš™XÝË™š[™
›ÝÏOœ›ÝËšYOO[^[Ý]Ù[XÝY
_[ØÛÛœÝÛÜšÜÜXÙO[›ÙJ	Ù]‰Ë[	Ü›ÛÛK\[›™\‰ÊNÝÛÜšÜÜXÙK˜Û\ÜÓ\ÝÙÙÛJ	Ú\ËYY][™ÉËœ›ÝÜÙS[ÙOOOIÙY]	ÊNÝÛÜšÜÜXÙK˜Û\ÜÓ\ÝÙÙÛJ	Ú\ËXÛX[‹Xœ›ÝÜÙIËœ›ÝÜÙS[ÙOOOIØœ›ÝÜÙIÉ‰ˆ[^[Ý]\I‰ˆ[^[Ý][˜Ù\Z[ŠNÝÛÜšÜÜXÙK˜Û\ÜÓ\ÝÙÙÛJ	ÜÚÝË]ÛÛÉË[›™\”ÚÝÕÛÛÊNÝÛÜšÜÜXÙK˜Û\ÜÓ\ÝÙÙÛJ	ÜÚÝËZ[œÜXÝÜ‰Ë[›™\”ÚÝÒ[œÜXÝÜŠNØÛÛœÝÛÛ˜\[›ÙJ	Ù]‰Ë[	Ü[›™\‹]ÛÛ˜\‰ÊNØÛÛœÝXÚÙ\•Ü˜\[›ÙJ	ÛX™[	Ë	Ô›ÛÛIË	Ü[›™\‹\›ÛÛK\XÚÙ\‰ÊKXÚÙ\[›ÙJ	ÜÙ[XÝ	ÊNÜXÚÙ\‹œÙ]]šX]J	Ø\šXK[X™[	Ë	ÕÛÜšÜÚÜ›ÛÛIÊNÜXÚÙ\‹˜\[™
™]ÈÜ[ÛŠ	ÐÚÛÜÙHH›ÛÛIË	ÉÊJNÙ›ÜŠÛÛœÝ›ÛÛHÙˆ›ÛÛ\Ê\XÚÙ\‹˜\[™
™]ÈÜ[ÛŠ›ÛÛK›˜[YK›ÛÛKšY
JNÜXÚÙ\‹˜[YO\Ù[XÝYËšY	ÉÎÜXÚÙ\‹™\ØX›YHH[^[Ý][˜Ù\Z[ŽÜXÚÙ\‹›Û˜Ú[™ÙOJ
OOœÙ[XÝ›ÛÛJXÚÙ\‹˜[Y_[
NÜXÚÙ\•Ü˜\˜\[™
XÚÙ\ŠNÝÛÛ˜\‹˜\[™
XÚÙ\•Ü˜\
NØÛÛœÝ[Ù\Ï[›ÙJ	Ù]‰Ë[	Ü[›™\‹[[Ù\ÉÊNØÛÛœÝœ›ÝÜÙOX]ÛŠ	Ðœ›ÝÜÙIË

OOžØØ[˜Ù[[™[™Ô[]TXÙ[Y[

NØœ›ÝÜÙS[ÙOIØœ›ÝÜÙIÎÝÛÜšÜÚÜZ[

_Kœ›ÝÜÙS[ÙOOOIØœ›ÝÜÙIÏÉØXÝ]™IÎ‰ÉÊKY]X]ÛŠ	ÑY]	Ë

OOžØœ›ÝÜÙS[ÙOIÙY]	ÎÝÛÜšÜÚÜZ[

_Kœ›ÝÜÙS[ÙOOOIÙY]	ÏÉØXÝ]™IÎ‰ÉÊNÙY]™\ØX›YH[X[˜YÙ\Š
_H[^[Ý][˜Ù\Z[ŽØœ›ÝÜÙKœÙ]]šX]J	Ø\šXK\™\ÜÙY	ËÝš[™Êœ›ÝÜÙS[ÙOOOIØœ›ÝÜÙIÊJNÙY]œÙ]]šX]J	Ø\šXK\™\ÜÙY	ËÝš[™Êœ›ÝÜÙS[ÙOOOIÙY]	ÊJNÛ[Ù\Ë˜\[™
œ›ÝÜÙKY]
NÝÛÛ˜\‹˜\[™
[Ù\ÊNØÛÛœÝÝ]\Ï[›ÙJ	ÜÜ[‰Ë^[Ý][˜Ù\Z[ÉÔØ]™H™\Ý[™YYÈÚXÚÚ[™ÉÎ›^[Ý]\OÉÕ[œØ]™Y›ÛÛHÚ[™Ù\ÉÎ‰Ð[›ÛÛHÚ[™Ù\ÈØ]™Y	Ë	Ü[›™\‹\Ø]™K\Ý]IÊNÜÝ]\Ë™]\Ù]œ›ÛÛTØ]™TÝ]OIÝYIÎÜÝ]\ËœÙ]]šX]J	Ü›ÛIË	ÜÝ]\ÉÊNÝÛÛ˜\‹˜\[™
Ý]\ÊNØÛÛœÝØ]™OX]ÛŠ	ÔØ]™HÚ[™Ù\ÉËØ]™S^[Ý]	ÛXZ[‰ÊNÜØ]™K˜Û\ÜÓ\Ý˜Y
	Ü[›™\‹\Ø]™KX]Û‰ÊNÜØ]™KœÙ]]šX]J	Ø\šXK[X™[	Ë	ÔØ]™H[›ÛÛHÚ[™Ù\ÉÊNÜØ]™K™\ØX›YH[^[Ý]\_H[^[Ý][˜Ù\Z[Ÿ[X[˜YÙ\Š
NÝÛÛ˜\‹˜\[™
Ø]™JNÚYŠ^[Ý][˜Ù\Z[Š]ÛÛ˜\‹˜\[™
]ÛŠ	ÐÚXÚÈØ]™HÝ]\ÉËÚXÚÓ^[Ý]Ø]™TÝ]\Ë	Ø][[Û‰ÊJNÚYŠ^[Ý]Ø]™Q\œ›ÜŠ^ØÛÛœÝY\ÜØYÙP›Þ[Y\ÜØYÙJ^[Ý]Ø]™Q\œ›Ü‹	Ù\œ›Ü‰ÊNÛY\ÜØYÙP›ÞœÙ]]šX]J	Ü›ÛIË	Ø[\	ÊNÝÛÛ˜\‹˜\[™
Y\ÜØYÙP›Þ]ÛŠ	Ô™[ØYØ]™Y[‰Ë™[ØYØ]™Y[ŠJ_ZYŠX[˜YÙ\Š
J]ÛÛ˜\‹˜\[™
Øš™XÝ˜\ÜÚYÛŠ]ÛŠ	ÐÜ™X]H›ÛÛIË

OOžØœ›ÝÜÙS[ÙOIÙY]	ÎØÜ™X]Q[\T›ÛÛJ
_K	Ü[›™\‹[™]Ë\›ÛÛIÊKÙ\ØX›YˆH[^[Ý][˜Ù\Z[Ÿ›ÛÛ\Ë›[™ÝLŒJJNØÛÛœÝÛÛÕÙÙÛOX]ÛŠ	ÓØš™XÝÉË

OOžÜ[›™\”ÚÝÕÛÛÏH\[›™\”ÚÝÕÛÛÎÝÛÜšÜÜXÙK˜Û\ÜÓ\ÝÙÙÛJ	ÜÚÝË]ÛÛÉË[›™\”ÚÝÕÛÛÊNÝÛÛÕÙÙÛKœÙ]]šX]J	Ø\šXKY^[™Y	ËÝš[™Ê[›™\”ÚÝÕÛÛÊJ_K	Ü[›™\‹\[™[]ÙÙÛH[›™\‹]ÛÛË]ÙÙÛIÊK[œÜXÝÜ•ÙÙÛOX]ÛŠ	Ñ]Z[ÉË

OOžÜ[›™\”ÚÝÒ[œÜXÝÜH\[›™\”ÚÝÒ[œÜXÝÜŽÝÛÜšÜÜXÙK˜Û\ÜÓ\ÝÙÙÛJ	ÜÚÝËZ[œÜXÝÜ‰Ë[›™\”ÚÝÒ[œÜXÝÜŠNÚ[œÜXÝÜ•ÙÙÛKœÙ]]šX]J	Ø\šXKY^[™Y	ËÝš[™Ê[›™\”ÚÝÒ[œÜXÝÜŠJ_K	Ü[›™\‹\[™[]ÙÙÛH[›™\‹Y]Z[Ë]ÙÙÛIÊNÝÛÛÕÙÙÛKœÙ]]šX]J	Ø\šXKY^[™Y	ËÝš[™Ê[›™\”ÚÝÕÛÛÊJNÚ[œÜXÝÜ•ÙÙÛKœÙ]]šX]J	Ø\šXKY^[™Y	ËÝš[™Ê[›™\”ÚÝÒ[œÜXÝÜŠJNÚYŠœ›ÝÜÙS[ÙOOOIÙY]	Ê]ÛÛ˜\‹˜\[™
ÛÛÕÙÙÛJNÝÛÛ˜\‹˜\[™
[œÜXÝÜ•ÙÙÛJNÝÛÜšÜÜXÙK˜\[™
ÛÛ˜\ŠNÚYŠœ›ÝÜÙS[ÙOOOIØœ›ÝÜÙIÊ]ÛÜšÜÜXÙK˜\[™
[›™\”]ZXÚÔÙX\˜Ú

JNÚYŠÛÜšÜÚÜ™Yœ™\ÚÚÚ\Y
]ÛÜšÜÜXÙK˜\[™
Y\ÜØYÙJ	ÐH˜]]™H™Yœ™\ÚÝ™\›\YHØ]™Kˆ™Yœ™\Ú˜]]™HÝ]\ÈÈØYÝ\œ™[™XÛÜ™Ë‰Ë	Ø][[Û‰ÊJNÚYŠ›ÛÛPÚÛÜÙ\“Y\ÜØYÙJ]ÛÜšÜÜXÙK˜\[™
Y\ÜØYÙJ›ÛÛPÚÛÜÙ\“Y\ÜØYÙK	Ø][[Û‰ÊJNØÛÛœÝÛÛ[[›ÙJ	Ù]‰Ë[	Ü[›™\‹]ÛÜšÜÜXÙIÊNØÛÛœÝ[]O[›ÙJ	Ø\ÚYIË[	Ü[›™\‹\[]IÊNÜ[]KœÙ]]šX]J	Ü›ÛIË	Ü™YÚ[Û‰ÊNÜ[]KœÙ]]šX]J	Ø\šXK[X™[	Ë	ÓØš™XÝ[]IÊNÜ[]K˜\[™
›ÙJ	Ú‰Ë	ÓØš™XÝÉÊJNØÛÛœÝÙX\˜Ú[›ÙJ	Ú[œ]	ÊNÜÙX\˜Ú\OIÜÙX\˜Ú	ÎÜÙX\˜ÚœXÙZÛ\IÔÙX\˜ÚØš™XÝÉÎÜÙX\˜ÚœÙ]]šX]J	Ø\šXK[X™[	Ë	ÔÙX\˜ÚØš™XÝÉÊNÜ[]K˜\[™
ÙX\˜Ú
NØÛÛœÝÚ[™ÏVË‹‹›™]ÈÙ]
Ë‹‹Š^[Ý]Ý]OË\\ß×JK‹‹œ[›™\’Ú[™Ë‹‹–ÉÌÑš[\‰Ë	ÐÓÈXXÚ[™I×K™š[\ŠÚ[™OˆJ^[Ý]Ý]OË\\ß×JKš[˜ÛY\ÊÚ[™
JWJWKÜ›Ý\Ï[™]ÈX\

NÙ›ÜŠÛÛœÝÚ[™ÙˆÚ[™Ê^ØÛÛœÝÜ›Ý\\[›™\’Ú[™Ü›Ý\
Ú[™
NÚYŠYÜ›Ý\Ëš\ÊÜ›Ý\
JYÜ›Ý\ËœÙ]
Ü›Ý\×JNÙÜ›Ý\Ë™Ù]
Ü›Ý\
Kœ\Ú
Ú[™
_XÛÛœÝ›ÝÜÏV×NÙ›ÜŠÛÛœÝÛ˜[YK][\×HÙˆÜ›Ý\Ê^ØÛÛœÝÙXÝ[Û[›ÙJ	Ù]Z[ÉË[	Ü[›™\‹[Øš™XÝYÜ›Ý\	ÊNÜÙXÝ[Û‹›Ü[]YNÜÙXÝ[Û‹˜\[™
›ÙJ	ÜÝ[[X\žIË˜[YJJNÙ›ÜŠÛÛœÝÚ[™Ùˆ][\Ê^ØÛÛœÝXÝX[Ú[™VÉÌÑš[\‰Ë	ÐÓÈXXÚ[™I×Kš[˜ÛY\ÊÚ[™
I‰ˆJ^[Ý]Ý]OË\\ß×JKš[˜ÛY\ÊÚ[™
OÉÓZ\ØÉÎšÚ[™™\Ù]˜[YOXXÝX[Ú[™OOZÚ[™Û[šÚ[™YX]ÛŠ[

OOžÚYŠœ›ÝÜÙS[ÙHOOIÙY]	Ê]›ÝÈ\œ›ÜŠ	ÔÝÚ]ÚÈY]™Y›Ü™HY[™È˜]Ú[™ÜË‰ÊNÚYŠ^[Ý][˜Ù\Z[Š]›ÝÈ\œ›ÜŠ	ÐÚXÚÈHØ]™H™\Ý[™Y›Ü™HY][™Ë‰ÊNÜ[™[™Ô[]RÚ[™XXÝX[Ú[™Ü[™[™Ô[]S˜[YO\™\Ù]˜[YNÜ[™[™Ô[]T™\Ù][[Ü[]Kœ]Y\žTÙ[XÝÜ[
	Ëœ[›™\‹[Øš™XÝœ[›™\‹\™\Ù]XØ\™	ÊK™›Ü‘XXÚ
][OOžØÛÛœÝXÝ]™OZ][OOOXYÚ][K˜Û\ÜÓ\ÝÙÙÛJ	ØXÝ]™IËXÝ]™JNÚ][KœÙ]]šX]J	Ø\šXK\™\ÜÙY	ËÝš[™ÊXÝ]™JJ_JNÝØ\Ý
	ÔÙ[XÝY	ÊÊ™\Ù]˜[Y_XÝX[Ú[™
JÉËˆÛXÚÈH[ˆÈXÙH]È™\ÜÈ\ØØ\HÈØ[˜Ù[‰ÊNÝšY]Ëœ]Y\žTÙ[XÝÜŠ	ÖÙ]K\[›™\‹XØ[˜\×IÊOË™›ØÝ\Ê
_K	Ü[›™\‹[Øš™XÝ	ÊNØY˜\[™
[›™\”[]RXÛÛŠÚ[™
K›ÙJ	ÜÜ[‰ËÚ[™
JNØY™\ØX›YH[X[˜YÙ\Š
_œ›ÝÜÙS[ÙHOOIÙY]	ßH[^[Ý][˜Ù\Z[ŽØYœÙ]]šX]J	Ø\šXK\™\ÜÙY	ËÝš[™Ê[™[™Ô[]RÚ[™OOXXÝX[Ú[™	‰œ[™[™Ô[]S˜[YOOO\™\Ù]˜[YJJNØY™]\Ù]›Øš™XÝ˜[YOZÚ[™ÓÝÙ\Ø\ÙJ
NÜÙXÝ[Û‹˜\[™
Y
NÜ›ÝÜËœ\Ú
ÚÚ[™YÙXÝ[ÛŸJ_\[]K˜\[™
ÙXÝ[ÛŠ_XÛÛœÝ™\Ù][]O\[›™\”™\Ù][]J[]K›ÝÜÊNÜ[]Kš[œÙ\™Y›Ü™J™\Ù][]KÙX\˜Ú›™^ÚX›[™ÊNÜÙX\˜Ú›Ûš[œ]J
OOžØÛÛœÝ]Y\žO\ÙX\˜Ú˜[YKš[J
KÓÝÙ\Ø\ÙJ
NÙ›ÜŠÛÛœÝ›ÝÈÙˆ›ÝÜÊ\›ÝË˜YšY[H\›ÝËšÚ[™ÓÝÙ\Ø\ÙJ
Kš[˜ÛY\Ê]Y\žJNÙ›ÜŠÛÛœÝÙXÝ[ÛˆÙˆ[]Kœ]Y\žTÙ[XÝÜ[
	Ëœ[›™\‹[Øš™XÝYÜ›Ý\	ÊJ\ÙXÝ[Û‹šY[HP\œ˜^K™œ›ÛJÙXÝ[Û‹œ]Y\žTÙ[XÝÜ[
	Ëœ[›™\‹[Øš™XÝœ[›™\‹\™\Ù]XØ\™	ÊJKœÛÛYJ][OOˆZ][KšY[Š_NÜ[]K˜\[™
›ÙJ	Ü	Ëœ›ÝÜÙS[ÙOOOIÙY]	ÏÉÐÚÛÜÙHH˜]Ú[™Ë[ˆÛXÚÈH[ˆÈXÙH]‰Î‰ÔÝÚ]ÚÈY]ÈXÙHÜˆ[šÈ˜]Ú[™ÜË‰Ë	ÜÝX‰ÊJNØÛÛœÝÝÜ˜YÙO[›ÙJ	Ù]Z[ÉË[	Ü[›™\‹\ÝÜ˜YÙIÊNÛ]ÝÜ˜YÙTZ[YY˜[ÙNÜÝÜ˜YÙK˜\[™
›ÙJ	ÜÝ[[X\žIË	Ó˜]]™HÝÜ˜YÙIÊJNÜÝÜ˜YÙK˜Y]™[\Ý[™\Š	ÝÙÙÛIË

OOžÚYŠÝÜ˜YÙK›Ü[‰‰ˆ\ÝÜ˜YÙTZ[Y
^ÜÝÜ˜YÙTZ[Y]YNÜZ[ÝÜ˜YÙJÝÜ˜YÙJ__JNÜ[]K˜\[™
ÝÜ˜YÙJNØÛÛœÝØ[˜\Ô[™[[›ÙJ	ÜÙXÝ[Û‰Ë[	Ü[›™\‹XØ[˜\Ë\[™[	ÊNØØ[˜\Ô[™[œÙ]]šX]J	Ü›ÛIË	Ü™YÚ[Û‰ÊNØØ[˜\Ô[™[œÙ]]šX]J	Ø\šXK[X™[	Ë	Ô›ÛÛH[ˆØ[˜\ÉÊNØØ[˜\Ô[™[˜\[™
›ÙJ	Ù]‰Ë	Ì‘›ÛÛH[‰Ë	Ü[›™\‹XØ[˜\Ë]]IÊJNØÛÛœÝØ[˜\ÕÛÛÏ[›ÙJ	Ù]‰Ë[	Ü[›™\‹XØ[˜\Ë]ÛÛÉÊNØÛÛœÝÜšYÙÙÛOXÚXÚØ›Þ
Ø[˜\ÕÛÛË	ÔÚÝÈ]X\\‹Y›ÛÝÜšY	Ë[›™\‘ÜšY˜[YOOžÜ[›™\‘ÜšY]˜[YNÝÛÜšÜÚÜZ[

_JNÙÜšYÙÙÛK™\ØX›YH\Ù[XÝYØÛÛœÝÛ˜\ÙÙÛOXÚXÚØ›Þ
Ø[˜\ÕÛÛË	ÔÛ˜\È]X\\‹Y›ÛÝÜšY	Ë[›™\”Û˜\˜[YOOžÜ[›™\”Û˜\]˜[Y_JNÜÛ˜\ÙÙÛK™\ØX›YH\Ù[XÝYœ›ÝÜÙS[ÙHOOIÙY]	ßH[^[Ý][˜Ù\Z[ŽØÛÛœÝ›ÛÛT™XYÝ][›ÙJ	ÜÜ[‰ËX]œ›Ý[™
[›™\–›ÛÛJŒL
JÉÉIË	Ü[›™\‹^›ÛÛK\™XYÝ]	ÊNØØ[˜\ÕÛÛË˜\[™
]ÛŠ	Ö›ÛÛH[‰Ë

OOžÜ[›™\–›ÛÛOSX]›Z[ŠË[›™\–›ÛÛJŒKŒŠNÝÛÜšÜÚÜZ[

_JK]ÛŠ	Ö›ÛÛHÝ]	Ë

OOžÜ[›™\–›ÛÛOSX]›X^
K[›™\–›ÛÛKÌKŒŠNÝÛÜšÜÚÜZ[

_JK]ÛŠ	Ñš]›ÛÛIË

OOžÜ[›™\–›ÛÛOLNÜ[›™\”[^ÞŒNŒNÝÛÜšÜÚÜZ[

_JK]ÛŠ	Ô[ˆY	Ë

OOžÜ[›™\”[‹žO\Ù[XÝYËÚY
‹ŒNÝÛÜšÜÚÜZ[

_JK]ÛŠ	Ô[ˆšYÚ	Ë

OOžÜ[›™\”[‹ž
Ï\Ù[XÝYËÚY
‹ŒNÝÛÜšÜÚÜZ[

_JK›ÛÛT™XYÝ]
NÚYŠX[˜YÙ\Š
I‰˜œ›ÝÜÙS[ÙOOOIÙY]	Ê^ØÛÛœÝ[™ÏX]ÛŠ	Õ[™ÉË[™Ô›ÛÛJNÝ[™Ë™\ØX›YHH[^[Ý][˜Ù\Z[ŸJ›ÛÛU[™Ë™Ù]
XÝ]™T›ÛÛRY
OË›[™Ý
NØÛÛœÝ™YÏX]ÛŠ	Ô™YÉË™YÔ›ÛÛJNÜ™YË™\ØX›YHH[^[Ý][˜Ù\Z[ŸJ›ÛÛT™YË™Ù]
XÝ]™T›ÛÛRY
OË›[™Ý
NØØ[˜\ÕÛÛË˜\[™
[™Ë™YÊ_XØ[˜\Ô[™[˜\[™
Ø[˜\ÕÛÛÊNØÛÛœÝØ[˜\Ñœ˜[YO[›ÙJ	Ù]‰Ë[	Ü[›™\‹XØ[˜\ËYœ˜[YIÊNØØ[˜\Ñœ˜[YKœÙ]]šX]J	Ù]K\›ÛÛK]ÚY	ËÝš[™ÊÙ[XÝYËÚY
JNØØ[˜\Ñœ˜[YKœÙ]]šX]J	Ù]K\›ÛÛKZZYÚ	ËÝš[™ÊÙ[XÝYËšZYÚ
JNÜZ[[›™\Ø[˜\ÊÙ[XÝYØ[˜\Ñœ˜[YJNØØ[˜\Ô[™[˜\[™
Ø[˜\Ñœ˜[YJNØÛÛœÝYÙ[™[›ÙJ	Ù]‰Ë[	Ü[›™\‹[YÙ[™	ÊNÙ›ÜŠÛÛœÝÚÚ[™X™[HÙˆÖÉÛ[šÙY	Ë	Ó[šÙYÈ˜]]™HÝÜ˜YÙI×KÉÙ˜]Ú[™Ë[Û›IË	Ñ˜]Ú[™ÈÛ›I×WJ^ØÛÛœÝ][O[›ÙJ	ÜÜ[‰ËX™[	Ü[›™\‹ZÙ^H[›™\‹ZÙ^KIÊÚÚ[™
NÚ][Kœ™\[™
›ÙJ	ÜÜ[‰Ë	ÉË	Ü[›™\‹ZÙ^KYÝ	ÊJNÛYÙ[™˜\[™
][J_[YÙ[™˜\[™
›ÙJ	ÜÜ[‰Ë	Ô›ÛÛH[š]Îˆ	ÊÊÙ[XÝYË[š]	Ù	ÊK	Ü[›™\‹][š][›ÝIÊJNØØ[˜\Ô[™[˜\[™
YÙ[™
NØÛÛœÝ]Z[Ï[›ÙJ	Ø\ÚYIË[	Ü[›™\‹Z[œÜXÝÜ‰ÊNÙ]Z[ËœÙ]]šX]J	Ü›ÛIË	Ü™YÚ[Û‰ÊNÙ]Z[ËœÙ]]šX]J	Ø\šXK[X™[	Ë	ÕÛÜšÜÚÜ[œÜXÝÜ‰ÊNÜ›ÛÛR[œÜXÝÜŠÙ[XÝYØš™XÝ]Z[ÊNØÛÛ[˜\[™
[]KØ[˜\Ô[™[]Z[ÊNÝÛÜšÜÜXÙK˜\[™
ÛÛ[
NÜÚÝÐÛÝ™\˜YÙJÛÜšÜÜXÙJNÝšY]Ë˜\[™
ÛÜšÜÜXÙJ_B™[˜Ý[ÛˆZ[[\UÛÜšÜÚÜ

^ÝÛÜšÜÚÜZ[

_B™[˜Ý[ÛˆÛÜšÜÚÜÙX\˜Ú™\]Y\ÝÝ\œ™[
ÚÙ[‹Y[]KÝÛ™\‹›Ý]KÙ[XÝ[Û‘Ù[™\˜][ÛŠ^Ü™]\›ˆY\ÜÜÙY	‰ÚÙ[OO]ÛÜšÜÚÜÙX\˜ÚÚÙ[‰‰˜Ý\œ™[OOIÝÛÜšÜÚÜ	É‰œ›Ý]OOO\›Ý]U™\œÚ[Û‰‰œÙ[XÝ[Û‘Ù[™\˜][ÛOO]ÛÜšÜÚÜÙ[XÝ[Û‘Ù[™\˜][Û‰‰šY[]OOOXÛÛ^ËšY[]I‰›ÝÛ™\OO\ØÛÜJ
_B™[˜Ý[Ûˆ™[™\•ÛÜšÜÚÜÙX\˜Ú›ÝÜÊ\™Ù]\›ÛÝœ]Y\žTÙ[XÝÜŠ	ËÛÜšÜÚÜ\ÙX\˜Ú\™\Ý[ÉÊJ^ÚYŠ\ÜÜÙYÝ\œ™[OOIÝÛÜšÜÚÜ	ßXÛÛ^
^ÝÛÜšÜÚÜÙX\˜Ú™[™\”[™[™ÏY˜[ÙNÜ™]\›ˆ[ZYŠ]\™Ù]
\™]\›ˆ[ÚYŠ\ÞJ^ÝÛÜšÜÚÜÙX\˜Ú™[™\”[™[™Ï]YNÜ™]\›ˆ\™Ù]]ÛÜšÜÚÜÙX\˜Ú™[™\”[™[™ÏY˜[ÙNÝ\™Ù]œ™\XÙPÚ[™[Š
NÚYŠ]ÛÜšÜÚÜÙX\˜Ú›ÝÜßÛÜšÜÚÜÙX\˜ÚY[]HOOXÛÛ^ËšY[]_ÛÜšÜÚÜÙX\˜ÚÝÛ™\ˆOO\ØÛÜJ
J\™]\›ˆ\™Ù]ØÛÛœÝO]ÛÜšÜÚÜÙX\˜Ú^š[J
KÓÝÙ\Ø\ÙJ
KX]Ú\Ï]ÛÜšÜÚÜÙX\˜Ú›ÝÜË™š[\Š›ÝÏO–Ü›ÝË›˜[YK›ÝË˜\ÜÙ]Y›ÝËœÙ\šX[[X™\‹›ÝË›X[Y˜XÝ\™\‹›ÝË›[Ù[›ÝËšYKš›Ú[Š	È	ÊKÓÝÙ\Ø\ÙJ
Kš[˜ÛY\ÊJJNÚYŠ[X]Ú\Ë›[™Ý
^Ý\™Ù]˜\[™
›ÙJ	Ü	Ë	Ó›È˜]]™H™XÛÜ™ÈX]Úˆ[šÛ›ÝÛˆÜˆX[Y˜XÝ\™\‹[Û›HÛÙ\ÈÈ›ÝÙ[XÝH™XÛÜ™‰ÊJNÜ™]\›ˆ\™Ù]Y›ÜŠÛÛœÝ›ÝÈÙˆX]Ú\ËœÛXÙJŒ
J^ØÛÛœÝ][O[›ÙJ	Ù]‰Ë[	ÜÙX\˜Ú\™\Ý[	ÊK][˜]]™S˜[YT]
›ÝÊK˜[YO\›ÝË›˜[Y_	Õ[›˜[YY™XÛÜ™	Ë\ÜÙ]\›ÝË˜\ÜÙ]Y	Ó›È\ÜÙ]ÛÙIË]Û”›ÝÏX]ÛŠ˜[YJÉÈ0­È	ÊØ\ÜÙ]
ÉÈ0­È	ÊÜ]
ÉÈ0­È	ÊÜ›ÝËšY

OOœÙ[XÝÛÜšÜÚÜ[]J›ÝËšYYJJNØ]Û”›ÝËœÙ]]šX]J	Ø\šXK[X™[	Ë˜[YJÉÈ0­È\ÜÙ]ÛÙH	ÊØ\ÜÙ]
ÉÈ0­È	ÊÜ]
ÉÈ0­ÈURQ	ÊÜ›ÝËšY
NÚ][K˜\[™
]Û”›ÝÊNÝ\™Ù]˜\[™
][J_\™]\›ˆ\™Ù]B™[˜Ý[ÛˆÛÛ™šYÝ\™UÛÜšÜÚÜÙX\˜Ú
ÙX\˜Ú™\Ý[Ê^ÜÙX\˜Ú›Ûš[œ]X\Þ[˜Ê
OOžÝÛÜšÜÚÜÙX\˜Ú^\ÙX\˜Ú˜[YNØÛÛœÝY[]OXÛÛ^ËšY[]KÝÛ™\\ØÛÜJ
K›Ý]O\›Ý]U™\œÚ[Û‹Ù[XÝ[Û‘Ù[™\˜][Û]ÛÜšÜÚÜÙ[XÝ[Û‘Ù[™\˜][Û‹ÚÙ[JÊÝÛÜšÜÚÜÙX\˜ÚÚÙ[ŽÚYŠZY[]_Ý\œ™[OOIÝÛÜšÜÚÜ	ß\ÜÜÙY
\™]\›ŽÚYŠÛÜšÜÚÜÙX\˜ÚY[]HOOZY[]_ÛÜšÜÚÜÙX\˜ÚÝÛ™\ˆOO[ÝÛ™\Š^ÝÛÜšÜÚÜÙX\˜Ú›ÝÜÏ[[ÝÛÜšÜÚÜÙX\˜ÚY[]O[[ÝÛÜšÜÚÜÙX\˜ÚÝÛ™\[[ZYŠ]ÛÜšÜÚÜÙX\˜Ú›ÝÜÊ^Ýž^ØÛÛœÝÙ›Ý[™\]Z\Y[›Ý[™ØØ][Ûœ×OX]ØZ]›ÛZ\ÙK˜[
Ø\J	Ù\]Z\Y[	Ë[™Yš[™YY[]JK\J	ÛØØ][ÛœÉË[™Yš[™YY[]JWJNÚYŠ]ÛÜšÜÚÜÙX\˜Ú™\]Y\ÝÝ\œ™[
ÚÙ[‹Y[]KÝÛ™\‹›Ý]KÙ[XÝ[Û‘Ù[™\˜][ÛŠJ\™]\›ŽÝÛÜšÜÚÜÙX\˜Ú›ÝÜÏVË‹‹™›Ý[™\]Z\Y[‹‹™›Ý[™ØØ][Ûœ×K™š[\Š›ÝÏOˆ\›ÝË˜\˜Ú]™Y
NÝÛÜšÜÚÜÙX\˜ÚY[]OZY[]NÝÛÜšÜÚÜÙX\˜ÚÝÛ™\[ÝÛ™\ŸXØ]ÚÚYŠ]ÛÜšÜÚÜÙX\˜Ú™\]Y\ÝÝ\œ™[
ÚÙ[‹Y[]KÝÛ™\‹›Ý]KÙ[XÝ[Û‘Ù[™\˜][ÛŠJ\™]\›ŽÝÛÜšÜÚÜÙX\˜Ú›ÝÜÏV×NÝÛÜšÜÚÜÙX\˜ÚY[]OZY[]NÝÛÜšÜÚÜÙX\˜ÚÝÛ™\[ÝÛ™\Ÿ_ZYŠ]ÛÜšÜÚÜÙX\˜Ú™\]Y\ÝÝ\œ™[
ÚÙ[‹Y[]KÝÛ™\‹›Ý]KÙ[XÝ[Û‘Ù[™\˜][ÛŠJ\™]\›ŽÜ™[™\•ÛÜšÜÚÜÙX\˜Ú›ÝÜÊ™\Ý[Ê_NÜÙX\˜Ú›ÛšÙ^YÝÛX\Þ[˜ÈOOžÚYŠKšÙ^HOOIÑ[\‰Ê\™]\›ŽÙKœ™]™[Y˜][

NØÛÛœÝ˜]Ï\ÙX\˜Ú˜[YKš[J
NÚYŠ\˜]ß\ÞJ\™]\›ŽÝÛÜšÜÚÜÙX\˜Ú^\˜]ÎØÛÛœÝY[]OXÛÛ^ËšY[]KÝÛ™\\ØÛÜJ
K›Ý]O\›Ý]U™\œÚ[Û‹Ù[XÝ[Û‘Ù[™\˜][Û]ÛÜšÜÚÜÙ[XÝ[Û‘Ù[™\˜][Û‹ÚÙ[JÊÝÛÜšÜÚÜÙX\˜ÚÚÙ[ŽÛ]™\ÛÛ™YÝž^Ü™\ÛÛ™YX]ØZ]\J	ÝÛÜšÜÚÜÜ™\ÛÛ™IËØÛÙNœ˜]ßKY[]J_XØ]Ú
\œ›ÜŠ^ÚYŠÛÜšÜÚÜÙX\˜Ú™\]Y\ÝÝ\œ™[
ÚÙ[‹Y[]KÝÛ™\‹›Ý]KÙ[XÝ[Û‘Ù[™\˜][ÛŠJ\™\Ü
\œ›ÜŠNÜ™]\›ŸZYŠ]ÛÜšÜÚÜÙX\˜Ú™\]Y\ÝÝ\œ™[
ÚÙ[‹Y[]KÝÛ™\‹›Ý]KÙ[XÝ[Û‘Ù[™\˜][ÛŠ_\ÞJ\™]\›ŽÚYŠ™\ÛÛ™Y™[]WÚY
^Ø]ØZ]Ù[XÝÛÜšÜÚÜ[]J™\ÛÛ™Y™[]WÚYYJNÜ™]\›ŸZYŠÛÜšÜÚÜÙX\˜ÚY[]HOOZY[]_ÛÜšÜÚÜÙX\˜ÚÝÛ™\ˆOO[ÝÛ™\Š^ÝÛÜšÜÚÜÙX\˜Ú›ÝÜÏ[[ÝÛÜšÜÚÜÙX\˜ÚY[]O[[ÝÛÜšÜÚÜÙX\˜ÚÝÛ™\[[XÛÛœÝ\™Ù]\™[™\•ÛÜšÜÚÜÙX\˜Ú›ÝÜÊ™\Ý[ÊNÝ\™Ù]Ëœ™\[™
Y\ÜØYÙJ™\ÛÛ™Y›Y\ÜØYÙ_	Ó›È[š\]YH˜]]™H™XÛÜ™›Ý[™ˆÙX\˜ÚžH˜]]™H˜[YHÜˆ\ÜÙ]]Z[Ë‰ÊJ_NßB™[˜Ý[Ûˆ[›™\”]ZXÚÔÙX\˜Ú

^ØÛÛœÝ™YÚ[Û[›ÙJ	Ù]‰Ë[	Ü[›™\‹\]ZXÚË\ÙX\˜Ú	ÊNÜ™YÚ[Û‹œÙ]]šX]J	Ü›ÛIË	ÜÙX\˜Ú	ÊNØÛÛœÝX™[[›ÙJ	ÛX™[	Ë	ÔÙX\˜Ú˜]]™H™XÛÜ™ÉË	ÙšY[	ÊKÙX\˜Ú[›ÙJ	Ú[œ]	ÊNÜÙX\˜Ú\OIÜÙX\˜Ú	ÎÜÙX\˜ÚœXÙZÛ\IÓ˜[YK\ÜÙ]ÛÙKÙ\šX[X[Y˜XÝ\™\‹ÜˆURQ	ÎÜÙX\˜ÚœÙ]]šX]J	Ø\šXK[X™[	Ë	ÔÙX\˜Ú˜]]™H™XÛÜ™ÉÊNÜÙX\˜Ú˜[YO]ÛÜšÜÚÜÙX\˜Ú^ØÛÛœÝ™\Ý[Ï[›ÙJ	Ù]‰Ë[	ÝÛÜšÜÚÜ\ÙX\˜Ú\™\Ý[È[›™\‹\ÙX\˜Ú\™\Ý[ÉÊNØÛÛ™šYÝ\™UÛÜšÜÚÜÙX\˜Ú
ÙX\˜Ú™\Ý[ÊNÛX™[˜\[™
ÙX\˜Ú
NÜ™YÚ[Û‹˜\[™
X™[™\Ý[ÊNÜ™[™\•ÛÜšÜÚÜÙX\˜Ú›ÝÜÊ™\Ý[ÊNÜ™]\›ˆ™YÚ[ÛŸB™[˜Ý[ÛˆZ[ÛÜšÜÚÜœ›ÝÜÙJ\™[
^ØÛÛœÝœ›ÝÜÙO\[™[
›ÙJ	Ú‰Ë	Ó˜]]™Hœ›ÝÜÙH	ˆÙ]\	ÊJKÙX\˜Ú[›ÙJ	Ú[œ]	ÊNÜÙX\˜Ú\OIÜÙX\˜Ú	ÎÜÙX\˜ÚœXÙZÛ\IÔÙX\˜Ú˜]]™H˜[YK\ÜÙ]ÛÙKÙ\šX[X[Y˜XÝ\™\‰ÎÜÙX\˜ÚœÙ]]šX]J	Ø\šXK[X™[	Ë	ÔÙX\˜Ú˜]]™H\]Z\Y[[™ÝÜ˜YÙIÊNÜÙX\˜Ú˜[YO]ÛÜšÜÚÜÙX\˜Ú^ØÛÛœÝ™\Ý[Ï[›ÙJ	Ù]‰Ë[	ÝÛÜšÜÚÜ\ÙX\˜Ú\™\Ý[ÉÊNØÛÛ™šYÝ\™UÛÜšÜÚÜÙX\˜Ú
ÙX\˜Ú™\Ý[ÊNØœ›ÝÜÙK˜\[™
ÙX\˜Ú™\Ý[ÊNÜ™[™\•ÛÜšÜÚÜÙX\˜Ú›ÝÜÊ™\Ý[ÊNØÛÛœÝ™Yœ™\ÚX™[]ÛÜšÜÚÜšY]ÏËœ™Yœ™\ÚYØ]Û™]È]JÛÜšÜÚÜšY]Ëœ™Yœ™\ÚYØ]
KÓØØ[TÝš[™Ê
N‰Ó›Ý™Yœ™\ÚY	ÎØœ›ÝÜÙK˜\[™
›ÙJ	Ü	Ë	Ó\Ý™Yœ™\ÚYˆ	ÊÜ™Yœ™\ÚX™[	ÜÝX‰ÊJNÚYŠ]ÛÜšÜÚÜšY]Ð]˜Z[X›J^Øœ›ÝÜÙK˜\[™
Y\ÜØYÙJ	ÔÝ]\È[˜]˜Z[X›IË	Ù\œ›Ü‰ÊJNÚYŠÛÜšÜÚÜšY]Ñ\œ›ÜŠXœ›ÝÜÙK˜\[™
›ÙJ	Ü	Ë	Ó˜]]™HÝ]\ÈÛÝ[›Ý™H™Yœ™\ÚYˆØXÚY\]Z\Y[\È›ÝÚÝÛˆ\È]˜Z[X›K‰Ë	ÜÝX‰ÊJ_Y[ÙHYŠÛÜšÜÚÜšY]Ê^ØÛÛœÝ]O]ÛÜšÜÚÜšY]ËÙ[XÝ[ÛY]KœÙ[XÝ[ÛŸßKÝ[[X\žO[›ÙJ	Ù]‰Ë[	ÝÛÜšÜÚÜ\Ù[XÝ[Û‰ÊNÚYŠ›ÛÛTÙ[XÝ[Û•[œÝ\ÜY
\Ý[[X\žK˜\[™
Y\ÜØYÙJ	Ô›ÛÛK\ÜXÚYšXÈÙ[XÝ[Ûˆ\È›ÝÝ\ÜYžHHÝ\œ™[X\TK‰Ë	Ø][[Û‰ÊJNÚYŠ]Kœ]Ë›[™Ý
^ØÛÛœÝÙ[XÝYY]Kœ]˜]
LJK[˜Ù\ÝÜœÏY]Kœ]œÛXÙJLJK™X\™\ÝÝÜ˜YÙOVË‹‹˜[˜Ù\ÝÜœ×Kœ™]™\œÙJ
K™š[™
Oœš\×ÛØØ][ÛŠK\Ý[˜][ÛY]Kœ]™š[™
OœšYOO\Ù[XÝ[Û‹™\Ý[˜][Û—ÚY
_\™[Ë™š[™
OœšYOO\Ù[XÝ[Û‹™\Ý[˜][Û—ÚY
KÝÜ˜YÙT]\Ù[XÝYš\×ÛØØ][ÛÙ]Kœ]˜[˜Ù\ÝÜœÎÜÝ[[X\žK˜\[™
›ÙJ	ÚÉË
Ù[XÝY›˜[Y_	ÔÙ[XÝY™XÛÜ™	ÊJÉÈ0­È	ÊÊÙ[XÝYšY	ÉÊJK›ÙJ	Ü	Ë	Ñ[˜]]™H]ˆ	ÊÙ]Kœ]›X\
Oœ›˜[YJKš›Ú[Š	ÈÈ	ÊJK›ÙJ	Ü	Ë	Ð\ÜÚYÛ™YÝÜ˜YÙNˆ	ÊÜÝÜ˜YÙT]›X\
Oœ›˜[YJKš›Ú[Š	ÈÈ	ÊJJNÚYŠÛÜšÜÚÜÙ[XÝYÝ]\Ê\Ý[[X\žK˜\[™
›ÙJ	Ü	Ë	ÐÛÛ™][ÛŽˆ	ÊÊÛÜšÜÚÜÙ[XÝYÝ]\Ë˜ÛÛ™][ÛŸ	Õ[œ™]šY]ÙY	ÊJÉÈ0­È	ÊÊÛÜšÜÚÜÙ[XÝYÝ]\Ë˜ÚXÚÙYÛÝ]ÉÐÚXÚÙYÝ]	Î‰Ó›ÝÚXÚÙYÝ]	ÊJÊÛÜšÜÚÜÙ[XÝYÝ]\Ë˜›ØÚÙ\ÉÈ0­È	ÊÝÛÜšÜÚÜÙ[XÝYÝ]\Ë˜›ØÚÙ\Ž‰ÉÊJJNÚYŠÙ[XÝ[Û‹šÚ[™OOIÙ^XÝ	Ê\Ý[[X\žK˜\[™
›ÙJ	Ü	Ë	Ñ^XÝX\XÙ[Y[‰ÊJNÙ[ÙHYŠÙ[XÝ[Û‹šÚ[™OOIØÛÛZ[š[™ÉÊ\Ý[[X\žK˜\[™
›ÙJ	Ü	Ë	ÔÝÜ™YÛˆ	ÊÊ™X\™\ÝÝÜ˜YÙOË›˜[Y_™X\™\ÝÝÜ˜YÙOËšY	ÝHÙ[XÝYÝÜ˜YÙHØØ][Û‰ÊJÉÎÈYÚYÚ[™ÈÛÛZ[š[™È\™XH	ÊÊ\Ý[˜][ÛË›˜[Y_	Û˜]]™HØØ][Û‰ÊJÉÈ
	ÊÊ\Ý[˜][ÛËšYÙ[XÝ[Û‹™\Ý[˜][Û—ÚY	Ý[šÛ›ÝÛ‰ÊJÉÊK‰ÊJNÙ[ÙHYŠÙ[XÝ[Û‹šÚ[™OOIÝ[›X\Y	Ê\Ý[[X\žK˜\[™
›ÙJ	Ü	Ë	Ó›ÈX\XÙ[Y[‰ÊJ_ZYŠY]K˜ÛÛ[ÏË›[™Ý
^ÜÝ[[X\žK˜\[™
›ÙJ	Ü	Ë	Ù]K˜ÛÝ[ÏË˜\ÜÚYÛ™YH\ÜÚYÛ™Y™XÛÜ™È0­È	Ù]K˜ÛÝ[ÏË˜ÚXÚÙYÛÝ]HÚXÚÙYÝ]0­È	Ù]K˜ÛÝ[ÏË˜]˜Z[X›_H]˜Z[X›H0­È	Ù]K˜ÛÝ[ÏË›™YY×Ø][[ÛŸH™YY][[Û‹ˆÛÝ[È\™H\]Z\Y[™XÛÜ™ÎÈÛÝ[ÈØ[ˆÝ™\›\˜
KÙ[XÝ
Ý[[X\žK	Ñ\]Z\Y[š[\‰ËÖÉØ[	Ë	Ð[Ý]\Ù\É×KÉØ]˜Z[X›IË	Ð]˜Z[X›I×KÉØÚXÚÙYÛÝ]	Ë	ÐÚXÚÙYÝ]	×KÉØ][[Û‰Ë	Ó™YYÈ][[Û‰×WKÛÜšÜÚÜš[\‹OžÝÛÜšÜÚÜš[\]ŽÝÛÜšÜÚÜZ[

_JJ_ZYŠ]K˜ÛÛ[ÏË›[™Ý
^ØÛÛœÝ›ÝÜÏY]K˜ÛÛ[Ë™š[\Š][OOÛÜšÜÚÜš[\OOIØ[	ß
ÛÜšÜÚÜš[\OOIØÚXÚÙYÛÝ]	ÏÚ][K˜ÚXÚÙYÛÝ]ÛÜšÜÚÜš[\OOIØ]˜Z[X›IÏÊZ][K˜ÚXÚÙYÛÝ]	‰ˆZ][K˜ÚXÚÛÝ]Ø›ØÚÙ\ŠNš][K˜ÛÛ™][ÛˆOOIÔ™XYIÊJNÜÝ[[X\žK˜\[™
›ÙJ	Ü	Ë	Ù]K˜ÛÝ[ÏË˜\ÜÚYÛ™YH\ÜÚYÛ™Y™XÛÜ™È0­È	Ù]K˜ÛÝ[ÏË˜ÚXÚÙYÛÝ]HÚXÚÙYÝ]0­È	Ù]K˜ÛÝ[ÏË˜]˜Z[X›_H]˜Z[X›H0­È	Ù]K˜ÛÝ[ÏË›™YY×Ø][[ÛŸH™YY][[Û‹ˆÛÝ[È\™H\]Z\Y[™XÛÜ™ÎÈÛÝ[ÈØ[ˆÝ™\›\˜
JNØÛÛœÝš[\\Ù[XÝ
Ý[[X\žK	Ñ\]Z\Y[š[\‰ËÖÉØ[	Ë	Ð[Ý]\Ù\É×KÉØ]˜Z[X›IË	Ð]˜Z[X›I×KÉØÚXÚÙYÛÝ]	Ë	ÐÚXÚÙYÝ]	×KÉØ][[Û‰Ë	Ó™YYÈ][[Û‰×WKÛÜšÜÚÜš[\‹OžÝÛÜšÜÚÜš[\]ŽÝÛÜšÜÚÜZ[

_JNÜÝ[[X\žK˜\[™
X›JÉÓ˜]]™H\]Z\Y[	Ë	ÔÝ]\ÉË	Ð›Üœ›ÝÚ[™ÉË	Ô™XÛÜ™	×K›ÝÜË›X\
][OOžØÛÛœÝ›ØÚÙ\Y\]Z\Y[›ØÚÙ\Š][JKÝ]\ÏZ][K˜ÚXÚÙYÛÝ]ÉÐÚXÚÙYÝ]	Î˜›ØÚÙ\ÉÐ›ØÚÙY0­È	ÊØ›ØÚÙ\Ž‰Ð]˜Z[X›IÎÜ™]\›ˆØ]ÛŠ][K›˜[YK

OOœÙ[XÝÛÜšÜÚÜ[]J][KšY
JK][K˜ÛÛ™][ÛŸ	Õ[šÛ›ÝÛ‰ËÝ]\Ë[šÊ	ÓÜ[ˆ˜]]™H™XÛÜ™	Ë
][K™[]U\OËš\ÓØØ][ÛÉËÛØØ][Û‹ÉÎ‰ËÚ][KÉÊJÙ[˜ÛÙUT’PÛÛ\Û™[
][KšY
JW_JJJ_Y[ÙHÝ[[X\žK˜\[™
›ÙJ	Ü	Ë	Ó›È\ÜÚYÛ™Y\]Z\Y[™XÛÜ™È[ˆ\ÈšY]Ë‰ÊJNÜÝ[[X\žK˜\[™
ÚXÚØ›Þ
Ý[[X\žK	Ò[˜ÛYH™\ÝYÛÛ[ÉË[˜ÛYS™\ÝYOœ™Yœ™\ÚÛÜšÜÚÜšY]ÊÛÜšÜÚÜ[]RYŠJKÚXÚØ›Þ
Ý[[X\žK	ÔÚÝÈÝ]\ÈÝ™\›^\ÈÛˆX\	ËÛÜšÜÚÜÝ™\›^\ËOžÝÛÜšÜÚÜÝ™\›^\Ï]ŽÝÛÜšÜÚÜZ[

_JJNÚYŠÛÜšÜÚÜÝ™\›^\Ê\Ý[[X\žK˜\[™
Y\ÜØYÙJ	ÔÝ]\ÈÝ™\›^HÛÛÜš[™È\È[Z]YÈHÙ[XÝYX\\™XK‰Ë	Ø][[ÛˆÛÜšÜÚÜ\Ý]\Ë\ØÛÜIÊJNÚYŠÙ[XÝ[Û‹›X]Ú\ÏË›[™ÝŒJ^ÜÝ[[X\žK˜\[™
›ÙJ	ÚÉË	ÐÚÛÜÙHHX\™\™\Ù[][Û‰ÊJNÙ›ÜŠÛÛœÝX]ÚÙˆÙ[XÝ[Û‹›X]Ú\Ê^ØÛÛœÝ\™Ù]›ÛÛO\›ÛÛPžRY
X]Úœ›ÛÛWÚY
KØš]\™Ù]›ÛÛOË›Øš™XÝË™š[™
›ÝÏOœ›ÝËšYOO[X]Ú™˜]Ú[™×ÚY
K[ØØ][ÛœË™š[™
›ÝÏOœ›ÝËšYOO[X]Ú›ØØ][Û—ÚY
NÜÝ[[X\žK˜\[™
]ÛŠ
\™Ù]›ÛÛOË›˜[Y_	Ô›ÛÛIÊJÉÈ0­È	ÊÊØšË˜Ø\[ÛŸØšË›˜[Y_	Ñ˜]Ú[™ÉÊJÉÈ0­È	ÊÊË›˜[Y_X]Ú›ØØ][Û—ÚY
JÉÈ0­È	ÊÛX]Ú›ØØ][Û—ÚY

OOžØÛÛœÝ›ÛÛO\›ÛÛPžRY
X]Úœ›ÛÛWÚY
K˜]Ú[™Ï\›ÛÛOË›Øš™XÝË™š[™
›ÝÏOœ›ÝËšYOO[X]Ú™˜]Ú[™×ÚY
NÚYŠ›ÛÛI‰™˜]Ú[™Ê^ØÚÛÜÙT[›™\”™\™\Ù[][ÛŠ›ÛÛK˜]Ú[™Ê__JJ__ZYŠÙ[XÝ[Û‹\™Ù]ÚY
^ØÛÛœÝ™XÛÜ™\\™[Ë™š[™
›ÝÏOœ›ÝËšYOO\Ù[XÝ[Û‹\™Ù]ÚY
_]Kœ]Ë˜]
LJK˜]ÔÙX\˜Ú™XÛÜ™]ÛÜšÜÚÜÙX\˜Ú›ÝÜÏË™š[™
›ÝÏOœ›ÝËšYOO\Ù[XÝ[Û‹\™Ù]ÚY
K\ÓØØ][ÛHHY]Kœ]Ë˜]
LJOËš\×ÛØØ][ÛŸH\™XÛÜ™Ëš\×ÛØØ][ÛŸH\™XÛÜ™Ëš\ÓØØ][ÛŸH\™XÛÜ™Ë™[]U\OËš\ÓØØ][ÛŸH\˜]ÔÙX\˜Ú™XÛÜ™Ë™[]U\OËš\ÓØØ][Û‹˜\ÙOJ\ÓØØ][ÛÉËÛØØ][Û‹ÉÎ‰ËÚ][KÉÊJÙ[˜ÛÙUT’PÛÛ\Û™[
Ù[XÝ[Û‹\™Ù]ÚY
NÜÝ[[X\žK˜\[™
[šÊ	ÓÜ[ˆ˜]]™H™XÛÜ™	Ë˜\ÙJJNÚYŠ\ÓØØ][ÛŠ\Ý[[X\žK˜\[™
[šÊ	ÑY]˜]]™HÝÜÉË˜\ÙJÉËÙY]	ÊJNÚYŠ]KœÝÜÏË›[™Ý
^ØÛÛœÝØ[\žO[›ÙJ	Ù]‰Ë[	ÝÛÜšÜÚÜYØ[\žIÊNÙ›ÜŠÛÛœÝÝÈÙˆ]KœÝÜÊ^ØÛÛœÝ[XYÙO[›ÙJ	Ú[YÉÊNÚ[XYÙKœÜ˜ÏIËØ\KÝŒKÙ[]Y\ËÉÊÙ[˜ÛÙUT’PÛÛ\Û™[
Ù[XÝ[Û‹\™Ù]ÚY
JÉËØ]XÚY[ËÉÊÙ[˜ÛÙUT’PÛÛ\Û™[
ÝËšY
NÚ[XYÙK˜[\ÝË˜[ÝË]_	Ó˜]]™HØØ][ÛˆÝÉÎÚ[XYÙK›ØY[™ÏIÛ^žIÎÙØ[\žK˜\[™
[XYÙJ_\Ý[[X\žK˜\[™
Ø[\žJ__ZYŠ]Kœ˜XÚÊ^ÜÝ[[X\žK˜\[™
›ÙJ	ÚÉË	Ô˜XÚÈœ›ÛšY]È0­ÈÚ[™\È›ÝÛHÈÜ	ÊJNÙ›ÜŠÛÛœÝÚ[ˆÙˆ]Kœ˜XÚËœÚ[™\ß×J\Ý[[X\žK˜\[™
]ÛŠ
Ú[‹˜ÛÙ_	ÉÊJÉÈ0­È	ÊÜÚ[‹›˜[YJÉÈ0­È	ÊÜÚ[‹šY

OOœÙ[XÝÛÜšÜÚÜ[]JÚ[‹šY
JJNÙ›ÜŠÛÛœÝÚ[Ùˆ]Kœ˜XÚË›Ý\—ØÚ[™[Ÿ×J\Ý[[X\žK˜\[™
]ÛŠ	ÓÝ\ˆÚ[0­È	ÊØÚ[›˜[YJÉÈ0­È	ÊØÚ[šY

OOœÙ[XÝÛÜšÜÚÜ[]JÚ[šY
JJNÚYŠ]Kœ˜XÚË[›Ü™\™YË›[™Ý
^ÜÝ[[X\žK˜\[™
›ÙJ	Ú	Ë	ÔÚ[™\ÈÚ]Ý][ˆÜ™\‰ÊJNÙ›ÜŠÛÛœÝÚ[ˆÙˆ]Kœ˜XÚË[›Ü™\™Y
\Ý[[X\žK˜\[™
]ÛŠÚ[‹›˜[YJÉÈ0­È	ÊÜÚ[‹šY

OOœÙ[XÝÛÜšÜÚÜ[]JÚ[‹šY
JJ_Y›ÜŠÛÛœÝ\œˆÙˆ]Kœ˜XÚË™\œ›Üœß×J\Ý[[X\žK˜\[™
Y\ÜØYÙJ\œ‹	Ø][[Û‰ÊJNÚYŠX[˜YÙ\Š
J\Ý[[X\žK˜\[™
]ÛŠ	Ô™]šY]ÈÚ[ˆÜ™\‰Ë

OOœÚ[“Ü™\‘X[ÙÊ]Kœ˜XÚÊK	ÛXZ[‰ÊJ_ZYŠ]K˜ÛÝ™\˜YÙOË›[™Ý
^ÜÝ[[X\žK˜\[™
›ÙJ	ÚÉË	ÓX\Ù]\ÛÝ™\˜YÙIÊJNÙ›ÜŠÛÛœÝ›ÝÈÙˆ]K˜ÛÝ™\˜YÙJ\Ý[[X\žK˜\[™
›ÙJ	Ü	Ë›ÝË›Y\ÜØYÙJÉÈ0­È	ÊÜ›ÝËšÚ[™
ÉÈ0­È	ÊÊ›ÝË›ØØ][Û—ÚY	Ù˜]Ú[™ÈÛ›IÊJÉÈ0­È	ÊÊ›ÝË™˜]Ú[™×ÚY	ÉÊJJ_ZYŠ]K™\œ›ÜœÏË›[™Ý
Y›ÜŠÛÛœÝ\œˆÙˆ]K™\œ›ÜœÊ\Ý[[X\žK˜\[™
Y\ÜØYÙJ\œ‹›Y\ÜØYÙK	Ø][[Û‰ÊJNØœ›ÝÜÙK˜\[™
Ý[[X\žJ_\\™[˜\[™
œ›ÝÜÙJ_B™[˜Ý[ÛˆÚ[“Ü™\‘X[ÙÊ˜XÚÊ^ØÛÛœÝÚ[™\ÏJ˜XÚËœÚ[™\ß×JK˜ÛÛ˜Ø]
˜XÚË[›Ü™\™Y×JKYÏ\Ú[™\Ë›X\
›ÝÏOœ›ÝËšY
K›Ü›O[›ÙJ	Ù]‰Ë[	Ù›Ü›IÊK˜]]™T˜XÚÏ[ØØ][ÛœË™š[™
›ÝÏOœ›ÝËšYOO\˜XÚËšY
K[™[™ÒÙ^OIÝÛÜšÜÚÜ[Ü™\Ž‰ÊÜØÛÜJ
JÉÎ‰ÊÜ˜XÚËšYÙ›Ü›K˜\[™
›ÙJ	Ü	Ë	Ô™\Ù[][ÛˆÜ™\ˆÛ›Kˆ\ÈÙ\È›Ý[Ý™HÝÜ˜YÙHÜˆ\]Z\Y[ˆÚ[™\È\™H\ÝY›ÝÛHÈÜ‰ÊJNÜÚ[™\Ë™›Ü‘XXÚ

›ÝË[™^
OO™›Ü›K˜\[™
›ÙJ	Ü	Ë
[™^
ÌJJÉËˆ	ÊÜ›ÝË›˜[YJÉÈ0­È	ÊÊ›ÝË˜ÛÙ_	Û›ÈÝÜ˜YÙHÛÙIÊJÉÈ0­È	ÊÜ›ÝËšY
JJNÛ]X\šÙ\[[Ýž^ÛX\šÙ\R”ÓÓ‹œ\œÙJØØ[ÝÜ˜YÙK™Ù]][J[™[™ÒÙ^J_	Û[	Ê_XØ]ÚßZYŠ\[ÙˆX\šÙ\Ëœ™\]Y\ÝÚÙ^OOOIÜÝš[™ÉÊ^Ù›Ü›K˜\[™
Y\ÜØYÙJ	ÐH™]š[Ý\ÈÚ[ˆÜ™\ˆ\È[ˆ[˜ÛÛ™š\›YY™\Ý[ˆØ]™Y™\]Y\ÝÙ^Nˆ	ÊÛX\šÙ\‹œ™\]Y\ÝÚÙ^JÉËˆÚXÚÈ]ÈÝ]\È™Y›Ü™HZÚ[™È[›Ý\ˆXÝ[Û‹‰Ë	Ø][[Û‰ÊK]ÛŠ	ÐÚXÚÈØ]™YÜ™\ˆ™\Ý[	Ë

OO˜ÚXÚÔ[™[™Ê[™[™Ê
K™š[™
›ÝÏOœ›ÝËšÙ^OOO[X\šÙ\‹œ™\]Y\ÝÚÙ^J_ÚÙ^N›X\šÙ\‹œ™\]Y\ÝÚÙ^K]‰ÝÛÜšÜÚÜÜÚ[‹[Ü™\‰ËX™[‰ÔØ]™H˜XÚÈÚ[ˆÜ™\‰ËÝXš™XÝœ˜XÚËšY]‰ÉßJJJNßY[ÙHYŠØØ[ÝÜ˜YÙK™Ù]][J[™[™ÒÙ^JJ^Ù›Ü›K˜\[™
Y\ÜØYÙJ	ÐHØ]™YÚ[‹[Ü™\ˆX\šÙ\ˆ\È[œ™XYX›KˆÈ›ÝÝX›Z][›Ý\ˆÜ™\ŽÈ[œÜXÝ™XÛÝ™\žK‰Ë	Ø][[Û‰ÊK]ÛŠ	ÓÜ[ˆ™XÛÝ™\žIË

OO™ÛÊ	Ü™XÛÝ™\žIÊJJ_Y[ÙH›Ü›K˜\[™
XÝ[ÛœÊ]ÛŠ	ÐØ[˜Ù[	Ë

OO˜ÛÜÙQX[ÙÊ
JK]ÛŠ	ÐÛÛ™š\›HÚ[ˆÜ™\‰Ë\Þ[˜Ê
OOžØÛÛœÝÙ^O]]ZY

NÛØØ[ÝÜ˜YÙKœÙ]][J[™[™ÒÙ^K”ÓÓ‹œÝš[™ÚYžJÜ™\]Y\ÝÚÙ^NšÙ^KÝ]\Î‰Ü[™[™ÉË[]WÚYœ˜XÚËšYÚ[—ÚYÎšYßJJNÝž^Ø]ØZ]Üš]J	ÝÛÜšÜÚÜÜÚ[‹[Ü™\‰ËÙ[]WÚYœ˜XÚËšY\]YØ]›˜]]™T˜XÚÏË\]YØ]Ú[—ÚYÎšYË™\]Y\ÝÚÙ^NšÙ^_K	ÔØ]™H˜XÚÈÚ[ˆÜ™\‰Ë˜XÚËšY
NØÛX\”Ú[“Ü™\“X\šÙ\ŠÙ^K˜XÚËšY
NØÛÜÙQX[ÙÊYJNØ]ØZ]™Yœ™\ÚÛÜšÜÚÜšY]ÊÛÜšÜÚÜ[]RY[˜ÛYS™\ÝY
_XØ]Ú
\œ›ÜŠ^ÚYŠ\[™[™Ê
KœÛÛYJ›ÝÏOœ›ÝËšÙ^OOOZÙ^JJXÛX\”Ú[“Ü™\“X\šÙ\ŠÙ^K˜XÚËšY
NÝ›ÝÈ\œ›ÜŸ_K	ÛXZ[‰ÊJJNÛÜ[‘X[ÙÊ	Ô™]šY]ÈÚ[ˆÜ™\‰Ë›Ü›J_B˜\Þ[˜È[˜Ý[ÛˆØ]™S^[Ý]

^ÚYŠ[X[˜YÙ\Š
J]›ÝÈ\œ›ÜŠ	ÕÛÜšÜÚÜX[˜YÙ\ˆ\›Z\ÜÚ[Ûˆ\È™\]Z\™YÈØ]™H›ÛÛHÚ[™Ù\Ë‰ÊNÚYŠ^[Ý][˜Ù\Z[Š^ÝØ\Ý
	ÐÚXÚÈHØ]™Y™\Ý[™Y›Ü™HÝX›Z][™È[›Ý\ˆØ]™K‰ÊNÜ™]\›ŸZYŠ[^[Ý]\J^ÝØ\Ý
	Ð[›ÛÛHÚ[™Ù\È\™HØ]™Y‰ÊNÜ™]\›ŸY›ÜŠÛÛœÝ›ÛÛHÙˆ^[Ý]˜Yœ›ÛÛ\Ê^Ý˜[Y]T›ÛÛJ›ÛÛJNÙ›ÜŠÛÛœÝØš™XÝÙˆ›ÛÛK›Øš™XÝÊ]˜[Y]SØš™XÝ
›ÛÛKØš™XÝ
_ZYŠ^[Ý]˜Yœ›ÛÛ\Ë›[™ÝŒŒ
]›ÝÈ\œ›ÜŠ	ÐHÛÜšÜÚÜ[ˆØ[ˆÛÛZ[ˆ][ÜÝŒ›ÛÛ\Ë‰ÊNØÛÛœÝ[[^ÜØÚ[XWÝ™\œÚ[ÛŽŒ‹™]š\Ú[ÛŽ›^[Ý]Ý]Kœ™]š\Ú[Û‹ØÝ[Y[˜ÛÛ™J^[Ý]˜Y
K™\]Y\ÝÚÙ^N]ZY

_KÝÛ™\^ÚY[]N˜ÛÛ^šY[]KÜ›Ý\ÚY˜ÛÛ^™Ü›Ý\šY\Ù\—ÚY˜ÛÛ^\Ù\‹šYKÚÙ[XØ\\™UZJ
NÛ^[Ý]Ø]™Q\œ›ÜIÉÎÝž^ØÛÛœÝ™\Ý[X]ØZ]Üš]J	ÝÛÜšÜÚÜÜØ]™IË[[	ÔØ]™H[›ÛÛHÚ[™Ù\ÉÊNÚYŠ]ZPÝ\œ™[
ÚÙ[Š_\ÜÜÙYÝ\œ™[OOIÝÛÜšÜÚÜ	ßÛÛ^ËšY[]HOO[ÝÛ™\‹šY[]J\™]\›ŽÛ^[Ý]Ý]Kœ™]š\Ú[Û\™\Ý[œ™]š\Ú[ÛŽÛ^[Ý]Ý]K™ØÝ[Y[XÛÛ™J™\Ý[™ØÝ[Y[
NÛ^[Ý]Ý]K›^[Ý]\™\Ý[›^[Ý][Û^[Ý]˜YXÛÛ™J™\Ý[™ØÝ[Y[
NÛ^[Ý][˜Ù\Z[[[Û^[Ý]\OY˜[ÙNÜ›ÛÛU[™Ë˜ÛX\Š
NÜ›ÛÛT™YË˜ÛX\Š
NÙ[œÝ\™T›ÛÛR\ÝÜžJ^[Ý]˜Yœ›ÛÛ\ÊNÜ\œÚ\Ý[›™\”Ù\ÜÚ[ÛŠ
NÛ^[Ý]Ø]™Q\œ›ÜIÉÎÝÛÜšÜÚÜZ[

NÝØ\Ý
	Ð[›ÛÛHÚ[™Ù\ÈØ]™Yˆ˜]]™HÝÜ˜YÙH™XÛÜ™ÈÙ\™H›Ý[Ý™Y‰Ê_XØ]Ú
\œ›ÜŠ^ÚYŠ]ZPÝ\œ™[
ÚÙ[Š_\ÜÜÙYÝ\œ™[OOIÝÛÜšÜÚÜ	ßÛÛ^ËšY[]HOO[ÝÛ™\‹šY[]J\™]\›ŽÚYŠ\œ›Ü‹œÝ]\ÏOOM\œ›Ü‹œÝ]\ÏOOMJ^ØÛÛœÝÝ[[™[™Ï]ÛÜšÜÚÜœ[™[™Ê
K™š[™
›ÝÏOœ›ÝËœ]OOIÝÛÜšÜÚÜÜØ]™IÉ‰œ›ÝËšÙ^OOOZ[[œ™\]Y\ÝÚÙ^JNÚYŠÝ[[™[™Ê^Û^[Ý][˜Ù\Z[^ÚÙ^Nš[[œ™\]Y\ÝÚÙ^K™]š\Ú[ÛŽš[[œ™]š\Ú[Û‹ØÝ[Y[˜ÛÛ™J[[™ØÝ[Y[
KY[]N›ÝÛ™\‹šY[]KÜ›Ý\ÚY›ÝÛ™\‹™Ü›Ý\ÚY\Ù\—ÚY›ÝÛ™\‹\Ù\—ÚYNÜ\œÚ\Ý[›™\”Ù\ÜÚ[ÛŠ
_[^[Ý]Ø]™Q\œ›Ü\Ý[[™[™ÏÉÕHØ]™H™\Ý[\È[˜Ù\Z[‹ˆÚXÚÈ]ÈØ]™YÝ]\È™Y›Ü™HÚ[™È[ž][™È[ÙK‰Î™\œ›Ü‹œÝ]\ÏOOMOÉÕHØ]™Y[ˆÚ[™ÙY[Ù]Ú\™Kˆ[Ý\ˆ˜Y\È™\Ù\™YÈ™[ØYHØ]™Y[ˆÈ™\ÛÛ™HHÛÛ™›XÝ‰Î‰ÕHÙ\™\ˆ™Z™XÝY\È›ÛÛH[‹ˆ[Ý\ˆ˜Y\È™\Ù\™YÈÛÜœ™XÝHYÚYÚYÙ[ÛY]žHÜˆ™[ØYHØ]™Y[‹‰ÎÙØÑ\J
NÝÛÜšÜÚÜZ[

NÜ™]\›ŸXÛÛœÝXÝ[Û]ÛÜšÜÚÜœ[™[™Ê
K™š[™
›ÝÏOœ›ÝËœ]OOIÝÛÜšÜÚÜÜØ]™IÉ‰œ›ÝËšÙ^OOOZ[[œ™\]Y\ÝÚÙ^JNÚYŠXÝ[ÛŠ^Û^[Ý][˜Ù\Z[^ÚÙ^Nš[[œ™\]Y\ÝÚÙ^K™]š\Ú[ÛŽš[[œ™]š\Ú[Û‹ØÝ[Y[˜ÛÛ™J[[™ØÝ[Y[
KY[]N›ÝÛ™\‹šY[]KÜ›Ý\ÚY›ÝÛ™\‹™Ü›Ý\ÚY\Ù\—ÚY›ÝÛ™\‹\Ù\—ÚYNÜ\œÚ\Ý[›™\”Ù\ÜÚ[ÛŠ
_[^[Ý]Ø]™Q\œ›ÜXXÝ[ÛÉÕHØ]™H™\Ý[\È[šÛ›ÝÛ‹ˆÚXÚÈ]ÈØ]™YÝ]\È™Y›Ü™HÚ[™È[ž][™È[ÙK‰Î™\œ›Ü‹›Y\ÜØYÙ_	ÕHØ]™HÛÝ[›Ý™HÙ[‰ÎÝÛÜšÜÚÜZ[

__B˜\Þ[˜È[˜Ý[ÛˆÚXÚÓ^[Ý]Ø]™TÝ]\Ê
^ØÛÛœÝ[™[™ÔØ]™O]ÛÜšÜÚÜœ[™[™Ê
K™š[™
›ÝÏOœ›ÝËœ]OOIÝÛÜšÜÚÜÜØ]™IÉ‰œ›ÝËšÙ^OOO[^[Ý][˜Ù\Z[ËšÙ^I‰œ›ÝËšY[]OOOXÛÛ^ËšY[]I‰œ›ÝË™Ü›Ý\ÚYOOXÛÛ^Ë™Ü›Ý\šY	‰œ›ÝË\Ù\—ÚYOOXÛÛ^Ë\Ù\‹šY	‰œ›ÝËš[[ËœØÚ[XWÝ™\œÚ[ÛOOLŠNÚYŠ\[™[™ÔØ]™J]›ÝÈ\œ›ÜŠ	ÕHØ]™Y™\]Y\ÝY[]H\È[˜]˜Z[X›KˆÙY\\È˜Y[™\ÙH™XÛÝ™\žHÈ[œÜXÝ]‰ÊNØÛÛœÝ™\Ý[X]ØZ]\J	ÛÜ\˜][Û‹ÜÝ]\ÉËÜ™\]Y\ÝÚÙ^Nœ[™[™ÔØ]™KšÙ^_K[™[™ÔØ]™KšY[]JNÚYŠ™\Ý[œÝ]\ÏOOIØÛÛ\]Y	É‰œ™\Ý[˜XÝ[ÛOOIÝÛÜšÜÚÜÜØ]™IÉ‰œ™\Ý[œ™\Ý[ËœØÚ[XWÝ™\œÚ[ÛOOLŠ^ÝÛÜšÜÚÜ™›Ü™Ù]
[™[™ÔØ]™KšÙ^JNÛ^[Ý]Ý]Kœ™]š\Ú[Û\™\Ý[œ™\Ý[œ™]š\Ú[ÛŽÛ^[Ý]Ý]K™ØÝ[Y[XÛÛ™J™\Ý[œ™\Ý[™ØÝ[Y[
NÛ^[Ý]˜YXÛÛ™J™\Ý[œ™\Ý[™ØÝ[Y[
NÛ^[Ý][˜Ù\Z[[[Û^[Ý]\OY˜[ÙNÜ›ÛÛU[™Ë˜ÛX\Š
NÜ›ÛÛT™YË˜ÛX\Š
NÙ[œÝ\™T›ÛÛR\ÝÜžJ^[Ý]˜Yœ›ÛÛ\ÊNÜ\œÚ\Ý[›™\”Ù\ÜÚ[ÛŠ
NÛ^[Ý]Ø]™Q\œ›ÜIÉÎÝÛÜšÜÚÜZ[

NÝØ\Ý
	ÕHØ]™Y™\Ý[\ÈÛÛ™š\›YYˆ›È™\]Y\ÝØ\È™\X]Y‰ÊNÜ™]\›ŸZYŠ™\Ý[œÝ]\ÏOOIÛ›ÝÜÝ\Y	ß™\Ý[œÝ]\ÏOOIØØ[˜Ù[Y	Ê^ÝÛÜšÜÚÜ™›Ü™Ù]
[™[™ÔØ]™KšÙ^JNÛ^[Ý][˜Ù\Z[[[Û^[Ý]\O]YNÜ\œÚ\Ý[›™\”Ù\ÜÚ[ÛŠ
NÛ^[Ý]Ø]™Q\œ›ÜIÓ›ÈÛÛ\]YØ]™HØ\È›Ý[™ˆ[Ý\ˆ˜Y\ÈÝ[\™NÈØ]™HYØZ[ˆÛ›HÚ[ˆ[ÝHÚÛÜÙK‰ÎÝÛÜšÜÚÜZ[

NÜ™]\›Ÿ[^[Ý]Ø]™Q\œ›ÜIÕHØ]™HÝ[™YYÈÛÛ™š\›X][Û‹ˆ›È™\X]™\]Y\ÝØ\ÈÙ[‰ÎÝÛÜšÜÚÜZ[

_B˜\Þ[˜È[˜Ý[Ûˆ™[ØYØ]™Y[Š
^ÚYŠ]Ú[™ÝË˜ÛÛ™š\›J	Ñ\ØØ\™]™\žH[œØ]™Y›ÛÛHÚ[™ÙH[™ØYHÝ\œ™[Ø]™Y[ÉÊJ\™]\›ŽØÛÛœÝ]\ÝX]ØZ]\J	ÝÛÜšÜÚÜ	ÊNÛ^[Ý]Ý]O[]\ÝÛ^[Ý]˜YXÛÛ™J]\Ý™ØÝ[Y[Ý™\œÚ[ÛŽŒ‹›ÛÛ\Î–×_JNÛ^[Ý][˜Ù\Z[[[Û^[Ý]\OY˜[ÙNÛ^[Ý]Ø]™Q\œ›ÜIÉÎÜ›ÛÛU[™Ë˜ÛX\Š
NÜ›ÛÛT™YË˜ÛX\Š
NÙ[œÝ\™T›ÛÛR\ÝÜžJ^[Ý]˜Yœ›ÛÛ\ÊNØXÝ]™T›ÛÛRY[^[Ý]˜Yœ›ÛÛ\ËœÛÛYJ›ÛÛOOœ›ÛÛKšYOOXXÝ]™T›ÛÛRY
OØXÝ]™T›ÛÛRY›^[Ý]˜Yœ›ÛÛ\ÖÌOËšY[Û^[Ý]Ù[XÝYXXÝ]™T›ÛÛRYÊÙ[XÝY˜]Ú[™ÐžT›ÛÛVØXÝ]™T›ÛÛRY_[
N›[Ü™[[Ý™T[›™\”Ù\ÜÚ[ÛŠ
NØ]ØZ]™Yœ™\ÚÛÜšÜÚÜšY]ÊÛÜšÜÚÜ[]RY[˜ÛYS™\ÝY
NÝÛÜšÜÚÜZ[

_B™[˜Ý[ÛˆZ[ÝÜ˜YÙJ\™[
^ØÛÛœÝ\[™[
›ÙJ	Ú‰Ë	Ó˜]]™HÝÜ˜YÙHY\˜\˜ÚIÊJNØÛÛœÝ™YO[›ÙJ	Ý[	Ë[	ÛØØ][Û‹]™YIÊNÙ[˜Ý[Ûˆœ˜[˜Ú
Y\ÝÙY[[™]ÈÙ]

J^Ù›ÜŠÛÛœÝÙˆ\™[Ë™š[\ŠO›œ\™[ÚYOOJY[
JJ^ÚYŠÙY[‹š\ÊšY
JXÛÛ[YNØÛÛœÝÚ[[›ÙJ	ÛIÊNØÚ[˜\[™
[šÊY™\ÜÊšY
K
š\ÓØØ][ÛÉËÛØØ][Û‹ÉÎ‰ËÚ][KÉÊJÙ[˜ÛÙUT’PÛÛ\Û™[
šY
JK›ÙJ	ÜÛX[	ËšÚ[™
ÉÈ0­È	ÊÊ^[Ý]Ý]K˜ÛÝ[ÖÛšY_
JÉÈ\™XÝH\ÜÚYÛ™Y][\ÉË	ÜÝX‰ÊJNÚYŠX[˜YÙ\Š
JXÚ[˜\[™
]ÛŠ	ÐY[œÚYIË

OOœÝÜ˜YÙQX[ÙÊšY
JK]ÛŠ	Ó[Ý™HÝÜ˜YÙIË

OO›[Ý™TÝÜ˜YÙQX[ÙÊ
JJNØÛÛœÝ\ØÙ[™[Ï[›ÙJ	Ý[	Ë[	ÛØØ][Û‹]™YIÊNØœ˜[˜Ú
šY\ØÙ[™[Ë™]ÈÙ]
Ë‹‹œÙY[‹šYJJNÚYŠ\ØÙ[™[Ë˜Ú[›Ù\Ë›[™Ý
XÚ[˜\[™
\ØÙ[™[ÊNÛ\Ý˜\[™
Ú[
__Xœ˜[˜Ú
[™YJNÚYŠ]™YK˜Ú[›Ù\Ë›[™Ý
]™YK˜\[™
›ÙJ	ÛIË	Ó›È˜]]™HÝÜ˜YÙHØØ][ÛœÈY]‰ÊJNÜ˜\[™
™YJNÚYŠX[˜YÙ\Š
J\˜\[™
]ÛŠ	ÐYÜ[]™[ÝÜ˜YÙIË

OOœÝÜ˜YÙQX[ÙÊ[
JJNÜ\™[˜\[™

_B™[˜Ý[ÛˆÝÜ˜YÙQX[ÙÊ\™[Y
^ØÛÛœÝ˜Y^Û˜[YN‰ÉË\™[ÚYœ\™[YÝÜ˜YÙWÚÚ[™‰ÓØØ][Û‰ËÝÜ˜YÙWØÛÙN‰ÉßK›Ü›O[›ÙJ	Ù]‰Ë[	Ù›Ü›IÊNÙšY[
›Ü›K	ÓØØ][Ûˆ˜[YIË	ÉË	Ý^	ËO™˜Y›˜[YO]ŠNÙšY[
›Ü›K	ÔÝÜ˜YÙHÛÙIË	ÉË	Ý^	ËO™˜YœÝÜ˜YÙWØÛÙO]ŠNÜÙ[XÝ
›Ü›K	ÔÝÜ˜YÙHÚ[™	Ë^[Ý]Ý]KœÝÜ˜YÙWÝ\\Ë›X\
ÏO–ÚË×JK˜YœÝÜ˜YÙWÚÚ[™O™˜YœÝÜ˜YÙWÚÚ[™]ŠNÜÙ[XÝ
›Ü›K	Ò[œÚYH
Ü[Û˜[
IËÖÉÉË	ÕÜ]™[	×K‹‹˜]˜Z[X›T\™[Ê\™[ÊK›X\
O–ÛšYY™\ÜÊšY
WJWK\™[Y	ÉËO™˜Yœ\™[ÚY]Ÿ[
NÙ›Ü›K˜\[™
XÝ[ÛœÊ]ÛŠ	ÐØ[˜Ù[	Ë

OO˜ÛÜÙQX[ÙÊ
JK]ÛŠ	ÐÛÛ™š\›H˜]]™HØØ][Û‰Ë\Þ[˜Ê
OOžØ]ØZ]Üš]J	ÛØØ][ÛœËØÜ™X]IËÚ[œ]™˜YK	ÐÜ™X]HÝÜ˜YÙHØØ][Û‰Ë\™[Y	Ü›ÛÝ	ÊNØÛÜÙQX[ÙÊYJNÚYŠ^[Ý]\J^ÝØ\Ý
	ÔÝÜ˜YÙHÜ™X]YˆØ]™H[Ý\ˆÙ[ÛY]žH™Y›Ü™H™[ØY[™ÈHY\˜\˜ÚK‰Ê_Y[ÙH]ØZ]ÛÊ	ÝÛÜšÜÚÜ	Ë˜[ÙJ_K	ÛXZ[‰ÊJJNÛÜ[‘X[ÙÊ	ÐÜ™X]H˜]]™HÝÜ˜YÙHØØ][Û‰Ë›Ü›J_B™[˜Ý[Ûˆ[Ý™TÝÜ˜YÙQX[ÙÊ
^Û]\Ý[˜][Û[œ\™[ÚY	ÉÎØÛÛœÝ›Ü›O[›ÙJ	Ù]‰Ë[	Ù›Ü›IÊNÜÙ[XÝ
›Ü›K	Ò[œÚYH
Ü[Û˜[
IËÖÉÉË	ÕÜ]™[	×K‹‹˜]˜Z[X›T\™[Ê\™[ËÛšYJK›X\
O–ÜšYY™\ÜÊšY
WJWK\Ý[˜][Û‹O™\Ý[˜][Û]ŠNÙ›Ü›K˜\[™
›ÙJ	Ü	Ë	Õ\È[Ý™\ÈH˜]]™HØØ][ÛˆÚ]]ÈÚ[™[‹ˆ\]Z\Y[Y[]Y\È™[XZ[ˆ[˜Ú[™ÙY‰ÊKXÝ[ÛœÊ]ÛŠ	ÐØ[˜Ù[	Ë

OO˜ÛÜÙQX[ÙÊ
JK]ÛŠ	ÐÛÛ™š\›HÝÜ˜YÙH[Ý™IË\Þ[˜Ê
OOžØ]ØZ]Üš]J	ÝÛÜšÜÚÜÛ[Ý™IËÚY›šY\™[ÚY™\Ý[˜][ÛŸ[\]YØ]›\]YØ]K	Ó[Ý™H˜]]™HÝÜ˜YÙIËšY
NØÛÜÙQX[ÙÊYJNÚYŠ^[Ý]\J]Ø\Ý
	ÔÝÜ˜YÙH[Ý™YˆØ]™H[Ý\ˆÙ[ÛY]žH™Y›Ü™H™[ØY[™ÈÝÜ˜YÙK‰ÊNÙ[ÙH]ØZ]ÛÊ	ÝÛÜšÜÚÜ	Ë˜[ÙJ_K	ÛXZ[‰ÊJJNÛÜ[‘X[ÙÊ	Ó[Ý™H	ÊÛ›˜[YK›Ü›J_B˜\Þ[˜È[˜Ý[Ûˆ[\ÜÔYÙJ™]š\Ú[ÛŠ^ØÛÛœÝ˜]Ú\ÏX]ØZ]\J	Ú[\ÜÉÊNÚYŠ™]š\Ú[ÛˆOO\›Ý]U™\œÚ[ÛŠ\™]\›ŽÝ]J	Ò[\Ü\]Z\Y[	Ë	ÔØ]™YÔÕˆ˜]Ú\Ë[™]šYX[™]šY]È[™^XÚ]Ü™X][Û‹‰ÊNØÛÛœÝ›Ü›O[›ÙJ	Ù]‰Ë[	Ù›Ü›IÊKÛÝ\˜ÙOYšY[
›Ü›K	ÔÛÝ\˜ÙHÞ\Ý[IË	Ð\ÜÙ]X[˜YÙ\‰ÊKš[O[›ÙJ	Ú[œ]	ÊNÙš[K\OIÙš[IÎÙš[K˜XØÙ\IË˜ÜÝ‹^ØÜÝ‰ÎÙš[KœÙ]]šX]J	Ø\šXK[X™[	Ë	ÐÔÕˆš[IÊNÙ›Ü›K˜\[™
š[K›ÙJ	Ü	Ë	ÐÔÕˆU‹N\ÈL[™]šYX[H˜XÚÙY][\È[™ÌÐ‹ˆ\ÙHHØ[YHÛÝ\˜ÙH˜[YH[™ÝX›HQÈ›Üˆ™\X][\ÜË‰ÊK]ÛŠ	Õ\ØY	ˆX\ÔÕ‰Ë\Þ[˜Ê
OOžÚYŠYš[K™š[\Ë›[™Ý
]›ÝÈ\œ›ÜŠ	ÐÚÛÜÙHHÔÕˆš[K‰ÊNÚYŠš[K™š[\ÖÌKœÚ^™OÌ
]›ÝÈ\œ›ÜŠ	ÐÚÛÜÙHHÔÕˆ[™\ˆÌÐ‹‰ÊNÚ[\Ü˜]ÚX]ØZ]Üš]J	Ú[\ÜËÝ\ØY	ËÜÛÝ\˜ÙNœÛÝ\˜ÙK˜[YKš[[˜[YN™š[K™š[\ÖÌK›˜[YKÜÝŽ˜]ØZ]š[K™š[\ÖÌK^

_K	Õ\ØYÔÕ‰ËÛÝ\˜ÙK˜[YJÉÎ‰ÊÙš[K™š[\ÖÌK›˜[YJNØ]ØZ]X\[\ÜX[ÙÊ
_K	ÛXZ[‰ÊJNÝšY]Ë˜\[™
[™[
›ÙJ	Ú‰Ë	ÔÝ\H˜]Ú	ÊK›Ü›JJNÝšY]Ë˜\[™
X›JÉÔØ]™Y˜]Ú	Ë	ÔÛÝ\˜ÙIË	Ò][\ÉË	ÐXÝ[Û‰×K˜]Ú\Ë›X\
O–Ø‹™š[[˜[YK‹œÛÝ\˜ÙK‹˜ÛÝ[]ÛŠ	Ô™\Ý[YH˜]Ú	Ë

OOœ™\Ý[YP˜]Ú
‹šY
JWJJJ_B˜\Þ[˜È[˜Ý[Ûˆ[\ÜÚÚXÙ\Ê
^ØÛÛœÝ˜[Y\ÏX]ØZ]›ÛZ\ÙK˜[
Ø\J	ÛØØ][ÛœÉÊK\J	Ù\]Z\Y[	ÊK\J	Ý\\ÉÊWJNÛØØ][ÛœÏVË‹‹˜[Y\ÖÌK‹‹˜[Y\ÖÌWWK™š[\ŠOˆ[˜\˜Ú]™Y
NÝ\\Ï]˜[Y\ÖÌ—K™š[\ŠOˆ]š\ÓØØ][ÛŠ_B˜\Þ[˜È[˜Ý[Ûˆ™\Ý[YP˜]Ú
Y
^ÚYŠ\ÞJ]›ÝÈ\œ›ÜŠ	ÕØZ]›ÜˆÛÛ™š\›X][ÛˆÈš[š\Ú‰ÊNÚYŠX[ÙË›Ü[‰‰ˆXÛÜÙQX[ÙÊ
J\™]\›ŽØÛÛœÝÚÙ[XØ\\™UZJ
KÙ[XÝ[Û”™]š\Ú[ÛJÊÚ[\ÜÙ[XÝ[Û”™]š\Ú[Û‹˜]ÚX]ØZ]\J	Ú[\ÜËÙÙ]	ËÚYJNÚYŠ]ZPÝ\œ™[
ÚÙ[Š_Ù[XÝ[Û”™]š\Ú[ÛˆOOZ[\ÜÙ[XÝ[Û”™]š\Ú[ÛŠ\™]\›ŽÚ[\Ü˜]ÚX˜]ÚÚYŠ˜]Úš][\Ë›[™Ý
X]ØZ]™[™\˜]Ú

NÙ[ÙH]ØZ]X\[\ÜX[ÙÊ
_B˜\Þ[˜È[˜Ý[ÛˆX\[\ÜX[ÙÊ
^ØÛÛœÝ˜]ÚZ[\Ü˜]ÚÚÙ[XØ\\™UZJ
KÙ[XÝ[Û”™]š\Ú[ÛZ[\ÜÙ[XÝ[Û”™]š\Ú[ÛŽØ]ØZ][\ÜÚÚXÙ\Ê
NÚYŠ]ZPÝ\œ™[
ÚÙ[Š_Ù[XÝ[Û”™]š\Ú[ÛˆOOZ[\ÜÙ[XÝ[Û”™]š\Ú[ÛŸ˜]ÚOOZ[\Ü˜]Ú
\™]\›ŽØÛÛœÝX\[™Ï^ßKY˜][Ï^ÛØØ][Û—ÚY‰ÉË\WÚY‰ÉßK›Ü›O[›ÙJ	Ù]‰Ë[	Ù›Ü›IÊNÙ›Ü›K˜\[™
›ÙJ	Ü	Ë[\Ü˜]Ú™š[[˜[YJÉÈ0­È	ÊÊ[\Ü˜]Úœ˜]ÏË›[™Ý
JÉÈÛÝ\˜ÙH›ÝÜË‰ÊJNØÛÛœÝ[X\Ù\Ï^Û˜[YN–ÉÛ˜[YIË	Ù\]Z\Y[	Ë	Ø\ÜÙ]˜[YI×KÙ\šX[–ÉÜÙ\šX[	Ë	ÜÙ\šX[[X™\‰×KX[Y˜XÝ\™\Ž–ÉÛX[Y˜XÝ\™\‰Ë	Øœ˜[™	×K[Ù[–ÉÛ[Ù[	×K\ØÜš\[ÛŽ–ÉÙ\ØÜš\[Û‰Ë	Û›Ý\É×KØØ][ÛŽ–ÉÛØØ][Û‰Ë	ÜÚ[‰×KØ]YÛÜžN–ÉØØ]YÛÜžIË	Ý\I×K^\›˜[ÚY–ÉÚY	Ë	Ø\ÜÙ]Y	Ë	Ø\ÜÙ][X™\‰×KÛÝ\˜ÙWØÛÛ™][ÛŽ–ÉØÛÛ™][Û‰Ë	ÜÝ]\É×_NÙ›ÜŠÛÛœÝÚÙ^K˜[Y\×HÙˆØš™XÝ™[šY\Ê[X\Ù\ÊJ^ÛX\[™ÖÚÙ^WOZ[\Ü˜]ÚšXY\œË™š[™
O›˜[Y\Ëš[˜ÛY\ÊÓÝÙ\Ø\ÙJ
JJ_	ÉÎÜÙ[XÝ
›Ü›KÙ^Kœ™\XÙP[
	×ÉË	È	ÊKÖÉÉË	Ó›ÝX\Y	×K‹‹š[\Ü˜]ÚšXY\œË›X\
O–ÚJWKX\[™ÖÚÙ^WKO›X\[™ÖÚÙ^WO]Š_\Ù[XÝ
›Ü›K	ÑY˜][ØØ][Û‰ËÖÉÉË	ÐÚÛÜÙH\š[™È™]šY]É×K‹‹›ØØ][ÛœË›X\
O–ÛšY›˜[YWJWK	ÉËO™Y˜][Ë›ØØ][Û—ÚY]ŠNÜÙ[XÝ
›Ü›K	ÑY˜][Ø]YÛÜžIËÖÉÉË	ÐÚÛÜÙH\š[™È™]šY]É×K‹‹\\Ë›X\
O–ÝšY›˜[YWJWK	ÉËO™Y˜][Ë\WÚY]ŠNÙ›Ü›K˜\[™
XÝ[ÛœÊ]ÛŠ	ÐØ[˜Ù[	Ë

OO˜ÛÜÙQX[ÙÊ
JK]ÛŠ	ÔØ]™HX\[™È	ˆ™]šY]È›ÝÜÉË\Þ[˜Ê
OOžÚYŠ[X\[™Ë›˜[YJ]›ÝÈ\œ›ÜŠ	ÓX\H\]Z\Y[˜[YHÛÛ[[‹‰ÊNÚ[\Ü˜]ÚX]ØZ]Üš]J	Ú[\ÜËÛX\	ËÚYš[\Ü˜]ÚšYX\[™Ë‹‹™Y˜][ßK	ÓX\[\Ü˜]Ú	Ë[\Ü˜]ÚšY
NØÛÜÙQX[ÙÊYJNØ]ØZ]™[™\˜]Ú

_K	ÛXZ[‰ÊJJNÛÜ[‘X[ÙÊ	ÓX\ÔÕˆÛÛ[[œÉË›Ü›J_B˜\Þ[˜È[˜Ý[Ûˆ™[™\˜]Ú

^ØÛÛœÝ˜]ÚZ[\Ü˜]ÚÚÙ[XØ\\™UZJ
KÙ[XÝ[Û”™]š\Ú[ÛZ[\ÜÙ[XÝ[Û”™]š\Ú[ÛŽØ]ØZ][\ÜÚÚXÙ\Ê
NÚYŠ]ZPÝ\œ™[
ÚÙ[Š_Ù[XÝ[Û”™]š\Ú[ÛˆOOZ[\ÜÙ[XÝ[Û”™]š\Ú[ÛŸ˜]ÚOOZ[\Ü˜]Ú
\™]\›ŽÝšY]Ëœ™\XÙPÚ[™[Š
NÝ]J[\Ü˜]Ú™š[[˜[YK	Ô™]šY]È[™Ø]™HXXÚ›ÝËˆ˜]]™H[™[ÜžH\ÈÜ™X]YÛ›HY\ˆ^XÚ]ÛÛ™š\›X][Û‹‰Ë]ÛŠ	ÔØ]™Y˜]Ú\ÉË

OO™ÛÊ	Ú[\ÜÉÊJJNØÛÛœÝ™XYOZ[\Ü˜]Úš][\Ë™š[\ŠOœ‹œÙ[XÝY	‰œ‹œÝ]\ÏOOIÜ™]šY]ÙY	É‰ˆ\‹™\œ›ÜœÏË›[™Ý
KÜ™X]YZ[\Ü˜]Úš][\Ë™š[\ŠOœ‹œÝ]\ÏOOIØÜ™X]Y	ÊNÝšY]Ë˜\[™
Y\ÜØYÙJÜ™X]Y›[™Ý
ÉÈÜ™X]Y0­È	ÊÜ™XYK›[™Ý
ÉÈ˜[Y™]šY]ÙY0­È	ÊÚ[\Ü˜]Úš][\Ë™š[\ŠOœ‹œÙ[XÝY	‰œ‹œÝ]\ÈOOIØÜ™X]Y	É‰ˆ\™XYKš[˜ÛY\ÊŠJK›[™Ý
ÉÈ™YY™]šY]ÉÊJNÝšY]Ë˜\[™
X›JÉÐÔÕˆ›ÝÉË	Ñ\]Z\Y[	Ë	ÔÝÜ˜YÙIË	ÔÝ]IË	Ô™]šY]É×K[\Ü˜]Úš][\Ë›X\
O–Ü‹˜ÜÝ—Ü›ÝË‹š[œ]›˜[YKØØ][ÛœË™š[™
O›šYOO\‹š[œ]›ØØ][Û—ÚY
OË›˜[Y_	ÐÚÛÜÙHØØ][Û‰Ë‹œÝ]\ÊÊ‹™\œ›ÜœÏË›[™ÝÉÈ0­È	ÊÜ‹™\œ›ÜœËš›Ú[Š	ÎÈ	ÊN‰ÉÊK]ÛŠ‹œÝ]\ÏOOIØÜ™X]Y	ÏÉÓ˜]]™H™XÛÜ™	Î‰ÑY]›ÝÉË

OOœ‹œÝ]\ÏOOIØÜ™X]Y	ÏÛØØ][Û‹˜\ÜÚYÛŠ	ËÚ][KÉÊÙ[˜ÛÙUT’PÛÛ\Û™[
‹™[]WÚY
JNœ™]šY]Ò[\Ü›ÝÊŠJWJJJNØÛÛœÝÛÛ›ÛÏXXÝ[ÛœÊ]ÛŠ	Ô™Yœ™\ÚØ]™Y˜]Ú	Ë\Þ[˜Ê
OOžÚ[\Ü˜]ÚX]ØZ]\J	Ú[\ÜËÙÙ]	ËÚYš[\Ü˜]ÚšYJNØ]ØZ]™[™\˜]Ú

_JJNÚYŠ™XYK›[™Ý
XÛÛ›ÛË˜\[™
]ÛŠ	Ô™]šY]ÈÜ™X][ÛˆÙˆ	ÊÜ™XYK›[™Ý
ÉÈ][\ÉË

OOš[\ÜXÝ[Û‘X[ÙÊ	ØÜ™X]IË™XYJK	ÛXZ[‰ÊJNÚYŠÜ™X]YœÛÛYJOœ‹›X™[ÜÝ]\ÏOOIÜ[™[™ÉÊJXÛÛ›ÛË˜\[™
]ÛŠ	Ô™]šY]È[™[™ÈHX™[ÉË

OOš[\ÜX™[X[ÙÊÜ™X]Y™š[\ŠOœ‹›X™[ÜÝ]\ÏOOIÜ[™[™ÉÊJJJNÝšY]Ë˜\[™
ÛÛ›ÛÊNÜ[™[™Ð˜[›™\Š
_B™[˜Ý[Ûˆ™]šY]Ò[\Ü›ÝÊ›ÝÊ^ØÛÛœÝ˜]ÚYZ[\Ü˜]ÚšYÙ[XÝ[Û”™]š\Ú[ÛZ[\ÜÙ[XÝ[Û”™]š\Ú[ÛŽÚYŠÉØÜ™X][™ÉË	Ü™]šY]ÉË	ØÜ™X]Y	×Kš[˜ÛY\Ê›ÝËœÝ]\ÊJ]›ÝÈ\œ›ÜŠ	Õ\È›ÝÈ\ÈHØ]™YÜ\˜][Û‹ˆ[œÜXÝ™XÛÝ™\žH™Y›Ü™HY][™ÈÜˆ™]žZ[™Ë‰ÊNØÛÛœÝ˜YXÛÛ™J›ÝËš[œ]
K›Ü›O[›ÙJ	Ù]‰Ë[	Ù›Ü›IÊNÙ›Ü›K˜\[™
›ÙJ	Ü	Ë	ÐÔÕˆ›ÝÈ	ÊÜ›ÝË˜ÜÝ—Ü›ÝÊÉÈ0­ÈÛÝ\˜ÙHQ	ÊÊ›ÝË›ÜšYÚ[˜[™^\›˜[ÚY	Û›ÝÝ\YY	ÊJJNÙ›ÜŠÛÛœÝÚÙ^KX™[HÙˆÖÉÛ˜[YIË	Ñ\]Z\Y[˜[YI×KÉÜÙ\šX[	Ë	ÔÙ\šX[[X™\‰×KÉÛX[Y˜XÝ\™\‰Ë	ÓX[Y˜XÝ\™\‰×KÉÛ[Ù[	Ë	Ó[Ù[	×KÉÙ\ØÜš\[Û‰Ë	Ñ\ØÜš\[Û‰×WJYšY[
›Ü›KX™[˜YÚÙ^WKÙ^OOOIÙ\ØÜš\[Û‰ÏÉÝ^\™XIÎ‰Ý^	ËO™˜YÚÙ^WO]ŠNÜÙ[XÝ
›Ü›K	Ò[œÚYH
Ü[Û˜[
IËÖÉÉË	ÕÜ]™[È›È\™[	×K‹‹›ØØ][ÛœË›X\
O–ÛšY›˜[YWJWK˜Y›ØØ][Û—ÚYO™˜Y›ØØ][Û—ÚY]ŠNÜÙ[XÝ
›Ü›K	Ñ\]Z\Y[Ø]YÛÜžIËÖÉÉË	ÐÚÛÜÙHHØ]YÛÜžI×K‹‹\\Ë›X\
O–ÝšY›˜[YWJWK˜Y\WÚYO™˜Y\WÚY]ŠNÜÙ[XÝ
›Ü›K	ÐÛÛ™][Û‰ËÉÕ[œ™]šY]ÙY	Ë	Ô™XYIË	Ó™YYÈ][[Û‰Ë	ÓXZ[[˜[˜ÙIË	Ô]X\˜[[™Y	Ë	Ð\˜Ú]™Y	Ë	Ô™]\™Y	Ë	Ðœ›ÚÙ[‰Ë	Õ˜\ÚY	×K›X\
O–Ý‹—JK˜Yš[\ÜØÛÛ™][Û‹O™˜Yš[\ÜØÛÛ™][Û]ŠNØÚXÚØ›Þ
›Ü›K	Ô\ÚXØ[H[œÜXÝY[™ØY™HÈ\ÙIË˜Yœ™]šY]ÙYO™˜Yœ™]šY]ÙY]ŠNØÛÛœÝØ]™OX\Þ[˜ÈÙ[XÝYOžØÛÛœÝ™\Ý[X]ØZ]Üš]J	Ú[\ÜËÜØ]™IËÚY˜˜]ÚY[™^œ›ÝËš[™^[œ]™˜YÙ[XÝYK	ÔØ]™H[\Ü™]šY]ÉË˜]ÚY
ÉÎ‰ÊÜ›ÝËš[™^
NÚYŠÙ[XÝ[Û”™]š\Ú[ÛˆOOZ[\ÜÙ[XÝ[Û”™]š\Ú[ÛŠ\™]\›ŽÚ[\Ü˜]Ú\™\Ý[ØÛÜÙQX[ÙÊYJNØ]ØZ]™[™\˜]Ú

_NÙ›Ü›K˜\[™
XÝ[ÛœÊ]ÛŠ	ÐØ[˜Ù[	Ë

OO˜ÛÜÙQX[ÙÊ
JK]ÛŠ	ÔÚÚ\\È›ÝÉË

OOœØ]™J˜[ÙJJK]ÛŠ	ÔØ]™H›ÝÈ™]šY]ÉË

OOœØ]™JYJK	ÛXZ[‰ÊJJNÛÜ[‘X[ÙÊ	Ô™]šY]È[\ÜY\]Z\Y[	Ë›Ü›J_B˜\Þ[˜È[˜Ý[Ûˆ[\ÜX™[X[ÙÊ›ÝÜÊ^ÂˆYŠ[X™[[\]\Ë›[™Ý
^ØÛÛœÝY[]OXÛÛ^ËšY[]K[\]\ÏX]ØZ]\J	ÛX™[ËÝ[\]\ÉË[™Yš[™YY[]JNÚYŠY[]HOOXÛÛ^ËšY[]J\™]\›ŽÛX™[[\]\Ï][\]\ßBˆ›ÝÜÏ\›ÝÜË™š[\ŠOœ‹›X™[ÜÝ]\ÏOOIÜ[™[™ÉÊNÚYŠ\›ÝÜË›[™Ý
]›ÝÈ\œ›ÜŠ	Ó›È[™[™È[\ÜYX™[È™[XZ[‹ˆ™Yœ™\ÚHØ]™Y˜]Úš\œÝ‰ÊNÂˆÛÛœÝ˜]ÚZ[\Ü˜]Ú˜]ÚYX˜]ÚšYÙ[XÝY[™]ÈÙ]
›ÝÜË›X\
Oœ‹š[™^
JK›Ü›O[›ÙJ	Ù]‰Ë[	Ù›Ü›IÊK[\]O[›ÙJ	ÜÙ[XÝ	ÊK™\Ý[Ï[›ÙJ	Ù]‰ÊNÛ]]Y]YTÝÜYY˜[ÙK]Y]YTÙ[™[™ÏY˜[ÙKš[ÛÛ›ÛÏV×NÂˆ[\]KœÙ]]šX]J	Ø\šXK[X™[	Ë	ÓX™[[\]H›Üˆ[\ÜY][\ÉÊNÝ[\]K˜\[™
™]ÈÜ[ÛŠ	ÐÚÛÜÙHHØ]™Y[\]IË	ÉÊJNÙ›ÜŠÛÛœÝÙˆX™[[\]\Ê][\]K˜\[™
™]ÈÜ[ÛŠ›˜[YJÉÈ0­È	ÊÝœ›Ùš[JÉÈ0­È‰ÊÝœ™]š\Ú[Û‹šY
JNÂˆÛÛœÝ\Ý[›ÙJ	Ù]‰ÊNÙ›ÜŠÛÛœÝ›ÝÈÙˆ›ÝÜÊ^ØÛÛœÝØ[›ÙJ	Ú[œ]	ÊNØØ‹\OIØÚXÚØ›Þ	ÎØØ‹˜ÚXÚÙY]YNØØ‹›Û˜Ú[™ÙOJ
OO˜Ø‹˜ÚXÚÙYÜÙ[XÝY˜Y
›ÝËš[™^
NœÙ[XÝY™[]J›ÝËš[™^
NØÛÛœÝ[™O[›ÙJ	ÛX™[	ÊNÛ[™K˜\[™
Ø‹ØÝ[Y[˜Ü™X]U^›ÙJ›ÝËš[œ]›˜[YJÉÈ0­ÈÔÕˆ›ÝÈ	ÊÜ›ÝË˜ÜÝ—Ü›ÝÊÉÈ0­È	ÊÜ›ÝË›X™[ÜÝ]\ÊJNÛ\Ý˜\[™
[™J_BˆÛÛœÝ™]šY]ÏX]ÛŠ	Ô™]šY]ÈÙ[XÝY[\ÜYX™[ÉË\Þ[˜Ê
OOžÚYŠ\Ù[XÝYœÚ^™J]›ÝÈ\œ›ÜŠ	ÔÙ[XÝ]X\ÝÛ™H[\ÜY][K‰ÊNØÛÛœÝÚÜÙ[[X™[[\]\Ë™š[™
OšYOO][\]K˜[YJNÚYŠXÚÜÙ[Š]›ÝÈ\œ›ÜŠ	ÐÚÛÜÙHHØ]™Y[\]K‰ÊNØÛÛœÝÚÙ[XØ\\™UZJ
KÙ[XÝ[Û”™]š\Ú[ÛZ[\ÜÙ[XÝ[Û”™]š\Ú[Û‹Ù[XÝY›ÝÜÏ\›ÝÜË™š[\ŠOœÙ[XÝYš\Ê‹š[™^
JKÙ^\Ï\Ù[XÝY›ÝÜË›X\
OŠÚ[™^œ‹š[™^X™[ÚÙ^Nœ‹›X™[ÚÙ^K[]WÚYœ‹™[]WÚYJJNØÛÛœÝ™\ÜÛœÙOX]ØZ]\J	ÛX™[ËÜ™]šY]ÉËÛ[ÙN‰Ú][IË[]WÚYÎšÙ^\Ë›X\
Ož™[]WÚY
K[\]WÚY˜ÚÜÙ[‹šY[\]WÜ™]š\Ú[ÛŽ˜ÚÜÙ[‹œ™]š\Ú[ÛŸJNÚYŠ]ZPÝ\œ™[
ÚÙ[Š_Ù[XÝ[Û”™]š\Ú[ÛˆOOZ[\ÜÙ[XÝ[Û”™]š\Ú[ÛŸ˜]ÚOOZ[\Ü˜]ÚÙ^\Ë›X\
Ožš[™^
Kš›Ú[Š	ß	ÊHOO\›ÝÜË™š[\ŠOœÙ[XÝYš\Ê‹š[™^
JK›X\
Oœ‹š[™^
Kš›Ú[Š	ß	Ê_[\]K˜[YHOOXÚÜÙ[‹šY
\™]\›ŽØÛÛœÝ™]šY]ÜÏ\™\ÜÛœÙKœ™]šY]Üß×NÚYŠ™]šY]ÜË›[™ÝOOZÙ^\Ë›[™Ý
]›ÝÈ\œ›ÜŠ	ÕHÛÛ\]H[\ÜYZ][H™]šY]ÈØ\È›Ý™]\›™Yˆ™]šY]ÈH]Y]YHYØZ[‹‰ÊNÜ™\Ý[Ëœ™\XÙPÚ[™[Š
NÜ]Y]YTÝÜYY˜[ÙNÜ]Y]YTÙ[™[™ÏY˜[ÙNÜš[ÛÛ›ÛÏV×NÙ›ÜŠÛÛœÝÚK™]šY]×HÙˆ™]šY]ÜË™[šY\Ê
J^ØÛÛœÝÙ^OZÙ^\ÖÚWK›ÝÏ\›ÝÜË™š[™
Oœ‹š[™^OOZÙ^Kš[™^
NÚYŠ\›Ýß›ÝË›X™[ÚÙ^HOOZÙ^K›X™[ÚÙ^_›ÝË™[]WÚYOOZÙ^K™[]WÚY
]›ÝÈ\œ›ÜŠ	Ò[\ÜY›ÝÈY[]HÚ[™ÙYˆ™]šY]ÈYØZ[‹‰ÊNØÛÛœÝØ\™\[™[
›ÙJ	Ü	Ë	ÐÔÕˆ›ÝÈ	ÊÜ›ÝË˜ÜÝ—Ü›ÝÊÉÈ0­È	ÊÜ›ÝËš[œ]›˜[YJÉÈ0­ÈÜšYÚ[˜[š[™\]Y\Ý™]Z[™Y	ÊJK[YÏ[›ÙJ	Ú[YÉÊNÚ[YËœÜ˜Ï\™]šY]Ëš[XYÙNÚ[YË˜[IÔ™]šY]ÙY[\ÜY][HX™[	ÎÚ[YË˜Û\ÜÓ˜[YOIÛX™[Z[XYÙIÎÛ]][\YY˜[ÙNØÛÛœÝš[X]ÛŠ	ÐÛÛ™š\›HHš[	Ë\Þ[˜Ê
OOžÚYŠ][\Y]Y]YTÝÜY]Y]YTÙ[™[™Ê]›ÝÈ\œ›ÜŠ	Õ\È[\Ü]Y]YH\ÈÝÜYˆ™Yœ™\ÚØ]™Y›ÙÜ™\ÜÈ™Y›Ü™H[›Ý\ˆXÝ[Û‹‰ÊNØ][\Y]YNÜ]Y]YTÙ[™[™Ï]YNÜš[ÛÛ›ÛË™›Ü‘XXÚ
ÛÛ›ÛO˜ÛÛ›Û™\ØX›Y]YJNÝž^Ø]ØZ]Üš]J	Ú[\ÜËÛX™[	ËÚY˜˜]ÚY[™^šÙ^Kš[™^™\]Y\ÝÚÙ^NšÙ^K›X™[ÚÙ^K™]šY]×ÚYœ™]šY]Ëœ™]šY]×ÚYK	Ôš[[\ÜY][HX™[	Ë˜]ÚY
ÉÎ‰ÊÚÙ^Kš[™^
NÜš[™\ØX›Y]YNÜ™\Ý[Ë˜\[™
Y\ÜØYÙJ	ÔHš[\ˆÛÛ™š\›YY\È™\]Y\Ýˆ[œÜXÝH\ÚXØ[X™[‰ÊJ_XØ]Ú
\œ›ÜŠ^Ü]Y]YTÝÜY]YNÜš[ÛÛ›ÛË™›Ü‘XXÚ
ÛÛ›ÛO˜ÛÛ›Û™\ØX›Y]YJNÜ™\Ü
\œ›ÜŠNÜ™\Ý[Ë˜\[™
Y\ÜØYÙJ	Ô]Y]YHÝÜYˆ™Yœ™\ÚØ]™Y›ÙÜ™\ÜÈ[™[œÜXÝ™XÛÝ™\žH™Y›Ü™Hš[[™È[›Ý\ˆ›ÝË‰Ë	Ø][[Û‰ÊJ_Yš[˜[^Ü]Y]YTÙ[™[™ÏY˜[ÙNÚYŠ\]Y]YTÝÜY
\š[ÛÛ›ÛË™š[\ŠÛÛ›ÛOˆXÛÛ›Û™]\Ù]œÙ[
K™›Ü‘XXÚ
ÛÛ›ÛO˜ÛÛ›Û™\ØX›YY˜[ÙJ__JNÜš[™]\Ù]œÙ[IÉÎÜš[ÛÛ›ÛËœ\Ú
š[
NØØ\™˜\[™
[YËš[
NÜ™\Ý[Ë˜\[™
Ø\™
__JNÂˆ›Ü›K˜\[™
›ÙJ	Ü	Ë	ÑXXÚ™]šY]ÙYX™[Ý^\È]XÚYÈ]ÈÜšYÚ[˜[ÔÕˆ›ÝÈ[™ÝX›Hš[Ù^Kˆ]™\žHš[™[XZ[œÈHÙ\\˜]HÛÛ™š\›X][Û‹‰ÊK[\]K\Ý™]šY]Ë™\Ý[ÊNÛÜ[‘X[ÙÊ	Ô™]šY]È[\ÜY][HX™[ÉË›Ü›JBŸB™[˜Ý[Ûˆ[\ÜXÝ[Û‘X[ÙÊXÝ[Û‹›ÝÜÊ^ØÛÛœÝ˜]ÚYZ[\Ü˜]ÚšYØÛÛœÝÙ[XÝY[™]ÈÙ]
›ÝÜË›X\
Oœ‹š[™^
JK›Ü›O[›ÙJ	Ù]‰Ë[	Ù›Ü›IÊK›ÙÜ™\ÜÏ[›ÙJ	Ü	ÊNÙ›Ü›K˜\[™
›ÙJ	Ü	ËXÝ[ÛOOIØÜ™X]IÏÉÐÜ™X]H™]šY]ÙY\]Z\Y[[ˆËPÜ˜]Kˆ^\Ý[™È™XÛÜ™ÈÚ[›Ý™HÝ™\Üš][‹‰Î‰Ôš[X™[ÈÛˆHHX™[š[\‹ˆ[œÜXÝ\ÚXØ[ÝØÚÈ™Y›Ü™HÛÛ™š\›Z[™Ë‰ÊJNÙ›ÜŠÛÛœÝ›ÝÈÙˆ›ÝÜÊXÚXÚØ›Þ
›Ü›K›ÝËš[œ]›˜[YKYK˜[YOO˜[YOÜÙ[XÝY˜Y
›ÝËš[™^
NœÙ[XÝY™[]J›ÝËš[™^
JNÛ]ÝÜY˜[ÙNØÛÛœÝÝÜ]ÛX]ÛŠ	ÔÝÜY\ˆÝ\œ™[][IË

OOžÜÝÜ]YNÜÝÜ]Û‹™\ØX›Y]Y_JNÜÝÜ]Û‹™]\Ù]œ]Y]YTÝÜIÝYIÎÜÝÜ]Û‹šY[]YNÙ›Ü›K˜\[™
›ÙÜ™\ÜËÝÜ]Û‹XÝ[ÛœÊ]ÛŠ	ÐØ[˜Ù[	Ë

OO˜ÛÜÙQX[ÙÊ
JK]ÛŠXÝ[ÛOOIØÜ™X]IÏÉÐÛÛ™š\›HÙ[XÝYÜ™X][Û‰Î‰ÐÛÛ™š\›HÙ[XÝYHX™[ÉË\Þ[˜Ê
OOžÚYŠ\Ù[XÝYœÚ^™J]›ÝÈ\œ›ÜŠ	ÔÙ[XÝ]X\ÝÛ™H][K‰ÊNÜÝÜ]Û‹šY[Y˜[ÙNÛ]Û™OLÙ›ÜŠÛÛœÝ›ÝÈÙˆ›ÝÜË™š[\ŠOœÙ[XÝYš\Ê‹š[™^
JJ^ÚYŠÝÜ
Xœ™XZÎÜ›ÙÜ™\ÜË^ÛÛ[JXÝ[ÛOOIØÜ™X]IÏÉÐÜ™X][™È	Î‰Ôš[[™È	ÊJÜ›ÝËš[œ]›˜[YNÚ[\Ü˜]ÚX]ØZ]Üš]J	Ú[\ÜËÉÊØXÝ[Û‹ÚY˜˜]ÚY[™^œ›ÝËš[™^™\]Y\ÝÚÙ^N˜XÝ[ÛOOIØÜ™X]IÏÜ›ÝË˜Ü™X]WÚÙ^Nœ›ÝË›X™[ÚÙ^_KXÝ[ÛOOIØÜ™X]IÏÉÐÜ™X]H[\ÜY\]Z\Y[	Î‰Ôš[[\ÜYX™[	Ë˜]ÚY
ÉÎ‰ÊÜ›ÝËš[™^
NÙÛ™JÊßXÛÜÙQX[ÙÊYJNØ]ØZ]™[™\˜]Ú

NÝØ\Ý
Û™JÉÈ][JÊHÛÛ\]YˆØ]™Y›ÙÜ™\ÜÈ\È™]Z[™Y‰ÊNßK	ÛXZ[‰ÊJJNÛÜ[‘X[ÙÊXÝ[ÛOOIØÜ™X]IÏÉÔ™]šY]ÈÙ[XÝYÜ™X][Û‰Î‰Ô™]šY]ÈÙ[XÝYHX™[ÉË›Ü›J_B˜\Þ[˜È[˜Ý[Ûˆ™XÛÝ™\žTYÙJ™]š\Ú[ÛŠ^ØÛÛœÝ›ÝÜÏX]ØZ]\J	Ü™XÛÝ™\žIÊNÚYŠ™]š\Ú[ÛˆOO\›Ý]U™\œÚ[ÛŠ\™]\›ŽÝ]J	Ô™XÛÝ™\žIË	ÐÚXÚÈØ]™YÝ]ÛÛY\È[™[œÜXÝ\]Z\Y[Üˆ\ÚXØ[X™[È™Y›Ü™H™\ÛÛš[™È[K‰ÊNØÛÛœÝ[™[™Ô›ÝÜÏ\[™[™Ê
NÚYŠ[™[™Ô›ÝÜË›[™Ý
]šY]Ë˜\[™
[™[
›ÙJ	Ú‰Ë	ÐXÝ[ÛœÈ]ØZ][™ÈÛÛ™š\›X][Û‰ÊK‹‹œ[™[™Ô›ÝÜË›X\
OžØÛÛœÝ[™O[›ÙJ	Ù]‰ÊNÛ[™K˜\[™
›ÙJ	Ü	Ë›X™[
ÉÈ0­È	ÊÝ[Y\Ý[\
˜]
JK]ÛŠœ]OOIÝÛÜšÜÚÜØÚXÚÜËÜÝ\	ÏÉÐÚXÚÈÚ[‹XÚXÚÈÝ\	Î‰ÐÚXÚÈØ]™Y™\Ý[	Ë

OOœœ]OOIÝÛÜšÜÚÜØÚXÚÜËÜÝ\	ÏÜ™XÛÝ™\”Ú[ÚXÚÊšÙ^JN˜ÚXÚÔ[™[™Ê
JJNÜ™]\›ˆ[™_JJJNÝšY]Ë˜\[™
X›JÉÓÜ\˜][Û‰Ë	ÔÝ]\ÉË	Ñ\]Z\Y[	Ë	ÐXÝ[Û‰×K›ÝÜË›X\
O–Ü‹˜XÝ[Û‹‹œÝ]\Ë
‹›˜]]™WØ\ÜÙ]ß×JK›X\
OO™K›˜[YJKš›Ú[Š	Ë	Ê_‹œ™\Ý[Û˜[Y_	ÉË]ÛŠ	Ò[œÜXÝÜ\˜][Û‰Ë

OOœ™XÛÝ™\žQX[ÙÊŠJWJJJ_B˜\Þ[˜È[˜Ý[ÛˆÚXÚÔ[™[™Ê
^ØÛÛœÝÜšYÚ[˜[ØÛÜO\ØÛÜJ
KY[]OXÛÛ^ËšY[]K™\Ý[X]ØZ]\J	ÛÜ\˜][Û‹ÜÝ]\ÉËÜ™\]Y\ÝÚÙ^NœšÙ^_KY[]JNÚYŠØÛÜJ
HOO[ÜšYÚ[˜[ØÛÜ_ÛÛ^ËšY[]HOOZY[]J\™]\›ŽØÛÛœÝÚ[“Ü™\\œ]OOIÝÛÜšÜÚÜÜÚ[‹[Ü™\‰ËX\šÙ\\Ú[“Ü™\ÜÚ[“Ü™\“X\šÙ\ŠšÙ^KœÝXš™XÝ
N›[˜[YÚ[•\›Z[˜[HH[X\šÙ\‰‰œ™\Ý[˜XÝ[ÛOOIÝÛÜšÜÚÜÜÚ[—ÛÜ™\‰É‰œ™\Ý[›˜]]™WÚ›ØOO]YK˜[Y›ÝÝ\Y\™\Ý[œÝ]\ÏOOIÛ›ÝÜÝ\Y	É‰“Øš™XÝšÙ^\Ê™\Ý[
K›[™ÝOOLI‰“Øš™XÝš\ÓÝÛŠ™\Ý[	ÜÝ]\ÉÊK[™›Ï[›ÙJ	Ù]‰ÊNÚ[™›Ë˜\[™
›ÙJ	Ü	Ë	ÔØ]™Y™\]Y\ÝÙ^Nˆ	ÊÜšÙ^JÉÈ0­È	ÊÜ›X™[
ÉÈ0­È	ÊÜ™\Ý[œÝ]\ÊJNÚYŠÚ[“Ü™\‰‰Š[X\šÙ\Ÿ
ÉØÛÛ\]Y	Ë	ØØ[˜Ù[Y	×Kš[˜ÛY\Ê™\Ý[œÝ]\ÊI‰ˆ]˜[YÚ[•\›Z[˜[
_
™\Ý[œÝ]\ÏOOIÛ›ÝÜÝ\Y	É‰ˆ]˜[Y›ÝÝ\Y
JJ^Ú[™›Ë˜\[™
Y\ÜØYÙJ	ÕH™]\›™YÝ]\ÈÙ\È›ÝX]Ú\ÈØ]™YÚ[‹[Ü™\ˆ™\]Y\Ýˆ]™[XZ[œÈØÚÙY›Üˆ[œÜXÝ[Û‹‰Ë	Ø][[Û‰ÊK]ÛŠ	Ð˜XÚÈÈ™XÛÝ™\žIË

OO˜ÛÜÙQX[ÙÊYJJJNÛÜ[‘X[ÙÊ	ÔØ]™YXÝ[Ûˆ™\Ý[	Ë[™›ÊNÜ™]\›ŸZYŠÉØÛÛ\]Y	Ë	ØØ[˜Ù[Y	×Kš[˜ÛY\Ê™\Ý[œÝ]\ÊJ^ÚYŠœ]OOIÝÛÜšÜÚÜÜØ]™IÊ\™[[Ý™T[™[™ÊšÙ^JNÚYŠÚ[“Ü™\ŠXÛX\”Ú[“Ü™\“X\šÙ\ŠšÙ^KœÝXš™XÝ
NÚ[™›Ë˜\[™
›ÙJ	Ü	Ëœ]OOIÝÛÜšÜÚÜÜØ]™IÏÉÕHØ]™YÝ]ÛÛYH\È]˜Z[X›Kˆ™]\›ˆÈH[›™\ˆ[™ÚXÚÈØ]™HÝ]\ÈÈ™XÛÛ˜Ú[H\ÈØÝ[Y[‰Î‰ÕHØ]™YÝ]ÛÛYH\ÈÛÛ™š\›YYˆ]Ú[›Ý™H™\ÝX›Z]Y‰ÊK]ÛŠ	Ô™]\›ˆÈ™XÛÝ™\žIË

OOžØÛÜÙQX[ÙÊYJNÙÛÊ	Ü™XÛÝ™\žIË˜[ÙJ_JJ_Y[ÙHYŠ™\Ý[œÝ]\ÏOOIÛ›ÝÜÝ\Y	Ê^Ú[™›Ë˜\[™
›ÙJ	Ü	Ë	ÕHÙ\™\ˆ\È›ÈÝ\YÜ\˜][Ûˆ›Üˆ\È™\]Y\Ýˆ›È]]ÛX]XÈ™]žHÚ[™HÙ[‰ÊK]ÛŠ	ÐXÚÛ›ÝÛYÙH›ÈÜ\˜][ÛˆÝ\Y	Ë

OOžÚYŠØÛÜJ
HOO[ÜšYÚ[˜[ØÛÜ_ÛÛ^ËšY[]HOOZY[]_Ú[“Ü™\‰‰ˆ\Ú[“Ü™\“X\šÙ\ŠšÙ^KœÝXš™XÝ
J\™]\›ŽÚYŠœ]OOIÝÛÜšÜÚÜÜØ]™IÊ\™[[Ý™T[™[™ÊšÙ^JNÚYŠÚ[“Ü™\ŠXÛX\”Ú[“Ü™\“X\šÙ\ŠšÙ^KœÝXš™XÝ
NØÛÜÙQX[ÙÊYJNÙÛÊ	Ü™XÛÝ™\žIË˜[ÙJ_JJ_Y[ÙH[™›Ë˜\[™
›ÙJ	Ü	Ë	ÕHÝ]ÛÛYHÝ[™YYÈ[œÜXÝ[Û‹ˆ™Yœ™\ÚHØ]™Y˜]Ú^[Ý]Üˆ™XÛÝ™\žH\Ý™Y›Ü™H[›Ý\ˆ][\ˆÈ›Ý™\X]H\ÚXØ[š[‰ÊK]ÛŠ	Ð˜XÚÈÈ™XÛÝ™\žIË

OO˜ÛÜÙQX[ÙÊYJJJNÛÜ[‘X[ÙÊ	ÔØ]™YXÝ[Ûˆ™\Ý[	Ë[™›Ê_B™[˜Ý[Ûˆ™XÛÝ™\žQX[ÙÊ›ÝÊ^ØÛÛœÝXØÛÝ[VÉÝ\Ù\œËØÜ™X]IË	Ý\Ù\œËÝ\]I×Kš[˜ÛY\Ê›ÝË˜XÝ[ÛŠK›Ü›O[›ÙJ	Ù]‰Ë[	Ù›Ü›IÊNÙ›Ü›K˜\[™
›ÙJ	Ü	Ë	ÓÜ\˜][ÛŽˆ	ÊÜ›ÝË˜XÝ[ÛŠÉÈ0­È	ÊÜ›ÝËœÝ]\ÊK›ÙJ	Ü	Ë	ÔØ]™YQˆ	ÊÜ›ÝËšY
K›ÙJ	Ü	Ë	ÔÝ\Yˆ	ÊÝ[Y\Ý[\
›ÝË˜Ü™X]YØ]
JJNÚYŠ›ÝË›Y\ÜØYÙJY›Ü›K˜\[™
›ÙJ	Ü	Ë›ÝË›Y\ÜØYÙJJNÚYŠXØÛÝ[
Y›Ü›K˜\[™
[šÊ	ÓÜ[ˆX[˜YÙH\Ù\œÉË	ËØÛÛXÝ[Û‹ÛY[X™\œÉÊJNÚYŠ›ÝËš[[	‰“Øš™XÝšÙ^\Ê›ÝËš[[
K›[™Ý
^ØÛÛœÝ[[\[™[
›ÙJ	ÚÉË	ÔØ]™Y™\]Y\Ý	ÊJNÙ›ÜŠÛÛœÝÚÙ^K˜[YWHÙˆØš™XÝ™[šY\Ê›ÝËš[[
JZ[[˜\[™
›ÙJ	Ü	ËÙ^Kœ™\XÙP[
	×ÉË	È	ÊJÉÎˆ	ÊÊ˜[YOOO[[ÉÛ›Û™IÎ”Ýš[™Ê˜[YJJJJNÙ›Ü›K˜\[™
[[
NßY›ÜŠÛÛœÝHÙˆ›ÝË›˜]]™WØ\ÜÙ]ß×JY›Ü›K˜\[™
›ÙJ	Ü	ËK›˜[YJÉÈ0­È	ÊÊK™\œ›ÜŸK˜ÛÛ™][ÛŸ	ÉÊJÉÈ0­È	ÊÊKœ\™[	ÉÊJÉÈ0­È™XÛÜ™	ÊÊKšY	Ý[˜]˜Z[X›IÊJJNÙ›ÜŠÛÛœÝÈÙˆ›ÝË˜ÛÛ^ËœÝ\ß×JY›Ü›K˜\[™
›ÙJ	Ü	Ë	Ô[›™Yˆ	ÊÊË˜ÛÛ™][Û—ØY\Ÿ	Ý[˜Ú[™ÙY	ÊJÉÈ0­È\Ý[˜][Ûˆ	ÊØY™\ÜÊËœ\™[ØY\ŠJJNÙ›ÜŠÛÛœÝˆÙˆ›ÝËœ™]\›—Û›Ý\ß›ÝË˜ÛÛ^Ëœ™]\›—Û›Ý\ß×JY›Ü›K˜\[™
›ÙJ	Ü	Ë	Ô™]\›ˆ›ÝNˆ	ÊÛ‹^
JNÙ›Ü›K˜\[™
Y\ÜØYÙJXØÛÝ[ÉÒ[œÜXÝHØ]™Y\Ù\ˆ›Ùš[H[™]È\Ù\ˆQ[ˆX[˜YÙH\Ù\œÈ™Y›Ü™H™\ÛÛš[™È\È™\]Y\Ý‰Î‰Ò[œÜXÝH\ÚXØ[™\Ý[[™˜]]™H˜[Y\Ëˆš[š\Ú[™È[ˆ[˜Ù\Z[ˆš[XÚÛ›ÝÛYÙ\È[œÜXÝYÝ]]È]]\Ý›Ý›[™HÙ[™[›Ý\ˆš[‰Ë	Ø][[Û‰ÊJNÛ]™\šYšYYY˜[ÙNØÚXÚØ›Þ
›Ü›KXØÛÝ[ÉÒH[œÜXÝYHØ]™Y\Ù\ˆ›Ùš[K‰Î‰ÒH[œÜXÝY\ÚXØ[\]Z\Y[ÜˆX™[È[™HÝÜ™Y˜[Y\Ë‰Ë˜[ÙKO™\šYšYY]ŠNÙ›ÜŠÛÛœÝÝ]ÛÛYHÙˆÉØÛÛ\]IË	ØØ[˜Ù[	×JY›Ü›K˜\[™
]ÛŠÝ]ÛÛYOOOIØÛÛ\]IÏÉÐÛÛ™š\›HÛÛ\][Û‰Î‰ÐÛÛ™š\›HØY™HØ[˜Ù[][Û‰Ë\Þ[˜Ê
OOžÚYŠ]™\šYšYY
]›ÝÈ\œ›ÜŠ	Ò[œÜXÝ[™ÛÛ™š\›HH\ÚXØ[™\Ý[š\œÝ‰ÊNØ]ØZ]Üš]J	Ü™XÛÝ™\žKÜ™\ÛÛ™IËÚYœ›ÝËšYÝ]ÛÛYK˜]]™WÚ›ØŽˆH\›ÝË›˜]]™WÚ›Ø‹\ÚÝÜÚ›ØŽˆH\›ÝË™\ÚÝÜÚ›Ø‹[œÜXÝYY_K	Ô™\ÛÛ™H[\œ\YÜ\˜][Û‰Ë›ÝËšY
NØÛÜÙQX[ÙÊYJNØ]ØZ]ÛÊ	Ü™XÛÝ™\žIË˜[ÙJNÝØ\Ý
	Ô™XÛÝ™\žHXÚ\Ú[ÛˆØ]™Y‰ÊNßJJNÙ›Ü›K˜\[™
]ÛŠ	ÐØ[˜Ù[	Ë

OO˜ÛÜÙQX[ÙÊ
JJNÛÜ[‘X[ÙÊ	Ò[œÜXÝ[\œ\YÜ\˜][Û‰Ë›Ü›J_B™[˜Ý[Ûˆ\™Ø\™T[™[
]šXÙK[š]X[
^ØÛÛœÝØ\™\[™[
›ÙJ	Ú‰Ë]šXÙOOOIÜš[\‰ÏÉÔÕTSˆX™[š[\‰Î‰ÔHÎLŒÙX˜Ø[IÊJK™\Ý[[›ÙJ	Ù]‰ÊNÜ™\Ý[œÙ]]šX]J	Ü›ÛIË	ÜÝ]\ÉÊNØÛÛœÝZ[Y]OOžÜ™\Ý[œ™\XÙPÚ[™[Š›ÙJ	Ü	Ë]K›Y\ÜØYÙ_
]K˜ÛÛ›™XÝYÉÔ™XYIÎ‰Ó›Ý™XYIÊJJNØÛÛœÝÝ\Ï[›ÙJ	ÛÛ	ÊNÙ›ÜŠÛÛœÝÝ\Ùˆ]KœÝ\ß×J\Ý\Ë˜\[™
›ÙJ	ÛIËÝ\
JNÜ™\Ý[˜\[™
Ý\Ê_NÜZ[
[š]X[ßJNØÛÛœÝ™XÛÛ›™XÝX]ÛŠ]šXÙOOOIÜš[\‰ÏÉÔ™XÛÛ›™XÝš[\‰Î‰Ô™XÛÛ›™XÝÙX˜Ø[IË\Þ[˜Ê
OOžÜ™XÛÛ›™XÝ™\ØX›Y]YNÜ™\Ý[œ™\XÙPÚ[™[Š›ÙJ	Ü	Ë	ÐÚXÚÚ[™ÈHÛÛ›™XÝ[Û¸ )‰ÊJNÝž^ØÛÛœÝ]OX]ØZ]\J	Ú\™Ø\™KÜ™XÛÛ›™XÝ	ËÙ]šXÙ_JNÚYŠØ\™š\ÐÛÛ›™XÝY
\Z[
]J_XØ]Ú
\œ›ÜŠ^ÚYŠØ\™š\ÐÛÛ›™XÝY
\Z[
ÛY\ÜØYÙN™\œ›Ü‹›Y\ÜØYÙKÝ\Î–ÉÐÚXÚÈHØX›H[™ÝÙ\‹[ˆžH™XÛÛ›™XÝYØZ[‹‰×_J_Yš[˜[^Ü™XÛÛ›™XÝ™\ØX›YY˜[Ù__JNØØ\™˜\[™
™\Ý[™XÛÛ›™XÝ
NÜ™]\›ˆØ\™B˜\Þ[˜È[˜Ý[ÛˆÞ\Ý[TYÙJ™]š\Ú[ÛŠ^ØÛÛœÝ]OX]ØZ]\J	ÜÞ\Ý[IÊNÚYŠ™]š\Ú[ÛˆOO\›Ý]U™\œÚ[ÛŠ\™]\›ŽÝ]J	ÔÞ\Ý[IË	ÔHÙ\šXÙ\Ëš[\ˆ™XY[™\ÜÈ[™š]˜]H™XÛÝ™\žH˜XÚÝ\Ë‰Ë]ÛŠ	Ô™Yœ™\ÚÝ]\ÉË

OO™ÛÊ	ÜÞ\Ý[IË˜[ÙJJJNØÛÛœÝ›ÝÜÏVÖÉÐËPÜ˜]IË]KšÛYX›Þ
ÉÈ0­È	ÊÙ]KšÛYX›ÞÝ™\œÚ[Û—KÉÐÛÛ\[š[Û‰Ë]K˜ÛÛ\[š[Û—KÉÔHX™[š[\‰Ë]Kœš[\Ë˜ÛÛ›™XÝYÉÐÛÛ›™XÝY0­È	ÊÙ]Kœš[\‹ÚYÛ[JÉÈ0åÈ	ÊÙ]Kœš[\‹šZYÚÛ[JÉÈ[HÝØÚÉÎ‰Ó›Ý™XYI×KÉÐØ[Y\˜H]šXÙ\ÈÛˆIË]K˜Ø[Y\˜WÙ]šXÙ\×KÉÑœ™YHÝÜ˜YÙIË]K™œ™YWÙØŠÉÈÐ‰×KÉÔš]˜]H˜XÚÝ\ÉË]Kœš]˜]WØ˜XÚÝ\ÊÊ]K˜˜XÚÝ\ÉÈ0­È	ÊÙ]K˜˜XÚÝ\œÝ]\Î‰ÉÊWWNÝšY]Ë˜\[™
X›JÉÔÞ\Ý[HÛÛ\Û™[	Ë	ÐÝ\œ™[Ý]\É×K›ÝÜÊK\™Ø\™T[™[
	Üš[\‰Ë]Kœš[\ŠK\™Ø\™T[™[
	ØØ[Y\˜IË]K˜Ø[Y\˜JJNÚYŠ]KœÝÜ˜YÙOË›Y\ÜØYÙJ]šY]Ë˜\[™
Y\ÜØYÙJ]KœÝÜ˜YÙK›Y\ÜØYÙK	Ø][[Û‰ÊJNÝšY]Ë˜\[™
[™[
›ÙJ	Ü	Ë	Ð˜XÚÝ\È™[XZ[ˆš]˜]HÛˆHKˆÜ™X][™ÈHÛÛœÚ\Ý[˜XÚÝ\œšYY›H]\Ù\ÈHÚ[ÜÚÈ[™™\Ý\È]‰ÊK]ÛŠ	Ô™]šY]È™XÛÝ™\žH˜XÚÝ\	Ë

OO›Ü[‘X[ÙÊ	ÐÛÛ™š\›Hš]˜]H™XÛÝ™\žH˜XÚÝ\	Ë›ÙJ	Ü	Ë	ÕHÚ[ÜÚÈœšYY›H]\Ù\È[™™\Ý\ËˆH\˜Ú]™HÝ^\Èš]˜]HÛˆHK‰ÊKXÝ[ÛœÊ]ÛŠ	ÐØ[˜Ù[	Ë

OO˜ÛÜÙQX[ÙÊ
JK]ÛŠ	ÐÛÛ™š\›H˜XÚÝ\	Ë\Þ[˜Ê
OOžØ]ØZ]Üš]J	Ø˜XÚÝ\ÜÝ\	ËßK	ÐÜ™X]Hš]˜]H˜XÚÝ\	ÊNØÛÜÙQX[ÙÊYJNÝØ\Ý
	Ð˜XÚÝ\Ý\YˆØZ]›ÜˆÙ\šXÙH™\Ý\[ˆ™Yœ™\ÚÝ]\Ë‰ÊNßK	ÛXZ[‰ÊJJJJJ_B˜\Þ[˜È[˜Ý[ÛˆÝ\

^Ýž^ØÛÛ^X]ØZ]ÛÜšÜÚÜœ™Yœ™\Ú

NØ]ØZ]ÛÊ[š]X[YÙK˜[ÙJ_XØ]Ú
\œ›ÜŠ^ÜÚYÛ™YÝ]

NÚYŠ\œ›Ü‹œÝ]\ÈOOMJ\™\Ü
\œ›ÜŠ__BœÝ\

NÂœ™]\›ˆÂˆ™Yœ™\ÚÛÜšÜÚÜšY]ËˆÙ[XÝÛÜšÜÚÜ[]Kˆ\]UÛÜšÜÚÜÙ[XÝ[Û‹ˆÜ[”Ú[ÚXÚËˆ™XÛÝ™\”Ú[ÚXÚËˆØ[“X]™J
^ÚYŠ\Þ_X™[Y]Ü\ÞJ^ÝØ\Ý
	ÕØZ]›ÜˆÛÛ™š\›X][ÛˆÈš[š\Ú‰ÊNÜ™]\›ˆ˜[Ù_ZYŠX™[Y]Ü‰‰ˆ[X™[Y]Ü‹˜Ø[“X]™J
J\™]\›ˆ˜[ÙNÚYŠX™[Y]Ü‘\I‰ˆ]Ú[™ÝË˜ÛÛ™š\›J	Ñ\ØØ\™\ÙH[œØ]™YY]ÏÉÊJ\™]\›ˆ˜[ÙNÚYŠ^[Ý][˜Ù\Z[Š^Ü\œÚ\Ý[›™\”Ù\ÜÚ[ÛŠ
NÝØ\Ý
	ÐÚXÚÈHØ]™Y›ÛÛH™\Ý[™Y›Ü™HX]š[™È\ÈYÙK‰ÊNÜ™]\›ˆ˜[Ù_ZYŠÚ[“›Ý\Ñ\I‰ˆ]Ú[™ÝË˜ÛÛ™š\›J	ÓX]™H\ÈÚXÚÈÚ][œØ]™Y›Ý\ÏÈ^HÚ[›Ý™HØ]™YÛˆ\È]šXÙK‰ÊJ\™]\›ˆ˜[ÙNÚYŠX[ÙÑ\I‰ˆ]Ú[™ÝË˜ÛÛ™š\›J	Ñ\ØØ\™\ÙH[œØ]™Y›Ü›HY]ÏÉÊJ\™]\›ˆ˜[ÙNÚYŠ^[Ý]\J^ÚYŠ]Ú[™ÝË˜ÛÛ™š\›J	ÓX]™H\ÈYÙH[™ÙY\H›ÛÛH˜YØ]™YÛˆ\È]šXÙOÉÊJ\™]\›ˆ˜[ÙNÜ\œÚ\Ý[›™\”Ù\ÜÚ[ÛŠ
_\™]\›ˆY_KˆÙ[XÝ›ÛÛKˆ[Ý™Q˜]Ú[™Ëˆ™[[Ý™Q[\T›ÛÛKˆØ]™S^[Ý]ˆ\ÜÜÙJ
^Ù\ÜÜÙY]YNÜ[›™\Ø[˜\ÓØœÙ\™\Ë™\ØÛÛ›™XÝ

NÜ[›™\Ø[˜\ÓØœÙ\™\[[ØÛÛœÝÛØÛÜO\ØÛÜJ
NÚYŠÛØÛÜJ[X™[]Y]Y\Ë™[]JÛØÛÜJNÛX™[Y]ÜË™\ÜÜÙJ
NÛX™[Y]Ü[[ÛX™[Y]Ü‘\O[X™[Y]Ü\ÞOY˜[ÙNÛX™[Ù[XÝ[Û‹˜ÛX\Š
NÛX™[™]šY]ÜÏ[[ÛX™[™]šY]ÒYÏV×NÛX™[ÛÜšÜÜXÙO[[ÛX™[ÛÜšÜÜXÙPÚ[™ÙY
[	ÕHX™[ÛÜšÜÜXÙHÚ[™ÙYˆ™[ØYHYÙHÈÛÛ[YK‰ÊNÜ›Ý]U™\œÚ[ÛŠÊÎÜÚ[•ÚÙ[ŠÊÎÝÛÜšÜÚÜ™XYÚÙ[ŠÊÎÝÛÜšÜÚÜÙX\˜ÚÚÙ[ŠÊÎÝÛÜšÜÚÜÙX\˜Ú›ÝÜÏ[[ÝÛÜšÜÚÜÙX\˜ÚY[]O[[ÝÛÜšÜÚÜÙX\˜ÚÝÛ™\[[ÝÛÜšÜÚÜÙX\˜Ú^IÉÎÝÛÜšÜÚÜÙX\˜Ú™[™\”[™[™ÏY˜[ÙNÙX[ÙÑ\ØÚ
ÊÎØÛX\’[\˜[
ÛÛ^[Y\ŠNÛ\Ý[™\œË™›Ü‘XXÚ

Û˜[YK›—JOOÚ[™ÝËœ™[[Ý™Q]™[\Ý[™\Š˜[YK›ŠJNÚYŠX[ÙË›Ü[ŠYX[ÙË˜ÛÜÙJ
NÙX[ÙÐ›ÙKœ™\XÙPÚ[™[Š
NØÛÛ^[[Û^[Ý]˜Y[[Ú[\Ü˜]Ú[[ÜÚ[ÚXÚÏ[[ÜÚ[“›Ý\Ñ˜YIÉÎÜÚ[“›Ý\Ñ\OY˜[ÙNßBŸNÂŸB‚™[˜Ý[Ûˆ]˜Z[X›T\™[Ê™XÛÜ™Ë^ÛYYV×J^ØÛÛœÝ›ØÚÙY[™]ÈÙ]
^ÛYY
KžRY[™]ÈX\
™XÛÜ™Ë›X\
O–ÜšYJJNÜ™]\›ˆ™XÛÜ™Ë™š[\ŠOžÚYŠ˜\˜Ú]™Y
\™]\›ˆ˜[ÙNØÛÛœÝÙY[[™]ÈÙ]

NÛ]Ý\œ™[\ÝÚ[JÝ\œ™[
^ÚYŠ›ØÚÙYš\ÊÝ\œ™[šY
_ÙY[‹š\ÊÝ\œ™[šY
J\™]\›ˆ˜[ÙNÜÙY[‹˜Y
Ý\œ™[šY
NØÝ\œ™[XžRY™Ù]
Ý\œ™[œ\™[ÚYÝ\œ™[œ\™[ËšY
_\™]\›ˆY_J_B