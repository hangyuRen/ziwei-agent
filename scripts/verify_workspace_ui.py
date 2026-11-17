import asyncio,json,gzip
from playwright.async_api import async_playwright

async def check_chart(page,desktop=True):
 await page.wait_for_timeout(180)
 assert await page.locator('.palaceCell').count()==12
 result=await page.evaluate('''()=>{
 const board=document.querySelector('#natalBoard'),r=board.getBoundingClientRect();
 const clipped=[];
 for(const cell of board.querySelectorAll('.palaceCell')){const d=cell.querySelector('.starDeck'),dr=d.getBoundingClientRect();for(const s of d.children){const sr=s.getBoundingClientRect();if(sr.bottom>dr.bottom+1||sr.right>dr.right+1)clipped.push({branch:cell.dataset.branch,name:s.title,font:cell.style.getPropertyValue('--star-font'),bottom:sr.bottom,limit:dr.bottom})}}
 const center=board.querySelector('.compactCenter').getBoundingClientRect(),inner=board.querySelector('.centerContent').getBoundingClientRect();
 return {left:document.querySelector('#natalPanel').getBoundingClientRect().toJSON(),board:r.toJSON(),clipped,centerFits:inner.top>=center.top-1&&inner.bottom<=center.bottom+1&&inner.left>=center.left-1&&inner.right<=center.right+1,fonts:[...board.querySelectorAll('.palaceCell')].map(c=>c.style.getPropertyValue('--star-font')),overflow:document.documentElement.scrollWidth>innerWidth}
 }''')
 assert not result['clipped'],result['clipped']
 assert result['centerFits'],result
 assert not result['overflow'],result
 if desktop:
  w=page.viewport_size['width'];assert abs(result['left']['width']/w-1/3)<.005,result
  assert result['board']['bottom']<=page.viewport_size['height']-30,result
 return result

async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(headless=True,args=['--no-sandbox']);page=await b.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto('http://127.0.0.1',wait_until='networkidle')
  await page.locator('#locationTrigger').click();await page.locator('#locationGroups [data-location-id="CN:110000"]').click();await page.locator('#locationDistricts [data-location-id="CN:110101"]').click();await page.locator('#birthName').fill('命盘预览');await page.locator('#year').select_option('2002');await page.locator('#month').select_option('1');await page.locator('#day').select_option('25');await page.locator('#hour').select_option('8');await page.locator('#loadChart').click();
  try:await page.locator('.palaceCell').first.wait_for(timeout=20000)
  except Exception:
   print('UI_DIAGNOSTIC',await page.evaluate('({notice:document.querySelector("#chartNotice").textContent,location:document.querySelector("#birthLocation").value,name:document.querySelector("#birthName").value,year:document.querySelector("#year").value,month:document.querySelector("#month").value,day:document.querySelector("#day").value})'),errors,flush=True)
   await page.screenshot(path='/tmp/ziwei-compact-failure.png',full_page=True);raise
  initial=await check_chart(page)
  assert await page.locator('.siteHeader #headerModes').count()==0
  assert await page.locator('.rightModeBar #headerModes').count()==1
  tabs=await page.locator('#tabs').bounding_box();mode=await page.locator('.rightModeBar').bounding_box();left=await page.locator('#natalPanel').bounding_box()
  await page.locator('.palaceCell[data-branch="0"]').click()
  assert await page.locator('.palaceConnections line').count()==4
  assert await page.locator('.palaceConnections circle').count()==4
  assert await page.locator('.selectedPalace').count()==1
  assert await page.locator('.relatedPalace').count()==3
  assert await page.evaluate('JSON.stringify(PalaceBoard.relations(0))')=='[0,6,4,8]'
  await check_chart(page)
  await page.screenshot(path='/tmp/ziwei-compact-linked.png',full_page=True)
  await page.locator('.palaceCell[data-branch="0"]').press('Escape')
  assert await page.locator('.palaceConnections line').count()==0
  if await page.locator('.reportDisclosure').count():await page.locator('.reportDisclosure').first.evaluate('(el)=>el.open=true')
  await page.locator('.analysisScroll').evaluate('(el)=>el.scrollTop=600')
  assert await page.locator('#tabs').bounding_box()==tabs
  assert await page.locator('.rightModeBar').bounding_box()==mode
  assert await page.locator('#natalPanel').bounding_box()==left
  await page.screenshot(path='/tmp/ziwei-compact-analysis.png',full_page=True)
  await page.locator('#chatMode').click();assert await page.locator('.sessionSidebar').is_visible()
  assert await page.locator('#toggleConversations').count()==0 and await page.locator('#splitNewChat').count()==0
  sidebar=await page.locator('.sessionSidebar').bounding_box();main=await page.locator('.chatMain').bounding_box();assert sidebar['x']+sidebar['width']<=main['x']+1 and sidebar['width']<=200,(sidebar,main)
  assert await page.locator('#natalPanel').bounding_box()==left
  await page.screenshot(path='/tmp/ziwei-compact-chat.png',full_page=True)
  await page.locator('#analysisMode').click()
  sizes=[]
  for w,h in [(1280,800),(1366,768),(1920,1080),(390,844)]:
   await page.set_viewport_size({'width':w,'height':h});sizes.append(await check_chart(page,w>1100))
  await page.screenshot(path='/tmp/ziwei-compact-mobile.png',full_page=True)
  # Stress the densest palace in the independent upstream fixtures, using live Python output.
  data=json.load(gzip.open('tests/fixtures/upstream-parity.json.gz','rt'))
  samples=[x for x in data['cases'] if 'expected' in x and x['input']['policy']=='split' and x['input']['school']=='QS']
  dense=max(samples,key=lambda x:max(len(p['stars']) for p in x['expected']['palaces']))['input'];dense={k:v for k,v in dense.items() if k not in ('policy','school')};dense['name']='密集星曜核验'
  await page.set_viewport_size({'width':1440,'height':900});await page.evaluate('async input=>{const j=await api("/api/charts/resolve","POST",input);showChart(j)}',dense);await check_chart(page)
  for w,h in [(1280,800),(1366,768),(390,844)]:
   await page.set_viewport_size({'width':w,'height':h});await check_chart(page,w>1100)
  assert not errors,errors
  print(json.dumps({'status':'PASS','initial':initial,'viewport_count':4,'dense_input':dense,'javascript_errors':errors},ensure_ascii=False))
  await b.close()
asyncio.run(main())
