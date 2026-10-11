import asyncio, pathlib, json
from playwright.async_api import async_playwright
K=pathlib.Path('video-kit').resolve()
F=pathlib.Path('fonts/node_modules/@fontsource/manrope/files').resolve()
fonts=''.join(f"@font-face{{font-family:'Manrope';font-weight:{w};src:url('file://{F}/manrope-latin-{w}-normal.woff2')}}" for w in [300,400,500,600,700,800])
CSS=fonts+'''
*{box-sizing:border-box;margin:0}
html,body{width:1920px;height:1080px;overflow:hidden;background:#0B0B0C;color:#F2F2F2;font-family:Manrope,sans-serif;-webkit-font-smoothing:antialiased}
.bg{position:absolute;inset:0;background:radial-gradient(1000px 640px at 82% 0%,rgba(224,162,69,.22),transparent 62%),radial-gradient(800px 600px at 0% 100%,rgba(255,255,255,.04),transparent 60%),#0B0B0C}
.chip{position:absolute;left:96px;top:72px;display:flex;align-items:center;gap:12px;padding:10px 20px;border-radius:999px;background:rgba(255,255,255,.06);border:1px solid #2A2A2E;font:600 24px Manrope;color:#F2F2F2}
.chip i{width:10px;height:10px;border-radius:50%;background:#E0A245}
.tc{position:absolute;right:96px;top:80px;font:500 22px Manrope;color:#6F6F75;font-variant-numeric:tabular-nums}
.cap{position:absolute;left:50%;bottom:64px;transform:translateX(-50%);max-width:1400px;text-align:center;font:500 34px/1.38 Manrope;letter-spacing:-.005em;color:#F2F2F2;background:rgba(11,11,12,.8);padding:14px 26px;border-radius:16px;border:1px solid rgba(255,255,255,.06)}
.win{position:absolute;border-radius:18px;overflow:hidden;border:1px solid #2A2A2E;box-shadow:0 40px 110px rgba(0,0,0,.65)}
.win img{display:block;width:100%}
.spot{position:absolute;border:2px solid #E0A245;border-radius:16px;box-shadow:0 0 0 9999px rgba(11,11,12,.58)}
.cur{position:absolute;width:30px;height:30px;border-radius:50%;background:#F2F2F2;border:2px solid #0B0B0C;box-shadow:0 0 0 10px rgba(224,162,69,.25),0 0 0 22px rgba(224,162,69,.1)}
.h{font:600 88px/1.04 Manrope;letter-spacing:-.035em}
.k{font:500 28px/1.4 Manrope;color:#A3A3A8}
.big{font:300 220px/0.9 Manrope;letter-spacing:-.05em}
.amber{color:#E0A245}
.ph{position:absolute;border-radius:54px;background:#1C1C1F;padding:14px;box-shadow:0 50px 100px rgba(0,0,0,.7),0 0 0 1px #2E2E33}
.ph .in{border-radius:42px;overflow:hidden;background:#0B0B0C}
.ph img{display:block;width:100%}
.lbl{position:absolute;font:600 24px Manrope;color:#A3A3A8}
'''
def img(p): return f'file://{K}/{p}'
def win(p,l,t,w,extra=''): return f'<div class="win" style="left:{l}px;top:{t}px;width:{w}px;{extra}"><img src="{img(p)}"></div>'
def phone(p,l,t,w,rot='',crop=204):
    return f'<div class="ph" style="left:{l}px;top:{t}px;width:{w+28}px;transform:{rot}"><div class="in" style="height:{int(w*2.05)}px"><img src="{img(p)}" style="margin-top:-{int(crop*w/1290)}px"></div></div>'
def chip(t): return f'<div class="chip"><i></i>{t}</div>'
def cap(t): return f'<div class="cap">{t}</div>'
def tc(t): return f'<div class="tc">{t}</div>'
S={}
S['k01']=f'''<div class="bg"></div>{tc("0:00")}
<div style="position:absolute;left:160px;top:250px"><div class="big">1,200</div><div class="h" style="font-size:64px;margin-top:28px;max-width:1300px">active construction sites in Mumbai, each now required to run a dust sensor.</div></div>
{cap("Mumbai has about twelve hundred active construction sites.")}'''
S['k02']=f'''<div class="bg"></div>{tc("0:08")}
<div style="position:absolute;left:160px;top:190px" class="h">A sensor tells you the air is already bad.</div>
''' + ''.join(f'<div style="position:absolute;left:{160+i*540}px;top:420px;width:500px;padding:36px;border-radius:24px;background:rgba(255,255,255,.035);border:1px solid #25252A"><div class="big" style="font-size:150px;{c}">{n}</div><div class="k" style="margin-top:22px;color:#C9C9CD">{d}</div></div>' for i,(n,d,c) in enumerate([('45%','of sites had a sensor by October 2025',''),('117','sensors found switched off in one inspection drive','color:#EB6E5B'),('2×','PM2.5 in five wards last winter, versus the national standard','color:#E0A245')]))+cap("By the time it reads high, the dust has reached the school next door.")
S['k03']=f'''<div class="bg"></div>{tc("0:17")}
<img src="{img('hero/h1-overview-monitor.png')}" style="position:absolute;inset:0;width:1920px;opacity:.16">
<div style="position:absolute;left:0;right:0;top:330px;text-align:center"><svg width="96" height="96" viewBox="0 0 30 30"><circle cx="15" cy="15" r="13.5" fill="none" stroke="#E0A245" stroke-width="1.6"/><path d="M6 18c4-6 9-6 18-3" stroke="#F2F2F2" stroke-width="1.6" fill="none" stroke-linecap="round"/><circle cx="11" cy="11" r="2" fill="#E0A245"/><circle cx="17" cy="9" r="1.5" fill="#E0A245"/><circle cx="21" cy="12" r="1.2" fill="#E0A245"/></svg>
<div class="h" style="font-size:140px;margin-top:18px">DustTrace</div>
<div style="margin-top:26px;display:flex;justify-content:center;gap:64px;font:500 40px Manrope;color:#A3A3A8"><span>Predict</span><span class="amber">Prevent</span><span>Prove</span></div></div>
{cap("DustTrace stops construction dust before it reaches people.")}'''
S['k04']=f'''<div class="bg"></div>{chip("Ward console, K-East")}{tc("0:24")}
{win('screens-4k/01-overview-0800.png',190,170,1540)}
<div class="spot" style="left:{190+int(293*1540/1920)-8}px;top:{170+int(215*1540/1920)-8}px;width:{int(477*1540/1920)+16}px;height:{int(92*1540/1920)+16}px"></div>
{cap("Thursday morning: a 78% chance PM10 crosses the standard tomorrow, 7 to 11.")}'''
S['k05']=f'''<div class="bg"></div>{chip("Dust weather, tomorrow")}{tc("0:34")}
{win('detail/d02-dust-weather-map.png',120,160,1300)}
<div style="position:absolute;right:110px;top:300px;text-align:right"><div class="big" style="font-size:150px">08:00</div><div class="k">Plays 06:00 to 18:00</div></div>
{cap("Each plume is a forecast from one site, carried by tomorrow’s wind.")}'''
S['k06']=f'''<div class="bg"></div>{chip("Needs you")}{tc("0:44")}
{win('detail/d04-alert-critical.png',200,330,1000)}
<div class="cur" style="left:{200+int(95*1000/461)-15}px;top:{330+int(104*1000/461)-15}px"></div>
<div style="position:absolute;left:1280px;top:330px;width:520px"><div class="k">Every alert carries its fix.</div><div class="h" style="font-size:64px;margin-top:16px">One tap turns the mist curtain on.</div></div>
{cap("Site B is spiking with its mist off. One tap, and it’s on.")}'''
S['k07']=f'''<div class="bg"></div>{chip("Agent case DT-KE-0142")}{tc("0:52")}
{win('detail/d06-agent-steps.png',150,160,480)}
{win('detail/d08-actions-first-vs-final.png',690,160,1080)}
<div class="spot" style="left:{690+int(20*1080/756)-6}px;top:{160+int(68*1080/756)-6}px;width:{int(716*1080/756)+12}px;height:{int(78*1080/756)+12}px"></div>
{cap("No reply to the photo request, so the agent adds an inspection. It never assumes.")}'''
S['k08']=f'''<div class="bg"></div>{chip("Ward officer approval")}{tc("1:07")}
{win('detail/d19-case-approve-click.png',335,150,1250)}
<div class="spot" style="left:960px;top:704px;width:594px;height:210px"></div><div class="cur" style="left:1120px;top:822px"></div>
{cap("Anything stronger than a reminder needs a ward officer’s sign-off.")}'''
S['k09']=f'''<div class="bg"></div>{chip("Site manager app")}{tc("1:13")}
{phone('phone/p3-manager-plan.png',560,100,340,'rotate(-3deg)')}{phone('phone/p4-manager-accepted.png',1010,120,340,'rotate(3deg)')}
{cap("The contractor gets a plan the evening before, and accepts it in one tap.")}'''
S['k10']=f'''<div class="bg"></div>{chip("Site A, Safe-Work Windows")}{tc("1:23")}
{win('detail/d11-safe-work-windows.png',150,250,1200)}
<div style="position:absolute;left:1440px;top:230px"><div class="big amber" style="font-size:200px">64</div><div class="k" style="margin-top:12px;width:360px">Dust Score, shown on the site’s LED board</div></div>
{win('detail/d12-capture-and-clean.png',150,600,860)}
{cap("Every site gets Safe-Work Windows and a public Dust Score.")}'''
S['k11']=f'''<div class="bg"></div>{chip("Sensors and BEST buses")}{tc("1:31")}
{win('detail/d16-bus-readings.png',140,170,900)}{win('detail/d15-sensor-health.png',1090,230,700)}
{cap("Our nodes and sensors on BEST buses check whether each site sensor can be trusted.")}'''
S['k12']=f'''<div class="bg"></div>{chip("Resident view")}{tc("1:38")}
{phone('phone/p2-resident-sent.png',840,100,340)}
<div style="position:absolute;left:160px;top:380px;width:520px"><div class="k">Scan the QR on the site board.</div><div class="h" style="font-size:64px;margin-top:16px">See the score. Report dust without your name.</div></div>
{cap("Residents scan the site’s QR code to see its score and report dust.")}'''
S['k13']=f'''<div class="bg"></div>{chip("Impact, simulated pilot")}{tc("1:44")}
{win('detail/d17-impact-did-chart.png',140,220,1120)}
<div style="position:absolute;left:1340px;top:230px"><div class="big" style="font-size:180px;color:#6CC59A">−11%</div><div class="k" style="margin-top:16px;width:440px">PM10 on high-risk days versus control wards. Demo data; the pilot will measure it.</div></div>
{cap("A case only closes when the air measurably improves.")}'''
S['k14']=f'''<div class="bg"></div>{tc("1:54")}
<div style="position:absolute;left:160px;top:300px;width:1500px"><div class="h" style="font-size:96px">Mumbai already paid for the sensors.</div><div class="h amber" style="font-size:96px;margin-top:10px">DustTrace turns them into prevention.</div>
<div class="k" style="margin-top:60px">Techfest IIT Bombay, InnovateX 2026–27, Theme 2: Rising AQI</div><div class="k" style="margin-top:8px;color:#6F6F75">Team ARA IGNITE: Ansh, Dhruv, Anuj, Sarang</div></div>'''
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1920,'height':1080})
        for k,v in S.items():
            f=K/'keyframes'/'_t.html'; f.write_text(f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{v}</body></html>')
            await pg.goto('file://'+str(f)); await pg.wait_for_timeout(250); await pg.screenshot(path=str(K/'keyframes'/f'{k}.png'))
        f.unlink(); (K/'keyframes'/'design.css').write_text(CSS.split('*{box-sizing')[0] and '*{box-sizing'+CSS.split('*{box-sizing')[1])
        await b.close()
asyncio.run(main())
