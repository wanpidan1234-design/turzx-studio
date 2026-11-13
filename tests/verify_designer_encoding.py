from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from io import BytesIO
from panel_calibration import prepare_panel_image
import json
report=[]
for p in Path('runtime/designer-verification').glob('*.png'):
    if not p.stem.endswith(('-H','-V')):continue
    im=Image.open(p)
    out=prepare_panel_image(im,270 if im.width>im.height else 0,'brg',{'gamma':1,'saturation':1,'offset_x':-60,'offset_y':0})
    stream=BytesIO();out.save(stream,'PNG',compress_level=1);level=1
    if len(stream.getvalue())>=1048576:
        stream=BytesIO();out.save(stream,'PNG',compress_level=9);level=9
    assert out.size==(720,1280) and out.mode=='RGBA' and out.getchannel('A').getextrema()==(255,255) and stream.getvalue()[25]==6
    report.append({'name':p.stem,'bytes':len(stream.getvalue()),'compression':level})
Path('runtime/designer-verification/encoding-report.json').write_text(json.dumps(report,indent=2))
print('frames',len(report),'max',max(report,key=lambda r:r['bytes']),'over_limit',[r for r in report if r['bytes']>=1048576])
assert all(r['bytes']<1048576 for r in report)
