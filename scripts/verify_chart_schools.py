"""Real-service browser regression for the three chart views and annual API."""
import asyncio
import json

from playwright.async_api import async_playwright, expect


async def check_fit(page):
    await page.wait_for_timeout(120)
    result=await page.evaluate('''()=>{
      const board=document.querySelector('#natalBoard'),clipped=[];
      for(const cell of board.querySelectorAll('.palaceCell')){
        const deck=cell.querySelector('.starDeck'),rect=deck.getBoundingClientRect();
        for(const star of deck.children){const r=star.getBoundingClientRect();if(r.bottom>rect.bottom+1||r.right>rect.right+1)clipped.push({branch:cell.dataset.branch,star:star.dataset.starName})}
      }
      const c=board.querySelector('.compactCenter').getBoundingClientRect(),r=board.querySelector('.centerContent').getBoundingClientRect();
      return {clipped,centerFits:r.left>=c.left-1&&r.right<=c.right+1&&r.top>=c.top-1&&r.bottom<=c.bottom+1,overflow:document.documentElement.scrollWidth>innerWidth};
    }''')
    assert not result['clipped'],result
    assert result['centerFits'] and not result['overflow'],result


async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto('http://127.0.0.1',wait_until='networkidle')
        await page.locator('#locationTrigger').click()
        await page.locator('#locationGroups [data-location-id="CN:110000"]').click()
        await page.locator('#locationDistricts [data-location-id="CN:110101"]').click()
        await page.locator('#birthName').fill('三种排盘对拍')
        for field,value in [('year','2000'),('month','8'),('day','16'),('hour','12')]:
            await page.locator('#'+field).select_option(value)
        async with page.expect_response(lambda r:'/api/charts/resolve' in r.url and r.request.method=='POST') as pending:
            await page.locator('#loadChart').click()
        response=await pending.value
        assert response.ok,await response.text()
        chart=await response.json()
        transforms=chart['natal_chart']['transformations']
        await expect(page.locator('.palaceCell')).to_have_count(12)
        await expect(page.locator('#natalBoard')).to_have_attribute('data-mode','sanhe')
        base_star_count=await page.locator('.starColumn').count()
        assert base_star_count>18
        await page.locator('.palaceCell[data-branch="0"]').click()
        await expect(page.locator('.palaceConnections line')).to_have_count(4)
        await check_fit(page)

        await page.locator('[data-chart-school=feixing]').click()
        await expect(page.locator('#natalBoard')).to_have_attribute('data-mode','feixing')
        await expect(page.locator('.starColumn')).to_have_count(18)
        await expect(page.locator('.flightPath')).to_have_count(4)
        for branch in range(12):
            await page.locator('#natalBoard').press('Escape')
            await page.locator(f'.palaceCell[data-branch="{branch}"]').click()
            await expect(page.locator('.flightPath')).to_have_count(4)
            edges=await page.locator('.flightPath').evaluate_all('(nodes)=>nodes.map(n=>({source:+n.dataset.sourceBranch,target:+n.dataset.targetBranch,kind:n.dataset.siHua}))')
            expected=[{'source':e['sourceBranch'],'target':e['targetBranch'],'kind':e['siHua']} for e in transforms['flyingStars'] if e['sourceBranch']==branch]
            assert edges==expected,(edges,expected)
            await expect(page.locator('.centerFlightRow')).to_have_count(4)
        # Our specimen has a known self-transform in 巳宫.
        await page.locator('#natalBoard').press('Escape')
        await page.locator('.palaceCell[data-branch="5"]').click()
        assert await page.locator('.flightPath[data-source-branch="5"][data-target-branch="5"]').count()>0

        await page.locator('[data-chart-school=sihua]').click()
        await expect(page.locator('.centerFlightRow')).to_have_count(4)
        await expect(page.locator('.selfSihuaBadge')).to_have_count(sum(len(v) for v in transforms['selfSihua'].values()))
        target=transforms['natal']['placements'][0]['targetBranch']
        await page.locator(f'.palaceCell[data-branch="{target}"]').click()
        incoming=[e for e in transforms['flyingStars'] if e['targetBranch']==target and any(
            x['starName']==e['starName'] and x['siHua']==e['siHua'] for x in transforms['natal']['placements'])]
        await expect(page.locator('.flightPath')).to_have_count(len(incoming))

        await page.locator('#siHuaLayer').select_option('annual')
        async with page.expect_response(lambda r:'/transformations?year=2027' in r.url) as pending:
            await page.locator('#siHuaYear').fill('2027')
            await page.locator('#siHuaYear').press('Tab')
        response=await pending.value
        assert response.ok,await response.text()
        annual=await response.json()
        assert annual['annual']['stemName']=='丁'
        await expect(page.locator('.centerReadingTitle')).to_have_text('2027 流年四化 · 丁干')
        await expect(page.locator('.contextSiHua')).to_have_count(4)
        await page.reload(wait_until='networkidle')
        await expect(page.locator('#natalBoard')).to_have_attribute('data-mode','sihua')
        await expect(page.locator('#siHuaLayer')).to_have_value('annual')
        await expect(page.locator('#siHuaYear')).to_have_value('2027')
        await expect(page.locator('.centerReadingTitle')).to_have_text('2027 流年四化 · 丁干')

        await page.locator('#siHuaLayer').select_option('daxian')
        await page.locator('#siHuaDaXian').select_option('0')
        await expect(page.locator('.contextSiHua')).to_have_count(4)
        for width,height in ((1440,1000),(1366,768),(390,844)):
            await page.set_viewport_size({'width':width,'height':height})
            for mode in ('sanhe','feixing','sihua'):
                await page.locator(f'[data-chart-school={mode}]').click()
                await check_fit(page)
                await page.locator('#natalPanel').screenshot(path=f'/tmp/ziwei-{mode}-{width}.png')
        # A young child must not silently use the first actual decade.
        await page.evaluate('''async()=>{const chart=await api('/api/charts/resolve','POST',{year:2026,month:1,day:1,hour:0,gender:'female',name:'童限验证'});showChart(chart)}''')
        await expect(page.locator('#siHuaDaXian')).to_have_value('-1')
        await expect(page.locator('.contextSiHua')).to_have_count(0)
        await expect(page.locator('.centerReadingEmpty')).to_contain_text('尚未进入大限')
        assert not errors,errors
        await browser.close()
        print(json.dumps({'status':'PASS','upstream_flights_checked':48,'viewport_count':3,'modes':3,
            'annual_year':2027,'restoration':True,'child_decade':True,'javascript_errors':errors},ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(main())
