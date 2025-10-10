from pathlib import Path

from pydantic import BaseModel, Field
from typing import Literal
import ujson

soul_list = {
    "欲望化身": "desire_avatar",
    "霸道总裁": "dominator",
    "耽美鉴赏家": "aesthetic_curator",
    "恋物诗人": "fetish_poet",
    "纯欲神官": "oracle_of_purity",
    "百合诗人": "lily_poet",
    "邪恶兽人控": "animal_avatar",
    "硬核-简短模式": "hardcore_simple",
    "硬核-详细模式": "hardcore_detail",
    "硬核-小说模式": "hardcore",
}

prompt: dict[str, str] = ujson.loads(
    (Path(__file__).parent / "prompt.json").read_text(encoding="utf-8")
)


def get_prompt(s: str | int):
    if isinstance(s, int) and not 0 < s <= len(soul_list):
        raise ValueError("人格不存在！")
    if isinstance(s, str) and s not in soul_list.keys():
        raise ValueError("人格不存在！")
    if isinstance(s, int):
        return prompt[list(soul_list.values())[s - 1]]
    else:
        return prompt[soul_list[s]]


class FuckResponse(BaseModel):
    verdict: Literal["上", "不上"] = Field(..., description="'上' 或 '不上'")
    rating: int = Field(..., description="1到10的数字")
    explanation: str = Field(..., description="你的评语/解释")
