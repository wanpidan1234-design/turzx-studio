const {chromium}=require('playwright');const assert=require('node:assert/strict');const fs=require('fs');
(async()=>{
 fs.mkdirSync('runtime/designer-verification',{recursive:true});
 const original=await(await fetch('http://127.0.0.1:8765/api/state')).json();const metrics=await(await fetch('http://127.0.0.1:8765/api/metrics')).json();const info=await(await fetch('http://127.0.0.1:8765/api/info')).json();
 const b=await chromium.launch({channel:'chrome',headless:true});let count=0;const errors=[];
 for(const width of [1440,390]){
 let state={...structuredClone(original),page:'system',claude_background:'stand',connected:true,streaming:false,error:null},offline=false,fail=false,release=null;const requests=[];
 const p=await b.newPage({viewport:{width,height:1000}});p.on('pageerror',e=>errors.push(e.message));
 await p.route('**/api/**',async route=>{const url=new URL(route.request().url());if(url.pathname==='/api/control'){
 const patch=route.request().postDataJSON();requests.push(patch);if(release)await new Promise(r=>release=r);if(fail){await route.fulfill({status:500,json:{error:'测试失败提示'}});return;}
 if(patch.action==='start')state.streaming=true;if(patch.action==='stop')state.streaming=false;
 if(patch.action==='focus_start')state.focus.running=true;if(patch.action==='focus_pause')state.focus.running=false;if(patch.action==='focus_reset')state.focus={duration:1500,remaining:1500,running:false};
 state={...state,...patch,animation:{...state.animation,...patch.animation}};delete state.action;await route.fulfill({json:state});
 }else if(url.pathname==='/api/state'){await route.fulfill({status:offline?503:200,json:offline?{error:'offline'}:state});}else if(url.pathname==='/api/metrics')await route.fulfill({json:metrics});else if(url.pathname==='/api/info')await route.fulfill({json:info});else await route.abort();});
 await p.goto('http://127.0.0.1:8765/');await p.waitForSelector('#connection.online');
 const tab=async name=>{if(width<768)await p.locator(`[data-tab="${name}"]`).click();};
 const last=async expected=>{await p.waitForTimeout(100);assert.deepEqual(requests.at(-1),expected);count++;};
 for(const scene of ['system','network','clock','focus','ambient','openai','claude','cswap','media','guide','calibrate']){await p.locator(`[data-page="${scene}"]`).click();await last({page:scene});assert.equal(await p.locator(`[data-page="${scene}"]`).getAttribute('aria-current'),'true');}
 await tab('display');await p.selectOption('#rotation','0');await last({rotation:0});await p.waitForFunction(()=>document.querySelector('#preview-box').classList.contains('portrait'));const ratio=await p.locator('#preview-box').evaluate(e=>e.clientWidth/e.clientHeight);assert.ok(Math.abs(ratio-720/1280)<.01);
 await p.selectOption('#rotation','270');await last({rotation:270});await p.selectOption('#fps','5');await last({fps:5});await p.check('#auto');await last({auto:true});await p.selectOption('#interval','60');await last({interval:60});
 for(const [id,value,key] of [['brightness','80','brightness']]){await p.locator('#'+id).evaluate((e,v)=>{e.value=v;e.dispatchEvent(new Event('input'));e.dispatchEvent(new Event('change'));},value);await last({[key]:Number(value)});}
 await p.selectOption('#panel-color-order','rgb');await last({panel_color_order:'rgb'});
 await p.locator('[data-page="ambient"]').click();await last({page:'ambient'});await tab('scene');await p.selectOption('#animation-preset','aurora');await last({animation:{preset:'aurora'}});await p.selectOption('#animation-detail','light');await last({animation:{detail:'light'}});await p.uncheck('#animation-clock');await last({animation:{show_clock:false}});await p.click('#animation-pause');await last({animation:{paused:true}});await p.locator('#animation-speed').evaluate(e=>{e.value='1.5';e.dispatchEvent(new Event('change'));});await last({animation:{speed:1.5}});await p.click('#animation-seed');assert.ok(Number.isInteger(requests.at(-1).animation.seed));
 await p.screenshot({path:`runtime/designer-verification/console-animation-${width}.png`,fullPage:true});
 await p.locator('[data-page="openai"]').click();await last({page:'openai'});await tab('display');await p.selectOption('#subscription-background','dragon');await last({subscription_background:'dragon'});await tab('scene');await p.selectOption('#subscription-view','billing');await last({subscription_view:'billing',subscription_auto:false});await p.check('#subscription-auto');await last({subscription_auto:true});await tab('display');await p.locator('#subscription-transparency').evaluate(e=>{e.value='40';e.dispatchEvent(new Event('change'));});await last({subscription_background_transparency:40});await tab('scene');await p.click('#subscription-refresh');await last({action:'subscription_refresh'});
 await p.screenshot({path:`runtime/designer-verification/console-openai-${width}.png`,fullPage:true});
 await p.locator('[data-page="cswap"]').click();await last({page:'cswap'});await p.click('#claude-refresh');await last({action:'claude_refresh'});await p.screenshot({path:`runtime/designer-verification/console-claude-${width}.png`,fullPage:true});
 await tab('display');
 for(const value of ['thought','greeting','floral','celestial','atelier','botanical','paperland','glasswave','none','stand']){await p.locator('input[name="claude-background"][value="'+value+'"]').check();await last({claude_background:value});assert.equal(await p.locator('input[name="claude-background"]:checked').inputValue(),value);}
 await p.reload();await p.waitForSelector('#connection.online');assert.equal(await p.locator('input[name="claude-background"]:checked').inputValue(),'stand');
 for(const [id,value,key] of [['image-brightness','120','image_brightness'],['image-saturation','80','image_saturation'],['image-fade','18','image_fade']]){await p.locator('#'+id).evaluate((e,v)=>{e.value=v;e.dispatchEvent(new Event('input'));e.dispatchEvent(new Event('change'));},value);await last({[key]:Number(value)});assert.equal(await p.locator('#'+id+'-value').textContent(),value+'%');}
 await p.click('#image-original');await last({image_brightness:100,image_saturation:100,image_fade:0});
 await p.reload();await p.waitForSelector('#connection.online');assert.equal(await p.inputValue('#image-fade'),'0');assert.equal(await p.inputValue('#image-brightness'),'100');
 await p.click('#image-pale');await last({image_brightness:112,image_saturation:85,image_fade:12});
 await p.screenshot({path:`runtime/designer-verification/console-image-controls-${width}.png`,fullPage:true});
 await tab('focus');await p.click('#focus-start');await last({action:'focus_start'});await p.click('#focus-start');await last({action:'focus_pause'});await p.click('#focus-reset');await last({action:'focus_reset'});
 await p.fill('#note','测试草稿');await p.locator('#note').blur();await p.waitForTimeout(1400);assert.equal(await p.inputValue('#note'),'测试草稿');await p.click('#save-note');await last({note:'测试草稿'});assert.equal(await p.textContent('#note-state'),'已保存');
 fail=true;await p.fill('#note','保存失败保留草稿');await p.click('#save-note');await p.waitForFunction(()=>document.querySelector('#note-state').textContent==='保存失败');assert.equal(await p.inputValue('#note'),'保存失败保留草稿');fail=false;
 await tab('device');if(width>=768)await p.click('#device-section-toggle');await p.waitForSelector('#device-facts .fact');assert.ok(await p.locator('#device-facts .source-links a').count());await p.screenshot({path:`runtime/designer-verification/console-device-${width}.png`,fullPage:true});await p.click('#info-close');assert.equal(await p.locator('#device-details').isVisible(),false);
 release=true;const click=p.click('#start-button');await p.waitForFunction(()=>document.body.classList.contains('busy'));assert.equal(await p.locator('#start-button').isDisabled(),true);assert.equal(await p.locator('#stop-button').isDisabled(),true);while(typeof release!=='function')await p.waitForTimeout(20);release();release=null;await click;await p.waitForFunction(()=>!document.body.classList.contains('busy'));await last({action:'start'});await p.click('#stop-button');await last({action:'stop'});
 offline=true;await p.waitForSelector('#service-banner:not([hidden])');assert.equal(await p.locator('#start-button').isDisabled(),true);await p.screenshot({path:`runtime/designer-verification/console-disconnected-${width}.png`,fullPage:true});offline=false;await p.click('#service-retry');await p.waitForSelector('#connection.online');assert.equal(await p.locator('#service-banner').isVisible(),false);
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 if(width<768){await tab('display');await p.locator('[data-tab="display"]').focus();await p.keyboard.press('ArrowRight');assert.equal(await p.locator('[data-tab="scene"]').getAttribute('aria-selected'),'true');assert.equal(state.page,'cswap');}
 await p.close();
 }
 assert.deepEqual(errors,[]);await b.close();fs.writeFileSync('runtime/designer-verification/console-report.json',JSON.stringify({assertedPayloads:count,pageErrors:errors,widths:[1440,390]},null,2));console.log('Console passed:',count,'payload checks; dirty note, save failure, busy, reconnect, tabs, device links and portrait preview.');
})().catch(e=>{console.error(e);process.exit(1)});
