import asyncio, pathlib, shutil, sys
from playwright.async_api import async_playwright
B=pathlib.Path('.').resolve(); K=B/'video-kit'; V=B/'vid'
F=B/'fonts/node_modules/@fontsource/manrope/files'
fonts=''.join(f"@font-face{{font-family:'Manrope';font-weight:{w};src:url('file://{F}/manrope-latin-{w}-normal.woff2')}}" for w in [300,400,500,600,700])
u=lambda p:'file://'+str(p)
maps=''.join(f'<img class="mh" id="m{h}" src="{u(V/f"map-{h:02d}.jpg")}">' for h in range(6,15))
html=f'''<!doctype html><html><head><meta charset="utf-8"><style>{fonts}
*{{box-sizing:border-box;margin:0}}
html,body{{width:1920px;height:1080px;overflow:hidden;background:#0B0B0C;color:#F2F2F2;font-family:Manrope,sans-serif;-webkit-font-smoothing:antialiased}}
.bg{{position:absolute;inset:0;background:radial-gradient(1000px 640px at 82% 0%,rgba(224,162,69,.20),transparent 62%),radial-gradient(800px 600px at 0% 100%,rgba(255,255,255,.035),transparent 60%),#0B0B0C}}
.sc{{position:absolute;inset:0;opacity:0}}
.chip{{position:absolute;left:96px;top:72px;display:flex;align-items:center;gap:12px;padding:10px 20px;border-radius:999px;background:rgba(255,255,255,.06);border:1px solid #2A2A2E;font:600 24px Manrope}}
.chip i{{width:10px;height:10px;border-radius:50%;background:#E0A245}}
.cap{{position:absolute;left:50%;bottom:56px;transform:translateX(-50%);text-align:center;font:500 34px/1.35 Manrope;background:rgba(11,11,12,.82);padding:14px 28px;border-radius:16px;border:1px solid rgba(255,255,255,.06);white-space:nowrap}}
.win{{position:absolute;border-radius:18px;overflow:hidden;border:1px solid #2A2A2E;box-shadow:0 40px 110px rgba(0,0,0,.65)}}
.panel{{position:absolute;left:150px;top:160px;width:1620px;height:740px;border-radius:24px;background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,.012)),#141416;border:1px solid #25252A;padding:40px 56px}}
.ti{{font:600 44px/1.15 Manrope;letter-spacing:-.02em}}
.su{{font:500 26px/1.4 Manrope;color:#A3A3A8;margin-top:8px}}
.src{{position:absolute;left:56px;bottom:28px;font:500 19px Manrope;color:#6F6F75}}
.h{{font:600 88px/1.04 Manrope;letter-spacing:-.035em}}
.k{{font:500 28px/1.4 Manrope;color:#A3A3A8}}
.big{{font:300 200px/0.9 Manrope;letter-spacing:-.05em;font-variant-numeric:tabular-nums}}
svg text{{font-family:Manrope}}
.cur{{position:absolute;width:30px;height:30px;border-radius:50%;background:#F2F2F2;border:2px solid #0B0B0C;z-index:5}}
.rip{{position:absolute;width:30px;height:30px;border-radius:50%;border:3px solid #E0A245;z-index:4;opacity:0}}
.ph{{position:absolute;border-radius:54px;background:#1C1C1F;padding:14px;box-shadow:0 50px 100px rgba(0,0,0,.7),0 0 0 1px #2E2E33}}
.ph .in{{border-radius:42px;overflow:hidden;background:#0B0B0C;position:relative}}
.ph img{{display:block;width:100%;position:absolute;left:0}}
.mh{{position:absolute;left:0;top:0;width:100%;opacity:0}}
.lab{{display:inline-block;font:600 22px Manrope;padding:6px 14px;border-radius:999px;border:1px solid #E0A245;color:#E0A245}}
.leg{{display:flex;gap:32px;font:500 24px Manrope;color:#C9C9CD;margin-top:14px}} .leg span{{display:flex;align-items:center;gap:10px}} .leg i{{width:28px;height:4px;border-radius:2px}}
</style></head><body><div class="bg"></div>
<div class="sc" id="s1"><div class="panel"><div class="ti">Mumbai has the sensors on paper</div><div class="su">Construction sites and their mandated dust sensors, 2025</div><svg id="c1" width="1508" height="470" style="margin-top:34px"></svg><div class="src">Sources: Karmactive (Oct 2025); Free Press Journal (Nov 2025)</div></div></div>
<div class="sc" id="s2"><div class="panel"><div class="ti">Five wards ran near twice the standard</div><div class="su">Winter average PM2.5, Oct 2024 to Jan 2025, µg/m³</div><svg id="c2" width="1508" height="470" style="margin-top:34px"></svg><div class="src">Source: CSE analysis of CPCB data (2025)</div></div></div>
<div class="sc" id="s3"><div style="position:absolute;left:0;right:0;top:300px;text-align:center"><svg width="104" height="104" viewBox="0 0 30 30"><circle id="ring" cx="15" cy="15" r="13.5" fill="none" stroke="#E0A245" stroke-width="1.6" stroke-dasharray="85" stroke-dashoffset="85" transform="rotate(-90 15 15)"/><path d="M6 18c4-6 9-6 18-3" stroke="#F2F2F2" stroke-width="1.6" fill="none" stroke-linecap="round"/><circle cx="11" cy="11" r="2" fill="#E0A245"/><circle cx="17" cy="9" r="1.5" fill="#E0A245"/><circle cx="21" cy="12" r="1.2" fill="#E0A245"/></svg>
<div class="h" id="logo" style="font-size:150px;margin-top:18px">DustTrace</div>
<div style="margin-top:30px;display:flex;justify-content:center;gap:70px;font:500 44px Manrope;color:#A3A3A8"><span id="w1">Predict</span><span id="w2" style="color:#E0A245">Prevent</span><span id="w3">Prove</span></div></div></div>
<div class="sc" id="s4"><div class="panel"><div class="ti">K-East PM10 forecast, next 48 hours</div><div class="su">Hourly, µg/m³, with the forecast's likely range</div><svg id="c4" width="1508" height="500" style="margin-top:24px"></svg><div class="src">Prototype output on demo data</div></div></div>
<div class="sc" id="s5"><div class="chip"><i></i>Dust weather, tomorrow</div><div class="win" id="mapw" style="left:120px;top:160px;width:1180px;height:760px;transform-origin:50% 40%">{maps}</div>
<div style="position:absolute;right:110px;top:300px;text-align:right"><div class="big" id="hr" style="font-size:150px">06:00</div><div class="k">Forecast plumes, by site</div></div></div>
<div class="sc" id="s6"><div class="chip"><i></i>Site manager app</div>
<div class="ph" id="pa" style="left:560px;top:100px;width:368px"><div class="in" style="height:697px"><img src="{u(K/'phone/p3-manager-plan.png')}" style="top:-58px"></div></div>
<div class="ph" id="pb" style="left:1010px;top:120px;width:368px"><div class="in" style="height:697px"><img src="{u(K/'phone/p3-manager-plan.png')}" style="top:-58px"><img id="p4" src="{u(K/'phone/p4-manager-accepted.png')}" style="top:-58px;opacity:0"></div></div>
<div class="rip" id="rip2"></div><div class="cur" id="cur2"></div></div>
<div class="sc" id="s7"><div class="panel" style="width:1080px"><div class="ti">PM10 on high-risk days, weekly</div><div class="leg"><span><i style="background:#C27F26"></i>K-East, with DustTrace</span><span><i style="background:#6F6F75"></i>Control wards</span></div><svg id="c7" width="968" height="470" style="margin-top:18px"></svg><div class="src">Simulated pilot on demo data</div></div>
<div style="position:absolute;left:1300px;top:230px;width:500px"><div class="big" id="n7" style="font-size:180px">0%</div><div class="k" style="margin-top:16px">PM10 on high-risk days, K-East versus control wards</div><div class="lab" style="margin-top:24px">Simulated pilot, demo data</div></div></div>
<div class="sc" id="s8"><div style="position:absolute;left:160px;top:330px;width:1600px"><div class="h" id="e1" style="font-size:100px">Mumbai already paid for the sensors.</div><div class="h" id="e2" style="font-size:100px;margin-top:10px;color:#E0A245">DustTrace turns them into prevention.</div>
<div class="k" id="e3" style="margin-top:60px">Team ARA IGNITE: Ansh, Dhruv, Anuj, Sarang<br><span style="color:#6F6F75">Techfest IIT Bombay, InnovateX 2026–27, Theme 2: Rising AQI</span></div></div></div>
<div class="cap" id="cap"></div>
<script>
const $=id=>document.getElementById(id);
const cl=(x,a=0,b=1)=>Math.min(b,Math.max(a,x));
const eo=x=>1-Math.pow(1-cl(x),3);
const io=x=>{{x=cl(x);return x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2}};
const AM='#C27F26', GR='#6F6F75', INK='#F2F2F2', MU='#8E8E94', GRID='#25252A';
function hbars(svg,rows,max,p,opt={{}}){{
  const W=+svg.getAttribute('width'),L=opt.L||430,R=150,top=10,bh=opt.bh||44,gap=opt.gap||104;
  const x=v=>L+(W-L-R)*v/max; let s='';
  rows.forEach(([lab,v,hl,vlab],i)=>{{const y=top+i*gap; const pp=eo((p-i*.12)/.7); const w=Math.max(0,(x(v)-L)*pp);
    s+=`<text x="${{L-24}}" y="${{y+bh/2+9}}" text-anchor="end" font-size="27" font-weight="${{hl?600:500}}" fill="${{hl?INK:'#C9C9CD'}}">${{lab}}</text>`;
    s+=`<path d="M${{L}} ${{y}} h${{Math.max(0,w-4)}} a4 4 0 0 1 4 4 v${{bh-8}} a4 4 0 0 1 -4 4 h-${{Math.max(0,w-4)}}z" fill="${{hl?AM:GR}}"/>`;
    s+=`<text x="${{L+w+16}}" y="${{y+bh/2+10}}" font-size="30" font-weight="600" fill="${{INK}}" opacity="${{cl((pp-.6)/.4)}}">${{vlab||v}}</text>`}});
  if(opt.ref){{const rx=x(opt.ref[0]),o=eo((p-.85)/.3); s+=`<line x1="${{rx}}" x2="${{rx}}" y1="0" y2="${{top+rows.length*gap-30}}" stroke="${{INK}}" stroke-width="2" opacity="${{.55*o}}"/><text x="${{rx+12}}" y="${{top+rows.length*gap-6}}" font-size="24" fill="${{INK}}" opacity="${{o}}">${{opt.ref[1]}}</text>`}}
  svg.innerHTML=s}}
// forecast data
const FC=[];for(let i=0;i<=48;i++){{const t=12+i,hod=t%24,day=Math.floor(t/24);const m=Math.exp(-Math.pow((hod-9)/2.8,2)),n=Math.exp(-Math.pow((hod-22)/2.5,2))*.5;FC.push((62+(day===1?30:12)+(day===1?70:35)*m+25*n)*1.18)}};const FS=FC.map((v,i)=>{{let a=0,c=0;for(let j=-3;j<=3;j++){{const q=FC[i+j];if(q!==undefined){{a+=q;c++}}}}return a/c}});FC.splice(0,FC.length,...FS);
function fchart(p){{
  const svg=$('c4'),W=1508,H=500,L=80,R=30,T=20,Bm=60,ymax=200;
  const x=i=>L+(W-L-R)*i/48,y=v=>T+(H-T-Bm)*(1-v/ymax);let s='';
  [0,50,100,150,200].forEach(v=>s+=`<line x1="${{L}}" x2="${{W-R}}" y1="${{y(v)}}" y2="${{y(v)}}" stroke="${{GRID}}"/><text x="${{L-14}}" y="${{y(v)+8}}" text-anchor="end" font-size="22" fill="${{MU}}">${{v}}</text>`);
  [[0,'Thu 12:00','start'],[12,'Fri 00:00','middle'],[24,'Fri 12:00','middle'],[36,'Sat 00:00','middle'],[48,'Sat 12:00','end']].forEach(([i,l,a])=>s+=`<text x="${{x(i)}}" y="${{H-18}}" text-anchor="${{a}}" font-size="22" fill="${{MU}}">${{l}}</text>`);
  // avoid window Fri 07-11 => i=19..23
  const aw=eo((p-.62)/.25);s+=`<rect x="${{x(19)}}" y="${{T}}" width="${{x(23)-x(19)}}" height="${{H-T-Bm}}" fill="rgba(224,162,69,${{.12*aw}})"/><text x="${{x(21)}}" y="${{H-Bm-16}}" text-anchor="middle" font-size="22" font-weight="600" fill="${{INK}}" opacity="${{aw}}">Avoid 07–11</text>`;
  s+=`<line x1="${{L}}" x2="${{W-R}}" y1="${{y(100)}}" y2="${{y(100)}}" stroke="${{INK}}" stroke-width="2" opacity=".5"/><text x="${{L+12}}" y="${{y(100)-12}}" font-size="22" fill="${{INK}}" opacity=".85">National 24-h standard, 100</text>`;
  const n=Math.max(1,Math.round(48*eo(p/.6)));
  const up=FC.slice(0,n+1).map((v,i)=>`${{x(i)}} ${{y(v*1.13)}}`),dn=FC.slice(0,n+1).map((v,i)=>`${{x(i)}} ${{y(v*.87)}}`).reverse();
  s+=`<path d="M${{up.join(' L')}} L${{dn.join(' L')}}Z" fill="${{AM}}" opacity=".14"/>`;
  s+=`<path d="M${{FC.slice(0,n+1).map((v,i)=>`${{x(i)}} ${{y(v)}}`).join(' L')}}" fill="none" stroke="${{AM}}" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/>`;
  const pk=21, po=eo((p-.75)/.2);
  s+=`<circle cx="${{x(pk)}}" cy="${{y(FC[pk])}}" r="7" fill="${{AM}}" stroke="#141416" stroke-width="3" opacity="${{po}}"/><g opacity="${{po}}"><line x1="${{x(pk)+10}}" y1="${{y(FC[pk])-6}}" x2="${{x(pk)+60}}" y2="${{y(188)}}" stroke="${{INK}}" stroke-width="1.5" opacity=".6"/><text x="${{x(pk)+70}}" y="${{y(188)+6}}" font-size="30" font-weight="700" fill="${{INK}}">78% chance above 100</text><text x="${{x(pk)+70}}" y="${{y(188)+38}}" font-size="22" fill="#C9C9CD">Peak ${{Math.round(FC[pk])}} µg/m³, Fri 09:00</text></g>`;
  $('c4').innerHTML=s}}
const KE=[148,152,145,150,147,138,131,128,124,129,125],CW=[146,149,147,151,148,149,146,150,147,151,148];
function didchart(p){{
  const W=968,H=470,L=70,R=110,T=20,Bm=50,y0=110,y1=160;const n=KE.length;
  const x=i=>L+(W-L-R)*i/(n-1),y=v=>T+(H-T-Bm)*(1-(v-y0)/(y1-y0));let s='';
  [110,120,130,140,150,160].forEach(v=>s+=`<line x1="${{L}}" x2="${{W-R}}" y1="${{y(v)}}" y2="${{y(v)}}" stroke="${{GRID}}"/><text x="${{L-12}}" y="${{y(v)+7}}" text-anchor="end" font-size="20" fill="${{MU}}">${{v}}</text>`);
  for(let i=0;i<n;i++){{const w=i-4;s+=`<text x="${{x(i)}}" y="${{H-14}}" text-anchor="middle" font-size="19" fill="${{MU}}">${{w<0?'W'+w:(w===0?'Start':'W+'+w)}}</text>`}}
  s+=`<line x1="${{x(4)}}" x2="${{x(4)}}" y1="${{T}}" y2="${{H-Bm}}" stroke="${{INK}}" stroke-width="1.5" opacity=".35"/><text x="${{x(4)+10}}" y="${{T+22}}" font-size="21" fill="#C9C9CD">Pilot starts</text>`;
  const k=Math.max(1,Math.round((n-1)*eo(p/.7)));
  const pth=a=>'M'+a.slice(0,k+1).map((v,i)=>`${{x(i)}} ${{y(v)}}`).join(' L');
  s+=`<path d="${{pth(CW)}}" fill="none" stroke="${{GR}}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>`;
  s+=`<path d="${{pth(KE)}}" fill="none" stroke="${{AM}}" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/>`;
  const eo2=eo((p-.72)/.2);
  s+=`<g opacity="${{eo2}}"><circle cx="${{x(n-1)}}" cy="${{y(CW[n-1])}}" r="6" fill="${{GR}}" stroke="#141416" stroke-width="3"/><circle cx="${{x(n-1)}}" cy="${{y(KE[n-1])}}" r="7" fill="${{AM}}" stroke="#141416" stroke-width="3"/><text x="${{x(n-1)+16}}" y="${{y(CW[n-1])+8}}" font-size="24" font-weight="600" fill="${{INK}}">148</text><text x="${{x(n-1)+16}}" y="${{y(KE[n-1])+8}}" font-size="24" font-weight="600" fill="${{INK}}">125</text></g>`;
  $('c7').innerHTML=s}}
const SC=[['s1',0,4.7],['s2',4.5,9.2],['s3',9.0,12.2],['s4',12.0,17.2],['s5',17.0,21.2],['s6',21.0,24.7],['s7',24.5,28.0],['s8',27.8,30.5]];
const CAP=[[0.3,4.5,'Mumbai required every site to run a dust sensor. Far fewer report.'],[4.8,9.0,'Last winter, five wards averaged nearly twice the PM2.5 standard.'],[9.3,12.0,'DustTrace stops construction dust before it reaches people.'],[12.3,17.0,'It forecasts tomorrow’s dust, ward by ward, 48 hours ahead…'],[17.3,21.0,'…and shows where each site’s plume will drift.'],[21.3,24.5,'Sites get a plan the evening before, and accept it in one tap.'],[24.8,27.8,'A case only closes when the air measurably improves.']];
function vis(a,b,t,f=.4){{return cl((t-a)/f)*cl((b-t)/f)}}
function setT(t){{
  SC.forEach(([id,a,b])=>{{const o=vis(a,b,t);const e=$(id);e.style.opacity=o;e.style.transform=`translateY(${{(1-eo((t-a)/.6))*24}}px)`}});
  const c=CAP.find(x=>t>=x[0]&&t<x[1]);const cp=$('cap');if(c){{cp.textContent=c[2];cp.style.opacity=vis(c[0],c[1],t,.25)}}else cp.style.opacity=0;
  hbars($('c1'),[['Active construction sites',1200,0,'~1,200'],['Sensors installed, Nov 2025',662,0],['Reaching BMC’s dashboard',400,1,'~400'],['Found switched off',117,0]],1200,(t-.3)/2.4);
  hbars($('c2'),[['Deonar',79.6,1],['Shivaji Nagar',75.8,1],['Malad West',74.5,1],['Mazgaon',73.0,1],['Sewri',70.5,1]],90,(t-4.9)/2.2,{{ref:[40,'Annual standard, 40'],gap:84,bh:40}});
  $('ring').style.strokeDashoffset=85*(1-eo((t-9.2)/1.0));$('logo').style.opacity=eo((t-9.5)/.5);
  [['w1',10.1],['w2',10.5],['w3',10.9]].forEach(([id,s])=>{{$(id).style.opacity=eo((t-s)/.4)}});
  fchart((t-12.3)/4.2);
  const ht=6+cl((t-17.3)/3.5)*8,h0=Math.floor(ht),fr=ht-h0;
  for(let h=6;h<=14;h++){{let o=0;if(h===h0)o=1;else if(h===h0+1)o=io(cl((fr-.55)/.45));$('m'+h).style.opacity=o}}
  $('hr').textContent=String(Math.min(14,h0+(fr>.78?1:0))).padStart(2,'0')+':00';$('mapw').style.transform=`scale(${{1+.04*cl((t-17)/4)}})`;
  $('pa').style.transform=`rotate(-3deg) translateY(${{(1-eo((t-21.1)/.7))*80}}px)`;$('pb').style.transform=`rotate(3deg) translateY(${{(1-eo((t-21.4)/.7))*80}}px)`;
  const ax=1120,ay=489,p2=io((t-22.0)/.9),c2x=ax+220*(1-p2),c2y=ay+160*(1-p2);
  $('cur2').style.left=(c2x-15)+'px';$('cur2').style.top=(c2y-15)+'px';
  const r2=cl((t-23.0)/.5);$('rip2').style.left=(ax-15)+'px';$('rip2').style.top=(ay-15)+'px';$('rip2').style.opacity=r2>0&&r2<1?1-r2:0;$('rip2').style.transform=`scale(${{1+r2*2.4}})`;
  $('cur2').style.opacity=t<23.6?1:1-cl((t-23.6)/.3);$('p4').style.opacity=io((t-23.2)/.4);
  didchart((t-24.8)/2.4);$('n7').textContent='−'+Math.round(11*eo((t-25.6)/1.3))+'%';
  $('e1').style.opacity=eo((t-28.0)/.5);$('e2').style.opacity=eo((t-28.4)/.5);$('e3').style.opacity=eo((t-28.8)/.5);
}}
setT(0);
</script></body></html>'''
(V/'anim2.html').write_text(html)
async def main():
    out=V/'frames2'
    frames=[int(x) for x in sys.argv[1:]]
    if not frames:
        if out.exists(): shutil.rmtree(out)
        frames=range(900)
    out.mkdir(exist_ok=True)
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1920,'height':1080})
        errs=[];pg.on('pageerror',lambda e:errs.append(str(e)))
        await pg.goto(u(V/'anim2.html')); await pg.wait_for_timeout(800)
        for f in frames:
            await pg.evaluate(f'setT({f/30})')
            await pg.screenshot(path=str(out/f'f{f:04d}.jpg'),type='jpeg',quality=93)
        print('errors',errs); await b.close()
asyncio.run(main())
