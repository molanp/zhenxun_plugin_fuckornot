import base64
from pathlib import Path
from typing import Literal

from nonebot.exception import IgnoredException
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    At,
    Image,
    Option,
    Reply,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_alconna.uniseg.tools import reply_fetch
from nonebot_plugin_htmlrender import template_to_pic
import ujson

from zhenxun.configs.config import Config
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.withdraw_manage import WithdrawManager

from .prompt import get_prompt

__plugin_meta__ = PluginMetadata(
    name="上不上",
    description="上不上AI评分系统",
    usage="""
    上传图片，让AI来评判它的可操性
        上 [图片]
    或 **引用一张图片**
    也可以通过附加参数来指定风格
    简短模式: 短平快，1-2句，够味
    详细模式:细嗦3+句，够劲
    小说模式:全程15+句教你咋上，纯硬核
    例如:
        上 [图片] --m 简短模式
        上 [图片] --m 详细模式
        上 [图片] --m 小说模式
    """.strip(),
    extra=PluginExtraData(
        author="molanp",
        version="1.1",
        menu_type="群内小游戏",
        configs=[
            RegisterConfig(
                key="base_url",
                value="https://generativelanguage.googleapis.com",
                help="Gemini API根地址(镜像: https://api-proxy.me/gemini)",
                default_value="https://generativelanguage.googleapis.com",
            ),
            RegisterConfig(
                key="api_key",
                value=None,
                help="Gemini API密钥",
            ),
            RegisterConfig(
                key="model",
                value="gemini-2.5-flash-preview-05-20",
                help="Gemini AI 模型名称",
            ),
            RegisterConfig(
                key="withdraw_time", value=30, help="撤回时间,单位秒, 0为不撤回"
            ),
        ],
    ).dict(),
)

fuck = on_alconna(
    Alconna(
        "上",
        Args["image?", Image | At],
        Option(
            "--m",
            Args["mode", Literal["简短模式", "详细模式", "小说模式"]],
            default="简短模式",
        ),
    ),
    block=True,
    priority=5,
)


@fuck.handle()
async def _(bot, event, params: Arparma):
    image = params.query("image") or await reply_fetch(event, bot)
    mode = params.query("mode")
    prompt = get_prompt(mode)
    if isinstance(image, Reply) and not isinstance(image.msg, str):
        image = await UniMessage.generate(message=image.msg, event=event, bot=bot)
        for i in image:
            if isinstance(i, Image):
                image = i
                break
    if isinstance(image, Image) and image.url:
        image_bytes = await AsyncHttpx.get_content(image.url)
    elif isinstance(image, At):
        image_bytes = await PlatformUtils.get_user_avatar(image.target, "qq")
    else:
        return
    if not image_bytes:
        await UniMessage("下载图片失败QAQ...").send(reply_to=True)
        return
    data = {}
    base_url = Config.get_config("fuckornot", "base_url")
    model = Config.get_config("fuckornot", "model")
    api_key = Config.get_config("fuckornot", "api_key")
    chat_url = f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}"

    try:
        result = await AsyncHttpx.post(
            chat_url,
            json={
                "system_instruction": {"parts": [{"text": prompt}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": "请分析这张图片并决定的：上还是不上？",
                            },
                            {
                                "inline_data": {
                                    "data": base64.b64encode(image_bytes).decode(
                                        "utf-8"
                                    ),
                                    "mime_type": "image/jpeg",
                                },
                            },
                        ],
                    },
                ],
                "generationConfig": {
                    "thinkingConfig": {"thinkingBudget": 0},
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "OBJECT",
                        "properties": {
                            "verdict": {
                                "type": "STRING",
                                "description": "'上' 或 '不上'",
                            },
                            "rating": {
                                "type": "STRING",
                                "description": "1到10的数字",
                            },
                            "explanation": {
                                "type": "STRING",
                                "description": "你的明确、粗俗的解释（中文）",
                            },
                        },
                    },
                },
            },
            timeout=5,
        )
        data = result.json()
        data = ujson.loads(data["candidates"][0]["content"]["parts"][0]["text"])

        receipt = await UniMessage(
            Image(
                raw=await template_to_pic(
                    str(Path(__file__).parent),
                    "result.html",
                    templates={
                        "verdict": data["verdict"],
                        "rating": data["rating"],
                        "explanation": data["explanation"],
                    },
                )
            )
        ).send(reply_to=True)
        if Config.get_config("fuckornot", "withdraw_time") > 0:
            await WithdrawManager.withdraw_message(
                bot,
                receipt.msg_ids[0]["message_id"],
                time=Config.get_config("fuckornot", "withdraw_time"),
            )

    except Exception as e:
        logger.error(f"评分失败...\n{data}", "fuckornot", e=e)
        error_msg = data.get("candidates", [{}])[0].get("finishReason")
        if error_msg:
            receipt = await UniMessage(
                f"评分失败，请稍后再试.\n错误信息: {error_msg}"
            ).send(reply_to=True)
        else:
            receipt = await UniMessage(
                f"评分失败，请稍后再试.\n错误信息: {type(e)}:{e}"
            ).send(reply_to=True)
        if Config.get_config("fuckornot", "withdraw_time") > 0:
            await WithdrawManager.withdraw_message(
                bot,
                receipt.msg_ids[0]["message_id"],
                time=Config.get_config("fuckornot", "withdraw_time"),
            )
