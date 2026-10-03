"""Short-lived display cache derived only from native inventory records."""
import threading,time
from conditions import condition
_lock=threading.Lock();_cache=None;_time=0
def browse(client,refresh=False):
    global _cache,_time
    with _lock:
        if _cache is None or refresh or time.monotonic()-_time>10:
            rows=[]
            for summary in client.entities():
                e=client.entity(summary['id']);rows.append({'id':e['id'],'name':e['name'],'assetId':e.get('assetId'),'parent':e.get('parent'),'entityType':e.get('entityType'),'quantity':e.get('quantity'),'archived':e.get('archived'),'condition':condition(e),'manufacturer':e.get('manufacturer',''),'tags':e.get('tags',[])})
            _cache=rows;_time=time.monotonic()
        return [dict(e) for e in _cache]
def invalidate():
    global _time
    with _lock:_time=0
