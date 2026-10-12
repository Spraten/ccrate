"""Revocable bearer badges referencing native Homebox users, without profiles."""
import hashlib,secrets,os,tempfile
from cryptography.fernet import Fernet,InvalidToken
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
            db.execute('''CREATE TABLE IF NOT EXISTS badge_print_secrets(
              badge_id TEXT PRIMARY KEY REFERENCES badges(id),encrypted_code BLOB NOT NULL)''')
    def cipher(self,create=False):
        # Reprint credentials remain encrypted on this Pi, separately from the
        # hashed scan registry and all public lists/journal payloads.
        key_path=self.ledger.path.with_name('badge-print.key')
        if not key_path.exists():
            if not create:raise ValueError('Badge reprint key is missing. Restore the private key before printing')
            with self.ledger.connection() as db:
                if db.execute('SELECT 1 FROM badge_print_secrets LIMIT 1').fetchone():raise ValueError('Badge reprint key is missing. Restore the private key before issuing more badges')
            fd,temporary=tempfile.mkstemp(prefix='.badge-print-key-',dir=key_path.parent)
            try:
                with os.fdopen(fd,'wb') as output:
                    output.write(Fernet.generate_key());output.flush();os.fsync(output.fileno())
                try:os.link(temporary,key_path)
                except FileExistsError:pass
            finally:os.unlink(temporary)
        fd=os.open(key_path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as source:
            st=os.fstat(source.fileno())
            if st.st_uid!=os.getuid() or st.st_mode&0o077:raise ValueError('Badge reprint key must remain private on this Pi')
            return Fernet(source.read())
    def issue(self,group,user,member_ids):
        group,user=uuid(group),uuid(user)
        if user not in {uuid(m) for m in member_ids}:raise ValueError('User is not a current C-Crate group member')
        token=secrets.token_urlsafe(32);badge_id=str(uuid4());code=self.PREFIX+token
        encrypted=self.cipher(create=True).encrypt(code.encode())
        with self.ledger.transaction() as db:
            db.execute('INSERT INTO badges(id,token_hash,group_id,user_id,created_at) VALUES(?,?,?,?,?)',
                (badge_id,hashlib.sha256(token.encode()).hexdigest(),group,user,timestamp()))
            db.execute('INSERT INTO badge_print_secrets VALUES(?,?)',(badge_id,encrypted))
        return {'id':badge_id,'code':code,'user_id':user}
    def print_code(self,group,badge_id,member_ids):
        with self.ledger.connection() as db:
            row=db.execute('''SELECT b.user_id,s.encrypted_code FROM badges b
              LEFT JOIN badge_print_secrets s ON s.badge_id=b.id
              WHERE b.group_id=? AND b.id=? AND b.revoked=0''',(uuid(group),uuid(badge_id))).fetchone()
        if not row or row['user_id'] not in {uuid(m) for m in member_ids}:raise ValueError('Choose an active badge for a current member')
        if not row['encrypted_code']:raise ValueError('The original QR for this older badge was not saved. Issue a replacement badge first')
        try:code=self.cipher().decrypt(row['encrypted_code']).decode()
        except (InvalidToken,UnicodeError):raise ValueError('The saved badge QR could not be opened. Review its private key before printing') from None
        if self.resolve(group,code,member_ids)!=row['user_id']:raise ValueError('Saved QR does not match this badge')
        return code
    def replace(self,group,badge_id,member_ids):
        group,badge_id=uuid(group),uuid(badge_id);members={uuid(m) for m in member_ids}
        token=secrets.token_urlsafe(32);replacement=str(uuid4());code=self.PREFIX+token;encrypted=self.cipher(create=True).encrypt(code.encode())
        with self.ledger.transaction() as db:
            old=db.execute('SELECT user_id FROM badges WHERE group_id=? AND id=? AND revoked=0',(group,badge_id)).fetchone()
            if not old or old['user_id'] not in members:raise ValueError('Choose an active badge for a current member')
            db.execute('INSERT INTO badges(id,token_hash,group_id,user_id,created_at) VALUES(?,?,?,?,?)',
                (replacement,hashlib.sha256(token.encode()).hexdigest(),group,old['user_id'],timestamp()))
            db.execute('INSERT INTO badge_print_secrets VALUES(?,?)',(replacement,encrypted))
            db.execute('UPDATE badges SET revoked=1,revoked_at=? WHERE id=?',(timestamp(),badge_id))
        return {'id':replacement,'code':code,'user_id':old['user_id']}
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
            return [dict(r) for r in db.execute('''SELECT id,user_id,revoked,created_at,revoked_at,
              EXISTS(SELECT 1 FROM badge_print_secrets s WHERE s.badge_id=badges.id) AS reprintable
              FROM badges WHERE group_id=? ORDER BY created_at''',(uuid(group),))]
