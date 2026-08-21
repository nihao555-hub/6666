# AI 填表示例

本目录是 **「Excel 事实 → AI 填官方属性 → 停（不发布）」** 的本地验证产物。

## 文件

| 文件 | 说明 |
|------|------|
| `ai_filled_demo.xlsx` | 填写表 + AI填明细 + AI填宽表 + 质量摘要 |
| `ai_filled_demo.json` | 同上数据的 JSON，便于 diff / 脚本读取 |

## 如何复现

```bash
cd icbu-listing
# 需要：data/auto-shoper.db（含店铺 token + 已缓存 schema）、.env 里 OPENAI_* 
PYTHONPATH=backend:server python3 scripts/export_ai_filled_table.py
```

模型以 `.env` 为准（当前为 `TEXT_MODEL=gemini-3.1-flash-lite`，经 grsai 代理）。

## 工作表说明

1. **填写** — 卖家只填的短表（货号、价、MOQ、规格列等）
2. **AI填-明细** — 每个官方字段一行：值、显示标签、来源（excel/shop/ai）、依据摘录
3. **AI填-宽表** — 一行一个 SKU，便于和 ERP 对照
4. **质量摘要** — AI 调用次数、已填/仍缺必填、红色问题数

无依据的必填项 **不会瞎填**，在明细里标「未填-待人工」。
