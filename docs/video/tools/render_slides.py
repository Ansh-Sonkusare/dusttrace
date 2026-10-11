import asyncio, pathlib, re, sys
from playwright.async_api import async_playwright
base=pathlib.Path('.').resolve(); D=base/'deck/project/slides'
blobmap={'6611ab6a32cc2f7473f16a419ff2e331':'01-overview-0800','6d477fbd2a4835e26e21d25818077258':'02-overview-1500','a955fa5d542fdeba72ec4280206f9ed5':'05-cases','5af15dad4c9f86015b1d0a8f2d6909ab':'06-case-awaiting','8823b03fb7f1b8f322564cd45285d932':'07-case-approved','b739270a3758a00529bcad52c13c4dda':'09-site-A-mist-on','2bfeec89c138a20af434a31ecb06dd70':'10-site-B','85940fd97b96aa7b5fb79f5e286f73e0':'12-site-D','01bf7c0c7ebbac4afd5135e60c2c0f1a':'14-forecast','d6f624f8abff37a0c93d8ec04a6466cb':'15-sensors-buses','f89ec804fa1eab2612dda53eecce0e91':'16-impact','48ec7222ea68761d8ba75c9c405dec1b':'18-overview-light','54493cbadcb3beba0e57543ad98d080f':'h1-overview-monitor','7e4b7bcf90122d10307e198aae994fdc':'h3-two-phones','4d7bce218af9e5b79819677866471f0d':'h4-console-and-phone','bf37b48b300c50de01ff9bca169fab1d':'p1-resident','6475e811cc6b2f54a8c38cd4248efd80':'p3-manager-plan','f0386054a7f6e77f7c150fdeebee79fb':'p4-manager-accepted'}
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1920,'height':1080})
        for sid in sys.argv[1:]:
            h=(D/f'{sid}.html').read_text()
            h=re.sub(r'<aside>.*?</aside>','',h,flags=re.S)
            h=re.sub(r'/_blob/([0-9a-f]{32})',lambda m:'file://'+str(base/'deckassets'/(blobmap.get(m.group(1),'x')+'.png')),h)
            h=h.replace('<section','<section class="s"',1)
            F=base/'fonts/node_modules/@fontsource/manrope/files'
            ff=''.join(f"@font-face{{font-family:'Manrope';font-weight:{w};src:url('file://{F}/manrope-latin-{w}-normal.woff2')}}" for w in [300,400,500,600,700,800])
            doc=f'<!doctype html><html><head><meta charset="utf-8"><style>'+ff+f'*{{box-sizing:border-box;margin:0}} body{{width:1920px;height:1080px}} .s{{position:relative;width:1920px;height:1080px;overflow:hidden}} table{{border-collapse:collapse}} ul{{padding-left:28px}}</style></head><body>{h}</body></html>'
            f=base/'_r.html'; f.write_text(doc); await pg.goto('file://'+str(f)); await pg.wait_for_timeout(200)
            await pg.screenshot(path=f'render-{sid}.png')
        await b.close()
asyncio.run(main())
