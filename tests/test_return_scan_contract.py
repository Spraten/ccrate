import json
import ast
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
import pathlib
import shutil
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]


def section(source,start,end):
    return source[source.index(start):source.index(end,source.index(start))]


class ReturnScanBehaviorTests(unittest.TestCase):
    def test_actual_handler_session_get_reports_anonymous_context(self):
        from sessions import Session
        server=(ROOT/'deploy/kiosk-server.py').read_text()
        tree=ast.parse(server)
        handler=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Handler')
        import shelf_checks
        namespace={'BaseHTTPRequestHandler':BaseHTTPRequestHandler,'property':property,'urlsplit':urlsplit,'parse_qs':parse_qs,
                   'desktop_handle':lambda *args:False,'ROOT':ROOT,'lock':object(),
                   'ledger':object(),'badges':object(),'native_jobs':object(),
                   'imports':object(),'workshop':object(),'sessions':None,
                   'shelf_checks':shelf_checks,'label_layouts':object(),'LABEL_ASSET_ROOT':ROOT}
        exec(compile(ast.Module(body=[handler],type_ignores=[]),str(ROOT/'deploy/kiosk-server.py'),'exec'),namespace)
        session=Session();generation=session.begin_anonymous_return()
        class Manager:
            def get(self,client):return session
        namespace['sessions']=Manager()
        instance=namespace['Handler'].__new__(namespace['Handler'])
        instance.path='/api/session';instance.headers={}
        result=[];instance.reply_json=lambda code,data:result.append((code,data))
        instance.do_GET()
        self.assertEqual(result[0][0],200)
        self.assertEqual(result[0][1],{'user':None,'generation':generation,'instance':session.instance,'return_only':True})

    def test_return_context_and_focus_callbacks_in_fake_browser(self):
        chromium=shutil.which('chromium')
        if not chromium:self.skipTest('Chromium is unavailable for the UI behavior fixture')
        page=(ROOT/'kiosk/index.html').read_text()
        workflow=(ROOT/'kiosk/workflow-ui.js').read_text()
        returns=(ROOT/'kiosk/return-ui.js').read_text()
        checkout=(ROOT/'kiosk/checkout-ui.js').read_text()
        return_actions=section(returns,'function returnActionControls(shell){','\nasync function startAnonymousReturn')
        checkout_notice=section(checkout,'function checkoutNotice(shell,message){','\nfunction checkoutRows')
        checkout_picker=section(checkout,'async function checkoutPicker(message=\'\'){','\nconst checkoutOriginalAdd=addCheckout;')
        checkout_add_wrapper=section(checkout,'addCheckout=async function(e){','\n};\nconfirmCheckout=async function(){')
        return_add_wrapper=section(returns,'addReturn=async function(entity){','\nconfirmReturn=async function(){')
        scanner=section(page,"document.querySelector('#scan').onclick=async()=>",'window.addEventListener(\'pagehide\',stopScan)')
        api_wrapper=section(workflow,'api=async function(path,data,extraHeaders={}){','\nfunction workflowBusy()')
        identity_poll=section(workflow,'updateIdentity=async function(){','\ndocument.querySelector(\'#end-session\').onclick=')
        heading_wrapper=section(workflow,'const originalHeading=heading;','\nfunction ensureNavigation')
        switch_action=section(workflow,'function beginItemActionSwitch(){','\nfunction backToItemActionOrigin')
        back_action=section(workflow,'function backToItemActionOrigin(){','\nconst originalOpen=open;')
        capture_route=section(workflow,'function captureRoute(){','function routeBack')
        route_back=section(workflow,'function routeBack(discard=false){','const originalHeading=heading;')
        clear_offer=section(workflow,'function clearItemActionOffer(){','\nfunction leaveTask')
        self.assertLess(scanner.index('await cameraFocusControls(overlay,message,false,true)'),scanner.index('async function capture()'))
        focus=section(workflow,'async function cameraFocusControls','// Native locations and items')
        add=section(page,'async function addReturn(e){','async function routeReturnEntity')
        add_checkout=section(page,'async function addCheckout(e){','\nasync function confirmCheckout')
        route_scan=section(page,'async function routeScan(code,expectedOverlay=null){',"document.querySelector('#scan').onclick=async()=>")
        start=section(returns,'async function startAnonymousReturn(){','renderReturn=function')
        ready=section(returns,'function returnReady(){','async function startAnonymousReturn')
        confirm=section(returns,'confirmReturn=async function(){','\n};\nconst returnStyle')
        checkout_start=checkout.index("renderCheckout=function(message=''){")
        checkout_end=checkout.index('    if(checkoutPickerOpen)',checkout_start)
        checkout_gate=checkout[checkout_start:checkout_end]+'};'

        script='''
const node=(tag,text='',cls='')=>({tag,textContent:text||'',className:cls,children:[],attrs:{},style:{},disabled:false,isConnected:true,removed:false,classList:{add(){}},append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},remove(){this.removed=true},setAttribute(k,v){this.attrs[k]=v}});
const primary=(label,fn)=>Object.assign(node('button',label),{onclick:fn});
let scanOverlay=null,photoOverlay=null,identified=false,anonymousReturn=false,returnMode=false,returnBusy=false,returnCart=[],returnAvailable=[],returnKitVersions={},kitDraft=null,returnKey=null,returnAdding=false,returnReview=false,returnPicker=false,returnDestinationFor=null,checkoutMode=false,checkoutReview=false,checkoutPickerOpen=false,checkoutFeedback='',checkoutCart=[],checkoutBusy=false,checkoutAdding=false,checkoutKey=null,identityGeneration=3,identityInstance='old',routeRevision=1,routeTitle='',routeStack=[],restoringRoute=false,routeTransition=false,formDirty=false,problemMode=false,scanPurpose=null,itemNoteMode=false,manufacturerCodeDraft=null,enrollment=null,lastTouch=0,itemActionOffer=null,itemActionOrigin=null,pendingItemAction=null,labelQueue=[],labelMakerReviews=[],labelReviewOrder=[],labelMakerTemplates=[],labelQueueContext='old',labelMakerDirty=false,labelMakerBusy=false,labelDisposed=0,labelDesignerHandle={dispose(){labelDisposed++}};
const identity=node('span'),endSession=node('button');
const outputElement=window.document.querySelector('#result');
const nav=node('button');const document={body:{children:[outputElement],append(){}},querySelector(selector){return selector==='#identity'?identity:selector==='#end-session'?endSession:selector==='#layout-nav'?nav:null},querySelectorAll(){return []}};
const labelMakerPanel=node('section'),view={childNodes:[],children:[],className:'',scrollTop:0,querySelector(selector){return selector==='[data-label-maker-root]'?labelMakerPanel:null},querySelectorAll(){return []},replaceChildren(...items){this.childNodes=items;this.children=items}};
let api,fetch,renderedMessage='',identityAtRender=null,returnFeedback='',lastShell=null,renderReturn=message=>{renderedMessage=returnFeedback=message||'';identityAtRender=identified;if(returnMode&&routeTitle==='Add returns')view.replaceChildren(node('p','Original guest return'))},transactionDone=async(...args)=>{doneArgs=args},resolveTransaction=async()=>({status:'unknown'}),doneArgs=null,requestBody=null,frames=[];
let maybeKit=async()=>false;
let workflowBusy=()=>false,activeScanRequest=null,cancelScanRequest=()=>{},stopScan=()=>{},stopPhoto=()=>{},closeKeyboard=()=>{},ensureNavigation=()=>{},checkoutFrame=(title,step)=>{frames.push(title);heading(title);const shell=node('section');lastShell=shell;return shell},checkoutButton=(label,fn)=>primary(label,fn),touchField=(parent,label,draft,key)=>{const field=node('input');field.value=draft[key]||'';parent.append(field);return field},workflowMessage=()=>{},manualCodeEntry=()=>{},checkoutRows=()=>{},leaveTask=()=>{},home=()=>{},status=node('span'),detail=()=>{},routeReturnEntity=()=>{},startReturn=()=>{},renderKit=()=>{},problemForm=()=>{},renderEnrollment=()=>{},startProblem=()=>{},lookupEnrollment=()=>{},acceptSession=data=>(identityGeneration=data.generation,identityInstance=data.instance,true),heading=title=>{routeTitle=title};
function assert(value,message){if(!value)throw Error(message)}
'''
        script+='\n'+api_wrapper+'\n'+capture_route+'\n'+route_back+'\n'+heading_wrapper+'\n'+clear_offer+'\n'+identity_poll+'\n'+focus+'\n'+ready+'\n'+start+'\n'+add+'\n'+add_checkout+'\nconst originalReturnAdd=addReturn;\n'+return_add_wrapper+'\nconst checkoutOriginalAdd=addCheckout;\n'+checkout_add_wrapper+'\n};\n'+return_actions+'\n'+checkout_notice+'\n'+checkout_picker+'\n'+switch_action+'\n'+back_action+'\n'+confirm+'\n};\n'+checkout_gate+'\n'+route_scan+'\n'
        script+='''
(async()=>{try{
  // The no-badge path starts a scoped return context, adds a real fixture item, and confirms it.
  identified=false;anonymousReturn=false;returnMode=true;identityGeneration=3;identityInstance='old';
  let startRequest;
  fetch=async(path,options)=>{startRequest={path,options};return {ok:true,json:async()=>({generation:4,instance:'terminal-1',return_only:true})}};
  await startAnonymousReturn();assert(returnReady(),'anonymous return should satisfy the return readiness gate');
  assert(startRequest.path==='/return/session/start'&&startRequest.options.method==='POST'&&startRequest.options.body==='{}','anonymous context must call the server route with POST and an empty JSON body');
  api=async(path,data)=>{if(path==='/return/confirm'){requestBody=data;return {count:1}}throw Error('Unexpected API '+path)};
  let entityCalls=0;
  fetch=async path=>{if(path.startsWith('/api/entity')){entityCalls++;return {ok:true,json:async()=>({entity:{id:'asset-1',name:'Fixture item',quantity:1,entityType:{isLocation:false}},condition:'Ready'})}}if(path==='/api/custody')return {ok:true,json:async()=>[{entity_id:'asset-1'}]};throw Error('Unexpected fetch '+path)};
  await addReturn({id:'asset-1',name:'Fixture item'});assert(returnCart.length===1&&entityCalls===1,'anonymous return should add a checked-out item');
  await confirmReturn();assert(requestBody.anonymous_return===true,'confirmation must explicitly mark anonymous return');assert(requestBody.session_generation===4&&requestBody.session_instance==='terminal-1','confirmation must bind to the return-owned context');assert(doneArgs[2]==='Unidentified returner','completion should use the honest audit label');

  // A live unavailable return offers checkout for the original native item identity.
  identified=true;anonymousReturn=false;returnMode=true;checkoutMode=false;returnKey=null;returnCart=[{entity:{id:'source',name:'Source item'},note:'Keep this note'}];returnKitVersions={'source-kit':['v1']};itemActionOffer=null;itemActionOrigin=null;
  let switchFetches=[];fetch=async path=>{switchFetches.push(path);return path.startsWith('/api/entity')?{ok:true,json:async()=>({entity:{id:'asset-2',name:'Held fixture',quantity:1,entityType:{isLocation:false},condition:'Ready'},condition:'Ready'})}:{ok:true,json:async()=>[]}};
  await addReturn({id:'asset-2',name:'Held fixture'});
  const switchPanel=node('section');returnActionControls(switchPanel);assert(itemActionOffer?.mode==='checkout'&&itemActionOffer.entity.id==='asset-2'&&switchPanel.children.some(c=>c.textContent==='Check out this item instead'),'unavailable return should render checkout for the same item: '+JSON.stringify({renderedMessage,mode:returnMode,ready:returnReady(),offer:itemActionOffer,children:switchPanel.children.map(c=>c.textContent)}));
  await switchPanel.children[0].onclick();await new Promise(resolve=>setTimeout(resolve,0));assert(checkoutCart.some(e=>e.id==='asset-2')&&returnCart[0].note==='Keep this note'&&returnKitVersions['source-kit'][0]==='v1','switch should revalidate/add the same item while preserving source selections and kit draft');assert(!switchFetches.includes('/scan'),'switch should use the native item ID without an equipment scan');
  const backPanel=node('section');checkoutNotice(backPanel,'');assert(backPanel.children.some(c=>c.textContent==='Back to original list'),'destination view should offer explicit return to original list');backPanel.children.find(c=>c.textContent==='Back to original list').onclick();assert(returnMode&&!checkoutMode&&returnCart[0].note==='Keep this note','Back should restore the original list and its notes');

  // A held item offers return before its readiness blocker, then uses the same ID in the return flow.
  returnCart=[];checkoutCart=[{id:'checkout-source',name:'Keep checkout'}];checkoutMode=true;returnMode=false;itemActionOrigin=null;itemActionOffer=null;
  fetch=async path=>path.startsWith('/api/entity')?{ok:true,json:async()=>({entity:{id:'asset-3',name:'Damaged held item',quantity:1,entityType:{isLocation:false},condition:'Broken'},blocker:'Needs attention'})}:{ok:true,json:async()=>[{entity_id:'asset-3',borrower:'Fixture'}]};
  await addCheckout({id:'asset-3',name:'Damaged held item'});const reversePanel=node('section');checkoutNotice(reversePanel,'');assert(itemActionOffer?.mode==='return'&&reversePanel.children.some(c=>c.textContent==='Return this item instead'),'held equipment should offer return even when checkout is blocked');
  await reversePanel.children.find(c=>c.textContent==='Return this item instead').onclick();await new Promise(resolve=>setTimeout(resolve,0));assert(returnCart.some(t=>t.entity.id==='asset-3')&&checkoutCart[0].id==='checkout-source','switch to return should revalidate/add selected item and preserve checkout source');

  // The actual checkout picker leaves held individually tracked equipment clickable despite its readiness blocker.
  checkoutMode=true;returnMode=false;checkoutCart=[];checkoutAdding=false;api=async path=>path==='/api/stock'?[{id:'picker-held',name:'Picker held',quantity:1,condition:'Broken',entityType:{isLocation:false}}]:[{entity_id:'picker-held',borrower:'Fixture'}];await checkoutPicker();
  const findButton=(root,text)=>root.children.find(child=>child.children.some(grand=>grand.textContent===text))||root.children.map(child=>findButton(child,text)).find(Boolean);const heldChoice=findButton(lastShell,'Return this item instead');assert(heldChoice&&!heldChoice.disabled,'held blocked equipment in the picker should remain clickable for a return offer');
  fetch=async path=>path.startsWith('/api/entity')?{ok:true,json:async()=>({entity:{id:'picker-held',name:'Picker held',quantity:1,condition:'Broken',entityType:{isLocation:false}},blocker:'Broken'})}:{ok:true,json:async()=>[{entity_id:'picker-held',borrower:'Fixture'}]};await heldChoice.onclick();await new Promise(resolve=>setTimeout(resolve,0));assert(itemActionOffer?.entity.id==='picker-held'&&itemActionOffer.mode==='return','picker selection should reach the normal held-item switch flow');

  // Transport errors, invalid custody payloads and unresolved operation keys never create a switch offer.
  checkoutMode=true;returnMode=false;itemActionOffer=null;checkoutCart=[];
  fetch=async path=>path.startsWith('/api/entity')?{ok:true,json:async()=>({entity:{id:'asset-4',name:'Fixture',quantity:1,entityType:{isLocation:false},condition:'Ready'}})}:{ok:false,json:async()=>[]};
  await addCheckout({id:'asset-4'});assert(!itemActionOffer,'custody transport failure must not offer a switch');
  checkoutMode=false;returnMode=true;returnKey=null;returnCart=[];itemActionOffer=null;
  fetch=async path=>path.startsWith('/api/entity')?{ok:true,json:async()=>({entity:{id:'asset-5',name:'Fixture',quantity:1,entityType:{isLocation:false}},condition:'Ready'})}:{ok:true,json:async()=>({invalid:true})};
  await addReturn({id:'asset-5'});assert(!itemActionOffer&&renderedMessage==='Could not verify custody','invalid custody data must stay an error');
  returnCart=[];itemActionOffer=null;let releaseCustody;fetch=async path=>path.startsWith('/api/entity')?{ok:true,json:async()=>({entity:{id:'late',name:'Late',quantity:1,entityType:{isLocation:false}},condition:'Ready'})}:new Promise(resolve=>{releaseCustody=()=>resolve({ok:true,json:async()=>[]})});
  const lateAdd=addReturn({id:'late'});await new Promise(resolve=>setTimeout(resolve,0));routeRevision++;releaseCustody();await lateAdd;assert(!itemActionOffer&&!returnCart.length,'a custody callback from an old route must not restore an item or offer');routeRevision++;
  fetch=async path=>path.startsWith('/api/entity')?{ok:true,json:async()=>({entity:{id:'archived',name:'Archived',archived:true,quantity:1,entityType:{isLocation:false}},condition:'Ready'})}:{ok:true,json:async()=>[]};
  await addReturn({id:'archived'});assert(!itemActionOffer,'an unavailable archived item must not offer checkout');
  fetch=async path=>path.startsWith('/api/entity')?{ok:true,json:async()=>({entity:{id:'archived-held',name:'Archived held',archived:true,quantity:1,entityType:{isLocation:false}},condition:'Ready'})}:{ok:true,json:async()=>[{entity_id:'archived-held'}]};
  await addReturn({id:'archived-held'});assert(returnCart.some(t=>t.entity.id==='archived-held'),'existing valid return of held archived equipment should remain available');
  itemActionOffer={mode:'checkout',entity:{id:'asset-6'},sourceMode:'return',generation:identityGeneration,instance:identityInstance};returnKey='uncertain';const beforeMode=returnMode;beginItemActionSwitch();assert(returnMode===beforeMode&&returnKey==='uncertain'&&itemActionOffer.entity.id==='asset-6','an unresolved return key must prevent switching and retain recovery state');returnKey=null;itemActionOffer=null;

  // Anonymous badge handoff holds only the selected ID, keeps Back lossless, then clears the old cart on identification.
  identified=false;anonymousReturn=true;returnMode=true;checkoutMode=false;identityGeneration=8;identityInstance='anon';returnCart=[{entity:{id:'anon-other'},note:'Do not transfer'}];returnKitVersions={'anon-kit':['verified']};
  itemActionOffer={mode:'checkout',entity:{id:'transfer-only',name:'Transfer item'},sourceMode:'return',generation:8,instance:'anon'};const anonPanel=node('section');returnActionControls(anonPanel);anonPanel.children.find(c=>c.textContent==='Check out this item instead').onclick();
  assert(returnCart.length===1&&pendingItemAction?.entity.id==='transfer-only'&&checkoutMode,'anonymous checkout gate should preserve its source list until identification');
  const pendingBack=node('section');checkoutNotice(pendingBack,'');pendingBack.children.find(c=>c.textContent==='Back to original list').onclick();assert(!pendingItemAction&&returnCart.length===1&&returnMode,'Back before badge acceptance must cancel the handoff and preserve the anonymous list');
  itemActionOffer={mode:'checkout',entity:{id:'transfer-only',name:'Transfer item'},sourceMode:'return',generation:8,instance:'anon'};const again=node('section');returnActionControls(again);again.children[0].onclick();
  checkoutCart=[{id:'old-badge-checkout'}];checkoutKitVersions={'old-badge-kit':['old stamp']};fetch=async path=>path.startsWith('/api/entity')?{ok:true,json:async()=>({entity:{id:'transfer-only',name:'Transfer item',quantity:1,entityType:{isLocation:false},condition:'Ready'}})}:{ok:true,json:async()=>[]};
  labelQueue=['old-label-item'];labelMakerReviews=[{review_id:'old-review'}];labelReviewOrder=['old-label-item'];labelMakerTemplates=[{id:'old-template'}];labelMakerDirty=true;labelMakerBusy=true;labelMakerPanel.children=[node('p','Old label session')];
  api=async()=>({user:{id:'new-user',name:'New user'},generation:9,instance:'terminal-1',return_only:false});await updateIdentity();
  assert(checkoutCart.length===1&&checkoutCart[0].id==='transfer-only'&&!checkoutKitVersions['old-badge-kit']&&returnCart.length===0&&!returnKitVersions['anon-kit']&&!pendingItemAction,'badge acceptance should clear old-owner drafts and revalidate only the selected item');
  assert(labelDisposed===1&&labelDesignerHandle===null&&!labelQueue.length&&!labelMakerReviews.length&&!labelReviewOrder.length&&!labelMakerTemplates.length&&!labelMakerDirty&&!labelMakerBusy&&labelQueueContext===''&&labelMakerPanel.children[0]?.textContent.includes('session changed'),'badge acceptance should dispose and clear the prior label editor and reviews');

  // Starting an anonymous return drops parked old-badge checkout drafts only after a safe identity transition.
  identified=true;anonymousReturn=false;returnMode=true;checkoutCart=[{id:'old-badge-checkout'}];checkoutKitVersions={'old':['verified']};
  api=async()=>({generation:10,instance:'anon-2'});await startAnonymousReturn();
  assert(anonymousReturn&&!checkoutCart.length&&!checkoutKitVersions.old,'starting anonymous return must clear old-owner checkout selections and kit stamps');

  // routeBack restores the source return route and cancels its pending badge transfer.
  identityGeneration=10;identityInstance='anon-2';returnMode=true;checkoutMode=false;identified=false;anonymousReturn=true;returnCart=[{entity:{id:'guest-source'},note:'Guest note'}];returnKitVersions={'guest':['verified']};routeTitle='Add returns';view.childNodes=[node('p','Original guest return')];routeStack=[];
  itemActionOffer={mode:'checkout',entity:{id:'must-not-transfer',name:'Pending'},sourceMode:'return',generation:10,instance:'anon-2'};const switchToBadge=node('section');returnActionControls(switchToBadge);switchToBadge.children.find(c=>c.textContent==='Check out this item instead').onclick();
  checkoutKey='uncertain-checkout';const guardedStack=routeStack.length;routeBack();assert(checkoutKey==='uncertain-checkout'&&routeStack.length===guardedStack&&checkoutMode&&!returnMode&&pendingItemAction?.entity.id==='must-not-transfer','routeBack must preserve the destination mode, origin, and recovery key while checkout is uncertain');checkoutKey=null;
  const staleSourceOffer=node('button','Check out this item instead');view.querySelectorAll=()=>[staleSourceOffer];routeBack();assert(returnMode&&!checkoutMode&&!pendingItemAction&&returnCart[0].note==='Guest note'&&view.childNodes[0].textContent==='Original guest return'&&!routeStack.length&&staleSourceOffer.removed,'Escape/routeBack should restore the guest list, clear its stale offer, and cancel the pending transfer');view.querySelectorAll=()=>[];
  fetch=async path=>({ok:true,json:async()=>({user:{id:'badge-user',name:'Badge user'},generation:11,instance:'anon-2'})});
  await routeScan('badge');assert(!checkoutCart.some(e=>e.id==='must-not-transfer')&&returnMode&&!checkoutMode,'badge scan after Back must not resurrect the cancelled transfer');

  // A deliberate badge scan carries one selected ID through routeScan and clears parked checkout drafts.
  identityGeneration=12;identityInstance='anon-3';identified=false;anonymousReturn=true;returnMode=true;checkoutMode=false;returnCart=[{entity:{id:'anonymous-other'},note:'Do not carry'}];returnKitVersions={'anonymous':['stamp']};checkoutCart=[{id:'old-checkout'}];checkoutKitVersions={'old-checkout-kit':['stamp']};
  itemActionOffer={mode:'checkout',entity:{id:'scan-transfer',name:'Scan transfer'},sourceMode:'return',generation:12,instance:'anon-3'};const scanSwitch=node('section');returnActionControls(scanSwitch);scanSwitch.children.find(c=>c.textContent==='Check out this item instead').onclick();
  fetch=async path=>path==='/scan'?{ok:true,json:async()=>({user:{id:'badge-user',name:'Badge user'},generation:13,instance:'anon-3'})}:path.startsWith('/api/entity')?{ok:true,json:async()=>({entity:{id:'scan-transfer',name:'Scan transfer',quantity:1,entityType:{isLocation:false},condition:'Ready'}})}:{ok:true,json:async()=>[]};
  await routeScan('badge');assert(checkoutCart.length===1&&checkoutCart[0].id==='scan-transfer'&&!checkoutKitVersions['old-checkout-kit']&&!returnCart.length&&!returnKitVersions.anonymous,'routeScan badge acceptance should clear old-owner drafts and revalidate only the selected ID');

  // A duplicate, storage label, or unrecognized scan invalidates a previous item offer.
  returnMode=true;checkoutMode=false;returnCart=[{entity:{id:'duplicate'}}];itemActionOffer={mode:'checkout',entity:{id:'older'},sourceMode:'return',generation:identityGeneration,instance:identityInstance};await addReturn({id:'duplicate'});assert(!itemActionOffer,'duplicate item attempts must clear stale offers');
  checkoutMode=true;returnMode=false;itemActionOffer={mode:'return',entity:{id:'older'},sourceMode:'checkout',generation:identityGeneration,instance:identityInstance};fetch=async()=>({ok:true,json:async()=>({entity:{id:'shelf',entityType:{isLocation:true}}})});await routeScan('shelf');assert(!itemActionOffer,'storage-label attempts must clear stale offers');
  itemActionOffer={mode:'return',entity:{id:'older'},sourceMode:'checkout',generation:identityGeneration,instance:identityInstance};const visibleOffer=node('button','Return this item instead');view.querySelectorAll=()=>[visibleOffer];fetch=async()=>({ok:true,json:async()=>({reason:'Unknown code'})});await routeScan('unknown');assert(!itemActionOffer&&visibleOffer.removed,'unrecognized scans must remove stale offer controls');view.querySelectorAll=()=>[];

  // The actual poll callback invalidates any draft when anonymous ownership changes.
  anonymousReturn=true;identified=false;returnMode=true;identityGeneration=4;identityInstance='terminal-1';returnCart=[{entity:{id:'stale'}}];returnKitVersions={'kit':['old']};kitDraft={id:'old'};
  api=async()=>({user:null,generation:5,instance:'terminal-1',return_only:true});await updateIdentity();
  assert(!anonymousReturn&&returnCart.length===0&&returnKitVersions&&Object.keys(returnKitVersions).length===0&&!kitDraft,'a replaced anonymous context must discard its return draft and kit verification '+JSON.stringify({anonymousReturn,returnCart,returnKitVersions,kitDraft}));
  anonymousReturn=true;identified=false;returnMode=true;identityGeneration=5;identityInstance='terminal-1';returnCart=[{entity:{id:'stale'}}];
  api=async()=>({user:{id:'borrower',name:'Fixture borrower'},generation:6,instance:'terminal-1',return_only:false});await updateIdentity();
  assert(identified&&!anonymousReturn&&returnCart.length===0&&identityAtRender===true,'a newly observed badge must clear the anonymous draft and rerender return under the badge identity '+JSON.stringify({identified,anonymousReturn,returnCart,identityAtRender,returnMode,pendingItemAction}));

  // The checkout renderer still shows its badge gate in the same anonymous client state.
  identified=false;anonymousReturn=true;checkoutMode=true;frames=[];renderCheckout();assert(frames[0]==='Check out equipment','anonymous context must not satisfy checkout identity');

  // Existing focus helper exposes controls and initializes auto focus before it returns.
  const focusCalls=[];scanOverlay=node('overlay');let focusMessage=node('p','Starting');
  api=async(path,data)=>{focusCalls.push([path,data]);return path==='/api/camera'?{supported:true,value:100}:{mode:data.mode,value:data.value}};
  await cameraFocusControls(scanOverlay,focusMessage,false,true);
  const controls=scanOverlay.children[0];assert(controls.children.some(c=>c.textContent==='Autofocus'),'autofocus button should be available');assert(controls.children.some(c=>c.textContent==='Label focus'),'manual focus button should be available');assert(controls.children.some(c=>c.attrs['aria-label']==='Pi camera focus: far to near'),'manual slider should be available');assert(focusCalls.some(([path,data])=>path==='/camera/focus'&&data.mode==='auto'),'scan startup should enable autofocus');

  // A delayed camera-status response after close/new scan must not mount stale controls.
  const oldOverlay=node('old'),newOverlay=node('new');scanOverlay=oldOverlay;let resolveCamera;
  api=(path)=>new Promise(resolve=>{resolveCamera=()=>resolve({supported:true,value:50})});
  const lateSetup=cameraFocusControls(oldOverlay,node('p'),false,true);scanOverlay=newOverlay;resolveCamera();await lateSetup;assert(oldOverlay.children.length===0,'late setup must not attach controls to a closed scan');

  // A delayed focus response after the overlay changes must not update the old status node.
  scanOverlay=oldOverlay;let resolveFocus;
  api=(path,data)=>path==='/api/camera'?Promise.resolve({supported:true,value:50}):new Promise(resolve=>{resolveFocus=()=>resolve({mode:data.mode,value:data.value})});
  const staleMessage=node('p','Keep this status');await cameraFocusControls(oldOverlay,staleMessage,false,false);
  const auto=oldOverlay.children[0].children.find(c=>c.textContent==='Autofocus');const pending=auto.onclick();scanOverlay=newOverlay;resolveFocus();await pending;assert(staleMessage.textContent==='Keep this status','late focus completion must not mutate stale overlay status');

  const result=document.body.children[0];if(!result)throw Error('test result node missing');result.textContent='PASS';
}catch(error){const result=document.body.children[0];if(result)result.textContent='FAIL '+error.stack}})();
'''
        html='<!doctype html><meta charset="utf-8"><pre id="result">RUNNING</pre><script>window.onerror=(message)=>{document.querySelector("#result").textContent="JS ERROR "+message}</script><script>(function(){\n'+script+'\n})();</script>'
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest('Playwright is unavailable for the UI behavior fixture')
        with tempfile.TemporaryDirectory(prefix='return-ui-fixture-') as temp, sync_playwright() as playwright:
            path=pathlib.Path(temp)/'fixture.html';path.write_text(html)
            browser=playwright.chromium.launch(executable_path=chromium,headless=True,timeout=15000,args=['--no-sandbox','--disable-background-networking','--disable-component-update','--disable-gpu','--disable-dev-shm-usage'])
            page=browser.new_page();page_errors=[];page.on('pageerror',lambda error:page_errors.append(str(error)))
            try:
                page.goto(path.as_uri(),wait_until='domcontentloaded',timeout=10000)
                page.wait_for_function("document.querySelector('#result')?.textContent !== 'RUNNING'",timeout=10000)
                result=page.locator('#result').inner_text()
                self.assertEqual(result,'PASS','UI fixture failed: '+result+'; page errors: '+repr(page_errors))
                self.assertFalse(page_errors,'Unexpected browser errors: '+repr(page_errors))
            finally:
                browser.close()


if __name__=='__main__':unittest.main()
