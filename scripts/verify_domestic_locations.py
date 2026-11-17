"""Verify all domestic API branches and real desktop/mobile picker behavior."""
import asyncio
import re

import httpx
from playwright.async_api import async_playwright, expect

BASE = 'http://127.0.0.1'


async def verify_api():
    async with httpx.AsyncClient(base_url=BASE,timeout=30) as client:
        root=await client.get('/api/location-picker')
        root.raise_for_status()
        assert len(root.json()['provinces'])==34
        total_cities=total_districts=0
        ids=set()
        for province in root.json()['provinces']:
            response=await client.get('/api/location-picker',params={'province':province['id']})
            response.raise_for_status()
            cities=response.json()['cities']
            total_cities+=len(cities)
            for city in cities:
                response=await client.get('/api/location-picker',params={'province':province['id'],'city':city['id']})
                response.raise_for_status()
                districts=response.json()['districts']
                assert districts,(province,city)
                total_districts+=len(districts)
                for district in districts:
                    assert district['province_id']==province['id']
                    assert district['city_id']==city['id']
                    assert district['id'] not in ids
                    ids.add(district['id'])
        assert total_cities==365 and total_districts==3246
        assert (await client.get('/api/location-picker?region=overseas')).status_code==422
        print(f'PASS API: 34 provinces, {total_cities} city groups, {total_districts} complete leaf options; no duplicate IDs or cross-parent results',flush=True)


async def choose(page,province,city,district):
    await page.locator(f'#locationGroups [data-location-id="{province}"]').click()
    await page.locator(f'#locationCities [data-location-id="{city}"]').click()
    await page.locator(f'#locationDistricts [data-location-id="{district}"]').click()
    await expect(page.locator('#birthLocation')).to_have_value(district)


async def verify_browser():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(BASE,wait_until='networkidle')
        assert await page.locator('#locationOverseas').count()==0
        await page.locator('#locationTrigger').click()
        await expect(page.locator('.locationProvince')).to_have_count(34)
        assert 'CN.' not in await page.locator('#locationGroups').inner_text()
        await choose(page,'CN:440000','CN:440300','CN:440305')
        await expect(page.locator('#selectedLocationText')).to_have_text('广东省 / 深圳市 / 南山区')

        # A county ID must feed the real chart endpoint and survive page restoration.
        await page.locator('#birthName').fill('国内区县回归')
        for field,value in [('year','2002'),('month','1'),('day','25'),('hour','8'),('minute','5')]:
            await page.locator('#'+field).select_option(value)
        async with page.expect_response(lambda r:'/api/charts/resolve' in r.url and r.request.method=='POST') as pending:
            await page.locator('#loadChart').click()
        response=await pending.value
        assert response.ok,await response.text()
        chart=await response.json()
        assert chart['time_correction']['location']['id']=='CN:440305'
        await expect(page.locator('.palaceCell')).to_have_count(12)
        await page.locator('#homeBrand').click()
        await page.reload(wait_until='networkidle')
        await expect(page.locator('#birthLocation')).to_have_value('CN:440305')
        await page.locator('#locationTrigger').click()
        await expect(page.locator('#locationDistricts .selected')).to_have_text('南山区')

        async def delay_tianjin(route):
            await asyncio.sleep(.4)
            await route.continue_()
        await page.route(re.compile(r'/api/location-picker\?.*province=CN%3A120000'),delay_tianjin)
        await page.locator('#locationGroups [data-location-id="CN:120000"]').click()
        assert await page.locator('#locationDistricts .locationDistrict').count()==0
        await page.locator('#locationGroups [data-location-id="CN:440000"]').click()
        await expect(page.locator('#locationCities [data-location-id="CN:440300"]')).to_be_visible()
        await page.wait_for_timeout(600)
        await expect(page.locator('#locationGroups .selected')).to_have_text('广东省')
        assert await page.locator('#locationDistricts .locationDistrict').count()==0

        # Search results expose full ancestry when districts have identical names.
        await page.locator('#locationSearch').fill('朝阳')
        target=page.locator('#locationResults [data-location-id="CN:110105"]')
        await expect(target).to_contain_text('北京市 / 朝阳区')
        assert await page.locator('#locationResults .locationDistrict').count()>1
        await target.click()
        await expect(page.locator('#selectedLocationText')).to_have_text('北京市 / 朝阳区')

        await page.locator('#locationTrigger').click()
        await choose(page,'CN:710000','TW:63000','TW:63000010')
        await expect(page.locator('#selectedLocationText')).to_contain_text('台湾省 / 台北市')
        await page.locator('#locationTrigger').click()
        await choose(page,'CN:810000','CN:810100','CN:810102')
        await expect(page.locator('#selectedLocationText')).to_have_text('香港特别行政区 / 湾仔区')
        await page.locator('#locationTrigger').click()
        await choose(page,'CN:440000','CN:441900','CN:441900:all')
        await expect(page.locator('#selectedLocationText')).to_have_text('广东省 / 东莞市')

        for width,height in ((1440,1000),(390,844)):
            await page.set_viewport_size({'width':width,'height':height})
            await page.locator('#locationTrigger').click()
            await page.locator('#locationGroups [data-location-id="CN:510000"]').click()
            await page.locator('#locationCities [data-location-id="CN:510100"]').click()
            await expect(page.locator('#locationDistricts [data-location-id="CN:510107"]')).to_be_visible()
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.locator('#locationPopover').screenshot(path=f'/tmp/ziwei-domestic-picker-{width}.png')
            await page.locator('#locationDistricts [data-location-id="CN:510107"]').click()
            await expect(page.locator('#selectedLocationText')).to_have_text('四川省 / 成都市 / 武侯区')
        assert not errors,errors
        await browser.close()
        print('PASS browser: district selection, chart resolution, refresh restore, response races, duplicate names, Taiwan/HK, whole-city fallback, desktop/mobile; no JavaScript errors')


async def main():
    await verify_api()
    await verify_browser()


if __name__=='__main__':
    asyncio.run(main())
