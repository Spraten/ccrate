"""Ownership and callback contracts for the badge-owned Terminal item-note task."""
import pathlib
import re
import os
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def function_source(source, name):
    match = re.search(rf"(?:async )?function {re.escape(name)}\([^)]*\)\s*\{{", source)
    if not match:
        return ''
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    return ''


class ItemNotesBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT/'kiosk/workflow-ui.js').read_text()
        cls.terminal = (ROOT/'kiosk/terminal.js').read_text()

    def test_dashboard_and_scan_flow_require_active_individual_equipment(self):
        self.assertIn("['Add Notes to Item','Record an independent equipment note']", self.terminal)
        self.assertIn("else if(itemNoteMode)startItemNote()", self.terminal)
        self.assertIn("data.entity.archived||data.entity.quantity!==1", self.terminal)
        self.assertIn("function startItemNote(message='')", self.workflow)
        self.assertIn('function itemNoteForm(entity,draft=', self.workflow)

    def test_confirm_is_single_owner_bound_post_and_rejects_invalid_utf8_size(self):
        confirm = function_source(self.workflow, 'confirmItemNote')
        self.assertTrue(confirm)
        self.assertIn("api('/notes/confirm'", confirm)
        self.assertIn('session_generation:generation', confirm)
        self.assertIn('session_instance:instance', confirm)
        self.assertIn('new TextEncoder().encode', confirm)
        self.assertIn('Array.from(note).length>1000', confirm)
        self.assertIn('itemNoteOwnerCurrent(pending,true)', confirm)
        self.assertNotIn('transactionDone(', confirm)

    def test_uncertain_result_callback_only_checks_status_and_never_resubmits(self):
        inspect = function_source(self.workflow, 'checkItemNoteResult')
        self.assertTrue(inspect)
        self.assertIn("api('/operation/status'", inspect)
        self.assertNotIn("api('/notes/confirm'", inspect)
        self.assertIn("result.status==='completed'", inspect)
        self.assertIn("['not_started','cancelled'].includes(result.status)", inspect)
        self.assertIn('itemNoteOwnerCurrent(pending,false)', inspect)

    def test_pending_storage_contains_only_owner_scoped_metadata(self):
        persist = function_source(self.workflow, 'saveItemNotePending')
        self.assertTrue(persist)
        self.assertIn('request_key:pending.key', persist)
        self.assertIn('entity_id:pending.entityId', persist)
        self.assertIn('actor_id:pending.actorId', persist)
        self.assertIn('generation:pending.generation', persist)
        self.assertIn('instance:pending.instance', persist)
        self.assertNotIn('note:', persist)
        self.assertNotIn('body:', persist)

    def test_confirmed_result_ends_only_expected_session_and_cleanup_error_is_saved(self):
        finish = function_source(self.workflow, 'finishItemNoteSaved')
        self.assertTrue(finish)
        self.assertIn("api('/session/end'", finish)
        self.assertIn('expected_generation:pending.generation', finish)
        self.assertIn('expected_instance:pending.instance', finish)
        self.assertIn('Note saved', finish)
        self.assertIn('cleanup', finish)

    def test_reload_stale_reply_and_double_click_remain_owner_scoped(self):
        load = function_source(self.workflow, 'readItemNotePending')
        confirm = function_source(self.workflow, 'confirmItemNote')
        inspect = function_source(self.workflow, 'checkItemNoteResult')
        self.assertIn('sessionStorage.getItem', load)
        self.assertIn('actor_id', load)
        self.assertIn('request_key', load)
        self.assertIn('itemNoteBusy||itemNotePending', confirm)
        self.assertIn('revision!==routeRevision', confirm)
        self.assertIn('generation!==identityGeneration', confirm)
        self.assertIn('instance!==identityInstance', confirm)
        self.assertIn('actor!==identityUserId', inspect)
        self.assertIn('generation!==identityGeneration', inspect)
        self.assertIn('instance!==identityInstance', inspect)
        self.assertIn('identityUserId!==itemNoteDraft.actorId', self.workflow)

    def test_recovery_surfaces_item_note_status_and_requires_safe_action(self):
        self.assertIn("add_note:'Item note'", self.terminal)
        self.assertIn("label=note?(outcome==='complete'?'Confirm saved Item note':'Cancel unstarted Item note')", self.terminal)
        self.assertIn("b.disabled=outcome==='complete'?row.status==='prepared':row.status!=='prepared'", self.terminal)
        tools = (ROOT/'homebox-ui/overlay/lib/workshop-tools.js').read_text()
        recovery = function_source(tools, 'recoveryPage')
        dialog = function_source(tools, 'recoveryDialog')
        self.assertTrue(recovery)
        self.assertTrue(dialog)
        self.assertIn("table(['Operation','Status','Equipment','Action']", recovery)
        self.assertIn("button('Inspect operation'", recovery)
        self.assertIn("node('p','Operation: '+row.action+' · '+row.status)", dialog)
        self.assertIn("write('recovery/resolve'", dialog)
        self.assertNotIn("notes/confirm", dialog)

    def test_plain_http_uuid_fallback_sets_rfc4122_bits(self):
        self.assertIn('if(!crypto.randomUUID)crypto.randomUUID=()', self.workflow)
        self.assertIn("bytes[6]=(bytes[6]&15)|64", self.workflow)
        self.assertIn("bytes[8]=(bytes[8]&63)|128", self.workflow)

    def test_route_and_dashboard_guards_cover_note_draft_and_pending_state(self):
        self.assertIn('routeBack=function(discard=false){\n    if(itemNoteBusy)return;', self.workflow)
        self.assertIn('leaveTask=function(action){if(itemNoteBusy)return;', self.workflow)
        self.assertIn('hasDraft=function(){return originalHasDraftForNotes()||!!itemNoteDraft?.note||!!itemNotePending}', self.workflow)
        self.assertIn('workflowBusy=function(){return originalWorkflowBusyForNotes()||itemNoteBusy}', self.workflow)
        self.assertIn('resetTask=function(){itemNoteMode=false;itemNoteDraft=null;return originalResetTaskForNotes()}', self.workflow)
        self.assertNotIn('clearItemNotePending();return originalResetTaskForNotes()', self.workflow)
        capture = function_source(self.workflow, 'captureRoute')
        self.assertIn('itemNoteMode', capture)

    def test_server_confirm_route_is_same_origin_and_recovers_add_note_explicitly(self):
        server = (ROOT/'deploy/kiosk-server.py').read_text()
        self.assertIn("if self.path == '/notes/confirm' or self.path.startswith('/workshop/checks/')", server)
        self.assertIn("if self.path=='/notes/confirm':", server)
        self.assertIn('same_origin(self.headers.get(\'Origin\'),self.headers.get(\'Host\'))', server)
        self.assertIn("handler=recover_note if job['kind']=='add_note'", server)


@unittest.skipUnless(os.environ.get('RUN_ITEM_NOTE_BROWSER_FIXTURE') == '1',
                     'coordinator runs the real callback fixture with installed Chromium')
class ItemNoteCallbackBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT/'kiosk/workflow-ui.js').read_text()
        start_marker = '// Standalone notes are owner-bound requests'
        end_marker = '\nasync function showContents(panel,entity)'
        if cls.workflow.count(start_marker) != 1 or cls.workflow.count(end_marker) != 1:
            raise AssertionError('Expected one bounded standalone-note callback block')
        start = cls.workflow.index(start_marker)
        end = cls.workflow.index(end_marker)
        if end <= start:
            raise AssertionError('Standalone-note callback block boundary is invalid')
        cls.note_code = cls.workflow[start:end]
        if not cls.note_code.strip():
            raise AssertionError('Standalone-note callback block is empty')
        fallback_lines = [line for line in cls.workflow.splitlines()
                          if line.startswith('if(!crypto.randomUUID)crypto.randomUUID=()=>')]
        if len(fallback_lines) != 1:
            raise AssertionError('Expected one checked plain-HTTP UUID initializer')
        cls.uuid_fallback = fallback_lines[0]
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.set_content('<main id="view"></main><div id="status"></div><span id="identity"></span><button id="end-session"></button><button id="scan"></button>')
        prelude = r"""
const view=document.querySelector('#view'),status=document.querySelector('#status');
let identityUserId='actor-A',identityGeneration=4,identityInstance='session-A',identified=true,routeRevision=12,routeStack=[],formDirty=false;
const inventory=[];const calls=[];let apiHandler=async(path,data)=>path==='/api/session'?{user:{id:identityUserId},generation:identityGeneration,instance:identityInstance}:path==='/session/end'?{ended:true}:{status:'unknown'};
Object.defineProperty(window,'sessionStorage',{value:(()=>{const values=new Map();return {getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,String(value)),removeItem:key=>values.delete(key)}})()});
async function api(path,data){calls.push({path,data});return apiHandler(path,data)}
function node(tag,text,cls){const value=document.createElement(tag);if(text!==undefined)value.textContent=text;if(cls)value.className=cls;return value}
function primary(label,fn){const button=node('button',label);button.onclick=fn;return button}
function heading(title){routeRevision++;view.replaceChildren();view.dataset.title=title}
function workflowBusy(){return false}function hasDraft(){return false}function resetTask(){}function routeBack(){}function leaveTask(action){action()}function open(){}async function updateIdentity(){const data=await api('/api/session');identityUserId=data.user?.id||null;identityGeneration=data.generation;identityInstance=data.instance;identified=!!data.user}
window.__setApiHandler=fn=>apiHandler=fn;window.__calls=calls;window.__state={get pending(){return itemNotePending},set pending(value){itemNotePending=value},get draft(){return itemNoteDraft},set draft(value){itemNoteDraft=value},get busy(){return itemNoteBusy},set busy(value){itemNoteBusy=value},get actor(){return identityUserId},set actor(value){identityUserId=value},get identified(){return identified},set identified(value){identified=value},get generation(){return identityGeneration},set generation(value){identityGeneration=value},get instance(){return identityInstance},set instance(value){identityInstance=value},get routeRevision(){return routeRevision},get title(){return view.dataset.title},get savedText(){return view.textContent},get storage(){return sessionStorage.getItem('c-crate-item-note-pending-v1')}};
"""
        self.page.add_script_tag(content=prelude+self.uuid_fallback+'\n'+self.note_code+"\nwindow.__note={startItemNote,itemNoteForm,reviewItemNote,confirmItemNote,checkItemNoteResult,finishItemNoteSaved,routeBack,leaveTask,readItemNotePending,saveItemNotePending};")

    def tearDown(self):
        self.page.close()

    def test_double_confirm_sends_one_note_and_success_ends_expected_session(self):
        result = self.page.evaluate("""async()=>{
          let finish;window.__setApiHandler((path,data)=>{if(path==='/notes/confirm')return new Promise(resolve=>finish=resolve);if(path==='/session/end')return Promise.resolve({ended:true});return Promise.resolve({status:'unknown'})});
          const pending={key:'11111111-1111-4111-8111-111111111111',entityId:'item-1',actorId:'actor-A',generation:4,instance:'session-A'};
          const first=window.__note.confirmItemNote(pending,'A separate note');await Promise.resolve();
          const second=window.__note.confirmItemNote(pending,'A separate note');await Promise.resolve();
          const before=window.__calls.filter(call=>call.path==='/notes/confirm').length;
          finish({id:'job-1',status:'completed',note_saved:true,session_ended:false});await Promise.all([first,second]);
          return {before,posts:window.__calls.filter(call=>call.path==='/notes/confirm').length,ends:window.__calls.filter(call=>call.path==='/session/end').length,title:window.__state.title,text:window.__state.savedText,stored:window.__state.storage};
        }""")
        self.assertEqual(result['before'], 1)
        self.assertEqual(result['posts'], 1)
        self.assertEqual(result['ends'], 1)
        self.assertEqual(result['title'], 'Item note saved')
        self.assertIn('Note saved', result['text'])
        self.assertIsNone(result['stored'])

    def test_lost_reply_checks_status_once_then_saved_cleanup_failure_stays_saved(self):
        result = self.page.evaluate("""async()=>{
          window.__setApiHandler(async(path)=>{if(path==='/notes/confirm')throw Error('reply lost');if(path==='/operation/status')return {status:'completed'};if(path==='/session/end')throw Error('cleanup failed');return {}});
          const pending={key:'22222222-2222-4222-8222-222222222222',entityId:'item-2',actorId:'actor-A',generation:4,instance:'session-A'};
          await window.__note.confirmItemNote(pending,'Saved once');
          return {paths:window.__calls.map(call=>call.path),title:window.__state.title,text:window.__state.savedText,stored:window.__state.storage};
        }""")
        self.assertEqual(result['paths'].count('/notes/confirm'), 1)
        self.assertEqual(result['paths'].count('/operation/status'), 1)
        self.assertEqual(result['paths'].count('/session/end'), 1)
        self.assertEqual(result['title'], 'Item note saved')
        self.assertIn('cleanup needs checking', result['text'])
        self.assertNotIn('/notes/confirm', result['paths'][1:])
        self.assertIsNone(result['stored'])

    def test_stale_reply_cannot_end_replacement_badge_session(self):
        result = self.page.evaluate("""async()=>{
          let finish;window.__setApiHandler((path)=>path==='/notes/confirm'?new Promise(resolve=>finish=resolve):Promise.resolve({}));
          const pending={key:'33333333-3333-4333-8333-333333333333',entityId:'item-3',actorId:'actor-A',generation:4,instance:'session-A'};
          const request=window.__note.confirmItemNote(pending,'Old owner draft');await Promise.resolve();
          window.__state.actor='actor-B';window.__state.generation=5;window.__state.instance='session-B';
          finish({status:'completed',note_saved:true,session_ended:false});await request;
          return {ends:window.__calls.filter(call=>call.path==='/session/end').length,title:window.__state.title,stored:window.__state.storage};
        }""")
        self.assertEqual(result['ends'], 0)
        self.assertNotEqual(result['title'], 'Item note saved')
        self.assertIsNotNone(result['stored'])

    def test_reload_metadata_has_no_body_and_different_actor_cannot_inspect_or_transfer(self):
        result = self.page.evaluate("""()=>{
          const pending={key:'44444444-4444-4444-8444-444444444444',entityId:'item-4',actorId:'actor-A',generation:4,instance:'session-A'};
          window.__note.saveItemNotePending(pending);
          const stored=window.__state.storage;window.__state.pending=window.__note.readItemNotePending();
          window.__state.actor='actor-B';window.__note.startItemNote();
          return {stored,pendingActor:window.__state.pending?.actorId,title:window.__state.title,text:window.__state.savedText,notesPosts:window.__calls.filter(call=>call.path==='/notes/confirm').length,statusCalls:window.__calls.filter(call=>call.path==='/operation/status').length,sessionEnds:window.__calls.filter(call=>call.path==='/session/end').length};
        }""")
        self.assertNotIn('A private note body', result['stored'])
        self.assertNotIn('note', result['stored'])
        self.assertEqual(result['pendingActor'], 'actor-A')
        self.assertEqual(result['notesPosts'], 0)
        self.assertEqual(result['statusCalls'], 0)
        self.assertEqual(result['sessionEnds'], 0)
        self.assertIn('another badge', result['text'])

    def test_back_discard_and_busy_callback_keep_unsent_note_in_memory_only(self):
        result = self.page.evaluate("""()=>{
          window.__state.draft={note:'Never persist this text',actorId:'actor-A',generation:4,instance:'session-A'};
          routeStack.push({dirty:false});routeBack();
          const prompt=document.querySelector('.workflow-dialog');const before=window.__state.draft?.note;
          const discard=[...prompt.querySelectorAll('button')].find(button=>button.textContent==='Discard note & go back');discard.click();
          window.__state.busy=true;const busy=workflowBusy();window.__state.busy=false;
          return {before,after:window.__state.draft,busy,stored:window.__state.storage};
        }""")
        self.assertEqual(result['before'], 'Never persist this text')
        self.assertIsNone(result['after'])
        self.assertTrue(result['busy'])
        self.assertIsNone(result['stored'])

    def test_inflight_confirm_blocks_all_back_and_home_paths_then_shows_saved(self):
        result = self.page.evaluate("""async()=>{
          let finish;window.__setApiHandler((path)=>path==='/notes/confirm'?new Promise(resolve=>finish=resolve):Promise.resolve({ended:true}));
          const pending={key:'55555555-5555-4555-8555-555555555555',entityId:'item-5',actorId:'actor-A',generation:4,instance:'session-A'};
          const entity={id:'item-5',name:'Scope',assetId:'EQ-5'};const draft={note:'A note body',actorId:'actor-A',generation:4,instance:'session-A'};
          reviewItemNote(entity,draft);const request=window.__note.confirmItemNote(pending,draft.note);await Promise.resolve();
          const before={title:window.__state.title,revision:window.__state.routeRevision};
          routeBack();leaveTask(()=>heading('Home'));
          const reviewBack=[...view.querySelectorAll('button')].find(button=>button.textContent==='Back');reviewBack.click();
          const during={title:window.__state.title,revision:window.__state.routeRevision};
          finish({status:'completed',note_saved:true,session_ended:true});await request;
          return {before,during,title:window.__state.title,stored:window.__state.storage,posts:window.__calls.filter(call=>call.path==='/notes/confirm').length,ends:window.__calls.filter(call=>call.path==='/session/end').length};
        }""")
        self.assertEqual(result['during'], result['before'])
        self.assertEqual(result['title'], 'Item note saved')
        self.assertEqual(result['posts'], 1)
        self.assertEqual(result['ends'], 0)
        self.assertIsNone(result['stored'])

    def test_reset_or_expiry_preserves_pending_for_same_badge_status_only(self):
        result = self.page.evaluate("""async()=>{
          const pending={key:'66666666-6666-4666-8666-666666666666',entityId:'item-6',actorId:'actor-A',generation:4,instance:'session-A'};
          saveItemNotePending(pending);window.__state.draft={note:'body must not survive reset',actorId:'actor-A'};resetTask();
          const retainedAfterReset=window.__state.storage;
          window.__state.actor=null;window.__state.identified=false;window.__state.generation=8;window.__state.instance='session-A-expired';
          window.__setApiHandler(async(path)=>path==='/operation/status'?{status:'completed'}:{user:{id:'actor-A'},generation:8,instance:'session-A-restarted'});
          leaveTask(()=>startItemNote());const mustRescan=[...view.querySelectorAll('button')].some(button=>button.textContent==='Scan badge');
          await updateIdentity();startItemNote();
          const card=[...view.querySelectorAll('button')].find(button=>button.textContent==='Check saved result');card.click();
          await new Promise(resolve=>setTimeout(resolve,0));
          return {retainedAfterReset,mustRescan,pending:window.__state.storage,posts:window.__calls.filter(call=>call.path==='/notes/confirm').length,status:window.__calls.filter(call=>call.path==='/operation/status').length,ends:window.__calls.filter(call=>call.path==='/session/end').length,title:window.__state.title};
        }""")
        self.assertIsNotNone(result['retainedAfterReset'])
        self.assertTrue(result['mustRescan'])
        self.assertIsNone(result['pending'])
        self.assertEqual(result['posts'], 0)
        self.assertEqual(result['status'], 1)
        self.assertEqual(result['ends'], 0)
        self.assertEqual(result['title'], 'Item note saved')

    def test_replacement_badge_cannot_receive_pending_body_or_cleanup(self):
        result = self.page.evaluate("""()=>{
          const pending={key:'77777777-7777-4777-8777-777777777777',entityId:'item-7',actorId:'actor-A',generation:4,instance:'session-A'};
          saveItemNotePending(pending);window.__state.draft={note:'private prior-owner body'};window.__state.actor='actor-B';window.__state.generation=5;window.__state.instance='session-B';
          startItemNote();
          return {storage:window.__state.storage,title:window.__state.title,text:window.__state.savedText,calls:window.__calls.map(call=>call.path)};
        }""")
        self.assertIsNotNone(result['storage'])
        self.assertEqual(result['title'], 'Item note belongs to another badge')
        self.assertNotIn('private prior-owner body', result['text'])
        self.assertNotIn('/notes/confirm', result['calls'])
        self.assertNotIn('/operation/status', result['calls'])
        self.assertNotIn('/session/end', result['calls'])


if __name__ == '__main__':
    unittest.main()
