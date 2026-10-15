// Common client ownership, navigation and request lifecycle for the companion.
const editorMode=new URLSearchParams(location.search).get('mode')==='editor'||!['127.0.0.1','localhost','[::1]'].includes(location.hostname);
function homeboxURL(path){const url=new URL(location.href);url.port='17745';url.pathname=path;url.search='';url.hash='';return url.href}
if(!crypto.randomUUID)crypto.randomUUID=()=>{const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');return [hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join('-')};
const clientId=crypto.randomUUID(); // A fresh page, including a duplicated tab, owns a fresh session.
let routeRevision=0,routeTitle='',routeStack=[],restoringRoute=false,routeTransition=false,formDirty=false,writeCount=0,activeScanRequest=null,itemActionOffer=null,itemActionOrigin=null,pendingItemAction=null;
const nativeFetch=window.fetch.bind(window);
const readPosts=new Set(['/workshop/get','/workshop/view','/workshop/resolve','/imports/get','/imports/list','/label/preview','/label/paper','/label/templates/result','/operation/status','/decode']);
const passivePosts=new Set(['/scan','/scan/cancel','/session/end','/session/activity','/camera/focus']);
window.fetch=async function(resource,options={}){
    const url=new URL(typeof resource==='string'?resource:resource.url,location.href),path=url.pathname;
    if(url.origin!==location.origin)return nativeFetch(resource,options);
    const method=(options.method||'GET').toUpperCase(),headers=new Headers(options.headers||{});
    headers.set('X-Homebox-Client',clientId);headers.set('X-Homebox-Client-Mode',editorMode?'editor':'kiosk');
    const templateSave=path==='/label/templates/save',writing=method!=='GET'&&!readPosts.has(path)&&!passivePosts.has(path)&&!templateSave;
    const controller=new AbortController(),readDeadline=readPosts.has(path),timer=setTimeout(()=>controller.abort(),readDeadline?60000:25000);
    if(writing)writeCount++;
    try{const response=await nativeFetch(resource,{...options,headers,signal:options.signal||controller.signal});const body=await response.arrayBuffer();return new Response(body,{status:response.status,statusText:response.statusText,headers:response.headers})}
    catch(error){if(writing)status.textContent='No confirmation received. Check Admin recovery before trying another create or print.';throw Error(error.name==='AbortError'?(readDeadline?'Label preview timed out. Select fewer items or preview again.':templateSave?'Template Save timed out. Its saved result will be checked.':'The request timed out. Check the saved result before retrying.'):error.message)}
    finally{clearTimeout(timer);if(writing)writeCount--}
};
api=async function(path,data,extraHeaders={}){const r=await fetch(path,data===undefined?{headers:extraHeaders}:{method:'POST',headers:{'Content-Type':'application/json',...extraHeaders},body:JSON.stringify(data)});let value;try{value=await r.json()}catch(e){const error=Error('The service did not return a readable result. Check recovery before retrying a write.');if(!r.ok)error.status=r.status;throw error}if(!r.ok){const error=Error(value.error||value.reason||'Request failed');error.status=r.status;throw error}return value};
function workflowBusy(){return writeCount>0||checkoutBusy||returnBusy||labelMakerBusy||(typeof workshopSavePending!=='undefined'&&workshopSavePending)}
function workflowMessage(message){view.querySelector('.workflow-message')?.remove();const panel=node('div',message,'workflow-message');panel.setAttribute('role','alert');(view.querySelector('.checkout-shell')||view).append(panel);return panel}
function captureRoute(){return {nodes:Array.from(view.childNodes),className:view.className,title:routeTitle,scroll:view.scrollTop,dirty:formDirty,identity:identityGeneration,instance:identityInstance,nav:document.querySelector('#layout-nav').textContent,modes:{checkoutMode,returnMode,problemMode,scanPurpose,returnDestinationFor,anonymousReturn,itemNoteMode}}}
function routeBack(discard=false){if(workflowBusy()){workflowMessage('Wait for the current confirmation to finish.');return}if(checkoutKey||returnKey){workflowMessage('Check the saved result before leaving this operation.');return}if((formDirty||labelMakerDirty)&&!discard&&routeStack.length&&!routeStack.at(-1).dirty){const overlay=node('div',undefined,'workflow-dialog'),panel=node('div',undefined,'notice');panel.append(node('h1','Discard these edits?'),primary('Keep editing',()=>overlay.remove()),primary('Discard & go back',()=>{overlay.remove();routeBack(true)}));overlay.append(panel);document.body.append(overlay);return}if(labelDesignerHandle){labelDesignerHandle.dispose();labelDesignerHandle=null}labelMakerDirty=false;cancelScanRequest();stopScan();stopPhoto();closeKeyboard();const previous=routeStack.pop();if(!previous){home();return}if(previous.identity!==identityGeneration||previous.instance!==identityInstance){home();return}const switched=itemActionOrigin;restoringRoute=true;view.replaceChildren(...previous.nodes);view.className=previous.className;routeTitle=previous.title;checkoutMode=previous.modes.checkoutMode;returnMode=previous.modes.returnMode;problemMode=previous.modes.problemMode;scanPurpose=previous.modes.scanPurpose;returnDestinationFor=previous.modes.returnDestinationFor;anonymousReturn=previous.modes.anonymousReturn;itemNoteMode=!!previous.modes.itemNoteMode;formDirty=previous.dirty;document.querySelector('#layout-nav').textContent=previous.nav;view.scrollTop=previous.scroll;routeRevision++;restoringRoute=false;clearItemActionOffer();itemActionOrigin=pendingItemAction=null;if(previous.className.includes('dashboard'))checkoutMode=returnMode=false;if(switched&&!previous.className.includes('dashboard')){routeTransition=true;try{if(switched.mode==='return')renderReturn();else renderCheckout()}finally{routeTransition=false}}ensureNavigation()}
const originalHeading=heading;
heading=function(title){if(!restoringRoute&&!routeTransition&&view.childNodes.length&&title!==routeTitle){routeStack.push(captureRoute());if(routeStack.length>30)routeStack.shift()}if(title!==routeTitle)routeRevision++;routeTitle=title;originalHeading(title);ensureNavigation()};
function ensureNavigation(){if(view.classList.contains('dashboard'))return;const row=view.querySelector('.toolbar');if(row&&Array.from(row.querySelectorAll('button:not([data-local-back])')).some(b=>b.textContent==='Back'))row.querySelector('[data-local-back]')?.remove();if(row&&!row.querySelector('[data-local-back]')&&!Array.from(row.querySelectorAll('button')).some(b=>b.textContent==='Back')){const back=node('button','Back','workflow-back');back.dataset.localBack='true';back.onclick=()=>routeBack();row.prepend(back)}for(const a of view.querySelectorAll('a[data-homebox]')){a.hidden=!editorMode;a.title='Open the native record in a separate tab; close that tab to return.'}}
new MutationObserver(ensureNavigation).observe(view,{childList:true,subtree:true});
function hasDraft(){return labelMakerDirty||formDirty||workshopDirty||checkoutCart.length>0||returnCart.length>0||!!problemDraft?.note||!!enrollment?.name}
function clearItemActionOffer(){itemActionOffer=null;for(const button of view.querySelectorAll('button'))if(button.textContent.startsWith('Check out this item instead')||button.textContent.startsWith('Return this item instead'))button.remove()}
function leaveTask(action){if(workflowBusy()){workflowMessage('Wait for the current confirmation to finish.');return}if(checkoutKey||returnKey){const overlay=node('div',undefined,'workflow-dialog'),panel=node('div',undefined,'notice');panel.append(node('h1','Check this operation first'),node('p','Its outcome is still uncertain. Keep the request until its saved result or recovery is resolved.'),primary('Keep task',()=>overlay.remove()),primary('Open recovery',()=>{overlay.remove();showRecovery();checkoutMode=false;returnMode=false}));overlay.append(panel);document.body.append(overlay);return}if(hasDraft()){const overlay=node('div',undefined,'workflow-dialog'),panel=node('div',undefined,'notice');panel.append(node('h1','Leave this task?'),node('p','Your unsaved edits or selected items will be discarded.'),primary('Keep editing',()=>overlay.remove()),primary('Discard & leave',()=>{overlay.remove();resetTask();action()}));overlay.append(panel);document.body.append(overlay);return}resetTask();action()}
function resetTask(){labelDesignerHandle?.dispose();labelDesignerHandle=null;labelMakerDirty=labelMakerBusy=false;labelQueue=[];labelMakerReviews=[];labelReviewOrder=[];cancelScanRequest();stopScan();stopPhoto();closeKeyboard();if(anonymousReturn)api('/session/end',{expected_generation:identityGeneration,expected_instance:identityInstance}).catch(()=>{});document.querySelectorAll('.workshop-dialog,.workflow-dialog').forEach(n=>n.remove());itemActionOffer=itemActionOrigin=pendingItemAction=null;anonymousReturn=false;scanPurpose=null;manufacturerCodeDraft=null;kitDraft=null;checkoutKitVersions={};returnKitVersions={};checkoutMode=false;checkoutCart=[];checkoutKey=null;checkoutReview=false;checkoutPickerOpen=false;checkoutAdding=false;returnMode=false;returnCart=[];returnKey=null;returnDestinationFor=null;returnReview=false;returnPicker=false;enrollment=null;problemMode=false;problemDraft=null;formDirty=false;importDrafts={};importMappingDraft=null;routeStack=[];routeTitle='';routeRevision++;if(workshopDirty){workshopDraft=workshopState?.layout?workshopClone(workshopState.layout):null;workshopDirty=false;workshopUndo=[]}}
const originalHome=home;
home=function(preservedBadgePanel=null){resetTask();originalHome(preservedBadgePanel)};
function beginItemActionSwitch(){const offer=itemActionOffer;if(!offer||offer.generation!==identityGeneration||offer.instance!==identityInstance||offer.sourceMode!==(returnMode?'return':'checkout')||workflowBusy()||checkoutKey||returnKey){workflowMessage('Finish or recover the current operation before switching items.');return}const routeDepth=routeStack.length;routeStack.push(captureRoute());itemActionOffer=null;itemActionOrigin={mode:offer.sourceMode,generation:identityGeneration,instance:identityInstance,routeDepth};routeTransition=true;try{if(offer.mode==='checkout'){returnMode=false;checkoutMode=true;checkoutReview=false;checkoutPickerOpen=false;if(anonymousReturn&&!identified)pendingItemAction={mode:'checkout',entity:offer.entity,generation:identityGeneration,instance:identityInstance};renderCheckout()}else{checkoutMode=false;returnMode=true;returnReview=false;returnPicker=false;renderReturn()}}finally{routeTransition=false}if(offer.mode==='checkout'){if(!(anonymousReturn&&!identified))addCheckout(offer.entity)}else addReturn(offer.entity)}
function backToItemActionOrigin(){if(!itemActionOrigin||itemActionOrigin.generation!==identityGeneration||itemActionOrigin.instance!==identityInstance||workflowBusy()||checkoutKey||returnKey){workflowMessage('Finish or recover the current operation before returning to the original list.');return}pendingItemAction=null;const {mode,routeDepth}=itemActionOrigin;itemActionOrigin=null;itemActionOffer=null;routeStack.length=routeDepth;routeTransition=true;try{checkoutMode=mode==='checkout';returnMode=mode==='return';if(returnMode)renderReturn();else renderCheckout()}finally{routeTransition=false}}
const originalOpen=open;
open=function(title){leaveTask(()=>originalOpen(title))};
for(const id of ['home-nav','storage-nav','layout-nav','admin','report-problem']){const button=document.querySelector('#'+id),handler=button.onclick;button.onclick=()=>{if(id==='layout-nav'&&view.classList.contains('workshop-view')){if(!workflowBusy())handler();return}leaveTask(()=>handler())}}
const originalPrimary=primary;
primary=function(label,fn){const writing=/^(Confirm|Print|Save|Issue|Revoke)/.test(label);let button;button=originalPrimary(label,async()=>{if(writing&&workflowBusy()){workflowMessage('Wait for the current confirmation to finish.');return}const previousWriteButton=window.workflowPrimaryWriteButton;if(writing){writeCount++;window.workflowPrimaryWriteDepth=(window.workflowPrimaryWriteDepth||0)+1;window.workflowPrimaryWriteButton=button}try{return await fn()}catch(e){workflowMessage(e.message)}finally{if(writing){window.workflowPrimaryWriteDepth=Math.max(0,(window.workflowPrimaryWriteDepth||1)-1);window.workflowPrimaryWriteButton=previousWriteButton;writeCount--}}});if(/^(Confirm |Review equipment|Review report|Save review|Save kit|Print one)/.test(label))button.classList.add('workflow-primary');return button};
for(const id of ['scan','manual']){const control=document.querySelector('#'+id),handler=control.onclick;control.onclick=()=>{if(workflowBusy()){workflowMessage('Wait for the current confirmation to finish.');return}return handler()}}
const originalTouchField=touchField;
touchField=function(...args){const input=originalTouchField(...args),update=input.oninput;input.oninput=()=>{formDirty=true;update()};return input};
view.addEventListener('change',event=>{if(!event.target.getAttribute('aria-label')?.endsWith(' filter'))formDirty=true});
window.addEventListener('beforeunload',event=>{if(hasDraft()||writeCount){event.preventDefault();event.returnValue=''}});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!workflowBusy()){if(keyboardOverlay)closeKeyboard();else if(scanOverlay)stopScan();else if(photoOverlay)stopPhoto();else if(document.querySelector('.workflow-dialog,.workshop-dialog'))document.querySelector('.workflow-dialog,.workshop-dialog').remove();else routeBack()}});

function cancelScanRequest(){if(!activeScanRequest)return;const request=activeScanRequest;activeScanRequest=null;request.cancelled=true;fetch('/scan/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scan_token:request.token})}).catch(()=>{});if(request.session)fetch('/session/end',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_generation:request.session.generation,expected_instance:request.session.instance})}).catch(()=>{})}
const originalStopScan=stopScan;
stopScan=function(){cancelScanRequest();return originalStopScan()};
const genericRouteScan=routeScan;let workshopMapScanToken=0,workshopMapScanOpenings=0;
stopScan=function(){if(scanPurpose==='workshop_map'||workshopMapScanOpenings>0)workshopMapScanToken++;cancelScanRequest();return originalStopScan()};
routeScan=async function(code,expectedOverlay=null){if(scanPurpose==='workshop_check_item')return workshopCheckScan(code,expectedOverlay);if(scanPurpose!=='workshop_map')return genericRouteScan(code,expectedOverlay);if(workflowBusy())return 'Wait for the current confirmation to finish before scanning the map.';const token=++workshopMapScanToken,revision=routeRevision,instance=identityInstance,generation=identityGeneration;try{const result=await api('/workshop/resolve',{code});if(token!==workshopMapScanToken||scanPurpose!=='workshop_map'||revision!==routeRevision||instance!==identityInstance||generation!==identityGeneration||(expectedOverlay&&scanOverlay!==expectedOverlay))return false;stopScan();scanPurpose=null;if(result.entity_id){let openedRevision=revision;if(typeof workshopIsMapPage==='function'&&!workshopIsMapPage()){workshopMapScanOpenings++;try{await workshopOpen()}finally{workshopMapScanOpenings--}openedRevision=routeRevision}if(token+1!==workshopMapScanToken||openedRevision!==routeRevision||instance!==identityInstance||generation!==identityGeneration||!workshopIsMapPage())return false;await workshopSelectEntity(result.entity_id)}else workshopShowResolution(result);return true}catch(error){if(token===workshopMapScanToken&&instance===identityInstance&&generation===identityGeneration){stopScan();scanPurpose=null;if(['Workshop','Storage'].includes(routeTitle)&&routeRevision===revision)workshopShowResolution({kind:'unavailable',entity_id:null,candidates:[],message:error.message})}return false}};


// Clear every borrower-owned draft on *any* externally observed session transition.
updateIdentity=async function(){if(workflowBusy()||activeScanRequest)return;try{const previousGeneration=identityGeneration,previousInstance=identityInstance,previousUserId=identityUserId,wasAnonymous=anonymousReturn,data=await api('/api/session'),sessionChanged=data.instance!==identityInstance||data.generation!==identityGeneration,changed=identified&&sessionChanged,anonymousChanged=anonymousReturn&&(!data.return_only||!!data.user||sessionChanged),transfer=pendingItemAction,handoff=wasAnonymous&&!!data.user&&transfer?.mode==='checkout'&&transfer.generation===previousGeneration&&transfer.instance===previousInstance;if(!acceptSession(data))return;if(data.user)clearMemberBadgeForIdentityChange(data.user.id);const endedOwnerPanel=sessionChanged&&!data.user&&previousUserId&&memberBadgeSessionHandoff?.memberId===previousUserId?preserveMemberBadgeSessionEnd(previousUserId):null;if(sessionChanged){labelDesignerHandle?.dispose();labelDesignerHandle=null;labelMakerDirty=labelMakerBusy=false;labelQueue=[];labelMakerReviews=[];labelReviewOrder=[];labelMakerTemplates=[];labelQueueContext='';const maker=view.querySelector('[data-label-maker-root]');maker?.replaceChildren(node('p','The session changed. Return and reopen Label maker to review labels for this session.'))}if(changed){identified=false;home(endedOwnerPanel);status.textContent='Badge session changed. Start a new task.'}else if(endedOwnerPanel&&!endedOwnerPanel.isConnected){view.append(endedOwnerPanel);finishMemberBadgeSessionEnd(endedOwnerPanel)}if(anonymousChanged){anonymousReturn=false;returnCart=[];returnKey=null;returnKitVersions={};kitDraft=null;returnReview=false;returnPicker=false;returnDestinationFor=null}identified=!!data.user;if(handoff&&checkoutMode){checkoutCart=[];checkoutKey=null;checkoutKitVersions={};checkoutReview=false;pendingItemAction=null;itemActionOffer=null;if(itemActionOrigin){itemActionOrigin.generation=identityGeneration;itemActionOrigin.instance=identityInstance}}else if(anonymousChanged){pendingItemAction=itemActionOffer=itemActionOrigin=null}if(anonymousChanged&&returnMode&&!handoff)renderReturn(data.user?'Badge detected. Review the return again under this identity.':'No-badge return ended. Start again and rescan any kit contents.');document.querySelector('#identity').textContent=data.user?data.user.name:anonymousReturn?'Unidentified returner':'Scan badge to identify yourself';document.querySelector('#end-session').style.display=data.user?'block':'none';if(handoff&&checkoutMode){renderCheckout();await addCheckout(transfer.entity)}}catch(e){}};
document.querySelector('#end-session').onclick=()=>{if(workflowBusy()){workflowMessage('Wait for the current confirmation to finish.');return}leaveTask(async()=>{try{await api('/session/end',{expected_generation:identityGeneration,expected_instance:identityInstance});identified=false;home();await updateIdentity()}catch(e){workflowMessage('Could not end the session. Try End again. '+e.message)}})};
if(editorMode){
    const native=document.createElement('button');native.id='homebox-nav';native.textContent='C-Crate';native.title='Open shared inventory and badge management';
    native.onclick=()=>window.open(homeboxURL('/'),'_blank','noopener');
    document.querySelector('header').insertBefore(native,document.querySelector('#desktop'));
    const desktop=document.querySelector('#desktop');desktop.textContent='Disconnect';desktop.onclick=()=>leaveTask(()=>{heading('Disconnect laptop');view.append(node('p','Close this browser tab when finished. If using the Workshop connection window, press Enter there to stop its SSH tunnel.'),primary('Return to editor',home))});document.querySelector('#scan').title='Use manual codes or the laptop camera. The Pi scanner is a separate terminal.';
}
async function resolveTransaction(key){try{return await api('/operation/status',{request_key:key})}catch(e){return {status:'unknown'}}}
function recoveryActions(shell,key,mode){const controls=node('div',undefined,'workflow-recovery');controls.append(primary('Check saved result',async()=>{const revision=routeRevision,generation=identityGeneration,instance=identityInstance,count=mode==='checkout'?checkoutCart.length:returnCart.length;const saved=await resolveTransaction(key);if(revision!==routeRevision||generation!==identityGeneration||instance!==identityInstance)return;if(saved.status==='completed'){await transactionDone(mode,mode==='checkout'?checkoutReceiptAssetCount(saved,checkoutCart):count);return}if(['not_started','cancelled'].includes(saved.status)){if(mode==='checkout'){checkoutKey=null;checkoutReview=false;renderCheckout('No changes were made. Correct the list and review again.')}else{returnKey=null;returnReview=false;renderReturn('No changes were made. Correct the list and review again.')}return}workflowMessage('The result still needs review. Open Admin recovery; do not start another confirmation.')}),primary('Open recovery',()=>{showRecovery();checkoutMode=false;returnMode=false}));shell.append(controls)}
async function transactionDone(mode,count,borrower=''){
    writeCount++;
    try{
        const anonymous=mode==='return'&&anonymousReturn;
        let ended=true;
        try{await api('/session/end',{expected_generation:identityGeneration,expected_instance:identityInstance})}catch(e){ended=false}
        identified=false;anonymousReturn=false;identityGeneration++;
        document.querySelector('#identity').textContent='Scan badge to identify yourself';document.querySelector('#end-session').style.display='none';
        home();
        const shell=checkoutFrame(mode==='checkout'?'Checkout complete':'Return complete',ended?'Your badge session has ended':'Operation confirmed; session end needs checking'),done=node('div',undefined,'checkout-done');
        done.append(node('h2',count+' item'+(count===1?'':'s')+(mode==='checkout'?' checked out':' returned')),node('p',anonymous?'Recorded as an unidentified returner. The original borrower remains in loan history.':borrower?'Recorded for '+borrower:'The operation was confirmed.'),checkoutButton('Done',home,'main'));
        if(!ended)done.append(node('p','Check the End control before handing the terminal to someone else.'));
        shell.append(done);load();
    }finally{writeCount--;updateIdentity()}
}


home();load();updateIdentity();


async function cameraFocusControls(overlay,message,photo=false,autofocus=photo){
const active=()=>photo?photoOverlay===overlay:scanOverlay===overlay;
try{const current=await api('/api/camera');if(!active())return;if(!current.supported){if(photo)message.textContent='Focus controls unavailable. Check the preview before capturing.';return}
const row=node('div',undefined,'toolbar'),slider=node('input');slider.type='range';slider.min=0;slider.max=250;slider.step=5;slider.value=current.value;slider.style='width:180px;height:44px';slider.setAttribute('aria-label','Pi camera focus: far to near');
const change=async(mode,value)=>{if(!active())return;try{await api('/camera/focus',{mode,value});if(!active())return;message.textContent=mode==='auto'?'Autofocus on. Hold '+(photo?'the equipment':'the QR')+' steady.':'Manual focus '+value+' · adjust until the preview looks sharp.'}catch(e){if(active())message.textContent=e.message}};
slider.onchange=()=>change('manual',Number(slider.value));row.append(primary(photo?'Manual focus':'Label focus',()=>change('manual',Number(slider.value))),primary('Autofocus',()=>change('auto')),slider);overlay.append(row);if(autofocus)await change('auto')
}catch(e){if(photo&&active())message.textContent='Focus controls unavailable. Check the preview before capturing.'}}

// Native locations and items share one optional parent edge.
async function loadParents(){return (await Promise.all([api('/api/locations'),api('/api/inventory')])).flat()}
function parentPath(entity,records){const path=[],seen=new Set();let current=entity;while(current&&!seen.has(current.id)){seen.add(current.id);path.unshift(current.name);const id=current.parent_id||current.parent?.id;current=records.find(p=>p.id===id)}return path.join(' / ')}
function parentChoices(records,excluded=[]){const byId=new Map(records.map(p=>[p.id,p])),blocked=new Set(excluded);return records.filter(p=>{if(p.archived)return false;const seen=new Set();let current=p;while(current){if(blocked.has(current.id)||seen.has(current.id))return false;seen.add(current.id);current=byId.get(current.parent_id||current.parent?.id)}return true})}
function addInsideActions(panel,entity){if(entity.archived)return;panel.append(primary('Add location inside',()=>locationForm({name:'',description:'',parent_id:entity.id,map_room:false})),primary('Add equipment inside',()=>{enrollment={key:crypto.randomUUID(),name:'',description:'',serial:'',manufacturer:'',model:'',gtin:'',location_id:entity.id,reviewed:false};renderEnrollment()}))}

// Standalone notes are owner-bound requests, not custody transactions.
let itemNoteMode=false,itemNoteDraft=null,itemNoteBusy=false;
const ITEM_NOTE_PENDING_KEY='c-crate-item-note-pending-v1';
function readItemNotePending(){
    try{
        const saved=JSON.parse(sessionStorage.getItem(ITEM_NOTE_PENDING_KEY)||'null');
        if(!saved||Object.keys(saved).sort().join(',')!=='actor_id,entity_id,generation,instance,request_key'
            ||![saved.actor_id,saved.entity_id,saved.instance,saved.request_key].every(value=>typeof value==='string'&&value)
            ||!Number.isInteger(saved.generation))return null;
        return {actorId:saved.actor_id,entityId:saved.entity_id,generation:saved.generation,instance:saved.instance,key:saved.request_key};
    }catch(_){return null}
}
let itemNotePending=readItemNotePending();
function saveItemNotePending(pending){
    const safe={request_key:pending.key,entity_id:pending.entityId,actor_id:pending.actorId,generation:pending.generation,instance:pending.instance};
    sessionStorage.setItem(ITEM_NOTE_PENDING_KEY,JSON.stringify(safe));
    itemNotePending=pending;
}
function clearItemNotePending(){itemNotePending=null;try{sessionStorage.removeItem(ITEM_NOTE_PENDING_KEY)}catch(_){}}
function itemNoteOwnerCurrent(pending,strict){
    return !!pending&&!!identityUserId&&identityUserId===pending.actorId
        &&(!strict||(identityGeneration===pending.generation&&identityInstance===pending.instance));
}
function itemNoteStatus(message){const line=node('p',message);line.dataset.itemNoteStatus='true';view.append(line);return line}
function itemNoteRecoveryCard(message){
    heading('Check saved item note');
    const card=node('div',undefined,'notice');
    card.append(node('h1','Item note outcome needs checking'),node('p',message||'The request may have reached C-Crate. Check its saved status; do not submit it again.'));
    card.append(primary('Check saved result',()=>checkItemNoteResult(itemNotePending)),primary('Open Admin recovery',()=>{showRecovery();itemNoteMode=false}));
    view.append(card);
}
function itemNoteForeignPendingCard(){
    heading('Item note belongs to another badge');
    view.append(node('h1','Item note belongs to another badge'));
    view.append(node('p','A prior badge holder has an unresolved item note. It cannot be inspected, submitted, or cleaned up under this badge. The original owner can check its saved status after signing in again.'));
    view.append(primary('Open Admin recovery',()=>showRecovery()));
}
function startItemNote(message=''){
    itemNoteMode=true;
    if(!identified||!identityUserId){heading('Add Notes to Item');view.append(node('p','Scan a group-member badge before choosing equipment.'));view.append(primary('Scan badge',()=>document.querySelector('#scan').click()));if(message)itemNoteStatus(message);return}
    if(itemNotePending){
        if(itemNotePending.actorId!==identityUserId){itemNoteDraft=null;itemNoteForeignPendingCard();return}
        else {itemNoteRecoveryCard('A previous confirmation may have been saved. This screen checks status only and will not send another note.');return}
    }
    itemNoteDraft=null;heading('Add Notes to Item');view.append(node('p','Choose active individually tracked equipment. Checked-out and checkout-blocked items may still receive a note.'));
    view.append(primary('Scan equipment',()=>document.querySelector('#scan').click()));
    const choices=node('div',undefined,'items');
    for(const entity of inventory.filter(row=>!row.archived&&row.quantity===1&&!row.entityType?.isLocation)){
        const button=node('button',undefined,'item');button.append(node('strong',entity.name),node('small',(entity.assetId||'')+' · '+(entity.condition||'Condition not available')+' · '+(entity.parent?.name||'No assigned shelf')));
        button.onclick=()=>chooseItemNoteEntity(entity);choices.append(button);
    }
    if(!choices.childNodes.length)view.append(node('p','No active individually tracked equipment is available.'));
    view.append(choices);if(message)itemNoteStatus(message);
}
async function chooseItemNoteEntity(candidate){
    const generation=identityGeneration,instance=identityInstance,revision=routeRevision;
    if(!identified||!identityUserId||itemNotePending)return;
    try{
        const response=await fetch('/api/entity?id='+encodeURIComponent(candidate.id)),data=await response.json();
        if(!response.ok)throw Error(data.error||'Could not verify equipment');
        if(generation!==identityGeneration||instance!==identityInstance||revision!==routeRevision||!identified)return;
        const entity=data.entity;
        if(!entity||entity.id!==candidate.id||entity.archived||entity.quantity!==1||entity.entityType?.isLocation){startItemNote('Choose active, individually tracked equipment.');return}
        itemNoteForm(entity);
    }catch(error){if(generation===identityGeneration&&instance===identityInstance&&revision===routeRevision)startItemNote(error.message)}
}
function itemNoteForm(entity,draft={note:'',entity,actorId:identityUserId,generation:identityGeneration,instance:identityInstance}){
    itemNoteMode=true;itemNoteDraft=draft;heading('Add Notes to Item');
    const card=node('div',undefined,'notice');card.dataset.itemNoteForm='true';
    card.append(node('h1',entity.name),node('p','Write an independent note. This will not change checkout, condition, photos, kits, or labels.'));
    const field=node('label','Note (up to 1,000 characters)');const textarea=node('textarea');textarea.value=draft.note;textarea.maxLength=4000;textarea.setAttribute('aria-label','Item note');textarea.rows=5;textarea.style='width:100%;font:inherit';
    textarea.oninput=()=>{draft.note=textarea.value;formDirty=true;count.textContent=Array.from(draft.note).length+' / 1000 characters'};
    const count=node('small',Array.from(draft.note).length+' / 1000 characters');field.append(textarea,count);card.append(field);
    const review=primary('Review note',()=>reviewItemNote(entity,draft));review.disabled=!draft.note.trim();
    textarea.addEventListener('input',()=>{review.disabled=!draft.note.trim()||Array.from(draft.note).length>1000});
    card.append(review,primary('Back',()=>routeBack()));view.append(card);textarea.focus();
}
function reviewItemNote(entity,draft){
    if(!itemNoteOwnerCurrent({actorId:draft.actorId,generation:draft.generation,instance:draft.instance},true))return startItemNote('Badge session changed. Scan your badge again.');
    const key=crypto.randomUUID(),note=draft.note;
    if(!note.trim()||Array.from(note).length>1000||new TextEncoder().encode(note+'\n\n[Kiosk note '+key+']').length>2500){itemNoteForm(entity,draft);itemNoteStatus('The note must be nonempty, at most 1,000 characters, and fit the native 2,500-byte record limit.');return}
    heading('Review item note');const card=node('div',undefined,'notice');card.dataset.itemNoteReview='true';
    card.append(node('h1','Confirm item note'),node('p','Equipment: '+entity.name+' · '+(entity.assetId||entity.id)),node('p','Person: '+document.querySelector('#identity').textContent),node('p','The note will be saved as a separate native maintenance entry.'),node('p',note));
    const pending={key,entityId:entity.id,actorId:draft.actorId,generation:draft.generation,instance:draft.instance};
    const confirm=primary('Confirm note',()=>confirmItemNote(pending,note));confirm.dataset.confirmItemNote='true';
    card.append(confirm,primary('Back',()=>{
        if(itemNoteBusy)return;
        if(itemNotePending&&(!identified||!identityUserId)){itemNoteMode=true;startItemNote('Scan the original badge to inspect the saved note status.');return}
        if(itemNotePending){if(itemNotePending.actorId===identityUserId)itemNoteRecoveryCard('A note request is already pending. Check saved status before editing or submitting again.');else itemNoteForeignPendingCard();return}
        itemNoteForm(entity,draft);
    }));view.append(card);formDirty=true;
}
async function confirmItemNote(pending,note){
    if(itemNoteBusy||itemNotePending||!itemNoteOwnerCurrent(pending,true))return;
    if(!note.trim()||Array.from(note).length>1000||new TextEncoder().encode(note+'\n\n[Kiosk note '+pending.key+']').length>2500){itemNoteStatus('The note exceeds the supported limit. Edit it before confirming.');return}
    try{saveItemNotePending(pending)}catch(_){itemNoteStatus('This browser cannot safely retain the request key. No note was sent.');return}
    itemNoteBusy=true;const revision=routeRevision,generation=identityGeneration,instance=identityInstance;
    const confirm=view.querySelector('[data-confirm-item-note]');if(confirm)confirm.disabled=true;
    try{
        const result=await api('/notes/confirm',{request_key:pending.key,input:{entity_id:pending.entityId,note},session_generation:generation,session_instance:instance});
        if(revision!==routeRevision||generation!==identityGeneration||instance!==identityInstance||!itemNoteOwnerCurrent(pending,true))return;
        if(result.status==='completed'&&result.note_saved){await finishItemNoteSaved(pending,!!result.session_ended);return}
        itemNoteRecoveryCard('C-Crate did not confirm the note result. Check saved status; do not submit it again.');
    }catch(_){
        if(revision!==routeRevision||generation!==identityGeneration||instance!==identityInstance||!itemNoteOwnerCurrent(pending,true))return;
        await checkItemNoteResult(pending);
    }finally{itemNoteBusy=false;if(confirm?.isConnected&&itemNotePending===null)confirm.disabled=false}
}
async function checkItemNoteResult(pending){
    if(!pending||!itemNoteOwnerCurrent(pending,false)){workflowMessage('This pending note belongs to another badge holder. Use Admin recovery; it cannot be checked or submitted under this identity.');return}
    const revision=routeRevision,actor=identityUserId,generation=identityGeneration,instance=identityInstance;
    try{
        const result=await api('/operation/status',{request_key:pending.key});
        if(revision!==routeRevision||actor!==identityUserId||generation!==identityGeneration||instance!==identityInstance||!itemNoteOwnerCurrent(pending,false))return;
        if(result.status==='completed'){await finishItemNoteSaved(pending,false);return}
        if(['not_started','cancelled'].includes(result.status)){
            clearItemNotePending();itemNoteMode=false;itemNoteDraft=null;
            heading('Item note not saved');view.append(node('p','No item note was created. Review a new note before confirming; no request was retried.'));
            view.append(primary('Add another note',()=>startItemNote()));return;
        }
        itemNoteRecoveryCard('The saved item note still needs inspection. Do not submit another copy.');
    }catch(_){if(revision===routeRevision&&actor===identityUserId)itemNoteRecoveryCard('Saved status is unavailable. Keep this request and use Admin recovery; do not submit it again.')}
}
async function finishItemNoteSaved(pending,serverEnded){
    if(!itemNoteOwnerCurrent(pending,false))return;
    const sameSession=pending.generation===identityGeneration&&pending.instance===identityInstance;
    let ended=serverEnded;
    if(sameSession&&!ended){try{await api('/session/end',{expected_generation:pending.generation,expected_instance:pending.instance});ended=true}catch(_){ended=false}}
    clearItemNotePending();itemNoteDraft=null;itemNoteMode=false;formDirty=false;
    if(sameSession&&ended){identityGeneration=pending.generation+1;identified=false;identityUserId=null;document.querySelector('#identity').textContent='Scan badge to identify yourself';document.querySelector('#end-session').style.display='none'}
    heading('Item note saved');view.append(node('h1','Note saved'));
    view.append(node('p',sameSession&&!ended?'Note saved. Badge session cleanup needs checking.':'The independent item note was confirmed in C-Crate.'));
    view.append(primary('Done',()=>home()));status.textContent=sameSession&&!ended?'Note saved · session cleanup needs checking':'Note saved in C-Crate';
}

const originalWorkflowBusyForNotes=workflowBusy;
workflowBusy=function(){return originalWorkflowBusyForNotes()||itemNoteBusy};
const originalHasDraftForNotes=hasDraft;
hasDraft=function(){return originalHasDraftForNotes()||!!itemNoteDraft?.note||!!itemNotePending};
const originalResetTaskForNotes=resetTask;
resetTask=function(){itemNoteMode=false;itemNoteDraft=null;return originalResetTaskForNotes()};
const originalRouteBackForNotes=routeBack;
routeBack=function(discard=false){
    if(itemNoteBusy)return;
    if(itemNotePending&&(!identified||!identityUserId)){itemNoteMode=true;startItemNote('Scan the original badge to inspect the saved note status.');return}
    if(itemNotePending&&itemNotePending.actorId!==identityUserId){itemNoteForeignPendingCard();return}
    if(itemNotePending){itemNoteRecoveryCard('A note request has an uncertain result. Check its saved status before leaving.');return}
    if(itemNoteDraft?.note&&!discard&&routeStack.length&&!routeStack.at(-1).dirty){
        const overlay=node('div',undefined,'workflow-dialog'),panel=node('div',undefined,'notice');
        panel.append(node('h1','Discard this note?'),primary('Keep editing',()=>overlay.remove()),primary('Discard note & go back',()=>{overlay.remove();itemNoteDraft=null;itemNoteMode=false;originalRouteBackForNotes(true)}));overlay.append(panel);document.body.append(overlay);return;
    }
    if(discard){itemNoteDraft=null;itemNoteMode=false}return originalRouteBackForNotes(discard);
};
const originalLeaveTaskForNotes=leaveTask;
leaveTask=function(action){if(itemNoteBusy)return;if(itemNotePending&&(!identified||!identityUserId)){itemNoteMode=true;startItemNote('Scan the original badge to inspect the saved note status.');return}if(itemNotePending&&itemNotePending.actorId!==identityUserId){itemNoteForeignPendingCard();return}if(itemNotePending){itemNoteRecoveryCard('A note request has an uncertain result. Check its saved status before starting another task.');return}return originalLeaveTaskForNotes(action)};
const originalOpenForItemNotes=open;
open=function(title){if(title==='Add Notes to Item'){leaveTask(()=>startItemNote());return}return originalOpenForItemNotes(title)};
const originalUpdateIdentityForNotes=updateIdentity;
updateIdentity=async function(){
    const priorActor=identityUserId,priorGeneration=identityGeneration,priorInstance=identityInstance;
    await originalUpdateIdentityForNotes();
    if(itemNoteDraft&&(identityUserId!==itemNoteDraft.actorId||identityGeneration!==itemNoteDraft.generation||identityInstance!==itemNoteDraft.instance)){
        itemNoteDraft=null;itemNoteMode=false;formDirty=false;status.textContent='Badge session changed. The unsent note draft was cleared.';
    }
    if(itemNotePending&&identityUserId&&identityUserId!==itemNotePending.actorId){itemNoteDraft=null;itemNoteMode=false;status.textContent='A prior badge holder has an item note in Recovery. It was not transferred.'}
    if(priorActor&&priorActor!==identityUserId&&priorGeneration===identityGeneration&&priorInstance===identityInstance){itemNoteDraft=null;itemNoteMode=false}
};
const originalWindowBeforeUnloadForNotes=hasDraft;

async function showContents(panel,entity){try{const parents=await loadParents();if(!panel.isConnected)return;const list=node('div',undefined,'items');const current=parents.find(p=>p.id===entity.id);if(current)panel.append(node('p',parentPath(current,parents)));list.append(node('h2','Inside '+entity.name));for(const child of parents.filter(p=>!p.archived&&p.parent?.id===entity.id)){const button=node('button',child.name,'item');button.onclick=()=>detail(child);list.append(button)}if(list.childNodes.length>1)panel.append(list)}catch(error){if(panel.isConnected)panel.append(node('p',error.message))}}


// Preserve Workshop planner requests through task changes and offer saved-result inspection.
const canonicalWorkshopResetTask=resetTask;
resetTask=function(){if(typeof workshopTask5Persist==='function')workshopTask5Persist();return canonicalWorkshopResetTask()};
const canonicalWorkshopLeaveTask=leaveTask;
leaveTask=function(action){if(typeof workshopTask5HasPending==='function'&&workshopTask5HasPending()){if(workflowBusy()){workflowMessage('Wait for the current confirmation to finish.');return}const overlay=node('div',undefined,'workflow-dialog'),panel=node('div',undefined,'notice');panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Workshop save recovery');panel.append(node('h1','Check the saved room plan'),node('p','Its result is uncertain. Keep the request and inspect its original collection and service actor. It will not be sent again automatically.'),primary('Keep this task',()=>overlay.remove()),primary('Leave and keep request',()=>{overlay.remove();workshopTask5Persist?.();canonicalWorkshopResetTask();action()}));if(routeTitle==='Workshop')panel.append(primary('Check saved result',async()=>{overlay.remove();await workshopCheckSave?.(workshopTask5PendingKeyValue?.())}));overlay.append(panel);document.body.append(overlay);return}return canonicalWorkshopLeaveTask(action)};
