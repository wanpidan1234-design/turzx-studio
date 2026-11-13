(() => {
  'use strict';
  const root = document.getElementById('display');
  const params = new URLSearchParams(location.search);
  const renderer = params.get('renderer') === '1';
  const pinnedPage = params.get('page');
  const safe = value => String(value ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const number = (value, digits=0) => finite(value) ? value.toFixed(digits) : null;
  const metric = (value, unit='', digits=0) => finite(value) ? `${number(value,digits)}<span class="unit">${safe(unit)}</span>` : '<span class="unavailable">—</span>';
  let state = {page:'system',rotation:270,streaming:false,focus:{duration:1500,remaining:1500,running:false},note:'把注意力留给真正重要的事。'};
  let metrics = {};
  let failed = false;
  let stateReceivedAt = performance.now();
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let animationId = null;
  let lastAmbientPaint = 0;
  const dateFormat = new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'long',day:'numeric',weekday:'long'});
  const timeFormat = zone => new Intl.DateTimeFormat('en-GB',{timeZone:zone,hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
  const time = (zone='Asia/Shanghai',withSeconds=false) => timeFormat(zone).format(new Date()).slice(0,withSeconds?8:5);
  const duration = seconds => {const n=Math.max(0,Math.ceil(finite(seconds)?seconds:1500));return `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;};
  const stale = () => failed || !metrics.timestamp || Date.now()-Date.parse(metrics.timestamp)>6500;
  const sensorState = () => !metrics.timestamp ? ['','等待采样'] : stale()?['stale','数据已过期']:['live','实时'];
  const footer = (text,clock=true) => `<footer class="screen-foot"><span class="foot-note">${safe(text)}</span>${clock?`<time>${time()}</time>`:''}</footer>`;
  const header = (title,label,kind='') => `<header class="screen-head"><h1>${safe(title)}</h1>${label?`<span class="status ${kind}">${safe(label)}</span>`:'<span class="brand-name">TURZX STUDIO</span>'}</header>`;
  const level = value => `<div class="level"><i style="width:${finite(value)?Math.max(0,Math.min(100,value)):0}%"></i></div>`;
  const sample = entry => typeof entry==='number'?entry:typeof entry?.value==='number'?entry.value:NaN;
  function lineChart(histories,colors,height=140,fixedMax=null){
    const series=histories.map(history=>(Array.isArray(history)?history:[]).slice(-60).map(sample));
    const all=series.flat().filter(finite);
    if(!all.length)return '<div class="chart-empty">等待真实采样</div>';
    const maximum=fixedMax||Math.max(1,...all), count=Math.max(2,...series.map(a=>a.length)), w=600,h=height,pad=8;
    let paths='';
    series.forEach((list,j)=>{let d='',drawing=false;list.forEach((v,i)=>{if(!finite(v)){drawing=false;return;}const x=pad+i/(count-1)*(w-pad*2),y=h-pad-v/maximum*(h-pad*2);d+=`${drawing?'L':'M'}${x.toFixed(1)},${y.toFixed(1)} `;drawing=true;});paths+=`<path d="${d}" fill="none" stroke="${colors[j]}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>`;});
    return `<svg class="chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-label="实测历史曲线"><path d="M0 ${h-1}H${w} M0 ${h/2}H${w} M0 1H${w}" fill="none" stroke="currentColor" stroke-opacity=".14" stroke-width="1"/>${paths}</svg>`;
  }
  function rate(value){if(!finite(value))return '<span class="unavailable">—</span>';const units=['B/s','KiB/s','MiB/s','GiB/s'];let n=Math.max(0,value),i=0;while(n>=1024&&i<3){n/=1024;i++;}return `${n.toFixed(n>=100?0:n>=10?1:2)}<span class="unit">${units[i]}</span>`;}
  function uptime(value){if(!finite(value))return '运行时间未接入';const hours=Math.floor(value/3600);return `已运行 ${hours>=24?Math.floor(hours/24)+'天 ':''}${hours%24}小时 ${Math.floor(value/60)%60}分`;}
  function systemPage(){
    const cpu=metrics.cpu||{},mem=metrics.memory||{},gpu=metrics.gpu||{},disk=(metrics.disks||[])[0],s=sensorState();
    return `<section class="screen system-screen">${header('性能脉搏',s[1],s[0])}<div class="screen-main system-layout"><section class="cpu-channel"><div class="channel-name">CPU <small>${finite(cpu.logical)?cpu.logical+' 线程':''}</small></div><div class="cpu-number">${metric(cpu.percent,'%')}</div><div class="hardware-name">${safe(cpu.name||'处理器信息未接入')}</div><div class="cpu-chart">${lineChart([cpu.history],['#8bd3a0'],150,100)}</div><div class="chart-caption"><span>最近 ${Math.min(60,(cpu.history||[]).length)} 次实际采样</span><span>0–100%</span></div></section><div class="side-channels"><section class="sensor-block"><div class="sensor-line"><h2>内存</h2><strong>${metric(mem.percent,'%')}</strong></div>${level(mem.percent)}<div class="sensor-sub">${finite(mem.used_gb)&&finite(mem.total_gb)?`${mem.used_gb.toFixed(1)} / ${mem.total_gb.toFixed(1)} GiB`:'容量未接入'}</div></section><section class="sensor-block"><div class="sensor-line"><h2>GPU</h2><strong>${metric(gpu.percent,'%')}</strong></div><div class="sensor-sub">${safe(gpu.name||'显卡信息未接入')}</div><div class="sensor-sub">${finite(gpu.memory_used_gb)?'显存 '+gpu.memory_used_gb.toFixed(1)+(finite(gpu.memory_total_gb)?' / '+gpu.memory_total_gb.toFixed(1):'')+' GiB':finite(gpu.memory_total_gb)?'显存总量 '+gpu.memory_total_gb.toFixed(1)+' GiB':'显存用量未接入'}</div></section><section class="sensor-block"><div class="sensor-line"><h2>${disk?safe(disk.drive)+' 磁盘':'磁盘'}</h2><strong>${metric(disk?.percent,'%')}</strong></div><div class="sensor-sub">${disk&&finite(disk.used_gb)&&finite(disk.total_gb)?`${disk.used_gb.toFixed(0)} / ${disk.total_gb.toFixed(0)} GiB`:'容量未接入'}</div></section></div></div>${footer(finite(metrics.temperature_c)?`温度 ${metrics.temperature_c.toFixed(0)}°C · ${uptime(metrics.uptime_s)}`:`温度未接入 · ${uptime(metrics.uptime_s)}`)}</section>`;
  }
  function networkPage(){
    const n=metrics.network||{},s=sensorState(),active=(n.interfaces||[]).filter(x=>x.up).map(x=>x.name).join(' · ');
    const lane=(name,key,history,total,color)=>{const values=(history||[]).map(sample).filter(finite),peak=values.length?Math.max(...values):null;return `<section class="network-lane" style="--lane:${color}"><div class="network-flow"><div class="label">${name==='下载'?'↓':'↑'} ${name}</div><div class="flow-value">${rate(n[key])}</div><div class="network-total">${finite(total)?'累计'+(name==='下载'?'接收 ':'发送 ')+total.toFixed(2)+' GiB':'累计流量未接入'}</div></div><div class="network-graph"><div class="chart-caption"><span>━ ${name}</span><span>峰值 ${peak===null?'—':rate(peak)}</span></div>${lineChart([history],[color],150)}</div></section>`;};
    return `<section class="screen network-screen">${header('网络航道',s[1],s[0])}<div class="screen-main network-layout">${lane('下载','recv_bps',n.history_down,n.total_recv_gb,'#86c8ea')}${lane('上传','sent_bps',n.history_up,n.total_sent_gb,'#e7b45a')}</div>${footer(active?'活跃网卡 '+active:'等待网卡信息',false)}</section>`;
  }
  function clockPage(){
    const t=time('Asia/Shanghai',true),day=zone=>new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    const zones=[['东京','Asia/Tokyo'],['伦敦','Europe/London'],['纽约','America/New_York']];
    return `<section class="screen clock-screen"><div class="clock-zone-label">北京时间</div><div class="clock-main"><span class="hhmm">${t.slice(0,5)}</span><span class="ss">${t.slice(6)}</span></div><div class="clock-date">${dateFormat.format(new Date())}</div><div class="world-times">${zones.map(([name,zone])=>`<div class="world-zone"><span>${name}${day(zone)<day('Asia/Shanghai')?' · 前一天':day(zone)>day('Asia/Shanghai')?' · 后一天':''}</span><strong>${time(zone)}</strong></div>`).join('')}<div class="world-note"><span>便签</span><p>${safe(state.note||'每个当下，都值得专注。')}</p></div></div></section>`;
  }
  function focusPage(){
    const f=state.focus||{},left=finite(f.remaining)?Math.max(0,f.remaining):1500,total=finite(f.duration)&&f.duration>0?f.duration:1500,elapsed=Math.max(0,total-left),done=Math.min(100,elapsed/total*100),kind=left===0?'done':f.running?'running':left<total?'paused':'ready';
    const labels={done:'完成，休息一下',running:'专注中',paused:'已暂停',ready:'准备好，开始专注'};
    return `<section class="screen focus-screen" data-focus="${kind}"><div class="focus-state-label">${kind==='done'?'✓ ':kind==='paused'?'Ⅱ ':kind==='running'?'● ':''}${labels[kind]}</div><div class="focus-digits">${duration(left)}</div><div class="focus-progress"><i style="width:${done}%"></i></div><div class="focus-timing"><span>${kind==='ready'?'尚未开始':kind==='paused'?'已暂停 · 计时不在走':`已专注 ${Math.floor(elapsed/60)} 分 ${Math.floor(elapsed%60)} 秒`}</span><span>总时长 ${Math.floor(total/60)} 分钟${total%60?' '+total%60+' 秒':''}</span></div><div class="focus-note"><span>便签</span><p>${safe(state.note||'只做眼前这一件事。')}</p></div></section>`;
  }
  function ambientPage(){return `<section class="screen ambient-screen"><canvas id="ambient-canvas" class="ambient-canvas" aria-label="可选择的生成动画"></canvas></section>`;}
  function mediaPage(){return `<section class="screen media-screen">${header('音乐一隅','未接入媒体源')}<div class="screen-main media-layout"><div class="record-art"><span aria-hidden="true">♫</span><small>封面留位</small></div><div class="media-copy"><h2>留一个位置，<br>给喜欢的声音。</h2><p>接入播放器后，这里显示封面、曲目与进度。<br>现在没有正在播放的内容。</p><dl><div><dt>曲目</dt><dd>—</dd></div><div><dt>艺人</dt><dd>—</dd></div></dl><div class="media-progress"></div><div class="media-dashes">— <span>—</span></div></div></div></section>`;}
  function guidePage(){return `<section class="screen guide-screen">${header('一块屏幕，更多可能','')}<div class="screen-main guide-layout"><section class="guide-column"><h2>现在可体验</h2><p class="guide-intro">本机数据与生成画面</p><ul class="guide-list"><li>性能 / 网络<small>真实采样与历史曲线</small></li><li>时钟 / 专注<small>时间、倒计时与便签</small></li><li>氛围 / 校准<small>原创图形与显示检查</small></li></ul></section><section class="guide-column"><h2>等待数据源</h2><p class="guide-intro">接入后才呈现真实内容</p><ul class="guide-list"><li>媒体 / 天气<small>播放器、城市与接口</small></li><li>任务 / 训练<small>进度、阶段与提醒</small></li><li>温度 / 功耗<small>兼容的传感器接口</small></li></ul></section><section class="guide-column"><h2>仍需验证</h2><p class="guide-intro">不从产品名称推断</p><ul class="guide-list"><li>触控 / 音频<small>未确认硬件能力</small></li><li>离线播放<small>存储与固件支持</small></li><li>扩展桌面<small>官网列出，尚待实测</small></li></ul></section></div>${footer('USB 图像输出 · 实际刷新能力以本机实测为准',false)}</section>`;}
  function calibratePage(){const bars=Array.from({length:8},()=>'<i></i>').join(''),gray=Array.from({length:11},(_,i)=>{let c=Math.round(i*25.5);return `<i style="background:rgb(${c},${c},${c})"></i>`;}).join('');return `<section class="screen calibrate-screen"><span class="edge-label tl">TL</span><span class="edge-label tr">TR</span><span class="edge-label bl">BL</span><span class="edge-label br">BR</span>${header('显示校准',`${innerWidth} × ${innerHeight} · ${innerWidth>innerHeight?'横屏':'竖屏'}`)}<div class="screen-main calibrate-layout"><div class="calibration-bars">${bars}</div><div class="grayscale">${gray}</div><div class="calibration-middle"><div class="type-specimens"><span>24 px · 看清每一个细节 0123456789</span><span>28 px · 清晰来自合适的距离</span><span>32 px · 阅读舒适，信息从容</span><span>40 px · 大字，看得见</span></div><div class="circle-test" aria-label="正圆应没有拉伸"></div></div></div>${footer('四角完整 · 正圆不变形 · 灰阶可分辨',false)}</section>`;}
  const pages={system:systemPage,network:networkPage,clock:clockPage,focus:focusPage,ambient:ambientPage,openai:()=>window.TurzxSubscription.render(state.subscription,state.subscription_view,state.subscription_bucket,failed,state.subscription_background,state.subscription_background_transparency),claude:()=>window.TurzxClaude.single(state.claude,failed,state.claude_background),cswap:()=>window.TurzxClaude.overview(state.claude,failed,state.claude_background),media:mediaPage,guide:guidePage,calibrate:calibratePage};
  function paintAmbient(){
    const canvas=document.getElementById('ambient-canvas');if(!canvas||(!renderer&&document.hidden))return;
    const motion={preset:'orbit',speed:1,detail:'balanced',show_clock:true,paused:false,seed:52,time:0,...state.animation};
    const elapsed=motion.paused?0:(performance.now()-stateReceivedAt)/1000*motion.speed;
    window.TurzxAnimations.draw(canvas,{...motion,time:reducedMotion.matches?0:motion.time+elapsed,width:innerWidth,height:innerHeight});
    canvas.setAttribute('aria-label',window.TurzxAnimations.definitions[motion.preset]?.title||'生成动画');
  }
  window.captureAnimationFrame=()=>root.dataset.page==='ambient'?document.getElementById('ambient-canvas')?.toDataURL('image/png'):null;
  function render(){
    for(const [key,fallback,low,high] of [['image_brightness',112,80,140],['image_saturation',85,50,120],['image_fade',12,0,50]]){
      const value=finite(state[key])?Math.min(high,Math.max(low,state[key])):fallback;
      root.style.setProperty('--'+key.replaceAll('_','-'),value/100);
    }
    const page=pages[pinnedPage||state.page]?pinnedPage||state.page:'system';
    const keepCanvas=page==='ambient'&&root.dataset.page==='ambient'&&document.getElementById('ambient-canvas');
    root.dataset.page=page;if(!keepCanvas)root.innerHTML=pages[page]();
    if(page==='ambient')paintAmbient();
    if(failed&&!['system','network','openai','claude','cswap'].includes(page)){root.insertAdjacentHTML('beforeend','<div class="offline-band">工作台连接中断</div>');}
    if(!renderer)resumeMotion();
  }
  window.renderFrame = async (nextState,nextMetrics) => {
    if(nextState){state={...state,...nextState};stateReceivedAt=performance.now();}
    if(nextMetrics)metrics=nextMetrics;
    failed=false;await document.fonts.load('400 24px Inter');await document.fonts.ready;render();
    await Promise.all([...root.querySelectorAll('.subscription-wallpaper img, .claude-character img, .account-wallpaper img')].map(img=>img.decode().catch(()=>{})));
    window.renderReady=true;
  };
  async function poll(){try{const [sr,mr]=await Promise.all([fetch('/api/state',{cache:'no-store'}),fetch('/api/metrics',{cache:'no-store'})]);if(!sr.ok||!mr.ok)throw new Error('poll');await window.renderFrame(await sr.json(),await mr.json());}catch{failed=true;render();window.renderReady=true;}}
  function animate(timestamp){
    animationId=null;
    if(document.hidden||reducedMotion.matches||renderer||root.dataset.page!=='ambient'||state.animation?.paused)return;
    if(root.dataset.page==='ambient'&&!state.animation?.paused&&timestamp-lastAmbientPaint>=1000/30){paintAmbient();lastAmbientPaint=timestamp;}
    animationId=requestAnimationFrame(animate);
  }
  function resumeMotion(){if(animationId!==null)cancelAnimationFrame(animationId);animationId=null;if(!renderer&&!document.hidden&&!reducedMotion.matches&&root.dataset.page==='ambient'&&!state.animation?.paused)animationId=requestAnimationFrame(animate);}
  render();
  document.fonts.load('500 56px Inter').then(()=>document.fonts.ready).then(()=>{render();window.renderReady=true;});
  if(!renderer){poll();setInterval(poll,1000);resumeMotion();}
  document.addEventListener('visibilitychange',resumeMotion);reducedMotion.addEventListener('change',()=>{render();resumeMotion();});
  addEventListener('resize',render);
})();
