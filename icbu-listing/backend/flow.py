"""User-visible listing flow mapped to official ICBU APIs.

The product principle: the seller only supplies images plus price/MOQ.
Everything else is filled by AI or shop defaults, then checked against schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FlowStep:
    id: str
    title: str
    actor: str  # user | ai | system | shop
    user_input: str
    apis: tuple[str, ...]
    notes: str = ""
    schema_fields: tuple[str, ...] = field(default_factory=tuple)


SHOP_DEFAULTS = (
    "market",
    "priceUnit",
    "paymentMethod",
    "port",
    "ladderPeriod",
    "shippingTemplateId",
    "pkgMeasure",
    "pkgWeight",
    "logisticsMode",
    "logisticsProperty",
)

AI_FIELDS = (
    "productTitle",
    "productKeywords",
    "icbuCatProp",
    "productDescType",
    "superText",
    "scImages",
)

USER_FIELDS = (
    "fob",
    "minOrderQuantity",
    "ladderPrice",
    "scPrice",
)

FLOW: tuple[FlowStep, ...] = (
    FlowStep(
        id="authorize",
        title="授权店铺",
        actor="user",
        user_input="点一次「连接国际站」，在官方页确认授权",
        apis=("openapi-auth.alibaba.com/oauth/authorize", "/auth/token/create"),
        notes="不要收集店铺密码。session 过期后静默刷新或重新授权。",
    ),
    FlowStep(
        id="shop_defaults",
        title="店铺默认（只填一次）",
        actor="shop",
        user_input="询盘/一口价、币种、港口、付款、交期、运费模板、包装",
        apis=(
            "/alibaba/icbu/product/group/get",
            "/alibaba/wholesale/shippingline/template/list",
        ),
        schema_fields=SHOP_DEFAULTS,
        notes="这些是经营策略，AI 不该猜。填完后后面每条商品自动套用。",
    ),
    FlowStep(
        id="drop_assets",
        title="投料",
        actor="user",
        user_input="拖入 1～6 张图；建议再填货号、FOB/售价、MOQ。没图时写出品名，由平台生成 6 张套图",
        apis=(),
        notes="这是用户每条商品真正要做的事。没图时平台按类目生成套图，并标黄提醒不是实拍。",
    ),
    FlowStep(
        id="understand",
        title="AI 看图理解",
        actor="ai",
        user_input="无",
        apis=(),
        notes="一次多模态调用，产出品名、颜色、材质、规格、用途、套装、图质量。不在这一步写标题。",
    ),
    FlowStep(
        id="predict_category",
        title="预测叶子类目",
        actor="ai",
        user_input="仅当 Top1 置信度低时选一下",
        apis=("/alibaba/icbu/product/schema/get",),
        notes="先在缓存的类目树里检索，再让模型在候选里选。必须落到 leaf_category=true。",
    ),
    FlowStep(
        id="load_schema",
        title="拉取该类目发布规则",
        actor="system",
        user_input="无",
        apis=("/alibaba/icbu/product/schema/get",),
        notes="返回 XML。必填、选项、长度、正则都以 schema 为准，不要写死表单。",
    ),
    FlowStep(
        id="align_attributes",
        title="属性对齐到官方 option",
        actor="ai",
        user_input="对不上的属性标红，点一下",
        apis=(),
        schema_fields=("icbuCatProp", "saleProp"),
        notes="Color=Black 必须变成 p-191288010 的官方 value_id。对不上不要硬写自定义值。",
    ),
    FlowStep(
        id="write_copy",
        title="生成英文标题 / 关键词 / 详情",
        actor="ai",
        user_input="无，先填再给人审",
        apis=(),
        schema_fields=("productTitle", "productKeywords", "superText"),
        notes="标题 ≤128 字节、关键词 1～3 个、禁中文、禁邮箱、禁 HTML。先质检再给人核对，人不点审过不能发。",
    ),
    FlowStep(
        id="upload_photos",
        title="图片进图片银行",
        actor="system",
        user_input="无",
        apis=("/alibaba/icbu/photobank/upload",),
        schema_fields=("scImages",),
        notes="外链和商品详情里扒的图都不能直接发。必须拿到 url + fileId。",
    ),
    FlowStep(
        id="review",
        title="核对（人审 AI 填的）",
        actor="user",
        user_input="改错的标题/属性，点「审过了」才能发",
        apis=(),
        schema_fields=USER_FIELDS + ("productTitle", "icbuCatProp", "saleProp"),
        notes="AI 会填错类目和规格。绿的也要人看一眼。没审过不能进队列。手改过的重新成稿不会被盖掉。",
    ),
    FlowStep(
        id="publish",
        title="排队发布",
        actor="system",
        user_input="点发布，可关掉页面",
        apis=("/icbu/product/schema/add",),
        notes="限流、重试、失败回草稿。成功记下 product_id。",
    ),
    FlowStep(
        id="online",
        title="在线商品",
        actor="user",
        user_input="需要时改价、上下架、复制",
        apis=(
            "/alibaba/icbu/product/list",
            "/alibaba/icbu/product/schema/render",
            "/alibaba/icbu/product/schema/update",
            "/alibaba/icbu/product/batch/update/display",
        ),
        notes="第二期。发品是获客，改品和多店才是留存。",
    ),
)


def user_must_do() -> list[FlowStep]:
    return [step for step in FLOW if step.actor == "user"]


def first_release_steps() -> list[FlowStep]:
    skip = {"online"}
    return [step for step in FLOW if step.id not in skip]
