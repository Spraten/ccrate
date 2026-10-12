import json
import pathlib
import base64
import os
import time
import unittest
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError

from playwright.sync_api import sync_playwright


ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCATION = '11111111-1111-4111-8111-111111111111'
ITEM = '22222222-2222-4222-8222-222222222222'
DRAWING = '33333333-3333-4333-8333-333333333333'
RACK = '44444444-4444-4444-8444-444444444444'
SHELF = '55555555-5555-4555-8555-555555555555'


class RemoteShelfFixture:
    """Query the verifier-owned Ledger through its loopback fixture bridge."""
    def __init__(self, endpoint):
        self.endpoint=endpoint
    def state(self):
        if not self.endpoint: raise RuntimeError('Run these browser cases through deploy/verify-shelf-checks.py.')
        with urlopen(self.endpoint+'/__fixture__/state',timeout=5) as response:
            return json.loads(response.read())
    def check_count(self): return self.state()['check_count']
    @property
    def requests(self): return self.state()['requests']


def view(entity_id=None):
    path = ([{'id': LOCATION, 'name': 'Storage Room', 'is_location': True, 'parent_id': None}]
            if entity_id == LOCATION else ([
                {'id': LOCATION, 'name': 'Storage Room', 'is_location': True, 'parent_id': None},
                {'id': '66666666-6666-4666-8666-666666666666', 'name': 'the Cage', 'is_location': True, 'parent_id': LOCATION},
                {'id': RACK, 'name': 'Rack 1', 'is_location': True, 'parent_id': '66666666-6666-4666-8666-666666666666'},
                {'id': SHELF, 'name': 'Rack 1-A', 'is_location': True, 'parent_id': RACK},
            ] if entity_id == SHELF else [
                {'id': LOCATION, 'name': 'Storage Room', 'is_location': True, 'parent_id': None},
                {'id': '66666666-6666-4666-8666-666666666666', 'name': 'the Cage', 'is_location': True, 'parent_id': LOCATION},
                {'id': RACK, 'name': 'Rack 1', 'is_location': True, 'parent_id': '66666666-6666-4666-8666-666666666666'},
                {'id': SHELF, 'name': 'Rack 1-A', 'is_location': True, 'parent_id': RACK},
                {'id': ITEM, 'name': 'Camera', 'is_location': False, 'parent_id': SHELF},
            ]))
    return {
        'selection': {'target_id': entity_id, 'destination_id': LOCATION,
                      'kind': 'containing', 'matches': [{'room_id': None,
                      'drawing_id': DRAWING, 'location_id': LOCATION, 'name': 'Rack 1'},
                      {'room_id': None, 'drawing_id': '77777777-7777-4777-8777-777777777777',
                       'location_id': LOCATION, 'name': 'Rack 1 alternate'}]},
        'path': path,
        'contents': ([{'id': ITEM, 'name': 'Camera', 'assetId': 'CAM-9', 'serialNumber': 'SN-9',
                      'manufacturer': 'Northwind', 'condition': 'Ready', 'checkout_blocker': None,
                      'checked_out': True, 'parent': {'id': SHELF}}] if entity_id == LOCATION else []),
        'include_nested': entity_id == ITEM,
        'counts': ({'assigned': 1, 'checked_out': 1, 'available': 0, 'needs_attention': 0}
                   if entity_id == LOCATION else {'assigned': 0, 'checked_out': 0, 'available': 0, 'needs_attention': 0}),
        'coverage': [{'location_id': SHELF, 'drawing_id': None, 'kind': 'unmapped',
                      'message': 'No map coverage for Rack 1-A'}],
        'rack': {'id': LOCATION, 'name': 'Rack 1', 'shelves': [
            {'id': SHELF, 'name': 'Rack 1-A', 'code': '1-A'}], 'unordered': [],
            'other_children': [{'id': ITEM, 'name': 'Camera'}], 'errors': []},
        'photos': ([{'id': 'photo-1', 'title': 'Rack photo', 'primary': True, 'alt': 'Rack shelf photo'}]
                   if entity_id == LOCATION else []),
        'errors': [], 'refreshed_at': '2026-10-07T12:00:00+00:00',
    }


class WorkshopBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'homebox-ui/overlay/lib/workshop-tools.js').read_text().replace('import { mountLabelDesigner, exportReviewedPaper } from "./label-editor.js";\n', 'const mountLabelDesigner=()=>{}; const exportReviewedPaper=()=>{};\n').replace('export function mountWorkshopTools', 'function mountWorkshopTools')
        cls.source += '\nwindow.mountWorkshopTools=mountWorkshopTools;'
        cls.css = (ROOT / 'homebox-ui/overlay/assets/css/workshop.css').read_text()

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True, executable_path='/usr/bin/chromium')
        self.addCleanup(self.browser.close)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('console', lambda message: self.errors.append('console: ' + message.text) if message.type == 'error' else None)
        self.page.set_default_timeout(2500)
        self.page.set_default_navigation_timeout(2500)
        self.fixture=RemoteShelfFixture(os.environ.get('SHELF_CHECKS_FIXTURE_URL'))
        html = '''<!doctype html><meta charset="utf-8"><main id="root" class="workshop-native"><div id="view" tabindex="-1"></div><dialog id="dialog" aria-labelledby="dialog-title"><div><h2 id="dialog-title"></h2><button id="dialog-close">Close</button></div><div id="dialog-body"></div></dialog></main>'''
        self.context.route('https://fixture.invalid/**', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j8XQAAAAASUVORK5CYII=')
        self.context.route('https://fixture.invalid/api/v1/entities/**', lambda route: route.fulfill(status=200, content_type='image/png', body=png))
        self.page.goto('https://fixture.invalid/workshop/map', wait_until='domcontentloaded', timeout=2500)
        self.page.add_style_tag(content=self.css)
        self.page.add_script_tag(content=self.source)
        if not self.page.evaluate('typeof window.mountWorkshopTools === "function"'):
            self.fail('The copied host module did not load: ' + repr(self.errors))
        init = '''
            const context={value:{user:{id:'user-1',name:'Tester'},group:{id:'group-1',name:'Storage Room'},manager:true,identity:'identity-1'}}; window.fixtureContext=context;
            const layout={revision:7,layout:{name:'Old drawing name',width:14,height:20,unit:'ft',approximate:false,objects:[{id:'33333333-3333-4333-8333-333333333333',name:'Old drawing name',kind:'Rack',x:0,y:0,width:3,height:2,location_id:'11111111-1111-4111-8111-111111111111'}]},locations:[{id:'11111111-1111-4111-8111-111111111111',name:'the Cage',parent_id:null,kind:'Rack',code:'1',updated_at:'v1'}],parents:[{id:'11111111-1111-4111-8111-111111111111',name:'the Cage',parent_id:null,kind:'Rack',code:'1',isLocation:true},{id:'22222222-2222-4222-8222-222222222222',name:'Camera',parent_id:'55555555-5555-4555-8555-555555555555',isLocation:false}],counts:{},types:['Rack'],storage_types:['Rack']};
            const locationView=''' + json.dumps(view(LOCATION)) + '''; const itemView=''' + json.dumps(view(ITEM)) + '''; const nestedView=structuredClone(itemView); nestedView.contents=[{id:'22222222-2222-4222-8222-222222222222',name:'Camera',assetId:'CAM-9',condition:'Ready',checkout_blocker:null,checked_out:true,parent:{id:'55555555-5555-4555-8555-555555555555'}}];nestedView.counts={assigned:1,checked_out:1,available:0,needs_attention:0}; window.fixtureViews={locationView,itemView,nestedView}; window.fixtureLayout=layout;
             window.writes=[]; window.navigate=[]; window.apiCalls=[]; window.failViewOnce=false; const pendingStorageKey=()=>`workshop-pending:${window.fixtureContext.value.group.id}:${window.fixtureContext.value.user.id}`;window.fixtureWorkshop={context,refresh:async()=>window.fixtureContext.value,pending:()=>JSON.parse(localStorage.getItem(pendingStorageKey())||'[]'),forget:key=>{const rows=JSON.parse(localStorage.getItem(pendingStorageKey())||'[]');localStorage.setItem(pendingStorageKey(),JSON.stringify(rows.filter(row=>row.key!==key)))},request:async(path,data,identity)=>{window.apiCalls.push([path,data,identity]); const route=path.split('?')[0]; if(route==='workshop'){if(window.deferWorkshopRefresh){window.workshopRefreshStarted=true;await new Promise(resolve=>window.releaseWorkshopRefresh=resolve);window.deferWorkshopRefresh=false;}return structuredClone(window.fixtureLayout);} if(route==='equipment')return structuredClone(window.fixtureSearchEquipment||[{id:'22222222-2222-4222-8222-222222222222',name:'Camera',assetId:'CAM-9',serialNumber:'SN-9',manufacturer:'Northwind',parent:{id:'55555555-5555-4555-8555-555555555555'}}]); if(route==='locations')return structuredClone(window.fixtureSearchLocations||window.fixtureLayout.locations); if(route==='entity')return {entity:{id:'22222222-2222-4222-8222-222222222222',name:'Camera',assetId:'CAM-9',parent:{id:'55555555-5555-4555-8555-555555555555'}},condition:'Ready',blocker:null}; if(route==='loans')return [{entity_id:'22222222-2222-4222-8222-222222222222',borrower:'Private Borrower'}]; if(route==='workshop/view'){if(window.failViewOnce){window.failViewOnce=false;throw new Error('fixture read failure')} if(path.includes('22222222-2222-4222-8222-222222222222'))return structuredClone(path.includes('nested=1')?window.fixtureViews.nestedView:window.fixtureViews.itemView);return structuredClone(window.fixtureViews.locationView);} if(route==='workshop/resolve')return data.code==='UNKNOWN-MFR'?{kind:'unknown',entity_id:null,candidates:[],message:'No unique native record found.'}:{kind:'entity',entity_id:'22222222-2222-4222-8222-222222222222',candidates:[]}; if(route==='recovery')return []; if(route==='operation/status'){const status=window.fixtureOperationStatus||'not_started';return status==='not_started'?{status}:{id:'job-1',status,action:window.fixtureOperationAction||'workshop_shelf_order',native_job:true,...(window.fixtureOperationResult?{result:window.fixtureOperationResult}:{})};} return {};},write:async(path,data,label,subject)=>{window.writes.push([path,data]);if(path==='workshop/save'){window.layoutSaveStarted=true;window.layoutSaveCount=(window.layoutSaveCount||0)+1;if(window.fixtureForceSaveConflict){const error=new Error('fixture revision conflict');error.status=409;throw error;}if(window.deferLayoutSave)await new Promise(resolve=>window.releaseLayoutSave=resolve);const result={revision:data.revision+1,layout:structuredClone(data.layout)};window.fixtureOperationAction='workshop/save';window.fixtureOperationResult={schema_version:2,revision:result.revision,document:structuredClone(data.document)};window.fixtureOperationAction='workshop/save';window.fixtureOperationResult={schema_version:2,revision:result.revision,document:structuredClone(data.document)};window.fixtureLayout.revision=result.revision;window.fixtureLayout.layout=structuredClone(data.layout);window.fixtureLayout.document=structuredClone(data.document);if(window.fixtureLoseSaveResponse)throw new Error('fixture lost save response');return result;}const storageKey='workshop-pending:group-1:user-1';if(path==='workshop/shelf-order'){const rows=JSON.parse(localStorage.getItem(storageKey)||'[]');rows.push({key:data.request_key,path,label,subject,at:'2026-10-07T12:00:00Z'});localStorage.setItem(storageKey,JSON.stringify(rows));if(window.loseOrderResponse)throw new Error('fixture lost response');localStorage.setItem(storageKey,JSON.stringify(rows.filter(row=>row.key!==data.request_key)));}return {id:'order-1',status:'completed',entity_id:data.entity_id};}};window.fixtureNavigate=path=>window.navigate.push(path);window.fixtureNotify=()=>{};window.fixtureSelection={entityId:'11111111-1111-4111-8111-111111111111',drawingId:'33333333-3333-4333-8333-333333333333'};window.mountFixture=()=>window.mountWorkshopTools(document.querySelector('#root'),'workshop',window.fixtureWorkshop,window.fixtureNavigate,window.fixtureNotify,window.fixtureSelection);window.instance=window.mountFixture();
        '''
        self.page.evaluate(init)
        self.page.wait_for_timeout(250)
        if not self.page.locator('#workshop-content, .room-planner').count():
            self.fail('The real Workshop host did not render: ' + repr(self.errors) + ' body=' + self.page.locator('body').inner_text() + ' instance=' + str(self.page.evaluate('typeof window.instance')))

    def test_desktop_dirty_refresh_and_identity(self):
        self.page.get_by_role('button', name='Edit layout').click()
        self.page.get_by_role('button', name='Room settings').click()
        self.page.locator('#dialog[open]').wait_for(state='visible', timeout=1500)
        name = self.page.get_by_label('Room name')
        name.fill('Draft floor')
        self.page.get_by_role('button', name='Apply room changes').click()
        before = self.page.locator('[data-workshop-caption]').inner_text()
        self.page.get_by_role('button', name='Refresh native view').click()
        self.page.wait_for_timeout(50)
        after = self.page.locator('[data-workshop-caption]').inner_text()
        self.assertEqual(before, after)
        self.assertEqual(before, 'Old drawing name')
        self.assertEqual(self.page.evaluate('window.writes'), [])
        self.page.evaluate("async () => { window.failViewOnce=true; await window.instance.refreshWorkshopView('11111111-1111-4111-8111-111111111111', false) }")
        self.assertTrue(self.page.get_by_text('Status unavailable', exact=True).is_visible())
        self.page.evaluate("window.fixtureContext.value={...window.fixtureContext.value,identity:'identity-2'}; window.dispatchEvent(new Event('focus'))")
        self.page.wait_for_timeout(100)
        suspended = json.loads(self.page.evaluate("localStorage.getItem('workshop-draft:group-1:user-1')"))
        self.assertEqual(suspended['identity'], 'identity-1')
        self.assertEqual(self.errors, [])

    def test_desktop_uncertain_reopen(self):
        # The host must expose scoped entry points so Recovery can reopen a
        # committed check without replaying the pending start request.
        self.assertTrue(self.page.evaluate("typeof window.instance.openShelfCheck === 'function'"))
        self.assertTrue(self.page.evaluate("typeof window.instance.recoverShelfCheck === 'function'"))
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        self.install_rooms4_plan({'version':2,'rooms':[{'id':room,'location_id':LOCATION,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[{'id':DRAWING,'name':'Rack','kind':'Rack','x':0,'y':0,'width':3,'height':2,'rotation':0,'location_id':LOCATION}]}]},selected_drawing=DRAWING)
        self.page.get_by_role('button',name='Start shelf check').wait_for(state='visible',timeout=8000)
        self.install_shelf_check_fixture()
        self.page.evaluate("window.loseShelfStartResponse=true")
        self.page.get_by_role('button', name='Start shelf check').click()
        self.page.get_by_text('The start reply was not confirmed.', exact=False).wait_for()
        key=self.page.evaluate("JSON.parse(localStorage.getItem(Object.keys(localStorage).find(key=>key.startsWith('workshop-pending:')))).find(row=>row.path==='workshop/checks/start').key")
        self.assertEqual(self.fixture.check_count(), 1)
        self.page.evaluate("window.instance.dispose(); window.instance=window.mountFixture()")
        self.page.evaluate("window.instance.recoverShelfCheck("+json.dumps(key)+")")
        self.page.get_by_text('Direct contents', exact=True).wait_for()
        self.assertEqual(sum(row['action']=='start' for row in self.fixture.requests),1)
        self.assertEqual(self.fixture.check_count(), 1)
        self.assertEqual(self.errors, [])

    def test_desktop_uncertain_start_recovery_keeps_scope_provenance(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        self.install_rooms4_plan({'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[{'id':DRAWING,'name':'Rack','kind':'Rack','x':0,'y':0,'width':3,'height':2,'rotation':0,'location_id':LOCATION}]}]},selected_drawing=DRAWING)
        self.page.evaluate("""() => {
          window.fixtureShelfStarts=0;
          window.fixtureWorkshop.write=async(path)=>{if(path==='workshop/checks/start'){window.fixtureShelfStarts++;throw Error('lost start reply')}return {}};
          const check={id:'check-recovered',location_id:'11111111-1111-4111-8111-111111111111',state:'completed',can_edit:false,revision:1,started_at:'2026-10-09T12:00:00Z',include_nested:false,groups:{},original_snapshot:{items:[]}};
          window.fixtureWorkshop.request=async(path)=>{if(path==='workshop/checks/request')return {status:'completed',action:'start',result:{id:check.id,location_id:check.location_id}};if(path.startsWith('workshop/checks/get'))return structuredClone(check);if(path.startsWith('workshop/checks/list'))return [structuredClone(check)];return []};
        }""")
        self.page.get_by_role('button',name='Start shelf check').click()
        self.page.get_by_text('The start reply was not confirmed.',exact=False).wait_for()
        row=self.page.evaluate("window.fixtureWorkshop.pending().find(item=>item.path==='workshop/checks/start')")
        self.assertEqual(row['identity'],'identity-1')
        self.assertEqual(row['group_id'],'group-1')
        self.assertEqual(row['user_id'],'user-1')
        self.page.evaluate("window.instance.recoverShelfCheck("+json.dumps(row['key'])+")")
        self.page.get_by_text('Direct contents',exact=True).wait_for()
        self.assertEqual(self.page.evaluate('window.fixtureShelfStarts'),1)

    def test_desktop_successful_start_with_failed_reopen_is_not_recovery(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        self.install_rooms4_plan({'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[{'id':DRAWING,'name':'Rack','kind':'Rack','x':0,'y':0,'width':3,'height':2,'rotation':0,'location_id':LOCATION}]}]},selected_drawing=DRAWING)
        self.page.evaluate("""() => {
          window.fixtureShelfStarts=0;
          window.fixtureWorkshop.write=async(path,data)=>{if(path==='workshop/checks/start'){window.fixtureShelfStarts++;return {id:'check-started',location_id:data.location_id,state:'completed',can_edit:false,revision:1,started_at:'2026-10-09T12:00:00Z',include_nested:false,groups:{},original_snapshot:{items:[]}}}return {}};
          window.fixtureWorkshop.request=async(path)=>{if(path.startsWith('workshop/checks/get'))throw Error('check reopen failed');return []};
        }""")
        self.page.get_by_role('button',name='Start shelf check').click()
        self.page.get_by_role('alert').get_by_text('check reopen failed',exact=False).wait_for()
        self.assertEqual(self.page.evaluate("window.fixtureWorkshop.pending().filter(item=>item.path==='workshop/checks/start')"),[])
        self.assertFalse(self.page.get_by_text('The start reply was not confirmed.',exact=False).count())
        self.assertEqual(self.page.evaluate('window.fixtureShelfStarts'),1)

    def test_desktop_observe_refresh_finish_history(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        self.install_rooms4_plan({'version':2,'rooms':[{'id':room,'location_id':LOCATION,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[{'id':DRAWING,'name':'Rack','kind':'Rack','x':0,'y':0,'width':3,'height':2,'rotation':0,'location_id':LOCATION}]}]},selected_drawing=DRAWING)
        self.page.get_by_role('button',name='Start shelf check').wait_for(state='visible',timeout=8000)
        self.install_shelf_check_fixture()
        self.assertFalse(self.page.get_by_label('Include nested contents').is_checked())
        self.page.get_by_role('button', name='Start shelf check').click()
        self.page.get_by_text('Direct contents', exact=True).wait_for()
        self.assertEqual(self.fixture.check_count(), 1)
        for group in ('Observed here', 'Not observed', 'Checked out', 'Unexpected here'):
            self.assertTrue(self.page.get_by_text(group, exact=True).is_visible(), group)
        self.assertTrue(self.page.get_by_label('Scan or enter asset code').is_visible())
        self.assertTrue(self.page.get_by_label('Visual quantity').is_visible())
        visual=self.page.get_by_label('Visual equipment');visual.select_option(ITEM)
        self.page.get_by_label('Visual quantity').fill('2')
        self.page.get_by_role('button',name='Save visual observation').click()
        self.assertEqual(sum(row['action']=='observe' for row in self.fixture.requests),1)
        self.assertTrue(self.page.get_by_text('Checkout conflict', exact=False).is_visible())
        self.page.get_by_role('button',name='Refresh review').click()
        self.assertTrue(self.page.get_by_text('observed 2',exact=False).is_visible())
        notes=self.page.get_by_label('Observation notes');notes.fill('Observed shelf contents')
        self.page.evaluate('window.confirmMessages=[];window.confirm=message=>{window.confirmMessages.push(message);return false}')
        self.page.get_by_role('button',name='Finish check').click()
        self.assertTrue(self.page.evaluate("window.confirmMessages.some(text=>String(text||'').includes('unsaved edits'))"))
        check_id=self.page.evaluate('window.fixtureLastCheckId')
        self.page.evaluate("async checkId=>{const state=await fetch(window.fixtureEndpoint+'/__fixture__/state').then(response=>response.json());window.fixtureContext.value=state.manager2_context;window.fixtureUserToken='manager2';window.instance.dispose();window.instance=window.mountFixture();await new Promise(resolve=>setTimeout(resolve,100));await window.instance.openShelfCheck('11111111-1111-4111-8111-111111111111',checkId)}",check_id)
        self.page.get_by_role('button',name='Confirm cancellation').wait_for(state='visible')
        self.assertFalse(self.page.get_by_label('Visual equipment').count())
        self.page.evaluate('window.confirm=message=>{window.confirmMessages.push(message);return true}')
        self.page.get_by_role('button',name='Confirm cancellation').click()
        self.page.get_by_text('Cancelled',exact=False).wait_for()
        self.assertEqual(self.fixture.check_count(),1)
        self.assertTrue(any(row['action']=='cancel' for row in self.fixture.requests))
        self.page.evaluate("async()=>{const state=await fetch(window.fixtureEndpoint+'/__fixture__/state').then(response=>response.json());window.fixtureContext.value=state.manager1_context;window.fixtureUserToken='alpha';window.instance.dispose();window.instance=window.mountFixture();await new Promise(resolve=>setTimeout(resolve,100));await window.instance.openShelfCheck('11111111-1111-4111-8111-111111111111',null)}")
        self.page.get_by_role('button',name='Start shelf check').wait_for(state='visible')
        self.page.get_by_role('button',name='Start shelf check').click()
        self.page.get_by_text('Direct contents',exact=True).wait_for()
        self.page.evaluate('window.confirm=()=>true')
        self.page.get_by_role('button',name='Finish check').click()
        self.page.get_by_text('Completed point-in-time comparison',exact=False).wait_for()
        self.assertFalse(self.page.get_by_role('button',name='Finish check').count())
        self.assertEqual(self.fixture.check_count(),2)
        self.assertEqual(self.errors, [])

    def install_local_shelf_check(self):
        self.page.evaluate("""async () => {
          const check={id:'check-local',location_id:'11111111-1111-4111-8111-111111111111',location:{id:'11111111-1111-4111-8111-111111111111',name:'the Cage'},state:'draft',can_edit:true,revision:1,started_at:'2026-10-09T12:00:00Z',include_nested:false,notes:'',review_fingerprint:'fingerprint',original_snapshot:{items:[{id:'22222222-2222-4222-8222-222222222222',name:'Camera',path:[{id:'11111111-1111-4111-8111-111111111111',name:'the Cage'}]}]},groups:{observed_here:[],not_observed:[{entity_id:'22222222-2222-4222-8222-222222222222',name:'Camera',expected_quantity:1,observed_quantity:null}],checked_out:[],unexpected_here:[]}};
          window.localShelfCheck=check;window.localShelfWrites=[];
          window.fixtureWorkshop.request=async(path)=>path.startsWith('workshop/checks/get')?structuredClone(check):path.startsWith('workshop/checks/list')?[structuredClone(check)]:{};
          window.fixtureWorkshop.write=async(path,data)=>{window.localShelfWrites.push([path,data]);return structuredClone(check)};
          await window.instance.openShelfCheck('11111111-1111-4111-8111-111111111111','check-local');
        }""")
        self.page.get_by_text('Direct contents', exact=True).wait_for()

    def test_desktop_shelf_refresh_preserves_unsaved_notes_and_tallies(self):
        self.install_local_shelf_check()
        self.page.get_by_label('Observation notes').fill('still writing this note')
        self.page.get_by_label('Visual equipment').select_option(ITEM)
        self.page.get_by_label('Visual quantity').fill('4')
        self.page.evaluate('window.confirmMessages=[];window.confirm=message=>{window.confirmMessages.push(message);return false}')
        self.page.get_by_role('button', name='Refresh check').click()
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.get_by_label('Observation notes').input_value(), 'still writing this note')
        self.assertEqual(self.page.get_by_label('Visual quantity').input_value(), '4')
        self.assertTrue(self.page.evaluate("window.confirmMessages.some(message=>String(message).includes('unsaved'))"))
        self.page.locator('.shelf-check-history button').click()
        self.assertEqual(self.page.get_by_label('Observation notes').input_value(), 'still writing this note')
        self.assertEqual(self.page.get_by_label('Visual quantity').input_value(), '4')
        self.assertGreaterEqual(self.page.evaluate('window.confirmMessages.length'), 2)
        self.assertEqual(self.page.evaluate('window.localShelfWrites'), [])

    def test_desktop_shelf_notes_block_beforeunload(self):
        self.install_local_shelf_check()
        self.page.get_by_label('Observation notes').fill('leave only after a warning')
        blocked = self.page.evaluate("() => {const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented}")
        self.assertTrue(blocked)

    def test_desktop_shelf_review_shows_inventory_changes_and_pending_operations(self):
        self.install_local_shelf_check()
        self.page.evaluate("""() => {
          window.localShelfCheck.changes=[{kind:'changed',items:[{id:'22222222-2222-4222-8222-222222222222',name:'Camera',before:{quantity:1,path:[{name:'Old shelf'}],custody:'Available'},after:{quantity:2,path:[{name:'New shelf'}],custody:'Checked out'}}]}];
          window.localShelfCheck.pending_operations=[{id:'operation-1',group_id:'group-1',actor_id:'user-1',action:'check_out',request_key:'request-secret',request_hash:'hash-secret',status:'review',created_at:'2026-10-09T12:00:00Z'}];
          window.localShelfCheck.groups.unexpected_here=[{entity_id:'99999999-9999-4999-8999-999999999999',name:'Tripod',expected_quantity:0,observed_quantity:1,original_path:[{name:'Old storage'}],current_path:[{name:'Rack A'}]}];
          window.fixtureWorkshop.request=async path=>path.startsWith('workshop/checks/get')?structuredClone(window.localShelfCheck):[structuredClone(window.localShelfCheck)];
          window.instance.openShelfCheck('11111111-1111-4111-8111-111111111111','check-local');
        }""")
        for evidence in ('Changed inventory', 'Camera', '1', '2', 'Old shelf', 'New shelf',
                         'Pending native operations', 'check out', 'review', 'operation-1',
                         'Old storage', 'Rack A'):
            self.page.get_by_text(evidence, exact=False).first.wait_for()
        text = self.page.locator('main').inner_text()
        self.assertNotIn('request-secret', text)
        self.assertNotIn('hash-secret', text)

    def test_desktop_shelf_tallies_start_blank_and_require_integer(self):
        self.install_local_shelf_check()
        self.assertEqual(self.page.get_by_label('Observed quantity').input_value(), '')
        self.assertEqual(self.page.get_by_label('Visual quantity').input_value(), '')
        self.page.get_by_label('Visual equipment').select_option(ITEM)
        self.page.get_by_role('button', name='Save visual observation').click()
        self.page.get_by_role('alert').get_by_text('Enter a whole number', exact=False).wait_for()
        self.page.get_by_label('Visual quantity').fill('1.5')
        self.page.get_by_role('button', name='Save visual observation').click()
        self.page.get_by_role('alert').get_by_text('Enter a whole number', exact=False).wait_for()
        self.page.get_by_label('Scan or enter asset code').fill('CAM-9')
        self.page.get_by_role('button', name='Resolve code').click()
        self.page.get_by_role('button', name='Save scan observation').click()
        self.page.get_by_role('alert').get_by_text('Enter a whole number', exact=False).wait_for()
        self.page.get_by_label('Observed quantity').fill('2.25')
        self.page.get_by_role('button', name='Save scan observation').click()
        self.page.get_by_role('alert').get_by_text('Enter a whole number', exact=False).wait_for()
        self.assertEqual(self.page.evaluate('window.localShelfWrites'), [])

    def install_shelf_check_fixture(self):
        endpoint=self.fixture.endpoint
        def proxy(route):
            incoming=route.request
            headers=incoming.headers
            data=incoming.post_data.encode() if incoming.post_data else None
            path=incoming.url.split('https://fixture.invalid',1)[-1]
            forwarded=UrlRequest(endpoint+path,data=data,headers={
                'X-Workshop-Identity':headers.get('x-workshop-identity',''),
                'X-Fixture-User':headers.get('x-fixture-user','alpha'),
                'Content-Type':headers.get('content-type','application/json')},method=incoming.method)
            try:
                with urlopen(forwarded,timeout=10) as response: status,body=response.status,response.read()
            except HTTPError as error: status,body=error.code,error.read()
            route.fulfill(status=status,headers={'content-type':'application/json'},body=body)
        self.context.route('https://fixture.invalid/__fixture__/state',proxy)
        self.context.route('https://fixture.invalid/workshop-api/**',proxy)
        self.page.evaluate("""async () => {
          const state=await fetch('/__fixture__/state').then(response=>response.json());
          window.fixtureEndpoint='';window.fixtureUserToken='alpha';window.fixtureContext.value=state.manager1_context;
          window.fixture={check_count:async()=> (await fetch('/__fixture__/state')).json().then(value=>value.check_count)};
          const request=window.fixtureWorkshop.request.bind(window.fixtureWorkshop),write=window.fixtureWorkshop.write.bind(window.fixtureWorkshop);
          const send=async(path,data,identity)=>{const response=await fetch('/workshop-api/'+path,{method:data===undefined?'GET':'POST',headers:{'X-Workshop-Identity':identity||window.fixtureContext.value.identity,'X-Fixture-User':window.fixtureUserToken,...(data===undefined?{}:{'Content-Type':'application/json'})},body:data===undefined?undefined:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Object.assign(new Error(result.error||'Fixture request failed'),{status:response.status});return result};
          window.fixtureWorkshop.request=async(path,data,identity)=>path.startsWith('workshop/checks/')?send(path,data,identity):request(path,data,identity);
          window.fixtureWorkshop.write=async(path,data,label,subject)=>{if(!path.startsWith('workshop/checks/'))return write(path,data,label,subject);const storageKey='workshop-pending:'+window.fixtureContext.value.group.id+':'+window.fixtureContext.value.user.id,rows=JSON.parse(localStorage.getItem(storageKey)||'[]'),row={key:data.request_key,path,label,subject,at:new Date().toISOString(),identity:window.fixtureContext.value.identity,group_id:window.fixtureContext.value.group.id,user_id:window.fixtureContext.value.user.id};rows.push(row);localStorage.setItem(storageKey,JSON.stringify(rows));const result=await send(path,data,window.fixtureContext.value.identity);if(path==='workshop/checks/start')window.fixtureLastCheckId=result.id;if(path==='workshop/checks/start'&&window.loseShelfStartResponse)throw new Error('fixture dropped committed reply');window.fixtureWorkshop.forget(data.request_key);return result};
          window.instance.dispose();window.instance=window.mountFixture();
        }""")
        self.page.get_by_role('button',name='Start shelf check').wait_for(state='visible',timeout=8000)

    def test_recovery_keeps_uncertain_planner_save_for_planner_reconciliation(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Original','width':14,'height':20,'unit':'ft','approximate':False,'objects':[]}]}
        self.install_rooms4_plan(document)
        self.page.evaluate("""() => {
          const key='save-key',draft=structuredClone(window.fixtureLayout.document);draft.rooms[0].name='Saved draft';
          const intent={schema_version:2,revision:7,document:draft,request_key:key};
          localStorage.setItem('workshop-pending:group-1:user-1',JSON.stringify([{key,path:'workshop/save',label:'Save all room changes',subject:'',at:'2026-10-09T12:00:00Z',intent,identity:'identity-1',group_id:'group-1',user_id:'user-1'}]));
          const sessionKey='workshop-room-draft:group-1:user-1:'+sessionStorage.getItem('workshop-room-draft-tab');
          localStorage.setItem(sessionKey,JSON.stringify({identity:'identity-1',group_id:'group-1',user_id:'user-1',revision:7,dirty:true,document:draft,room_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',drawing_id:null,selectedDrawingByRoom:{},undo:{},redo:{},uncertain:{key,revision:7,document:draft}}));
          window.fixtureOperationStatus='completed';window.fixtureOperationAction='workshop/save';window.fixtureOperationResult={schema_version:2,revision:8,document:draft};
        }""")
        self.page.evaluate("""() => { window.instance.dispose(); window.instance=window.mountWorkshopTools(document.querySelector('#root'),'recovery',window.fixtureWorkshop,window.fixtureNavigate,window.fixtureNotify,window.fixtureSelection) }""")
        if not self.page.get_by_role('button',name='Check saved result').count():
            self.fail('Recovery did not show pending planner save: '+self.page.locator('body').inner_text()+' pending='+str(self.page.evaluate('window.fixtureWorkshop.pending()')))
        self.page.get_by_role('button',name='Check saved result').click()
        self.page.get_by_role('button',name='Return to recovery').click()
        self.assertTrue(self.page.evaluate("window.fixtureWorkshop.pending().some(row=>row.path==='workshop/save')"))
        self.page.evaluate("""() => { window.instance.dispose(); window.instance=window.mountWorkshopTools(document.querySelector('#root'),'workshop',window.fixtureWorkshop,window.fixtureNavigate,window.fixtureNotify,window.fixtureSelection) }""")
        self.page.get_by_role('button',name='Check save status').click()
        self.page.get_by_text('Saved draft',exact=True).wait_for()
        self.assertEqual(self.page.evaluate("window.fixtureWorkshop.pending().filter(row=>row.path==='workshop/save').length"),0)
        self.assertEqual(self.errors,[])

    def test_planner_exposes_custom_drawing_styles_and_layers(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        self.install_rooms4_plan({'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[{'id':DRAWING,'name':'Rack','kind':'Rack','x':0,'y':0,'width':3,'height':2,'rotation':0,'location_id':LOCATION}]}]},selected_drawing=DRAWING)
        self.page.get_by_role('button', name='Edit', exact=True).click()
        palette = self.page.get_by_role('region', name='Object palette')
        for kind in ('Wall', 'Bin', 'Crate', 'Drawer', 'Misc', 'Custom'):
            self.assertTrue(palette.get_by_role('button', name=kind, exact=True).count(), kind)
        self.page.locator('[data-workshop-drawing]').click()
        inspector = self.page.locator('.planner-inspector')
        for label in ('Drawing color', 'Drawing opacity', 'Drawing layer'):
            self.assertTrue(inspector.get_by_label(label).count(), label)
        inspector.get_by_label('Drawing color').fill('#336699')
        inspector.get_by_label('Drawing opacity').fill('0.65')
        inspector.get_by_label('Drawing layer').select_option('below')
        self.page.get_by_role('button',name='Save all room changes').click()
        saved=self.page.evaluate('window.writes.at(-1)[1].document.rooms[0].objects[0]')
        self.assertEqual((saved['color'],saved['opacity'],saved['layer']),('#336699',0.65,'below'))
        self.assertEqual(self.errors,[])


    def test_native_rename_refresh_keeps_geometry_and_updates_paths(self):
        self.page.get_by_role('button', name='Edit layout').click()
        self.page.get_by_role('button', name='Room settings').click()
        self.page.locator('#dialog[open]').wait_for(state='visible', timeout=1500)
        self.page.get_by_label('Room name').fill('Draft floor')
        self.page.get_by_role('button', name='Apply room changes').click()
        self.page.get_by_role('button', name='Edit drawing properties').click()
        self.page.get_by_label('Width in feet').fill('4')
        self.page.get_by_label('Position from left').fill('2.5')
        self.page.get_by_role('button', name='Apply drawing changes').click()
        before = self.page.locator('[data-workshop-caption]').inner_text()
        self.page.evaluate("""async () => {
          const id='11111111-1111-4111-8111-111111111111';
          window.fixtureLayout.locations[0].name='Storage Room renamed';
          delete window.fixtureLayout.locations[0].code;
          window.fixtureLayout.parents[0].name='Storage Room renamed';
          delete window.fixtureLayout.parents[0].code;
          window.fixtureLayout.revision=99;
          window.fixtureViews.locationView.path[0].name='Storage Room renamed';
          await window.instance.refreshWorkshopView(id,false);
        }""")
        self.assertEqual(before, 'Old drawing name')
        self.assertEqual(self.page.locator('[data-workshop-caption]').inner_text(), before)
        self.assertIn('Storage Room renamed', self.page.locator('.map').text_content())
        self.assertTrue(self.page.get_by_role('link', name='Storage Room renamed', exact=True).count())
        self.assertTrue(self.page.get_by_text('Assigned storage: Storage Room renamed', exact=False).count())
        self.assertEqual(self.page.evaluate('window.writes'), [])
        self.page.get_by_role('button', name='Save layout changes').click()
        saved = self.page.evaluate('window.writes[0][1]')
        self.assertEqual(saved['revision'], 7)
        self.assertEqual(saved['layout']['name'], 'Draft floor')
        self.assertEqual(saved['layout']['objects'][0], {
            'id': DRAWING, 'name': 'Old drawing name', 'kind': 'Rack', 'x': 2.5, 'y': 0,
            'width': 4, 'height': 2, 'location_id': LOCATION,
        })
        self.assertEqual(self.errors, [])

    def test_search_rows_do_not_replace_normalized_storage_hierarchy(self):
        self.page.evaluate("""() => {
          const cage='66666666-6666-4666-8666-666666666666';
          window.fixtureLayout.parents=[
            {id:'""" + LOCATION + """',name:'Storage Room',parent_id:null,isLocation:true},
            {id:cage,name:'the Cage',parent_id:'""" + LOCATION + """',isLocation:true},
            {id:'""" + RACK + """',name:'Rack 1',parent_id:cage,isLocation:true},
            {id:'""" + SHELF + """',name:'Rack 1-A',parent_id:'""" + RACK + """',isLocation:true},
            {id:'""" + ITEM + """',name:'Camera',parent_id:'""" + SHELF + """',isLocation:false}
          ];
          window.fixtureLayout.locations=window.fixtureLayout.parents.filter(row=>row.isLocation);
          window.fixtureSearchLocations=[{id:'""" + SHELF + """',name:'Rack 1-A',assetId:'1-A',entityType:{isLocation:true},parent:{id:'""" + RACK + """'}}];
          window.instance.dispose();
          window.instance=window.mountFixture();
        }""")
        self.assertTrue(self.page.get_by_role('link', name='Storage Room / the Cage / Rack 1 / Rack 1-A', exact=True).count())
        search = self.page.get_by_label('Search native equipment and storage')
        search.fill('Rack 1-A')
        result = self.page.locator('.workshop-search-results button').filter(has_text='1-A')
        result.click()
        self.assertTrue(self.page.get_by_role('link', name='Storage Room / the Cage / Rack 1 / Rack 1-A', exact=True).count())
        self.assertTrue(self.page.get_by_role('link', name='Storage Room / the Cage / Rack 1 / Rack 1-A / Camera', exact=True).count())
        self.assertEqual(self.page.evaluate('window.writes'), [])
        self.assertEqual(self.errors, [])

    def test_search_results_render_after_refresh_replaces_search_container(self):
        self.page.evaluate("""() => {
          const request=window.fixtureWorkshop.request;
          window.fixtureWorkshop.request=async (path,data,identity)=>{
            if(path.startsWith('workshop/view')&&window.deferFixtureView){
              window.fixtureViewStarted=true;
              await new Promise(resolve=>window.releaseFixtureView=resolve);
              window.deferFixtureView=false;
            }
            if(path==='locations'&&window.deferFixtureSearch){
              window.fixtureSearchStarted=true;
              await new Promise(resolve=>window.releaseFixtureSearch=resolve);
              window.deferFixtureSearch=false;
            }
            return request(path,data,identity);
          };
          window.deferFixtureView=true;
          window.deferFixtureSearch=true;
          window.manualRefresh=window.instance.refreshWorkshopView('11111111-1111-4111-8111-111111111111',false);
        }""")
        self.page.wait_for_function('window.fixtureViewStarted===true')
        self.page.get_by_label('Search native equipment and storage').fill('CAM-9')
        self.page.wait_for_function('window.fixtureSearchStarted===true')
        self.page.evaluate('window.releaseFixtureView()')
        self.page.evaluate('window.manualRefresh')
        self.assertEqual(self.page.get_by_label('Search native equipment and storage').input_value(), 'CAM-9')
        self.page.evaluate('window.releaseFixtureSearch()')
        result = self.page.locator('.workshop-search-results button').filter(has_text='CAM-9')
        result.wait_for(state='visible')
        self.assertIn('Camera', result.inner_text())
        self.assertEqual(self.page.evaluate('window.writes'), [])
        self.assertEqual(self.errors, [])

    def test_search_response_during_save_waits_to_render_enabled_results(self):
        self.page.get_by_role('button', name='Edit layout').click()
        self.page.get_by_role('button', name='Room settings').click()
        self.page.get_by_label('Room name').fill('Busy search draft')
        self.page.get_by_role('button', name='Apply room changes').click()
        self.page.evaluate("""() => {
          const request=window.fixtureWorkshop.request;
          window.fixtureWorkshop.request=async (path,data,identity)=>{
            const result=path==='locations'&&window.deferFixtureSearch
              ? (window.fixtureSearchStarted=true,await new Promise(resolve=>window.releaseFixtureSearch=resolve),window.deferFixtureSearch=false,await request(path,data,identity))
              : await request(path,data,identity);
            if(path==='locations')window.fixtureSearchResponseReturned=true;
            return result;
          };
          window.deferFixtureSearch=true;
          window.deferLayoutSave=true;
        }""")
        self.page.get_by_label('Search native equipment and storage').fill('CAM-9')
        self.page.wait_for_function('window.fixtureSearchStarted===true')
        self.page.get_by_role('button', name='Save layout changes').click()
        self.page.wait_for_function('window.layoutSaveCount===1')
        self.page.evaluate('window.releaseFixtureSearch()')
        self.page.wait_for_function('window.fixtureSearchResponseReturned===true')
        self.page.wait_for_timeout(50)
        self.assertTrue(self.page.get_by_role('button', name='Save layout changes', exact=True).is_disabled())
        self.assertEqual(self.page.locator('.workshop-search-results button').count(), 0)
        self.assertEqual(self.page.evaluate('window.writes.length'), 1)
        self.page.evaluate('window.releaseLayoutSave()')
        self.page.get_by_role('button', name='Layout saved', exact=True).wait_for()
        self.page.locator('.workshop-search-results button').filter(has_text='CAM-9').wait_for(state='visible')
        self.assertEqual(self.page.evaluate('window.writes.length'), 1)
        self.assertEqual(self.errors, [])

    def test_stale_owner_search_response_cannot_replace_current_results(self):
        self.page.evaluate("""() => {
          const request=window.fixtureWorkshop.request;
          window.fixtureWorkshop.request=async (path,data,identity)=>{
            if(path==='locations'&&window.deferFirstSearch&&!window.fixtureSearchStarted){
              window.fixtureSearchStarted=true;
              await new Promise(resolve=>window.releaseFirstSearch=resolve);
            }
            return request(path,data,identity);
          };
          window.deferFirstSearch=true;
        }""")
        search = self.page.get_by_label('Search native equipment and storage')
        search.fill('CAM-9')
        self.page.wait_for_function('window.fixtureSearchStarted===true')
        self.page.evaluate("""() => {
          window.fixtureContext.value.identity='identity-2';
          window.fixtureSearchEquipment=[{id:'88888888-8888-4888-8888-888888888888',name:'Fresh owner asset',assetId:'FRESH-2'}];
          window.fixtureSearchLocations=[];
        }""")
        search.fill('Fresh owner')
        fresh = self.page.locator('.workshop-search-results button').filter(has_text='FRESH-2')
        fresh.wait_for(state='visible')
        self.page.evaluate('window.releaseFirstSearch()')
        self.assertTrue(fresh.is_visible())
        search.fill('CAM-9')
        self.page.get_by_text('No native records match.', exact=False).wait_for(state='visible')
        self.assertEqual(self.page.locator('.workshop-search-results button').filter(has_text='CAM-9').count(), 0)
        identities = [row[2] for row in self.page.evaluate('window.apiCalls') if row[0] in ('equipment','locations')]
        self.assertIn('identity-2', identities)
        self.assertEqual(self.errors, [])

    def test_stale_owner_search_failure_cannot_clear_current_results(self):
        self.page.evaluate("""() => {
          const request=window.fixtureWorkshop.request;
          window.fixtureWorkshop.request=async (path,data,identity)=>{
            if(path==='locations'&&window.deferFirstSearch&&!window.fixtureSearchStarted){
              window.fixtureSearchStarted=true;
              await new Promise(resolve=>window.releaseFirstSearch=resolve);
              throw new Error('stale search failure');
            }
            return request(path,data,identity);
          };
          window.deferFirstSearch=true;
        }""")
        search = self.page.get_by_label('Search native equipment and storage')
        search.fill('CAM-9')
        self.page.wait_for_function('window.fixtureSearchStarted===true')
        self.page.evaluate("""() => {
          window.fixtureContext.value.identity='identity-2';
          window.fixtureSearchEquipment=[{id:'88888888-8888-4888-8888-888888888888',name:'Fresh owner asset',assetId:'FRESH-2'}];
          window.fixtureSearchLocations=[];
        }""")
        search.fill('Fresh owner')
        fresh = self.page.locator('.workshop-search-results button').filter(has_text='FRESH-2')
        fresh.wait_for(state='visible')
        self.page.evaluate('window.releaseFirstSearch()')
        search.fill('Fresh owner')
        self.assertTrue(fresh.is_visible())
        self.assertEqual(self.page.locator('.workshop-search-results button').filter(has_text='CAM-9').count(), 0)
        self.assertEqual(self.errors, [])

    def test_enter_resolution_finishing_after_dispose_cannot_navigate(self):
        self.page.evaluate("""() => {
          const request=window.fixtureWorkshop.request;
          window.fixtureWorkshop.request=async (path,data,identity)=>{
            if(path==='workshop/resolve'&&window.deferFixtureResolve){
              window.fixtureResolveStarted=true;
              await new Promise(resolve=>window.releaseFixtureResolve=resolve);
              window.deferFixtureResolve=false;
            }
            return request(path,data,identity);
          };
          window.deferFixtureResolve=true;
        }""")
        search = self.page.get_by_label('Search native equipment and storage')
        search.fill('CAM-9')
        search.press('Enter')
        self.page.wait_for_function('window.fixtureResolveStarted===true')
        self.page.evaluate('window.instance.dispose(); window.instance=window.mountFixture()')
        self.page.evaluate('window.releaseFixtureResolve()')
        self.page.wait_for_timeout(50)
        self.assertEqual(self.page.evaluate('window.navigate'), [])
        self.assertTrue(self.page.get_by_label('Search native equipment and storage').is_visible())
        self.assertEqual(self.errors, [])

    def test_new_query_invalidates_held_enter_resolution(self):
        self.page.evaluate("""() => {
          const request=window.fixtureWorkshop.request;
          window.fixtureWorkshop.request=async (path,data,identity)=>{
            if(path==='workshop/resolve'&&window.deferFixtureResolve){
              window.fixtureResolveStarted=true;
              await new Promise(resolve=>window.releaseFixtureResolve=resolve);
              window.deferFixtureResolve=false;
            }
            return request(path,data,identity);
          };
          window.deferFixtureResolve=true;
        }""")
        search = self.page.get_by_label('Search native equipment and storage')
        search.fill('CAM-9')
        search.press('Enter')
        self.page.wait_for_function('window.fixtureResolveStarted===true')
        self.page.evaluate("""() => {
          window.selectionUpdate=window.instance.updateWorkshopSelection({
            entityId:'55555555-5555-4555-8555-555555555555',drawingId:null,roomId:null
          });
        }""")
        self.page.evaluate('window.selectionUpdate')
        self.page.evaluate('window.releaseFixtureResolve()')
        self.page.wait_for_timeout(50)
        self.assertEqual(self.page.evaluate('window.navigate'), [])
        self.assertEqual(self.page.evaluate('window.writes'), [])
        self.assertEqual(self.errors, [])

    def test_unknown_enter_does_not_cache_an_empty_inventory_result(self):
        self.page.evaluate("""() => {
          const request=window.fixtureWorkshop.request;
          window.fixtureWorkshop.request=async (path,data,identity)=>{
            if(path==='locations'&&!window.fixtureSearchStarted){
              window.fixtureSearchStarted=true;
              await new Promise(resolve=>window.releaseFixtureSearch=resolve);
            }
            return request(path,data,identity);
          };
        }""")
        search = self.page.get_by_label('Search native equipment and storage')
        search.fill('UNKNOWN-MFR')
        self.page.wait_for_function('window.fixtureSearchStarted===true')
        search.press('Enter')
        self.page.get_by_text('No unique native record found.', exact=False).wait_for(state='visible')
        self.page.evaluate('window.releaseFixtureSearch()')
        search.fill('CAM-9')
        self.page.locator('.workshop-search-results button').filter(has_text='CAM-9').wait_for(state='visible')
        self.assertEqual(self.errors, [])

    def test_disposed_pending_search_cannot_clear_remounted_instance_results(self):
        self.page.get_by_role('button', name='Edit layout').click()
        self.page.get_by_role('button', name='Room settings').click()
        self.page.get_by_label('Room name').fill('Old instance draft')
        self.page.get_by_role('button', name='Apply room changes').click()
        self.page.evaluate("""() => {
          const request=window.fixtureWorkshop.request;
          window.fixtureWorkshop.request=async (path,data,identity)=>{
            if(path==='locations'&&window.deferOldSearch){
              window.oldSearchStarted=true;
              await new Promise(resolve=>window.releaseOldSearch=resolve);
              window.deferOldSearch=false;
            }
            const result=await request(path,data,identity);
            if(path==='locations'&&window.oldSearchStarted)window.oldSearchResponseReturned=true;
            return result;
          };
          window.deferOldSearch=true;
          window.deferLayoutSave=true;
        }""")
        self.page.get_by_label('Search native equipment and storage').fill('CAM-9')
        self.page.wait_for_function('window.oldSearchStarted===true')
        self.page.get_by_role('button', name='Save layout changes').click()
        self.page.wait_for_function('window.layoutSaveCount===1')
        self.page.evaluate('window.releaseOldSearch()')
        self.page.wait_for_function('window.oldSearchResponseReturned===true')
        self.page.wait_for_timeout(50)
        self.page.evaluate("""() => {
          window.instance.dispose();
          window.fixtureSearchEquipment=[{id:'99999999-9999-4999-8999-999999999999',name:'Remounted asset',assetId:'NEW-9'}];
          window.fixtureSearchLocations=[];
          window.instance=window.mountFixture();
        }""")
        search = self.page.get_by_label('Search native equipment and storage')
        search.fill('NEW-9')
        fresh = self.page.locator('.workshop-search-results button').filter(has_text='NEW-9')
        fresh.wait_for(state='visible')
        self.page.evaluate('window.releaseLayoutSave()')
        self.page.wait_for_timeout(50)
        self.assertTrue(fresh.is_visible())
        self.assertEqual(self.page.locator('.workshop-search-results button').filter(has_text='CAM-9').count(), 0)
        self.assertEqual(self.errors, [])

    def test_new_query_wins_over_held_search_navigation(self):
        self.page.evaluate("""() => {
          window.instance.dispose();
          window.fixtureNavigate=async path=>{
            window.navigate.push(path);
            window.fixtureNavigationStarted=true;
            await new Promise(resolve=>window.releaseFixtureNavigation=resolve);
          };
          window.instance=window.mountFixture();
        }""")
        self.page.get_by_label('Search native equipment and storage').fill('CAM-9')
        self.page.locator('.workshop-search-results button').filter(has_text='CAM-9').click()
        self.page.wait_for_function('window.fixtureNavigationStarted===true')
        self.page.evaluate("""() => {
          window.selectionUpdate=window.instance.updateWorkshopSelection({
            entityId:'55555555-5555-4555-8555-555555555555',drawingId:null,roomId:null
          });
        }""")
        self.page.evaluate('window.selectionUpdate')
        self.page.evaluate('window.releaseFixtureNavigation()')
        self.page.wait_for_timeout(50)
        views = [row[0] for row in self.page.evaluate('window.apiCalls') if row[0].startswith('workshop/view')]
        self.assertTrue(any('55555555-5555-4555-8555-555555555555' in path for path in views))
        self.assertFalse(any('22222222-2222-4222-8222-222222222222' in path for path in views))
        self.assertEqual(self.page.evaluate('window.writes'), [])
        self.assertEqual(self.errors, [])

    def test_disposed_held_search_navigation_cannot_repaint_remounted_page(self):
        self.page.evaluate("""() => {
          window.instance.dispose();
          window.fixtureNavigate=async path=>{
            window.navigate.push(path);
            window.fixtureNavigationStarted=true;
            await new Promise(resolve=>window.releaseFixtureNavigation=resolve);
          };
          window.instance=window.mountFixture();
        }""")
        self.page.get_by_label('Search native equipment and storage').fill('CAM-9')
        self.page.locator('.workshop-search-results button').filter(has_text='CAM-9').click()
        self.page.wait_for_function('window.fixtureNavigationStarted===true')
        self.page.evaluate("""() => {
          window.instance.dispose();
          window.fixtureSearchEquipment=[{id:'99999999-9999-4999-8999-999999999999',name:'Remounted asset',assetId:'NEW-9'}];
          window.fixtureSearchLocations=[];
          window.instance=window.mountFixture();
        }""")
        search = self.page.get_by_label('Search native equipment and storage')
        search.fill('NEW-9')
        fresh = self.page.locator('.workshop-search-results button').filter(has_text='NEW-9')
        fresh.wait_for(state='visible')
        self.page.evaluate('window.releaseFixtureNavigation()')
        self.page.wait_for_timeout(50)
        self.assertTrue(fresh.is_visible())
        self.assertEqual(self.page.locator('.workshop-search-results button').filter(has_text='CAM-9').count(), 0)
        self.assertEqual(self.errors, [])

    def test_empty_layout_keeps_setup_and_safe_browse_controls(self):
        self.page.evaluate("""() => {
          window.instance.dispose();
          window.fixtureLayout.layout=null;
          window.instance=window.mountFixture();
        }""")
        create = self.page.get_by_role('button', name='Create empty room')
        create.wait_for(state='visible')
        self.page.get_by_label('Equipment filter').select_option('attention')
        self.page.get_by_role('checkbox', name='Show status overlays on map').check()
        self.assertTrue(create.is_visible())
        create.click()
        self.page.get_by_role('button', name='Edit layout').wait_for(state='visible')
        self.assertFalse(self.page.get_by_role('button', name='Create empty room').count())
        self.assertTrue(self.page.get_by_role('heading', name='Workshop & storage', exact=True).is_visible())
        self.page.get_by_role('button', name='Edit layout').click()
        self.page.get_by_role('button', name='Room settings').click()
        self.page.get_by_label('Room name').fill('Created room draft')
        self.page.get_by_role('button', name='Apply room changes').click()
        self.page.get_by_role('button', name='Add drawing object').click()
        self.page.get_by_label('Object name').fill('Fixture rack')
        self.page.get_by_role('button', name='Apply drawing changes').click()
        self.page.get_by_role('button', name='Refresh native view').click()
        self.page.get_by_role('button', name='Save layout changes').wait_for(state='visible')
        self.assertEqual(self.page.locator('.map + p').inner_text(), 'Created room draft · 13.5 × 21 ft · approximate')
        self.assertTrue(self.page.get_by_text('Fixture rack', exact=True).count())
        self.assertFalse(self.page.get_by_role('button', name='Create empty room').count())
        self.assertEqual(self.page.evaluate('window.writes'), [])
        self.assertEqual(self.errors, [])

    def test_shelf_order_recovery_uses_saved_action_and_never_reposts(self):
        self.page.evaluate('window.loseOrderResponse=true')
        self.page.get_by_role('button', name='Review shelf order').click()
        self.page.get_by_role('button', name='Confirm shelf order').click()
        self.page.get_by_text('fixture lost response').wait_for()
        pending = json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:group-1:user-1')"))
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['path'], 'workshop/shelf-order')
        self.assertEqual(pending[0]['subject'], LOCATION)
        request_key = pending[0]['key']
        order_marker = json.loads(self.page.evaluate("localStorage.getItem('workshop-order:group-1:user-1:11111111-1111-4111-8111-111111111111')"))
        self.assertEqual(order_marker['request_key'], request_key)
        self.assertEqual(order_marker['status'], 'pending')
        self.page.get_by_role('button', name='Close').click()
        self.page.get_by_role('button', name='Review shelf order').click()
        self.page.get_by_role('button', name='Check saved order result').click()
        self.assertIn(request_key, self.page.locator('#dialog-body').inner_text())
        self.assertTrue(self.page.get_by_text('not_started', exact=False).is_visible())
        self.page.get_by_role('button', name='Acknowledge no operation started').click()
        self.assertEqual(json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:group-1:user-1')")), [])
        self.assertIsNone(self.page.evaluate("localStorage.getItem('workshop-order:group-1:user-1:11111111-1111-4111-8111-111111111111')"))
        self.assertEqual(len(self.page.evaluate('window.writes')), 1)
        status_calls = [call for call in self.page.evaluate('window.apiCalls') if call[0]=='operation/status']
        self.assertEqual(len(status_calls), 1)
        self.assertEqual(status_calls[0][1], {'request_key': request_key})
        self.assertEqual(status_calls[0][2], 'identity-1')

    def test_shelf_order_completed_recovery_clears_matching_request_without_replay(self):
        self.page.evaluate("window.loseOrderResponse=true; window.fixtureOperationStatus='completed'")
        self.page.get_by_role('button', name='Review shelf order').click()
        self.page.get_by_role('button', name='Confirm shelf order').click()
        self.page.get_by_text('fixture lost response').wait_for()
        before = json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:group-1:user-1')"))
        request_key = before[0]['key']
        self.page.get_by_role('button', name='Close').click()
        self.page.get_by_role('button', name='Review shelf order').click()
        self.page.get_by_role('button', name='Check saved order result').click()
        self.assertTrue(self.page.get_by_text('The saved outcome is confirmed. It will not be resubmitted.', exact=True).is_visible())
        self.assertEqual(json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:group-1:user-1')")), [])
        self.assertIsNone(self.page.evaluate("localStorage.getItem('workshop-order:group-1:user-1:11111111-1111-4111-8111-111111111111')"))
        self.assertEqual(len(self.page.evaluate('window.writes')), 1)
        self.assertEqual(len([call for call in self.page.evaluate('window.apiCalls') if call[0]=='operation/status' and call[1]=={'request_key':request_key}]), 1)

    def test_shelf_order_wrong_terminal_action_stays_locked(self):
        self.page.evaluate("window.loseOrderResponse=true; window.fixtureOperationStatus='completed'; window.fixtureOperationAction='print_label'")
        self.page.get_by_role('button', name='Review shelf order').click()
        self.page.get_by_role('button', name='Confirm shelf order').click()
        self.page.get_by_text('fixture lost response').wait_for()
        pending = json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:group-1:user-1')"))
        request_key = pending[0]['key']
        self.page.get_by_role('button', name='Close').click()
        self.page.get_by_role('button', name='Review shelf order').click()
        self.page.get_by_role('button', name='Check saved order result').click()
        self.assertTrue(self.page.get_by_text('The returned status does not match this saved shelf-order request. It remains locked for inspection.', exact=True).is_visible())
        self.assertEqual(json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:group-1:user-1')")), pending)
        self.assertEqual(json.loads(self.page.evaluate("localStorage.getItem('workshop-order:group-1:user-1:11111111-1111-4111-8111-111111111111')"))['request_key'], request_key)
        self.assertEqual(len(self.page.evaluate('window.writes')), 1)

    def test_status_overlay_is_scoped_to_the_selected_native_drawing(self):
        self.page.evaluate("""() => {
          window.fixtureViews.locationView.contents[0].condition='Broken';
          window.fixtureViews.locationView.counts.needs_attention=1;
          window.fixtureLayout.layout.objects.push({id:'88888888-8888-4888-8888-888888888888',name:'Unrelated shelf',kind:'Shelf',x:5,y:0,width:2,height:1,location_id:'99999999-9999-4999-8999-999999999999'});
          window.instance.dispose();
          window.instance=window.mountFixture();
        }""")
        self.page.locator('.map g rect').nth(1).wait_for(state='attached')
        self.page.get_by_role('checkbox', name='Show status overlays on map').check()
        fills = self.page.locator('.map g rect').evaluate_all('(nodes)=>nodes.map(node=>node.getAttribute("fill"))')
        self.assertIn('--destructive', fills[0])
        self.assertNotIn('--destructive', fills[1])
        self.assertTrue(self.page.get_by_text('Status overlay coloring is limited to the selected map area.', exact=True).is_visible())
        self.assertEqual(self.errors, [])

    def test_rooms4_status_overlay_toggles_selected_scope_without_editing_plan(self):
        self.page.evaluate("""() => {
          const room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
          const duplicate='77777777-7777-4777-8777-777777777777',unrelated='88888888-8888-4888-8888-888888888888';
          window.fixtureViews.locationView.contents[0].condition='Broken';
          window.fixtureViews.locationView.counts.needs_attention=1;
          window.fixtureViews.locationView.selection.matches=[
            {room_id:room,drawing_id:'33333333-3333-4333-8333-333333333333',location_id:'11111111-1111-4111-8111-111111111111'},
            {room_id:room,drawing_id:duplicate,location_id:'11111111-1111-4111-8111-111111111111'}
          ];
          window.fixtureViews.itemView.selection_status={condition:'Broken',checked_out:false,blocker:null};
          window.fixtureViews.itemView.selection.matches=window.fixtureViews.locationView.selection.matches;
          window.fixtureLayout={revision:7,document:{version:2,rooms:[{id:room,location_id:null,name:'Main',width:14,height:20,unit:'ft',approximate:false,objects:[
            {id:'33333333-3333-4333-8333-333333333333',name:'Rack 1',kind:'Rack',x:0,y:0,width:3,height:2,rotation:0,location_id:'11111111-1111-4111-8111-111111111111'},
            {id:duplicate,name:'Duplicate rack drawing',kind:'Rack',x:3.5,y:0,width:3,height:2,rotation:0,location_id:'11111111-1111-4111-8111-111111111111'},
            {id:unrelated,name:'Unrelated shelf',kind:'Shelf',x:5,y:0,width:2,height:1,rotation:0,location_id:'99999999-9999-4999-8999-999999999999'}
          ]}]},locations:window.fixtureLayout?.locations||[{id:'11111111-1111-4111-8111-111111111111',name:'the Cage',parent_id:null,kind:'Rack',code:'1',updated_at:'v1'}],parents:window.fixtureLayout?.parents||[],counts:{},types:['Rack'],storage_types:['Rack']};
          window.instance.dispose(); window.instance=window.mountFixture();
        }""")
        self.page.get_by_text('Show wider native coverage and search', exact=True).click()
        overlay = self.page.get_by_role('checkbox', name='Show status overlays on map')
        self.assertFalse(overlay.is_checked())
        shapes = self.page.locator('[data-workshop-drawing] rect')
        shapes.nth(1).wait_for(state='attached')
        original_fills = shapes.evaluate_all('(nodes)=>nodes.map(node=>node.getAttribute("fill"))')
        session = self.page.evaluate("""() => {const key=Object.keys(localStorage).find(k=>k.startsWith('workshop-room-draft:'));return JSON.parse(localStorage.getItem(key))}""")
        overlay.evaluate('(el)=>{el.checked=true;el.dispatchEvent(new Event("change",{bubbles:true}))}')
        on_fills = shapes.evaluate_all('(nodes)=>nodes.map(node=>node.getAttribute("fill"))')
        self.assertIn('--destructive', on_fills[0])
        self.assertNotIn('--destructive', on_fills[1],'an unselected drawing for the same native target must stay neutral')
        self.assertNotIn('--destructive', on_fills[2])
        self.page.get_by_text('Show wider native coverage and search', exact=True).click()
        self.assertTrue(self.page.get_by_text('Status overlay coloring is limited to the selected map area.', exact=True).is_visible())
        self.page.get_by_role('checkbox', name='Show status overlays on map').evaluate('(el)=>{el.checked=false;el.dispatchEvent(new Event("change",{bubbles:true}))}')
        off_fills = shapes.evaluate_all('(nodes)=>nodes.map(node=>node.getAttribute("fill"))')
        self.assertEqual(off_fills, original_fills)
        after = self.page.evaluate("""() => {const key=Object.keys(localStorage).find(k=>k.startsWith('workshop-room-draft:'));return JSON.parse(localStorage.getItem(key))}""")
        self.assertEqual(after['document'], session['document'])
        self.assertEqual(after['revision'], 7)

        self.page.evaluate("""() => {
          window.fixtureSelection={entityId:'22222222-2222-4222-8222-222222222222',drawingId:'33333333-3333-4333-8333-333333333333',roomId:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'};
          window.instance.dispose();window.instance=window.mountFixture();
        }""")
        self.page.get_by_text('Show wider native coverage and search',exact=True).click()
        self.page.get_by_role('checkbox',name='Show status overlays on map').evaluate('(el)=>{el.checked=true;el.dispatchEvent(new Event("change",{bubbles:true}))}')
        item_fills=self.page.locator('[data-workshop-drawing] rect').evaluate_all('(nodes)=>nodes.map(node=>node.getAttribute("fill"))')
        self.assertIn('--destructive',item_fills[0],'the selected item representation must color its matched drawing')
        self.assertNotIn('--destructive',item_fills[1],'duplicate exact-target drawing must remain neutral')
        self.assertNotIn('--destructive',item_fills[2])
        self.assertEqual(self.errors, [])

    def install_rooms4_plan(self, document, revision=7, *, selected_drawing=None):
        self.page.evaluate("""({document,revision,selectedDrawing}) => {
          const room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
          window.fixtureLayout={revision,document,layout:null,
            locations:[{id:'11111111-1111-4111-8111-111111111111',name:'the Cage',parent_id:null,kind:'Rack',code:'1',updated_at:'v1'}],
            parents:[{id:'11111111-1111-4111-8111-111111111111',name:'the Cage',parent_id:null,kind:'Rack',code:'1',isLocation:true}],
            counts:{},types:['Rack'],storage_types:['Rack']};
          window.fixtureSelection={entityId:selectedDrawing?'11111111-1111-4111-8111-111111111111':null,drawingId:selectedDrawing,roomId:room};
          window.instance.dispose(); window.instance=window.mountFixture();
        }""", {'document': document, 'revision': revision, 'selectedDrawing': selected_drawing})
        self.page.locator('.planner-svg').wait_for(state='visible')

    def test_rooms4_clean_refresh_clears_only_stale_room_history(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Original','width':14,'height':20,'unit':'ft','approximate':False,'objects':[]}]}
        self.install_rooms4_plan(document)
        self.page.get_by_role('button',name='Edit',exact=True).click()
        self.page.get_by_label('Room title').fill('Draft')
        self.page.get_by_role('button',name='Apply room changes').click()
        undo=self.page.get_by_role('button',name='Undo',exact=True)
        redo=self.page.get_by_role('button',name='Redo',exact=True)
        undo.click()
        self.assertEqual(self.page.get_by_label('Room title').input_value(),'Original')
        self.assertTrue(redo.is_enabled())
        self.page.evaluate('window.instance.refreshWorkshopView(null,false)')
        self.assertTrue(redo.is_enabled(),'same-revision refresh must preserve Redo')
        redo.click()
        self.assertEqual(self.page.get_by_label('Room title').input_value(),'Draft')
        undo.click()
        self.assertEqual(self.page.get_by_label('Room title').input_value(),'Original')

        remote={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Remote saved','width':14,'height':20,'unit':'ft','approximate':False,'objects':[]}]}
        self.page.evaluate('(document)=>{window.fixtureLayout.revision=8;window.fixtureLayout.document=document}',remote)
        self.page.evaluate('window.instance.refreshWorkshopView(null,false)')
        self.assertEqual(self.page.get_by_label('Room title').input_value(),'Remote saved')
        self.assertFalse(undo.is_enabled())
        self.assertFalse(redo.is_enabled())

        self.page.get_by_label('Room title').fill('Local draft')
        self.page.get_by_role('button',name='Apply room changes').click()
        newer={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Another remote','width':14,'height':20,'unit':'ft','approximate':False,'objects':[]}]}
        self.page.evaluate('(document)=>{window.fixtureLayout.revision=9;window.fixtureLayout.document=document}',newer)
        self.page.evaluate('window.instance.refreshWorkshopView(null,false)')
        self.assertEqual(self.page.get_by_label('Room title').input_value(),'Local draft')
        self.assertTrue(undo.is_enabled(),'dirty local draft and its history must survive refresh')
        self.assertEqual(self.errors,[])

    def test_rooms4_other_tab_save_recovery_preserves_this_tabs_draft_and_history(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        base={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Original','width':14,'height':20,'unit':'ft','approximate':False,'objects':[]}]}
        self.install_rooms4_plan(base)
        self.page.get_by_role('button',name='Edit',exact=True).click()
        self.page.get_by_label('Room title').fill('A draft')
        self.page.get_by_role('button',name='Apply room changes').click()
        before=self.page.evaluate("""() => {
          const prefix='workshop-room-draft:group-1:user-1:';
          const token=sessionStorage.getItem('workshop-room-draft-tab');
          const key=Object.keys(localStorage).find(k=>k.startsWith(prefix)&&k.endsWith(token));
          window.rooms4TabAKey=key;
          return JSON.parse(localStorage.getItem(key));
        }""")
        self.assertTrue(before['dirty'])
        self.assertTrue(before['undo'][room])
        other={'version':2,'rooms':[{'id':room,'location_id':None,'name':'B uncertain save','width':14,'height':20,'unit':'ft','approximate':False,'objects':[]}]}
        pending_key='rooms4-b-pending'
        self.page.evaluate("""({other,pendingKey}) => {
          const scope='group-1:user-1',base='workshop-room-draft:'+scope;
          localStorage.setItem(base+':tab-B',JSON.stringify({identity:'identity-1',group_id:'group-1',user_id:'user-1',revision:7,dirty:true,document:other,room_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',undo:{},redo:{},uncertain:{key:pendingKey,revision:7,document:other}}));
          window.fixtureLayout.revision=8;window.fixtureLayout.document=structuredClone(other);
          localStorage.setItem('workshop-pending:'+scope,JSON.stringify([{key:pendingKey,path:'workshop/save',label:'Save all room changes',subject:'',at:'2026-10-08T00:00:00Z',identity:'identity-1',group_id:'group-1',user_id:'user-1',intent:{schema_version:2,revision:7,document:other}}]));
          window.instance.dispose();window.instance=window.mountFixture();
        }""", {'other':other,'pendingKey':pending_key})
        self.assertTrue(self.page.get_by_role('button',name='Edit',exact=True).is_enabled(),"another tab pending save must not lock this tab draft")
        self.page.get_by_role('button',name='Edit',exact=True).click()
        self.assertEqual(self.page.get_by_label('Room title').input_value(),'A draft')
        after_reload=self.page.evaluate('JSON.parse(localStorage.getItem(window.rooms4TabAKey))')
        self.assertEqual(after_reload['document'],before['document'])
        self.assertEqual(after_reload['undo'],before['undo'])
        self.assertEqual(after_reload['revision'],7,'the draft base revision must remain stale after B commits revision 8')

        recovery=self.context.new_page()
        self.addCleanup(recovery.close)
        recovery.goto('https://fixture.invalid/workshop/recovery',wait_until='domcontentloaded',timeout=2500)
        recovery.add_script_tag(content=self.css)
        recovery.add_script_tag(content=self.source)
        recovery.evaluate("""() => {
          const context={value:{user:{id:'user-1',name:'Tester'},group:{id:'group-1',name:'Storage Room'},manager:true,identity:'identity-1'}};
          const pending=()=>JSON.parse(localStorage.getItem('workshop-pending:group-1:user-1')||'[]');
          const workshop={context,refresh:async()=>context.value,pending,forget:key=>localStorage.setItem('workshop-pending:group-1:user-1',JSON.stringify(pending().filter(row=>row.key!==key))),request:async(path)=>path==='recovery'?[]:path==='operation/status'?{status:'completed'}:{}};
          window.recoveryInstance=window.mountWorkshopTools(document.querySelector('#root'),'recovery',workshop,()=>{},()=>{});
        }""")
        recovery.get_by_role('button',name='Check saved result').wait_for(state='visible')
        recovery.get_by_role('button',name='Check saved result').click()
        recovery.get_by_role('button',name='Return to recovery').click()
        recovery.wait_for_function("JSON.parse(localStorage.getItem('workshop-pending:group-1:user-1')||'[]').length===1")
        self.page.evaluate('window.instance.dispose();window.instance=window.mountFixture()')
        self.page.get_by_role('button',name='Edit',exact=True).click()
        self.assertEqual(self.page.get_by_label('Room title').input_value(),'A draft')
        after_recovery=self.page.evaluate('JSON.parse(localStorage.getItem(window.rooms4TabAKey))')
        self.assertEqual(after_recovery['document'],before['document'])
        self.assertEqual(after_recovery['undo'],before['undo'])
        self.assertEqual(after_recovery['revision'],7)
        self.assertEqual(self.errors,[])

    def test_rooms4_blocked_equipment_is_not_labeled_available(self):
        self.page.evaluate("""() => {
          window.fixtureSearchEquipment=[
            {id:'88888888-8888-4888-8888-888888888888',name:'Blocked camera',assetId:'CAM-B',condition:'Ready',blocker:'Checkout review required',parent:{id:'11111111-1111-4111-8111-111111111111'}},
            {id:'99999999-9999-4999-8999-999999999999',name:'Ready camera',assetId:'CAM-A',condition:'Ready',blocker:null,parent:{id:'11111111-1111-4111-8111-111111111111'}}
          ];
          window.instance.dispose();
          window.instance=window.mountWorkshopTools(document.querySelector('#root'),'equipment',window.fixtureWorkshop,window.fixtureNavigate,window.fixtureNotify,{entityId:null,drawingId:null,roomId:null});
        }""")
        self.page.get_by_role('heading',name='Equipment',exact=True).wait_for(state='visible')
        blocked=self.page.locator('tr').filter(has_text='Blocked camera')
        self.assertTrue(blocked.count())
        self.assertIn('Checkout review required',blocked.inner_text())
        self.assertNotIn('Available',blocked.inner_text())
        ready=self.page.locator('tr').filter(has_text='Ready camera')
        self.assertIn('Available',ready.inner_text())
        self.page.get_by_label('Equipment filter').select_option('available')
        self.assertFalse(self.page.locator('tr').filter(has_text='Blocked camera').count())
        self.page.get_by_label('Equipment filter').select_option('blocked')
        self.assertTrue(self.page.locator('tr').filter(has_text='Blocked camera').count())
        self.assertEqual(self.errors,[])

    def test_rooms4_planner_contents_inspector_preserves_checkout_blocker(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[
            {'id':DRAWING,'name':'Rack 1','kind':'Rack','x':0,'y':0,'width':3,'height':2,'rotation':0,'location_id':LOCATION}
        ]}]}
        self.install_rooms4_plan(document,selected_drawing=DRAWING)
        self.page.evaluate("""() => {
          window.fixtureViews.locationView.contents=[{id:'22222222-2222-4222-8222-222222222222',name:'Blocked camera',condition:'Ready',checkout_blocker:'Checkout review required',checked_out:false,parent:{id:'11111111-1111-4111-8111-111111111111'}}];
          window.fixtureViews.locationView.counts={assigned:1,checked_out:0,available:0,needs_attention:0};
        }""")
        self.page.evaluate("window.instance.refreshWorkshopView('11111111-1111-4111-8111-111111111111',false)")
        row=self.page.locator('[aria-label="Equipment contents"] p').filter(has_text='Blocked camera')
        row.wait_for(state='visible')
        self.assertIn('Checkout review required',row.inner_text())
        self.assertNotIn('Available',row.inner_text())
        self.assertEqual(self.errors,[])

    def test_query_selection_updates_without_discarding_dirty_geometry(self):
        self.page.get_by_role('button', name='Edit layout').click()
        self.page.get_by_role('button', name='Room settings').click()
        self.page.locator('#dialog[open]').wait_for(state='visible', timeout=1500)
        self.page.get_by_label('Room name').fill('Draft floor')
        self.page.get_by_role('button', name='Apply room changes').click()
        self.page.get_by_role('button', name='Edit drawing properties').click()
        self.page.get_by_label('Width in feet').fill('4.5')
        self.page.get_by_label('Position from left').fill('2.25')
        self.page.get_by_role('button', name='Apply drawing changes').click()
        self.page.evaluate("""async () => window.instance.updateWorkshopSelection({
          entityId:'22222222-2222-4222-8222-222222222222',drawingId:null,roomId:null
        })""")
        self.assertTrue(self.page.get_by_text('Camera · 22222222-2222-4222-8222-222222222222', exact=True).is_visible())
        self.assertEqual(self.page.evaluate('window.writes'), [])
        self.page.get_by_role('button', name='Save layout changes').click()
        saved = self.page.evaluate('window.writes[0][1]')
        self.assertEqual(saved['revision'], 7)
        self.assertEqual(saved['layout']['name'], 'Draft floor')
        self.assertEqual(saved['layout']['objects'][0]['id'], DRAWING)
        self.assertEqual(saved['layout']['objects'][0]['x'], 2.25)
        self.assertEqual(saved['layout']['objects'][0]['width'], 4.5)
        self.assertEqual(self.errors, [])

    def test_query_change_during_save_waits_for_commit_before_refresh(self):
        self.page.get_by_role('button', name='Edit layout').click()
        self.page.get_by_role('button', name='Room settings').click()
        self.page.get_by_label('Room name').fill('Deferred draft')
        self.page.get_by_role('button', name='Apply room changes').click()
        self.page.get_by_role('button', name='Edit drawing properties').click()
        self.page.get_by_label('Width in feet').fill('4.5')
        self.page.get_by_label('Position from left').fill('2.25')
        self.page.get_by_role('button', name='Apply drawing changes').click()
        self.page.evaluate('window.deferLayoutSave=true')
        self.page.get_by_role('button', name='Save layout changes').click()
        self.page.wait_for_function('window.layoutSaveStarted===true')
        save_button = self.page.get_by_role('button', name='Save layout changes', exact=True)
        self.assertTrue(save_button.is_disabled())
        before = self.page.locator('.map + p').inner_text()
        self.page.evaluate("""async () => window.instance.updateWorkshopSelection({
          entityId:'22222222-2222-4222-8222-222222222222',drawingId:null,roomId:null
        })""")
        self.assertTrue(save_button.is_disabled())
        self.assertEqual(self.page.locator('.map + p').inner_text(), before)
        self.assertEqual(self.page.evaluate('window.writes.length'), 1)
        self.page.evaluate('window.releaseLayoutSave()')
        self.page.get_by_role('button', name='Layout saved', exact=True).wait_for()
        self.page.get_by_text('Camera · 22222222-2222-4222-8222-222222222222', exact=True).wait_for()
        self.assertEqual(self.page.locator('.map + p').inner_text(), 'Deferred draft · 14 × 20 ft')
        request = self.page.evaluate('window.writes[0][1]')
        self.assertEqual(request['revision'], 7)
        self.assertEqual(request['layout']['name'], 'Deferred draft')
        self.assertEqual(request['layout']['objects'][0], {
            'id': DRAWING, 'name': 'Old drawing name', 'kind': 'Rack', 'x': 2.25, 'y': 0,
            'width': 4.5, 'height': 2, 'location_id': LOCATION,
        })
        view_reads = [call for call in self.page.evaluate('window.apiCalls') if call[0].startswith('workshop/view')]
        self.assertEqual(len(view_reads), 2, 'initial read plus exactly one deferred selected-identity refresh')
        self.assertEqual(self.errors, [])

    def test_latest_deferred_query_survives_queued_timer_and_following_save(self):
        self.page.evaluate("""() => {
          window.fixtureTimers=[];
          window.fixtureOriginalTimeout=window.setTimeout.bind(window);
          window.setTimeout=(callback,delay,...args)=>{
            if(delay===0){window.fixtureTimers.push(()=>callback(...args));return window.fixtureTimers.length}
            return window.fixtureOriginalTimeout(callback,delay,...args);
          };
          window.deferLayoutSave=true;
        }""")
        self.page.get_by_role('button', name='Edit layout').click()
        self.page.get_by_role('button', name='Room settings').click()
        self.page.get_by_label('Room name').fill('First deferred draft')
        self.page.get_by_role('button', name='Apply room changes').click()
        self.page.get_by_role('button', name='Save layout changes').click()
        self.page.wait_for_function('window.layoutSaveCount===1')
        self.page.evaluate("""async () => window.instance.updateWorkshopSelection({
          entityId:'22222222-2222-4222-8222-222222222222',drawingId:null,roomId:null
        })""")
        self.page.evaluate('window.releaseLayoutSave()')
        self.page.get_by_role('button', name='Layout saved', exact=True).wait_for()
        self.page.wait_for_function('window.fixtureTimers.length===1')
        # A newer route query replaces the pending selection before its timer fires.
        self.page.evaluate("""async () => window.instance.updateWorkshopSelection({
          entityId:'11111111-1111-4111-8111-111111111111',drawingId:null,roomId:null
        })""")
        self.page.get_by_role('button', name='Room settings').click()
        self.page.get_by_label('Room name').fill('Second deferred draft')
        self.page.get_by_role('button', name='Apply room changes').click()
        self.page.get_by_role('button', name='Save layout changes').click()
        self.page.wait_for_function('window.layoutSaveCount===2')
        self.page.evaluate('window.fixtureTimers.shift()()')
        self.assertTrue(self.page.get_by_role('button', name='Save layout changes', exact=True).is_disabled())
        self.assertEqual(len([call for call in self.page.evaluate('window.apiCalls') if call[0].startswith('workshop/view')]), 1)
        self.page.evaluate('window.releaseLayoutSave()')
        self.page.get_by_role('button', name='Layout saved', exact=True).wait_for()
        self.page.wait_for_function('window.fixtureTimers.length===1')
        self.page.evaluate('window.fixtureTimers.shift()()')
        self.page.get_by_text('Storage Room · 11111111-1111-4111-8111-111111111111', exact=True).wait_for()
        self.assertEqual(self.page.locator('.map + p').inner_text(), 'Second deferred draft · 14 × 20 ft')
        self.assertEqual(len([call for call in self.page.evaluate('window.apiCalls') if call[0].startswith('workshop/view')]), 2)
        self.assertEqual([row[1]['revision'] for row in self.page.evaluate('window.writes')], [7, 8])
        self.assertEqual(self.errors, [])

    def test_refresh_finishing_during_save_cannot_repaint_enabled_edit_controls(self):
        self.page.get_by_role('button', name='Edit layout').click()
        self.page.get_by_role('button', name='Room settings').click()
        self.page.get_by_label('Room name').fill('Saved geometry')
        self.page.get_by_role('button', name='Apply room changes').click()
        self.page.get_by_role('button', name='Edit drawing properties').click()
        self.page.get_by_label('Width in feet').fill('4.5')
        self.page.get_by_label('Position from left').fill('2.25')
        self.page.get_by_role('button', name='Apply drawing changes').click()
        self.page.evaluate("""() => {
          window.deferWorkshopRefresh=true;
          window.refreshPromise=window.instance.refreshWorkshopView('11111111-1111-4111-8111-111111111111',false);
        }""")
        self.page.wait_for_function('window.workshopRefreshStarted===true')
        self.page.evaluate('window.deferLayoutSave=true')
        self.page.get_by_role('button', name='Save layout changes').click()
        self.page.wait_for_function('window.layoutSaveCount===1')
        self.page.evaluate('window.releaseWorkshopRefresh()')
        self.page.evaluate('window.refreshPromise')
        save_button = self.page.get_by_role('button', name='Save layout changes', exact=True)
        self.assertTrue(save_button.is_disabled())
        self.assertEqual(self.page.locator('.map + p').inner_text(), 'Saved geometry · 14 × 20 ft')
        self.assertEqual(self.page.evaluate('window.writes.length'), 1)
        self.page.evaluate('window.releaseLayoutSave()')
        self.page.get_by_role('button', name='Layout saved', exact=True).wait_for()
        refresh_notice = self.page.get_by_text('A native refresh overlapped a save. Refresh native view to load current status.', exact=True)
        refresh_notice.wait_for(state='visible')
        self.assertEqual(self.page.evaluate('window.writes[0][1]'), {
            'revision': 7,
            'layout': {'name': 'Saved geometry', 'width': 14, 'height': 20, 'unit': 'ft', 'approximate': False,
                       'objects': [{'id': DRAWING, 'name': 'Old drawing name', 'kind': 'Rack', 'x': 2.25,
                                    'y': 0, 'width': 4.5, 'height': 2, 'location_id': LOCATION}]},
        })
        self.page.get_by_role('button', name='Refresh native view').click()
        refresh_notice.wait_for(state='hidden')
        self.assertEqual(self.errors, [])

    def test_search_accessible_identity_includes_full_name_path_and_uuid(self):
        other_cage='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        other_rack='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
        other_item='cccccccc-cccc-4ccc-8ccc-cccccccccccc'
        self.page.evaluate("""rows => {
          window.fixtureLayout.parents=[
            {id:'""" + LOCATION + """',name:'Storage Room',parent_id:null,isLocation:true},
            {id:'66666666-6666-4666-8666-666666666666',name:'The Cage',parent_id:'""" + LOCATION + """',isLocation:true},
            {id:'""" + RACK + """',name:'North Rack',parent_id:'66666666-6666-4666-8666-666666666666',isLocation:true},
            {id:'""" + ITEM + """',name:'Shared kit',parent_id:'""" + RACK + """',isLocation:false},
            {id:'""" + other_cage + """',name:'The Cage',parent_id:'""" + LOCATION + """',isLocation:true},
            {id:'""" + other_rack + """',name:'South Rack',parent_id:'""" + other_cage + """',isLocation:true},
            {id:'""" + other_item + """',name:'Shared kit',parent_id:'""" + other_rack + """',isLocation:false}
          ];
          window.fixtureSearchEquipment=rows;
          window.fixtureSearchLocations=[];
          window.instance.dispose();
          window.instance=window.mountFixture();
        }""", [
          {'id':ITEM,'name':'Shared kit','assetId':'DUP','parent':{'id':RACK}},
          {'id':other_item,'name':'Shared kit','assetId':'DUP','parent':{'id':other_rack}}
        ])
        self.page.get_by_role('link', name='Storage Room / The Cage / North Rack / Shared kit', exact=True).wait_for()
        self.page.get_by_label('Search native equipment and storage').fill('Shared kit')
        names = self.page.get_by_role('button', name='Shared kit ·', exact=False).all()
        self.assertEqual(len(names), 2)
        for row, expected_path in zip(names, ['Storage Room / The Cage / North Rack / Shared kit', 'Storage Room / The Cage / South Rack / Shared kit']):
            text = row.inner_text()
            accessible = row.get_attribute('aria-label')
            self.assertIn(expected_path, text)
            self.assertIn(expected_path, accessible)
            self.assertIn('Shared kit', accessible)
            self.assertIn('DUP', accessible)
        self.assertIn(ITEM, names[0].inner_text())
        self.assertIn(other_item, names[1].inner_text())
        self.assertEqual(self.errors, [])

    def test_desktop_search_rack_coverage_photos(self):
        self.assertTrue(self.page.get_by_role('checkbox', name='Show status overlays on map').is_visible())
        self.assertFalse(self.page.get_by_role('checkbox', name='Show status overlays on map').is_checked())
        self.assertTrue(self.page.get_by_role('link', name='Open native record').last.is_visible())
        self.assertEqual(self.page.get_by_role('link', name='Edit native photos').get_attribute('href'), '/location/11111111-1111-4111-8111-111111111111/edit')
        self.assertTrue(self.page.get_by_text('Choose a map representation', exact=True).is_visible())
        self.assertTrue(self.page.get_by_text('No map coverage', exact=False).is_visible())
        self.assertTrue(self.page.get_by_role('img', name='Rack shelf photo').is_visible(), str(self.page.evaluate('window.apiCalls'))+' '+self.page.locator('#view').inner_text())
        self.page.get_by_label('Search native equipment and storage').fill('CAM-9')
        self.page.locator('.workshop-search-results button').filter(has_text='CAM-9').click()
        self.assertIn('/workshop/map?id=22222222-2222-4222-8222-222222222222', self.page.evaluate('window.navigate').pop())
        self.page.get_by_text('Condition: Ready · Checked out', exact=True).wait_for()
        self.assertTrue(self.page.get_by_text('Assigned storage: Storage Room / the Cage / Rack 1 / Rack 1-A').is_visible())
        self.assertTrue(self.page.get_by_text('Full native path: Storage Room / the Cage / Rack 1 / Rack 1-A / Camera').is_visible())
        self.assertTrue(self.page.get_by_role('link', name='Open native record').first.get_attribute('href').endswith('/item/22222222-2222-4222-8222-222222222222'))
        self.assertTrue(any(call[0].startswith('workshop/view?id=22222222-2222-4222-8222-222222222222&nested=0') for call in self.page.evaluate('window.apiCalls')))
        self.assertFalse(self.page.get_by_text('Private Borrower').count())
        self.page.get_by_role('checkbox', name='Include nested contents').check()
        self.assertTrue(any(call[0].startswith('workshop/view?id=22222222-2222-4222-8222-222222222222&nested=1') for call in self.page.evaluate('window.apiCalls')))
        self.page.evaluate("async () => { window.failViewOnce=true; await window.instance.refreshWorkshopView('22222222-2222-4222-8222-222222222222', true) }")
        self.assertTrue(self.page.get_by_text('Status unavailable', exact=True).is_visible())
        self.assertFalse(self.page.get_by_text('Assigned storage: Storage Room / the Cage / Rack 1 / Rack 1-A').count())

    def test_desktop_boxed_selection_uses_projection_status_and_full_storage_path(self):
        self.page.evaluate("""() => {
          const selected=window.fixtureViews.itemView;
          selected.path.splice(-1,0,{id:'88888888-8888-4888-8888-888888888888',name:'Box 7',
            is_location:false,parent_id:'55555555-5555-4555-8555-555555555555'});
          selected.selection_status={condition:'Broken',checked_out:false,blocker:'Condition: Broken'};
          selected.contents=[];
          selected.counts={assigned:0,checked_out:0,available:0,needs_attention:0};
        }""")
        api_calls_before = self.page.evaluate('window.apiCalls.length')
        self.page.evaluate("async () => await window.instance.selectWorkshopEntity('" + ITEM + "')")
        observed = self.page.evaluate("""args => {
          const text=document.querySelector('.workshop-selection').innerText;
          const calls=window.apiCalls.slice(args.before).map(call=>call[0].split('?')[0]);
          return {status:text.split('\\n').find(line=>line.startsWith('Condition:'))||null,
            storage:text.split('\\n').find(line=>line.startsWith('Assigned storage:'))||null,
            guidance:text.split('\\n').find(line=>line.startsWith('Stored on '))||null,
            unscopedStatusReads:calls.filter(path=>path==='entity'||path==='loans'),
            writes:window.writes};
        }""", {'before': api_calls_before})
        expected = {
            'status': 'Condition: Broken · Not checked out · Condition: Broken',
            'storage': 'Assigned storage: Storage Room / the Cage / Rack 1 / Rack 1-A / Box 7',
            'guidance': 'Stored on Rack 1-A; highlighting containing area Storage Room (' + LOCATION + ').',
            'unscopedStatusReads': [], 'writes': [],
        }
        self.assertEqual(observed, expected,
                         'The selected descendant is outside direct contents; its private-free status and true storage path come from one view projection.')
        self.assertEqual(self.errors, [])

    def test_search_selection_uses_native_location_shape_for_links_and_reads(self):
        shelf_view = json.dumps(view(SHELF))
        self.page.evaluate("""shelfView => {
          window.fixtureSearchLocations=[{id: '""" + SHELF + """', name: 'Rack 1-A', assetId: '1-A',
            entityType: {isLocation: true}, parent: {id: '""" + RACK + """'}}];
          window.fixtureViews.locationView = JSON.parse(shelfView);
        }""", shelf_view)
        search = self.page.get_by_label('Search native equipment and storage')
        search.fill('Rack 1-A')
        result = self.page.locator('.workshop-search-results button').filter(has_text='1-A')
        result.wait_for(timeout=1500)
        result.click()
        self.assertIn('/workshop/map?id=' + SHELF, self.page.evaluate('window.navigate').pop())
        open_link = self.page.get_by_role('link', name='Open native record', exact=True).last
        self.assertEqual(open_link.get_attribute('href'), '/location/' + SHELF)
        self.assertEqual(self.page.get_by_role('link', name='Edit native photos', exact=True).get_attribute('href'),
                         '/location/' + SHELF + '/edit')
        routes = [call[0].split('?')[0] for call in self.page.evaluate('window.apiCalls')]
        self.assertNotIn('entity', routes)
        self.assertNotIn('loans', routes)
        self.assertNotIn('null', self.page.locator('.workshop-selection').inner_text())
        self.assertTrue(self.page.get_by_text('Assigned storage: Storage Room / the Cage / Rack 1 / Rack 1-A').is_visible())
        self.assertEqual(self.page.evaluate('window.writes'), [])
        self.assertEqual(self.errors, [])

    def test_desktop_search_unknown_and_order_recovery(self):
        self.page.get_by_label('Search native equipment and storage').fill('UNKNOWN-MFR')
        self.page.get_by_label('Search native equipment and storage').press('Enter')
        self.assertTrue(self.page.get_by_text('No unique native record found.', exact=True).is_visible())
        self.assertEqual(self.page.evaluate('window.navigate'), [])
        self.assertEqual(self.page.evaluate('window.writes'), [])
        self.page.evaluate('window.loseOrderResponse=true')
        self.page.get_by_role('button', name='Review shelf order').click()
        self.assertTrue(self.page.get_by_role('button', name='Confirm shelf order').count(), 'dialog='+self.page.locator('#dialog-body').inner_text()+' page='+self.page.locator('#view').inner_text())
        self.page.get_by_role('button', name='Confirm shelf order').click()
        self.page.get_by_text('fixture lost response').wait_for()
        pending = json.loads(self.page.evaluate("localStorage.getItem('workshop-order:group-1:user-1:11111111-1111-4111-8111-111111111111')"))
        self.assertEqual(pending['status'], 'pending')
        self.page.get_by_role('button', name='Cancel').click()
        self.page.get_by_role('button', name='Review shelf order').click()
        self.assertTrue(self.page.get_by_text('A previous shelf order has an unconfirmed result.', exact=False).is_visible())
        self.assertFalse(self.page.get_by_role('button', name='Confirm shelf order').count())
        self.assertEqual(len(self.page.evaluate('window.writes')), 1)


class TerminalMapBrowserTests(unittest.TestCase):
    """Run the checked-in Terminal page, map host, and final lifecycle script."""

    ITEM = '22222222-2222-4222-8222-222222222222'
    RACK = '11111111-1111-4111-8111-111111111111'
    DRAWING = '33333333-3333-4333-8333-333333333333'
    PHOTO = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / 'kiosk/index.html').read_text(encoding='utf-8')
        cls.scripts = {
            '/import-ui.js': (ROOT / 'kiosk/import-ui.js').read_text(encoding='utf-8'),
            '/workshop-ui.js': (ROOT / 'kiosk/workshop-ui.js').read_text(encoding='utf-8'),
            '/checkout-ui.js': (ROOT / 'kiosk/checkout-ui.js').read_text(encoding='utf-8'),
            '/return-ui.js': (ROOT / 'kiosk/return-ui.js').read_text(encoding='utf-8'),
            '/workflow-ui.js': (ROOT / 'kiosk/workflow-ui.js').read_text(encoding='utf-8'),
            '/users-ui.js': (ROOT / 'kiosk/users-ui.js').read_text(encoding='utf-8'),
        }

    def setUp(self):
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True, executable_path='/usr/bin/chromium')
        self.addCleanup(self.browser.close)
        self.context = self.browser.new_context(viewport={'width': 800, 'height': 480}, is_mobile=True,
                                                has_touch=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(2500)
        self.page.set_default_navigation_timeout(2500)
        self.errors = []
        self.failed_requests = []
        self.error_responses = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('console', lambda message: self.errors.append(message.text) if message.type == 'error' else None)
        self.page.on('requestfailed', lambda request: self.failed_requests.append((request.method, urlsplit(request.url).path)))
        self.page.on('response', lambda response: self.error_responses.append((urlsplit(response.url).path, response.status)) if response.status >= 400 else None)
        self.calls = []
        self.workshop_view_refreshes = 0
        self.session_polls = 0
        self.unexpected_requests = []
        self.saved_layouts = []
        self.pending_saves = []
        self.defer_save = False
        self.save_status = 200
        self.malformed_save = False
        self.fail_view_once = False
        self.defer_initial_view = False
        self.pending_views = []
        self.defer_workshop_open = False
        self.pending_workshop_gets = []
        self.defer_map_resolve = False
        self.pending_map_resolves = []
        self.lose_order_response = False
        self.shelf_orders = []
        self.operation_checks = []
        self.defer_operation_status = False
        self.pending_operation_status = []
        self.native_visits = []
        self.operation_response = {'status': 'not_started'}
        self.expire_session = False
        self.session = {'user': {'id': 'user-1', 'name': 'Map tester'},
                        'generation': 1, 'instance': 'session-1'}
        self.parents = [
            {'id': self.RACK, 'name': 'The Cage', 'parent_id': None, 'isLocation': True,
             'kind': 'Rack', 'code': '1', 'updated_at': 'rack-v1'},
            {'id': '55555555-5555-4555-8555-555555555555', 'name': 'Shelf 1',
             'parent_id': self.RACK, 'isLocation': True, 'kind': 'Shelf', 'code': '1-A',
             'updated_at': 'shelf-v1'},
            {'id': '77777777-7777-4777-8777-777777777777', 'name': 'Shelf 2',
             'parent_id': self.RACK, 'isLocation': True, 'kind': 'Shelf', 'code': '1-B',
             'updated_at': 'shelf-2-v1'},
            {'id': '88888888-8888-4888-8888-888888888888', 'name': 'Rack B',
             'parent_id': None, 'isLocation': True, 'kind': 'Rack', 'code': '2',
             'updated_at': 'rack-b-v1'},
            {'id': '99999999-9999-4999-8999-999999999999', 'name': 'The Cage',
             'parent_id': '88888888-8888-4888-8888-888888888888', 'isLocation': True,
             'kind': 'Rack', 'code': '2-A', 'updated_at': 'cage-b-v1'},
            {'id': self.ITEM, 'name': 'Camera', 'parent_id': '55555555-5555-4555-8555-555555555555',
             'isLocation': False},
        ]
        self.native_locations = [
            {'id': self.RACK, 'name': 'The Cage', 'entityType': {'name': 'Rack', 'isLocation': True},
             'parent': None, 'code': '1', 'updated_at': 'rack-v1'},
            {'id': '55555555-5555-4555-8555-555555555555', 'name': 'Shelf 1',
             'entityType': {'name': 'Shelf', 'isLocation': True},
             'parent': {'id': self.RACK}, 'code': '1-A', 'updated_at': 'shelf-v1'},
            {'id': '77777777-7777-4777-8777-777777777777', 'name': 'Shelf 2',
             'entityType': {'name': 'Shelf', 'isLocation': True},
             'parent': {'id': self.RACK}, 'code': '1-B', 'updated_at': 'shelf-2-v1'},
            {'id': '88888888-8888-4888-8888-888888888888', 'name': 'Rack B',
             'entityType': {'name': 'Rack', 'isLocation': True},
             'parent': None, 'code': '2', 'updated_at': 'rack-b-v1'},
            {'id': '99999999-9999-4999-8999-999999999999', 'name': 'The Cage',
             'entityType': {'name': 'Rack', 'isLocation': True},
             'parent': {'id': '88888888-8888-4888-8888-888888888888'},
             'code': '2-A', 'updated_at': 'cage-b-v1'},
        ]
        self.layout = {
            'revision': 7,
            'layout': {'name': 'Workshop floor', 'width': 14, 'height': 20, 'unit': 'ft',
                       'approximate': False,
                       'objects': [{'id': self.DRAWING, 'name': 'Cage drawing', 'kind': 'Rack',
                                    'x': 1, 'y': 2, 'width': 3, 'height': 2,
                                    'rotation': 0, 'location_id': self.RACK}]},
            'locations': self.parents[:2], 'parents': self.parents,
            'types': ['Rack', 'Cabinet', 'Workbench', 'Table', 'Fence', 'Gate', 'Door', 'Area', 'Kiosk'],
            'storage_types': ['Area', 'Rack', 'Shelf', 'Bin', 'Cabinet', 'Drawer', 'Workbench', 'Location'],
            'counts': {},
        }
        self.view = {
            'selection': {'target_id': self.ITEM, 'destination_id': self.RACK,
                          'kind': 'containing', 'matches': [{'room_id': None,
                          'drawing_id': self.DRAWING, 'location_id': self.RACK}]},
            'path': [{'id': self.RACK, 'name': 'The Cage', 'is_location': True, 'parent_id': None},
                     {'id': self.parents[1]['id'], 'name': 'Shelf 1', 'is_location': True,
                      'parent_id': self.RACK},
                     {'id': self.ITEM, 'name': 'Camera', 'is_location': False,
                      'parent_id': self.parents[1]['id']}],
            'contents': [], 'include_nested': False,
            'counts': {'assigned': 0, 'checked_out': 0, 'available': 0, 'needs_attention': 0},
            'coverage': [], 'rack': None,
            'photos': [{'id': self.PHOTO, 'title': 'Cage shelves', 'primary': True,
                        'alt': 'The Cage shelving'}], 'errors': [],
            'refreshed_at': '2026-10-08T12:00:00+00:00',
        }
        self.selection_status = None
        self.png = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j8XQAAAAASUVORK5CYII=')
        self.context.route('**/*', self._deny_unexpected_origin)
        self.context.route('https://terminal.fixture/**', self._route)
        self.context.route('https://terminal.fixture:17745/**', self._native_route)
        self.page.goto('https://terminal.fixture/', wait_until='load', timeout=5000)
        self.page.wait_for_function("document.querySelector('#identity')?.textContent === 'Map tester'", timeout=6000)
        # Test-only accessors call the actual functions and close over the actual host state.
        self.page.add_script_tag(content="""
          window.task6Harness={
            routeScan:code=>routeScan(code), setScanPurpose:value=>{scanPurpose=value},
            updateIdentity:()=>updateIdentity(),
            openNativeRecord:async id=>detail((await api('/api/entity?id='+encodeURIComponent(id))).entity),
            observeWorkshopRefreshes:()=>{
              const original=workshopRefreshView;
              window.__task6NativeRefreshPromises=[];
              workshopRefreshView=(...args)=>{
                const promise=original(...args);
                window.__task6NativeRefreshPromises.push(promise);
                return promise;
              };
            },
            awaitWorkshopRefreshes:async()=>await Promise.all(window.__task6NativeRefreshPromises||[]),
            snapshot:()=>({draft:workshopDraft,state:workshopState,selected:workshopSelected,
              dirty:workshopDirty,editing:workshopEditing,title:routeTitle,viewData:workshopViewData,
              identity:{instance:identityInstance,generation:identityGeneration}, identified}),
            storageSnapshots:()=>Object.entries(localStorage).map(([key,value])=>({key,value}))
          };
        """)

    def _json(self, route, value, status=200):
        route.fulfill(status=status, content_type='application/json', body=json.dumps(value))

    def _native_route(self, route):
        parsed = urlsplit(route.request.url)
        if (parsed.scheme, parsed.hostname, parsed.port, route.request.method, parsed.path) not in {
                ('https', 'terminal.fixture', 17745, 'GET', '/location/' + self.RACK),
                ('https', 'terminal.fixture', 17745, 'GET', '/location/' + self.RACK + '/edit')}:
            self.unexpected_requests.append((route.request.method, parsed.netloc, parsed.path))
            route.abort()
            return
        self.native_visits.append(parsed.path)
        route.fulfill(status=200, content_type='text/html',
                      body='<!doctype html><title>Disposable native record</title><main>Fixture only</main>')

    def _deny_unexpected_origin(self, route):
        parsed = urlsplit(route.request.url)
        if parsed.scheme == 'https' and parsed.hostname == 'terminal.fixture' and parsed.port in (None, 17745):
            route.continue_()
            return
        self.unexpected_requests.append((route.request.method, parsed.netloc, parsed.path))
        route.abort()

    def _route(self, route):
        request = route.request
        parsed = urlsplit(request.url)
        path = parsed.path
        if path == '/':
            route.fulfill(status=200, content_type='text/html', body=self.index)
            return
        if path in self.scripts:
            route.fulfill(status=200, content_type='application/javascript', body=self.scripts[path])
            return
        if path in ('/favicon.svg', '/caci-create.svg'):
            route.fulfill(status=200, content_type='image/svg+xml',
                          body='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0h1v1H0z"/></svg>')
            return
        self.calls.append((request.method, path, request.post_data_json if request.post_data else None))
        exact = {
            '/api/session': ('GET', None),
            '/api/inventory': ('GET', None),
            '/api/locations': ('GET', None),
            '/api/types': ('GET', None),
            '/api/custody': ('GET', None),
            '/workshop/get': ('POST', {}),
            '/api/map': ('GET', None),
            '/api/members': ('GET', None),
            '/api/badges': ('GET', None),
            '/session/activity': ('POST', {}),
        }
        if path in exact and (request.method, request.post_data_json if request.post_data else None) != exact[path]:
            self.unexpected_requests.append((request.method, path, request.post_data_json if request.post_data else None))
            route.abort()
            return
        if path == '/workshop/view':
            body = request.post_data_json
            if (request.method != 'POST' or not isinstance(body, dict) or
                    set(body) != {'entity_id', 'include_nested'} or
                    (body['entity_id'] is not None and not isinstance(body['entity_id'], str)) or
                    not isinstance(body['include_nested'], bool)):
                self.unexpected_requests.append((request.method, path, body))
                route.abort()
                return
        if path == '/workshop/resolve':
            body = request.post_data_json
            if request.method != 'POST' or not isinstance(body, dict) or set(body) != {'code'} or not isinstance(body['code'], str):
                self.unexpected_requests.append((request.method, path, body))
                route.abort()
                return
        if path == '/operation/status':
            body = request.post_data_json
            if request.method != 'POST' or not isinstance(body, dict) or set(body) != {'request_key'} or not isinstance(body['request_key'], str):
                self.unexpected_requests.append((request.method, path, body))
                route.abort()
                return
        if path == '/workshop/save':
            body = request.post_data_json
            if request.method != 'POST' or not isinstance(body, dict) or set(body) != {'revision', 'layout'} or not isinstance(body['revision'], int) or not isinstance(body['layout'], dict):
                self.unexpected_requests.append((request.method, path, body))
                route.abort()
                return
        if path == '/workshop/shelf-order':
            body = request.post_data_json
            if (request.method != 'POST' or not isinstance(body, dict) or
                    set(body) != {'entity_id', 'updated_at', 'shelf_ids', 'request_key'} or
                    body.get('entity_id') != self.RACK or not isinstance(body.get('request_key'), str) or
                    not isinstance(body.get('updated_at'), str) or not isinstance(body.get('shelf_ids'), list)):
                self.unexpected_requests.append((request.method, path, body))
                route.abort()
                return
        if path == '/api/entity' and (request.method != 'GET' or request.post_data):
            self.unexpected_requests.append((request.method, path, request.post_data))
            route.abort()
            return
        if path == '/scan':
            body = request.post_data_json
            if request.method != 'POST' or not isinstance(body, dict) or set(body) != {'code', 'scan_token'} or not all(isinstance(body[key], str) for key in body):
                self.unexpected_requests.append((request.method, path, body))
                route.abort()
                return
        if path == '/api/session':
            self.session_polls += 1
            if self.expire_session:
                self._json(route, {'user': None,
                                   'generation': self.session['generation'] + 1,
                                   'instance': self.session['instance']})
            else:
                self._json(route, self.session)
        elif path == '/api/inventory':
            self._json(route, [])
        elif path == '/api/locations':
            self._json(route, self.native_locations)
        elif path == '/api/types':
            self._json(route, [])
        elif path == '/api/custody':
            self._json(route, [])
        elif path.startswith('/api/entity'):
            entity_id = parsed.query.split('id=', 1)[-1] if 'id=' in parsed.query else self.ITEM
            is_location = entity_id == self.RACK
            entity = {'id': entity_id, 'name': 'The Cage' if is_location else 'Camera',
                      'assetId': 'LOC-1' if is_location else 'CAM-9',
                      'entityType': {'isLocation': is_location},
                      'parent': (None if entity_id == self.RACK else
                                 {'id': self.RACK, 'name': 'The Cage'} if entity_id == self.parents[1]['id'] else
                                 {'id': self.parents[1]['id'], 'name': 'Shelf 1'}),
                      'attachments': [{'id': self.PHOTO, 'title': 'Cage shelves', 'type': 'photo'}]
                      if is_location else []}
            self._json(route, {'entity': entity, 'condition': 'Ready', 'blocker': None})
        elif path == '/workshop/get':
            if self.defer_workshop_open:
                self.defer_workshop_open = False
                self.pending_workshop_gets.append(route)
                return
            self._json(route, self.layout)
        elif path == '/workshop/view':
            body = request.post_data_json
            if self.defer_initial_view:
                self.defer_initial_view = False
                self.pending_views.append(route)
                return
            if self.fail_view_once:
                self.fail_view_once = False
                self._json(route, {'error': 'Workshop view is unavailable.'}, status=503)
                return
            entity_id = body.get('entity_id')
            response = json.loads(json.dumps(self.view))
            response['selection'] = {
                'target_id': entity_id,
                'destination_id': self.RACK if entity_id else None,
                'kind': 'exact' if entity_id == self.RACK else 'containing',
                'matches': ([{'room_id': None, 'drawing_id': self.DRAWING,
                              'location_id': self.RACK, 'name': 'The Cage'}] if entity_id else []),
            }
            if entity_id == self.RACK:
                response['path'] = [{'id': self.RACK, 'name': 'The Cage', 'is_location': True,
                                     'parent_id': None}]
                nested = body['include_nested']
                response['contents'] = ([{'id': self.ITEM, 'name': 'Camera', 'assetId': 'CAM-9',
                                          'condition': 'Ready', 'checkout_blocker': None,
                                          'checked_out': False,
                                          'parent': {'id': self.parents[1]['id']}}] if nested else [])
                response['counts'] = {'assigned': int(nested), 'checked_out': 0,
                                      'available': int(nested), 'needs_attention': 0}
                response['rack'] = {'id': self.RACK, 'name': 'The Cage',
                                    'shelves': [{'id': self.parents[1]['id'], 'name': 'Shelf 1',
                                                 'code': '1-A'},
                                                {'id': self.parents[2]['id'], 'name': 'Shelf 2',
                                                 'code': '1-B'}], 'unordered': [],
                                    'other_children': [], 'errors': []}
            elif entity_id == self.ITEM:
                response['path'] = self.view['path']
                response['contents'] = self.view['contents']
                response['counts'] = self.view['counts']
                response['rack'] = None
            else:
                response['path'] = []
                response['contents'] = []
                response['rack'] = None
            response['include_nested'] = body['include_nested']
            response['photos'] = self.view['photos'] if entity_id == self.RACK else []
            if entity_id == self.ITEM and self.selection_status is not None:
                response['selection_status'] = self.selection_status
            self.workshop_view_refreshes += 1
            response['refreshed_at'] = '2026-10-08T12:00:%02d+00:00' % self.workshop_view_refreshes
            self._json(route, response)
        elif path == '/workshop/resolve':
            code = request.post_data_json['code']
            if self.defer_map_resolve:
                self.defer_map_resolve = False
                self.pending_map_resolves.append(route)
                return
            if code == 'AMBIGUOUS':
                self._json(route, {'kind': 'entity', 'entity_id': None,
                                   'candidates': [
                                       {'id': self.ITEM, 'name': 'Camera', 'is_location': False,
                                        'asset_id': 'CAM-9', 'path': self.view['path']},
                                       {'id': '66666666-6666-4666-8666-666666666666',
                                        'name': 'Camera duplicate', 'is_location': False,
                                        'asset_id': 'CAM-9', 'path': self.view['path']}],
                                   'message': 'Select the matching native record.'})
            elif code == 'UNKNOWN':
                self._json(route, {'kind': 'unknown', 'entity_id': None, 'candidates': [],
                                   'message': 'No active native record matches this code.'})
            elif code.startswith('LAB:U:'):
                self._json(route, {'kind': 'invalid', 'entity_id': None, 'candidates': [],
                                   'message': 'A person badge cannot identify equipment.'})
            else:
                self._json(route, {'kind': 'entity', 'entity_id': self.ITEM,
                                   'candidates': [{'id': self.ITEM, 'name': 'Camera', 'is_location': False,
                                                   'asset_id': 'CAM-9', 'path': self.view['path']}],
                                   'message': 'Native record resolved.'})
        elif path == '/workshop/save':
            body = request.post_data_json
            self.saved_layouts.append(body)
            if self.defer_save:
                self.pending_saves.append(route)
                return
            if self.save_status == 409:
                message = 'The layout changed elsewhere. Reload before saving your edits.'
                self._json(route, {'error': message, 'reason': message}, status=409)
            elif self.malformed_save:
                self._json(route, {'revision': body['revision'] + 1, 'layout': {'name': 'truncated'}})
            else:
                self.layout['revision'] = body['revision'] + 1
                self.layout['layout'] = body['layout']
                self._json(route, {'revision': self.layout['revision'], 'layout': self.layout['layout']})
        elif path == '/workshop/shelf-order':
            self.shelf_orders.append(request.post_data_json)
            if self.lose_order_response:
                route.abort()
            else:
                self._json(route, {'id': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
                                   'status': 'completed', 'entity_id': self.RACK})
        elif path == '/operation/status':
            self.operation_checks.append(request.post_data_json)
            if self.defer_operation_status:
                self.pending_operation_status.append(route)
            else:
                self._json(route, self.operation_response)
        elif path == '/scan':
            self._json(route, {'entity': {'id': self.ITEM, 'name': 'Camera', 'assetId': 'CAM-9',
                                         'entityType': {'isLocation': False},
                                         'parent': {'id': self.parents[1]['id'], 'name': 'Shelf 1'}}})
        elif path == '/api/map':
            self._json(route, {'path': [], 'rooms': [], 'objects': []})
        elif path == '/api/members':
            self._json(route, [])
        elif path == '/api/badges':
            self._json(route, [])
        elif path == '/api/file':
            query = dict(parse_qsl(parsed.query))
            if (request.method != 'GET' or set(query) != {'entity', 'attachment'} or
                    query != {'entity': self.RACK, 'attachment': self.PHOTO}):
                self.unexpected_requests.append((request.method, path, query))
                route.abort()
                return
            route.fulfill(status=200, content_type='image/png', body=self.png)
        elif path == '/session/activity':
            self._json(route, {'active': True})
        else:
            self.unexpected_requests.append((request.method, path))
            route.abort()

    def _open_editing_map(self):
        self.page.locator('#layout-nav').click()
        self.page.locator('.workshop-view').wait_for(state='visible')
        self.page.locator('[data-workshop-object]').first.wait_for(state='visible')

    def _select_first_drawing(self):
        drawing = self.page.locator('[data-workshop-object]').first
        drawing.focus()
        drawing.press('Enter')
        self.page.get_by_role('button', name='Rotate 90°').wait_for(state='visible')

    def _wait_for_fixture(self, predicate, description):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(10)
        self.fail('Timed out waiting for fixture callback: ' + description)

    def _assert_fixture_network_errors(self, *, aborted=(), statuses=()):
        actual_aborts=[path for method,path in self.failed_requests if method=='POST']
        self.assertEqual(actual_aborts, list(aborted))
        actual_statuses=[(path,status) for path,status in self.error_responses]
        self.assertEqual(actual_statuses, list(statuses))
        expected_console=(['Failed to load resource: net::ERR_FAILED']*len(aborted)+
                          ['Failed to load resource: the server responded with a status of 503 (Service Unavailable)'
                           for path,status in statuses if status==503])
        self.assertCountEqual(self.errors, expected_console,
                              'Only the exact fixture-owned aborted/status response may emit a console resource error.')

    def _use_task5_layout_fixture(self):
        self.layout.update({
            'workshop_context': {
                'group_id': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
                'actor_id': 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
            },
            'document': {
                'version': 2,
                'rooms': [{
                    'id': 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
                    'location_id': None,
                    'name': 'Workshop floor',
                    'width': 14,
                    'height': 20,
                    'unit': 'ft',
                    'approximate': False,
                    'objects': [{
                        'id': self.DRAWING,
                        'caption': 'Cage drawing',
                        'kind': 'Rack',
                        'x': 1,
                        'y': 2,
                        'width': 3,
                        'height': 2,
                        'rotation': 0,
                        'location_id': self.RACK,
                    }],
                }],
            },
        })

    def _drag_world(self, object_id, dx_pixels, dy_pixels=0):
        points = self.page.evaluate("""args=>{const object=window.task6Harness.snapshot().draft.objects.find(row=>row.id===args.id),node=document.querySelector('[data-workshop-object="'+args.id+'"]'),matrix=node.parentElement.getScreenCTM(),point=(dx,dy)=>new DOMPoint((object.x+object.width/2)*24+dx,(object.y+object.height/2)*24+dy).matrixTransform(matrix);const from=point(0,0),to=point(args.dx,args.dy);return {from:{x:from.x,y:from.y},to:{x:to.x,y:to.y}}}""", {'id': object_id, 'dx': dx_pixels, 'dy': dy_pixels})
        self.page.mouse.move(points['from']['x'], points['from']['y'])
        self.page.mouse.down()
        self.page.mouse.move(points['to']['x'], points['to']['y'], steps=3)
        self.page.mouse.up()

    def test_terminal_browse_rotation_and_conflict(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.get_by_role('button', name='Rotate 90°').click()
        # The API must reject a stale base revision without replacing the editable draft.
        self.save_status = 409
        self.page.get_by_role('button', name='Save layout').click()
        self.page.get_by_text('The layout changed elsewhere. Reload before saving your edits.', exact=False).wait_for()
        self.assertEqual(len(self.saved_layouts), 1)
        saved = self.saved_layouts[0]['layout']['objects'][0]
        self.assertEqual((saved['width'], saved['height']), (3, 2),
                         'A quarter-turn must keep the stored width × height footprint.')
        self.assertEqual(saved['rotation'], 90)
        live = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(live['state']['revision'], 7)
        self.assertEqual((live['draft']['objects'][0]['width'], live['draft']['objects'][0]['height']), (3, 2))
        self.assertTrue(live['dirty'], 'A conflict must retain the dirty draft for review.')

    def test_terminal_malformed_save_keeps_original_base_and_draft(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.locator('.workshop-pad button').nth(3).click()
        before = self.page.evaluate('window.task6Harness.snapshot()')
        self.malformed_save = True
        self.page.get_by_role('button', name='Save layout').click()
        self._wait_for_fixture(lambda: len(self.saved_layouts) == 1, 'malformed Save request')
        self.page.get_by_text('The save response could not be verified.', exact=False).wait_for()
        after = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(after['state']['revision'], before['state']['revision'])
        self.assertEqual(after['state']['layout'], before['state']['layout'])
        self.assertEqual(after['draft'], before['draft'])
        self.assertTrue(after['dirty'])
        self.assertEqual(len(self.saved_layouts), 1)
        self.assertEqual(self.errors, [])

    def test_terminal_scan_and_desktop_selection_parity(self):
        # Start from the normal dashboard: map-purpose resolution must open the map itself.
        self.page.evaluate("window.task6Harness.setScanPurpose('workshop_map')")
        result = self.page.evaluate("window.task6Harness.routeScan('/item/" + self.ITEM + "')")
        self.assertTrue(result)
        resolve_calls = [call for call in self.calls if call[1] == '/workshop/resolve']
        self.assertEqual(len(resolve_calls), 1, 'Map scans must use the native resolver before generic scan handling.')
        self.assertEqual(resolve_calls[0][2], {'code': '/item/' + self.ITEM})
        self.assertFalse(any(call[1] == '/scan' for call in self.calls),
                         'Map-purpose scans must not enter badge/enrollment or generic scan handling.')
        self.page.wait_for_function("window.task6Harness.snapshot().title === 'Workshop'")
        self.assertEqual(self.page.evaluate('window.task6Harness.snapshot().selected'), self.DRAWING)
        self.page.locator('.workshop-native-details').get_by_text(
            'Full path: The Cage / Shelf 1 / Camera', exact=True).wait_for()
        item_link = self.page.get_by_role('link', name='Open native record', exact=True)
        self.assertEqual(urlsplit(item_link.get_attribute('href')).path, '/item/' + self.ITEM)
        self.assertEqual([body for _, path, body in self.calls if path == '/workshop/view'][-1],
                         {'entity_id': self.ITEM, 'include_nested': False})
        self.page.evaluate("window.task6Harness.openNativeRecord('" + self.ITEM + "')")
        self.page.get_by_role('button', name='Back').wait_for(state='visible')
        prior_refresh = self.page.evaluate('window.task6Harness.snapshot().viewData.refreshed_at')
        self.page.locator('.workflow-back').click()
        self._wait_for_fixture(
            lambda: self.page.evaluate("(() => {const s=window.task6Harness.snapshot();return s.viewData?.refreshed_at!==" +
                                       json.dumps(prior_refresh) + "&&s.viewData?.selection?.target_id===" +
                                       json.dumps(self.ITEM) + "})()"),
            'Back applies the completed native-target refresh')
        self.assertTrue(any(path == '/workshop/view' and body ==
                            {'entity_id': self.ITEM, 'include_nested': False}
                            for _, path, body in self.calls))
        self.assertEqual(urlsplit(self.page.get_by_role('link', name='Open native record', exact=True)
                                  .get_attribute('href')).path, '/item/' + self.ITEM)
        # Deliberately selecting the same highlighted drawing changes the target
        # from Camera back to its containing Rack, even though the drawing id is stable.
        self.page.get_by_role('button', name='Hide workshop sidebar').click()
        self.page.get_by_role('button', name='Show workshop sidebar').wait_for(state='visible')
        self.assertEqual(self.page.get_by_role('button', name='Show workshop sidebar').get_attribute('aria-expanded'), 'false')
        drawing = self.page.locator('[data-workshop-object="' + self.DRAWING + '"]')
        drawing.scroll_into_view_if_needed()
        bounds = drawing.bounding_box()
        hit = self.page.evaluate("p=>document.elementFromPoint(p.x,p.y)?.closest('[data-workshop-object]')?.getAttribute('data-workshop-object')||null",
                                 {'x': bounds['x'] + bounds['width'] / 2, 'y': bounds['y'] + bounds['height'] / 2})
        self.assertEqual(hit, self.DRAWING, 'The actual touch point is centered on the intended map drawing.')
        drawing.evaluate("node=>{window.touchMapTrace=[];for(const type of ['pointerdown','pointerup'])node.addEventListener(type,event=>window.touchMapTrace.push({type:event.type,pointerType:event.pointerType,target:event.target.closest('[data-workshop-object]')?.getAttribute('data-workshop-object')}),true)}")
        self.page.touchscreen.tap(bounds['x'] + bounds['width'] / 2, bounds['y'] + bounds['height'] / 2)
        try:
            self._wait_for_fixture(lambda: any(path == '/workshop/view' and body ==
                                           {'entity_id': self.RACK, 'include_nested': False}
                                           for _, path, body in self.calls),
                                   'Touch selecting the highlighted drawing changes target to Rack')
        except AssertionError as error:
            self.fail(str(error) + ' Pointer trace: ' + json.dumps(self.page.evaluate('window.touchMapTrace')))
        self.page.evaluate("async code=>{scanPurpose='workshop_map';await routeScan(code)}", '/item/' + self.ITEM)
        drawing.focus()
        drawing.press('Enter')
        self._wait_for_fixture(lambda: any(path == '/workshop/view' and body ==
                                           {'entity_id': self.RACK, 'include_nested': False}
                                           for _, path, body in self.calls),
                               'same drawing selection refreshes the native Rack target')
        self.assertEqual(urlsplit(self.page.get_by_role('link', name='Open native record', exact=True)
                                  .get_attribute('href')).path, '/location/' + self.RACK)
        self.page.evaluate("window.task6Harness.setScanPurpose(null)")
        self.page.evaluate("window.task6Harness.routeScan('CAM-9')")
        self.assertTrue(any(call[1] == '/scan' for call in self.calls),
                        'Non-map scanner purposes keep the existing generic scan route.')
        self.assertEqual(self.errors, [])

    def test_terminal_boxed_selection_uses_projection_status_and_full_storage_path(self):
        box_id = '88888888-8888-4888-8888-888888888888'
        self.view['path'].insert(-1, {'id': box_id, 'name': 'Box 7', 'is_location': False,
                                     'parent_id': self.parents[1]['id']})
        self.view['contents'] = [{'id': box_id, 'name': 'Box 7', 'assetId': 'BOX-7',
                                  'condition': 'Ready', 'checkout_blocker': None,
                                  'checked_out': False, 'parent': {'id': self.parents[1]['id']}}]
        self.view['counts'] = {'assigned': 1, 'checked_out': 0, 'available': 1, 'needs_attention': 0}
        self.selection_status = {'condition': 'Broken', 'checked_out': False,
                                 'blocker': 'Condition: Broken'}
        self.page.evaluate("window.task6Harness.setScanPurpose('workshop_map')")
        self.page.evaluate("window.task6Harness.routeScan('/item/" + self.ITEM + "')")
        rendered = self.page.locator('.workshop-native-details').inner_text()
        contents = self.page.locator('.workshop-native-contents')
        observed = {
            'status': next((line for line in rendered.splitlines() if line.startswith('Condition:')), None),
            'storage': next((line for line in rendered.splitlines() if line.startswith('Assigned storage:')), None),
            'guidance': next((line for line in rendered.splitlines() if line.startswith('Stored on ')), None),
            'box_in_scope': contents.get_by_text('Box 7', exact=False).count() == 1,
            'selected_item_in_direct_contents': contents.locator('[data-native-id="' + self.ITEM + '"]').count() > 0,
            'borrower_leaked': 'Private Borrower' in rendered,
        }
        expected = {
            'status': 'Condition: Broken · Not checked out · Condition: Broken',
            'storage': 'Assigned storage: The Cage / Shelf 1 / Box 7',
            'guidance': 'Stored on Shelf 1; map highlights The Cage (' + self.RACK + ').',
            'box_in_scope': True, 'selected_item_in_direct_contents': False,
            'borrower_leaked': False,
        }
        self.assertEqual(observed, expected,
                         'A boxed item status is separate from direct contents, and guidance names its actual location/destination.')
        views = [row for row in self.calls if row[1] == '/workshop/view' and row[2] ==
                 {'entity_id': self.ITEM, 'include_nested': False}]
        self.assertEqual(len(views), 1)
        self.assertEqual(self.unexpected_requests, [])
        self.assertEqual(self.errors, [])

    def test_terminal_duplicate_cages_keep_full_path_and_uuid_choices(self):
        self._open_editing_map()
        self._select_first_drawing()
        search = self.page.get_by_role('searchbox', name='Search native equipment and storage')
        search.fill('The Cage')
        results = self.page.locator('.workshop-native-search-results button')
        self.assertEqual(results.count(), 2)
        rows = [(results.nth(index).inner_text(), results.nth(index).get_attribute('data-native-id'))
                for index in range(results.count())]
        self.assertIn(('The Cage · 1 · The Cage', self.RACK), rows)
        self.assertIn(('The Cage · 2-A · Rack B / The Cage',
                       '99999999-9999-4999-8999-999999999999'), rows)
        self.assertEqual(len({native_id for _, native_id in rows}), 2)
        self.assertEqual(self.errors, [])

    def test_terminal_nested_scope_and_status_filters(self):
        self._open_editing_map()
        self._select_first_drawing()
        contents = self.page.locator('.workshop-native-contents')
        self.assertFalse(contents.get_by_text('Camera', exact=False).count(),
                         'A Rack view excludes grandchildren unless nested contents are requested.')
        nested = self.page.get_by_label('Include nested contents')
        nested.check()
        contents.get_by_text('Camera', exact=False).wait_for()
        self.assertTrue(self.page.get_by_text('1 assigned · 0 checked out · 1 available · 0 need attention. Counts are equipment records and may overlap.',
                                              exact=True).is_visible())
        self.page.get_by_label('Equipment status filter').select_option('checked_out')
        self.assertTrue(self.page.get_by_text('No equipment records in this selected scope.', exact=True).is_visible())
        self.page.get_by_label('Equipment status filter').select_option('available')
        self.assertTrue(contents.get_by_text('Camera', exact=False).is_visible())
        self.assertEqual(self.errors, [])

    def test_terminal_unavailable_view_never_reuses_old_status(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.get_by_label('Include nested contents').check()
        self.page.locator('.workshop-native-contents').get_by_text('Camera', exact=False).wait_for()
        self.fail_view_once = True
        self.page.locator('.workshop-native-details').get_by_role('button', name='Refresh native status').click()
        self.page.get_by_text('Native status unavailable: Workshop view is unavailable.', exact=True).wait_for()
        self.assertFalse(self.page.locator('.workshop-native-contents').get_by_text('Camera', exact=False).count(),
                         'A failed refresh must not present an earlier status as current.')
        self.page.locator('.workshop-native-details').get_by_role('button', name='Refresh native status').click()
        self.page.locator('.workshop-native-contents').get_by_text('Camera', exact=False).wait_for()
        self._assert_fixture_network_errors(statuses=[('/workshop/view', 503)])

    def test_terminal_deferred_view_after_navigation_does_not_repaint_dashboard(self):
        self.defer_initial_view = True
        self.page.locator('#layout-nav').click()
        self.page.locator('[data-workshop-object]').wait_for(state='visible')
        self._wait_for_fixture(lambda: len(self.pending_views) == 1, 'held initial native view')
        self.page.locator('#home-nav').click()
        self.page.locator('.dashboard').wait_for(state='visible')
        self.pending_views[0].fulfill(status=200, content_type='application/json', body=json.dumps(self.view))
        self.page.wait_for_timeout(50)
        self.assertTrue(self.page.locator('.dashboard').is_visible())
        self.assertFalse(self.page.locator('.workshop-native-details').count())
        self.assertEqual(self.errors, [])

    def test_terminal_scan_opening_cannot_select_after_map_was_revisited(self):
        self._use_task5_layout_fixture()
        self.defer_workshop_open = True
        self.page.evaluate("code=>{scanPurpose='workshop_map';window.originalMapScan=routeScan(code);return true}", '/item/' + self.ITEM)
        self._wait_for_fixture(lambda: len(self.pending_workshop_gets) == 1,
                               'held map opening after resolver success')
        self.page.locator('#home-nav').click()
        self.page.locator('.dashboard').wait_for(state='visible')
        self.page.locator('#layout-nav').click()
        self.page.locator('[data-workshop-drawing="' + self.DRAWING + '"]').wait_for(state='visible')
        self.pending_workshop_gets[0].fulfill(status=200, content_type='application/json',
                                              body=json.dumps(self.layout))
        settled = self.page.evaluate('async()=>await window.originalMapScan')
        self.assertFalse(settled, 'The original scan continuation settles only after the successful held map-open response.')
        self.page.wait_for_function("window.task6Harness.snapshot().title === 'Workshop planner'")
        self.assertFalse(any(path == '/workshop/view' and body.get('entity_id') == self.ITEM
                             for _, path, body in self.calls if isinstance(body, dict)),
                         'An old map-scan opening cannot select its resolved UUID into a later map visit.')
        self.assertEqual(self.page.evaluate('window.task6Harness.snapshot().selected'), None)
        self.assertEqual(self.errors, [])

    def test_terminal_late_map_resolve_after_owner_change_is_ignored(self):
        self.defer_map_resolve = True
        with self.page.expect_request('**/workshop/resolve'):
            self.page.evaluate("code=>{scanPurpose='workshop_map';void routeScan(code)}", 'CAM-9')
        self._wait_for_fixture(lambda: len(self.pending_map_resolves) == 1, 'held map resolve')
        self.session = {'user': {'id': 'user-2', 'name': 'Replacement user'},
                        'generation': 1, 'instance': 'session-2'}
        self.page.evaluate('window.task6Harness.updateIdentity()')
        self.page.wait_for_function("document.querySelector('#identity')?.textContent === 'Replacement user'")
        self.pending_map_resolves[0].fulfill(
            status=200, content_type='application/json',
            body=json.dumps({'kind': 'entity', 'entity_id': self.ITEM, 'candidates': [],
                             'message': 'Native record resolved.'}))
        self.page.locator('.dashboard').wait_for(state='visible')
        self.assertEqual(self.page.evaluate('window.task6Harness.snapshot().title'), '')
        self.page.locator('.dashboard').wait_for(state='visible')
        self.assertFalse(self.page.locator('.workshop-view').count())
        self.assertFalse(any(path == '/session/end' for _, path, _ in self.calls))
        self.assertEqual(self.errors, [])

    def test_terminal_gate_rotation_transforms_swing_footprint(self):
        self._open_editing_map()
        self.page.get_by_role('button', name='Show workshop sidebar').click()
        self.page.get_by_role('button', name='Add object').click()
        self.page.get_by_role('button', name='Gate', exact=True).click()
        self.page.get_by_role('button', name='Rotate 90°').click()
        gate = self.page.locator('[data-workshop-object][aria-label="Gate · rotated 90 degrees"]')
        self.assertEqual(gate.get_attribute('aria-label'), 'Gate · rotated 90 degrees')
        swing = gate.locator('path')
        self.assertTrue(swing.get_attribute('d'))
        transform = swing.get_attribute('transform')
        self.assertTrue(transform.startswith('rotate(90 '), transform)
        center = [float(value) for value in transform.removeprefix('rotate(90 ').rstrip(')').split()]
        self.assertAlmostEqual(center[0], 2.4)
        self.assertAlmostEqual(center[1], 24)
        bounds = gate.evaluate("""gate=>{const frame=gate.querySelector('rect').getBoundingClientRect(),glyph=gate.querySelector('path').getBoundingClientRect();return {frame:{left:frame.left,right:frame.right,top:frame.top,bottom:frame.bottom},glyph:{left:glyph.left,right:glyph.right,top:glyph.top,bottom:glyph.bottom,width:glyph.width,height:glyph.height}}}""")
        self.assertGreater(bounds['glyph']['width'], 0)
        self.assertGreater(bounds['glyph']['height'], 0)
        for edge in ('left', 'top'):
            self.assertGreaterEqual(bounds['glyph'][edge], bounds['frame'][edge] - 0.5)
        for edge in ('right', 'bottom'):
            self.assertLessEqual(bounds['glyph'][edge], bounds['frame'][edge] + 0.5)
        stored = self.page.evaluate("window.task6Harness.snapshot().draft.objects.find(row=>row.kind==='Gate')")
        self.assertEqual((stored['width'], stored['height'], stored['rotation']), (0.2, 2, 90))
        self.page.get_by_role('button', name='All objects').click()
        self.page.get_by_role('button', name='Add object').click()
        self.page.get_by_role('button', name='Fence', exact=True).click()
        self.page.get_by_role('button', name='Rotate 90°').click()
        fence = self.page.locator('[data-workshop-object][aria-label="Fence · rotated 90 degrees"]')
        self.assertEqual(fence.count(), 1)
        fence_bounds = fence.evaluate("""fence=>{
          const frame=fence.querySelector('rect').getBoundingClientRect();
          const marks=[...fence.querySelectorAll('line')].map(line=>line.getBoundingClientRect());
          return {frame:{left:frame.left,right:frame.right,top:frame.top,bottom:frame.bottom},
                  marks:marks.map(mark=>({left:mark.left,right:mark.right,top:mark.top,bottom:mark.bottom}))};
        }""")
        self.assertTrue(fence_bounds['marks'], 'Rotated Fence keeps its visible hatch inside its saved footprint.')
        for mark in fence_bounds['marks']:
            self.assertGreaterEqual(mark['left'], fence_bounds['frame']['left'] - 0.5)
            self.assertLessEqual(mark['right'], fence_bounds['frame']['right'] + 0.5)
            self.assertGreaterEqual(mark['top'], fence_bounds['frame']['top'] - 0.5)
            self.assertLessEqual(mark['bottom'], fence_bounds['frame']['bottom'] + 0.5)
        fence_state = self.page.evaluate("window.task6Harness.snapshot().draft.objects.find(row=>row.kind==='Fence')")
        self.assertEqual((fence_state['width'], fence_state['height'], fence_state['rotation']), (3, 0.2, 90))

    def test_terminal_transformed_pointer_drag_preserves_world_coordinates(self):
        gate_id = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
        self.layout['layout']['objects'].append({'id': gate_id, 'name': 'Gate test', 'kind': 'Gate',
                                                 'x': 5, 'y': 5, 'width': 2, 'height': 1,
                                                 'rotation': 0, 'location_id': None})
        self._open_editing_map()
        self.page.get_by_role('button', name='Show view controls').click()
        self.page.get_by_role('button', name='Zoom in').click()
        self.page.get_by_role('button', name='Pan right').click()
        self.page.get_by_role('button', name='Turn view').click()
        before = self.page.evaluate("window.task6Harness.snapshot().draft.objects.find(row=>row.id==='" + gate_id + "')")
        self._drag_world(gate_id, 6)
        after = self.page.evaluate("window.task6Harness.snapshot().draft.objects.find(row=>row.id==='" + gate_id + "')")
        self.assertAlmostEqual(after['x'], before['x'] + 0.25, places=5)
        self.assertEqual(after['y'], before['y'])
        self.assertEqual((after['width'], after['height']), (before['width'], before['height']))
        self.assertTrue(self.page.evaluate('window.task6Harness.snapshot().dirty'))
        self.assertEqual(self.errors, [])
        self.assertEqual(self.errors, [])

    def test_terminal_native_view_started_before_save_cannot_apply_across_new_revision(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.get_by_role('button', name='Rotate 90°').click()
        before = self.page.evaluate('window.task6Harness.snapshot()')
        self.defer_initial_view = True
        self.page.evaluate('window.task6Harness.observeWorkshopRefreshes()')
        self.page.locator('.workshop-native-details').get_by_role('button', name='Refresh native status').click()
        self._wait_for_fixture(lambda: len(self.pending_views) == 1, 'native view held before Save')
        before_view = before['viewData']
        with self.page.expect_request('**/workshop/save'):
            self.page.get_by_role('button', name='Save layout').click()
        self.page.wait_for_function("""before => {
          const current=window.task6Harness.snapshot();
          return current.state.revision===8 && current.viewData?.refreshed_at!==before;
        }""", arg=before_view['refreshed_at'])
        committed = self.page.evaluate('window.task6Harness.snapshot()')
        stale = dict(self.view)
        stale['path'] = [{'id': self.ITEM, 'name': 'Stale pre-Save projection', 'is_location': False}]
        self.pending_views[0].fulfill(status=200, content_type='application/json', body=json.dumps(stale))
        self.page.evaluate('async()=>await window.task6Harness.awaitWorkshopRefreshes()')
        final = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(committed['state']['revision'], before['state']['revision'] + 1)
        self.assertEqual(final['state']['revision'], committed['state']['revision'])
        self.assertEqual(final['viewData'], committed['viewData'],
                         'A read started against the old layout cannot replace native projection after Save.')
        self.assertNotEqual(final['viewData']['path'][0]['name'], 'Stale pre-Save projection')
        self.assertEqual(self.errors, [])

    def test_terminal_native_rename_and_move_refresh_preserves_draft(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.locator('.workshop-pad button').nth(3).click()
        before = self.page.evaluate('window.task6Harness.snapshot()')
        self.parents[0]['name'] = 'Cage North'
        self.native_locations[0]['name'] = 'Cage North'
        self.parents[0]['parent_id'] = '88888888-8888-4888-8888-888888888888'
        self.native_locations[0]['parent'] = {'id': '88888888-8888-4888-8888-888888888888'}
        self.parents[1]['parent_id'] = self.RACK
        self.native_locations[1]['parent'] = {'id': self.RACK}
        self.view['path'][0]['name'] = 'Rack B'
        self.view['path'][0]['parent_id'] = None
        self.view['path'][1]['name'] = 'Cage North'
        self.view['path'][1]['parent_id'] = self.RACK
        self.page.get_by_role('button', name='Refresh native hierarchy').click()
        self.page.wait_for_function("window.task6Harness.snapshot().state.parents[0].name === 'Cage North'")
        refreshed = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(refreshed['draft']['objects'], before['draft']['objects'])
        self.assertEqual(refreshed['state']['revision'], before['state']['revision'])
        self.assertTrue(refreshed['dirty'])
        query = self.page.get_by_role('searchbox', name='Search native equipment and storage')
        query.fill('Cage North')
        self.assertTrue(self.page.locator('.workshop-native-search-results').get_by_text(
            'Cage North · 1 · Rack B / Cage North', exact=True).is_visible())
        self.assertEqual(self.errors, [])

        self.page.evaluate("window.task6Harness.setScanPurpose(null)")
        self.page.evaluate("window.task6Harness.routeScan('CAM-9')")
        self.assertTrue(any(call[1] == '/scan' for call in self.calls),
                        'Existing non-map scan purposes must retain the generic scan route.')

    def test_terminal_ambiguous_unknown_and_badge_codes_never_select_or_end_session(self):
        self._open_editing_map()
        for code in ('AMBIGUOUS', 'UNKNOWN', 'LAB:U:person-badge'):
            with self.subTest(code=code):
                self.page.evaluate("window.task6Harness.setScanPurpose('workshop_map')")
                before = self.page.evaluate('window.task6Harness.snapshot()')
                self.page.evaluate('window.task6Harness.routeScan(' + json.dumps(code) + ')')
                after = self.page.evaluate('window.task6Harness.snapshot()')
                self.assertEqual(after['title'], before['title'])
                self.assertEqual(after['selected'], before['selected'],
                                 'Ambiguous, unavailable, and person-badge codes select no drawing.')
        self.assertEqual(len([call for call in self.calls if call[1] == '/workshop/resolve']), 3)
        self.assertFalse(any(call[1] == '/scan' for call in self.calls))
        self.assertFalse(any(call[1] == '/session/end' for call in self.calls),
                         'A map read does not end the badge session.')
        self.assertEqual(self.errors, [])

    def test_terminal_view_controls_keyboard_undo_and_stored_footprint(self):
        self._open_editing_map()
        before = self.page.evaluate('window.task6Harness.snapshot()')
        self.page.get_by_role('button', name='Show view controls').click()
        self.page.get_by_role('button', name='Zoom in').click()
        self.page.get_by_role('button', name='Pan right').click()
        self.page.get_by_role('button', name='Fit').click()
        self.page.get_by_role('button', name='Turn view').click()
        after_view = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(after_view['draft']['objects'], before['draft']['objects'],
                         'Viewport pan, zoom, fit and turn never edit saved geometry.')
        self._select_first_drawing()
        self.page.get_by_role('button', name='Rotate 90°').click()
        turned = self.page.evaluate('window.task6Harness.snapshot().draft.objects[0]')
        self.assertEqual((turned['width'], turned['height']), (3, 2))
        self.assertEqual(turned['rotation'], 90)
        self.assertTrue(self.page.evaluate('window.task6Harness.snapshot().dirty'))
        self.assertTrue(self.page.get_by_role('button', name='Undo').is_visible(),
                        'A confirmed local edit records undo even inside the primary confirmation callback.')
        self.page.get_by_role('button', name='Undo').click()
        undone = self.page.evaluate('window.task6Harness.snapshot().draft.objects[0]')
        self.assertEqual((undone['width'], undone['height'], undone['rotation']), (3, 2, 0))
        heights = self.page.locator('.workshop-view button').evaluate_all(
            "nodes=>nodes.filter(b=>b.offsetParent!==null).map(b=>b.getBoundingClientRect().height)")
        self.assertTrue(heights and min(heights) >= 44,
                        'Visible Terminal workshop controls must remain touch-sized at 800×480.')
        self.assertEqual(self.errors, [])

    def test_terminal_confirm_remove_records_undo_and_dirty_state(self):
        self._open_editing_map()
        self._select_first_drawing()
        before = self.page.evaluate('window.task6Harness.snapshot()')
        self.page.get_by_role('button', name='Remove drawing').click()
        self.page.get_by_role('button', name='Confirm').click()
        after = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertTrue(after['dirty'])
        self.assertEqual(after['draft']['objects'], [])
        self.assertTrue(self.page.get_by_role('button', name='Undo').is_visible())
        self.page.get_by_role('button', name='Undo').click()
        undone = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(undone['draft'], before['draft'])
        self.assertTrue(undone['dirty'])
        self.assertEqual(self.errors, [])

    def test_terminal_native_photo_gallery_and_editor_return(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.locator('.workshop-pad button').nth(3).click()
        expected_view = {'entity_id': self.RACK, 'include_nested': False}
        self.assertTrue(any(path == '/workshop/view' and body == expected_view
                            for _, path, body in self.calls),
                        'Selecting a linked native location must load its authorized view by UUID.')
        photo = self.page.locator('img[alt="The Cage shelving"]')
        photo.wait_for(state='visible')
        self.assertEqual(urlsplit(photo.get_attribute('src')).path, '/api/file')
        record = self.page.get_by_role('link', name='Open native record', exact=True)
        editor = self.page.get_by_role('link', name='Edit native photos', exact=True)
        self.assertEqual(urlsplit(record.get_attribute('href')).path, '/location/' + self.RACK)
        self.assertEqual(urlsplit(editor.get_attribute('href')).path, '/location/' + self.RACK + '/edit')
        before = self.page.evaluate('window.task6Harness.snapshot()')
        with self.context.expect_page() as popup_info:
            editor.click()
        popup = popup_info.value
        popup.wait_for_url('**/location/' + self.RACK + '/edit')
        self.assertEqual(self.native_visits, ['/location/' + self.RACK + '/edit'],
                         'The native editor link is served only by the disposable fixture origin.')
        popup.close()
        after = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(after['draft']['objects'][0]['x'], before['draft']['objects'][0]['x'])
        self.assertEqual(after['state']['revision'], before['state']['revision'])
        self.assertTrue(after['dirty'])
        self.assertEqual(self.errors, [])

    def test_terminal_order_recovery_and_photo_return(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.get_by_role('button', name='Open shelves & bins').click()
        review = self.page.get_by_role('button', name='Review shelf order')
        review.wait_for(state='visible')
        self.assertTrue(review.is_visible(), 'Order review is available after opening the selected native Rack.')
        self.lose_order_response = True
        self.page.get_by_role('button', name='Review shelf order').click()
        self.assertTrue(self.page.get_by_role('heading', name='Review shelf order').is_visible())
        self.page.get_by_role('button', name='Move down').first.click()
        self.page.get_by_role('button', name='Confirm shelf order').click()
        self.page.get_by_text('A previous shelf order has an unconfirmed result.', exact=False).wait_for()
        self.assertEqual(len(self.shelf_orders), 1)
        submitted = self.shelf_orders[0]
        request_key = submitted['request_key']
        self.assertRegex(request_key, r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
        self.assertEqual(submitted, {'entity_id': self.RACK, 'updated_at': 'rack-v1',
                                     'shelf_ids': [self.parents[2]['id'], self.parents[1]['id']],
                                     'request_key': request_key})
        pending = json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:user-1')"))
        marker = json.loads(self.page.evaluate("localStorage.getItem('workshop-order:user-1:" + self.RACK + "')"))
        self.assertEqual(len(pending), 1)
        self.assertEqual({key: pending[0][key] for key in ('key', 'path', 'label', 'subject')},
                         {'key': request_key, 'path': 'workshop/shelf-order',
                          'label': 'Shelf order · The Cage', 'subject': self.RACK})
        self.assertTrue(pending[0]['at'])
        self.assertEqual(marker['request_key'], request_key)
        self.assertEqual(marker['owner_id'], 'user-1')
        self.assertEqual(marker['rack_id'], self.RACK)
        self.assertEqual(marker['shelf_ids'], submitted['shelf_ids'])
        self.assertFalse(self.page.get_by_role('button', name='Confirm shelf order').count())
        self.page.get_by_role('button', name='Check saved order result').click()
        self._wait_for_fixture(lambda: len(self.operation_checks) == 1, 'shelf-order result check from Storage')
        self.assertEqual(self.operation_checks, [{'request_key': request_key}],
                         'Recovery checks the original shelf-order key and never resubmits it.')
        self.page.get_by_role('button', name='Acknowledge no operation started').click()
        self.assertEqual(json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:user-1')")), [])
        self.assertIsNone(self.page.evaluate("localStorage.getItem('workshop-order:user-1:" + self.RACK + "')"))
        self.assertEqual(len(self.shelf_orders), 1)
        self.assertEqual(len(self.operation_checks), 1)
        self._assert_fixture_network_errors(aborted=['/workshop/shelf-order'])

    def test_terminal_shelf_order_confirm_submits_exact_review_once(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.get_by_role('button', name='Open shelves & bins').click()
        self.page.get_by_role('button', name='Review shelf order').click()
        self.page.get_by_role('button', name='Confirm shelf order').click()
        self.page.get_by_text('Shelf order saved. Native equipment identities were unchanged.', exact=True).wait_for()
        self.assertEqual(len(self.shelf_orders), 1)
        payload = self.shelf_orders[0]
        self.assertEqual(payload['entity_id'], self.RACK)
        self.assertEqual(payload['updated_at'], 'rack-v1')
        self.assertEqual(set(payload['shelf_ids']), {self.parents[1]['id'], self.parents[2]['id']})
        self.assertRegex(payload['request_key'], r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
        self.assertEqual(json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:user-1')")), [])
        self.assertIsNone(self.page.evaluate("localStorage.getItem('workshop-order:user-1:" + self.RACK + "')"))
        self.assertEqual(self.errors, [])

    def test_terminal_shelf_order_committed_lost_reply_uses_status_only(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.get_by_role('button', name='Open shelves & bins').click()
        self.page.get_by_role('button', name='Review shelf order').click()
        self.lose_order_response = True
        self.page.get_by_role('button', name='Confirm shelf order').click()
        self.page.get_by_text('A previous shelf order has an unconfirmed result.', exact=False).wait_for()
        request_key = self.shelf_orders[0]['request_key']
        self.operation_response = {'id': 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
                                   'status': 'completed', 'action': 'workshop_shelf_order',
                                   'native_job': True}
        self.page.get_by_role('button', name='Check saved order result').click()
        self.page.get_by_text('The saved shelf order is completed. It was not resubmitted.', exact=True).wait_for()
        self.assertEqual(len(self.shelf_orders), 1)
        self.assertEqual([body for _, path, body in self.calls if path == '/operation/status'],
                         [{'request_key': request_key}])
        self.assertEqual(json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:user-1')")), [])
        self.assertIsNone(self.page.evaluate("localStorage.getItem('workshop-order:user-1:" + self.RACK + "')"))
        self._assert_fixture_network_errors(aborted=['/workshop/shelf-order'])

    def test_terminal_status_reply_after_owner_change_keeps_original_recovery_key(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.get_by_role('button', name='Open shelves & bins').click()
        self.page.get_by_role('button', name='Review shelf order').click()
        self.lose_order_response = True
        self.page.get_by_role('button', name='Confirm shelf order').click()
        self.page.get_by_text('A previous shelf order has an unconfirmed result.', exact=False).wait_for()
        request_key = self.shelf_orders[0]['request_key']
        self.defer_operation_status = True
        self.page.get_by_role('button', name='Check saved order result').click()
        self._wait_for_fixture(lambda: len(self.pending_operation_status) == 1, 'held shelf-order status')
        self.assertEqual(self.operation_checks, [{'request_key': request_key}])
        self.session = {'user': {'id': 'user-2', 'name': 'Replacement user'},
                        'generation': 1, 'instance': 'session-2'}
        self.page.evaluate('window.task6Harness.updateIdentity()')
        self.page.wait_for_function("document.querySelector('#identity')?.textContent === 'Replacement user'")
        self.assertEqual(len(self.pending_operation_status), 1)
        self.pending_operation_status[0].fulfill(status=200, content_type='application/json',
                                                 body=json.dumps({'id': 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
                                                                  'status': 'completed', 'action': 'workshop_shelf_order',
                                                                  'native_job': True}))
        self.page.wait_for_timeout(50)
        self.assertEqual(len(self.shelf_orders), 1)
        self.assertEqual(json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:user-1')"))[0]['key'], request_key)
        self.assertIsNotNone(self.page.evaluate("localStorage.getItem('workshop-order:user-1:" + self.RACK + "')"))
        self.assertEqual(json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:user-2') || '[]'")), [])
        self._assert_fixture_network_errors(aborted=['/workshop/shelf-order'])

    def test_terminal_shelf_order_wrong_status_remains_locked(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.get_by_role('button', name='Open shelves & bins').click()
        self.page.get_by_role('button', name='Review shelf order').click()
        self.lose_order_response = True
        self.page.get_by_role('button', name='Confirm shelf order').click()
        request_key = self.shelf_orders[0]['request_key']
        self.operation_response = {'id': 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
                                   'status': 'completed', 'action': 'print_label', 'native_job': True}
        self.page.get_by_role('button', name='Check saved order result').click()
        self.page.get_by_text('The returned status does not match this saved shelf-order request. It remains locked for inspection.', exact=True).wait_for()
        self.assertEqual([body for _, path, body in self.calls if path == '/operation/status'],
                         [{'request_key': request_key}])
        self.assertEqual(len(self.shelf_orders), 1)
        pending = json.loads(self.page.evaluate("localStorage.getItem('workshop-pending:user-1')"))
        self.assertEqual(pending[0]['key'], request_key)
        self.assertIsNotNone(self.page.evaluate("localStorage.getItem('workshop-order:user-1:" + self.RACK + "')"))
        self._assert_fixture_network_errors(aborted=['/workshop/shelf-order'])

    def test_terminal_native_location_return_preserves_map_selection(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.locator('.workshop-pad button').nth(3).click()
        self.page.get_by_role('button', name='Open shelves & bins').click()
        self.page.get_by_role('button', name='Open record').wait_for(state='visible')
        self.page.get_by_role('button', name='Open record').click()
        self.page.get_by_role('button', name='Show on map').wait_for(state='visible')
        self.page.get_by_role('button', name='Show on map').click()
        self.page.locator('[data-workshop-object]').wait_for(state='visible')
        restored = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(restored['draft']['objects'][0]['x'], 1.25)
        self.assertEqual(restored['state']['revision'], 7)
        self.assertTrue(restored['dirty'])
        self.assertTrue(any(path == '/workshop/view' and body == {'entity_id': self.RACK,
                                                                  'include_nested': False}
                            for _, path, body in self.calls),
                        'Returning from the native location must refresh its map view by UUID.')
        self.assertEqual(self.errors, [])

    def test_terminal_dirty_draft_suspends_before_leave_and_identity_change(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.locator('.workshop-pad button').nth(3).click()
        self.page.locator('.workshop-pad button').nth(3).click()
        draft = self.page.evaluate('window.task6Harness.snapshot().draft')
        self.assertEqual(draft['objects'][0]['x'], 1.5)

        # Exercise the actual shared Back handler and its complete map snapshot.
        self.page.get_by_role('button', name='Open shelves & bins').click()
        self.page.get_by_role('button', name='Back', exact=True).click()
        self.page.wait_for_function("window.task6Harness.snapshot().title === 'Workshop'")
        restored = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(restored['draft']['objects'][0]['x'], 1.5)
        self.assertEqual(restored['state']['revision'], 7)
        self.assertTrue(restored['dirty'])

        # Prime the final identity handler, then let the interval captured by index.html
        # observe expiry. The map draft belongs to the original user/group/session.
        self.page.evaluate('window.task6Harness.updateIdentity()')
        polls_before_expiry = self.session_polls
        self.expire_session = True
        self.page.wait_for_function("document.querySelector('#identity')?.textContent === 'Scan badge to identify yourself'",
                                    timeout=7000)
        self.assertFalse(self.page.locator('.workshop-view').count(),
                         'The captured poll should leave the map before changing identity.')
        suspended = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(suspended['identity']['instance'], 'session-1')
        self.assertEqual(suspended['identity']['generation'], 2)
        snapshots = self.page.evaluate('window.task6Harness.storageSnapshots()')
        original_owner = [row for row in snapshots if 'user-1' in row['value'] and
                          'session-1' in row['value']]
        self.assertTrue(original_owner, 'Expiry must suspend the draft under its observed owner/session.')
        saved = json.loads(original_owner[0]['value'])
        saved_text = json.dumps(saved, sort_keys=True)
        self.assertIn('"dirty": true', saved_text)
        self.assertIn('"revision": 7', saved_text)
        self.assertIn('"undo"', saved_text)
        def drawing_rows(value):
            found = []
            if isinstance(value, dict):
                if value.get('id') == self.DRAWING and 'x' in value:
                    found.append(value)
                for child in value.values():
                    found.extend(drawing_rows(child))
            elif isinstance(value, list):
                for child in value:
                    found.extend(drawing_rows(child))
            return found
        drawing_history = drawing_rows(saved)
        self.assertTrue(any(row.get('x') == 1.5 and row.get('y') == 2 and row.get('width') == 3 and
                            row.get('height') == 2 and row.get('rotation') == 0 and
                            row.get('location_id') == self.RACK for row in drawing_history),
                        'Suspended JSON keeps the full current geometry and native UUID link.')
        self.assertTrue({row.get('x') for row in drawing_history}.issuperset({1, 1.25, 1.5}),
                        'The original undo geometry must remain recoverable.')
        self.assertGreater(self.session_polls, polls_before_expiry,
                           'Expiry must be observed by the 3-second callback captured from index.html.')

        self.expire_session = False
        self.session = {'user': {'id': 'user-2', 'name': 'Replacement user'},
                        'generation': 1, 'instance': 'session-2'}
        self.page.wait_for_function("document.querySelector('#identity')?.textContent === 'Replacement user'",
                                    timeout=7000)
        self._open_editing_map()
        replacement = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(replacement['draft']['objects'][0]['x'], 1,
                         'A replacement user sees the saved layout, never the previous owner’s draft.')
        self.assertFalse(replacement['dirty'])
        self.assertEqual(self.errors, [])

    def test_terminal_pending_save_blocks_geometry_mutation(self):
        self._open_editing_map()
        self._select_first_drawing()
        self.page.locator('.workshop-pad button').nth(3).click()
        before = self.page.evaluate('window.task6Harness.snapshot()')
        self.defer_save = True
        with self.page.expect_request('**/workshop/save'):
            self.page.get_by_role('button', name='Save layout').click()
        self.page.wait_for_function("document.querySelector('.workshop-message') || document.querySelector('.workshop-pad button')")
        self._wait_for_fixture(lambda: len(self.pending_saves) == 1, 'held map save response')

        # Shared busy state must freeze SVG selection/drag and edit controls as well
        # as the Save button; otherwise an old saved response overwrites new geometry.
        self._drag_world(self.DRAWING, 6)
        move_right = self.page.locator('.workshop-pad button').nth(3)
        self.assertTrue(move_right.is_visible())
        if move_right.is_disabled():
            move_right.dispatch_event('click')
        else:
            move_right.click()
        during = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(len(self.saved_layouts), 1, 'A blocked edit cannot trigger a second Save.')
        self.page.locator('#layout-nav').click()
        self.assertEqual(self.page.evaluate('window.task6Harness.snapshot().title'), 'Workshop',
                         'A competing navigation is refused while the map save remains pending.')

        # The original owner may expire while the response body is still pending.
        # Do not apply the old save into a replacement identity; defer that observed
        # transition until this response has been consumed.
        self.session = {'user': {'id': 'user-2', 'name': 'Replacement user'},
                        'generation': 1, 'instance': 'session-2'}
        self.page.evaluate('window.task6Harness.updateIdentity()')
        self.assertEqual(self.page.locator('#identity').inner_text(), 'Map tester')
        self.assertEqual(self.page.evaluate('window.task6Harness.snapshot().identity.instance'), 'session-1')

        body = self.saved_layouts[0]
        self.pending_saves[0].fulfill(status=200, content_type='application/json',
                                      body=json.dumps({'revision': body['revision'] + 1,
                                                       'layout': body['layout']}))
        self.page.wait_for_function("window.task6Harness.snapshot().state.revision === 8")
        self.assertEqual(during['draft']['objects'][0]['x'], before['draft']['objects'][0]['x'],
                         'Canvas controls and pointer edits must be frozen until the save result arrives.')
        self.assertEqual(during['state']['revision'], before['state']['revision'])
        self.assertEqual(self.page.evaluate('window.task6Harness.snapshot().draft.objects[0].x'),
                         before['draft']['objects'][0]['x'])
        self.page.wait_for_function("document.querySelector('#identity')?.textContent === 'Replacement user'", timeout=4000)
        self._open_editing_map()
        replacement = self.page.evaluate('window.task6Harness.snapshot()')
        self.assertEqual(replacement['draft']['objects'][0]['x'], before['draft']['objects'][0]['x'])
        self.assertFalse(replacement['dirty'])
        self.assertEqual(self.unexpected_requests, [])
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
