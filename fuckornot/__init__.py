import base64
from pathlib import Path
from typing import Literal

from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, Image, Option, on_alconna
from nonebot_plugin_htmlrender import template_to_pic
import ujson

from zhenxun.configs.utils import PluginExtraData
from zhenxun.utils.http_utils import AsyncHttpx

from .prompt import get_prompt

__plugin_meta__ = PluginMetadata(
    name="上不上AI评分系统",
    description="上不上AI评分系统",
    usage="""
    上传图片，让AI来评判它的可操性
        上 [图片]
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
        version="1.0",
        menu_type="群内小游戏",
    ).dict(),
)

fuck = on_alconna(
    Alconna(
        "上",
        Args["image", Image],
        Option(
            "--m",
            Args["mode", Literal["简短模式", "详细模式", "小说模式"]],
            default="简短模式",
        ),
    ),
)


@fuck.handle()
async def _(params: Arparma):
    image = params.query("image")
    assert isinstance(image, Image)
    mode = params.query("mode")
    prompt = get_prompt(mode)
    try:
        if image.url is None:
            raise ValueError("图片资源下载失败!")
        image_bytes = await AsyncHttpx.get_content(image.url)
        result = await AsyncHttpx.post(
            "https://api.websim.com/api/v1/inference/run_chat_completion",
            json={
                "project_id": "vno75_2x4ii3ayx8wmmw",
                "messages": [
                    {
                        "role": "system",
                        "content": prompt,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请分析这张图片并决定的：上还是不上？",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": (
                                        "data:image/jpeg;base64,"
                                        f"{base64.b64encode(image_bytes).decode('utf-8')}"
                                    )
                                },
                            },
                        ],
                    },
                ],
                "json": True,
            },
        )
        data = ujson.loads(result.json()["content"])
        await fuck.send(
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
        )
    except Exception as e:
        await fuck.send(f"评分失败，请稍后再试.\n错误信息: {type(e)}:{e}")
