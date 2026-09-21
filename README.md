# Action Memo：录音豆个人行动纪要

这是一个面向 soundcore Work 3200 黑客松的 MVP。它把录音或会议转写内容整理为每个人真正需要处理的行动项，并显示负责人、截止时间、置信度和原文依据。

## 能做什么

- 直接粘贴中文会议转写，或上传音频、视频录音
- 提取“我的待办”和“全部待办”
- 识别多人共同负责的任务与跨句出现的截止时间
- 让每条任务回溯到原始说话人和时间戳
- 在网页中确认、修改或忽略任务
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
- `GET /docs`：打开接口文档。
