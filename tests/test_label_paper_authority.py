import pathlib
import hashlib
import json
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'ops'))
import labels
from ledger import Conflict


class FakeLayouts:
    asset_root = pathlib.Path('/fixture')
    def __init__(self, *, mutation=None, foreign=False, expired=False, template_changed=False):
        self.mutation, self.foreign, self.expired, self.template_changed = mutation, foreign, expired, template_changed
        self.template = {'revision': 4, 'document': {'page': {'widthMm': 60, 'heightMm': 40}}}
    def review(self, group, actor, review_id):
        if self.foreign: return None
        return {'review_id': review_id, 'created': time.time()-(90000 if self.expired else 0), 'item_id': 'item-1', 'item_updated_at': 'v1', 'item_display_id': 'BIN-D-GC-C-1-A17-U1234567890ABCDEF1234567890ABCDEF', 'template_id': 'template-1', 'template_revision': 4, 'template_hash': hashlib.sha256(json.dumps(self.template['document'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(), 'profile': 'letter', 'dpi': 300, 'label_mm': [60, 40]}
    def get(self, group, template_id):
        if self.template_changed: return {'revision': 5, 'document': {'changed': True}}
        return self.template


class Client:
    timeout = 60
    def __init__(self, changed=False, display_id='BIN-D-GC-C-1-A17-U1234567890ABCDEF1234567890ABCDEF'): self.changed=changed; self.display_id=display_id; self.calls=0
    def entity(self, item_id):
        self.calls+=1
        return {'updatedAt': 'v2' if self.changed else 'v1', 'displayId': self.display_id, 'archived': False}


class PaperAuthorityTests(unittest.TestCase):
    def call(self, layouts, client=None, ids=None, geometry=None):
        client=client or Client()
        geometry=geometry or {'page_mm':[215.9,279.4], 'label_mm':[60,40], 'margin_mm':10, 'gap_mm':3, 'cut_guides':True}
        return labels.paper(client, layouts, 'group-1', 'actor-1', {'review_ids':ids or ['review-1'], 'geometry':geometry})

    def test_stale_or_foreign_review_never_reaches_compositor(self):
        cases=[('foreign',FakeLayouts(foreign=True),Client(),None,Conflict),('expired',FakeLayouts(expired=True),Client(),None,Conflict),('changed item',FakeLayouts(),Client(changed=True),None,Conflict),('changed display ID after ancestor move',FakeLayouts(),Client(display_id='BIN-E-GC-C-1-A17-U1234567890ABCDEF1234567890ABCDEF'),None,Conflict),('changed template',FakeLayouts(template_changed=True),Client(),None,Conflict),('slot mismatch',FakeLayouts(),Client(),{'page_mm':[215.9,279.4],'label_mm':[50,30],'margin_mm':10,'gap_mm':3,'cut_guides':True},ValueError)]
        for name,layouts,client,geometry,error in cases:
            with self.subTest(name=name), patch('label_render.render_paper_sheet') as render:
                with self.assertRaises(error): self.call(layouts,client,geometry=geometry)
                render.assert_not_called()

    def test_item_limit_rejects_before_ticket_reads_or_composition(self):
        layouts=FakeLayouts()
        with patch('label_render.render_paper_sheet') as render:
            with self.assertRaisesRegex(ValueError,'1 to 36'):
                labels.paper(Client(),layouts,'group-1','actor-1',{'review_ids':['review']*37,'geometry':{'page_mm':[215.9,279.4],'label_mm':[60,40]}})
            render.assert_not_called()


if __name__ == '__main__': unittest.main()
