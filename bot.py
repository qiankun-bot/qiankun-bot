"""
QK Community 鈥?All-in-One Bot (no api credentials needed!)
Just phone number + verification code
"""
import asyncio, os, json, time, random, threading, logging, re
from datetime import datetime
from flask import Flask, request, render_template_string
from telegram import Update, ChatMemberUpdated
from telegram.constants import ChatMemberStatus
from telegram.ext import (Application, CommandHandler, MessageHandler, ChatMemberHandler, ContextTypes, filters)
from telethon import TelegramClient, events
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import FloodWaitError, UserPrivacyRestrictedError, PeerFloodError

PORT = 10000
DATA_DIR = "/tmp/qk"
os.makedirs(DATA_DIR, exist_ok=True)
BOT_TOKEN = "8703063744:AAEW0qb7jDkF9UHxQUqGULsc54y42HXi8Rc"
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# GROWTH ENGINE
# ============================================================
class GrowthEngine:
    def __init__(self):
        self.client = None
        self.running = False
        self.ready = False
        self.targets = []
        self.mygroups = []
        self.phone = ""
        self.phone_code_hash = ""
        self.bl = set()
        self.stats = {"scraped":0,"invited":0,"skipped":0,"last":"","log":[],"step":"waiting"}
        self._load_bl()

    def _load_bl(self):
        try:
            f = os.path.join(DATA_DIR, "bl.json")
            if os.path.exists(f): self.bl = set(json.load(open(f)))
        except: pass
    def _save_bl(self):
        json.dump(list(self.bl), open(os.path.join(DATA_DIR, "bl.json"), "w"))
    def log(self, msg):
        t = datetime.now().strftime("%H:%M:%S")
        self.stats["log"].append(f"[{t}] {msg}")
        self.stats["log"] = self.stats["log"][-50:]
        print(msg)

    async def send_code(self, phone):
        """Step 1: Send verification code"""
        sp = os.path.join(DATA_DIR, "session_h")
        self.client = TelegramClient(sp, API_ID, API_HASH)
        await self.client.connect()
        result = await self.client.send_code_request(phone)
        self.phone = phone
        self.phone_code_hash = result.phone_code_hash
        self.stats["step"] = "code_sent"
        self.log(f"Code sent to {phone}")
        return True

    async def verify_code(self, code):
        """Step 2: Verify code and complete login"""
        try:
            await self.client.sign_in(self.phone, code, phone_code_hash=self.phone_code_hash)
        except Exception as e:
            # Try password if 2FA
            if "password" in str(e).lower():
                self.stats["step"] = "need_password"
                return {"need_password": True}
            raise

        me = await self.client.get_me()
        self.ready = True
        self.stats["step"] = "ready"
        self.log(f"Logged in: {me.first_name}")
        return {"ok": True, "name": me.first_name}

    async def verify_password(self, password):
        """Step 2b: Verify 2FA password"""
        await self.client.sign_in(password=password)
        me = await self.client.get_me()
        self.ready = True
        self.stats["step"] = "ready"
        self.log(f"Logged in: {me.first_name}")
        return {"ok": True, "name": me.first_name}

    async def scrape(self, link):
        self.log(f"Scrape: {link}")
        try:
            if "t.me" in link:
                h = link.split("/")[-1].split("?")[0].replace("+","")
                e = await self.client(ImportChatInviteRequest(h))
                chat = e.chats[0] if hasattr(e,"chats") else e
            else: chat = await self.client.get_entity(link)
            members = []
            async for u in self.client.iter_participants(chat, aggressive=True, limit=200):
                if not u.bot and not u.deleted and not u.is_self: members.append(u)
            self.log(f"Found {len(members)}")
            return members
        except Exception as e:
            self.log(f"Err: {str(e)[:60]}")
            return []

    async def invite(self, members, link):
        if "t.me" in link:
            h = link.split("/")[-1].split("?")[0].replace("+","")
            e = await self.client(ImportChatInviteRequest(h))
            chat = e.chats[0] if hasattr(e,"chats") else e
        else: chat = await self.client.get_entity(link)
        added = 0
        for u in members:
            if str(u.id) in self.bl: self.stats["skipped"]+=1; continue
            try:
                await self.client(InviteToChannelRequest(channel=chat, users=[u]))
                self.bl.add(str(u.id)); added+=1; self.stats["invited"]+=1
                self.log(f"+ {u.first_name or ''}")
                time.sleep(random.randint(8,20))
            except FloodWaitError as e:
                self.log(f"Wait {e.seconds}s"); time.sleep(e.seconds+5)
            except (UserPrivacyRestrictedError, PeerFloodError): self.stats["skipped"]+=1
            except: self.stats["skipped"]+=1
            if added>=30: break
        self._save_bl()
        return added

    async def cycle(self):
        self.running = True
        self.stats["last"] = datetime.now().strftime("%H:%M:%S")
        self.log("Cycle start")
        am = []
        for g in self.targets:
            m = await self.scrape(g); am.extend(m); time.sleep(random.randint(5,15))
        seen=set(); uniq=[]
        for m in am:
            if m.id not in seen: seen.add(m.id); uniq.append(m)
        random.shuffle(uniq)
        self.stats["scraped"] += len(uniq)
        tot=0
        for g in self.mygroups:
            n = await self.invite(uniq, g); tot+=n
        self.log(f"Done: +{tot}")
        self.running = False
        return tot

engine = GrowthEngine()

# ============================================================
# KEYWORDS
# ============================================================
KEYWORDS = {
    "閲戠嫍":"馃悤 *閲戠嫍棰戦亾*\nDev+娴佸姩鎬?鍚堢害涓夊厓鏍￠獙銆俓n馃憠 绉佽亰缇や富杩涚兢",
    "鏈熸潈":"馃幆 *ETH/BTC鏈熸潈*\n鍗栨柟60%APR | 鏈棩杞?00U鍗?000U+\n馃憠 绉佽亰缇や富棰嗘暀绋?,
    "鍚堢害":"馃搳 *涓変俊鍙风郴缁?\n璐圭巼+绋冲畾甯佹祦鍏?椴搁奔\n鑳滅巼78%\n馃憠 绉佽亰缇や富杩涚兢",
    "绌烘姇":"馃獋 *澶х┖鎶?\nMonad/Berachain/EigenLayer\n馃憠 绉佽亰缇や富棰嗘暀绋?,
    "濂楀埄":"馃挵 *绋冲畾甯佸鍒?\n骞村寲20-30%闆堕闄‐n馃憠 绉佽亰缇や富",
    "鏂版墜":"馃憢 娆㈣繋锛佸厛鐪嬪叆闂ㄦ寚鍗?鏃ユ姤\n馃憠 绉佽亰缇や富",
    "鏀惰垂":"鉁?鍏ㄩ儴鍏嶈垂","鍏嶈垂":"鉁?鍏ㄩ儴鍏嶈垂","鑱旂郴鏂瑰紡":"馃摡 绉佽亰缇や富",
    "鎬庝箞涔?:"馃挕 Binance/OKX 鈫?KYC 鈫?C2C涔癠SDT 鈫?涔板竵\n馃憠 绉佽亰棰嗗浘鏂囨暀绋?,
    "鍏ラ棬":"馃摉 鏂版墜鎵嬪唽锛氭敞鍐?鍑哄叆閲?鍚堢害/椋庢帶\n馃憠 绉佽亰缇や富鍏嶈垂棰?,
}

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cu = update.chat_member
    if cu.new_chat_member.status != ChatMemberStatus.MEMBER: return
    if cu.old_chat_member.status == ChatMemberStatus.MEMBER: return
    u = cu.new_chat_member.user; gn = update.effective_chat.title or "绀惧尯"
    await update.effective_chat.send_message(
        f"馃憢 娆㈣繋 [{u.first_name}](tg://user?id={u.id}) 鍔犲叆 *{gn}*锛乗n\n馃敟 閲戠嫍 | 馃搳 鍚堢害 | 馃幆 鏈熸潈 | 馃獋 绌烘姇\n鍏ㄩ儴鍏嶈垂锛岀鑱婄兢涓汇€?,
        parse_mode="Markdown", disable_web_page_preview=True)

async def keyword_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    if update.effective_chat.type == "private": return
    for kw, resp in KEYWORDS.items():
        if kw in update.message.text:
            await update.message.reply_text(resp, parse_mode="Markdown", disable_web_page_preview=True)
            return

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("涔惧潳鏈哄櫒浜哄湪绾匡紒/help")
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("*鍏抽敭璇嶏細*\n閲戠嫍 | 鏈熸潈 | 鍚堢害 | 绌烘姇 | 濂楀埄 | 鏂版墜", parse_mode="Markdown")

# ============================================================
# FLASK PANEL
# ============================================================
app = Flask(__name__)

@app.route("/")
def home(): return "QK Bot online"
@app.route("/health")
def health(): return "OK"

PANEL = """
<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>QK Panel</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui;background:#0a0a0a;color:#eee;padding:16px;max-width:600px;margin:0 auto}
h1{color:#0f0;margin-bottom:16px}
.card{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:16px;margin-bottom:16px}
.card h3{color:#0f0;margin-bottom:10px}
input,textarea{width:100%;padding:10px;margin:6px 0;background:#0a0a0a;color:#0f0;border:1px solid #333;border-radius:4px;font-size:14px}
textarea{height:60px;font-family:monospace;font-size:12px}
.btn{width:100%;padding:14px;margin:8px 0;border:none;border-radius:6px;font-size:16px;font-weight:bold;cursor:pointer;color:#000}
.g{background:#0a0}.r{background:#a00;color:#fff}.b{background:#224;color:#fff}
.s{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #222}
.log{background:#000;color:#0a0;padding:8px;border-radius:4px;font-size:11px;max-height:150px;overflow-y:auto;font-family:monospace;white-space:pre-wrap}
.step{background:#330;color:#ff0;padding:8px;border-radius:4px;margin:8px 0;font-size:14px}
</style></head><body>
<h1>QK Growth Panel</h1>
<div class="card">
  <h3>Status: {{step}}</h3>
  <div class="s"><span>Ready</span><span>{{ready}}</span></div>
  <div class="s"><span>Running</span><span>{{run}}</span></div>
  <div class="s"><span>Scraped</span><span>{{scraped}}</span></div>
  <div class="s"><span>Invited</span><span>{{invited}}</span></div>
  <div class="s"><span>Last</span><span>{{last}}</span></div>
</div>
<div id="login" class="card" style="display:{{show_login}}">
  <h3>Login (no API key needed!)</h3>
  <input id="phn" placeholder="Phone number (+86138...)">
  <button class="btn b" onclick="sendCode()">SEND CODE</button>
</div>
<div id="code_box" class="card" style="display:{{show_code}}">
  <h3>Enter Code</h3>
  <p style="color:#888;font-size:13px">Check your Telegram app for the verification code</p>
  <input id="code" placeholder="Verification code (e.g. 12345)">
  <button class="btn b" onclick="verifyCode()">VERIFY</button>
</div>
<div id="pwd_box" class="card" style="display:{{show_pwd}}">
  <h3>2FA Password</h3>
  <input id="pwd" type="password" placeholder="Your 2FA password">
  <button class="btn b" onclick="verifyPwd()">VERIFY</button>
</div>
<div class="card" style="display:{{show_groups}}">
  <h3>Groups</h3>
  <textarea id="tgs" placeholder="Target groups (one per line)&#10;https://t.me/crypto_group&#10;@btc_china">{{tgs}}</textarea>
  <textarea id="mgs" placeholder="Your groups&#10;https://t.me/your_group">{{mgs}}</textarea>
  <button class="btn b" onclick="save()">SAVE</button>
</div>
<div style="display:{{show_groups}}">
  <button class="btn g" onclick="start()">START GROWTH</button>
  <button class="btn r" onclick="stop()">STOP</button>
</div>
<div class="log">{{log}}</div>
<script>
var step="{{step}}";
async function api(u,b){
  let o={method:b?'POST':'GET'}
  if(b){o.headers={'Content-Type':'application/json'};o.body=JSON.stringify(b)}
  let r=await fetch(u,o);return await r.json()
}
async function sendCode(){
  let p=document.getElementById('phn').value;
  let r=await api('/g/send_code',{phone:p});alert(r.msg||r.error);location.reload()
}
async function verifyCode(){
  let c=document.getElementById('code').value;
  let r=await api('/g/verify_code',{code:c});
  if(r.need_password){alert('2FA required');location.reload()}
  else{alert(r.msg||r.error);location.reload()}
}
async function verifyPwd(){
  let p=document.getElementById('pwd').value;
  let r=await api('/g/verify_pwd',{password:p});alert(r.msg||r.error);location.reload()
}
async function save(){
  let d={targets:document.getElementById('tgs').value,mygroups:document.getElementById('mgs').value}
  let r=await api('/g/save',d);alert(r.msg);location.reload()
}
async function start(){let r=await api('/g/start');alert(r.msg||r.error)}
async function stop(){let r=await api('/g/stop');alert(r.msg)}
setInterval(async()=>{let r=await api('/g/status');document.getElementById('log').textContent=(r.log||[]).join('\n');document.querySelector('.card h3').textContent='Status: '+r.step},5000)
</script></body></html>
"""

@app.route("/panel")
def panel():
    s = engine.stats
    step = s["step"]
    return render_template_string(PANEL,
        step=step, ready="YES" if engine.ready else "NO",
        run="YES" if engine.running else "NO",
        scraped=s["scraped"], invited=s["invited"], last=s["last"],
        log="\n".join(s["log"]),
        show_login="block" if step=="waiting" else "none",
        show_code="block" if step=="code_sent" else "none",
        show_pwd="block" if step=="need_password" else "none",
        show_groups="block" if engine.ready else "none",
        tgs="\n".join(engine.targets), mgs="\n".join(engine.mygroups))

@app.route("/g/send_code", methods=["POST"])
async def g_send_code():
    d = request.json
    try:
        await engine.send_code(d["phone"])
        return {"msg": "Code sent! Check Telegram app."}
    except Exception as e:
        return {"error": str(e)[:200]}

@app.route("/g/verify_code", methods=["POST"])
async def g_verify_code():
    try:
        r = await engine.verify_code(request.json["code"])
        if r.get("need_password"): return r
        return {"msg": f"Logged in as {r['name']}!"}
    except Exception as e:
        return {"error": str(e)[:200]}

@app.route("/g/verify_pwd", methods=["POST"])
async def g_verify_pwd():
    try:
        r = await engine.verify_password(request.json["password"])
        return {"msg": f"Logged in as {r['name']}!"}
    except Exception as e:
        return {"error": str(e)[:200]}

@app.route("/g/save", methods=["POST"])
def g_save():
    d = request.json
    engine.targets = [l.strip() for l in d["targets"].split("\n") if l.strip()]
    engine.mygroups = [l.strip() for l in d["mygroups"].split("\n") if l.strip()]
    return {"msg": "Saved"}

@app.route("/g/start")
async def g_start():
    if not engine.ready: return {"error": "Login first"}
    if engine.running: return {"msg": "Running"}
    asyncio.ensure_future(engine.cycle())
    return {"msg": "Started"}

@app.route("/g/status")`ndef g_status():`n    return {"step": engine.stats["step"], "ready": engine.ready, "running": engine.running, "log": engine.stats["log"]}

@app.route("/g/stop")
def g_stop():
    engine.running = False
    return {"msg": "Stopped"}

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

def main():
    print("QK Bot starting...")
    threading.Thread(target=run_flask, daemon=True).start()
    print(f"Panel: http://0.0.0.0:{PORT}/panel")
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_cmd))
    bot_app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, keyword_reply))
    print("Bot running!")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()


