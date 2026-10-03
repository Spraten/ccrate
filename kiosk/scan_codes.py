"""Normalize native Homebox codes without navigating scanned URLs."""
import re
from urllib.parse import urlsplit, unquote
from uuid import UUID

def normalize(raw):
    if not isinstance(raw,str) or len(raw)>2048:
        return {'kind':'invalid','reason':'Code is too long or not text'}
    value=raw.strip()
    try:
        parsed=urlsplit(value)
    except ValueError:
        return {'kind':'invalid','reason':'Malformed code'}
    if parsed.scheme and parsed.scheme not in ('http','https'):
        return {'kind':'invalid','reason':'Unsupported code'}
    path=unquote(parsed.path)
    match=re.fullmatch(r'/a/(\d{3}-\d{3})/?',path)
    if match:
        return {'kind':'asset','asset_id':match.group(1)}
    match=re.fullmatch(r'/entities/([0-9a-fA-F-]{36})/?',path)
    if match:
        try:return {'kind':'entity','entity_id':str(UUID(match.group(1)))}
        except ValueError:pass
    if re.fullmatch(r'\d{3}-\d{3}',value):
        return {'kind':'asset','asset_id':value}
    if value.isascii() and value.isdigit() and len(value) in (8,12,13,14):
        body=value[:-1]
        total=sum(int(n)*(3 if i%2==0 else 1) for i,n in enumerate(reversed(body)))
        if (10-total%10)%10==int(value[-1]):return {'kind':'product','gtin':value}
        return {'kind':'invalid','reason':'Barcode check digit does not match'}
    return {'kind':'invalid','reason':'Unrecognized code'}
