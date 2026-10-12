"""Check profile input boundaries and preserved recovery intent without live APIs."""
import base64
import io
import unittest
from uuid import uuid4
from PIL import Image
import accounts
from desktop_api import safe_intent

class AccountInputs(unittest.TestCase):
    def test_member_name_utf8_byte_boundaries(self):
        accepted = ('a' * 255, '界' * 85, '😀' * 63 + 'abc', '  Valid name  ')
        for name in accepted:
            with self.subTest(name=name[:12]):
                expected = name.strip()
                create = accounts.creation_input({'name': name, 'request_key': str(uuid4())})
                update = accounts.profile_input({'name': name, 'updatedAt': 'fixture'})
                self.assertEqual(create['name'], expected)
                self.assertEqual(update['name'], expected)
        rejected = ('', ' \t\n ', 123, 'a' * 256, '界' * 86, '界' * 90, '😀' * 64)
        for name in rejected:
            with self.subTest(name=repr(name)[:32]):
                with self.assertRaises(ValueError):
                    accounts.creation_input({'name': name, 'request_key': str(uuid4())})
                with self.assertRaises(ValueError):
                    accounts.profile_input({'name': name, 'updatedAt': 'fixture'})

    def test_profile_limits_preserve_email_and_notes_semantics(self):
        profile = {'name': 'Fixture member', 'updatedAt': 'fixture', 'notes': '界' * 1000}
        self.assertEqual(accounts.creation_input({'name': 'Fixture', 'email': '', 'request_key': str(uuid4())})['email'], '')
        self.assertEqual(accounts.profile_input(profile)['notes'], '界' * 1000)
        max_email = 'a' * 249 + '@x.com'
        self.assertEqual(accounts.creation_input({'name': 'Fixture', 'email': max_email, 'request_key': str(uuid4())})['email'], max_email)
        self.assertEqual(accounts.profile_input(dict(profile, email=max_email))['email'], max_email)
        with self.assertRaisesRegex(ValueError, 'Email is missing or too long'):
            accounts.creation_input({'name': 'Fixture', 'email': 'a' * 250 + '@x.com', 'request_key': str(uuid4())})
        with self.assertRaises(ValueError):
            accounts.profile_input(dict(profile, email='a' * 250 + '@x.com'))
        with self.assertRaises(ValueError):
            accounts.profile_input(dict(profile, notes='界' * 1001))

    def test_name_only_and_future_credentials(self):
        key=str(uuid4());value=accounts.creation_input({'name':' Bob ','request_key':key})
        self.assertEqual(value,{'name':'Bob','email':'','requestKey':key})
        for field in ('password','pin'):
            with self.assertRaises(ValueError):accounts.creation_input({'name':'Bob','request_key':key,field:'1234'})
        for field in ('password','pin'):
            with self.assertRaises(ValueError):accounts.profile_input({'name':'Bob','updatedAt':'fixture',field:''})
        with self.assertRaises(ValueError):accounts.creation_input({'name':'Bob','request_key':key,'email':'bad'})

    def test_picture_normalization_and_unsafe_input(self):
        raw=io.BytesIO();Image.new('RGBA',(160,100),(25,80,120,100)).save(raw,'PNG')
        value=accounts.avatar('data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with Image.open(io.BytesIO(base64.b64decode(value.split(',')[1]))) as picture:
            self.assertEqual(picture.format,'JPEG');self.assertLessEqual(max(picture.size),128);self.assertEqual(picture.mode,'RGB')
        self.assertEqual(accounts.avatar(value),value)
        self.assertEqual(accounts.avatar(''),'')
        for unsafe in ('data:image/svg+xml,<svg/>','data:image/png;base64,bad','javascript:alert(1)'):
            with self.assertRaises(ValueError):accounts.avatar(unsafe)

    def test_recovery_intent_retains_identity_without_picture_or_notes(self):
        key=str(uuid4());intent=safe_intent('users/create',{'name':'Bob','email':'private@example.invalid','request_key':key})
        self.assertEqual(intent,{'name':'Bob','user_id':key})
        value={'name':'Bob','email':'','avatar':'','notes':'Private fixture notes','updatedAt':'2026-10-06T12:00:00Z','user_id':key}
        intent=safe_intent('users/update',value)
        self.assertEqual(set(intent),{'user_id','updatedAt','profile_digest'})
        self.assertEqual(len(intent['profile_digest']),64)
        self.assertNotIn('Private fixture notes',str(intent))
        with self.assertRaises(ValueError):accounts.profile_input(dict(value,updatedAt=''))
