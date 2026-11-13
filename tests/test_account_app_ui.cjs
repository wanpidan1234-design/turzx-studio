const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require('playwright');
const base=process.env.ACCOUNT_APP_URL||'http://127.0.0.1:8766';
(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true});
  try{
    const page=await browser.newPage();
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    let state={style:{claude_background:'thought',image_brightness:112,image_saturation:85,image_fade:12},busy:false,claude:{status:'ok',stale:false,active_account_id:'2',accounts:Array.from({length:3},(_,i)=>({id:String(i+1),label:['jackey2','jackey','账号 3'][i],status:'ok',updated_at:Date.now()/1000,subscription_type:'Max',usage:{five_hour:{utilization:20+i*10,resets_at:Date.now()/1000+7200},seven_day:{utilization:44,resets_at:Date.now()/1000+86400},seven_day_fable:{utilization:12,resets_at:Date.now()/1000+90000}}}))}};
    await page.route('**/api/session',r=>r.fulfill({json:{token:'test'}}));
    await page.route('**/api/app-state',r=>r.fulfill({json:state}));
    let requests=0,release;
    await page.route('**/api/switch',async r=>{requests++;assert.equal(r.request().headers()['x-app-token'],'test');const id=r.request().postDataJSON().account_id;await new Promise(resolve=>release=resolve);state.claude.active_account_id=id;await r.fulfill({json:{ok:true,account_id:id,state}});});
    fs.mkdirSync('runtime/account-app-validation',{recursive:true});
    for(const [w,h] of [[1280,720],[720,1280],[390,844]]){
      await page.setViewportSize({width:w,height:h});await page.goto(base);await page.waitForFunction(()=>document.querySelectorAll('.account-hit:not(:disabled)').length===3);await page.evaluate(()=>document.fonts.ready);
      await page.locator('.account-wallpaper img').evaluate(img=>img.decode());
      for(const card of await page.locator('.account-card').all()){
        const box=await card.boundingBox();assert(box.x>=0&&box.y>=0&&box.x+box.width<=w+1&&box.y+box.height<=h+1,JSON.stringify(box));
        assert(box.width>=44&&box.height>=44);
      }
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight),false);
      await page.screenshot({path:`runtime/account-app-validation/${w}x${h}.png`});
    }
    await page.getByRole('button',{name:'切换到账号 3',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#feedback').textContent==='正在切换账号…');
    assert.equal(await page.locator('.account-hit:disabled').count(),3);
    assert.equal(requests,1);release();
    await page.waitForFunction(()=>document.querySelector('[data-account-id="3"]').getAttribute('aria-pressed')==='true');
    await page.locator('[data-account-id="1"]').focus();
    await page.waitForTimeout(2200);
    assert.equal(await page.evaluate(()=>document.activeElement.dataset.accountId),'1');
    await page.route('**/api/switch',r=>r.fulfill({status:409,json:{error:'账号登录已失效，请重新登录。'}}));
    await page.keyboard.press('Enter');await page.waitForFunction(()=>document.querySelector('#feedback').dataset.error==='true');
    assert.equal(await page.locator('[data-account-id="3"]').getAttribute('aria-pressed'),'true');
    state.claude.stale=true;
    await page.waitForFunction(()=>document.querySelectorAll('.account-hit:disabled').length===3);
    assert.deepEqual(errors,[]);
    console.log('Passed: 3 sizes, 3 accounts, successful switch, busy lock, keyboard/focus, failed switch and stale data.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
