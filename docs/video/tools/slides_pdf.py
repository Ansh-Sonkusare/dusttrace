import asyncio, pathlib, re, json
from playwright.async_api import async_playwright
exec(open('render_slides.py').read().split('async def main')[0])
order=json.load(open('deck/project/deck.json'))['order']
F=base/'fonts/node_modules/@fontsource/manrope/files'
ff=''.join(f"@font-face{{font-family:'Manrope';font-weight:{w};src:url('file://{F}/manrope-latin-{w}-normal.woff2')}}" for w in [300,400,500,600,700,800])
body=''
for sid in order:
    h=(D/f'{sid}.html').read_text()
    h=re.sub(r'<aside>.*?</aside>','',h,flags=re.S)
    h=re.sub(r'/_blob/([0-9a-f]{32})',lambda m:'file://'+str(base/'deckassets'/(blobmap.get(m.group(1),'x')+'.png')),h)
    body+=h.replace('<section','<section class="s"',1)
doc=f'<!doctype html><html><head><meta charset="utf-8"><style>{ff}@page{{size:1920px 1080px;margin:0}}*{{box-sizing:border-box;margin:0}} html,body{{background:#0B0B0C}} .s{{position:relative;width:1920px;height:1080px;overflow:hidden;page-break-after:always;-webkit-print-color-adjust:exact;print-color-adjust:exact}} table{{border-collapse:collapse}} ul{{padding-left:28px}}</style></head><body>{body}</body></html>'
(base/'_deck.html').write_text(doc)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1920,'height':1080})
        await pg.goto('file://'+str(base/'_deck.html')); await pg.wait_for_timeout(1500)
        await pg.pdf(path=str(base/'exports/DustTrace-Round1-Pitch.pdf'),width='1920px',height='1080px',print_background=True,margin={'top':'0','bottom':'0','left':'0','right':'0'})
        await b.close()
asyncio.run(main())
