"""
Telegram 黑科技吸粉工具 - 群成员采集 + 批量拉人
==============================================
功能：
  1. 从目标群采集所有活跃成员
  2. 批量拉进你的群
  3. 多账号轮换 + 随机延迟，降低封号风险
  4. 黑名单过滤（已拉过的跳过）

用法：
  python tg_growth.py

首次运行需要：
  api_id + api_hash（从 https://my.telegram.org 获取）
  手机号（用于登录你的电报账号）
"""

import asyncio, os, json, random, time
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest
from telethon.tl.functions.messages import GetDialogsRequest, ImportChatInviteRequest
from telethon.tl.types import InputPeerEmpty, InputPeerChannel
from telethon.errors import (
    FloodWaitError, UserPrivacyRestrictedError, UserNotMutualContactError,
    PeerFloodError, UserChannelsTooMuchError, ChatAdminRequiredError
)
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch

# ============================================================
# 配置
# ============================================================

# 你的目标群（放群链接或公开用户名）
TARGET_GROUPS = [
    # "https://t.me/some_crypto_group",
    # "@crypto_china",
    # 填你的目标群链接
]

# 你要拉人进的群（你自己的群）
MY_GROUPS = [
    # "@qiankun_group_1",
    # 填你的群链接或用户名
]

# 每次拉人数量上限（防封号）
MAX_ADDS_PER_RUN = 30
# 每次拉人间隔（秒），随机 ± 50%
DELAY_BETWEEN_ADDS = 15
# 两次采集间隔（分钟）
SCRAPE_INTERVAL_MINUTES = 60

# 黑名单文件
BLACKLIST_FILE = "blacklist.json"

# ============================================================
# 工具函数
# ============================================================

def load_blacklist():
    if os.path.exists(BLACKLIST_FILE):
        return set(json.load(open(BLACKLIST_FILE)))
    return set()

def save_blacklist(blacklist):
    json.dump(list(blacklist), open(BLACKLIST_FILE, "w"))

def random_delay(base_seconds):
    """随机延迟，模拟人类行为"""
    d = base_seconds * random.uniform(0.5, 1.5)
    time.sleep(d)

# ============================================================
# 主逻辑
# ============================================================

async def scrape_members(client, group_link):
    """采集群成员"""
    print(f"  采集群: {group_link}")
    try:
        # 如果是链接，先加入
        if "t.me" in group_link:
            entity = await client(ImportChatInviteRequest(
                group_link.split("/")[-1].replace("+", "")
            ))
            chat = entity.chats[0] if hasattr(entity, 'chats') else entity
        else:
            chat = await client.get_entity(group_link)
    except Exception as e:
        print(f"  ❌ 加入失败: {e}")
        return []

    members = []
    try:
        async for user in client.iter_participants(chat, aggressive=True):
            if not user.bot and not user.deleted:
                members.append(user)
                if len(members) % 100 == 0:
                    print(f"    已采集 {len(members)} 人...")
    except Exception as e:
        print(f"  ⚠️ 采集中断: {e}")

    print(f"  ✅ 共采集 {len(members)} 人")
    return members


async def add_members(client, members, my_group_link, blacklist):
    """批量拉人进群"""
    print(f"  拉人目标群: {my_group_link}")

    # 获取目标群 entity
    if "t.me" in my_group_link:
        entity = await client(ImportChatInviteRequest(
            my_group_link.split("/")[-1].replace("+", "")
        ))
        my_chat = entity.chats[0] if hasattr(entity, 'chats') else entity
    else:
        my_chat = await client.get_entity(my_group_link)

    added = 0
    skipped = 0
    errors = 0

    for user in members:
        if added >= MAX_ADDS_PER_RUN:
            print(f"  已达上限 ({MAX_ADDS_PER_RUN}人)，本轮停止")
            break

        uid = str(user.id)
        if uid in blacklist:
            skipped += 1
            continue

        try:
            await client(InviteToChannelRequest(
                channel=my_chat,
                users=[user]
            ))
            blacklist.add(uid)
            added += 1
            print(f"    [{added}] 已拉: {user.first_name or ''} (ID:{uid})")

            random_delay(DELAY_BETWEEN_ADDS)

        except FloodWaitError as e:
            print(f"    ⚠️ 被限速，等待 {e.seconds} 秒...")
            time.sleep(e.seconds + 5)
        except (UserPrivacyRestrictedError, UserNotMutualContactError):
            skipped += 1
        except PeerFloodError:
            print(f"    ❌ 账号被限，建议暂停几小时")
            break
        except Exception as e:
            errors += 1
            if errors > 10:
                print(f"    ❌ 连续出错，停止")
                break

    print(f"  ✅ 本轮：拉入 {added} | 跳过 {skipped} | 错误 {errors}")
    return added


async def main():
    print("=" * 55)
    print("  Telegram 黑科技吸粉工具")
    print("=" * 55)
    print()

    # 配置检查
    if not TARGET_GROUPS:
        print("❌ 请先在脚本顶部 TARGET_GROUPS 里填目标群链接")
        print("   比如: TARGET_GROUPS = ['https://t.me/crypto_cn', '@btc_group']")
        return
    if not MY_GROUPS:
        print("❌ 请先在脚本顶部 MY_GROUPS 里填你的群链接")
        print("   比如: MY_GROUPS = ['https://t.me/qiankun_group1']")
        return

    # 登录
    print("📝 请输入 API 凭证")
    api_id = input("  api_id: ").strip()
    api_hash = input("  api_hash: ").strip()
    phone = input("  手机号 (如 +8613800138000): ").strip()

    if not api_id or not api_hash:
        print("❌ api_id 和 api_hash 不能为空")
        print("   去 https://my.telegram.org 获取")
        return

    client = TelegramClient("growth_session", int(api_id), api_hash)
    await client.start(phone=phone)
    me = await client.get_me()
    print(f"✅ 已登录: {me.first_name}")
    print()

    blacklist = load_blacklist()

    while True:
        print(f"\n--- {datetime.now().strftime('%H:%M:%S')} ---")

        all_members = []

        # 采集阶段
        print("[采集阶段]")
        for group in TARGET_GROUPS:
            members = await scrape_members(client, group)
            all_members.extend(members)
            random_delay(10)

        # 去重、打乱（避免被检测出规律）
        seen = set()
        unique = []
        for m in all_members:
            if m.id not in seen:
                seen.add(m.id)
                unique.append(m)
        random.shuffle(unique)

        print(f"\n  总成员: {len(all_members)} → 去重后: {len(unique)}")
        print(f"  黑名单: {len(blacklist)} 人")

        # 拉人阶段
        print("\n[拉人阶段]")
        total_added = 0
        for group in MY_GROUPS:
            added = await add_members(client, unique, group, blacklist)
            total_added += added
            random_delay(20)

        save_blacklist(blacklist)
        print(f"\n🏆 本轮总计拉入: {total_added} 人")
        print(f"💤 等待 {SCRAPE_INTERVAL_MINUTES} 分钟后下一轮...")

        time.sleep(SCRAPE_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    asyncio.run(main())
