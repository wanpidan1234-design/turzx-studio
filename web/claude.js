/* Display-only Claude views. Account credentials never belong in this module. */
(() => {
  'use strict';
  const safe = value => String(value ?? '').replace(/cswap/ig, '账号服务').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const stamp = value => finite(value) ? value * 1000 : typeof value === 'string' && value ? Date.parse(value) : NaN;
  const old = (account, offline=false) => offline || account?.stale===true || ['stale','error'].includes(account?.status) || (Number.isFinite(stamp(account?.updated_at)) && Date.now()-stamp(account.updated_at)>300000);
  const used = quota => finite(quota?.utilization) && quota.utilization>=0 && quota.utilization<=100 ? quota.utilization : null;
  const remaining = quota => used(quota)===null ? null : 100-used(quota);
  const percent = value => finite(value) ? new Intl.NumberFormat('zh-CN', {maximumFractionDigits:1}).format(value) : '—';
  const activeAccount = data => (data.accounts || []).find(a=>a.id===data.active_account_id) || (data.accounts || []).find(a=>a.is_active);
  const mark = '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2v28M2 16h28M6 6l20 20M6 26 26 6M10 3l12 26M3 10l26 12M3 22 29 10M10 29 22 3"/></svg>';
  function reset(quota) {
    const ms=stamp(quota?.resets_at);
    if(!Number.isFinite(ms)||ms<=Date.now())return '';
    const minutes=Math.ceil((ms-Date.now())/60000);
    const days=Math.floor(minutes/1440),hours=Math.floor(minutes%1440/60);
    return days?`${days}天${hours?hours+'小时':''}后重置`:hours?`${hours}小时${minutes%60?minutes%60+'分':''}后重置`:`${minutes}分后重置`;
  }
  function quotaCell(title,quota,stale=false,compact=false){
    const value=used(quota),expired=Number.isFinite(stamp(quota?.resets_at))&&stamp(quota.resets_at)<=Date.now();
    const unavailable=value===null,high=!unavailable&&value>=99;
    return `<section class="claude-quota ${compact?'compact':''} ${stale||expired?'old':''} ${high?'low':''}"><h3>${safe(title)}</h3><p class="claude-quota-label">已使用</p><div class="claude-value">${percent(value)}${unavailable?'':'<small>%</small>'}</div><div class="claude-meter ${unavailable?'unknown':''}"${unavailable?' aria-label="额度未知"':` role="meter" aria-label="${safe(title)}已使用" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${value}"`}><i style="width:${unavailable?0:value}%"></i></div><div class="claude-reset"><strong>${safe(reset(quota))}</strong></div></section>`;
  }
  function windows(account,stale,compact=false){
    return quotaCell('5h 窗口',account?.usage?.five_hour,stale,compact)+quotaCell('7d 窗口',account?.usage?.seven_day,stale,compact)+quotaCell('Fable · 7d',account?.usage?.seven_day_fable,stale,compact);
  }
  function models(account){
    const rows=[['Sonnet',account?.usage?.seven_day_sonnet],['Opus',account?.usage?.seven_day_opus],['Haiku',account?.usage?.seven_day_haiku]].filter(([,q])=>used(q)!==null);
    return rows.length?`<div class="claude-models">${rows.map(([name,q])=>`<div><span>${name} 周额度已使用</span><strong>${percent(used(q))}%</strong></div>`).join('')}</div>`:'';
  }
  function wallpaper(background){
    if(background==='none')return '';
    const files={stand:'claude-v3-decorated-stand',thought:'claude-v3-decorated-thought',greeting:'claude-v3-decorated-greeting',floral:'claude-v4-floral',celestial:'claude-v4-celestial',atelier:'claude-v4-atelier',botanical:'claude-v4-botanical',paperland:'claude-v4-paperland',glasswave:'claude-v4-glasswave'};
    const prefix=Object.hasOwn(files,background)?files[background]:files.stand;
    return `<picture class="account-wallpaper" aria-hidden="true"><source media="(max-aspect-ratio: 1/1)" srcset="assets/claude/${prefix}-portrait.png"><img src="assets/claude/${prefix}-landscape.png" alt=""></picture>`;
  }
  function accountCard(account,index,data,offline){
    const active=(account.id!=null&&account.id===data.active_account_id)||account.is_active===true,stale=old(account,offline);
    const name=(account.label||`账号 ${index+1}`).replace(/^Account (\d+)$/, '账号 $1');
    const status=stale?'旧数据':account.status==='live'||account.status==='ok'?'实时':'未知';
    return `<article class="account-card ${active?'is-active':''}"><div class="account-card-identity"><div class="account-card-top"><span class="account-number">${String(index+1).padStart(2,'0')}</span><h2 title="${safe(name)}">${safe(name)}</h2>${active?'<span class="account-card-status active-account-badge">当前</span>':''}</div><p class="account-email">${safe(account.email||'')}</p><div class="account-meta"><span>${safe(account.subscription_type||'')}</span><span class="account-status ${stale?'stale':status==='实时'?'live':'unknown'}">${status}</span></div></div><div class="account-card-quotas">${windows(account,stale,true)}</div></article>`;
  }
  function scene(accounts,data,offline,singleView=false,background='stand'){
    const count=accounts.length,decorated=['stand','thought','greeting','floral','celestial','atelier','botanical','paperland','glasswave'].includes(background);
    return `<section class="claude-screen account-scene ${singleView?'claude-single':''} ${decorated?'account-scene-decorated':''}" data-count="${count}" aria-label="Claude ${singleView?'订阅':'多账号'}">${wallpaper(background)}<div class="account-content"><header class="claude-head"><h1>${mark}Claude ${singleView?'订阅':'多账号'}${!singleView?`<span>· ${count} 个</span>`:''}</h1>${data.accounts?.length>5&&!singleView?`<span>共 ${data.accounts.length} 个，显示 5 个</span>`:''}</header>${count?`<div class="account-cards">${accounts.map((a,i)=>accountCard(a,i,data,offline||data.stale===true)).join('')}</div>${singleView?models(accounts[0]):''}`:`<div class="claude-empty"><span aria-hidden="true">＋</span><h2>${singleView?'等待连接当前账号':'还没有可显示的账号'}</h2><p>连接账号服务后，显示 5h、7d 和 Fable 已使用额度。</p></div>`}</div></section>`;
  }
  function single(data={},offline=false,background='stand'){
    const account=activeAccount(data);
    return scene(account?[account]:[],data,offline,true,background);
  }
  function overview(data={},offline=false,background='stand'){
    const all=Array.isArray(data.accounts)?data.accounts:[],accounts=all.slice(0,5);
    const active=activeAccount(data);
    if(all.length>5&&active&&!accounts.includes(active))accounts[4]=active;
    return scene(accounts,data,offline,false,background);
  }
  window.TurzxClaude={single,overview,used,remaining,reset,activeAccount};
})();
