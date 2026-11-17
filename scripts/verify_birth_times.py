"""Disposable-account browser check; chat answers are mocked, no LLM is invoked."""
import asyncio
import json
import os
import re
from pathlib import Path
from uuid import uuid4

import asyncpg
from playwright.async_api import async_playwright, expect


async def main():
    username='timeui_'+uuid4().hex[:12]
    password=uuid4().hex
    conn=await asyncpg.connect(os.environ['DATABASE_URL'])
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
            page=await browser.new_page(viewport={'width':1440,'height':1000})
            base='http://127.0.0.1'
            errors=[]
            page.on('pageerror',lambda err:errors.append(str(err)))
            response=await page.request.post(base+'/api/auth/register',data={
                'username':username,'password':password,'confirm_password':password})
            assert response.ok,await response.text()
            response=await page.request.post(base+'/api/auth/login',data={'account':username,'password':password})
            assert response.ok
            await page.goto(base,wait_until='networkidle')
            await page.locator('#locationTrigger').click()
            await page.locator('#locationGroups [data-location-id="CN:110000"]').click()
            await page.locator('#locationDistricts [data-location-id="CN:110105"]').click()
            await page.locator('#birthName').fill('原始时间A')
            for field,value in [('year','2002'),('month','1'),('day','25'),('hour','8'),('minute','5')]:
                await page.locator('#'+field).select_option(value)
            async with page.expect_response(lambda r:'/api/saved-charts' in r.url and r.request.method=='POST') as pending:
                await page.locator('#loadChart').click()
            response=await pending.value
            assert response.ok,await response.text()
            saved=await response.json()
            clock=saved['time_correction']['clock_time'].replace('T',' ')
            solar=saved['time_correction']['true_solar_time'].replace('T',' ')
            async def check_times(expected_clock=clock,expected_solar=solar):
                await expect(page.locator('[data-time-kind=clock]>span')).to_have_text(expected_clock)
                await expect(page.locator('[data-time-kind=solar]>span')).to_have_text(expected_solar)
            await check_times()

            # Exercise the exact first-question path that previously discarded context.
            captured=[]
            async def messages(route):
                if route.request.method!='POST':
                    await route.continue_()
                    return
                data=route.request.post_data_json
                await route.fulfill(status=202,json={'user_seq':1,'request_id':data['client_request_id']})
            async def events(route):
                await route.fulfill(status=200,content_type='text/event-stream',body=
                    'id: 2\nevent: message_end\ndata: '+json.dumps({'seq':2,'answer':'时间恢复测试完成','title':'时间核验'},ensure_ascii=False)+'\n\n')
            page.on('request',lambda request:captured.append(request.post_data_json)
                    if request.method=='POST' and request.url.endswith('/api/sessions') else None)
            await page.route(re.compile(r'/api/sessions/[^/]+/messages$'),messages)
            await page.route(re.compile(r'/api/sessions/[^/]+/events\?'),events)
            await page.locator('#chatMode').click()
            await page.locator('#question').fill('验证时间显示')
            async with page.expect_response(lambda r:r.url.endswith('/api/sessions') and r.request.method=='POST') as pending:
                await page.locator('#ask').click()
            created=await (await pending.value).json()
            sid=created['id']
            assert captured[0]['input_birth']['minute']==5
            assert created['input_birth']['location_id']=='CN:110105'
            await expect(page.locator('#messages')).to_contain_text('时间恢复测试完成')
            await expect(page.locator('#notice')).to_have_text('')
            await check_times()
            await page.reload(wait_until='networkidle')
            await check_times()
            await page.locator('#analysisMode').click()

            # Same corrected chart key, different raw minutes: never borrow another record.
            birth_b=saved['input_birth']|{'name':'原始时间B','minute':6}
            response=await page.request.post(base+'/api/saved-charts',data=birth_b)
            second=await response.json()
            assert second['chart_key']==saved['chart_key']
            response=await page.request.post(base+'/api/sessions',data={
                'chart_key':second['chart_key'],'chart_name':birth_b['name'],'input_birth':birth_b})
            second_sid=(await response.json())['id']
            await page.evaluate('async id=>selectSession(id,{mode:"analysis"})',second_sid)
            await check_times(second['time_correction']['clock_time'].replace('T',' '),
                              second['time_correction']['true_solar_time'].replace('T',' '))
            await page.evaluate('async id=>selectSession(id,{mode:"analysis"})',sid)
            await check_times()
            response=await page.request.delete(base+'/api/saved-charts')
            assert response.ok
            await page.reload(wait_until='networkidle')
            await check_times()

            # Migration restores only owner/name/key matches unchanged since session creation.
            uid=await conn.fetchval('SELECT id FROM auth_user WHERE username=$1',username)
            response=await page.request.post(base+'/api/saved-charts',data=saved['input_birth'])
            assert response.ok
            legacy=uuid4()
            await conn.execute('''INSERT INTO chat_session(id,user_id,chart_key,chart_name)
                VALUES($1,$2,$3,$4)''',legacy,uid,saved['chart_key'],saved['name'])
            await conn.execute((Path('sql')/'migrations'/'001_session_birth_context.sql').read_text())
            restored=await page.request.get(base+'/api/sessions/'+str(legacy))
            assert (await restored.json())['input_birth']['minute']==5
            assert not errors,errors
            await browser.close()
            print('PASS: clock/solar time on creation, first question, session switch, refresh, deletion of saved charts, distinct minutes sharing a chart key, and legacy migration; no LLM invoked')
    finally:
        await conn.execute('DELETE FROM auth_user WHERE username=$1',username)
        await conn.execute('DELETE FROM auth_login_attempt WHERE account_key=$1',username)
        await conn.close()


if __name__=='__main__':
    asyncio.run(main())
