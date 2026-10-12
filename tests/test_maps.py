import copy,json,unittest
from uuid import uuid4
from maps import ROOM_FIELD,OBJECT_FIELD,room_geometry,object_geometry,save_room,save_object,remove_object,list_map,ancestry


class Client:
    def __init__(self,entities):self.data=entities
    def entity(self,key):return copy.deepcopy(self.data[key])
    def entities(self,locations=False):return [self.entity(k) for k in self.data if self.data[k]['entityType']['isLocation']==locations]
    def call(self,path,method='GET',data=None):
        key=path.rsplit('/',1)[1];payload=copy.deepcopy(data)
        payload['parent']={'id':payload['parentId']} if payload['parentId'] else None
        self.data[key]=payload
        return self.entity(key)


class Tests(unittest.TestCase):
    def setUp(self):
        self.room,self.shelf,self.asset,self.foreign,self.type=[str(uuid4()) for _ in range(5)]
        def e(key,name,parent,location=True):return {'id':key,'name':name,'parent':{'id':parent} if parent else None,'entityType':{'id':self.type,'isLocation':location},'archived':False,'quantity':0 if location else 1,'tags':[],'fields':[{'name':'Keep','type':'text','textValue':'original'}],'description':'preserved'}
        self.client=Client({self.room:e(self.room,'Workshop',None),self.shelf:e(self.shelf,'Shelf',self.room),self.asset:e(self.asset,'Drone',self.shelf,False),self.foreign:e(self.foreign,'Other room',None)})
        save_room(self.client,self.room,{'width':10,'height':6})
        self.placement={'room_id':self.room,'x':2,'y':1,'width':2,'height':1,'type':'Shelf'}
    def test_native_room_and_object_preserve_inventory(self):
        before=self.client.entity(self.shelf);save_object(self.client,self.shelf,self.placement);after=self.client.entity(self.shelf)
        for key in ('name','parent','description','quantity','entityType','tags'):self.assertEqual(after[key],before[key])
        self.assertEqual(after['fields'][0],before['fields'][0])
        self.assertEqual(json.loads(next(f['textValue'] for f in after['fields'] if f['name']==OBJECT_FIELD))['x'],2)
    def test_asset_highlights_exact_native_shelf(self):
        save_object(self.client,self.shelf,self.placement);result=list_map(self.client,self.asset)
        self.assertEqual(result['highlight_id'],self.shelf);self.assertEqual(result['room_id'],self.room);self.assertTrue(result['exact'])
        self.assertEqual([p['name'] for p in result['path']],['Workshop','Shelf','Drone'])
    def test_deep_mixed_map_path_and_cycle(self):
        parent=self.shelf
        for index in range(70):
            key=str(uuid4());self.client.data[key]={'id':key,'name':'Level '+str(index),'parent':{'id':parent},'entityType':{'isLocation':index%2==0}}
            parent=key
        self.client.data[self.asset]['parent']={'id':parent}
        path=ancestry(self.client,self.client.entity(self.asset));self.assertEqual(len(path),73);self.assertEqual(path[-1]['id'],self.room)
        self.client.data[self.room]['parent']={'id':self.asset}
        with self.assertRaises(ValueError):ancestry(self.client,self.client.entity(self.asset))
    def test_remove_visual_object_preserves_native_location(self):
        save_object(self.client,self.shelf,self.placement);remove_object(self.client,self.shelf)
        self.assertIn(self.shelf,self.client.data);self.assertEqual(self.client.entity(self.shelf)['parent']['id'],self.room)
        self.assertFalse(list_map(self.client,self.asset)['exact'])
    def test_out_of_bounds_and_wrong_room_rejected(self):
        with self.assertRaises(ValueError):save_object(self.client,self.shelf,{**self.placement,'x':10})
        save_room(self.client,self.foreign,{'width':10,'height':6})
        with self.assertRaises(ValueError):save_object(self.client,self.shelf,{**self.placement,'room_id':self.foreign})
    def test_room_cannot_shrink_past_objects(self):
        save_object(self.client,self.shelf,{**self.placement,'x':8})
        with self.assertRaises(ValueError):save_room(self.client,self.room,{'width':4,'height':3})
    def test_corrupt_field_reported_without_invented_geometry(self):
        self.client.data[self.shelf]['fields'].append({'name':OBJECT_FIELD,'type':'text','textValue':'bad json'})
        result=list_map(self.client,self.asset);self.assertEqual(result['objects'],[]);self.assertEqual(result['errors'][0]['id'],self.shelf)
    def test_non_location_and_archived_location_rejected(self):
        with self.assertRaises(ValueError):save_object(self.client,self.asset,self.placement)
        self.client.data[self.shelf]['archived']=True
        with self.assertRaises(ValueError):save_object(self.client,self.shelf,self.placement)
    def test_integer_bounds_reject_boolean_and_float(self):
        for value in (True,1.5,'10',None):
            with self.assertRaises(ValueError):room_geometry({'width':value,'height':6})
    def test_duplicate_text_field_requires_native_review(self):
        self.client.data[self.shelf]['fields'] += [{'name':OBJECT_FIELD,'type':'text','textValue':'{}'}]*2
        with self.assertRaises(ValueError):save_object(self.client,self.shelf,self.placement)


if __name__=='__main__':unittest.main()
