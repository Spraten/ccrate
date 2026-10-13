"""Normalize native Homebox codes without navigating scanned URLs."""
import re
from urllib.parse import urlsplit, unquote, parse_qs
from uuid import UUID

def normalize(raw):
    if not isinstance(raw,str) or len(raw)>2048:
        return {'kind':'invalid','reason':'Code is too long or not text'}
    value=raw.strip()
    try:parsed=urlsplit(value)
    except ValueError:return {'kind':'invalid','reason':'Malformed code'}
    if parsed.scheme and parsed.scheme not in ('http','https'):
        return {'kind':'invalid','reason':'Unsupported code'}
    if any(ord(c)<32 for c in value):return {'kind':'invalid','reason':'Code contains control characters'}
    path=unquote(parsed.path)
    match=re.fullmatch(r'/(?:a|assets)/(\d{3}-\d{3})/?',path)
    if match:return {'kind':'asset','asset_id':match.group(1)}
    match=re.fullmatch(r'/(?:item|location|entity|entities)/([0-9a-fA-F-]{36})/?',path)
    if match:
        try:return {'kind':'entity','entity_id':str(UUID(match.group(1)))}
        except ValueError:pass
    try:
        if str(UUID(value)).lower()==value.lower():return {'kind':'entity','entity_id':str(UUID(value))}
    except ValueError:pass
    if parsed.scheme in ('http','https'):
        if not parsed.hostname or parsed.username or parsed.password:return {'kind':'invalid','reason':'Malformed manufacturer QR URL'}
        return {'kind':'manufacturer','manufacturer_code':value}
    if re.fullmatch(r'\d{3}-\d{3}',value):return {'kind':'asset','asset_id':value}
    match=re.fullmatch(r'([A-Za-z0-9]{3})-([0-9]{3,})',value)
    if match:return {'kind':'short_code','short_code':f'{match.group(1).upper()}-{match.group(2)}'}
    if value.isascii() and value.isdigit() and len(value) in (8,12,13,14):
        total=sum(int(n)*(3 if i%2==0 else 1) for i,n in enumerate(reversed(value[:-1])))
        if (10-total%10)%10==int(value[-1]):return {'kind':'product','gtin':value}
        return {'kind':'invalid','reason':'Barcode check digit does not match'}
    if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{3,254}',value):
        return {'kind':'serial','serial':value}
    return {'kind':'invalid','reason':'Unrecognized code'}


def resolve_serial(code, items):
    """Match native serial metadata exactly; ambiguity never selects an asset."""
    matches=[e for e in items if not e.get('entityType',{}).get('isLocation')
             and not e.get('archived') and e.get('serialNumber')==code['serial']]
    if len(matches)==1:
        return {**code,'entity':matches[0]}
    if matches:
        return {**code,'ambiguous':True,'reason':'Multiple equipment records use this serial. Scan the C-Crate asset label.'}
    return {**code,'reason':'Manufacturer serial recognized. Add equipment and scan this code to register it.'}

MANUFACTURER_FIELD='Manufacturer QR code'
GTIN_FIELD='Product GTIN'

def manufacturer_code(raw):
    if not isinstance(raw,str) or not raw.strip() or len(raw)>2048 or any(ord(c)<32 for c in raw):
        raise ValueError('Use a manufacturer QR code of up to 2048 characters')
    value=raw.strip()
    if value.startswith('LAB:U:'):raise ValueError('A person badge cannot identify equipment')
    code=normalize(value)
    if code['kind'] in ('asset','entity'):raise ValueError('Use the manufacturer code, not the C-Crate label')
    return value

def resolve_equipment(raw,code,items):
    if not isinstance(raw,str) or not raw.strip() or len(raw)>2048 or any(ord(c)<32 for c in raw):return code
    active=[e for e in items if not e.get('archived') and not e.get('entityType',{}).get('isLocation')]
    value=raw.strip()
    def field(entity,name):return [f.get('textValue','') for f in entity.get('fields',[]) if f.get('name')==name]
    if code['kind']=='short_code':
        canonical=code['short_code'].upper()
        matches=[e for e in active if isinstance(e.get('shortCode'),str) and e['shortCode'].strip().upper()==canonical]
        metadata=[e for e in active if isinstance(e.get('serialNumber'),str) and e['serialNumber'].strip().upper()==canonical or
                  any(v.strip().upper()==canonical for v in field(e,MANUFACTURER_FIELD) if isinstance(v,str))]
        owners={e.get('id') or id(e):e for e in matches+metadata}
        if len(owners)>1:
            return {**code,'ambiguous':True,'reason':'This code matches multiple item identifiers. Check the item short code, serial number, or manufacturer code.'}
        if owners:return {**code,'entity':next(iter(owners.values()))}
        return {**code,'reason':'No equipment is registered with this short code.'}
    matches=[e for e in active if value in field(e,MANUFACTURER_FIELD)]
    if code['kind']=='serial':
        matches=[e for e in active if value in field(e,MANUFACTURER_FIELD) or e.get('serialNumber')==code['serial']]
        if not matches:return resolve_serial(code,active)
    if not matches and code['kind']=='manufacturer':
        params=parse_qs(urlsplit(value).query)
        serials={v for k,values in params.items() if k.lower() in ('sn','serial','serialnumber','serial_number') for v in values if v}
        if len(serials)==1:matches=[e for e in active if e.get('serialNumber')==next(iter(serials))]
    if not matches and code['kind']=='product':
        canonical=code['gtin'].zfill(14)
        matches=[e for e in active if any(v.zfill(14)==canonical for v in field(e,GTIN_FIELD))]
    if len(matches)==1:return {**code,'entity':matches[0]}
    if matches:return {**code,'ambiguous':True,'reason':'This manufacturer code matches multiple items. Scan the individual C-Crate label or serial number.'}
    if code['kind'] in ('manufacturer','product'):return {**code,'reason':'No equipment is registered with this manufacturer code. Add its code in C-Crate or when adding equipment.'}
    return code
