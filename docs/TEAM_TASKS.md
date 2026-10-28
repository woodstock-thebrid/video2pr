# 队友任务表 (Teammate Tasks)

我们团队已完成：后端、"修复前后截图对比"、"多视频并行"和 pitch 初稿（[`docs/PITCH.md`](PITCH.md)）。
下面是队友可以认领的任务，与现有实现并行推进。做完一项就在表里打勾（直接改这个文件、提 PR，或者在群里说一声）。

> ⚠️ 规则：**不要合并 AI agent 开的修 bug 的 PR**（比如 #2、#4，以及演示中新开的）。合并后 `main` 上的 bug 就没了，台上没法演示。
> 改代码请开新分支 + PR，不要直接推 `main`。

| # | 任务 | 怎么做 / 产出 | 预计时间 | 优先级 | 完成 |
|---|------|---------------|---------|--------|------|
| 1 | **在自己电脑上跑起来（备用机）** | 见下方「本地运行」。打开 http://localhost:8000 ，用备份模式上传 `bug1` 视频，走完整个流程。台上万一我这边断网，就用你的电脑演示。 | 15 分钟 | P0 | ☑ 备份模式跑通：上传 `bug1_quantity.mp4` → 报告 → PR 链接 → 修复前后对比 |
| 2 | **用手机录真实 bug 视频** | 打开 `/demo/`，用手机对着屏幕录 bug 1（汉堡 ×2，小计 $12.50，应为 $25.00）和 bug 4（结算按钮快速连点两下，出现 Order #2）。每段 10–15 秒，画面要清楚看到数字。发到群里。 | 15 分钟 | P0 | ☑ 用浏览器录屏代替手机：[`bug1_quantity.mp4`](media/bug1_quantity.mp4)、[`bug4_double_order.mp4`](media/bug4_double_order.mp4) |
| 3 | **做 4 页 slides** | ① 痛点："it's broken" 式 bug report；② 一句话 + 架构图（视频 → 截图 → AI agent 写报告 → 复现修复 → PR）；③ 现场演示（空白页，切到浏览器）；④ AI agent 的应用场景。参考 [`docs/PITCH.md`](PITCH.md)。 | 30 分钟 | P0 | ☑ [`video2pr_slides.pptx`](media/video2pr_slides.pptx) |
| 4 | **排练 pitch 并计时** | 按 [`docs/PITCH.md`](PITCH.md) 分好 Speaker A / B，计时控制在 3 分钟内。把觉得别扭的台词直接改进文件。 | 20 分钟 | P1 | ☐ |
| 5 | **录一个完整备份视频** | 用备份模式（不消耗 AI agent API 额度）录屏：上传视频 → 报告卡片出现 → PR 链接 → 修复前后对比，约 1–2 分钟。网络或 AI agent 出问题时直接播这个。 | 20 分钟 | P1 | ☑ [`backup_mode_walkthrough.mp4`](media/backup_mode_walkthrough.mp4)（约 53 秒） |
| 6 | **手机上检查 bug 2** | 用手机打开 demo 网站，确认"结算"按钮被黄色横幅挡住（这是故意埋的 bug）。截图留着做 slides。 | 5 分钟 | P2 | ☑ 390px 宽度截图：[`bug2_mobile_comparison.png`](media/bug2_mobile_comparison.png) |
| 7 | **README 加截图/GIF** | 把任务 5 的录屏截几帧，或做成 GIF，放进 README 顶部。开 PR。 | 15 分钟 | P2 | ☑ README 顶部已加 GIF |
| 8 | **准备评委问答** | 看 [`docs/PITCH.md`](PITCH.md) 里的「Likely judge questions」，每题准备一句话答案，再补 2 个你觉得评委会问的。 | 10 分钟 | P2 | ☑ 见 [`PITCH.md`](PITCH.md) 的 One-line answers，新增 2 题 |
| 9 | **提交材料** | 确认比赛的提交方式（Devpost / 表单），填项目名、一句话描述、repo 链接、demo 视频。截止前 15 分钟交完。 | 10 分钟 | P0（最后做） | ☐ |

## 本地运行

需要 Python 3.10+ 和 ffmpeg（macOS：`brew install ffmpeg`）。

```bash
git clone https://github.com/woodstock-thebrid/video2pr.git
cd video2pr                      # ← 一定要先进项目文件夹
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 备份模式：模拟 AI agent，无需 API key，不消耗额度
MOCK_DEVIN=1 VISION_PROVIDER=devin uvicorn backend.main:app --port 8000

# 真实模式：创建真实 AI agent session 并开 PR（会消耗额度）
DEVIN_API_KEY=<你的 key> uvicorn backend.main:app --port 8000
```

- 上传页面：http://localhost:8000
- 埋了 bug 的点餐网站：http://localhost:8000/demo/
- 4 个 bug 分别是：汉堡数量不进小计、手机上结算按钮被挡、多词搜索（"chicken tenders"）搜不到、连点结算下两单。

## 时间线（建议）

| 时间 | 你 | AI agent / 我 |
|------|----|-----------|
| 现在 – +30 分钟 | 任务 1、2、6 | 修复前后对比 |
| +30 – +75 分钟 | 任务 3、5 | 多视频并行 |
| +75 – +105 分钟 | 任务 4、7、8（一起排练） | 修 bug、润色、真实模式彩排 |
| 最后 15 分钟 | 任务 9 | 冻结代码，不再改 |
