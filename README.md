# YouTube Subscription Summaries

这个项目提供了一个命令行工具，帮助你抓取自己 YouTube 账户的订阅视频，在指定的发布时间范围内为每个视频生成 Gemini 总结，并把结果保存为 Markdown 文档，同时支持自动上传到 Notion。

⚠️ 由于涉及用户隐私与授权，仓库中不包含任何密钥或令牌，运行前请根据下方说明准备好对应的凭证。

## 功能概览

- 使用 OAuth 授权访问你订阅的频道列表。
- 在指定的时间范围内筛选每个频道发布的视频。
- 调用 Gemini 模型为每个视频生成 3-5 条要点总结。
- 输出包含视频链接、发布时间、总结的 Markdown 文档。
- 可选地，把结果上传到 Notion 数据库或页面中。

## 快速开始

1. **安装依赖**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **准备 Google OAuth 凭证**

   - 进入 [Google Cloud Console](https://console.cloud.google.com/) 新建或选择一个项目，启用 *YouTube Data API v3*。
   - 在“OAuth 同意屏幕”中添加测试用户（你的 Google 账号）。
   - 创建“桌面应用”类型的 OAuth 客户端 ID，并下载 `client_secret.json` 文件，把它放在仓库根目录。
   - 首次运行时会弹出浏览器要求授权，授权后生成的 `token.json` 会被保存在根目录，用于后续调用。

   如果希望自定义文件位置，可以通过环境变量覆盖：

   - `YOUTUBE_CLIENT_SECRETS`：`client_secret.json` 文件路径。
   - `YOUTUBE_TOKEN_FILE`：保存授权令牌的路径。

3. **配置 Gemini**

   - 访问 [Google AI Studio](https://aistudio.google.com/) 创建 API Key。
   - 将密钥设置到环境变量 `GEMINI_API_KEY`。
   - 可选的 `GEMINI_MODEL` 环境变量可用于更换模型（默认 `gemini-1.5-flash`）。

4. **配置 Notion（可选）**

   - 在 [Notion](https://www.notion.so/my-integrations) 创建内部集成，复制生成的密钥。
   - 将密钥保存到环境变量 `NOTION_API_KEY`。
   - 如果希望把内容写入数据库，设置 `NOTION_DATABASE_ID`；若直接写到已有页面，则设置 `NOTION_PARENT_PAGE_ID`。两者至少提供一个。

5. **运行示例**

   ```bash
   python -m youtube_summary.main \
     --start 2024-06-01T00:00:00+08:00 \
     --end 2024-06-07T23:59:59+08:00 \
     --language zh-CN \
     --title "本周订阅视频总结"
   ```

   命令会：

   - 授权访问你的 YouTube 订阅。
   - 筛选指定时间段内发布的视频。
   - 调用 Gemini 生成中文总结。
   - 把结果写入 `subscription_summaries.md`。
   - 如果配置了 Notion，自动创建新页面并填入内容。

   其他常用参数：

   - `--max-per-channel`：限制每个频道最多抓取的视频数量。
   - `--skip-gemini`：跳过调用 Gemini，仅输出视频元数据。
   - `--skip-notion`：跳过上传到 Notion。
   - `--output`：自定义输出 Markdown 路径。

## 输出示例

生成的 Markdown 文件大致如下：

```markdown
# 本周订阅视频总结

Time window: 2024-06-01T00:00:00+08:00 — 2024-06-07T23:59:59+08:00

## Awesome Talk – 如何系统学习
*Channel:* Learning Lab
*Published:* 2024-06-02T12:30:00+08:00
*Link:* https://www.youtube.com/watch?v=dQw4w9WgXcQ

- 关键要点 1
- 关键要点 2
- 关键要点 3
```

实际内容由 Gemini 生成，可能包含更多要点或行动建议。

## 常见问题

- **授权失败怎么办？**
  确认 OAuth 同意屏幕中已添加你的 Google 账号为测试用户，并确保 `client_secret.json` 与 `token.json` 文件权限正确。

- **如何重新授权？**
  删除 `token.json` 后重新运行程序即可触发新的授权流程。

- **Gemini 调用失败**
  检查 `GEMINI_API_KEY` 是否有效，以及当前项目是否有访问 Gemini 的权限。可使用 `--skip-gemini` 参数跳过总结步骤。

- **Notion 写入失败**
  确认集成已被邀请到目标数据库/页面，并验证 `NOTION_DATABASE_ID` 或 `NOTION_PARENT_PAGE_ID` 是否填写正确。

## 许可协议

本项目以 MIT 协议开源，详情参见 [LICENSE](LICENSE)（如未包含，可根据需要自行添加）。
