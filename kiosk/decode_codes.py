"""Decode full frames, then retry small centered labels at higher resolution."""
import math
import zxingcpp


def decode_frame(frame):
    width,height=frame.size
    def detected(image, transform):
        found=zxingcpp.read_barcodes(image,try_downscale=False)
        return [{'code':c.text,'corners':[transform(p.x,p.y) for p in
                (c.position.top_left,c.position.top_right,c.position.bottom_right,c.position.bottom_left)]}
                for c in found]
    result=detected(frame,lambda x,y:[x,y])
    if result:return result
    # Bound retry size and cost. Place tiny manufacturer labels in the center.
    left,top=width*3//8,height*3//8
    right,bottom=width*5//8,height*5//8
    crop=frame.crop((left,top,right,bottom)).convert('L')
    scale=min(8,2560/max(crop.size))
    enlarged=crop.resize((round(crop.width*scale),round(crop.height*scale)))
    sx,sy=enlarged.width/crop.width,enlarged.height/crop.height
    for angle in (0,3,-3):
        rotated=enlarged.rotate(angle,expand=True,fillcolor=255)
        radians=math.radians(angle);co,si=math.cos(radians),math.sin(radians)
        def original(x,y):
            dx,dy=x-rotated.width/2,y-rotated.height/2
            return [left+(co*dx-si*dy+enlarged.width/2)/sx,
                    top+(si*dx+co*dy+enlarged.height/2)/sy]
        result=detected(rotated,original)
        if result:return result
    return []
