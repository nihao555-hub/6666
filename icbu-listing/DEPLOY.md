# 公网部署（Production）

**生产地址：** https://icbu-listing.vercel.app

**生产分支：** `videos-dataset`（仓库默认分支）

## 规则（Cloud Agent / 开发者必读）

1. 功能开发在 `cursor/<name>-20a1` 分支完成并测试。
2. **合并 PR 到 `videos-dataset`**（或直接在 `videos-dataset` 上提交）。
3. **触发 Vercel 生产部署** — 任选其一：
   - 推送 `videos-dataset` 后 GitHub Actions 自动部署（需配置 `VERCEL_TOKEN` secret）
   - 本地/Agent：`VERCEL_TOKEN=… ./scripts/deploy-production.sh`
4. 部署后验证：
   - `curl https://icbu-listing.vercel.app/api/v1/health` 中 `git_sha` 与最新 commit 一致
   - 前端 Feed 包含预期功能（例如 `useEcosystemAssistant`）

**不要**只推 feature 分支就结束 — 公网不会更新，除非合并到 `videos-dataset` 并完成 Vercel 部署。

## GitHub Actions

工作流：`.github/workflows/deploy-production.yml`

在仓库 **Settings → Secrets → Actions** 添加：

| Secret | 说明 |
|--------|------|
| `VERCEL_TOKEN` | Vercel 账号 Token（与本地 `vercel deploy --prod` 相同） |

## 手动部署

```bash
cd icbu-listing
export VERCEL_TOKEN="your-token"
./scripts/deploy-production.sh
```

## Vercel 项目

- Project: `icbu-listing`
- Root directory: `icbu-listing`（`vercel.json` 在此目录）
- Production alias: `icbu-listing.vercel.app`
