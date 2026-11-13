/* Original, seeded Canvas animations. A frame depends only on time and settings. */
(() => {
  'use strict';
  const TAU = Math.PI * 2;
  const definitions = {
    orbit: {title:'缓慢轨道', subtitle:'层层轨道，保持自己的节奏。', color:'#e9c398'},
    aurora: {title:'极光夜航', subtitle:'把一片流动的夜空，留在桌边。', color:'#9ce7cb'},
    flow: {title:'流光织场', subtitle:'细线交错，像一阵看得见的风。', color:'#e8bd8a'},
    stars: {title:'星际漫游', subtitle:'缓缓前行，让远方接近。', color:'#b4d6f3'}
  };
  const cache = new Map();
  function points(seed, count) {
    const key=seed+':'+count;
    if(cache.has(key))return cache.get(key);
    let a=seed>>>0;
    const random=()=>{a=(a+0x6D2B79F5)>>>0;let t=a;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return ((t^(t>>>14))>>>0)/4294967296;};
    const result=Array.from({length:count},()=>[random(),random(),random(),random()]);
    if(cache.size>8)cache.clear();cache.set(key,result);return result;
  }
  function backdrop(ctx,w,h,color){ctx.fillStyle=color;ctx.fillRect(0,0,w,h);}
  function glow(ctx,x,y,r,color){const g=ctx.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,color);g.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=g;ctx.fillRect(x-r,y-r,r*2,r*2);}
  function orbit(ctx,w,h,t,o){
    backdrop(ctx,w,h,'#0B1020');
    const portrait=h>w,cx=w*(portrait?.55:.6),cy=h*(portrait?.42:.5),n=o.detail==='light'?22:34,max=portrait?620:900;
    ctx.save();ctx.translate(cx,cy);ctx.rotate(-Math.PI/10+Math.sin(t/45)*.035);
    for(let i=0;i<n;i++){
      const f=i/(n-1),r=30+(max-30)*Math.pow(f,1.25);
      ctx.beginPath();ctx.ellipse(0,0,r,r*.4,0,0,TAU);
      ctx.strokeStyle=`rgba(233,180,138,${.12+.3*(1-f)})`;ctx.lineWidth=1;ctx.stroke();
      if(i%7===3){const a=t*.035+f*TAU+o.seed*.03;ctx.fillStyle='#E9B48A';ctx.beginPath();ctx.arc(Math.cos(a)*r,Math.sin(a)*r*.4,2,0,TAU);ctx.fill();}
    }
    ctx.restore();
  }
  function aurora(ctx,w,h,t,o){
    backdrop(ctx,w,h,'#060C13');
    for(const [x,y,z,p] of points(o.seed,o.detail==='light'?60:120)){ctx.fillStyle=`rgba(204,224,235,${.15+.35*(.5+.5*Math.sin(t*.1+p*TAU))})`;ctx.beginPath();ctx.arc(x*w,y*h*.88,.5+z*.8,0,TAU);ctx.fill();}
    const colors=['86,213,166','79,193,187','85,172,207','122,135,202','153,122,188'];
    for(let k=0;k<(o.detail==='light'?3:5);k++){
      const mid=u=>h*(.32+k*.045+.06*Math.sin(u*5+t*.08+k*.7)+.025*Math.sin(u*11-t*.04));
      const gradient=ctx.createLinearGradient(0,h*.17,0,h*.78);
      gradient.addColorStop(0,`rgba(${colors[k]},0)`);gradient.addColorStop(.5,`rgba(${colors[k]},.18)`);gradient.addColorStop(1,`rgba(${colors[k]},0)`);
      ctx.beginPath();for(let i=0;i<=90;i++){const u=i/90;if(i)ctx.lineTo(u*w,mid(u));else ctx.moveTo(0,mid(0));}for(let i=90;i>=0;i--){const u=i/90;ctx.lineTo(u*w,mid(u)+h*.14);}ctx.closePath();ctx.fillStyle=gradient;ctx.fill();
      ctx.beginPath();for(let i=0;i<=90;i++){const u=i/90;if(i)ctx.lineTo(u*w,mid(u));else ctx.moveTo(0,mid(0));}ctx.strokeStyle=`rgba(${colors[k]},.3)`;ctx.lineWidth=1;ctx.stroke();
    }
    ctx.fillStyle='#03070C';ctx.beginPath();ctx.moveTo(0,h);for(let i=0;i<=32;i++)ctx.lineTo(i/32*w,h*(.88-.035*Math.sin(i*.5)-.02*Math.sin(i*1.3)));ctx.lineTo(w,h);ctx.fill();
  }
  function flow(ctx,w,h,t,o){
    backdrop(ctx,w,h,'#0C0E14');const n=o.detail==='light'?28:44;
    const gradient=ctx.createLinearGradient(0,0,w,h);gradient.addColorStop(0,'rgba(107,199,205,.4)');gradient.addColorStop(.5,'rgba(176,184,183,.3)');gradient.addColorStop(1,'rgba(233,180,138,.45)');
    for(let j=0;j<n;j++){const v=.12+j/(n-1)*.76;ctx.beginPath();for(let i=0;i<=90;i++){const u=i/90,y=h*(v+.07*Math.sin(u*6.4+t*.08+j*.09+o.seed*.01));if(i)ctx.lineTo(u*w,y);else ctx.moveTo(0,y);}ctx.strokeStyle=gradient;ctx.lineWidth=1;ctx.stroke();}
  }
  function stars(ctx,w,h,t,o){
    backdrop(ctx,w,h,'#04060C');ctx.save();ctx.translate(w*.62,h*.4);ctx.scale(1,.55);glow(ctx,0,0,w*.52,'rgba(65,57,109,.3)');ctx.restore();
    const list=points(o.seed,o.detail==='light'?140:260);
    list.forEach(([x,y,z,p],i)=>{const px=((x+t*.0008*(.3+z))%1)*w,py=((y+t*.00025)%1)*h,bright=i<6;ctx.fillStyle=`rgba(210,219,245,${bright?.85:.15+z*.45})`;ctx.beginPath();ctx.arc(px,py,bright?1.8:.4+z*.8,0,TAU);ctx.fill();if(bright){ctx.strokeStyle='rgba(220,230,255,.35)';ctx.lineWidth=.7;ctx.beginPath();ctx.moveTo(px-5,py);ctx.lineTo(px+5,py);ctx.moveTo(px,py-5);ctx.lineTo(px,py+5);ctx.stroke();}});
  }
  const painters={orbit,aurora,flow,stars};
  function draw(canvas,options={}){
    const w=Math.round(options.width||innerWidth),h=Math.round(options.height||innerHeight);
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
    const o={preset:'orbit',time:0,seed:52,detail:'balanced',show_clock:true,...options};
    const ctx=canvas.getContext('2d',{alpha:true});ctx.setTransform(1,0,0,1,0,0);ctx.globalAlpha=1;
    (painters[o.preset]||painters.orbit)(ctx,w,h,o.time,o);
    const portrait=h>w,inset=portrait?48:56,bottom=portrait?64:48,size=portrait?88:72;
    const clock=options.clock_text||new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date());
    ctx.font=`300 ${size}px Inter, sans-serif`;ctx.textBaseline='alphabetic';ctx.fillStyle='#ECF1EC';
    if(o.show_clock)ctx.fillText(clock,inset,h-bottom);
    if(o.paused){
      const x=o.show_clock?inset+ctx.measureText(clock).width+24:inset,y=h-bottom-30;
      ctx.fillStyle='rgba(255,255,255,.08)';ctx.beginPath();ctx.roundRect(x,y,100,32,8);ctx.fill();
      ctx.font='400 18px Inter, sans-serif';ctx.fillStyle='#A9B6AF';ctx.fillText('Ⅱ 已暂停',x+12,y+23);
    }
  }
  window.TurzxAnimations={draw,definitions};
})();
