import asyncio, pathlib
from playwright.async_api import async_playwright
K=pathlib.Path('video-kit').resolve()
def page(body):
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:1920px;height:1080px;overflow:hidden;background:#0B0B0C}}
.bg{{position:absolute;inset:0;background:radial-gradient(900px 600px at 78% 8%,rgba(224,162,69,.28),transparent 60%),radial-gradient(700px 500px at 10% 100%,rgba(255,255,255,.05),transparent 60%),#0B0B0C}}
.stage{{position:absolute;inset:0;perspective:2200px}}
.mon{{position:absolute;border-radius:26px;background:#1C1C1F;padding:18px;box-shadow:0 60px 120px rgba(0,0,0,.65),0 0 0 1px #2A2A2E,inset 0 1px 0 rgba(255,255,255,.08)}}
.mon img{{display:block;border-radius:12px}}
.mon::after{{content:"";position:absolute;inset:18px;border-radius:12px;background:linear-gradient(115deg,rgba(255,255,255,.07),transparent 35%);pointer-events:none}}
.ph{{position:absolute;border-radius:54px;background:#1C1C1F;padding:14px;box-shadow:0 50px 100px rgba(0,0,0,.7),0 0 0 1px #2E2E33,inset 0 1px 0 rgba(255,255,255,.1)}}
.ph img{{display:block;border-radius:42px}}
.ph .isl{{position:absolute;left:50%;top:26px;width:110px;height:30px;margin-left:-55px;background:#000;border-radius:20px}}
.floor{{position:absolute;left:0;right:0;bottom:0;height:260px;background:linear-gradient(180deg,transparent,rgba(224,162,69,.05))}}
</style></head><body><div class="bg"></div><div class="floor"></div><div class="stage">{body}</div></body></html>'''
def mon(img,l,t,w,rx,ry,rz=0):
    return f'<div class="mon" style="left:{l}px;top:{t}px;transform:rotateY({ry}deg) rotateX({rx}deg) rotateZ({rz}deg)"><img src="file://{K}/screens-4k/{img}" style="width:{w}px"></div>'
def ph(img,l,t,w,rx,ry,rz=0):
    h=int(w*932/430); s=w/430; off=int(68*s); sb=int(54*s)
    bar=f'<div style="height:{sb}px;display:flex;align-items:center;justify-content:space-between;padding:0 {int(30*s)}px;font:600 {int(15*s)}px -apple-system,Segoe UI,Arial;color:#F2F2F2;background:#0B0B0C"><span>08:40</span><span style="letter-spacing:2px">▮▮▮ ◔</span></div>'
    return f'<div class="ph" style="left:{l}px;top:{t}px;transform:rotateY({ry}deg) rotateX({rx}deg) rotateZ({rz}deg)"><div style="width:{w}px;height:{h}px;overflow:hidden;border-radius:42px;background:#0B0B0C">{bar}<div style="height:{h-sb}px;overflow:hidden"><img src="file://{K}/phone/{img}" style="width:{w}px;border-radius:0;margin-top:-{off}px"></div></div><span class="isl"></span></div>'
SC={
 'h1-overview-monitor':mon('01-overview-0800.png',300,150,1440,8,-16,1),
 'h2-case-monitor':mon('06-case-awaiting.png',260,150,1440,8,16,-1),
 'h3-two-phones':ph('p3-manager-plan.png',560,70,400,6,18,-3)+ph('p1-resident.png',1010,120,400,6,-14,3),
 'h4-console-and-phone':mon('16-impact.png',140,170,1300,6,-14,1)+ph('p4-manager-accepted.png',1350,220,330,4,-10,2),
 'h5-map-closeup':mon('02-overview-1500.png',-260,-40,2300,14,-22,2),
}
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1920,'height':1080},device_scale_factor=2)
        for k,v in SC.items():
            f=K/'hero'/f'{k}.html'; f.write_text(page(v)); await pg.goto('file://'+str(f)); await pg.wait_for_timeout(300)
            await pg.screenshot(path=str(K/'hero'/f'{k}.png')); f.unlink()
        await b.close()
asyncio.run(main())
