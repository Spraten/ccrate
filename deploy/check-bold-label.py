import pathlib,sys,json
root=pathlib.Path('/home/user/Desktop/inventory-system');sys.path[:0]=[str(root/'ops'),str(root/'work/hardware/python')]
import labels,zxingcpp
entity={'id':'efb41b6f-0386-452b-af21-75da992e9677','name':'Demo Drone 001','assetId':'000-022'}
image,code=labels.render(entity)
assert set(image.getdata())=={0,255},'Raster must contain solid black/white only'
assert any(r.text==code for r in zxingcpp.read_barcodes(image)),'QR must still decode'
image.save(root/'work/bold-label-preview.png')
print(json.dumps({'binary_raster':True,'qr_decodes':True,'font':'DejaVuSansCondensed-Bold','name_pixels':18,'printer_density':4}))
