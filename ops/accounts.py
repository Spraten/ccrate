"""Native group enrollment; password and invitation stay in request memory."""
import re,urllib.error
from datetime import datetime,timedelta,timezone
from ledger import Conflict
from setup_native import text
def create_account(client,data):
    name=text(data.get('name',''),'Name',required=True);email=text(data.get('email',''),'Email',required=True).lower()
    password=data.get('password')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise ValueError('Enter a valid email address')
    if not isinstance(password,str) or len(password)<6 or len(password)>128:raise ValueError('Homebox password must contain 6 to 128 characters')
    members=client.call('/api/v1/groups/members')
    if any(m['email'].lower()==email for m in members):raise Conflict('This native member already exists. Issue their badge from Admin')
    invitation=client.call('/api/v1/groups/invitations','POST',{'uses':1,'expiresAt':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()})
    try:
        try:client.call('/api/v1/users/register','POST',{'name':name,'email':email,'password':password,'token':invitation['token']})
        except (OSError,urllib.error.HTTPError):
            # Registration may have committed despite a missing response. Only
            # resolve the native member; never post the same account again here.
            members=client.call('/api/v1/groups/members')
            matches=[m for m in members if m['email'].lower()==email]
            if len(matches)!=1:raise Conflict('Account creation was not confirmed. Review native members before trying again')
        members=client.call('/api/v1/groups/members');matches=[m for m in members if m['email'].lower()==email]
        if len(matches)!=1:raise Conflict('New native membership could not be verified')
        return {'user':{'id':matches[0]['id'],'name':matches[0]['name']},'status':'created'}
    finally:
        try:client.call('/api/v1/groups/invitations/'+invitation['id'],'DELETE')
        except urllib.error.HTTPError as e:
            if e.code!=404:raise
