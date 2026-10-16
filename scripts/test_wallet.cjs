/* Browser acceptance checks. Requires Playwright in NODE_PATH and installed Chrome.
   Start: python -m http.server 8764 --bind 127.0.0.1
   Run: node scripts/test_wallet.cjs http://127.0.0.1:8764
   Test fixtures are intercepted in the browser only; offers.json is never changed. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.argv[2] || 'http://127.0.0.1:8764';
const out = path.resolve(__dirname, '../docs/design/after');
const data = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../offers.json'), 'utf8'));
const results = [];
const errors = [];
const screenshots = [];
const check = (name, condition) => { assert.ok(condition, name); results.push(name); };
(async () => {
 fs.mkdirSync(out, { recursive: true });
 const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'msedge', args: ['--disable-gpu', '--disable-dev-shm-usage'], timeout: 30000 });
 try {
 for (const [name, width, height] of [['mobile',390,844], ['desktop',1280,900], ['narrow',320,700]]) {
  const context = await browser.newContext({ viewport: {width,height}, timezoneId:'America/Los_Angeles', reducedMotion:'reduce' });
  await context.addInitScript(() => localStorage.setItem('oroodi_signup_shown','1'));
  const page = await context.newPage();
  page.on('pageerror', e => errors.push(name + ': ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(name + ': ' + m.text()); });
  // External font access can be offline. Keep actual local page/data requests real.
  await page.route(/fonts\.(googleapis|gstatic)\.com/, r => r.fulfill({status:200,contentType:'text/css',body:''}));
  await page.goto(base + '/index.html#home', {waitUntil:'load'});
  await page.waitForFunction(() => document.querySelectorAll('.wallet-offer').length > 0);
  await page.locator('.toast').waitFor({state:'detached'});
  const live = data.offers.filter(o => Date.parse(o.expiryDate+'T23:59:59+03:00') >= Date.now());
  check(name+': real provider generation', await page.locator('.wcard').count() === new Set(live.map(o=>o.providerName)).size);
  check(name+': real offer count', await page.locator('.wallet-offer').count() === live.length);
  check(name+': no horizontal page overflow', await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
  check(name+': home hides advanced filters', !(await page.locator('#filter-bar').isVisible()));
  check(name+': reduced motion', await page.locator('.wallet-offer').first().evaluate(e=>getComputedStyle(e).animationName === 'none'));
  for (const language of ['ar','en']) {
   if (language === 'en') await page.locator('#languageBtn').click();
   check(name+': '+language+' direction', await page.locator('html').getAttribute('dir') === (language==='ar'?'rtl':'ltr'));
   const offerButton = page.locator('.wallet-offer').first();
   const id = await offerButton.getAttribute('data-offer-id');
   const offer = live.find(o=>o.id===id);
   if(name !== 'narrow') {
    const file=path.join(out,name+'-home-'+language+'.png');
    await page.screenshot({path:file,fullPage:false,timeout:15000,animations:'disabled'}); screenshots.push(path.relative(path.resolve(__dirname,'..'),file).split(path.sep).join('/'));
   }
   await offerButton.click();
   const dialog = page.locator('#receiptDialog');
   await dialog.waitFor({state:'visible'});
   check(name+': '+language+' exact terms', await dialog.locator('.rc-terms').textContent() === offer.terms);
   check(name+': '+language+' official source', await dialog.locator('.rc-use').getAttribute('href') === offer.sourceUrl);
   check(name+': '+language+' value', await dialog.locator('.rc-disc').textContent() === offer.value);
   check(name+': '+language+' code/null', (await dialog.textContent()).includes(offer.promoCode || (language==='ar'?'مفيش كود مذكور':'No code specified')));
   check(name+': '+language+' modal focus', await dialog.evaluate(d=>d.contains(document.activeElement)));
   check(name+': '+language+' no dialog overflow', await dialog.evaluate(d=>d.scrollWidth <= d.clientWidth));
   if(name !== 'narrow') {
    const file=path.join(out,name+'-receipt-'+language+'.png');
    await page.screenshot({path:file,timeout:15000,animations:'disabled'}); screenshots.push(path.relative(path.resolve(__dirname,'..'),file).split(path.sep).join('/'));
   }
   // Web Share and clipboard are tested via controlled browser APIs, never send a real message.
   await page.evaluate(()=>{ Object.defineProperty(navigator,'share',{configurable:true,value:async d=>{window.sharedReceipt=d;}}); });
   await dialog.locator('.rc-share').click();
   check(name+': '+language+' share payload', await page.evaluate(src=>window.sharedReceipt.text.includes(src),offer.sourceUrl));
   await page.keyboard.press('Escape');
   await dialog.waitFor({state:'detached'});
   check(name+': '+language+' focus restored', await offerButton.evaluate(b=>document.activeElement===b));
  }
  await page.locator('#walletClearBtn').click();
  const cards=await page.locator('.wcard').count();
  for(let i=0;i<cards;i++) await page.locator('.wcard').nth(i).click();
  check(name+': empty selection is empty', await page.locator('.wallet-offer').count()===0);
  check(name+': empty saved locally', await page.evaluate(()=>localStorage.getItem('oroodi_cards_v2'))==='[]');
  await page.reload({waitUntil:'load'});
  check(name+': empty persists after reload', await page.locator('.wallet-offer').count()===0);
  await page.locator('#walletClearBtn').click();
  const one=await page.locator('.wcard').first().getAttribute('data-provider');
  for(let i=1;i<cards;i++) await page.locator('.wcard').nth(i).click();
  check(name+': provider-only filtering', await page.locator('.wallet-offer').count()===live.filter(o=>o.providerName===one).length);
  await page.reload({waitUntil:'load'});
  check(name+': provider selection persists', await page.locator('.wcard[aria-pressed=true]').count()===1);
  await page.evaluate(()=>localStorage.setItem('oroodi_cards_v2','{}'));
  await page.reload({waitUntil:'load'});
  check(name+': malformed storage recovers', await page.locator('.wallet-offer').count()>0);
  // Existing hash navigation remains supported.
  for(const route of ['offers','cards','wallets','saved','home']) {
   await page.evaluate(route=>{location.hash=route;},route);
   await page.waitForFunction(route=>document.querySelector('#page-'+route)?.classList.contains('active'),route);
   check(name+': route '+route, await page.locator('#page-'+route).isVisible());
  }
  // Review regressions: every browse route opens the same receipt by keyboard.
  await page.evaluate(() => {
    const wallet = {...OFFERS_DATA[0], id:'test-wallet', providerType:'wallet', providerName:'Test wallet'};
    OFFERS_DATA.push(wallet);
    savedIds = OFFERS_DATA.map(o=>o.id);
    resetMemo(); renderAll(false);
  });
  for (const lang of ['en','ar']) {
   if (await page.locator('html').getAttribute('lang') !== lang) await page.locator('#languageBtn').click();
   for (const route of ['offers','cards','wallets','saved']) {
    await page.evaluate(route=>{location.hash=route;},route);
    await page.waitForFunction(route=>document.querySelector('#page-'+route).classList.contains('active'),route);
    const section=page.locator('#page-'+route);
    check(name+': '+lang+' '+route+' heading', (await section.locator('h1').textContent()).trim() === ({en:{offers:'Offers',cards:'Bank cards',wallets:'Wallets and installments',saved:'Saved offers'},ar:{offers:'العروض',cards:'البطاقات البنكية',wallets:'المحافظ والتقسيط',saved:'المحفوظات'}})[lang][route]);
    const details=section.locator('[data-action=details]').first();
    await details.focus(); await page.keyboard.press('Enter');
    await page.locator('#receiptDialog').waitFor({state:'visible'});
    check(name+': '+lang+' '+route+' keyboard receipt', await page.locator('#receiptDialog .rc-terms').count()===1);
    await page.keyboard.press('Escape');
    check(name+': '+lang+' '+route+' restores focus', await details.evaluate(e=>e===document.activeElement));
    check(name+': '+lang+' '+route+' source preserved', (await section.locator('.source-btn').first().getAttribute('href')).startsWith('https://'));
    check(name+': '+lang+' '+route+' save translated', /Save|Saved/.test(await section.locator('.save-btn').first().textContent()) === (lang==='en'));
   }
   check(name+': '+lang+' filter translation', await page.locator('#clearFiltersBtn').textContent() === (lang==='en'?'Clear filters':'تصفير'));
   check(name+': '+lang+' type translation', await page.locator('#offerTypeFilter option[value=discount]').textContent() === (lang==='en'?'Discount':'خصم'));
  }
  await page.locator('#languageBtn').click(); // English error message.
  const snapshot = await page.evaluate(()=>({data:JSON.stringify(OFFERS_DATA), cache:localStorage.getItem(CACHE_KEY)}));
  for (const [label,payload] of [
    ['malformed',{lastUpdated:'2099-01-01T00:00:00Z',offers:[{bad:true}]}],
    ['mixed',{lastUpdated:'2099-01-01T00:00:00Z',offers:[live[0],{bad:true}]}],
    ['missing list',{lastUpdated:'2099-01-01T00:00:00Z'}],
    ['invalid timestamp',{lastUpdated:'bad',offers:[]}],
    ['duplicate IDs',{lastUpdated:'2099-01-01T00:00:00Z',offers:[live[0],live[0]]}]
  ]) {
   await page.route('**/offers.json',r=>r.fulfill({json:payload}));
   check(name+': '+label+' rejects update', await page.evaluate(()=>fetchAndUpdate(true))===false);
   check(name+': '+label+' preserves data', await page.evaluate(()=>JSON.stringify(OFFERS_DATA))===snapshot.data);
   check(name+': '+label+' preserves cache', await page.evaluate(()=>localStorage.getItem(CACHE_KEY))===snapshot.cache);
   check(name+': '+label+' visible failure', (await page.locator('.toast').textContent()).includes('Could not update'));
   await page.unroute('**/offers.json');
  }
  await page.route('**/offers.json',r=>r.fulfill({json:{lastUpdated:'2099-01-01T00:00:00Z',offers:[]}}));
  check(name+': valid empty response accepted', await page.evaluate(()=>fetchAndUpdate(true))===true);
  check(name+': valid empty response clears offers', await page.evaluate(()=>OFFERS_DATA.length)===0);
  check(name+': valid empty response cached', await page.evaluate(()=>JSON.parse(localStorage.getItem(CACHE_KEY)).offers.length)===0);
  await page.reload({waitUntil:'load'});
  await page.waitForFunction(()=>OFFERS_DATA.length===0);
  check(name+': valid empty reload stays empty', await page.locator('.wallet-offer').count()===0);
  await page.unroute('**/offers.json');
  // Boundary measured in Riyadh even though browser timezone is Los Angeles.
  await page.clock.install({time:new Date('2026-10-16T20:59:59Z')});
  check(name+': expiry day inclusive in Riyadh', await page.evaluate(()=>getDaysLeft('2026-10-16'))===0);
  await page.clock.setFixedTime(new Date('2026-10-16T21:00:00Z'));
  check(name+': expired at Riyadh midnight', await page.evaluate(()=>getDaysLeft('2026-10-16'))===-1);
  check(name+': javascript URLs rejected', await page.evaluate(o=>sanitizeOffers([{...o,sourceUrl:'javascript:alert(1)'}]).length,live[0])===0);
  await context.close();
 }
 check('No console or JavaScript errors in tested routes', errors.length===0);
 const result={checkedAt:new Date().toISOString(),passed:results.length,failed:0,checks:results,errors,screenshots,fontMode:'external fonts replaced with empty CSS; system fallback tested'};
 fs.writeFileSync(path.join(out,'acceptance.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify(result,null,2));
 } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
