(() => {
  'use strict';
  const root=document.getElementById('display'), feedback=document.getElementById('feedback');
  let state={claude:{}}, token='', busy=false, offline=false, pending=null, pressed=false;
  let messageUntil=0, polling=false;
  const hint='点击账号卡片切换 · 已运行的 Claude Code 会话可能需要重新打开';
  function message(text,error=false){feedback.textContent=text;feedback.dataset.error=String(error);}
  function fit(){
    const portrait=innerHeight>innerWidth,w=portrait?720:1280,h=portrait?1280:720;
    const scale=Math.min(innerWidth/w,innerHeight/h);
    Object.assign(root.style,{width:w+'px',height:h+'px',left:(innerWidth-w*scale)/2+'px',top:(innerHeight-h*scale)/2+'px',transform:`scale(${scale})`});
  }
  function render(){
    if(pressed)return;
    const focusId=document.activeElement?.dataset.accountId;
    const style=state.style||{};
    for(const [key,fallback] of [['image_brightness',112],['image_saturation',85],['image_fade',12]])root.style.setProperty('--'+key.replaceAll('_','-'),(style[key]??fallback)/100);
    root.innerHTML=window.TurzxClaude.overview(state.claude,offline,style.claude_background||'thought');
    const all=state.claude.accounts||[], visible=all.slice(0,5),active=window.TurzxClaude.activeAccount(state.claude);
    if(all.length>5&&active&&!visible.includes(active))visible[4]=active;
    root.querySelectorAll('.account-card').forEach((card,i)=>{
      const account=visible[i], button=document.createElement('button');
      button.className='account-hit';button.type='button';button.dataset.accountId=account.id;
      button.setAttribute('aria-label',`切换到${card.querySelector('h2').textContent}`);
      button.setAttribute('aria-pressed',String(account.id===state.claude.active_account_id));
      button.disabled=busy||state.busy||offline||!!state.claude.stale||!token;
      if(account.id===pending)card.classList.add('switch-pending');
      card.append(button);
      if(account.id===focusId)button.focus({preventScroll:true});
    });
    root.setAttribute('aria-busy',String(busy||!!state.busy));
    if(!busy&&Date.now()>messageUntil)message(offline?'连接中断，正在重连…':state.claude.stale?'账号服务数据已过期，暂时不能切换':hint,offline||!!state.claude.stale);
  }
  async function poll(){
    if(polling||busy)return;polling=true;
    try{
      if(!token){const r=await fetch('/api/session',{signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error();token=(await r.json()).token;}
      const r=await fetch('/api/app-state',{cache:'no-store',signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error();
      const next=await r.json();if(!busy){state=next;offline=false;render();}
    }catch{if(!busy){offline=true;render();}}finally{polling=false;}
  }
  root.addEventListener('pointerdown',()=>{pressed=true;});
  window.addEventListener('pointerup',()=>{pressed=false;});
  window.addEventListener('pointercancel',()=>{pressed=false;render();});
  root.addEventListener('click',async event=>{
    const button=event.target.closest('.account-hit');
    if(!button||button.disabled||busy)return;
    pending=button.dataset.accountId;busy=true;render();message('正在切换账号…');
    try{
      const r=await fetch('/api/switch',{method:'POST',headers:{'Content-Type':'application/json','X-App-Token':token},body:JSON.stringify({account_id:pending}),signal:AbortSignal.timeout(50000)});
      const result=await r.json();if(!r.ok)throw Error(result.error||'切换失败。');
      state=result.state;offline=false;message('已切换到'+(state.claude.accounts.find(a=>a.id===result.account_id)?.label||'所选账号'));
    }catch(error){message(error.name==='TimeoutError'?'切换结果尚未确认，请等待当前账号更新。':error.message||'连接中断，请等待当前账号更新。',true);}
    finally{messageUntil=Date.now()+6000;busy=false;pending=null;render();}
  });
  window.addEventListener('resize',fit);window.addEventListener('focus',poll);
  fit();render();poll();setInterval(poll,2000);
})();
