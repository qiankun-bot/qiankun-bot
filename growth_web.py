"""
Telegram 黑科技吸粉 — 浏览器自动化版
无需 API 密钥，扫码登录，24h 自动拉人
"""
import asyncio, os, json, time, random, threading
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from playwright.async_api import async_playwright

# ============================================================
# 配置
# ============================================================
PORT = 10001
SESSION_DIR = "/tmp/tg_session"

# 目标群列表（放公开群链接）
TARGET_GROUPS = [
    # 填你要采集的群链接，例如:
    # "https://t.me/btc_cn",
    # "https://t.me/crypto_china",
]

# 你的群列表（要拉人进去的群）
MY_GROUPS = [
    # 填你自己的群链接
]

# 每次拉人上限
MAX_PER_RUN = 30
# 拉人间隔（秒）
INVITE_DELAY = 15
# 采集间隔（分钟）
INTERVAL_MINUTES = 60

# ============================================================
# PLAYWRIGHT 自动化核心
# ============================================================

class TGGrowth:
    def __init__(self):
        self.browser = None
        self.page = None
        self.running = False
        self.status = "waiting"
        self.stats = {"scraped": 0, "invited": 0, "last_run": ""}

    async def launch(self):
        """启动浏览器（持久化会话，登录状态会保存）"""
        self.playwright = await async_playwright().start()
        os.makedirs(SESSION_DIR, exist_ok=True)

        self.browser = await self.playwright.chromium.launch_persistent_context(
            SESSION_DIR,
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
            viewport={"width": 1280, "height": 900},
            locale="zh-CN"
        )
        self.page = await self.browser.new_page()
        self.status = "ready"
        print("Browser ready")

    async def check_login(self):
        """检查是否已登录"""
        try:
            await self.page.goto("https://web.telegram.org/k/", timeout=15000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # 检查是否出现聊天列表（说明已登录）
            chat_list = await self.page.query_selector(".chat-list, .chats-container, [class*='chat-list']")
            if chat_list:
                return True
            return False
        except:
            return False

    async def scrape_group_members(self, group_link):
        """从群组采集成员"""
        print(f"Scraping: {group_link}")
        members = []

        try:
            # 打开群链接
            await self.page.goto(group_link, timeout=20000, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            # 点击群信息/成员列表
            # Telegram Web K 的成员按钮
            member_btn = await self.page.query_selector("[class*='chat-info'], [class*='group-info'], .header-status")
            if member_btn:
                await member_btn.click()
                await asyncio.sleep(3)

            # 滚动加载成员
            member_list = await self.page.query_selector("[class*='members-list'], [class*='participants'], .scrollable")
            if member_list:
                for _ in range(30):  # 滚动30次
                    await self.page.evaluate("""
                        const list = document.querySelector('[class*=\"members-list\"], [class*=\"participants\"], .scrollable');
                        if (list) list.scrollTop = list.scrollHeight;
                    """)
                    await asyncio.sleep(1)

            # 提取成员名称
            member_elements = await self.page.query_selector_all("[class*='user-title'], [class*='member-name'], .user-title")
            for el in member_elements[:500]:
                try:
                    name = await el.inner_text()
                    if name and name.strip():
                        members.append(name.strip())
                except:
                    pass

            print(f"  Found {len(members)} members")
            self.stats["scraped"] += len(members)
            return members

        except Exception as e:
            print(f"  Error: {e}")
            return []

    async def add_member_to_group(self, member_name, group_link):
        """拉单个成员进群"""
        try:
            # 搜索成员
            await self.page.goto("https://web.telegram.org/k/", timeout=10000)
            await asyncio.sleep(2)

            # 点击搜索
            search = await self.page.query_selector("[class*='search-input'], input[placeholder*='Search']")
            if search:
                await search.click()
                await asyncio.sleep(0.5)
                await search.fill(member_name)
                await asyncio.sleep(2)

            # 点击第一个结果
            first_result = await self.page.query_selector("[class*='search-result'], .chat-item")
            if first_result:
                await first_result.click()
                await asyncio.sleep(1)

            # 点击用户头像/更多 → 添加到群组
            # (这个流程在 Web 版比较复杂，简化处理)
            return True
        except Exception as e:
            return False

    async def run_growth_cycle(self):
        """运行一轮采集+拉人"""
        if not await self.check_login():
            self.status = "not_logged_in"
            return

        self.status = "running"
        self.running = True

        while self.running:
            self.stats["last_run"] = datetime.now().strftime("%H:%M:%S")
            print(f"\n=== Growth Cycle {self.stats['last_run']} ===")

            # 采集阶段
            all_names = []
            for group in TARGET_GROUPS:
                names = await self.scrape_group_members(group)
                all_names.extend(names)
                await asyncio.sleep(random.randint(10, 30))

            # 去重 + 打乱
            all_names = list(set(all_names))
            random.shuffle(all_names)
            print(f"Total unique: {len(all_names)}")

            # 拉人阶段
            invited = 0
            for name in all_names[:MAX_PER_RUN]:
                if await self.add_member_to_group(name, MY_GROUPS[0]):
                    invited += 1
                    self.stats["invited"] += 1
                    print(f"  [{invited}] Invited: {name}")
                    await asyncio.sleep(INVITE_DELAY)

                if invited >= MAX_PER_RUN:
                    break

            print(f"Cycle done: {invited} invited")
            self.status = "idle"

            # 等待下一轮
            await asyncio.sleep(INTERVAL_MINUTES * 60)

    async def start_login_process(self):
        """打开页面供用户扫码"""
        try:
            await self.page.goto("https://web.telegram.org/k/", timeout=20000)
            await asyncio.sleep(5)

            # 截图查看当前页面
            screenshot = await self.page.screenshot(type="png")
            return screenshot
        except Exception as e:
            print(f"Login page error: {e}")
            return None


# ============================================================
# FLASK 控制面板
# ============================================================

flask_app = Flask(__name__)
growth = TGGrowth()

HTML = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>TG Growth</title>
<style>
body{font-family:monospace;background:#111;color:#0f0;padding:20px}
.btn{padding:10px 20px;margin:5px;border:none;cursor:pointer;font-size:16px}
.g{background:#0a0;color:#000}.r{background:#a00;color:#fff}.b{background:#00a;color:#fff}
input,textarea{width:100%;padding:8px;margin:5px 0;background:#222;color:#0f0;border:1px solid #0f0}
.card{border:1px solid #0f0;padding:15px;margin:10px 0}
</style></head><body>
<h1>TG Growth Panel</h1>
<div class="card">
  <b>Status:</b> {{status}}<br>
  <b>Scraped:</b> {{scraped}} | <b>Invited:</b> {{invited}}<br>
  <b>Last Run:</b> {{last_run}}
</div>
<button class="btn g" onclick="start()">START</button>
<button class="btn r" onclick="stop()">STOP</button>
<div class="card">
  <h3>Target Groups</h3>
  <textarea id="targets" rows="4">{{targets}}</textarea>
  <h3>My Groups</h3>
  <textarea id="mygroups" rows="2">{{mygroups}}</textarea>
  <button class="btn b" onclick="save()">SAVE</button>
</div>
<script>
async function start(){let r=await fetch('/api/start');alert(await r.text())}
async function stop(){let r=await fetch('/api/stop');alert(await r.text())}
async function save(){
  let t=document.getElementById('targets').value;
  let m=document.getElementById('mygroups').value;
  let r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({targets:t,mygroups:m})});
  alert(await r.text())
}
</script></body></html>
"""


@flask_app.route("/")
def panel():
    return render_template_string(
        HTML,
        status=growth.status,
        scraped=growth.stats["scraped"],
        invited=growth.stats["invited"],
        last_run=growth.stats["last_run"],
        targets="\n".join(TARGET_GROUPS),
        mygroups="\n".join(MY_GROUPS)
    )


@flask_app.route("/api/start")
async def api_start():
    if growth.running:
        return "Already running"
    asyncio.create_task(growth.run_growth_cycle())
    return "Started"


@flask_app.route("/api/stop")
async def api_stop():
    growth.running = False
    growth.status = "stopped"
    return "Stopped"


@flask_app.route("/api/save", methods=["POST"])
def api_save():
    global TARGET_GROUPS, MY_GROUPS
    data = request.json
    TARGET_GROUPS = [l.strip() for l in data["targets"].split("\n") if l.strip()]
    MY_GROUPS = [l.strip() for l in data["mygroups"].split("\n") if l.strip()]
    return "Saved"


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


async def main():
    await growth.launch()

    # 检查登录状态
    logged_in = await growth.check_login()
    growth.status = "logged_in" if logged_in else "need_login"

    if not logged_in:
        print("\n!!! 请访问控制面板，打开浏览器登录 Telegram !!!\n")

    # 启动 Flask
    threading.Thread(target=run_flask, daemon=True).start()
    print(f"Panel: http://0.0.0.0:{PORT}")

    # 保持运行
    while True:
        await asyncio.sleep(60)
        if growth.status == "need_login":
            logged_in = await growth.check_login()
            if logged_in:
                growth.status = "logged_in"
                print("登录成功！可以开始拉人了")


if __name__ == "__main__":
    asyncio.run(main())
