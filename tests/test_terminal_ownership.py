import pathlib
import ast
import tempfile
import unittest
from uuid import uuid4
from ledger import Ledger
from native_jobs import NativeJobs
from sessions import Sessions, Session


def load_terminal_note_helpers(submit_note):
    source = pathlib.Path(__file__).resolve().parents[1]/'deploy/kiosk-server.py'
    tree = ast.parse(source.read_text())
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                and node.name in {'confirm_terminal_note', '_SessionBoundNativeClient'}]
    namespace = {'Conflict': RuntimeError, 'submit_note': submit_note}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace


class NoteClient:
    def __init__(self, session=None, switch_on_entity=False, archived=False, quantity=1, location=False):
        self.session = session
        self.switch_on_entity = switch_on_entity
        self.archived, self.quantity, self.location = archived, quantity, location
        self.tenant = None
        self.posts = []

    def call(self, path, *args):
        if path == '/api/v1/users/self':
            return {'item': {'defaultGroupId': 'group-1'}}
        if path == '/api/v1/groups/members':
            return [{'id': 'member-1', 'name': 'Member One'}]
        if args and args[0] == 'POST':
            self.posts.append((path, args))
        return []

    def entity(self, entity_id):
        if self.switch_on_entity:
            self.session.start('replacement')
        return {'id': entity_id, 'archived': self.archived, 'quantity': self.quantity,
                'entityType': {'isLocation': self.location}}


class TerminalOwnershipTests(unittest.TestCase):
    def invoke_note_route(self, *, actor='member-1', current_actor=None, switch_on_entity=False,
                          submit=None, payload=None):
        session = Session(); generation = session.start(actor)
        if current_actor is not None:
            generation = session.start(current_actor)
        client = NoteClient(session, switch_on_entity)
        calls = []
        def submit_fn(bound_client, jobs, group, who, key, data, author):
            calls.append((group, who, key, data.copy(), author, bound_client.tenant))
            if submit:
                return submit(bound_client)
            bound_client.call('/api/v1/entities/item-1/maintenance', 'POST', {'description': 'note'})
            return {'id': 'job-1', 'status': 'completed', 'entity_id': 'item-1'}
        helpers = load_terminal_note_helpers(submit_fn)
        body = payload or {'request_key': 'key-1', 'input': {'entity_id': 'item-1', 'note': 'Text'},
                           'session_generation': generation, 'session_instance': session.instance}
        return helpers['confirm_terminal_note'](client, object(), session, body), session, client, calls

    def test_terminal_note_confirm_sets_tenant_and_ends_only_confirmed_owner(self):
        result, session, client, calls = self.invoke_note_route()
        self.assertEqual(client.tenant, 'group-1')
        self.assertEqual(calls, [('group-1', 'member-1', 'key-1', {'entity_id': 'item-1', 'note': 'Text'}, 'Member One', 'group-1')])
        self.assertTrue(result['note_saved'])
        self.assertTrue(result['session_ended'])
        self.assertIsNone(session.current())
        self.assertEqual(len(client.posts), 1)

    def test_terminal_note_refuses_anonymous_or_nonmember_without_submit(self):
        session = Session(); generation = session.begin_anonymous_return()
        client = NoteClient(session); calls = []
        helpers = load_terminal_note_helpers(lambda *args: calls.append(args))
        body = {'request_key': 'key', 'input': {'entity_id': 'item-1', 'note': 'Text'},
                'session_generation': generation, 'session_instance': session.instance}
        with self.assertRaises((ValueError, RuntimeError)):
            helpers['confirm_terminal_note'](client, object(), session, body)
        self.assertEqual(calls, [])

        session = Session(); generation = session.start('former-member')
        body['session_generation'] = generation; body['session_instance'] = session.instance
        client = NoteClient(session)
        with self.assertRaises((ValueError, RuntimeError)):
            helpers['confirm_terminal_note'](client, object(), session, body)
        self.assertEqual(calls, [])

    def test_terminal_note_stale_owner_is_blocked_at_native_post(self):
        with self.assertRaises(RuntimeError):
            self.invoke_note_route(switch_on_entity=True)

    def test_terminal_note_uncertain_result_does_not_end_badge_session(self):
        def uncertain(_client):
            raise RuntimeError('outcome needs recovery')
        with self.assertRaisesRegex(RuntimeError, 'outcome needs recovery'):
            self.invoke_note_route(submit=uncertain)

    def test_terminal_note_untracked_archived_or_location_item_is_rejected(self):
        for archived, quantity, location in ((True, 1, False), (False, 2, False),
                                               (False, True, False), (False, 1, True)):
            session=Session();generation=session.start('member-1');client=NoteClient(session,archived=archived,quantity=quantity,location=location)
            calls=[];helpers=load_terminal_note_helpers(lambda *args:calls.append(args))
            body={'request_key':'key','input':{'entity_id':'item-1','note':'Text'},'session_generation':generation,'session_instance':session.instance}
            with self.assertRaises(ValueError):helpers['confirm_terminal_note'](client,object(),session,body)
            self.assertEqual(calls,[])
            self.assertEqual(client.posts,[])

    def test_terminal_note_started_session_change_blocks_before_post(self):
        session=Session();generation=session.start('member-1');client=NoteClient(session)
        calls=[]
        def submit(bound_client,*args):
            session.start('replacement')
            bound_client.call('/api/v1/entities/item-1/maintenance','POST',{'description':'Text'})
        helpers=load_terminal_note_helpers(submit)
        body={'request_key':'key','input':{'entity_id':'item-1','note':'Text'},'session_generation':generation,'session_instance':session.instance}
        with self.assertRaises(RuntimeError):helpers['confirm_terminal_note'](client,object(),session,body)
        self.assertEqual(client.posts,[])

    def test_terminal_note_cleanup_failure_still_reports_saved(self):
        class EndFailure(Session):
            def end(self, expected=None):raise OSError('cleanup failed')
        session=EndFailure();generation=session.start('member-1');client=NoteClient(session)
        def submit(bound_client,*args):
            bound_client.call('/api/v1/entities/item-1/maintenance','POST',{'description':'Text'})
            return {'id':'job-1','status':'completed','entity_id':'item-1'}
        helpers=load_terminal_note_helpers(submit)
        body={'request_key':'key','input':{'entity_id':'item-1','note':'Text'},'session_generation':generation,'session_instance':session.instance}
        result=helpers['confirm_terminal_note'](client,object(),session,body)
        self.assertTrue(result['note_saved'])
        self.assertFalse(result['session_ended'])
        self.assertEqual(session.current(),'member-1')

    def test_terminal_note_expired_session_does_not_submit(self):
        now=[0.0];session=Session(timeout=1,clock=lambda:now[0]);generation=session.start('member-1');now[0]=2.0
        client=NoteClient(session);calls=[];helpers=load_terminal_note_helpers(lambda *args:calls.append(args))
        body={'request_key':'key','input':{'entity_id':'item-1','note':'Text'},'session_generation':generation,'session_instance':session.instance}
        with self.assertRaises(RuntimeError):helpers['confirm_terminal_note'](client,object(),session,body)
        self.assertEqual(calls,[])

    def test_two_clients_have_independent_identity_scan_and_end(self):
        sessions=Sessions();pi=sessions.get('pi');laptop=sessions.get('laptop')
        generation=pi.start('alice');pi.record_scan('tool')
        laptop.start('bob');laptop.end()
        self.assertEqual(pi.snapshot(),('alice',generation))
        self.assertEqual(pi.scans(generation),{'tool'})
        self.assertNotEqual(pi.instance,laptop.instance)
        self.assertIsNone(laptop.current())

    def test_cancel_before_badge_response_prevents_start(self):
        session=Session();session.cancel_scan('pending-token')
        self.assertIsNone(session.start('alice','pending-token'))
        self.assertIsNone(session.current())

    def test_cancel_after_response_ends_only_matching_scan(self):
        session=Session();session.start('alice','first');session.start('bob','second')
        session.cancel_scan('first');self.assertEqual(session.current(),'bob')
        session.cancel_scan('second');self.assertIsNone(session.current())

    def test_revocation_ends_only_affected_users_across_clients(self):
        sessions=Sessions();a=sessions.get('a');b=sessions.get('b');c=sessions.get('c')
        a.start('alice');b.start('alice');c.start('bob');sessions.revoke_user('alice')
        self.assertIsNone(a.current());self.assertIsNone(b.current())
        self.assertEqual(c.current(),'bob')

    def test_abandoned_client_cleanup_does_not_evict_active_terminal(self):
        sessions=Sessions();active=sessions.get('active');active.start('alice')
        for i in range(300):sessions.get(str(i))
        self.assertIs(sessions.get('active'),active)
        self.assertEqual(active.current(),'alice')

    def test_note_intent_remains_bound_to_badge_actor_after_session_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            group, item = str(uuid4()), str(uuid4())
            original, replacement = str(uuid4()), str(uuid4())
            session = Session(); session.start(original)
            jobs = NativeJobs(Ledger(pathlib.Path(directory)/'ledger.db'))
            job = jobs.prepare(group, session.current(), 'add_note', str(uuid4()),
                               {'entity_id': item, 'note': 'Owner-bound fixture'},
                               context={'entity_id': item, 'author_name': 'Original badge holder'})
            session.start(replacement)
            saved = jobs.detail(group, job['id'])
            self.assertEqual(session.current(), replacement)
            self.assertEqual(saved['actor_id'], original)
            self.assertEqual(saved['context']['author_name'], 'Original badge holder')

if __name__=='__main__':unittest.main()
