import base64
from pathlib import Path

from nonebot.adapters import Bot, Event
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
from zhenxun.services.llm import get_model_instance
from zhenxun.services.llm.config.generation import (
    LLMGenerationConfig,
)
from zhenxun.services.llm.types.content import LLMContentPart, LLMMessage
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
    |1  | 欲望化身
    |2  | 霸道总裁
    |3  | 耽美鉴赏家
    |4  | 恋物诗人
    |5  | 纯欲神官
    |6  | 百合诗人
    |7  | 邪恶兽人控
    |8  | 硬核-简短模式
    |9  | 硬核-详细模式
    |10 | 硬核-小说模式

    例如:
        上 -s 1 [图片]
        上 -s 霸道总裁 [图片]
    """.strip(),
    extra=PluginExtraData(
        author="molanp",
        version="1.7",
        menu_type="群内小游戏",
        configs=[
            RegisterConfig(
                key="provider",
                value="Gemini/gemini-2.5-flash-lite-preview-06-17",
                help="AI服务提供者",
            ),
            RegisterConfig(
                key="withdraw_time",
                value=30,
                type=int,
                help="撤回时间,单位秒, 0为不撤回",
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


fuck = on_alconna(
    Alconna(
        "上",
        Args["image?", Image | At],
        Option(
            "-s",
            Args[
                "soul",
                [
                    "欲望化身",
                    "霸道总裁",
                    "耽美鉴赏家",
                    "恋物诗人",
                    "纯欲神官",
                    "百合诗人",
                    "邪恶兽人控",
                    "硬核-简短模式",
                    "硬核-详细模式",
                    "硬核-小说模式",
                    int,
                ],
            ],
        ),
    ),
    block=True,
    priority=5,
)


@fuck.handle()
async def _(bot: Bot, event: Event,params: Arparma):
    base_config = Config.get("fuckornot")
    image = params.query("image") or await reply_fetch(event, bot)
    soul = params.query("soul") or base_config.get("default_soul")
    withdraw_time = base_config.get("withdraw_time")
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
    provider = base_config.get("provider")
    preview = base_config.get("preview")
    preview_src = base64.b64encode(image_bytes).decode("utf-8") if preview else ""

    model_config = LLMGenerationConfig(
        response_mime_type="application/json",
        response_schema={
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
        # safety_settings={
        #     "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
        #     "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
        #     "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
        #     "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        #     "HARM_CATEGORY_CIVIC_INTEGRITY": "BLOCK_NONE",
        # },
    )
    try:
        async with await get_model_instance(provider) as model:
            response = await model.generate_response(
                messages=[
                    LLMMessage.system(content=prompt),
                    LLMMessage.user(
                        [
                            LLMContentPart.text_part("开始游戏。请评估这张艺术品"),
                            LLMContentPart.image_base64_part(
                                base64.b64encode(image_bytes).decode("utf-8"),
                                "image/jpeg",
                            ),
                        ]
                    ),
                ],
                config=model_config,
            )
            data = response.raw_response or {}
        res = data["candidates"][0]["content"]["parts"][0]["text"]
        if "`" in res:
            res = res.replace("`", "")
        if "json" in res:
            res = res.replace("json", "")
        if "\n" in res:
            res = res.replace("\n", "")
        if r"\n" in res:
            res = res.replace(r"\n", "")
        data: dict = ujson.loads(res)

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
        if withdraw_time > 0:
            await WithdrawManager.withdraw_message(
                bot,
                receipt.msg_ids[0]["message_id"],
                time=withdraw_time,
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
        if withdraw_time > 0:
            await WithdrawManager.withdraw_message(
                bot,
                receipt.msg_ids[0]["message_id"],
                time=withdraw_time,
            )
