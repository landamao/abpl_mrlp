__all__ = ["获取成员列表", "获取艾特用户", "发送回复文本", "下载头像", "发送查询结果"]

import asyncio, aiohttp
from astrbot.api.all import At, Plain, Image, Reply, logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

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
    新成员列表 = [ {"user_id": str(i["user_id"]), "nickname": i["nickname"], "card": i["card"]}
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


async def 发送查询结果(event: AiocqhttpMessageEvent, 老婆qq, 老婆昵称, 显示头像:bool=True):
    消息链 = [
        Reply(id=event.message_obj.message_id),
        Plain(f"💖 你的今日伴侣是：{老婆昵称}（{老婆qq}）\n对方头像：")
    ]

    if 显示头像:
        图片数据 = await 下载头像(f"https://q1.qlogo.cn/g?b=qq&nk={老婆qq}&s=640")
        if 图片数据:
            消息链.append(Image.fromBytes(图片数据))
        else:
            消息链.append(Plain("\n[头像获取失败]"))

    # 此文本最后添加
    消息链.append(Plain("\n💎 好好对待TA哦"))

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