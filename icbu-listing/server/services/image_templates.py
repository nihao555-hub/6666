"""High-converting Alibaba.com image stacks, grouped by category family.

We do not ship other people's photos. GitHub has the *recipes* that converting
listings actually use — slot order, one job per frame, category visual DNA —
and we encode those recipes here for ICBU (max 6 photobank images).
When the seller has no photos, Grsai gpt-image-2 renders these slots.

Sources we distilled (layouts and slot jobs only):

- motiful/product-shots — marketplace main-image rules + category DNA
  (electronics ≠ apparel ≠ grocery); identity lock across the set
- OnestarQQ/amazon-listing-skill — L1–L7 listing layouts
- liangdabiao/ecom-details-image — 25 scene types + campaign style lock
- gpt-img-2/gpt-image-2-ecommerce-skill — product identity lock first,
  one purchase-job per frame, reject SKU drift
- Ali-Aria/amazon-image-studio — MAIN + PT01… slot naming

Alibaba.com is B2B wholesale, not Amazon retail, so the sixth slot is almost
always carton / MOQ / OEM — the thing a factory buyer actually needs to see.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .ecom_skill import SKILL, assemble_prompt, clean_reference_urls, english_brief

ICBU_MAX_IMAGES = 6

# Shared rules every generated frame must keep. Main image is stricter.
# Distilled from high-star ecom skills (layouts/rules only, not their photos):
# buluslan/gpt-image2-ecommerce (312★) — concise lighting/composition/quality
# motiful/product-shots — main image 85% fill, white, no text
# gpt-img-2/gpt-image-2-ecommerce-skill — identity lock first
ICBU_BASE = (
    "Alibaba.com wholesale listing photo, square 1:1, commercial studio packshot. "
    "Soft diffused studio lighting, even illumination, true color, crisp edges. "
    "English text only if text is allowed. No Chinese characters. "
    "No Amazon or Prime badges, no star ratings, no prices, no watermarks, "
    "no fake CE/ISO/FDA marks, no invented accessories."
)
MAIN_RULES = (
    "Pure white background RGB 255,255,255. Product only, centered, "
    "fill about 85 percent of the frame. Subtle physically plausible contact shadow. "
    "No overlay text, no logos that are not on the real product, no props "
    "unless they ship in the box."
)
CRAFT = {
    "stationery": "Show true pigment and paper or wood tooth. Tidy factory-ready set.",
    "tools": "Working end visible. Honest metal or bristle texture. Include a scale cue if the slot allows.",
    "electronics": "True plastic or metal finish. Keep port and button layout exact. No fake screen UI.",
    "apparel": "Show real fabric drape and stitching. Ghost mannequin or tidy flat-lay. No invented prints.",
    "beauty": "Emphasize real texture and finish. Soft beauty dish. No glow that invents a formula.",
    "home": "Show material and craftsmanship. Believable domestic scale. No lifestyle clutter.",
    "toys": "Safe, tidy, age-plausible scene. No licensed characters unless they are on the real product.",
    "jewelry": "Macro sparkle and cut. Controlled specular highlights. Neutral luxury, not costume.",
    "industrial": "Technical, honest machine geometry. No cutaways of unseen internals.",
    "food": "Fresh true color and texture. No fake steam or nutrition claims.",
    "sports": "Use-ready gear, real materials. Outdoor light only in the lifestyle slot.",
    "general": "Neutral industrial catalog lighting. Product first.",
}
IDENTITY = (
    "PRODUCT IDENTITY LOCK: keep the exact silhouette, color, material, labels, "
    "port layout and accessory count. Do not redesign the SKU."
)

# L1–L7 from Amazon Visual Architect, used as composition, not as a brand.
LAYOUTS = {
    "L1": "文本叠加面板",
    "L2": "卖点特征块",
    "L3": "极简大场景",
    "L4": "形态衍生",
    "L5": "圆形特写",
    "L6": "结构分解",
    "L7": "Flat Lay 俯拍",
}


@dataclass(frozen=True)
class SlotSpec:
    id: str
    name: str
    buyer_job: str
    layout: str
    text_policy: str  # none | short_en | infographic
    scene: str
    prompt: str


@dataclass(frozen=True)
class Family:
    id: str
    name: str
    alibaba_hint: str
    keywords: tuple[str, ...]
    why: str
    slots: tuple[SlotSpec, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "alibaba_hint": self.alibaba_hint,
            "why": self.why,
            "keywords": list(self.keywords),
            "slots": [
                {
                    "id": slot.id,
                    "name": slot.name,
                    "buyer_job": slot.buyer_job,
                    "layout": slot.layout,
                    "layout_name": LAYOUTS.get(slot.layout, slot.layout),
                    "text_policy": slot.text_policy,
                    "scene": slot.scene,
                }
                for slot in self.slots
            ],
        }


def _slot(
    slot_id: str,
    name: str,
    buyer_job: str,
    layout: str,
    text_policy: str,
    scene: str,
    prompt: str,
) -> SlotSpec:
    return SlotSpec(slot_id, name, buyer_job, layout, text_policy, scene, prompt)


def _main(extra: str = "") -> SlotSpec:
    body = (
        "Hero product shot on seamless pure white. Even softbox lighting, "
        "slight ground shadow, true color, no text. Show {product} clearly."
    )
    if extra:
        body = f"{body} {extra}"
    return _slot("main", "白底主图", "搜索结果里 1 秒认出货是什么", "L3", "none", "hero-white", body)


FAMILIES: tuple[Family, ...] = (
    Family(
        id="stationery",
        name="文具 / 办公 / 彩铅画材",
        alibaba_hint="Office & School Supplies · Writing Instruments",
        keywords=(
            "pencil",
            "crayon",
            "marker",
            "pen",
            "notebook",
            "eraser",
            "stationery",
            "office",
            "brush pen",
            "watercolor",
            "sketch",
            "文具",
            "彩铅",
            "画笔",
        ),
        why="买手先看色号齐不齐、笔芯细不细、一盒几支、能不能印 logo。",
        slots=(
            _main("Full set facing camera, tidy factory-ready arrangement."),
            _slot(
                "range",
                "色号 / 规格铺开",
                "确认颜色或规格覆盖够不够订",
                "L7",
                "short_en",
                "flat-lay",
                "Flat-lay of the full {product} color or size range on clean white, "
                "even spacing, true pigments, optional tiny English labels for color names only.",
            ),
            _slot(
                "detail",
                "笔尖 / 材质特写",
                "判断铅芯、毛质、做工能不能过零售货架",
                "L5",
                "none",
                "macro",
                "Macro of the working tip or material of {product}. Sharp focus on "
                "lead, bristle or paper tooth. Neutral studio, no text.",
            ),
            _slot(
                "use",
                "教室 / 办公使用",
                "想象终端用户怎么用，方便转售话术",
                "L3",
                "none",
                "lifestyle",
                "Realistic classroom or office scene, {audience} using {product} for {usage}. "
                "Product must stay recognizable. No faces looking at camera, no logos.",
            ),
            _slot(
                "pack",
                "内盒 + 外箱",
                "看装箱量和出口包装，估运费和 MOQ",
                "L2",
                "short_en",
                "packaging",
                "Export inner box plus master carton of {product}. Honest packing, "
                "one short English line such as 'Assorted 24 pcs / carton'. No fake barcodes.",
            ),
            _slot(
                "custom",
                "OEM / 印 logo",
                "确认能不能做定制，这是询盘高频问题",
                "L1",
                "short_en",
                "oem",
                "The same {product} with a generic sample logo area marked, plus a small "
                "English panel 'Custom logo / OEM'. Do not invent a real brand.",
            ),
        ),
    ),
    Family(
        id="tools",
        name="五金 / 工具 / 刷具",
        alibaba_hint="Tools · Hardware · Brush",
        keywords=(
            "tool",
            "wrench",
            "drill",
            "hammer",
            "paint brush",
            "paintbrush",
            "roller",
            "hardware",
            "valve",
            "fitting",
            "clamp",
            "工具",
            "五金",
            "油漆刷",
        ),
        why="工厂买手看尺寸对照、头型材质、工地能不能用、一箱几把。",
        slots=(
            _main("Three-quarter studio angle, working end visible."),
            _slot(
                "scale",
                "尺寸对照",
                "判断是家用还是工业规格",
                "L5",
                "short_en",
                "scale",
                "{product} next to a hand or steel ruler on white, true proportions. "
                "Optional small English size callout only if a real measurement is known.",
            ),
            _slot(
                "detail",
                "头部 / 材质特写",
                "看钢材、刷毛、焊接是否像能用的货",
                "L5",
                "none",
                "macro",
                "Macro of the working head or ferrule of {product}, {material} texture sharp, no text.",
            ),
            _slot(
                "use",
                "工地 / 车间使用",
                "确认使用场景，减少错误类目询盘",
                "L3",
                "none",
                "lifestyle",
                "Workshop or jobsite, gloved hands using {product} for {usage}. Product sharp, background soft.",
            ),
            _slot(
                "pack",
                "外箱 / 打托",
                "算柜量和起订，这是批发决策图",
                "L2",
                "short_en",
                "packaging",
                "Export carton or pallet of {product}, warehouse lighting, one English pack-count line.",
            ),
            _slot(
                "custom",
                "规格信息图",
                "把柄长、材质、是否可定制一次讲清",
                "L2",
                "infographic",
                "infographic",
                "Clean infographic of {product} with 3 short English facts from known specs only. "
                "White studio, no fake certifications.",
            ),
        ),
    ),
    Family(
        id="electronics",
        name="消费电子 / 配件",
        alibaba_hint="Consumer Electronics · Accessories",
        keywords=(
            "earbud",
            "headphone",
            "charger",
            "cable",
            "adapter",
            "camera",
            "speaker",
            "led",
            "battery",
            "power bank",
            "electronic",
            "耳机",
            "充电",
        ),
        why="接口、配件清单、尺寸、外箱，比氛围图更能促成批发单。",
        slots=(
            _main("Front three-quarter, ports facing slightly toward camera."),
            _slot(
                "ports",
                "接口 / 按键特写",
                "确认兼容什么设备，减少退货争议",
                "L5",
                "none",
                "macro",
                "Close-up of real ports, buttons and indicators on {product}. Do not invent extra ports.",
            ),
            _slot(
                "explode",
                "结构 / 配件铺开",
                "看盒内有什么，按清单采购",
                "L6",
                "short_en",
                "exploded",
                "Exploded or neatly laid contents that actually ship with {product}. "
                "No invented dongles. Optional tiny English labels.",
            ),
            _slot(
                "use",
                "使用场景",
                "对上办公 / 车载 / 仓储等批发渠道",
                "L3",
                "none",
                "lifestyle",
                "Believable {usage} scene with {product} in use by {audience}. Product identity locked.",
            ),
            _slot(
                "pack",
                "彩盒 + 外箱",
                "零售盒好不好看、外箱能不能走柜",
                "L2",
                "short_en",
                "packaging",
                "Retail box plus master carton of {product}. Honest packaging, one English pack line.",
            ),
            _slot(
                "spec",
                "参数信息图",
                "电压、接口、续航等已知参数一眼看完",
                "L2",
                "infographic",
                "infographic",
                "Minimal spec card for {product}. Only list facts from known specs. No fake battery hours.",
            ),
        ),
    ),
    Family(
        id="apparel",
        name="服装 / 鞋包 / 纺织",
        alibaba_hint="Apparel · Footwear · Bags",
        keywords=(
            "dress",
            "shirt",
            "hoodie",
            "jacket",
            "pant",
            "shoe",
            "sneaker",
            "bag",
            "apparel",
            "garment",
            "fabric",
            "tee",
            "服装",
            "鞋子",
            "包包",
        ),
        why="服装转化靠版型、面料、尺码表和色组，外箱决定能不能整柜。",
        slots=(
            _main("Ghost-mannequin or tidy product-only front view, garment shape true."),
            _slot(
                "wear",
                "上身 / 立体",
                "看版型和垂感，减少尺码纠纷",
                "L3",
                "none",
                "model",
                "On-model or ghost-mannequin 3/4 view of {product}, true drape and color, no fashion-brand logos.",
            ),
            _slot(
                "fabric",
                "面料 / 车线特写",
                "判断克重和做工能不能当零售货",
                "L5",
                "none",
                "macro",
                "Macro of fabric weave, stitching or sole of {product}. True {material}. No text.",
            ),
            _slot(
                "size",
                "尺码信息图",
                "批发下单前必须能对尺码",
                "L2",
                "infographic",
                "size-chart",
                "Clean size-chart style graphic for {product}. Only include measurements you were given. "
                "If none, show a simple 'Size chart available' panel plus the garment flat.",
            ),
            _slot(
                "colors",
                "色组平铺",
                "一次看清可订颜色，方便配货",
                "L7",
                "short_en",
                "flat-lay",
                "Flat-lay of available colorways of {product} on white. Do not invent colors not mentioned.",
            ),
            _slot(
                "pack",
                "袋装 + 外箱",
                "看包装方式和装箱量",
                "L2",
                "short_en",
                "packaging",
                "Polybag or inner pack plus export carton of {product}. One English pack-count line.",
            ),
        ),
    ),
    Family(
        id="beauty",
        name="美妆 / 个护",
        alibaba_hint="Beauty · Personal Care",
        keywords=(
            "cream",
            "serum",
            "lotion",
            "shampoo",
            "soap",
            "cosmetic",
            "lipstick",
            "skincare",
            "beauty",
            "护肤",
            "化妆品",
        ),
        why="膏体质地、容量规格、外箱比前后对比图更适合国际站（对比图容易违规）。",
        slots=(
            _main("Bottle or compact centered, label readable if it exists."),
            _slot(
                "texture",
                "质地特写",
                "看膏体是水是乳，避免错订",
                "L5",
                "none",
                "macro",
                "Texture swatch of the real formula of {product} beside the closed pack. No skin before/after.",
            ),
            _slot(
                "use",
                "使用场景",
                "对上酒店、零售、日化渠道",
                "L3",
                "none",
                "lifestyle",
                "Clean bathroom or spa scene, {product} in natural use. No medical claims, no before/after.",
            ),
            _slot(
                "sizes",
                "容量 / 规格",
                "确认起订规格，方便配 SKU",
                "L2",
                "short_en",
                "multi-product",
                "Family of real pack sizes of {product} on white. Do not invent volumes.",
            ),
            _slot(
                "pack",
                "中盒 + 外箱",
                "酒店和商超买手看装箱",
                "L2",
                "short_en",
                "packaging",
                "Inner carton and master carton of {product}, honest packaging.",
            ),
            _slot(
                "facts",
                "成分 / 规格卡",
                "只写已知事实，不编功效数字",
                "L1",
                "infographic",
                "infographic",
                "Fact card for {product} using only given ingredients or specs. No miracle claims.",
            ),
        ),
    ),
    Family(
        id="home",
        name="家居 / 厨具 / 花园",
        alibaba_hint="Home & Garden · Kitchen",
        keywords=(
            "chair",
            "table",
            "sofa",
            "lamp",
            "pillow",
            "kitchen",
            "garden",
            "furniture",
            "mug",
            "pan",
            "home",
            "家具",
            "厨具",
        ),
        why="空间感、尺寸、材质、套装和外箱决定能不能进商超和酒店渠道。",
        slots=(
            _main("Product isolated, true scale, no room set."),
            _slot(
                "room",
                "空间场景",
                "看风格能不能进目标渠道",
                "L3",
                "none",
                "lifestyle",
                "Tasteful room or patio with {product} in {usage}. Product must match the reference exactly.",
            ),
            _slot(
                "dimension",
                "尺寸示意",
                "家具和厨具没有尺寸几乎不下单",
                "L2",
                "infographic",
                "size-spec",
                "{product} on white with simple English dimension lines only if measurements are known.",
            ),
            _slot(
                "material",
                "材质特写",
                "看木皮、织法、涂层是不是描述的那种",
                "L5",
                "none",
                "macro",
                "Macro of {material} surface of {product}. True texture, no text.",
            ),
            _slot(
                "set",
                "套装 / 搭配",
                "确认是单件还是套装报价",
                "L7",
                "short_en",
                "multi-product",
                "Complete set that actually ships as {product}. Do not add extra pieces.",
            ),
            _slot(
                "pack",
                "出口包装",
                "看是否打托、防撞，估运损",
                "L2",
                "short_en",
                "packaging",
                "Export carton or foam-in-box packing of {product}. Warehouse light.",
            ),
        ),
    ),
    Family(
        id="toys",
        name="玩具 / 母婴",
        alibaba_hint="Toys · Baby Products",
        keywords=("toy", "doll", "puzzle", "baby", "kid", "plush", "玩具", "母婴"),
        why="玩法、零件、年龄段包装和外箱。不编安全认证。",
        slots=(
            _main("Product centered, all real parts visible."),
            _slot(
                "play",
                "使用 / 玩法",
                "买手用来写零售卖点",
                "L3",
                "none",
                "lifestyle",
                "Child-appropriate play scene with {product}. No visible brand, no unsafe use.",
            ),
            _slot(
                "parts",
                "零件铺开",
                "确认套装件数，避免少件投诉",
                "L7",
                "short_en",
                "flat-lay",
                "All real parts of {product} laid out. Do not invent extra pieces.",
            ),
            _slot(
                "detail",
                "做工特写",
                "看缝线、边缘、印刷",
                "L5",
                "none",
                "macro",
                "Macro of stitching, print or edges of {product}.",
            ),
            _slot(
                "pack",
                "彩盒 + 外箱",
                "商超渠道看零售包装",
                "L2",
                "short_en",
                "packaging",
                "Retail box and master carton of {product}. No fake age or safety marks.",
            ),
            _slot(
                "custom",
                "OEM 说明",
                "玩具定制询盘多，单独给一张",
                "L1",
                "short_en",
                "oem",
                "{product} with a generic 'Custom color / logo' English panel. No real brands.",
            ),
        ),
    ),
    Family(
        id="jewelry",
        name="饰品 / 手表",
        alibaba_hint="Jewelry · Watches · Eyewear",
        keywords=("ring", "necklace", "earring", "bracelet", "watch", "jewelry", "饰品", "手表"),
        why="做工特写和克重/尺寸比模特大片更能促成批发。",
        slots=(
            _main("Product on white or very light grey, true metal color."),
            _slot(
                "wear",
                "佩戴示意",
                "看实际大小，避免照片欺骗",
                "L3",
                "none",
                "lifestyle",
                "Tasteful on-body crop showing true scale of {product}. No luxury-brand marks.",
            ),
            _slot(
                "craft",
                "工艺特写",
                "看镶嵌、抛光、表扣",
                "L5",
                "none",
                "macro",
                "Macro of craftsmanship on {product}, {material} true to reference.",
            ),
            _slot(
                "scale",
                "尺寸 / 克重",
                "批发按克或按尺寸下单",
                "L2",
                "infographic",
                "size-spec",
                "{product} with a scale reference. Only print measurements you were given.",
            ),
            _slot(
                "set",
                "套装平铺",
                "确认是单件还是套装报价",
                "L7",
                "none",
                "flat-lay",
                "Flat-lay of the real set of {product} on linen or white.",
            ),
            _slot(
                "pack",
                "礼盒 + 外箱",
                "看能否做零售礼盒和出口箱",
                "L2",
                "short_en",
                "packaging",
                "Gift box and export carton of {product}.",
            ),
        ),
    ),
    Family(
        id="industrial",
        name="机械 / 工业件",
        alibaba_hint="Machinery · Industrial Parts",
        keywords=("machine", "motor", "pump", "cnc", "industrial", "compressor", "机械", "电机"),
        why="结构、接口尺寸、铭牌真实信息、木箱打托，比精修氛围图有用。",
        slots=(
            _main("Machine isolated on light grey or white, true proportions."),
            _slot(
                "ports",
                "接口 / 铭牌",
                "工程采购核对接口和型号",
                "L5",
                "none",
                "macro",
                "Close-up of real ports, flanges or nameplate of {product}. Do not invent model numbers.",
            ),
            _slot(
                "explode",
                "结构分解",
                "看内部是什么级别的货",
                "L6",
                "short_en",
                "exploded",
                "Honest exploded or cutaway of {product} only if structure is visible or described. "
                "Otherwise a labeled exterior with 3 real parts.",
            ),
            _slot(
                "use",
                "产线使用",
                "对上工厂场景，减少民用询盘",
                "L3",
                "none",
                "lifestyle",
                "Factory floor with {product} in {usage}. Safety-realistic, no fake workers branding.",
            ),
            _slot(
                "spec",
                "参数图",
                "电压、流量、功率等已知参数",
                "L2",
                "infographic",
                "infographic",
                "Spec sheet style image for {product}. Only known numbers.",
            ),
            _slot(
                "pack",
                "木箱 / 打托",
                "出口机械必须能看到包装方式",
                "L2",
                "short_en",
                "packaging",
                "Wooden crate or pallet packing of {product} in a warehouse.",
            ),
        ),
    ),
    Family(
        id="food",
        name="食品 / 饮料 / 农产品",
        alibaba_hint="Food & Beverage",
        keywords=("food", "tea", "coffee", "snack", "spice", "sauce", "beverage", "食品", "茶叶"),
        why="内容物、克重、箱规。不编有机/FDA 标志。",
        slots=(
            _main("Closed retail pack, label only if it exists on the real product."),
            _slot(
                "contents",
                "内容物",
                "看货是什么，避免包装欺骗",
                "L5",
                "none",
                "macro",
                "Honest contents of {product} beside the closed pack. True color, no steam gimmicks.",
            ),
            _slot(
                "serve",
                "食用 / 冲泡",
                "给进口商写货架文案",
                "L3",
                "none",
                "lifestyle",
                "Simple serving scene for {product}. No health claims.",
            ),
            _slot(
                "sizes",
                "克重规格",
                "确认起订规格",
                "L2",
                "short_en",
                "multi-product",
                "Real pack weights of {product} on white. Do not invent sizes.",
            ),
            _slot(
                "pack",
                "箱规",
                "进口商按箱规算柜",
                "L2",
                "short_en",
                "packaging",
                "Master carton of {product} with one English count line. No fake organic seals.",
            ),
            _slot(
                "facts",
                "产地 / 规格卡",
                "只写已知产地和工艺",
                "L1",
                "infographic",
                "infographic",
                "Fact card: origin and known process for {product}. No invented certifications.",
            ),
        ),
    ),
    Family(
        id="sports",
        name="运动 / 户外",
        alibaba_hint="Sports & Entertainment · Outdoor",
        keywords=("bike", "ball", "yoga", "tent", "outdoor", "sport", "fitness", "运动", "户外"),
        why="动态使用、尺寸、材质和外箱，比精修海报更像能发的批发图。",
        slots=(
            _main("Product isolated on white, true colorway."),
            _slot(
                "action",
                "运动使用",
                "对上渠道：健身房、户外、学校",
                "L3",
                "none",
                "sports",
                "In-action {usage} photo with {product}. Product identity locked, no team logos.",
            ),
            _slot(
                "detail",
                "材质 / 结构",
                "看缝线、支架、握把",
                "L5",
                "none",
                "macro",
                "Macro of {material} or structure of {product}.",
            ),
            _slot(
                "scale",
                "尺寸对照",
                "帐篷、器材必须能估体积",
                "L2",
                "short_en",
                "scale",
                "{product} with a human or ruler scale. Only print sizes you know.",
            ),
            _slot(
                "pack",
                "收纳 + 外箱",
                "看能否压缩装箱",
                "L2",
                "short_en",
                "packaging",
                "Carry bag plus export carton of {product}.",
            ),
            _slot(
                "custom",
                "OEM 色组",
                "运动品定制色询盘多",
                "L1",
                "short_en",
                "oem",
                "Colorway or logo-area sample of {product}, English 'Custom color / logo'.",
            ),
        ),
    ),
    Family(
        id="general",
        name="通用工业品",
        alibaba_hint="General merchandise",
        keywords=(),
        why="认不出类目时用这套：白底、尺寸、细节、场景、外箱、定制。",
        slots=(
            _main(),
            _slot(
                "scale",
                "尺寸对照",
                "没有尺寸批发很难下单",
                "L5",
                "short_en",
                "scale",
                "{product} with a simple scale reference on white.",
            ),
            _slot(
                "detail",
                "细节特写",
                "看做工和材质",
                "L5",
                "none",
                "macro",
                "Macro detail of {product}, {material} texture, no text.",
            ),
            _slot(
                "use",
                "使用场景",
                "对上正确的批发渠道",
                "L3",
                "none",
                "lifestyle",
                "Believable {usage} scene featuring {product} for {audience}.",
            ),
            _slot(
                "pack",
                "外箱包装",
                "国际站询盘必问装箱",
                "L2",
                "short_en",
                "packaging",
                "Export carton of {product}, one English pack line.",
            ),
            _slot(
                "custom",
                "OEM / 卖点卡",
                "把已知卖点收成一张询盘图",
                "L1",
                "infographic",
                "infographic",
                "Clean English feature card for {product} using only given features. No fake awards.",
            ),
        ),
    ),
)

FAMILY_BY_ID = {item.id: item for item in FAMILIES}

# Official Alibaba.com top-level names, so a shop category pick matches a stack.
OFFICIAL_HINTS = {
    "stationery": ("office & school", "office supplies", "writing instruments", "办公", "文具"),
    "tools": ("tools & hardware", "construction & decoration", "五金工具", "建筑"),
    "electronics": ("consumer electronics", "electrical equipment", "消费电子", "电工"),
    "apparel": ("apparel & accessories", "shoes & accessories", "luggage, bags", "服装及配饰", "鞋", "箱包"),
    "beauty": ("beauty", "personal care", "health & medical", "美妆", "个护"),
    "home": ("home & garden", "furniture", "lights & lighting", "家居", "家具", "灯"),
    "toys": ("mother, kids & toys", "toys", "母婴", "玩具"),
    "jewelry": ("jewelry", "watches", "饰品", "手表"),
    "industrial": ("machinery", "industrial", "vehicle parts", "机械", "工业"),
    "food": ("food & beverage", "agriculture", "食品", "农业", "饮料"),
    "sports": ("sports & entertainment", "运动", "户外"),
}

# Repos we learned the slot grammar from — shown in the UI so sellers know
# this is a method, not a scraped image pack.
SOURCES = [SKILL]


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("_", " ").replace("-", " ").split())


def pick_family(*hints: str, family_id: str = "") -> Family:
    if family_id and family_id in FAMILY_BY_ID:
        return FAMILY_BY_ID[family_id]
    raw = " ".join(str(item or "") for item in hints)
    blob = _norm(f"{raw} {english_brief(raw)}")
    if not blob:
        return FAMILY_BY_ID["general"]
    best: Family | None = None
    best_hits = 0
    for family in FAMILIES:
        if family.id == "general":
            continue
        hits = sum(1 for word in family.keywords if word and word in blob)
        hits += sum(1 for word in OFFICIAL_HINTS.get(family.id, ()) if word and word in blob)
        if hits > best_hits:
            best, best_hits = family, hits
    return best or FAMILY_BY_ID["general"]


def _fill(template: str, values: Mapping[str, str]) -> str:
    text = template
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return " ".join(text.split())


def identity_lock(facts: Mapping[str, Any]) -> str:
    bits = [IDENTITY]
    name = str(facts.get("product") or facts.get("product_name") or "the product")
    bits.append(f"The product is: {name}.")
    if facts.get("material"):
        bits.append(f"Material stays {facts['material']}.")
    colors = facts.get("colors") or []
    if isinstance(colors, Sequence) and colors:
        bits.append("Colors stay " + ", ".join(str(item) for item in colors[:6]) + ".")
    if facts.get("note"):
        bits.append(f"Seller note: {facts['note']}.")
    return " ".join(bits)


def style_lock(family: Family) -> str:
    return (
        f"CAMPAIGN STYLE LOCK for {family.name}: consistent color temperature, "
        "the same product, the same lighting family across the set, no random "
        "background palette shifts."
    )


def plan_stack(
    *,
    family_id: str = "",
    product_name: str = "",
    category_hint: str = "",
    material: str = "",
    colors: Sequence[str] | None = None,
    usage: str = "",
    audience: str = "",
    features: Sequence[str] | None = None,
    specs: Mapping[str, Any] | None = None,
    note: str = "",
    reference_urls: Sequence[str] | None = None,
) -> dict[str, Any]:
    family = pick_family(product_name, category_hint, usage, note, family_id=family_id)
    colors = [str(item) for item in (colors or []) if str(item).strip()]
    features = [str(item) for item in (features or []) if str(item).strip()]
    specs = dict(specs or {})
    refs = clean_reference_urls(reference_urls)
    product = product_name or category_hint or "the wholesale product"
    brief = english_brief(product, note)
    facts = {
        "product": brief,
        "product_name": product,
        "material": material,
        "colors": colors,
        "note": note,
        "features": features,
        "specs": specs,
    }
    lock = identity_lock(facts)
    campaign = style_lock(family)
    slots: list[dict[str, Any]] = []
    for index, spec in enumerate(family.slots[:ICBU_MAX_IMAGES], start=1):
        prompt = assemble_prompt(
            spec.id,
            product=product,
            family_id=family.id,
            material=material,
            colors=colors,
            features=features,
            usage=usage,
            note=note,
            text_policy=spec.text_policy,
            product_brief=brief,
            specs=specs,
        )
        slots.append(
            {
                "id": spec.id,
                "index": index,
                "name": spec.name,
                "buyer_job": spec.buyer_job,
                "layout": spec.layout,
                "layout_name": LAYOUTS.get(spec.layout, spec.layout),
                "text_policy": spec.text_policy,
                "scene": spec.scene,
                "prompt": prompt,
            }
        )
    return {
        "family": family.as_dict(),
        "product_name": product,
        "product_brief": brief,
        "reference_urls": refs,
        "style_lock": campaign,
        "identity_lock": lock,
        "slots": slots,
        "skill": SKILL,
        "sources": SOURCES,
        "platform_note": "国际站图片银行最多 6 张。主图必须白底无字；外箱/OEM 是批发转化位，不要拿去堆氛围图。出图按英文，商品上原有印刷会保留。",
    }


def catalog() -> dict[str, Any]:
    return {
        "families": [item.as_dict() for item in FAMILIES],
        "layouts": LAYOUTS,
        "max_images": ICBU_MAX_IMAGES,
        "sources": SOURCES,
        "platform_note": "按阿里国际站 6 张位改编。GitHub 上的是亚马逊 7 张 + A+，我们把零售对比/评分位换成外箱和 OEM。",
    }
