__all__ = ["获取成员列表", "获取艾特用户", "发送回复文本", "下载头像", "发送查询结果", "解析黑白名单", "检测黑白名单", "获取成员昵称", "发送CQ码消息"]

import asyncio, aiohttp
from astrbot.api.all import At, Plain, Image, Reply, logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

async def 获取成员昵称(event: AiocqhttpMessageEvent, 用户ID) -> str:
    """获取当前群该成员的昵称"""
    信息 = await event.bot.get_group_member_info(
        group_id=int(event.get_group_id()),
        user_id=int(event.get_sender_id()),
        no_cache=True
    )
    return 信息['card'] or 信息['nickname']

async def 发送CQ码消息(event: AiocqhttpMessageEvent, text:str):
    """发送CQ码消息"""
    await event.bot.send_msg(
        user_id=int(event.get_sender_id()) or None,
        group_id=int(event.get_group_id()) or None,
        message=text,
    )

async def 获取成员列表(event: AiocqhttpMessageEvent) -> list[dict[str,str]]:
    """
    # 请每次都获取最新信息

    list[dict]：
    [
    {
    'user_id': QQ号（int）,
    'nickname': 原昵称（str）,
    'card': 群昵称（str）（可能未设置为空""）,
    'is_robot': 是否是机器人账号（bool）,
    },
    ...
    ]
    """

    成员列表: list[dict] = await event.bot.get_group_member_list(group_id=int(event.get_group_id()))
    # 发送者ID和机器人自身ID
    sid = (event.get_sender_id(), event.get_self_id())
    # 移除发送者和自己和机器人账号
    新成员列表 = [ {"user_id": str(i["user_id"]), "nickname": i["nickname"], "card": i["card"], "last_sent_time": i.get("last_sent_time", 0)}
                for i in 成员列表
                if (not i["is_robot"]) and (str(i["user_id"]) not in sid)]

    return 新成员列表

async def 下载头像(url: str, timeout: int = 20) -> bytes|None:
    """异步下载图片，返回图片字节数据，失败返回 None"""
    try:
        async with aiohttp.ClientSession() as 会话:
            async with 会话.get(url, timeout=timeout) as 响应:
                if 响应.status == 200:
                    return await 响应.read()
                else:
                    logger.warning(f"下载图片失败，状态码: {响应.status}, Content-Type: {响应.headers.get('Content-Type')}")
                    return None
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.warning(f"下载图片网络异常: {e}")
        return None
    except Exception as e:
        logger.error(f"下载图片未知错误: {e}")
        return None


async def 发送查询结果(event: AiocqhttpMessageEvent, 老婆qq, 老婆昵称, 已结婚: bool = False, 显示头像:bool=True):
    消息链 = [
        Reply(id=event.message_obj.message_id),
        Plain(f"💞 你的今日老婆是：{老婆昵称}（{老婆qq}）\n对方头像：")
        if 已结婚 else
        Plain(f"💖 你的今日伴侣是：{老婆昵称}（{老婆qq}）\n对方头像：")
    ]

    if 显示头像:
        图片数据 = await 下载头像(f"https://q1.qlogo.cn/g?b=qq&nk={老婆qq}&s=640")
        if 图片数据:
            消息链.append(Image.fromBytes(图片数据))
        else:
            消息链.append(Plain("\n[头像获取失败]"))

    # 此文本最后添加
    消息链.append(Plain("\n❤️ 你们已经结婚啦") if 已结婚 else Plain("\n💎 好好对待TA哦"))

    # 发送消息
    await event.send(event.chain_result(消息链))

async def 发送回复文本(event: AiocqhttpMessageEvent, 文本: str):
    await event.send(event.chain_result([Reply(id=event.message_obj.message_id),Plain(文本)]))

def 获取艾特用户(event: AiocqhttpMessageEvent) -> tuple[str, str] | None:
    """返回qq，昵称 or None"""
    for seg in event.get_messages():
        if isinstance(seg, At):
            if str(seg.qq) in (event.get_self_id(), event.get_sender_id()):
                continue
            return str(seg.qq), seg.name
    return None


def 解析黑白名单(原列表: list[str]|set[str], 通配符=None) -> tuple[set[str], set[str]]:
    """
    解析原始访问控制列表，返回标准化的白名单和黑名单。

    Args:
        原列表: 原始字符串列表，如 ["all", "/admin", "user", "/all"]
        通配符: 匹配的通配符，当匹配到通配符时，列表类型使用第一个
    Returns:
        tuple[set, set]: 顺序为黑名单，白名单
    """
    if 通配符 is None:
        通配符 = ['*', 'all']
    # 跳过非字符串和空字符串
    原列表 = [ i.strip() for i in 原列表 if isinstance(i, str) and i.strip() ]
    黑名单 = []
    白名单 = []
    if 通配符:
        if isinstance(通配符, (list, tuple)):
            t = 通配符[0]
            tl = 通配符
        elif isinstance(通配符, str):
            t = 通配符
            tl = [通配符]
        else:
            raise ValueError("通配符类型错误，应为list or str")
    else:
        tl = []

    for i in 原列表:

        # 黑名单判断（以 / 开头）
        if i.startswith('/'):
            i = i[1:]  # 去掉前缀 /
            if not i:
                continue
            if i in tl:
                return {t}, set()
            黑名单.append(i)
        else:
            白名单.append(i)

    # 规范化白名单
    if any(i in 白名单 for i in tl):
        白名单 = [t]

    白名单 = [ i for i in 白名单 if i not in 黑名单]

    return set(黑名单), set(白名单)

def 检测黑白名单(值:str, 黑白名单:tuple[set[str], set[str]], 通配符=None) -> bool:
    if 通配符 is None:
        通配符 = ['*', 'all']
    黑名单 = 黑白名单[0]
    白名单 = 黑白名单[1]
    if 通配符:
        if isinstance(通配符, (list, tuple)):
            t = 通配符[0]
        elif isinstance(通配符, str):
            t = 通配符
        else:
            raise ValueError("通配符类型错误，应为list or str")
    else:
        t = ''
    if not (黑名单 or 白名单):
        return False
    if 黑名单:
        if t in 黑名单:
            return False
        if 值 in 黑名单:
            return False
    if 白名单:
        if t in 白名单:
            return True
        if 值 in 白名单:
            return True
    # 规范使用通配符，为空则拒绝
    return False