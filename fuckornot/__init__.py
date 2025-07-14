import base64
from pathlib import Path
from typing import Literal

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
        上 @user
        [回复]上

    -----人格列表，可以使用序号或名称指定人格-----
    |1 | 欲望化身
    |2 | 霸道总裁
    |3 | 耽美鉴赏家
    |4 | 恋物诗人
    |5 | 纯欲神官
    |6 | 百合诗人
    |7 | 邪恶兽人控

    例如:
        上 -s 1 [图片]
        上 -s 霸道总裁 [图片]
    """.strip(),
    extra=PluginExtraData(
        author="molanp",
        version="1.5",
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
                value="gemini-2.5-flash-lite-preview-06-17",
                help="Gemini AI 模型名称",
            ),
            RegisterConfig(
                key="withdraw_time",
                value=30,
                type=int,
                help="撤回时间,单位秒, 0为不撤回"
            ),
            RegisterConfig(
                key="default_soul",
                value="欲望化身",
                help="不指定时的默认AI人格名称",
            ),
            RegisterConfig(
                key="preview",
                value=False,
                type=bool,
                help="是否在结果中展示输入图片",
            ),
        ],
    ).dict(),
)
try:
    default_soul = Config.get_config("fuckornot", "default_soul")
except Exception:
    default_soul = "欲望化身"
finally:
    if not default_soul:
        default_soul = "欲望化身"


fuck = on_alconna(
    Alconna(
        "上",
        Args["image?", Image | At],
        Option(
            "-s",
            Args[
                "soul",
                Literal[
                    "欲望化身",
                    "霸道总裁",
                    "耽美鉴赏家",
                    "恋物诗人",
                    "纯欲神官",
                    "百合诗人",
                    "邪恶兽人控",
                    int,
                ],
            ],
        ),
    ),
    block=True,
    priority=5,
)


@fuck.handle()
async def _(bot, event, params: Arparma):
    image = params.query("image") or await reply_fetch(event, bot)
    soul = params.query("soul") or default_soul
    assert soul is not None
    try:
        prompt = get_prompt(soul)
    except ValueError as e:
        await UniMessage(str(e)).finish(reply_to=True)
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
        await UniMessage("下载图片失败QAQ...").finish(reply_to=True)
    data = {}
    base_url = Config.get_config("fuckornot", "base_url")
    model = Config.get_config("fuckornot", "model")
    api_key = Config.get_config("fuckornot", "api_key")
    preview = Config.get_config("fuckornot", "preview")
    chat_url = f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}"

    preview_src = base64.b64encode(image_bytes).decode("utf-8") if preview else ""
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
                                "text": "开始游戏。请评估这张艺术品。",
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
                                "description": "你的评语/解释",
                            },
                        },
                        "nullable": False,
                        "required": ["verdict", "rating", "explanation"],
                    },
                },
                "safetySettings": [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_CIVIC_INTEGRITY",
                        "threshold": "BLOCK_NONE",
                    },
                ],
            },
            timeout=30,
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
                        "src": preview_src,
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
                f"评分失败，请稍后再试.\n错误信息: {type(e)}"
            ).send(reply_to=True)
        if Config.get_config("fuckornot", "withdraw_time") > 0:
            await WithdrawManager.withdraw_message(
                bot,
                receipt.msg_ids[0]["message_id"],
                time=Config.get_config("fuckornot", "withdraw_time"),
            )
