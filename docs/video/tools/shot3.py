import asyncio, pathlib, shutil
from playwright.async_api import async_playwright
base=pathlib.Path('.').resolve()
F=base/'fonts/node_modules/@fontsource'
css=''.join(f"@font-face{{font-family:'Manrope';font-weight:{w};src:url('file://{F}/manrope/files/manrope-latin-{w}-normal.woff2') format('woff2')}}\n" for w in [300,400,500,600,700])
html=(base/'dusttrace-console.html').read_text()
(base/'console3-local.html').write_text('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+css+'</style></head><body>'+html+'</body></html>')
URL='file://'+str(base/'console3-local.html')
OUT=base/'video-kit'
if OUT.exists(): shutil.rmtree(OUT)
for d in ['screens','screens-4k','phone','detail','frames-4k']: (OUT/d).mkdir(parents=True)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); errs=[]
        async def page(w=1600,h=900,s=2.4):
            pg=await b.new_page(viewport={'width':w,'height':h},device_scale_factor=s,color_scheme='dark')
            pg.on('pageerror',lambda e: errs.append(str(e)))
            pg.on('console',lambda m: errs.append(m.text) if m.type=='error' else None)
            await pg.route('https://fonts.googleapis.com/**',lambda r: r.fulfill(body='',content_type='text/css'))
            return pg
        async def shot(pg,path,keep=False):
            if not keep: await pg.evaluate("document.getElementById('toast').classList.remove('show')")
            await pg.wait_for_timeout(450)
            await pg.screenshot(path=str(OUT/path.replace('screens/','screens-4k/')))
            if path.startswith('screens/'):
                from PIL import Image
                Image.open(OUT/path.replace('screens/','screens-4k/')).resize((1920,1080),Image.LANCZOS).save(OUT/path)
            sh=await pg.evaluate('document.documentElement.scrollHeight')
            if sh>pg.viewport_size['height']+2 and path.startswith('screens'): print('OVERFLOW',path,sh)
        async def det(pg,sel,path,i=0):
            await pg.evaluate("document.getElementById('toast').classList.remove('show')"); await pg.wait_for_timeout(300)
            el=pg.locator(sel).nth(i); await el.screenshot(path=str(OUT/'detail'/path))
        async def hour(pg,h):
            await pg.fill('#hour',str(h)); await pg.dispatch_event('#hour','input')
        pg=await page()
        await pg.goto(URL+'#overview')
        for h in range(6,19):
            await hour(pg,h); await shot(pg,f'frames-4k/overview-{h:02d}00.png')
        await hour(pg,8)
        await shot(pg,'screens/01-overview-0800.png')
        await det(pg,'.stats','d01-briefing-stats.png')
        await det(pg,'#v-overview .ov > .panel','d02-dust-weather-map.png')
        await det(pg,'#v-overview .side .panel','d03-needs-you-queue.png')
        await det(pg,'.q','d04-alert-critical.png',0)
        await hour(pg,15); await shot(pg,'screens/02-overview-1500.png')
        await hour(pg,8)
        await pg.click('[data-alert="1"]'); await pg.wait_for_timeout(150); await shot(pg,'screens/03-overview-mist-on.png',True)
        await det(pg,'.q','d05-alert-handled.png',0)
        for a in [2,3,4,5]:
            await pg.click(f'[data-alert="{a}"]'); await pg.wait_for_timeout(60)
        await shot(pg,'screens/04-overview-all-handled.png')
        await pg.click('.nav[data-go="cases"]'); await shot(pg,'screens/05-cases.png')
        await pg.click('tr[data-case="DT-KE-0142"]'); await shot(pg,'screens/06-case-awaiting.png')
        await det(pg,'.cd > .panel','d06-agent-steps.png')
        await det(pg,'.cd .panel','d07-likely-causes.png',1)
        await det(pg,'.cd .panel','d08-actions-first-vs-final.png',2)
        await det(pg,'.cd .panel','d09-evidence.png',3)
        await det(pg,'.cd .panel','d10-verify-chart.png',4)
        await pg.click('[data-approve]'); await pg.wait_for_timeout(150); await shot(pg,'screens/07-case-approved.png',True)
        await pg.click('.nav[data-go="site"]'); await pg.click('[data-pick="A"]'); await shot(pg,'screens/08-site-A.png')
        await det(pg,'.sitegrid .panel','d11-safe-work-windows.png',0)
        await det(pg,'.sitegrid .panel','d12-capture-and-clean.png',2)
        await det(pg,'.sitegrid .panel','d13-dust-score-breakdown.png',3)
        await pg.click('[data-mist="on"]'); await pg.wait_for_timeout(150); await shot(pg,'screens/09-site-A-mist-on.png',True)
        for i,k in enumerate('BCDE'):
            await pg.click(f'[data-pick="{k}"]'); await shot(pg,f'screens/{10+i}-site-{k}.png')
        await pg.click('.nav[data-go="forecast"]'); await shot(pg,'screens/14-forecast.png')
        await det(pg,'#v-forecast .panel','d14-forecast-grid.png',0)
        await pg.click('.nav[data-go="sensors"]'); await shot(pg,'screens/15-sensors-buses.png')
        await det(pg,'#v-sensors .sg .panel','d15-sensor-health.png',0)
        await det(pg,'#v-sensors .sg .panel','d16-bus-readings.png',1)
        await pg.click('.nav[data-go="impact"]'); await shot(pg,'screens/16-impact.png')
        await det(pg,'#v-impact .im > .panel','d17-impact-did-chart.png')
        await det(pg,'#v-impact .stats','d18-impact-stats.png')
        await pg.click('.nav[data-go="resident"]'); await shot(pg,'screens/17-resident-desktop.png')
        lt=await page(); await lt.goto(URL+'#overview'); await lt.evaluate("document.documentElement.dataset.theme='light'"); await shot(lt,'screens/18-overview-light.png')
        await lt.goto(URL+'#case'); await lt.evaluate("document.documentElement.dataset.theme='light'"); await shot(lt,'screens/19-case-light.png')
        ph=await page(430,932,3)
        await ph.goto(URL+'#resident'); await shot(ph,'phone/p1-resident.png')
        await ph.click('[data-cat="Dust cloud"]'); await ph.click('.send'); await ph.wait_for_timeout(200); await ph.evaluate("window.scrollTo(0,document.body.scrollHeight)"); await shot(ph,'phone/p2-resident-sent.png')
        await ph.click('.nav[data-go="manager"]'); await ph.evaluate("window.scrollTo(0,0)"); await shot(ph,'phone/p3-manager-plan.png')
        await ph.click('[data-accept]'); await ph.wait_for_timeout(150); await shot(ph,'phone/p4-manager-accepted.png')
        await ph.click('[data-photo]'); await ph.wait_for_timeout(150); await ph.evaluate("window.scrollTo(0,420)"); await shot(ph,'phone/p5-manager-photo-sent.png')
        print('errors',errs); await b.close()
asyncio.run(main())
