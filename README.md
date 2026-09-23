# Action Memo：录音豆个人行动纪要

这是一个面向 soundcore Work 3200 黑客松的 MVP。它把录音或会议转写内容整理为当前用户需要处理的行动项，并保留原文依据。

## 能做什么

- 直接粘贴中文会议转写，或上传音频、视频录音
- 生成个人任务清单；明确且有截止时间的任务进入“我的任务清单”，需要确认或补充时间的任务进入“模糊任务清单”
- 用户可以修改模糊任务、补充截止时间并确认归入自己的清单
- 识别多人共同负责的任务与跨句出现的截止时间
- 让每条任务回溯到原始说话人和时间戳
- 在网页中确认、修改或忽略任务
- 将会议转写、任务清单与人工判断保存在本机“录音库”，后续分析会参考个人工作画像
- 只保留“动作 + 明确对象”的具体任务；模糊的“跟进一下、处理这个”等表述不会进入待办或个人画像
- 未配置 API Key 时仍可打开并查看本地兜底 Demo

## 首次运行

### 1. 克隆项目

```bash
git clone https://github.com/Wanft11/action-memo-demo.git
cd action-memo-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. 配置自己的 OpenAI API Key

在 Mac 上直接用文本编辑器打开 `.env`：

```bash
open -e .env
```

如果使用 VS Code：

```bash
code .env
```

把文件中的这一行：

```env
OPENAI_API_KEY=""
```

改为自己的 Key：

```env
OPENAI_API_KEY="你的 OpenAI API Key"
```

保存即可。每位队友使用自己的 Key；`.env` 不会被上传到 GitHub。

### 3. 启动 Demo

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

浏览器打开：<http://127.0.0.1:8000/demo>

没有 API Key 时，页面仍会打开并显示兜底示例。真实录音转写和 AI 会议分析需要配置 Key。

### 快速试跑样本

Demo 页面有“加载测试转写”按钮，可从 11 份不同场景的样本中选择。每份样本约 10–15 分钟，每轮发言间隔 5–15 秒。测试样本预设账号本人标为“小万”，其他发言者保留为“说话人 1/2/3”；对话中实际说出口的姓名仍按原话保留。加载样本后会自动选中“小万”，但真实录音目前不具备自动声纹认人的能力，仍需人工确认。预赛样本在 `static/samples/recording-bean-preliminary-meeting.txt`。

### 测试“个人重点”

点击“个人重点”，输入一个具体问题，例如“技术流程什么时候能给出？”，再点击“生成个人重点”。页面会给出围绕该问题的回答和原文依据；你也可以在“复查索引”中粘贴一句话或一段原文，定位并复制对应的会议片段。

### 本机录音库与个人画像

生成任务清单后点击“保存到录音库”，转写、分析结果、任务确认和文件夹关键词/称呼会保存在本机 `.action-memo/action_memo.db`。文件夹卡片上的“编辑”可修改关键词和称呼；刷新或重启后仍会保留。打开“个人画像”可查看人工反馈；下一次调用 AI 分析时，系统只检索相关的已确认/已排除任务标题作为辅助上下文，不会上传旧会议全文，也不会覆盖会议原文中明确的负责人。该目录已被 Git 忽略，修改不会自动上传到 GitHub。

### 安装团队共享的脱敏测试库

仓库中的 `static/samples/action_memo_demo.db` 是一份脱敏测试数据库，包含两场虚构会议、三个场景文件夹和示例关键词/称呼，不含任何本机真实记录或音频。队友拉取最新代码后，可在项目根目录执行：

```bash
mkdir -p .action-memo
cp static/samples/action_memo_demo.db .action-memo/action_memo.db
```

然后刷新 Demo，在“我的账号”填写 `演示用户`，打开“录音库”即可查看和编辑相同的测试文件夹。**复制命令会覆盖本机已有数据库**；如已有自己的记录，请先备份 `.action-memo/action_memo.db`。仓库中的演示库只是共享快照：每个人后续在页面上修改的关键词、称呼和任务仍仅保存在自己的电脑，不会实时同步给队友。如需重新生成仓库版本，执行：

```bash
.venv/bin/python scripts/create_demo_database.py
```

### 安装当前团队测试快照

`static/samples/action_memo_team.db` 是当前本机录音库的手动快照，包含此前用于测试的“录音豆预赛方案讨论”文字、生成结果和六个文件夹设置；没有音频文件。它与上面的脱敏演示库是两个可选测试起点。需要测试同一份记录时，在项目根目录运行：

```bash
mkdir -p .action-memo
cp static/samples/action_memo_team.db .action-memo/action_memo.db
```

刷新 Demo，并将“我的账号”设为 `小万`。**复制会覆盖已有本机数据库，请先备份。**后续在页面上修改记录、关键词或称呼不会自动同步到 GitHub；只有经过检查并重新提交快照后，队友才能取得更新。真实会议或录音加入本机库后，不要直接重新上传这个快照。GitHub 旧提交也会保留已上传的内容，之后删除文件不能抹去历史版本。

## 团队协作

仓库目前是私有的。先由仓库管理员在 GitHub 的 `Settings → Collaborators` 邀请队友，接受邀请后即可访问和提交代码。

### 在 GitHub 网页直接编辑或上传

适合修改文案、README 或上传小型测试文件：

1. 打开仓库，进入要修改的文件，点击右上角铅笔图标。
2. 修改完成后，在页面底部填写本次修改说明，点击 `Commit changes`。
3. 上传文件时点击 `Add file → Upload files`，把文件拖入页面后提交。

### 在本地修改并推送

适合修改前端、后端或多个文件。每次开始前先同步最新代码：

```bash
git pull origin master
```

修改并保存后，先查看这次会上传什么：

```bash
git status
```

再提交指定文件并推送：

```bash
git add static/index.html
git commit -m "优化任务卡片展示"
git push origin master
```

改后端时，把 `static/index.html` 换成实际修改的文件路径，例如：

```bash
git add app/services/meeting_analyzer.py
git commit -m "改进待办提取逻辑"
git push origin master
```

多人同时改同一个文件时，先 `git pull origin master` 再开始修改；每次提交只包含一件清晰的小修改，之后更容易合并和回退。

### 测试录音文件

可在项目里新建 `samples/` 文件夹，存放允许团队共享的测试音频。不要上传包含隐私内容的真实会议录音，也不要上传 API Key、`.env` 或个人账号信息。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 接口

- `GET /api/health`：检查服务是否启动。
- `POST /api/meetings/analyze`：接收 `current_user`、`transcript`、可选 `audio` 和 `markers`，返回会议分析结果。
- `POST /api/meetings/focus`：接收 `current_user`、`transcript` 和 `focus_query`，返回个人重点及可复查的原文依据。
- `GET /docs`：打开接口文档。
