import json
import pathlib
import base64
from io import BytesIO
import os
import time
import unittest
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError

from playwright.sync_api import sync_playwright
from PIL import Image


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
        catalog = (ROOT / 'homebox-ui/overlay/lib/workshop-object-catalog.js').read_text(encoding='utf-8')
        catalog = catalog.replace('export const workshopObjectPresets', 'const workshopObjectPresets').replace('export function workshopPresetForDrawing', 'function workshopPresetForDrawing')
        recovery = (ROOT / 'homebox-ui/overlay/lib/label-print-recovery.js').read_text(encoding='utf-8')
        recovery = recovery.replace('export function ', 'function ')
        cls.source = (ROOT / 'homebox-ui/overlay/lib/workshop-tools.js').read_text(encoding='utf-8').replace(
            'import { mountLabelDesigner, exportReviewedPaper } from "./label-editor.js";\n',
            catalog + '\nconst mountLabelDesigner=()=>{}; const exportReviewedPaper=()=>{};\n')
        cls.source = cls.source.replace('import { workshopObjectPresets, workshopPresetForDrawing } from "./workshop-object-catalog.js";\n', '')
        cls.source = cls.source.replace('import { labelPrintFailure, pendingLabelPrint } from "./label-print-recovery.js";\n', recovery + '\n')
        cls.source = cls.source.replace('export function mountWorkshopTools', 'function mountWorkshopTools')
        cls.source += '\nwindow.mountWorkshopTools=mountWorkshopTools;window.workshopObjectPresets=workshopObjectPresets;window.workshopPresetForDrawing=workshopPresetForDrawing;'
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
        self.context.route('https://fixture.invalid/workshop/objects/**', self._catalog_asset)
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
             window.writes=[]; window.navigate=[]; window.apiCalls=[]; window.failViewOnce=false; const pendingStorageKey=()=>`workshop-pending:${window.fixtureContext.value.group.id}:${window.fixtureContext.value.user.id}`;window.fixtureWorkshop={context,refresh:async()=>window.fixtureContext.value,pending:()=>JSON.parse(localStorage.getItem(pendingStorageKey())||'[]'),forget:key=>{const rows=JSON.parse(localStorage.getItem(pendingStorageKey())||'[]');localStorage.setItem(pendingStorageKey(),JSON.stringify(rows.filter(row=>row.key!==key)))},request:async(path,data,identity)=>{window.apiCalls.push([path,data,identity]); const route=path.split('?')[0]; if(route==='workshop'){if(window.deferWorkshopRefresh){window.workshopRefreshStarted=true;await new Promise(resolve=>window.releaseWorkshopRefresh=resolve);window.deferWorkshopRefresh=false;}return structuredClone(window.fixtureLayout);} if(route==='equipment')return structuredClone(window.fixtureSearchEquipment||[{id:'22222222-2222-4222-8222-222222222222',name:'Camera',assetId:'CAM-9',serialNumber:'SN-9',manufacturer:'Northwind',parent:{id:'55555555-5555-4555-8555-555555555555'}}]); if(route==='locations')return structuredClone(window.fixtureSearchLocations||window.fixtureLayout.locations); if(route==='entity')return {entity:{id:'22222222-2222-4222-8222-222222222222',name:'Camera',assetId:'CAM-9',parent:{id:'55555555-5555-4555-8555-555555555555'}},condition:'Ready',blocker:null}; if(route==='loans')return [{entity_id:'22222222-2222-4222-8222-222222222222',borrower:'Private Borrower'}]; if(route==='workshop/view'){if(window.failViewOnce){window.failViewOnce=false;throw new Error('fixture read failure')} if(path.includes('22222222-2222-4222-8222-222222222222'))return structuredClone(path.includes('nested=1')?window.fixtureViews.nestedView:window.fixtureViews.itemView);return structuredClone(window.fixtureViews.locationView);} if(route==='workshop/resolve')return data.code==='UNKNOWN-MFR'?{kind:'unknown',entity_id:null,candidates:[],message:'No unique native record found.'}:{kind:'entity',entity_id:'22222222-2222-4222-8222-222222222222',candidates:[]}; if(route==='recovery')return []; if(route==='operation/status'){const status=window.fixtureOperationStatus||'not_started';return status==='not_started'?{status}:{id:'job-1',status,action:window.fixtureOperationAction||'workshop_shelf_order',native_job:true,...(window.fixtureOperationResult?{result:window.fixtureOperationResult}:{})};} return {};},write:async(path,data,label,subject)=>{window.writes.push([path,data]);if(path==='workshop/save'){window.layoutSaveStarted=true;window.layoutSaveCount=(window.layoutSaveCount||0)+1;if(window.fixtureForceSaveConflict){const error=new Error('fixture revision conflict');error.status=409;throw error;}if(window.deferLayoutSave)await new Promise(resolve=>window.releaseLayoutSave=resolve);const result={revision:data.revision+1,layout:structuredClone(data.layout)};window.fixtureOperationAction='workshop/save';window.fixtureOperationResult={schema_version:2,revision:result.revision,document:structuredClone(data.document)};window.fixtureOperationAction='workshop/save';window.fixtureOperationResult={schema_version:2,revision:result.revision,document:structuredClone(data.document)};window.fixtureLayout.revision=result.revision;window.fixtureLayout.layout=structuredClone(data.layout);window.fixtureLayout.document=structuredClone(data.document);if(window.fixtureLoseSaveResponse)throw new Error('fixture lost save response');return result;}const storageKey='workshop-pending:group-1:user-1';if(path==='workshop/shelf-order'){const rows=JSON.parse(localStorage.getItem(storageKey)||'[]');rows.push({key:data.request_key,path,label,subject,at:'2026-10-07T12:00:00Z'});localStorage.setItem(storageKey,JSON.stringify(rows));if(window.loseOrderResponse)throw new Error('fixture lost response');localStorage.setItem(storageKey,JSON.stringify(rows.filter(row=>row.key!==data.request_key)));}return {id:'order-1',status:'completed',entity_id:data.entity_id};}};window.fixtureNavigate=path=>window.navigate.push(path);window.fixtureNotifications=[];window.fixtureNotify=text=>window.fixtureNotifications.push(text);window.fixtureSelection={entityId:'11111111-1111-4111-8111-111111111111',drawingId:'33333333-3333-4333-8333-333333333333'};window.mountFixture=()=>window.mountWorkshopTools(document.querySelector('#root'),'workshop',window.fixtureWorkshop,window.fixtureNavigate,window.fixtureNotify,window.fixtureSelection);window.instance=window.mountFixture();
        '''
        self.page.evaluate(init)
        self.page.wait_for_timeout(250)
        if not self.page.locator('#workshop-content, .room-planner').count():
            self.fail('The real Workshop host did not render: ' + repr(self.errors) + ' body=' + self.page.locator('body').inner_text() + ' instance=' + str(self.page.evaluate('typeof window.instance')))

    def _catalog_asset(self, route):
        name=urlsplit(route.request.url).path.rsplit('/',1)[-1]
        asset=ROOT/'homebox-ui/overlay/public/workshop/objects'/name
        if not asset.is_file():
            route.abort()
            return
        route.fulfill(status=200,content_type='image/svg+xml',body=asset.read_text(encoding='utf-8'))

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


    def test_workshop_map_starts_blank_and_palette_creates_only_selected_drawing(self):
        self.install_rooms4_plan({'version':2,'rooms':[]})
        self.page.get_by_role('button',name='Create room',exact=True).click()
        self.assertEqual(self.page.locator('[data-workshop-drawing]').count(),0)
        self.assertEqual(self.page.get_by_label('Room title').input_value(),'New room')
        palette=self.page.get_by_role('region',name='Object palette')
        self.assertTrue(palette.get_by_role('button',name='Rack',exact=True).count())
        self.assertTrue(palette.locator('.planner-object-icon').count())
        search=palette.get_by_label('Search objects')
        search.fill('bin')
        self.assertTrue(palette.get_by_role('button',name='Bin',exact=True).is_visible())
        self.assertEqual(palette.get_by_role('button',name='Rack',exact=True,include_hidden=True).evaluate('(el)=>getComputedStyle(el).display'),'none')
        self.assertEqual(palette.get_by_role('button',name='Rack',exact=True).count(),0)
        search.fill('')
        palette.get_by_role('button',name='Bin',exact=True).click()
        svg=self.page.locator('.planner-svg')
        svg_box=svg.bounding_box()
        svg.click(position={'x':svg_box['width']/2,'y':svg_box['height']/2})
        self.assertEqual(self.page.locator('[data-workshop-drawing]').count(),1)
        self.page.get_by_role('button',name='Save all room changes').click()
        saved=self.page.evaluate('window.writes.at(-1)[1].document')
        self.assertEqual(len(saved['rooms']),1)
        self.assertEqual([item['kind'] for item in saved['rooms'][0]['objects']],['Bin'])
        self.assertEqual(self.errors,[])

    def test_map_browse_hides_palette_and_machine_presets_keep_native_kind(self):
        self.page.set_viewport_size({'width':1277,'height':718})
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawings=[
            {'id':DRAWING,'name':'A very long shelf caption','kind':'Rack','x':1,'y':1,'width':3,'height':2,'rotation':0,'location_id':LOCATION},
            {'id':RACK,'name':'Long caption for this bench that cannot fit in its drawing '*2,'kind':'Misc','x':6,'y':1,'width':3,'height':2,'rotation':0,'location_id':None},
        ]
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':drawings}]}
        self.install_rooms4_plan(document,selected_drawing=DRAWING)
        self.page.locator('html').evaluate("el=>{el.style.setProperty('--foreground','0 0% 98%');el.style.setProperty('--background','220 20% 12%')}")
        palette=self.page.locator('.planner-palette')
        self.assertEqual(palette.evaluate('(el)=>getComputedStyle(el).display'),'none')
        self.assertEqual(self.page.get_by_role('button',name='Objects',exact=True).count(),0)
        self.assertEqual(self.page.locator('[data-workshop-drawing="'+DRAWING+'"]').get_attribute('data-link-status'),'linked')
        self.assertEqual(self.page.locator('[data-workshop-drawing="'+RACK+'"]').get_attribute('data-link-status'),'drawing-only')
        self.assertEqual(self.page.locator('[data-workshop-drawing="'+DRAWING+'"] [data-link-indicator]').get_attribute('data-link-indicator'),'linked')
        self.assertEqual(self.page.locator('[data-workshop-drawing="'+RACK+'"] [data-link-indicator]').get_attribute('data-link-indicator'),'drawing-only')
        self.assertTrue(self.page.get_by_text('Linked to native storage',exact=True).is_visible())
        self.assertTrue(self.page.get_by_text('Drawing only',exact=True).is_visible())
        caption=self.page.locator('[data-workshop-drawing="'+DRAWING+'"] text')
        self.assertIsNone(caption.get_attribute('textLength'))
        self.assertIsNone(caption.get_attribute('lengthAdjust'))
        contrast=caption.evaluate('''text=>{const backing=text.parentElement.querySelector('[data-workshop-caption-backdrop]'),ink=getComputedStyle(text).fill,background=getComputedStyle(backing).fill,channels=color=>color.match(/[\\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}),lum=color=>channels(color).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0),a=lum(ink),b=lum(background);return {ink,background,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),opacity:getComputedStyle(backing).opacity}}''')
        self.assertGreaterEqual(contrast['ratio'],4.5,contrast)
        self.assertEqual(contrast['opacity'],'1')
        self.assertGreaterEqual(float(caption.get_attribute('font-size')),.38)
        long_caption=self.page.locator('[data-workshop-drawing="'+RACK+'"] text')
        full_name=drawings[1]['name']
        shown_caption=long_caption.text_content()
        self.assertTrue(shown_caption.endswith('…'))
        self.assertLess(len(shown_caption),len(full_name))
        self.assertIn(full_name,self.page.locator('[data-workshop-drawing="'+RACK+'"]').get_attribute('aria-label'))
        frame=self.page.locator('.planner-canvas-frame').bounding_box()
        self.assertLessEqual(frame['y'],330,frame)
        self.assertLessEqual(frame['y']+frame['height'],718,frame)
        save_button=self.page.locator('.planner-save-button')
        self.assertEqual(save_button.evaluate('(el)=>getComputedStyle(el).display'),'none')
        self.page.get_by_role('button',name='Edit',exact=True).click()
        self.assertEqual(save_button.evaluate('(el)=>getComputedStyle(el).display'),'flex')
        self.assertTrue(palette.is_visible())
        desktop=self.page.locator('.planner-workspace')
        desktop_state=desktop.evaluate('''el=>({width:el.clientWidth,scrollWidth:el.scrollWidth,columns:getComputedStyle(el).gridTemplateColumns})''')
        self.assertEqual(len(desktop_state['columns'].split()),3,desktop_state)
        self.assertLessEqual(desktop_state['scrollWidth'],desktop_state['width']+1,desktop_state)
        self.assertFalse(self.page.get_by_role('button',name='Objects',exact=True).is_visible())
        palette.get_by_role('button',name='3D Printer',exact=True).click()
        self.page.locator('.planner-svg').click(position={'x':200,'y':200})
        created=self.page.locator('[data-workshop-drawing].is-selected')
        self.assertEqual(created.locator('rect[data-object-shape]').get_attribute('data-object-shape'),'machine')
        save=self.page.get_by_role('button',name='Save all room changes')
        self.assertTrue(save.is_enabled(),self.page.locator('#view').inner_text())
        save.click()
        self.page.wait_for_timeout(100)
        self.assertTrue(self.page.evaluate('window.writes.length'),self.page.locator('#view').inner_text())
        saved=self.page.evaluate('window.writes.at(-1)[1].document.rooms[0].objects.at(-1)')
        self.assertEqual((saved['kind'],saved['name']),('Misc','3D Printer'))
        self.assertEqual(self.errors,[])

    def test_catalog_search_place_undo_and_named_cabinet_fallback(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        cabinet_id='66666666-6666-4666-8666-666666666666'
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[{'id':cabinet_id,'name':'Cabinet 1','kind':'Cabinet','x':1,'y':1,'width':3,'height':2,'rotation':0,'opacity':.55,'layer':'above','location_id':LOCATION}]}]}
        self.install_rooms4_plan(document,selected_drawing=cabinet_id,types=['Rack','Cabinet','Table','Workbench'])
        existing=self.page.locator('[data-workshop-drawing="'+cabinet_id+'"]')
        self.assertTrue(existing.locator('[data-workshop-artwork]').count())
        self.assertEqual(existing.locator('[data-workshop-artwork]').get_attribute('opacity'),'0.55')
        self.assertGreater(existing.locator('[data-workshop-artwork]').evaluate('(image)=>image.parentElement.children.length-1'),existing.locator('[data-workshop-artwork]').evaluate('(image)=>[...image.parentElement.children].indexOf(image)'))
        self.assertEqual(existing.get_attribute('data-link-status'),'linked')
        self.assertIn('Cabinet 1',existing.get_attribute('aria-label'))
        self.page.get_by_role('button',name='Edit',exact=True).click()
        search=self.page.get_by_role('searchbox',name='Search objects')
        search.fill('wall cabinet')
        preset=self.page.locator('.planner-preset-card[data-preset-id="wall-cabinet"]')
        self.assertTrue(preset.is_visible())
        preset.click()
        self.page.locator('.planner-svg').click(position={'x':300,'y':260})
        created=self.page.locator('[data-workshop-drawing].is-selected')
        self.assertEqual(created.locator('[data-workshop-artwork]').get_attribute('data-workshop-artwork'),'wall-cabinet')
        self.assertEqual(created.get_attribute('data-link-status'),'drawing-only')
        self.assertEqual((created.get_attribute('data-width'),created.get_attribute('data-height')),('3','1'))
        self.assertEqual(self.page.evaluate('window.writes.length'),0,'Placing a catalog drawing must not create or link native storage.')
        self.assertTrue(self.page.get_by_role('button',name='Undo',exact=True).is_enabled())
        self.page.get_by_role('button',name='Undo',exact=True).click()
        self.assertEqual(self.page.locator('[data-workshop-drawing]').count(),1)
        search.fill('wall cabinet')
        preset=self.page.locator('.planner-preset-card[data-preset-id="wall-cabinet"]')
        preset.click()
        self.page.locator('.planner-svg').focus()
        self.page.keyboard.press('Escape')
        self.assertEqual(self.page.locator('[data-workshop-drawing]').count(),1)
        self.assertIn('Placement canceled.',self.page.evaluate('window.fixtureNotifications.join("\\n")'))
        self.assertEqual(self.page.evaluate('window.writes.length'),0)
        self.assertEqual(self.errors,[])

    def test_rotated_catalog_artwork_stays_within_visual_footprint(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing={'id':DRAWING,'name':'Wall cabinet','kind':'Cabinet','x':2,'y':3,'width':3,'height':1,'rotation':90,'layer':'above','location_id':LOCATION}
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[drawing]}]}
        self.install_rooms4_plan(document,selected_drawing=DRAWING,types=['Cabinet'])
        measured=self.page.locator('[data-workshop-artwork]').evaluate('''image=>{const bounds=node=>{const r=node.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}};return {image:bounds(image),stripe:bounds(image.parentElement.querySelector('[data-workshop-layer-stripe]')),rect:bounds(image.parentElement.querySelector('rect[data-object-shape]')),opacity:image.getAttribute('opacity')}}''')
        for shape in ['image','stripe']:
            for edge in ['left','right','top','bottom']:
                self.assertAlmostEqual(measured[shape][edge],measured['rect'][edge],delta=1,msg=repr(measured))
        self.assertEqual(measured['opacity'],'1')
        self.page.get_by_role('button',name='Edit',exact=True).click()
        handle=self.page.get_by_role('button',name='Resize drawing handle')
        box=handle.bounding_box()
        self.page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2)
        self.page.mouse.down()
        self.page.mouse.move(box['x']+box['width']/2+60,box['y']+box['height']/2+35)
        self.page.mouse.up()
        resized=self.page.locator('[data-workshop-layer-stripe]').evaluate('''stripe=>{const bounds=node=>{const r=node.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}};return {stripe:bounds(stripe),rect:bounds(stripe.parentElement.querySelector('rect[data-object-shape]'))}}''')
        for edge in ['left','right','top','bottom']:
            self.assertAlmostEqual(resized['stripe'][edge],resized['rect'][edge],delta=1,msg=repr(resized))
        self.assertEqual(self.errors,[])

    def test_rotated_shelf_details_stay_inside_the_plan_footprint(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing={'id':DRAWING,'name':'Rack A1','kind':'Rack','x':2,'y':3,'width':6,'height':1.25,'rotation':90,'location_id':None}
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[drawing]}]}
        self.install_rooms4_plan(document,selected_drawing=DRAWING)
        bounds=self.page.locator('[data-workshop-drawing] rect[data-object-shape]').evaluate('''rect => {
          const box=el=>{const r=el.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}};
          const footprint=box(rect),details=[...rect.parentElement.querySelectorAll('[data-footprint-detail]')].map(box);
          return details.map(detail=>({inside:detail.left>=footprint.left-5&&detail.right<=footprint.right+5&&detail.top>=footprint.top-5&&detail.bottom<=footprint.bottom+5,detail,footprint}));
        }''')
        self.assertTrue(bounds and all(row['inside'] for row in bounds),bounds)
        self.assertEqual(self.errors,[])

    def test_rotated_caption_stays_readable_and_unrotated(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing={'id':DRAWING,'name':'Wire rack','kind':'Misc','x':2,'y':3,'width':6,'height':1.25,'rotation':90,'location_id':None}
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[drawing]}]}
        self.install_rooms4_plan(document,selected_drawing=DRAWING)
        caption=self.page.locator('[data-workshop-drawing] text')
        transform=caption.evaluate('''el=>{const m=el.getScreenCTM();return {a:m.a,b:m.b,c:m.c,d:m.d,parent:el.parentElement.getAttribute('transform')}}''')
        self.assertAlmostEqual(transform['b'],0,delta=.001, msg='Artwork rotation must not rotate caption glyphs: '+repr(transform))
        self.assertAlmostEqual(transform['c'],0,delta=.001, msg='Artwork rotation must not rotate caption glyphs: '+repr(transform))

    def test_quarter_turn_caption_uses_horizontal_drawing_width(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing={'id':DRAWING,'name':'Long caption for a wide workbench drawing','kind':'Workbench','x':2,'y':3,'width':8,'height':1.25,'rotation':90,'location_id':None}
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[drawing]}]}
        self.install_rooms4_plan(document,selected_drawing=DRAWING,types=['Workbench'])
        caption=self.page.locator('[data-workshop-drawing] text')
        shown=caption.text_content()
        transform=caption.evaluate('''el=>{const m=el.getScreenCTM();return {a:m.a,b:m.b,c:m.c,d:m.d,size:parseFloat(getComputedStyle(el).fontSize)*Math.hypot(m.a,m.b),length:el.getComputedTextLength(),maxWidth:Number(el.parentElement.getAttribute('data-width'))*.82,bounds:el.getBoundingClientRect().width}}''')
        self.assertTrue(shown.startswith('Long') and shown.endswith('…'),shown)
        self.assertAlmostEqual(transform['b'],0,delta=.001, msg='The label stays horizontal after a quarter-turn.')
        self.assertAlmostEqual(transform['c'],0,delta=.001, msg='The label stays horizontal after a quarter-turn.')
        self.assertLessEqual(transform['length'],transform['maxWidth']+.02,transform)
        self.assertGreaterEqual(transform['size'],11)
        self.assertEqual(self.errors,[])

    def test_keyboard_focus_ring_stays_around_drawing_at_map_scale(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing={'id':DRAWING,'name':'Shelf A1','kind':'Rack','x':2,'y':3,'width':6,'height':2,'rotation':0,'location_id':None}
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[drawing]}]}
        self.install_rooms4_plan(document,selected_drawing=DRAWING)
        group=self.page.locator('[data-workshop-drawing]')
        shape_locator=group.locator('[data-object-shape]')
        self.page.locator('html').evaluate("el=>{el.style.setProperty('--primary','139 16% 43%');el.style.setProperty('--ring','139 16% 43%')}")
        unfocused=shape_locator.evaluate("el=>{const style=getComputedStyle(el);return {stroke:style.stroke,width:style.strokeWidth,dash:style.strokeDasharray}}")
        self.page.get_by_role('button',name='Pan right',exact=True).focus()
        self.page.keyboard.press('Tab')
        self.page.keyboard.press('Tab')
        self.assertTrue(group.evaluate("el=>el.matches(':focus-visible')"))
        focused=shape_locator.evaluate("el=>{const style=getComputedStyle(el);return {stroke:style.stroke,width:style.strokeWidth,dash:style.strokeDasharray,vectorEffect:style.vectorEffect}}")
        self.assertEqual(focused['stroke'],unfocused['stroke'])
        self.assertNotEqual(focused['dash'],unfocused['dash'],'focus stays distinct when the selected border uses the same theme color')
        self.assertEqual(focused['width'],'3px')
        self.assertEqual(focused['vectorEffect'],'non-scaling-stroke')
        self.page.locator('html').evaluate("el=>el.style.setProperty('--ring','300 100% 50%')")
        shape=shape_locator.bounding_box()
        self.assert_focus_ink_tracks(shape)
        self.assertEqual(self.errors,[])

    def test_pointer_focus_does_not_show_scaled_browser_outline(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing={'id':DRAWING,'name':'Workbench','kind':'Workbench','x':2,'y':3,'width':6,'height':2.5,'rotation':0,'location_id':None}
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[drawing]}]}
        self.install_rooms4_plan(document)
        group=self.page.locator('[data-workshop-drawing]')
        box=group.bounding_box()
        self.page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2)
        self.page.mouse.down()
        try:
            state=group.evaluate("el=>({focused:el.matches(':focus'),focusVisible:el.matches(':focus-visible'),outline:getComputedStyle(el).outlineStyle})")
            self.assertTrue(state['focused'],state)
            self.assertFalse(state['focusVisible'],state)
            self.assertEqual(state['outline'],'none','Pointer focus must not render the browser default outline in map units.')
        finally:
            self.page.mouse.up()
        self.assertEqual(self.errors,[])

    def test_left_drag_empty_canvas_pans_view_without_editing_room_in_browse_and_edit(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing={'id':DRAWING,'name':'Shelf A1','kind':'Rack','x':2,'y':3,'width':3,'height':2,'rotation':0,'location_id':None}
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[drawing]}]}
        self.install_rooms4_plan(document,selected_drawing=DRAWING)
        for mode in ('browse','edit'):
            if mode=='edit':
                self.page.get_by_role('button',name='Edit',exact=True).click()
            svg=self.page.locator('.planner-svg')
            self.assertEqual(svg.evaluate('el=>getComputedStyle(el).cursor'),'grab')
            surface=svg.locator('[data-room-surface]')
            surface_box=surface.bounding_box()
            start={'x':surface_box['x']+10,'y':surface_box['y']+10}
            initial_view=svg.get_attribute('viewBox').split()
            selected_before=self.page.locator('[data-workshop-drawing]').get_attribute('class')
            drawing_before=self.page.locator('[data-workshop-drawing]').evaluate("el=>['data-x','data-y','data-width','data-height'].map(key=>el.getAttribute(key))")
            self.page.mouse.click(start['x'],start['y'])
            self.assertEqual(svg.get_attribute('viewBox').split(),initial_view,'A background click must not pan the camera.')
            self.assertEqual(self.page.locator('[data-workshop-drawing]').get_attribute('class'),selected_before,'A background click must preserve drawing selection.')
            self.page.mouse.move(start['x'],start['y'])
            self.page.mouse.down()
            self.assertEqual(svg.evaluate('el=>getComputedStyle(el).cursor'),'grabbing')
            self.page.mouse.move(start['x']+60,start['y']+40)
            self.page.mouse.up()
            self.assertEqual(svg.evaluate('el=>getComputedStyle(el).cursor'),'grab')
            moved_view=svg.get_attribute('viewBox').split()
            self.assertLess(float(moved_view[0]),float(initial_view[0]),mode)
            self.assertLess(float(moved_view[1]),float(initial_view[1]),mode)
            self.assertEqual(self.page.locator('[data-workshop-drawing]').evaluate("el=>['data-x','data-y','data-width','data-height'].map(key=>el.getAttribute(key))"),drawing_before)
            self.assertEqual(self.page.locator('[data-workshop-drawing]').get_attribute('class'),selected_before)
            self.assertEqual(self.page.evaluate('window.writes.length'),0)
            self.assertEqual(self.page.evaluate('window.fixtureLayout.document.rooms[0].objects[0]'),drawing)
            if mode=='edit':
                self.assertTrue(self.page.get_by_role('button',name='Save all room changes').is_disabled())
                self.assertTrue(self.page.get_by_role('button',name='Undo',exact=True).is_disabled())
        self.assertEqual(self.errors,[])

    def test_pan_drag_does_not_place_pending_catalog_item_but_click_still_does(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[]}]}
        self.install_rooms4_plan(document)
        self.page.get_by_role('button',name='Edit',exact=True).click()
        self.page.get_by_role('region',name='Object palette').get_by_role('button',name='Bin',exact=True).click()
        svg=self.page.locator('.planner-svg')
        surface_box=svg.locator('[data-room-surface]').bounding_box()
        start={'x':surface_box['x']+10,'y':surface_box['y']+10}
        initial_view=svg.get_attribute('viewBox').split()
        self.page.mouse.move(start['x'],start['y'])
        self.page.mouse.down()
        self.page.mouse.move(start['x']+55,start['y']+32)
        self.page.mouse.up()
        self.assertEqual(self.page.locator('[data-workshop-drawing]').count(),0,'A drag used to pan must not trigger catalog placement.')
        self.assertNotEqual(svg.get_attribute('viewBox').split(),initial_view)
        self.assertEqual(self.page.get_by_role('region',name='Object palette').get_by_role('button',name='Bin',exact=True).get_attribute('aria-pressed'),'true')
        self.assertTrue(self.page.get_by_role('button',name='Save all room changes').is_disabled())
        svg=self.page.locator('.planner-svg')
        svg.click(position={'x':svg.bounding_box()['width']/2,'y':svg.bounding_box()['height']/2})
        self.assertEqual(self.page.locator('[data-workshop-drawing]').count(),1)
        self.assertEqual(self.page.locator('[data-workshop-drawing]').get_attribute('aria-label'),'Select Bin')
        self.assertTrue(self.page.get_by_role('button',name='Save all room changes').is_enabled())
        self.assertEqual(self.errors,[])

    def test_canvas_pan_tracks_pointer_through_svg_letterboxing_and_zoom(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing={'id':DRAWING,'name':'Shelf A1','kind':'Rack','x':6,'y':7,'width':4,'height':3,'rotation':0,'location_id':None}
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[drawing]}]}
        for viewport in ({'width':1280,'height':720},{'width':900,'height':1000}):
            with self.subTest(viewport=viewport):
                self.page.set_viewport_size(viewport)
                self.install_rooms4_plan(document,selected_drawing=DRAWING)
                self.page.get_by_role('button',name='Zoom in',exact=True).click()
                self.page.get_by_role('button',name='Zoom in',exact=True).click()
                svg=self.page.locator('.planner-svg')
                svg_box=svg.bounding_box()
                surface_box=svg.locator('[data-room-surface]').bounding_box()
                start={'x':svg_box['x']+8,'y':svg_box['y']+8}
                self.assertFalse(surface_box['x']<=start['x']<=surface_box['x']+surface_box['width'] and surface_box['y']<=start['y']<=surface_box['y']+surface_box['height'],
                                 'This gesture begins in blank SVG space outside the room boundary.')
                shape=self.page.locator('[data-workshop-drawing] [data-object-shape]')
                initial=shape.bounding_box()
                self.page.mouse.move(start['x'],start['y'])
                self.page.mouse.down()
                try:
                    self.assertTrue(svg.evaluate("el=>el.classList.contains('is-panning')"), 'The SVG must capture a background pan pointer.')
                    for dx,dy in ((36,24),(68,43)):
                        self.page.mouse.move(start['x']+dx,start['y']+dy)
                        moved=shape.bounding_box()
                        self.assertAlmostEqual(moved['x']-initial['x'],dx,delta=1.5, msg=f'x movement at {viewport}')
                        self.assertAlmostEqual(moved['y']-initial['y'],dy,delta=1.5, msg=f'y movement at {viewport}')
                finally:
                    self.page.mouse.up()
        self.assertEqual(self.errors,[])

    def test_repeated_canvas_pans_from_room_to_blank_keep_capture_and_page_position(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing={'id':DRAWING,'name':'Shelf A1','kind':'Rack','x':3.75,'y':2,'width':6,'height':2,'rotation':0,'location_id':None}
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':20,'height':16,'unit':'ft','approximate':False,'objects':[drawing]}]}
        self.page.set_viewport_size({'width':1280,'height':720})
        self.install_rooms4_plan(document)
        svg=self.page.locator('.planner-svg')
        svg.evaluate("el=>{el.addEventListener('pointerdown',event=>el.dataset.panDefaultPrevented=String(event.defaultPrevented));el.addEventListener('pointercancel',()=>el.dataset.panPointerCancelled='true')}")
        initial_scroll=self.page.evaluate('window.scrollY')
        for index in range(2):
            surface=svg.locator('[data-room-surface]').bounding_box()
            svg_box=svg.bounding_box()
            if index == 1:
                svg.evaluate("el=>{const text=el.querySelector('text');const range=document.createRange();range.selectNodeContents(text);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);document.addEventListener('dragstart',()=>el.dataset.panDragStarted='true',true)}")
                self.assertTrue(self.page.evaluate('window.getSelection().toString().length>0'),'The second gesture starts with SVG caption text selected, matching the native drag state.')
                start={'x':max(svg_box['x']+4,surface['x']+surface['width']+8),'y':surface['y']+surface['height']/2}
                end={'x':surface['x']+surface['width']+24,'y':surface['y']+surface['height']/2}
            else:
                start={'x':surface['x']+surface['width']/2,'y':surface['y']+surface['height']/2}
                end={'x':surface['x']+surface['width']+32,'y':surface['y']+surface['height']/2+18}
            before=svg.get_attribute('viewBox').split()
            self.page.mouse.move(start['x'],start['y'])
            self.page.mouse.down()
            try:
                self.assertTrue(svg.evaluate('el=>el.classList.contains("is-panning")'))
                self.assertEqual(svg.get_attribute('data-pan-default-prevented'),'true','The admitted pan pointer must not start native selection, dragging, or autoscroll.')
                self.page.mouse.move(end['x'],end['y'])
                self.assertNotEqual(svg.get_attribute('viewBox').split(),before,'Each successive pan gesture must move the camera.')
                self.assertEqual(self.page.evaluate('window.scrollY'),initial_scroll,'Panning must not trigger native page autoscroll.')
            finally:
                self.page.mouse.up()
            self.assertNotEqual(svg.get_attribute('data-pan-pointer-cancelled'),'true','Native browser behavior must not cancel a captured pan gesture.')
            self.assertNotEqual(svg.get_attribute('data-pan-drag-started'),'true','Selected SVG caption text must not start a native drag during canvas panning.')
        self.assertEqual(self.errors,[])

    def test_pointer_cancel_restores_empty_canvas_camera_without_room_edits(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing={'id':DRAWING,'name':'Shelf A1','kind':'Rack','x':2,'y':3,'width':3,'height':2,'rotation':0,'location_id':None}
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[drawing]}]}
        self.install_rooms4_plan(document,selected_drawing=DRAWING)
        svg=self.page.locator('.planner-svg')
        initial_view=svg.get_attribute('viewBox').split()
        surface_box=svg.locator('[data-room-surface]').bounding_box()
        start={'x':surface_box['x']+10,'y':surface_box['y']+10}
        self.page.mouse.move(start['x'],start['y'])
        self.page.mouse.down()
        self.page.mouse.move(start['x']+50,start['y']+28)
        self.assertNotEqual(svg.get_attribute('viewBox').split(),initial_view,'The pointer must move the camera before cancellation is exercised.')
        svg.evaluate("el=>el.dispatchEvent(new PointerEvent('pointercancel',{bubbles:true,pointerId:1,pointerType:'mouse'}))")
        self.assertEqual(svg.get_attribute('viewBox').split(),initial_view)
        self.page.mouse.up()
        self.assertEqual(self.page.locator('[data-workshop-drawing]').evaluate("el=>['data-x','data-y'].map(key=>el.getAttribute(key))"),['2','3'])
        self.assertEqual(self.page.evaluate('window.writes.length'),0)
        self.assertEqual(self.errors,[])

    def test_zoom_or_room_change_during_pan_does_not_commit_stale_camera_delta(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        other='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[]},{'id':other,'location_id':None,'name':'Annex','width':12,'height':16,'unit':'ft','approximate':False,'objects':[]}]}
        self.install_rooms4_plan(document)
        self.page.get_by_role('button',name='Edit',exact=True).click()
        svg=self.page.locator('.planner-svg')
        initial=svg.get_attribute('viewBox').split()
        surface=svg.locator('[data-room-surface]').bounding_box()
        start={'x':surface['x']+10,'y':surface['y']+10}
        self.page.mouse.move(start['x'],start['y'])
        self.page.mouse.down()
        self.page.mouse.move(start['x']+45,start['y']+30)
        self.assertNotEqual(svg.get_attribute('viewBox').split(),initial)
        self.page.get_by_role('button',name='Zoom in',exact=True).evaluate('el=>el.click()')
        zoomed=self.page.locator('.planner-svg').get_attribute('viewBox').split()
        self.assertEqual(zoomed[:2],initial[:2],'Zooming cancels an in-progress drag without adopting its temporary camera offset.')
        self.page.mouse.up()
        self.assertEqual(self.page.locator('.planner-svg').get_attribute('viewBox').split(),zoomed)

        svg=self.page.locator('.planner-svg')
        before_room_change=svg.get_attribute('viewBox').split()
        surface=svg.locator('[data-room-surface]').bounding_box()
        start={'x':surface['x']+10,'y':surface['y']+10}
        self.page.mouse.move(start['x'],start['y'])
        self.page.mouse.down()
        self.page.mouse.move(start['x']+42,start['y']+26)
        self.assertNotEqual(svg.get_attribute('viewBox').split(),before_room_change)
        self.page.get_by_label('Workshop room').select_option(other)
        other_view=self.page.locator('.planner-svg').get_attribute('viewBox').split()
        self.assertEqual(other_view[:2],before_room_change[:2],'Changing rooms cancels the old camera delta.')
        self.page.mouse.up()
        self.assertEqual(self.page.locator('.planner-svg').get_attribute('viewBox').split(),other_view)
        self.assertEqual(self.page.evaluate('window.writes.length'),0)
        self.assertTrue(self.page.get_by_role('button',name='Save all room changes').is_disabled())
        self.assertEqual(self.errors,[])

    def test_resize_handle_keeps_visible_bounded_keyboard_focus(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        drawing={'id':DRAWING,'name':'Shelf A1','kind':'Rack','x':2,'y':3,'width':6,'height':2,'rotation':0,'location_id':None}
        document={'version':2,'rooms':[{'id':room,'location_id':None,'name':'Main','width':14,'height':20,'unit':'ft','approximate':False,'objects':[drawing]}]}
        self.install_rooms4_plan(document,selected_drawing=DRAWING)
        self.page.get_by_role('button',name='Edit',exact=True).click()
        self.page.locator('html').evaluate("el=>el.style.setProperty('--ring','300 100% 50%')")
        self.page.get_by_role('button',name='Pan right',exact=True).focus()
        for _ in range(3):
            self.page.keyboard.press('Tab')
        handle=self.page.locator('[data-resize-handle]')
        self.assertTrue(handle.evaluate("el=>el===document.activeElement&&el.matches(':focus-visible')"))
        focus_style=handle.evaluate("el=>{const style=getComputedStyle(el);return {width:style.strokeWidth,dash:style.strokeDasharray,vectorEffect:style.vectorEffect}}")
        self.assertEqual(focus_style,{'width':'3px','dash':'4px, 2px','vectorEffect':'non-scaling-stroke'})
        self.assert_focus_ink_tracks(handle.bounding_box())
        self.assertEqual(self.errors,[])

    def test_legacy_map_focus_ring_uses_bounded_shape_stroke(self):
        self.page.locator('html').evaluate("el=>el.style.setProperty('--ring','300 100% 50%')")
        self.page.evaluate('''() => {
          const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
          svg.setAttribute('class','map');svg.setAttribute('viewBox','0 0 20 20');
          svg.style.cssText='position:fixed;left:24px;top:24px;width:200px;height:200px;z-index:9999';
          const group=document.createElementNS(svg.namespaceURI,'g');group.setAttribute('role','button');group.setAttribute('tabindex','0');
          const shape=document.createElementNS(svg.namespaceURI,'rect');shape.setAttribute('x','2');shape.setAttribute('y','3');shape.setAttribute('width','6');shape.setAttribute('height','2');shape.setAttribute('fill','#83909b');
          group.append(shape);svg.append(group);document.querySelector('.workshop-native').append(svg);group.focus();
        }''')
        shape_locator=self.page.locator('.map g[role=button] rect')
        focus_style=shape_locator.evaluate("el=>{const style=getComputedStyle(el);return {width:style.strokeWidth,dash:style.strokeDasharray,vectorEffect:style.vectorEffect}}")
        self.assertEqual(focus_style,{'width':'3px','dash':'4px, 2px','vectorEffect':'non-scaling-stroke'})
        shape=shape_locator.bounding_box()
        self.assert_focus_ink_tracks(shape)
        self.assertEqual(self.errors,[])

    def test_benchtop_cnc_caption_has_theme_contrast_backing(self):
        room='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaam��ͭ�G����ƭy�: '77777777-7777-4777-8777-777777777777', 'name': 'Shelf 2',
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
