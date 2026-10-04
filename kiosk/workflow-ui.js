// Common client ownership, navigation and request lifecycle for the companion.
const editorMode=new URLSearchParams(location.search).get('mode')==='editor';
const clientId=crypto.randomUUID(); // A fresh page, including a duplicated tab, owns a fresh session.
let routeRevision=0,routeTitle='',routeStack=[],restoringRoute=false,formDirty=false,writeCount=0,activeScanRequest=null;
const nativeFetch=window.fetch.bind(window);
const readPosts=new Set(['/workshop/get','/imports/get','/imports/list','/label/preview','/operation/status','/decode']);
const passivePosts=new Set(['/scan','/scan/cancel','/session/end','/session/activity','/camera/focus']);
window.fetch=async function(resource,options={}){
    const url=new URL(typeof resource==='string'?resource:resource.url,location.href),path=url.pathname;
    if(url.origin!==location.origin)return nativeFetch(resource,options);
    const method=(options.method||'GET').toUpperCase(),headers=new Headers(options.headers||{});
    headers.set('X-Homebox-Client',clientId);headers.set('X-Homebox-Client-Mode',editorMode?'editor':'kiosk');
    const writing=method!=='GET'&&!readPosts.has(path)&&!passivePosts.has(path);
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
    if(writing)writeCount++;
    try{const response=await nativeFetch(resource,{...options,headers,signal:options.signal||controller.signal});const body=await response.arrayBuffer();return new Response(body,{status:response.status,statusText:response.statusText,headers:response.headers})}
    catch(error){if(writing)status.textContent='No confirmation received. Check Admin recovery before trying another create or print.';throw Error(error.name==='AbortError'?'The request timed out. Check the saved result before retrying.':error.message)}
    finally{clearTimeout(timer);if(writing)writeCount--}
};
api=async function(path,data){const r=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});let value;try{value=await r.json()}catch(e){throw Error('The service did not return a readable result. Check recovery before retrying a write.')}if(!r.ok){const error=Error(value.error||value.reason||'Request failed');error.status=r.status;throw error}return value};
function workflowBusy(){return writeCount>0||checkoutBusy||returnBusy}
function workflowMessage(message){view.querySelector('.workflow-message')?.remove();const panel=node('div',message,'workflow-message');panel.setAttribute('role','alert');(view.querySelector('.checkout-shell')||view).append(panel);return panel}
function captureRoute(){return {nodes:Array.from(view.childNodes),className:view.className,title:routeTitle,scroll:view.scrollTop,dirty:formDirty,identity:identityGeneration,instance:identityInstance,nav:document.querySelector('#layout-nav').textContent,modes:{checkoutMode,returnMode,problemMode,scanPurpose,returnDestinationFor}}}
function routeBack(discard=false){if(workflowBusy()){workflowMessage('Wait for the current confirmation to finish.');return}if(formDirty&&!discard&&routeStack.length&&!routeStack.at(-1).dirty){const overlay=node('div',undefined,'workflow-dialog'),panel=node('div',undefined,'notice');panel.append(node('h1','Discard these edits?'),primary('Keep editing',()=>overlay.remove()),primary('Discard & go back',()=>{overlay.remove();routeBack(true)}));overlay.append(panel);document.body.append(overlay);return}cancelScanRequest();stopScan();stopPhoto();closeKeyboard();const previous=routeStack.pop();if(!previous){home();return}if(previous.identity!==identityGeneration||previous.instance!==identityInstance){home();return}restoringRoute=true;view.replaceChildren(...previous.nodes);view.className=previous.className;routeTitle=previous.title;checkoutMode=previous.modes.checkoutMode;returnMode=previous.modes.returnMode;problemMode=previous.modes.problemMode;scanPurpose=previous.modes.scanPurpose;returnDestinationFor=previous.modes.returnDestinationFor;formDirty=previous.dirty;document.querySelector('#layout-nav').textContent=previous.nav;view.scrollTop=previous.scroll;routeRevision++;restoringRoute=false;ensureNavigation()}
const originalHeading=heading;
heading=function(title){if(!restoringRoute&&view.childNodes.length&&title!==routeTitle){routeStack.push(captureRoute());if(routeStack.length>30)routeStack.shift()}if(title!==routeTitle)routeRevision++;routeTitle=title;originalHeading(title);ensureNavigation()};
function ensureNavigation(){if(view.classList.contains('dashboard'))return;const row=view.querySelector('.toolbar');if(row&&Array.from(row.querySelectorAll('button:not([data-local-back])')).some(b=>b.textContent==='Back'))row.querySelector('[data-local-back]')?.remove();if(row&&!row.querySelector('[data-local-back]')&&!Array.from(row.querySelectorAll('button')).some(b=>b.textContent==='Back')){const back=node('button','Back','workflow-back');back.dataset.localBack='true';back.onclick=()=>routeBack();row.prepend(back)}for(const a of view.querySelectorAll('a[href^="http://127.0.0.1:17745"]')){a.hidden=!editorMode;a.title='Open the native record in a separate tab; close that tab to return.'}}
new MutationObserver(ensureNavigation).observe(view,{childList:true,subtree:true});
function hasDraft(){return formDirty||workshopDirty||checkoutCart.length>0||returnCart.length>0||!!problemDraft?.note||!!enrollment?.name}
function leaveTask(action){if(workflowBusy()){workflowMessage('Wait for the current confirmation to finish.');return}if(checkoutKey||returnKey){const overlay=node('div',undefined,'workflow-dialog'),panel=node('div',undefined,'notice');panel.append(node('h1','Check this operation first'),node('p','Its outcome is still uncertain. Keep the request until its saved result or recovery is resolved.'),primary('Keep task',()=>overlay.remove()),primary('Open recovery',()=>{overlay.remove();showRecovery();checkoutMode=false;returnMode=false}));overlay.append(panel);document.body.append(overlay);return}if(hasDraft()){const overlay=node('div',undefined,'workflow-dialog'),panel=node('div',undefined,'notice');panel.append(node('h1','Leave this task?'),node('p','Your unsaved edits or selected items will be discarded.'),primary('Keep editing',()=>overlay.remove()),primary('Discard & leave',()=>{overlay.remove();resetTask();action()}));overlay.append(panel);document.body.append(overlay);return}resetTask();action()}
function resetTask(){cancelScanRequest();stopScan();stopPhoto();closeKeyboard();document.querySelectorAll('.workshop-dialog,.workflow-dialog').forEach(n=>n.remove());scanPurpose=null;kitDraft=null;checkoutKitVersions={};returnKitVersions={};checkoutMode=false;checkoutCart=[];checkoutKey=null;checkoutReview=false;checkoutPickerOpen=false;checkoutAdding=false;returnMode=false;returnCart=[];returnKey=null;returnDestinationFor=null;returnReview=false;returnPicker=false;enrollment=null;problemMode=false;problemDraft=null;formDirty=false;importDrafts={};importMappingDraft=null;routeStack=[];routeTitle='';routeRevision++;if(workshopDirty){workshopDraft=workshopState?.layout?workshopClone(workshopState.layout):null;workshopDirty=false;workshopUndo=[]}}
const originalHome=home;
home=function(){resetTask();originalHome()};
const originalOpen=open;
open=function(title){leaveTask(()=>originalOpen(title))};
for(const id of ['home-nav','storage-nav','layout-nav','admin','report-problem']){const button=document.querySelector('#'+id),handler=button.onclick;button.onclick=()=>{if(id==='layout-nav'&&view.classList.contains('workshop-view')){if(!workflowBusy())handler();return}leaveTask(()=>handler())}}
const originalPrimary=primary;
primary=function(label,fn){const writing=/^(Confirm|Print|Save|Issue|Revoke)/.test(label);const button=originalPrimary(label,async()=>{if(writing&&workflowBusy()){workflowMessage('Wait for the current confirmation to finish.');return}if(writing)writeCount++;try{return await fn()}catch(e){workflowMessage(e.message)}finally{if(writing)writeCount--}});if(/^(Confirm |Review equipment|Review report|Save review|Save kit|Print one)/.test(label))button.classList.add('workflow-primary');return button};
for(const id of ['scan','manual']){const control=document.querySelector('#'+id),handler=control.onclick;control.onclick=()=>{if(workflowBusy()){workflowMessage('Wait for the current confirmation to finish.');return}return handler()}}
const originalTouchField=touchField;
touchField=function(...args){const input=originalTouchField(...args),update=input.oninput;input.oninput=()=>{formDirty=true;update()};return input};
view.addEventListener('change',event=>{if(!event.target.getAttribute('aria-label')?.endsWith(' filter'))formDirty=true});
window.addEventListener('beforeunload',event=>{if(hasDraft()||writeCount){event.preventDefault();event.returnValue=''}});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!workflowBusy()){if(keyboardOverlay)closeKeyboard();else if(scanOverlay)stopScan();else if(photoOverlay)stopPhoto();else if(document.querySelector('.workflow-dialog,.workshop-dialog'))document.querySelector('.workflow-dialog,.workshop-dialog').remove();else routeBack()}});

function cancelScanRequest(){if(!activeScanRequest)return;const request=activeScanRequest;activeScanRequest=null;request.cancelled=true;fetch('/scan/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scan_token:request.token})}).catch(()=>{});if(request.session)fetch('/session/end',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_generation:request.session.generation,expected_instance:request.session.instance})}).catch(()=>{})}
const originalStopScan=stopScan;
stopScan=function(){cancelScanRequest();return originalStopScan()};

// Clear every borrower-owned draft on *any* externally observed session transition.
updateIdentity=async function(){if(workflowBusy()||activeScanRequest)return;try{const data=await api('/api/session'),changed=identified&&(data.instance!==identityInstance||data.generation!==identityGeneration);if(!acceptSession(data))return;if(changed){identified=false;home();status.textContent='Badge session changed. Start a new task.'}identified=!!data.user;document.querySelector('#identity').textContent=data.user?data.user.name:'Scan badge to identify yourself';document.querySelector('#end-session').style.display=data.user?'block':'none'}catch(e){}};
document.querySelector('#end-session').onclick=()=>{if(workflowBusy()){workflowMessage('Wait for the current confirmation to finish.');return}leaveTask(async()=>{try{await api('/session/end',{expected_generation:identityGeneration,expected_instance:identityInstance});identified=false;home();await updateIdentity()}catch(e){workflowMessage('Could not end the session. Try End again. '+e.message)}})};
if(editorMode){const desktop=document.querySelector('#desktop');desktop.textContent='Disconnect';desktop.onclick=()=>leaveTask(()=>{heading('Disconnect laptop');view.append(node('p','Close this browser tab, then press Enter in the Workshop connection window to stop the SSH tunnel.'),primary('Return to editor',home))});document.querySelector('#scan').title='Use manual codes or the laptop camera. The Pi scanner is a separate terminal.'}
async function resolveTransaction(key){try{return await api('/operation/status',{request_key:key})}catch(e){return {status:'unknown'}}}
function recoveryActions(shell,key,mode){const controls=node('div',undefined,'workflow-recovery');controls.append(primary('Check saved result',async()=>{const revision=routeRevision,generation=identityGeneration,instance=identityInstance,count=mode==='checkout'?checkoutCart.length:returnCart.length;const saved=await resolveTransaction(key);if(revision!==routeRevision||generation!==identityGeneration||instance!==identityInstance)return;if(saved.status==='completed'){await transactionDone(mode,count);return}if(['not_started','cancelled'].includes(saved.status)){if(mode==='checkout'){checkoutKey=null;checkoutReview=false;renderCheckout('No changes were made. Correct the list and review again.')}else{returnKey=null;returnReview=false;renderReturn('No changes were made. Correct the list and review again.')}return}workflowMessage('The result still needs review. Open Admin recovery; do not start another confirmation.')}),primary('Open recovery',()=>{showRecovery();checkoutMode=false;returnMode=false}));shell.append(controls)}
async function transactionDone(mode,count,borrower=''){
    writeCount++;
    try{
        let ended=true;
        try{await api('/session/end',{expected_generation:identityGeneration,expected_instance:identityInstance})}catch(e){ended=false}
        identified=false;identityGeneration++;
        document.querySelector('#identity').textContent='Scan badge to identify yourself';document.querySelector('#end-session').style.display='none';
        home();
        const shell=checkoutFrame(mode==='checkout'?'Checkout complete':'Return complete',ended?'Your badge session has ended':'Operation confirmed; session end needs checking'),done=node('div',undefined,'checkout-done');
        done.append(node('h2',count+' item'+(count===1?'':'s')+(mode==='checkout'?' checked out':' returned')),node('p',borrower?'Recorded for '+borrower:'The operation was confirmed.'),checkoutButton('Done',home,'main'));
        if(!ended)done.append(node('p','Check the End control before handing the terminal to someone else.'));
        shell.append(done);load();
    }finally{writeCount--;updateIdentity()}
}


home();load();updateIdentity();


async function cameraFocusControls(overlay,message){try{const current=await api('/api/camera');if(scanOverlay!==overlay||!current.supported)return;const row=node('div',undefined,'toolbar'),slider=node('input');slider.type='range';slider.min=0;slider.max=250;slider.step=5;slider.value=current.value;slider.style='width:180px;height:44px';slider.setAttribute('aria-label','Pi camera focus: far to near');const change=async(mode,value)=>{try{await api('/camera/focus',{mode,value});if(scanOverlay!==overlay)return;message.textContent=mode==='auto'?'Autofocus on. Hold the QR steady.':'Manual focus '+value+' · adjust until the QR squares look sharp.'}catch(e){if(scanOverlay===overlay)message.textContent=e.message}};slider.onchange=()=>change('manual',Number(slider.value));row.append(primary('Label focus',()=>change('manual',Number(slider.value))),primary('Autofocus',()=>change('auto')),slider);overlay.append(row)}catch(e){/* Manual code entry remains available when hardware state is unreadable. */}}
