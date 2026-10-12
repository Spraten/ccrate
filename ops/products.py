"""Offline catalog uses native Homebox templates rather than copied assets."""
from scan_codes import normalize
from native_fields import text_field

GTIN_FIELD='Product GTIN'
MARKER_FIELD='Kiosk creation request'


def gtin(value):
    code=normalize(value)
    if code['kind']!='product':raise ValueError('Enter a valid UPC/EAN/GTIN with its check digit')
    return code['gtin'].zfill(14)


def catalog(client):
    products=[];errors=[]
    for summary in client.call('/api/v1/templates'):
        template=client.call('/api/v1/templates/'+summary['id'])
        try:
            if text_field(template,MARKER_FIELD):continue
            code=text_field(template,GTIN_FIELD)
            if code is None:continue
            canonical=gtin(code)
            products.append({'id':template['id'],'gtin':canonical,'name':template.get('defaultName') or template['name'],
                'manufacturer':template.get('defaultManufacturer',''),'model':template.get('defaultModelNumber',''),
                'description':template.get('defaultDescription') or template.get('description',''),
                'revision':template['updatedAt'],'fields':template.get('fields',[])})
        except ValueError:errors.append({'id':template['id'],'name':template['name'],'error':'Product barcode field needs review'})
    return {'products':products,'errors':errors}


def lookup(client,value):
    canonical=gtin(value);products=catalog(client)
    matches=[p for p in products['products'] if p['gtin']==canonical]
    if len(matches)>1:raise ValueError('Multiple catalog templates use this barcode; review them in C-Crate')
    return {'gtin':canonical,'product':matches[0] if matches else None}


def template_update(template):
    result=dict(template)
    result['defaultLocationId']=(template.get('defaultLocation') or {}).get('id')
    result['defaultTagIds']=[t['id'] for t in template.get('defaultTags',[])]
    return result
