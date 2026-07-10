import asyncio,io, json, math, os, random, time
import re
from datetime import date
from typing import Optional

import base64

from astrbot.api.event import filter
from PIL import Image as PILImage, ImageDraw, ImageFont
from astrbot.core.star.star_tools import AiocqhttpMessageEvent, StarTools
from astrbot.api.all import Star, AstrBotConfig, Context, Plain, Image, Reply, logger
from .Tools import *

op = time.perf_counter()

class 每日老婆(Star):
    """每日重置，群组隔离"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.配对数据 = {}
        # { 群ID: { 用户ID: { '已配对': bool, '老婆ID': str, '老婆昵称': str, '分手次数': int,
        #                 '许愿次数': int, '强娶次数': int } } }
        self.冷静期 = config.冷静期 or 48
        self.随机匹配发言时间 = max(0, int(config.get("随机匹配发言时间", 0) or 0))
        self.黑白名单 = 解析黑白名单(config.黑白名单 or ['all'])

        self.冷静数据 = {}
        self.数据日期 = date.today()
        # { 群ID: { 用户ID: { 对方ID1: 结束时间戳, 对方ID2: 结束时间戳 } } }

        # 次数限制
        self.最大分手次数 = 3
        self.最大许愿次数 = 3  # 每日最大许愿次数
        self.最大强娶次数 = 3  # 每日最大强娶次数

        # 数据文件路径（相对于插件所在目录）
        self.数据目录 = StarTools.get_data_dir()
        self.数据文件 = os.path.join(self.数据目录, "daily_wife.json")

        # 加载持久化数据
        self.加载数据()
        # 清理过期的冷静期记录
        self.清理冷静期()

        ed = time.perf_counter()
        logger.info(f"今日老婆插件加载完成，耗时{(ed - op):.6f}秒")

    # ---------------------------- 持久化 ----------------------------
    def 保存数据(self):
        """保存配对数据和冷静数据到文件"""
        try:
            数据 = {
                "配对数据": self.配对数据,
                "冷静数据": self.冷静数据,
                "数据日期": str(self.数据日期)
            }
            with open(self.数据文件, "w", encoding="utf-8") as f:
                json.dump(数据, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

    def 加载数据(self):
        """从文件加载数据"""
        try:
            if os.path.exists(self.数据文件):
                with open(self.数据文件, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.配对数据 = data.get("配对数据", {})
                self.冷静数据 = data.get("冷静数据", {})
                数据日期 = data.get("数据日期", str(date.today()))
                self.数据日期 = date.fromisoformat(数据日期)
                logger.info("数据加载成功")
            else:
                logger.info("未找到数据文件，使用初始状态")
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            # 发生错误时使用空数据
            self.配对数据 = {}
            self.冷静数据 = {}
            self.数据日期 = date.today()

    def 清理冷静期(self):
        """清理过期的冷静期记录"""
        当前时间 = time.time()
        for 群ID, 用户信息 in self.冷静数据.copy().items():
            for 用户ID, 冷静信息 in 用户信息.copy().items():
                # 删除过期的对
                到期 = [mate for mate, 结束时间 in 冷静信息.items() if 结束时间 <= 当前时间]
                for i in 到期:
                    del 冷静信息[i]
                # 如果该用户没有冷静期记录了，删除该用户条目
                if not 冷静信息:
                    del 用户信息[用户ID]
            # 如果该群没有冷静期记录了，删除该群条目
            if not 用户信息:
                del self.冷静数据[群ID]
        # 如果有清理，保存数据
        self.保存数据()

    # ---------------------------- 辅助方法 ----------------------------
    def 获取配对信息(self, 群ID: str, 用户ID: str) -> dict:
        """获取用户的配对信息，若不存在则初始化"""
        if 群ID not in self.配对数据:
            self.配对数据[群ID] = {}
        if 用户ID not in self.配对数据[群ID]:
            self.配对数据[群ID][用户ID] = {
                '已配对': False,
                '老婆ID': '',
                '老婆昵称': '',
                '分手次数': 0,
                '许愿次数': 0,  # 新增：许愿次数
                '强娶次数': 0  # 新增：强娶次数
            }
        return self.配对数据[群ID][用户ID]

    def 配对(self, 群ID: str, 用户ID1: str, 用户ID2: str, 用户名字1: str, 用户名字2: str):
        """建立配对，需保证双方均未配对"""
        信息1 = self.获取配对信息(群ID, 用户ID1)
        信息2 = self.获取配对信息(群ID, 用户ID2)

        信息1['已配对'] = True
        信息1['老婆ID'] = 用户ID2
        信息1['老婆昵称'] = 用户名字2

        信息2['已配对'] = True
        信息2['老婆ID'] = 用户ID1
        信息2['老婆昵称'] = 用户名字1
        self.保存数据()  # 保存数据

    def 分手(self, 群ID: str, 用户ID: str, 被强娶: bool = False):
        """解除用户的配对，并解除对方配对，同时记录冷静期"""
        信息 = self.获取配对信息(群ID, 用户ID)
        if not 信息['已配对']:
            return
        配对的ID = 信息['老婆ID']
        配对的信息 = self.获取配对信息(群ID, 配对的ID)

        # 解除双方配对
        信息['已配对'] = False
        信息['老婆ID'] = ''
        信息['老婆昵称'] = ''
        信息['已锁定'] = False
        if not 被强娶:
            信息['分手次数'] += 1

        配对的信息['已配对'] = False
        配对的信息['老婆ID'] = ''
        配对的信息['老婆昵称'] = ''
        配对的信息['已锁定'] = False

        # 被强娶不记录冷静
        if not 被强娶:
            # 记录冷静期
            当前时间 = time.time()
            冷静结束时间 = 当前时间 + self.冷静期 * 3600

            # 确保冷静数据字典存在
            if 群ID not in self.冷静数据:
                self.冷静数据[群ID] = {}

            # 只记录单向冷静
            if 用户ID not in self.冷静数据[群ID]:
                self.冷静数据[群ID][用户ID] = {}
            self.冷静数据[群ID][用户ID][配对的ID] = 冷静结束时间

        self.保存数据()  # 保存数据

    def 锁定(self, 群ID: str, 用户ID: str):
        """锁定老婆"""
        信息 = self.获取配对信息(群ID, 用户ID)
        if not 信息['已配对']:
            return
        配对的ID = 信息['老婆ID']
        配对的信息 = self.获取配对信息(群ID, 配对的ID)
        信息['已锁定'] = True
        配对的信息['已锁定'] = True
        信息['待同意求婚'] = False
        配对的信息['待同意求婚'] = False
        self.保存数据()

    def 已配对(self, event: AiocqhttpMessageEvent) -> tuple[bool, dict]:
        """返回配对状态bool，配对信息dict"""
        信息 = self.获取配对信息(event.get_group_id(), event.get_sender_id())
        return 信息['已配对'], 信息

    @filter.command("今日老婆")
    async def 今日老婆指令(self, _):
        """发送今日老婆，获取随机老婆，无需指令前缀也可以"""

    @filter.command("查询老婆")
    async def 查询老婆指令(self, _):
        """发送查询老婆，查询今日老婆，无需指令前缀也可以"""

    @filter.command("我要分手")
    async def 我要分手指令(self, _):
        """发送我要分手，分手老婆，无需指令前缀也可以"""


    # ---------------------------- 核心功能 ----------------------------
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def 接收群消息(self, event: AiocqhttpMessageEvent):
        """接收群消息"""
        消息文本 = event.get_message_str()
        if not 消息文本:
            return
        if not 检测黑白名单(event.get_group_id(), self.黑白名单):
            return

        if 消息文本 == "查询老婆":
            self.隔天重置()
            已配对, 信息 = self.已配对(event)
            if 已配对:
                await 发送查询结果(event, 信息['老婆ID'], 信息['老婆昵称'], 信息.get("已锁定", False))
            else:
                await 发送回复文本(event, "❌ 你还没有老婆，请使用“今日老婆”抽取")
        elif 消息文本 == "今日老婆":
            self.隔天重置()
            await self.抽娶老婆(event)
        elif 消息文本 == "我要分手":
            self.隔天重置()
            已配对, 信息 = self.已配对(event)
            if not 已配对:
                await 发送回复文本(event, "❌ 你还没有老婆，无法分手")
                return
            分手次数 = 信息['分手次数']
            if 分手次数 >= self.最大分手次数:
                await 发送回复文本(event, f"❌ 你今天已经分手{self.最大分手次数}次了，不能再分手了！")
                return
            # 执行分手
            群ID = event.get_group_id()
            配对ID = 信息['老婆ID']
            配对名字 = 信息['老婆昵称']
            已锁定 = 信息.get('已锁定', False)
            self.分手(群ID, event.get_sender_id())
            if 已锁定:
                文本 = (f"[CQ:at,qq={event.get_sender_id()}]⁢ [CQ:at,qq={配对ID}]\n"
                        f"💔 你们离婚了\n⏳ {self.冷静期}小时内无法再匹配到一起\n"
                        f"剩余分手次数：{self.最大分手次数 - 信息['分手次数']}")
                event.stop_event()
                await 发送CQ码消息(event, 文本)
            else:
                await 发送回复文本(event,
                            f"💔 你已解除与{配对名字}（{配对ID}）的伴侣关系\n⏳ {self.冷静期}小时内无法再匹配到一起\n"
                            f"剩余分手次数：{self.最大分手次数 - 信息['分手次数']}")
        elif 消息文本 in ('愿意', '不愿意'):
            event.stop_event()
            await self.处理愿意(event)
        return

    async def 处理愿意(self, event: AiocqhttpMessageEvent):
        """处理愿意与不愿意"""
        消息链 = event.get_messages()
        text = event.get_message_str()
        if not isinstance(消息链[0], Reply):
            return
        回复文本 = 消息链[0].text
        pattern = r'（(\d+)）向你求婚啦，你愿意吗\n'
        match = re.search(pattern, 回复文本)
        if match:
            求婚方ID = match.group(1)
        else:
            await 发送回复文本(event, "❌ 请引用一条带求婚信息的消息")
            return
        # 发送者名字 = event.get_sender_name()
        发送者ID = event.get_sender_id()
        群ID = event.get_group_id()
        自己信息 = self.获取配对信息(群ID, 发送者ID)
        if not 自己信息.get('待同意求婚', False):
            await 发送回复文本(event, "❌ 你没有该求婚记录，可能该求婚不是你的，或已被处理或已过期")
            return
        求婚方信息 = self.获取配对信息(群ID, 求婚方ID)
        # 求婚方名字 = await 获取成员昵称(event, 求婚方ID)
        if text == '不愿意':
            文本 = f"[CQ:at,qq={求婚方ID}]⁢ 💔 很遗憾，对方不接受你的求婚申请"
            await 发送CQ码消息(event, 文本)
            自己信息['待同意求婚'] = False
            求婚方信息['待同意求婚'] = False
            self.保存数据()
            return
        self.锁定(群ID, 发送者ID)

        # 1. 下载头像（得到字节数据）
        sender_avatar = await 下载头像(f"https://q1.qlogo.cn/g?b=qq&nk={发送者ID}&s=640")
        proposer_avatar = await 下载头像(f"https://q1.qlogo.cn/g?b=qq&nk={求婚方ID}&s=640")

        # 2. 字节转 Base64 字符串
        sender_b64 = base64.b64encode(sender_avatar).decode('ascii')
        proposer_b64 = base64.b64encode(proposer_avatar).decode('ascii')

        # 3. 构造 CQ 图片码
        sender_img_cq = f"[CQ:image,file=base64://{sender_b64}]"
        proposer_img_cq = f"[CQ:image,file=base64://{proposer_b64}]"

        # 4. 原有的文字（保留你的零宽空格 \u200b）
        text = f"💒 结婚成功！\n恭喜 [CQ:at,qq={求婚方ID}]⁢  和 [CQ:at,qq={发送者ID}] 正式结婚啦！"

        full_message = f"{text}\n{sender_img_cq}🔗{proposer_img_cq}"

        # 6. 发送
        await 发送CQ码消息(event, full_message)


    async def 抽娶老婆(self, event: AiocqhttpMessageEvent):
        群ID = event.get_group_id()
        成员列表 = await 获取成员列表(event)
        if not 成员列表:
            await 发送回复文本(event, "😢 暂时找不到合适的人选（可能都已配对或处于冷静期）")
            return

        已配对, 配对信息 = self.已配对(event)
        if 已配对:
            await 发送查询结果(event, 配对信息['老婆ID'], 配对信息['老婆昵称'], 配对信息.get("已锁定", False))
            return

        随机匹配发言时间 = max(0, int(self.config.get("随机匹配发言时间", self.随机匹配发言时间) or 0))
        最后发言截止 = time.time() - 随机匹配发言时间 * 3600 if 随机匹配发言时间 > 0 else 0

        # 获取群内所有已配对用户的ID
        已配对用户 = set()
        if 群ID not in self.配对数据:
            self.配对数据[群ID] = {}
        else:
            for 用户ID, 用户信息 in self.配对数据[群ID].items():
                if 用户信息['已配对']:
                    已配对用户.add(用户ID)

        发送者ID = event.get_sender_id()
        # 过滤冷静期
        可娶列表 = []
        for i in 成员列表:
            成员ID = str(i['user_id'])
            if 最后发言截止 and i.get('last_sent_time', 0) < 最后发言截止:
                continue
            if 成员ID in 已配对用户:
                continue
            # 检查冷静期
            if self.正在冷却(群ID, 发送者ID, 成员ID):
                continue
            可娶列表.append(i)

        if not 可娶列表:
            await 发送回复文本(event, "😢 未找不到合适的人选（可能都已配对或处于冷静期）")
            return

        # 随机选择
        老婆信息 = random.choice(可娶列表)
        老婆ID = str(老婆信息['user_id'])
        老婆名字 = 老婆信息['card'] or 老婆信息['nickname']
        发送者名字 = event.get_sender_name()

        # 建立配对
        self.配对(群ID, 发送者ID, 老婆ID, 发送者名字, 老婆名字)

        # 发送消息
        消息链 = [
            Reply(id=event.message_obj.message_id),
            Plain(f"恭喜{发送者名字}（{发送者ID}），\n"
                  f"▻ 成功娶到：{老婆名字}（{老婆ID}）\n"
                  "▻ 对方头像：")
        ]
        图片数据 = await 下载头像(f"https://q1.qlogo.cn/g?b=qq&nk={老婆ID}&s=640")
        if 图片数据:
            消息链.append(Image.fromBytes(图片数据))
        else:
            消息链.append(Plain("[头像加载失败]"))
        消息链.append(Plain("\n💎 好好对待TA哦，\n使用 查询老婆 查看详细信息\n提示，可使用求婚指令防止伴侣被强娶：/求婚 @对方"))
        await event.send(event.chain_result(消息链))

    # ---------------------------- 指令 ----------------------------
    @filter.command("许愿")
    async def 许愿指令(self, event: AiocqhttpMessageEvent):
        """直接指定老婆"""
        if not 检测黑白名单(event.get_group_id(), self.黑白名单):
            return
        self.隔天重置()
        已配对, 发送者信息 = self.已配对(event)
        if 已配对:
            await 发送回复文本(event, "❌ 你已经有伴侣了……许愿将不可用")
            return

        # 检查许愿次数
        if 发送者信息['许愿次数'] >= self.最大许愿次数:
            await 发送回复文本(event, f"❌ 你今天已经许愿 {self.最大许愿次数} 次了，不能再许愿了")
            return

        艾特信息 = 获取艾特用户(event)
        if not 艾特信息:
            await 发送回复文本(event, "请指定许愿对象哦~")
            return
        被艾特方ID, 被艾特方名字 = 艾特信息

        群ID = event.get_group_id()
        发送者ID = event.get_sender_id()

        # 检查对方是否已配对
        艾特方信息 = self.获取配对信息(群ID, 被艾特方ID)
        if 艾特方信息.get("已锁定", False):
            await 发送回复文本(event, f"❌ {被艾特方名字}已经结婚啦，换个人试试吧")
            return
        if 艾特方信息['已配对']:
            await 发送回复文本(event, f"❌ {被艾特方名字}已经名花有主了，不能许愿，可以使用强娶指令：/强娶 @对方")
            return

        # 检查冷静期
        if self.正在冷却(群ID, 发送者ID, 被艾特方ID):
            await 发送回复文本(event, f"❌ 你与 {被艾特方名字} 处于冷静期中，无法许愿")
            return

        # 通过所有检查，增加许愿次数并建立配对
        发送者信息['许愿次数'] += 1
        发送者名字 = event.get_sender_name()
        self.配对(群ID, 发送者ID, 被艾特方ID, 发送者名字, 被艾特方名字)

        消息链 = [
            Reply(id=event.message_obj.message_id),
            Plain(f"✨ 许愿成功！系统已为你指定：{被艾特方名字}（{被艾特方ID}）作为伴侣\n对方头像：")]
        图片数据 = await 下载头像(f"https://q1.qlogo.cn/g?b=qq&nk={被艾特方ID}&s=640")
        if 图片数据:
            消息链.append(Image.fromBytes(图片数据))
        else:
            消息链.append(Plain("[头像加载失败]"))
        消息链.append(Plain(f"\n💎 好好对待TA哦\n剩余许愿次数：{self.最大许愿次数 - 发送者信息['许愿次数']}次"))
        yield event.chain_result(消息链)

    @filter.command("强娶")
    async def 强娶指令(self, event: AiocqhttpMessageEvent):
        """强娶已被别人娶走的老婆，若别人未娶走，则提示使用许愿指令"""
        if not 检测黑白名单(event.get_group_id(), self.黑白名单):
            return
        self.隔天重置()
        if not (艾特信息 := 获取艾特用户(event)):
            await 发送回复文本(event, "请指定要强娶的对象（艾特）")
            return
        被艾特方ID, 被艾特方名字 = 艾特信息

        群ID = event.get_group_id()
        发送者ID = event.get_sender_id()

        # 检查自己是否已配对
        自己已配对, 自己信息 = self.已配对(event)
        if 自己已配对:
            await 发送回复文本(event, "❌ 你已经有伴侣了")
            return

        # 检查强娶次数
        if 自己信息['强娶次数'] >= self.最大强娶次数:
            await 发送回复文本(event, f"❌ 你今天已经强娶 {self.最大强娶次数} 次了，不能再强娶了")
            return

        # 获取对方配对信息
        被艾特方信息 = self.获取配对信息(群ID, 被艾特方ID)
        if not 被艾特方信息['已配对']:
            await 发送回复文本(event, f"❌ {被艾特方名字}还没有伴侣，请使用“许愿”指令：/许愿 @对方")
            return
        if 被艾特方信息.get("已锁定", False):
            await 发送回复文本(event, f"❌ {被艾特方名字}已经结婚啦，换个人试试吧")
            return

        # 检查冷静期
        if self.正在冷却(群ID, 发送者ID, 被艾特方ID):
            await 发送回复文本(event, f"❌ 你与 {被艾特方名字} 处于冷静期中，无法强娶")
            return

        # 对方有伴侣，强娶
        被艾特方原配ID = 被艾特方信息['老婆ID']
        被艾特方原配名字 = 被艾特方信息['老婆昵称']

        # 解除原配双方配对，不增加分手次数
        self.分手(群ID, 被艾特方ID, True)

        # 增加强娶次数并建立新配对
        自己信息['强娶次数'] += 1
        发送者昵称 = event.get_sender_name()
        self.配对(群ID, 发送者ID, 被艾特方ID, 发送者昵称, 被艾特方名字)

        消息链 = [
            Reply(id=event.message_obj.message_id),
            Plain(
                f"🐮 强娶成功！\n系统已为你牛走了{被艾特方原配名字}（{被艾特方原配ID}）的{被艾特方名字}（{被艾特方ID}）\n作为伴侣\n对方头像：")
        ]
        图片数据 = await 下载头像(f"https://q1.qlogo.cn/g?b=qq&nk={被艾特方ID}&s=640")
        if 图片数据:
            消息链.append(Image.fromBytes(图片数据))
        else:
            消息链.append(Plain("[头像加载失败]"))
        消息链.append(Plain(f"\n💎 好好对待TA哦\n剩余许愿次数：{self.最大强娶次数 - 自己信息['强娶次数']}次\n提示，可使用求婚指令防止伴侣被强娶：/求婚 @对方"))
        yield event.chain_result(消息链)

    @filter.command("求婚", alias={"锁定"})
    async def 求婚指令(self, event: AiocqhttpMessageEvent):
        """求婚锁定老婆，让别人无法强娶走，需对方同意"""
        if not 检测黑白名单(event.get_group_id(), self.黑白名单):
            return
        self.隔天重置()
        if not (艾特信息 := 获取艾特用户(event)):
            await 发送回复文本(event, "请指定要求婚的对象（艾特）")
            return
        被艾特方ID, 被艾特方名字 = 艾特信息
        自己ID, 自己名字 = event.get_sender_id(), event.get_sender_name()
        群ID = event.get_group_id()
        自己信息 = self.获取配对信息(群ID, 自己ID)
        if not 自己信息['已配对']:
            await 发送回复文本(event, "❌ 对方还不是你的伴侣，请先使用`/今日老婆`或`/许愿 @对方`或`/强娶 @对方`与ta成为伴侣哦~")
            return
        老婆ID = 自己信息['老婆ID']
        老婆信息 = self.获取配对信息(群ID, 老婆ID)
        if 老婆信息.get("已锁定", False):
            await 发送回复文本(event, "❌ 对方已经被娶走啦，换个人试试吧")
            return
        if 老婆ID != 被艾特方ID:
            await 发送回复文本(event, "❌ 对方还不是你的伴侣，请先使用`/今日老婆`或`/许愿 @对方`或`/强娶 @对方`与ta成为伴侣哦~")
            return
        # 1. 下载自己的头像（字节数据）
        自己头像_bytes = await 下载头像(f"https://q1.qlogo.cn/g?b=qq&nk={自己ID}&s=640")

        # 2. 字节转 Base64 字符串
        自己头像_b64 = base64.b64encode(自己头像_bytes).decode('ascii')

        # 4. 原有文本（保留零宽空格和换行）
        文本 = f"[CQ:at,qq={被艾特方ID}]\n{自己名字}（{自己ID}）向你求婚啦，你愿意吗\n对方头像：\n[CQ:image,file=base64://{自己头像_b64}]请引用回复此条信息发送 愿意 或 不愿意"

        # 6. 发送
        await 发送CQ码消息(event, 文本)
        #使用⁢防止被strip()
        自己信息['待同意求婚'] = True
        老婆信息['待同意求婚'] = True
        self.保存数据()


    @filter.command("老婆次数")
    async def 老婆次数指令(self, event: AiocqhttpMessageEvent):
        """查询当前用户今日各项次数和剩余次数"""
        if not 检测黑白名单(event.get_group_id(), self.黑白名单):
            return
        self.隔天重置()
        信息 = self.获取配对信息(event.get_group_id(), event.get_sender_id())
        用户ID = event.get_sender_id()
        用户名 = event.get_sender_name()
        分手次数 = 信息.get('分手次数', 0)
        许愿次数 = 信息.get('许愿次数', 0)
        强娶次数 = 信息.get('强娶次数', 0)
        文本 = (
            f"【{用户名}（{用户ID}）的今日老婆次数】\n"
            f"分手：已用 {分手次数}/{self.最大分手次数}，剩余 {max(0, self.最大分手次数 - 分手次数)} 次\n"
            f"许愿：已用 {许愿次数}/{self.最大许愿次数}，剩余 {max(0, self.最大许愿次数 - 许愿次数)} 次\n"
            f"强娶：已用 {强娶次数}/{self.最大强娶次数}，剩余 {max(0, self.最大强娶次数 - 强娶次数)} 次"
        )
        await 发送回复文本(event, 文本)


    @filter.command("老婆菜单")
    async def 老婆菜单指令(self, event: AiocqhttpMessageEvent):
        if not 检测黑白名单(event.get_group_id(), self.黑白名单):
            return
        菜单 = (
            "【今日老婆插件菜单】\n"
            "今日老婆 - 随机抽取一位群友作为老婆\n"
            "查询老婆 - 查看当前伴侣信息\n"
            f"我要分手 - 与当前伴侣分手（最多{self.最大分手次数}次）\n"
            f"/许愿 @用户 - 指定某位群友作为伴侣（需对方单身，每日最多{self.最大许愿次数}次）\n"
            f"/强娶 @用户 - 强娶已有伴侣的群友（需对方已有伴侣，每日最多{self.最大强娶次数}次）\n"
            "/老婆次数 - 查询今日分手、许愿、强娶次数和剩余次数\n"
            "/老婆菜单 - 显示本菜单"
        )
        yield event.plain_result(菜单)

    @filter.command("重置配对")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def 重置配对指令(self, event: AiocqhttpMessageEvent):
        群ID = event.get_group_id()
        if not 群ID:
            return
        if 群ID in self.配对数据:
            del self.配对数据[群ID]
            self.保存数据()  # 保存数据
            yield event.plain_result("✅ 已重置本群所有配对数据")
        else:
            yield event.plain_result("本群暂无配对数据，无需重置")

    @filter.command("重置冷静")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def 重置冷静指令(self, event: AiocqhttpMessageEvent):
        if event.get_group_id() in self.冷静数据:
            del self.冷静数据[event.get_group_id()]
            self.保存数据()
            yield event.plain_result("✅ 已重置本群所有冷却数据")
        else:
            yield event.plain_result("本群暂无冷却数据，无需重置")

    def 隔天重置(self):
        """每天重置所有配对数据"""
        if date.today() != self.数据日期:
            self.数据日期 = date.today()
            self.配对数据.clear()
            self.清理冷静期()

    def 正在冷却(self, 群ID: str, 用户1: str, 用户2: str) -> bool:
        """检查两个用户之间是否存在未过期的冷静期"""
        当前时间 = time.time()
        群冷却信息 = self.冷静数据.get(群ID, {})
        # 检查 用户1 -> 用户2 的记录
        if 用户1 in 群冷却信息 and 用户2 in 群冷却信息[用户1]:
            if 当前时间 < 群冷却信息[用户1][用户2]:
                return True
        # 检查 用户2 -> 用户1 的记录
        if 用户2 in 群冷却信息 and 用户1 in 群冷却信息[用户2]:
            if 当前时间 < 群冷却信息[用户2][用户1]:
                return True
        return False

    @filter.command("老婆关系图")
    async def 老婆关系图指令(self, event: AiocqhttpMessageEvent):
        """生成本群老婆关系图"""
        if not 检测黑白名单(event.get_group_id(), self.黑白名单):
            return
        self.隔天重置()
        群ID = event.get_group_id()
        配对数据 = self.配对数据.get(群ID, {})

        # 收集所有已配对的用户
        paired_users = {uid for uid, info in 配对数据.items() if info.get('已配对', False)}
        if not paired_users:
            await 发送回复文本(event, "本群暂无任何配对关系，无法生成关系图")
            return

        # 构建节点列表，直接从配对数据获取名字
        nodes = []
        for uid in paired_users:
            info = 配对数据[uid]
            mate_id = info.get('老婆ID')
            if not mate_id or mate_id not in 配对数据:
                # 异常情况，使用占位符
                name = f"用户{uid}"
            else:
                # 自己的名字存储在对方的信息中
                mate_info = 配对数据[mate_id]
                name = mate_info.get('老婆昵称', f"用户{uid}")
            nodes.append({'uid': uid, 'name': name, 'url': f"https://q1.qlogo.cn/g?b=qq&nk={uid}&s=640"})

        # 构建关系边
        edges = []
        for uid, info in 配对数据.items():
            if info.get('已配对'):
                mate_id = info.get('老婆ID')
                if uid in paired_users and mate_id in paired_users:
                    edges.append((uid, mate_id))
        edges = list(set((min(a, b), max(a, b)) for a, b in edges))

        # 并行下载头像
        async def download_avatar(url):
            data = await 下载头像(url)
            if data:
                try:
                    return PILImage.open(io.BytesIO(data)).convert('RGB')
                except Exception as e:
                    logger.warning(f"头像转换失败: {e}")
            return None

        tasks = [download_avatar(node['url']) for node in nodes]
        images = await asyncio.gather(*tasks)
        for i, img in enumerate(images):
            nodes[i]['img'] = img if img else None

        # 生成图片
        img_bytes = await self._draw_graph(nodes, edges)
        if img_bytes:
            yield event.chain_result([Image.fromBytes(img_bytes)])
        else:
            yield event.plain_result("生成关系图失败")

    async def _draw_graph(self, nodes: list, edges: list) -> Optional[bytes]:
        """绘制关系图，返回图片二进制数据"""
        width, height = 1600, 1200
        img = PILImage.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)

        avatar_size = 100
        字体路径 = os.path.join(os.path.dirname(__file__), "ldm.ttf")
        font = None
        if os.path.exists(字体路径):
            try:
                # 直接用 FreeTypeFont，不进入全局缓存
                font = ImageFont.FreeTypeFont(字体路径, 20)
            except Exception as e:
                logger.warning(f"加载字体失败: {e}，将使用默认字体")
        font = font or ImageFont.load_default()
        radius = min(width, height) * 0.35
        center_x, center_y = width // 2, height // 2

        # 计算节点位置（均匀分布在圆上）
        positions = []
        n = len(nodes)
        for i, node in enumerate(nodes):
            angle = 2 * math.pi * i / n
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            positions.append((x, y))

        # 绘制连线
        for a, b in edges:
            ia = next((i for i, node in enumerate(nodes) if node['uid'] == a), None)
            ib = next((i for i, node in enumerate(nodes) if node['uid'] == b), None)
            if ia is not None and ib is not None:
                x1, y1 = positions[ia]
                x2, y2 = positions[ib]
                draw.line((x1, y1, x2, y2), fill='gray', width=3)

        # 绘制头像和文本
        for i, node in enumerate(nodes):
            x, y = positions[i]
            left = x - avatar_size // 2
            top = y - avatar_size // 2

            # 绘制头像
            if node['img']:
                img_avatar = node['img'].resize((avatar_size, avatar_size), PILImage.LANCZOS)
                mask = PILImage.new('L', (avatar_size, avatar_size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                img_avatar.putalpha(mask)
                img.paste(img_avatar, (int(left), int(top)), img_avatar)
            else:
                draw.rectangle((left, top, left + avatar_size, top + avatar_size), outline='gray', width=2)
                draw.text((left + avatar_size // 2, top + avatar_size // 2), "?", fill='gray', anchor='mm')

            # 绘制文本（名字和ID），手动居中
            name_text = f"{node['name']}({node['uid']})"
            bbox = draw.textbbox((0, 0), name_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_x = x - text_width // 2
            text_y = y + avatar_size // 2 + 10
            draw.text((text_x, text_y), name_text, fill='black', font=font)

        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()