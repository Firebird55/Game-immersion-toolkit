"""Generate original project-owned speech-bubble geometry; no external imagery."""
from pathlib import Path
from PIL import Image, ImageDraw
root=Path(__file__).resolve().parents[1]
image=Image.new('RGBA',(256,256),(0,0,0,0));draw=ImageDraw.Draw(image)
draw.rounded_rectangle((8,8,248,248),radius=48,fill='#17212a')
draw.rounded_rectangle((44,48,212,176),radius=24,fill='#b9ed55')
draw.polygon([(70,169),(70,210),(110,169)],fill='#b9ed55')
for y in (82,110,138):draw.rounded_rectangle((76,y,180,y+10),radius=5,fill='#17212a')
image.save(root/'public/proxy-transcript.png')
image.save(root/'assets/proxy-transcript.ico',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
(root/'public/favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect x="8" y="8" width="240" height="240" rx="48" fill="#17212a"/><rect x="44" y="48" width="168" height="128" rx="24" fill="#b9ed55"/><path d="M70 169v41l40-41" fill="#b9ed55"/><path d="M76 87h104M76 115h104M76 143h104" stroke="#17212a" stroke-width="10" stroke-linecap="round"/></svg>\n',encoding='utf-8')
