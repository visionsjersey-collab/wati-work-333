import os
import sys
import asyncio
import subprocess
import zipfile
from aiohttp import web
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ✅ Flush logs immediately for Render
sys.stdout.reconfigure(line_buffering=True)

# ✅ Detect environment
ON_RENDER = os.environ.get("RENDER") == "true"

# ✅ Configure Playwright browser path
if ON_RENDER:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright-browsers"
else:
    local_browser_path = os.path.join(os.getcwd(), "playwright_browsers")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = local_browser_path
os.makedirs(os.environ["PLAYWRIGHT_BROWSERS_PATH"], exist_ok=True)

# ✅ Persistent profile path
USER_DATA_DIR = (
    "/opt/render/project/src/wati_profile" if ON_RENDER else os.path.join(os.getcwd(), "wati_profile")
)
ZIP_PATH = os.path.join(os.getcwd(), "wati_profile.zip")

# 🧩 Unzip saved login profile on Render
def unzip_wati_profile():
    if ON_RENDER and os.path.exists(ZIP_PATH):
        if not os.path.exists(USER_DATA_DIR):
            print("📦 Extracting saved login (wati_profile.zip)...", flush=True)
            with zipfile.ZipFile(ZIP_PATH, "r") as zip_ref:
                zip_ref.extractall(os.path.dirname(USER_DATA_DIR))
            print("✅ Login data extracted successfully!", flush=True)
        else:
            print("✅ Existing login folder detected — skipping unzip.", flush=True)
    else:
        print("ℹ️ Running locally — unzip not required.", flush=True)

# ✅ Ensure Chromium installed
async def ensure_chromium_installed():
    chromium_path = os.path.join(os.environ["PLAYWRIGHT_BROWSERS_PATH"], "chromium-1117/chrome-linux/chrome")
    if not os.path.exists(chromium_path):
        print("🧩 Installing Chromium...", flush=True)
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "playwright", "install", "chromium",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            print(line.decode().strip(), flush=True)
        await process.wait()
        print("✅ Chromium installed successfully!", flush=True)
    else:
        print("✅ Chromium already installed.", flush=True)

# 🌐 Config
WATI_URL = "https://live.wati.io/1037246/teamInbox/"
LOGIN_URL = "https://auth.wati.io/login"
CHECK_INTERVAL = 180  # seconds

# ✅ Manual login helper
async def wait_for_manual_login(page, browser_context):
    print("\n============================")
    print("🟢 MANUAL LOGIN REQUIRED")
    print("============================", flush=True)
    print("➡️ Complete your WATI login in the opened browser.")
    print("➡️ Once 'Team Inbox' is visible, press ENTER to save session.\n", flush=True)

    await page.goto(LOGIN_URL, wait_until="networkidle")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: input("👉 Press ENTER after login is complete... "))

    try:
        await page.goto(WATI_URL, timeout=60000)
        await page.wait_for_selector("text=Team Inbox", timeout=30000)
        print("✅ Login detected! Saving session...", flush=True)
        await browser_context.storage_state(path=os.path.join(USER_DATA_DIR, "storage.json"))
        print("✅ Session saved successfully as storage.json", flush=True)
        return True
    except PlaywrightTimeout:
        print("🚨 Login was not detected. Please retry.", flush=True)
        return False

# ✅ Automatic login
async def auto_login(page):
    print("🔑 Attempting automatic login...", flush=True)
    js_script = """() => {
        function setReactInputValue(el,v){
            const s=Object.getOwnPropertyDescriptor(el.__proto__,'value').set;
            s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));
        }
        const e=document.querySelector('input[name="email"]');
        if(e)setReactInputValue(e,'Visionsjersey@gmail.com');
        const p=document.querySelector('input[name="password"]');
        if(p)setReactInputValue(p,'27557434@rR');
        const t=document.querySelector('input[name="tenantId"]');
        if(t)setReactInputValue(t,'1037246');
        const b=document.querySelector('form button[type="submit"]');
        if(b)b.click();
    }"""
    try:
        await page.evaluate(js_script)
        await page.wait_for_selector("text=Team Inbox", timeout=30000)
        print("✅ Automatic login successful!", flush=True)
        return True
    except PlaywrightTimeout:
        print("❌ Automatic login failed.", flush=True)
        return False

# ✅ Main automation
async def main_automation(page):
    while True:
        print("🔎 Checking for unread chats...", flush=True)
        try:
            await page.wait_for_selector("div.conversation-item__unread-count", timeout=10000)
        except PlaywrightTimeout:
            print("😴 No unread chats. Waiting 3 mins...", flush=True)
            await asyncio.sleep(CHECK_INTERVAL)
            await page.reload()
            continue

        unread = await page.query_selector_all("div.conversation-item__unread-count")
        if not unread:
            print("😴 No unread chats. Waiting 3 mins...", flush=True)
            await asyncio.sleep(CHECK_INTERVAL)
            await page.reload()
            continue

        print(f"💬 Found {len(unread)} unread chat(s).", flush=True)
        for i, elem in enumerate(unread, 1):
            try:
                await elem.scroll_into_view_if_needed()
                await elem.click()
                await asyncio.sleep(2.5)
                await page.click("#mainTeamInbox div.chat-side-content div span.chat-input__icon-option", timeout=10000)
                ads = await page.query_selector("#flow-nav-68ff67df4f393f0757f108d8")
                if ads: await ads.click()
                print(f"✅ Processed chat {i}/{len(unread)}", flush=True)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"⚠️ Error chat {i}: {e}", flush=True)
        await asyncio.sleep(CHECK_INTERVAL)
        await page.reload()

# ✅ Run bot
async def run_wati_bot():
    print("🌐 Launching WATI automation with persistent browser...", flush=True)
    headless_mode = False  # Xvfb handles GUI invisibly

    async with async_playwright() as p:
        browser_context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=headless_mode,
        )
        page = await browser_context.new_page()
        print("🌍 Navigating to WATI Inbox...", flush=True)
        await page.goto(WATI_URL, timeout=60000)
        await asyncio.sleep(3)

        try:
            await page.wait_for_selector("text=Team Inbox", timeout=60000)
            print("✅ Logged in — session active!", flush=True)
        except PlaywrightTimeout:
            success = await auto_login(page)
            if not success:
                print("ℹ️ Falling back to manual login...")
                await wait_for_manual_login(page, browser_context)

        # ✅ Zip after successful login
        if not ON_RENDER:
            print("📦 Creating wati_profile.zip for Render...", flush=True)
            with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(USER_DATA_DIR):
                    for file in files:
                        fp = os.path.join(root, file)
                        if any(s in fp for s in ["Singleton", "RunningChromeVersion"]):
                            continue
                        zipf.write(fp, os.path.relpath(fp, os.path.dirname(USER_DATA_DIR)))
            print("✅ wati_profile.zip created successfully!", flush=True)

        print("🤖 Starting main automation loop...", flush=True)
        await main_automation(page)

# ✅ Web server
async def start_web_server():
    async def handle(request):
        return web.Response(text="✅ WATI AutoBot running successfully!")
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()
    print("🌍 Web server running!", flush=True)

# 🚀 Entry
async def main():
    print("🚀 Initializing environment...", flush=True)
    unzip_wati_profile()
    await ensure_chromium_installed()
    print("🚀 Starting bot and web server...", flush=True)
    await asyncio.gather(start_web_server(), run_wati_bot())

if __name__ == "__main__":
    asyncio.run(main())
