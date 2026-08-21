# Alibaba ICBU Publishing Skill (vendored reference)

Upstream: https://github.com/aidi1723/alibaba-icbu-publishing-skill (MIT)

We vendor the operational guide — not official Alibaba docs — for:

- Title formula: `Core Product + Structure/Type + Performance + Scene + OEM/custom`
- Keyword clusters: exposure-oriented but inquiry-qualified
- Bulk upload safety: required fields, category fit, no duplicate filler SKUs
- Five-layer judgment: platform rules → market heat → store traction → supply fit → publish decision

Used by `server/services/smart_plan.py` and `server/services/review_enrich.py` for LLM prompts.

Title rules (from upstream SKILL.md):

- Put core product word early
- Use concrete buyer search language
- Keep OEM/custom as support words, not leading every title
- Avoid unverifiable claims without proof
- Vary by type/scene/spec/buyer role — not one adjective swaps

See upstream `references/bulk-upload-rules.md` and `references/search-ranking.md` for full detail.
