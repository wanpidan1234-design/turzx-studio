/* Display-only views. All account values arrive from the local read-only bridge. */
(() => {
  'use strict';
  const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const dateFormat = new Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false});
  const clockFormat = new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Shanghai', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false});
  const fullDateFormat = new Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
  const dayFormat = new Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'});
  const isOld = (source={}, offline=false) => offline || source.status==='stale' || (finite(source.observed_at) && Date.now()/1000-source.observed_at>(source.stale_seconds||180));
  const syncTime = source => finite(source?.observed_at)?clockFormat.format(new Date(source.observed_at*1000)):'未同步';
  const plans = {pro:'Pro', plus:'Plus', free:'Free', team:'Team', business:'Business', enterprise:'Enterprise', edu:'Edu', go:'Go'};
  const planName = data => data.account?.plan_type ? `ChatGPT ${plans[data.account.plan_type] || data.account.plan_type}` : '套餐未提供';
  const bucketName = bucket => bucket?.name || (bucket?.id === 'codex' ? 'Work / Codex' : bucket?.id) || 'Work / Codex';
  const windowName = (window, index) => {
    const minutes = window.duration_minutes;
    if (minutes === 10080) return '周窗口';
    if (!finite(minutes)) return `窗口 ${index+1}`;
    return minutes % 60 === 0 ? `${minutes/60} 小时窗口` : `${minutes} 分钟窗口`;
  };
  const remaining = value => finite(value) ? new Intl.NumberFormat('zh-CN',{maximumFractionDigits:1}).format(value) : '—';
  const creditBalance = bucket => {
    const credits = bucket?.credits;
    if (credits?.unlimited === true) return '不设上限';
    if (credits?.balance != null && Number.isFinite(Number(credits.balance))) {
      return new Intl.NumberFormat('zh-CN', {maximumFractionDigits:2}).format(Number(credits.balance));
    }
    return '来源未提供';
  };
  function countdown(at) {
    if (!finite(at)) return '重置时间未提供';
    const seconds = Math.ceil(at-Date.now()/1000);
    if (seconds <= 0) return '等待额度更新';
    const minutes = Math.ceil(seconds/60), days = Math.floor(minutes/1440), hours = Math.floor(minutes%1440/60);
    if (days) return `${days} 天 ${hours} 小时后重置`;
    if (hours) return `${hours} 小时 ${minutes%60} 分后重置`;
    return `${minutes} 分后重置`;
  }
  function featureCell(item, source, offline) {
    const old=isOld(source,offline),value=item.remaining,expired=finite(item.resets_at)&&item.resets_at<=Date.now()/1000;
    const blocked=(source.blocked_features||[]).includes(item.id);
    const note=old?'上次读取剩余':blocked?'当前受限':expired?'等待更新':value===0?'额度已耗尽':'剩余次数';
    return `<section class="feature-cell ${old||expired?'old':''}"><h2 data-note="${safe(note)}">${safe(item.name)}</h2><p class="feature-source">ChatGPT · ${note}</p><div class="feature-value">${remaining(value)}${finite(value)?'<span>次</span>':''}</div><div class="feature-reset"><strong>${safe(old?'重置时间待确认':countdown(item.resets_at))}</strong><span>${finite(item.resets_at)?safe(dateFormat.format(new Date(item.resets_at*1000)))+' 重置':'来源未提供时间'}</span></div></section>`;
  }
  function sharedCell(data,bucket,offline) {
    const old=isOld(data,offline),windows=bucket?.windows||[];
    return `<section class="feature-cell shared-cell ${old?'old':''} ${windows.length>1?'compact':''}"><h2>${safe(bucketName(bucket))}</h2><div class="shared-windows">${windows.length?windows.map((w,i)=>{const expired=finite(w.resets_at)&&w.resets_at<=Date.now()/1000;return `<div class="shared-window ${expired?'old':''}"><p class="feature-source">${safe(windowName(w,i))} · ${old?'上次剩余':w.remaining_percent===0?'额度已耗尽':'共享额度剩余'}</p><div class="feature-value">${remaining(w.remaining_percent)}${finite(w.remaining_percent)?'<span>%</span>':''}</div><div class="shared-meter"><i style="width:${finite(w.remaining_percent)?w.remaining_percent:0}%"></i></div><div class="feature-reset"><strong>${safe(old?'重置时间待确认':countdown(w.resets_at))}</strong><span>${finite(w.resets_at)?safe(dateFormat.format(new Date(w.resets_at*1000)))+' 重置':'来源未提供时间'}</span></div></div>`;}).join(''):'<p class="feature-source">尚未读取到共享额度</p><div class="feature-value">—</div>'}</div></section>`;
  }
  const renewal = (bill,full=false) => bill.will_renew===false?'不再自动续费':finite(bill.renews_at)?(full?fullDateFormat:dateFormat).format(new Date(bill.renews_at*1000)):'来源未提供';
  function empty(data) {
    const loading = data.status === 'loading';
    return `<div class="subscription-empty"><h2>${loading?'正在读取订阅数据':data.account?'暂时无法读取额度':'等待连接账户'}</h2><p>${safe(data.error || (loading?'正在连接本机 Codex 登录账户。':'请在电脑端登录 Codex，再刷新订阅数据。'))}</p><div class="subscription-empty-values"><div>套餐<strong>—</strong></div><div>剩余额度<strong>—</strong></div><div>重置时间<strong>—</strong></div></div></div>`;
  }
  function overview(data, bucket, offline) {
    if (!data.account) return empty(data);
    const features=data.chatgpt_feature_limits||{},bill=data.billing||{};
    const items=features.items?.length?features.items.slice(0,2):[{name:'深度研究',remaining:null},{name:'图像生成',remaining:null}];
    const cells=items.map(item=>featureCell(item,features,offline));
    const researchIndex=items.findIndex(item=>item.id==='deep_research'||item.name==='深度研究');
    const shared=sharedCell(data,bucket,offline);
    if(researchIndex>=0){const [research]=cells.splice(researchIndex,1);cells.push(research);}
    cells.unshift(shared);
    return `<div class="subscription-identity"><div><h2>${safe(planName(data))}</h2><span>${safe(data.account.email || '已连接账户')}</span></div></div><div class="subscription-content combined-quotas">${cells.join('')}</div><div class="subscription-extras combined-extras"><div class="${isOld(bill,offline)?'source-old':''}"><span>${isOld(bill,offline)?'续费 · 旧数据':'下次续费'}</span><strong>${safe(renewal(bill))}</strong></div><div><span>自动续费</span><strong>${bill.will_renew===true?'已开启':bill.will_renew===false?'已关闭':'来源未提供'}</strong></div><div><span>额外 credits</span><strong>${safe(creditBalance(bucket))}</strong></div><div><span>重置机会</span><strong>${Number.isInteger(data.reset_count)?data.reset_count+' 次':'来源未提供'}</strong></div></div>`;
  }
  function billing(data, offline) {
    if (!data.account) return empty(data);
    const b=data.billing||{},platforms={chatgpt_mobile_android:'Google Play',chatgpt_mobile_ios:'App Store',chatgpt_web:'ChatGPT 网页',web:'ChatGPT 网页'};
    const period=finite(b.period_start)&&finite(b.period_end)?`${dayFormat.format(new Date(b.period_start*1000))} – ${dayFormat.format(new Date(b.period_end*1000))}`:'来源未提供';
    const pricing=data.plan_pricing||{},price=pricing.monthly_prices?.[b.plan_code];
    const hasPrice=pricing.kind==='catalog_reference'&&pricing.currency==='USD'&&b.currency==='USD'&&b.billing_period==='monthly'&&finite(price)&&price>=0;
    const priceOld=isOld(pricing,offline)||isOld(b,offline);
    const priceText=hasPrice?`${new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(price)} USD / 月`:'来源未提供';
    const rows=[['当前账期',period],['下次续费',renewal(b,true)],['权益到期',finite(b.expires_at)?fullDateFormat.format(new Date(b.expires_at*1000)):'来源未提供'],['自动续费',b.will_renew===true?'已开启':b.will_renew===false?'已关闭':'来源未提供'],['订阅周期',({monthly:'每月',annual:'每年',yearly:'每年'})[b.billing_period]||b.billing_period||'来源未提供'],[priceOld?'套餐标价 · 上次读取':'套餐标价',priceText,priceOld]];
    return `<div class="subscription-billing subscription-content"><div class="subscription-account"><h2>${safe(planName(data))}</h2><p>${b.active===true?'订阅有效':b.active===false?'订阅未生效':'订阅状态未提供'}</p><p class="subscription-email">${safe(data.account.email || '账户邮箱未提供')}</p><div class="subscription-account-state"><span>订阅渠道</span><strong>${safe(platforms[b.purchase_platform]||b.purchase_platform||'来源未提供')}</strong><small>${b.is_delinquent===true?'账户存在欠款，请查看官方账单':'续费信息来自 ChatGPT 账户'}</small></div></div><dl>${rows.map(([label,value,old])=>`<div class="${old?'source-old':''}"><dt>${label}</dt><dd>${safe(value)}</dd></div>`).join('')}</dl></div><p class="subscription-note">${safe(b.error||pricing.error||(hasPrice?'官方美元目录参考价；实扣可能因税费、折扣及购买渠道不同。':'实扣金额未提供；未匹配到当前套餐的美元月费标价。'))}</p>`;
  }
  function entitlements(data, bucket, offline) {
    if (!data.account) return empty(data);
    const source=data.chatgpt_feature_limits||{},old=isOld(source,offline),items=source.items||[],voice=data.chatgpt_voice||{},voiceOld=isOld(voice,offline);
    const allRows=items.map(item=>{const expired=finite(item.resets_at)&&item.resets_at<=Date.now()/1000,blocked=(source.blocked_features||[]).includes(item.id),note=old?' · 上次读取':blocked?' · 当前受限':expired?' · 等待更新':item.remaining===0?' · 已耗尽':'';return {old:old||expired,cells:[item.name,`${remaining(item.remaining)}${finite(item.remaining)?' 次':''}${note}`,finite(item.resets_at)?dateFormat.format(new Date(item.resets_at*1000))+' 重置':'时间未提供']};});
    const restrictions=source.model_restrictions||[];
    if(!source.model_counters_provided) allRows.push({old,cells:['普通聊天','次数未提供',old?'限制状态待刷新':restrictions.length?'有模型受限':source.model_status_provided?'未报告模型限制':'状态未提供']});
    for(const item of restrictions) {const expired=finite(item.resets_at)&&item.resets_at<=Date.now()/1000;allRows.push({old:old||expired,cells:[item.model,old?'上次报告受限':expired?'等待状态更新':'模型受限',finite(item.resets_at)?dateFormat.format(new Date(item.resets_at*1000))+' 重置':'时间未提供']});}
    const modes=voice.modes?.length?voice.modes:[{name:'语音',available:null}];
    for(const mode of modes) {const expired=finite(mode.resets_at)&&mode.resets_at<=Date.now()/1000;allRows.push({old:voiceOld||expired,cells:[mode.name,voiceOld?'上次状态 · 待刷新':expired?'等待状态更新':mode.available===true?'可用 · 分钟数未提供':mode.available===false?'当前不可用':'状态未提供',finite(mode.resets_at)?dateFormat.format(new Date(mode.resets_at*1000))+' 重置':'时间未提供']});}
    const pages=Math.max(1,Math.ceil(allRows.length/4)),page=Math.floor(Date.now()/15000)%pages,rows=allRows.slice(page*4,page*4+4);
    return `<div class="subscription-identity"><h2>ChatGPT 功能额度</h2><span>${pages>1?`明细 ${page+1}/${pages} · 15 秒换页`:'次数与可用状态'}</span></div><div class="subscription-content subscription-entitlements"><div class="entitlement-row entitlement-head"><span>功能</span><span>剩余 / 状态</span><span>重置 / 限制 · 北京</span></div>${rows.map(row=>`<div class="entitlement-row ${row.old?'source-old':''}">${row.cells.map(cell=>`<span>${safe(cell)}</span>`).join('')}</div>`).join('')}</div><p class="subscription-note">${safe(source.error||voice.error||'“可用”不代表无限；聊天条数与语音分钟数未返回时不推算。')}</p>`;
  }
  function render(data={}, view='overview', selected='codex', disconnected=false, background='none', transparency=25) {
    const hasBackground=['it','anime','dragon'].includes(background);
    const opacity=1-Math.min(100,Math.max(0,finite(transparency)?transparency:25))/100;
    const wallpaper=hasBackground?`<picture class="subscription-wallpaper" aria-hidden="true"><source media="(max-aspect-ratio: 1/1)" srcset="assets/subscription/${background}-portrait-screen.png?v=2"><img src="assets/subscription/${background}-landscape-screen.png?v=2" alt=""></picture>`:'';
    const source=view==='billing'?(data.billing||{}):view==='entitlements'?(data.chatgpt_feature_limits||{}):data;
    const old=isOld(source,disconnected);
    const buckets = data.buckets || [], bucket = buckets.find(item=>item.id===selected) || buckets[0];
    const names = {overview:'OpenAI 订阅', billing:'套餐与续费', entitlements:'ChatGPT 额度明细'};
    const body = view==='billing'?billing(data,disconnected):view==='entitlements'?entitlements(data,bucket,disconnected):overview(data,bucket,disconnected);
    const stamp=view==='overview'?`ChatGPT ${syncTime(data.chatgpt_feature_limits)} · Work ${syncTime(data)}`:view==='billing'?`账单 ${syncTime(source)} · 标价 ${syncTime(data.plan_pricing)}`:`额度 ${syncTime(source)} · 语音 ${syncTime(data.chatgpt_voice)}`;
    return `<section data-view="${view}" class="subscription-screen ${old?'is-stale':''} ${view==='overview'?'combined-screen':''} ${hasBackground?`has-wallpaper wallpaper-${background}`:''}" style="--wallpaper-opacity:${opacity}">${wallpaper}<header class="subscription-head"><h1><svg class="subscription-code-mark" viewBox="0 0 32 32" aria-hidden="true"><path d="m10 8-7 8 7 8m12-16 7 8-7 8M19 5l-6 22"/></svg>OpenAI 订阅</h1><span class="subscription-sync ${old?'old':''}">${old?'○ 旧数据':source.status==='live'?'● 已同步':'◌ 未同步'}</span></header>${body}<footer class="subscription-footer"><span class="subscription-pages">${['overview','billing','entitlements'].map(v=>`<i class="${v===view?'selected':''}"></i>`).join('')} ${['overview','billing','entitlements'].indexOf(view)+1} / 3 ${names[view]||names.overview}</span><span>${safe(stamp)}</span></footer></section>`;
  }
  window.TurzxSubscription = {render, planName, bucketName, creditBalance};
})();
