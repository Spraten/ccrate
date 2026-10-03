"""Revocable bearer badges referencing native Homebox users, without profiles."""
import hashlib,secrets
from uuid import uuid4
from ledger import Ledger,uuid,timestamp

class Badges:
    PREFIX='LAB:U:' # Temporary prototype namespace; permanent labels require review.
    def __init__(self,ledger):
        self.ledger=ledger
        with ledger.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS badges(
              id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,group_id TEXT NOT NULL,
              user_id TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,revoked_at TEXT)''')
    def issue(self,group,user,member_ids):
        group,user=uuid(group),uuid(user)
        if user not in {uuid(m) for m in member_ids}:raise ValueError('User is not a current Homebox group member')
        token=secrets.token_urlsafe(32);badge_id=str(uuid4())
        with self.ledger.transaction() as db:
            db.execute('INSERT INTO badges(id,token_hash,group_id,user_id,created_at) VALUES(?,?,?,?,?)',
                (badge_id,hashlib.sha256(token.encode()).hexdigest(),group,user,timestamp()))
        return {'id':badge_id,'code':self.PREFIX+token,'user_id':user}
    def resolve(self,group,code,member_ids):
        group=uuid(group)
        if not isinstance(code,str) or not code.startswith(self.PREFIX):return None
        token=code[len(self.PREFIX):]
        if len(token)!=43 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in token):return None
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.ledger.connection() as db:
            row=db.execute('SELECT user_id FROM badges WHERE token_hash=? AND group_id=? AND revoked=0',(digest,group)).fetchone()
        return row['user_id'] if row and row['user_id'] in {uuid(m) for m in member_ids} else None
    def revoke(self,group,badge_id):
        with self.ledger.transaction() as db:
            return db.execute('UPDATE badges SET revoked=1,revoked_at=? WHERE group_id=? AND id=? AND revoked=0',
                (timestamp(),uuid(group),uuid(badge_id))).rowcount==1
    def list(self,group):
        with self.ledger.connection() as db:
            return [dict(r) for r in db.execute('SELECT id,user_id,revoked,created_at,revoked_at FROM badges WHERE group_id=? ORDER BY created_at',(uuid(group),))]
