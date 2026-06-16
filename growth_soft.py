"""
Telegram 软钓鱼工具 — 监听群聊 + 精准私信
===========================================
加入热门加密群 → 自动监测求助信号 → 友好私信 → 引导进群
"""
import asyncio, os, json, time, random, threading, logging, re
from datetime import datetime
from flask import Flask, request, render_template_string
from telethon import TelegramClient, events
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import FloodWaitError

PORT = 10002
DATA_DIR = "/tmp/qk_data"
os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================
# 配置
# ============================================================

# 目标群（加入并监听）
WATCH_GROUPS = [
    # "https://t.me/crypto_china",
    # "@btc_group",
]

# 你的群链接（对方回复后引导过去）
MY_GROUP_LINK = "https://t.me/your_group"

# 关键词匹配 — 检测求助信号
HELP_PATTERNS = [
    r"怎么买[币比特]", r"新手.*求", r"刚.*入.*[圈币]",
    r"亏了", r"被割", r"套住了", r"爆仓",
    r"有.*[群组织]", r"带带", r"跟单",
    r"推荐.*[币项目]", r"什么.*能买",
    r"how.*buy", r"new.*crypto", r"beginner",
    r"想.*[投玩玩]", r"有.*大佬",
]

# 私信话术（随机选一条发送）
DM_TEMPLATES = [
    """👋 你好！刚才在群里看到你在问{keyword}相关的问题。

我在加密市场做了几年了，正好对这个比较了解。如果你需要的话我可以分享一些分析，不收费的 😊""",

    """👋 Hi！刚在群里看到你的消息。

你问的{keyword}这个问题，很多新手都会遇到。我整理过一份入门指南，需要的话发你一份？""",

    """👋 嗨，看到你在群里问{keyword}。

其实这个问题说简单也简单，说复杂也复杂。如果你真的感兴趣，我可以花几分钟跟你聊聊我自己的经验，免费的。""",

    """👋 你好呀！刚群里有条消息我看到了。

如果你对{keyword}真的感兴趣，我刚好在做一个加密交流社区，里面全是实盘分享，不收费。可以来坐坐 👇
{MY_GROUP_LINK}""",
]

# 已私信用户（防重复）
CONTACTED_FILE = os.path.join(DATA_DIR, "contacted.json")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 引擎
# ============================================================

class SoftFishEngine:
    def __init__(self):
        self.client = None
        self.connected = False
        self.running = False
        self.watch_groups = []
        self.my_link = ""
        self.stats = {"matched": 0, "sent": 0, "replied": 0, "last": "", "log": []}
        self.contacted = set()
        self._load_contacted()

    def _load_contacted(self):
        try:
            if os.path.exists(CONTACTED_FILE):
                self.contacted = set(json.load(open(CONTACTED_FILE)))
        except: pass

    def _save_contacted(self):
        json.dump(list(self.contacted), open(CONTACTED_FILE, "w"))

    def log(self, msg):
        t = datetime.now().strftime("%H:%M:%S")
        self.stats["log"].append(f"[{t}] {msg}")
        self.stats["log"] = self.stats["log"][-50:]
        print(msg)

    async def setup(self, api_id, api_hash, phone):
        sp = os.path.join(DATA_DIR, "fish_session")
        self.client = TelegramClient(sp, int(api_id), api_hash)
        await self.client.start(phone=phone)
        me = await self.client.get_me()
        self.connected = True
        self.log(f"Logged in: {me.first_name}")
        return me

    async def join_and_watch(self):
        """加入所有目标群并开始监听"""
        entities = []
        for link in self.watch_groups:
            try:
                if "t.me" in link:
                    h = link.split("/")[-1].split("?")[0].replace("+", "")
                    res = await self.client(ImportChatInviteRequest(h))
                    chat = res.chats[0] if hasattr(res, "chats") else res
                else:
                    chat = await self.client.get_entity(link)
                entities.append(chat)
                self.log(f"Joined: {getattr(chat, 'title', link)}")
            except Exception as e:
                self.log(f"Join err ({link}): {str(e)[:60]}")

        # 注册消息监听
        @self.client.on(events.NewMessage(chats=entities))
        async def handler(event):
            await self._handle_message(event)

        self.log(f"Watching {len(entities)} groups")
        return entities

    async def _handle_message(self, event):
        """处理新消息 — 检测关键词并私信"""
        msg = event.message
        if not msg.text: return

        text = msg.text
        sender = await msg.get_sender()
        if not sender or sender.bot or sender.is_self: return

        uid = str(sender.id)
        if uid in self.contacted: return

        # 匹配关键词
        matched = None
        for pattern in HELP_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                matched = m.group()
                break

        if not matched: return

        self.stats["matched"] += 1
        self.log(f"Match: {sender.first_name or ''} said \"{matched}\" in {event.chat.title if hasattr(event.chat, 'title') else ''}")

        # 选择话术
        template = random.choice(DM_TEMPLATES)
        dm = template.format(keyword=matched, MY_GROUP_LINK=self.my_link or MY_GROUP_LINK)

        # 发送私信
        try:
            await self.client.send_message(sender.id, dm)
            self.contacted.add(uid)
            self.stats["sent"] += 1
            self._save_contacted()
            self.log(f"DM sent to: {sender.first_name}")
            time.sleep(random.randint(10, 30))  # 延迟防封
        except FloodWaitError as e:
            self.log(f"Flood wait {e.seconds}s")
            time.sleep(e.seconds + 5)
        except Exception as e:
            self.log(f"DM err: {str(e)[:60]}")

    async def start_fishing(self):
        """启动钓鱼"""
        if not self.connected:
            self.log("Not connected")
            return
        self.running = True
        self.stats["last"] = datetime.now().strftime("%H:%M:%S")

        # 加入并监听
        await self.join_and_watch()

        self.log("Fishing started — waiting for matches...")

        # 保持运行
        while self.running:
            await asyncio.sleep(60)

    def stop(self):
        self.running = False


engine = SoftFishEngine()

# ============================================================
# WEB PANEL
# ============================================================

app = Flask(__name__)

HTML = """
<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Soft Fish Panel</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui;background:#0a0a0a;color:#eee;padding:16px;max-width:600px;margin:0 auto}
h1{color:#00bfff;margin-bottom:16px}
.card{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:16px;margin-bottom:16px}
.card h3{color:#00bfff;margin-bottom:10px}
input,textarea{width:100%;padding:10px;margin:6px 0;background:#0a0a0a;color:#0f0;border:1px solid #333;border-radius:4px;font-size:14px}
textarea{height:80px;font-family:monospace;font-size:12px}
.btn{width:100%;padding:14px;margin:8px 0;border:none;border-radius:6px;font-size:16px;font-weight:bold;cursor:pointer;color:#000}
.g{background:#00bfff}.r{background:#a00;color:#fff}.b{background:#224;color:#fff}
.s{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #222}
.log{background:#000;color:#0a0;padding:8px;border-radius:4px;font-size:11px;max-height:180px;overflow-y:auto;font-family:monospace;white-space:pre-wrap}
</style></head><body>
<h1>Soft Fish Panel</h1>
<div class="card">
  <h3>Status</h3>
  <div class="s"><span>Connected</span><span>{{cfg}}</span></div>
  <div class="s"><span>Running</span><span>{{run}}</span></div>
  <div class="s"><span>Matched</span><span>{{s.matched}}</span></div>
  <div class="s"><span>DM Sent</span><span>{{s.sent}}</span></div>
  <div class="s"><span>Last</span><span>{{s.last}}</span></div>
</div>
<div class="card">
  <h3>1. Connect</h3>
  <input id="aid" placeholder="api_id">
  <input id="ahs" placeholder="api_hash">
  <input id="phn" placeholder="Phone (+86138...)">
  <button class="btn b" onclick="setup()">CONNECT</button>
</div>
<div class="card">
  <h3>2. Groups</h3>
  <textarea id="wgs" placeholder="Watch groups (one per line)
https://t.me/crypto_china
@btc_trading">{{wgs}}</textarea>
  <input id="mlk" placeholder="Your group link" value="{{mlk}}">
  <button class="btn b" onclick="save()">SAVE</button>
</div>
<div class="card">
  <h3>3. Run</h3>
  <button class="btn g" onclick="run()">START FISHING</button>
  <button class="btn r" onclick="stop()">STOP</button>
</div>
<div class="log" id="log">{{log}}</div>
<script>
async function api(u,b){
  let o={method:b?'POST':'GET'}
  if(b){o.headers={'Content-Type':'application/json'};o.body=JSON.stringify(b)}
  let r=await fetch(u,o);return await r.json()
}
async function setup(){
  let d={api_id:document.getElementById('aid').value,api_hash:document.getElementById('ahs').value,phone:document.getElementById('phn').value}
  let r=await api('/f/setup',d);alert(r.msg||r.error)
}
async function save(){
  let d={watch:document.getElementById('wgs').value,my_link:document.getElementById('mlk').value}
  let r=await api('/f/save',d);alert(r.msg)
}
async function run(){let r=await api('/f/start');alert(r.msg||r.error)}
async function stop(){let r=await api('/f/stop');alert(r.msg)}
setInterval(async()=>{let r=await api('/f/stats');document.getElementById('log').textContent=(r.log||[]).join('\n')},3000)
</script></body></html>
"""

@app.route("/")
def home():
    return "Soft Fish Engine online"

@app.route("/fish")
def panel():
    return render_template_string(HTML,
        cfg="YES" if engine.connected else "NO",
        run="YES" if engine.running else "NO",
        s=engine.stats,
        wgs="\n".join(engine.watch_groups),
        mlk=engine.my_link or MY_GROUP_LINK,
        log="\n".join(engine.stats["log"]))

@app.route("/f/setup", methods=["POST"])
async def f_setup():
    try:
        d = request.json
        me = await engine.setup(d["api_id"], d["api_hash"], d["phone"])
        return {"msg": f"OK: {me.first_name}"}
    except Exception as e:
        return {"error": str(e)[:200]}

@app.route("/f/save", methods=["POST"])
def f_save():
    d = request.json
    engine.watch_groups = [l.strip() for l in d["watch"].split("\n") if l.strip()]
    engine.my_link = d.get("my_link", "").strip()
    return {"msg": "Saved"}

@app.route("/f/start")
async def f_start():
    if not engine.connected: return {"error": "Connect first"}
    if engine.running: return {"msg": "Running"}
    asyncio.ensure_future(engine.start_fishing())
    return {"msg": "Started"}

@app.route("/f/stop")
def f_stop():
    engine.stop()
    return {"msg": "Stopped"}

@app.route("/f/stats")
def f_stats():
    return {"log": engine.stats["log"], "running": engine.running, "connected": engine.connected}

def run_web():
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    print(f"Soft Fish Panel: http://0.0.0.0:{PORT}/fish")
    run_web()
