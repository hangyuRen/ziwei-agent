"""Browser regression checks against the local service, using a disposable account.

Run with Playwright available and DATABASE_URL set (e.g. uv --env-file .env).
"""
import asyncio
import os
from uuid import uuid4

import asyncpg
from playwright.async_api import async_playwright, expect


async def main():
    username='recordui_'+uuid4().hex[:12]
    password=uuid4().hex
    conn=await asyncpg.connect(os.environ['DATABASE_URL'])
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
            page=await browser.new_page(viewport={'width':1440,'height':1000})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            base='http://127.0.0.1'
            response=await page.request.post(base+'/api/auth/register',data={
                'username':username,'password':password,'confirm_password':password})
            assert response.ok,await response.text()
            response=await page.request.post(base+'/api/auth/login',data={'account':username,'password':password})
            assert response.ok,await response.text()
            birth={'name':'保留命盘','calendar':'solar','year':2002,'month':1,'day':25,
                   'clock_hour':8,'minute':5,'gender':'male','location_id':'1816670'}
            for name in ('保留命盘','待修改命盘'):
                response=await page.request.post(base+'/api/saved-charts',data=birth|{'name':name})
                assert response.ok,await response.text()
                saved=await response.json()
            response=await page.request.post(base+'/api/sessions',data={'chart_key':saved['chart_key'],'chart_name':birth['name']})
            assert response.ok,await response.text()
            session=await response.json()
            await page.goto(base,wait_until='networkidle')
            await expect(page.locator('.savedChartEntry')).to_have_count(2)

            await page.locator('#locationTrigger').click()
            await expect(page.locator('.locationProvince',has_text='广东省')).to_be_visible()
            assert 'CN.' not in await page.locator('#locationGroups').inner_text()
            # A delayed response must never leave the previous province's cities clickable.
            async def delay_tianjin(route):
                await asyncio.sleep(.3)
                await route.continue_()
            await page.route('**/api/location-picker?*province=CN%3A120000*',delay_tianjin)
            await page.locator('#locationGroups').get_by_role('button',name='重庆市',exact=True).click()
            await expect(page.locator('.locationCity').first).to_contain_text('重庆')
            await page.locator('#locationGroups').get_by_role('button',name='天津市',exact=True).click()
            assert await page.locator('.locationCity').count()==0
            await page.locator('#locationGroups').get_by_role('button',name='广东省',exact=True).click()
            await expect(page.locator('.locationCity',has_text='广州')).to_be_visible()
            await page.wait_for_timeout(500)
            assert await page.locator('.locationProvince.selected').inner_text()=='广东省'
            assert '天津' not in await page.locator('#locationCities').inner_text()
            assert await page.locator('#locationOverseas').count()==0
            await page.locator('#locationGroups').get_by_role('button',name='天津市',exact=True).click()
            await expect(page.locator('.locationCity').first).to_contain_text('天津')
            assert '重庆' not in await page.locator('#locationCities').inner_text()
            await page.locator('#locationPicker').press('Escape')

            entry=page.locator('.savedChartEntry',has_text='待修改命盘')
            await entry.locator('.rename').click()
            await expect(page.locator('#actionLabel')).to_have_text('命盘名称')
            await page.locator('#actionInput').fill('已改名命盘')
            await page.locator('#actionConfirm').click()
            await expect(page.locator('.savedChartEntry',has_text='已改名命盘')).to_have_count(1)
            await page.locator('.recentConversations').evaluate('(el)=>el.open=true')
            await page.locator('#sessionList .rename').click()
            await page.locator('#actionInput').fill('已改名对话')
            await page.locator('#actionConfirm').click()
            await expect(page.locator('#sessionList .session')).to_have_text('已改名对话')
            await expect(page.locator('#chatSessionList .session')).to_have_text('已改名对话')
            # Both desktop and phone must expose actions without hover, with no overflow.
            for width,height in ((1440,1000),(390,844)):
                await page.set_viewport_size({'width':width,'height':height})
                await expect(page.locator('.savedChartEntry .delete').first).to_be_visible()
                await expect(page.locator('#sessionList .delete')).to_be_visible()
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                await page.locator('#sessionList .session').click()
                await expect(page.locator('#chatTitle')).to_have_text('已改名对话')
                await expect(page.locator('#chatSessionList .rename')).to_be_visible()
                await expect(page.locator('#chatSessionList .delete')).to_be_visible()
                assert await page.locator('#chatSessionList').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
                assert await page.locator('.sessionSidebar').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                await page.screenshot(path=f'/tmp/ziwei-record-controls-{width}.png',full_page=True)
                await page.locator('#homeBrand').click()
            await page.locator('.savedChartEntry',has_text='已改名命盘').locator('.delete').click()
            await page.locator('#actionConfirm').click()
            await expect(page.locator('.savedChartEntry')).to_have_count(1)
            await expect(page.locator('.savedChartEntry')).to_contain_text('保留命盘')
            response=await page.request.get(base+'/api/sessions/'+session['id'])
            assert response.ok
            await page.locator('#sessionList .delete').click()
            await page.locator('#actionConfirm').click()
            await expect(page.locator('#sessionList .session')).to_have_count(0)
            await expect(page.locator('#chatSessionList .session')).to_have_count(0)
            assert not errors,errors
            await browser.close()
            print('PASS: province changes, delayed responses, chart/session rename and single deletion, desktop/mobile actions, no JavaScript errors')
    finally:
        await conn.execute('DELETE FROM auth_user WHERE username=$1',username)
        await conn.execute('DELETE FROM auth_login_attempt WHERE account_key=$1',username)
        await conn.close()


if __name__=='__main__':
    asyncio.run(main())
