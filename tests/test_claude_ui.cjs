const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const fixed=Date.now();class FixedDate extends Date{static now(){return fixed;}}
const sandbox={window:{},Intl,Date:FixedDate};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/claude.js'),'utf8'),sandbox);
const {single,overview,used,remaining,reset,activeAccount}=sandbox.window.TurzxClaude;
const now=fixed/1000;
const account=(id,utilization)=>({id,label:`账号 ${id}`,email:`a•••${id}@example.com`,subscription_type:'Max',updated_at:now,status:'live',slot:{start:'07:00',end:'12:00'},usage:{five_hour:{utilization,resets_at:now+3600},seven_day:{utilization:43,resets_at:now+86400},seven_day_fable:{utilization:12.5,resets_at:now+90000}}});
const data={accounts:[account('a',99),account('b',30),account('c',0)],active_account_id:'b',status:'live'};
assert.equal(activeAccount(data).id,'b');
assert.equal(used({utilization:0}),0);assert.equal(used({utilization:100}),100);
assert.equal(remaining({utilization:30}),70);
for(const value of [null,undefined,'99',NaN,Infinity,-1,101])assert.equal(used({utilization:value}),null);
assert.equal(reset({resets_at:now+3660}),'1小时1分后重置');
assert.equal(reset({resets_at:now+90000}),'1天1小时后重置');
assert.equal(reset({resets_at:new Date(fixed+60000).toISOString()}),'1分后重置');
for(const resets_at of [null,undefined,'bad',now,now-3600])assert.equal(reset({resets_at}),'');
assert.match(single(data),/30<small>%/);assert.doesNotMatch(single(data),/70<small>%/);
assert.doesNotMatch(single(data),/账号 a/);
assert.equal((overview(data).match(/<article/g)||[]).length,3);
assert.equal((overview(data).match(/active-account-badge/g)||[]).length,1);
assert.equal((overview(data).match(/class="claude-value"/g)||[]).length,9);
assert.equal((overview(data).match(/Fable · 7d/g)||[]).length,6); // heading + meter label
assert.match(overview(data),/aria-valuenow="99"/);
assert.match(overview(data),/width:99%/);
assert.match(overview(data),/0<small>%/);
assert.match(overview(data),/12.5<small>%/);
assert.match(overview(data),/account-wallpaper/);
const stale=structuredClone(data);stale.stale=true;stale.accounts[0].stale=true;stale.accounts[0].error='额度待刷新。';stale.error='数据待刷新';
const forbidden=/上次读取|充值时间|计划时段|北京|数据待刷新|额度待刷新|剩余|重置时间未提供/;
for(const render of [single,overview]){
 for(const state of [data,stale])assert.doesNotMatch(render(state,true),forbidden);
 assert.match(render(stale),/1小时后重置/);
 assert.doesNotMatch(render(stale).replace(/<[^>]*>/g,''),/cswap/i);
}
const missing=structuredClone(data);missing.accounts[1].usage.five_hour={utilization:null};missing.accounts[1].usage.seven_day_fable={};
assert.match(single(missing),/aria-label="额度未知"/);
assert.match(single(missing),/<div class="claude-reset"><strong><\/strong><\/div>/);
assert.match(single(missing),/Fable · 7d/);
assert.doesNotMatch(single(missing),/undefined|NaN|时间未知|未提供/);
const expired=structuredClone(data);expired.accounts[1].usage.five_hour.resets_at=now-60;
assert.match(single(expired),/<div class="claude-reset"><strong><\/strong><\/div>/);
assert.doesNotMatch(single(expired),/等待额度更新|负/);
const malicious=structuredClone(data);malicious.accounts[1].label='<img src=x onerror=alert(1)>';malicious.error='<script>bad</script>';
assert.match(single(malicious),/&lt;img/);assert.doesNotMatch(overview(malicious),/<img src=x/);assert.doesNotMatch(single(malicious),/<script>/);
assert.match(single({}),/等待连接当前账号/);
assert.equal((overview({}).match(/<article/g)||[]).length,0);assert.doesNotMatch(overview({}),/active-account-badge/);
const modelData=structuredClone(data);for(const name of ['sonnet','opus','haiku'])modelData.accounts[1].usage['seven_day_'+name]={utilization:12.5};
for(const name of ['Sonnet','Opus','Haiku'])assert.match(single(modelData),new RegExp(name+' 周额度已使用'));
console.log('Claude used-quota semantics passed: 5h, 7d, Fable, one-line reset, missing/expired time, stale styling and escaping.');

for(let n=0;n<=5;n++){
 const result=overview({accounts:Array.from({length:n},(_,i)=>account(String(i),i*20)),active_account_id:'0'});
 assert.equal((result.match(/<article/g)||[]).length,n);
 assert.equal((result.match(/class="claude-value"/g)||[]).length,n*3);
 assert.match(result,new RegExp('data-count="'+n+'"'));
}
const many=overview({accounts:Array.from({length:7},(_,i)=>account(String(i),20)),active_account_id:'6'});
assert.equal((many.match(/<article/g)||[]).length,5);assert.match(many,/账号 6/);

for(const render of [single,overview]){
 for(const [value,file] of [['stand','claude-v3-decorated-stand'],['thought','claude-v3-decorated-thought'],['greeting','claude-v3-decorated-greeting'],...['floral','celestial','atelier','botanical','paperland','glasswave'].map(key=>[key,'claude-v4-'+key])]){const html=render(data,false,value);assert.ok(html.includes(file+'-landscape.png'));assert.ok(html.includes(file+'-portrait.png'));assert.match(html,/max-aspect-ratio: 1\/1/);}
 assert.doesNotMatch(render(data,false,'none'),/account-wallpaper/);
 assert.match(render(data,false,'__proto__'),/claude-v3-decorated-stand-landscape.png/);
}
