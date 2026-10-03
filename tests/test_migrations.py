import pathlib,tempfile,unittest
from uuid import uuid4
from ledger import Ledger


class Tests(unittest.TestCase):
    def test_version_zero_upgrade_preserves_existing_custody_and_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'ops.db';ledger=Ledger(path)
            group,actor,asset,key=[str(uuid4()) for _ in range(4)]
            operation=ledger.begin(group,actor,'check_out',[asset],key);ledger.complete(operation['id'])
            with ledger.connection() as db:db.executescript('DROP TABLE operation_context; PRAGMA user_version=0;')
            reopened=Ledger(path)
            self.assertEqual(reopened.begin(group,actor,'check_out',[asset],key)['id'],operation['id'])
            self.assertEqual(reopened.custody(group)[0]['entity_id'],asset)
            with reopened.connection() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
    def test_newer_database_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'ops.db';ledger=Ledger(path)
            with ledger.connection() as db:db.execute('PRAGMA user_version=2')
            with self.assertRaises(ValueError):Ledger(path)


if __name__=='__main__':unittest.main()
