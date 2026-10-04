# GitHub 项目同步到服务器操作指南

适用项目：`Global-CS-Paper-Awards-Agent`，GitHub 仓库：`peekabooXT/Global-CS-Paper-Awards-Agent`。

## 一、日常同步的推荐流程

先通过 SSH 登录服务器，并进入服务器上的项目目录：

```bash
ssh 用户名@服务器IP
cd /opt/Global-CS-Paper-Awards-Agent
```

### 1. 同步前检查

```bash
git status
git branch --show-current
git remote -v
```

重点确认：

- 当前分支是不是实际部署分支，例如 `main`；
- 服务器上是否存在未提交修改；
- `origin` 是否指向正确的 GitHub 仓库。

### 2. 获取并查看 GitHub 更新

以下示例假设部署分支是 `main`；如果实际使用其他分支，请替换分支名。

```bash
git fetch origin
git log --oneline HEAD..origin/main
```

如果第二条命令显示提交记录，说明 GitHub 上有服务器尚未同步的更新。

### 3. 拉取最新代码

```bash
git pull --ff-only origin main
```

使用 `--ff-only` 可以避免服务器在不知情的情况下自动生成合并提交。同步成功后，可执行：

```bash
git status
git log -1 --oneline
```

确认工作区干净，并核对最新提交。

## 二、更新本项目的 Python 依赖

本项目网页依赖记录在 `requirements-web.txt`。GitHub 更新如果修改了依赖文件，在服务器执行：

```bash
cd /opt/Global-CS-Paper-Awards-Agent
.venv/bin/python -m pip install -r requirements-web.txt
```

如果服务器没有使用项目内的 `.venv`，可改用：

```bash
python -m pip install -r requirements-web.txt
```

如需使用项目的 PDF 功能，再安装：

```bash
.venv/bin/python -m pip install -r requirements-pdf.txt
```

## 三、重启服务

如果网页由 systemd 管理，更新后执行：

```bash
sudo systemctl restart global-cs-paper-awards-agent.service
sudo systemctl status global-cs-paper-awards-agent.service
```

如需查看最近日志：

```bash
sudo journalctl -u global-cs-paper-awards-agent.service -n 100 --no-pager
```

如果目前是在终端中手动启动，可使用项目命令：

```bash
.venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

公网部署还应确认 GitHub 发布功能所需的服务器环境变量仍然存在，包括：

- `GITHUB_TOKEN`
- `GITHUB_REPOSITORY`
- `GITHUB_BRANCH`
- `PUBLISH_PASSWORD_SHA256`

不要把真实 Token、密码或 `.env` 文件提交到 GitHub。

## 四、服务器存在本地修改时怎么办

如果 `git status` 显示服务器上有未提交修改，不要立即执行强制覆盖。

可以先查看修改：

```bash
git diff
git status --short
```

如果这些修改需要保留，可先临时保存：

```bash
git stash push -u -m "server changes before GitHub update"
git pull --ff-only origin main
git stash pop
```

执行 `git stash pop` 后若出现冲突，需要人工决定保留 GitHub 版本还是服务器版本。

只有在明确确认“服务器本地修改全部不要，必须与 GitHub 完全一致”时，才使用：

```bash
git fetch origin
git reset --hard origin/main
```

警告：`git reset --hard` 会丢弃已跟踪文件中的未提交修改。未跟踪文件不会被这条命令删除，但也不建议在未检查前执行额外的清理命令。

## 五、首次部署时

如果服务器上还没有该项目：

```bash
git clone https://github.com/peekabooXT/Global-CS-Paper-Awards-Agent.git
cd Global-CS-Paper-Awards-Agent
python -m venv .venv
.venv/bin/python -m pip install -r requirements-web.txt
.venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

私有仓库建议为服务器配置专用 SSH Key 或 Deploy Key，不要在命令或脚本中明文保存 GitHub 密码。

## 六、最简日常命令清单

```bash
cd /opt/Global-CS-Paper-Awards-Agent
git status
git fetch origin
git pull --ff-only origin main
.venv/bin/python -m pip install -r requirements-web.txt
sudo systemctl restart global-cs-paper-awards-agent.service
sudo systemctl status global-cs-paper-awards-agent.service
```

## 七、当前项目 `tmp` 文件夹里有什么

检查时间：2026-09-28。

当前 `tmp` 目录结构如下：

```text
tmp/
└─ pdfs/
   └─ schema_driven/
      ├─ paper.txt
      └─ render/
         ├─ page-1.png
         ├─ page-3.png
         ├─ page-4.png
         ├─ page-5.png
         ├─ page-6.png
         ├─ page-7.png
         └─ page-8.png
```

这些文件的含义：

- `paper.txt`：从一篇 PDF 中提取出的文本，约 322 KB；
- `render/page-*.png`：PDF 页面渲染得到的图片，现有第 1 页和第 3～8 页，每张约 394～520 KB；
- 没有发现项目代码引用 `tmp/pdfs/schema_driven`；
- Git 当前显示 `?? tmp/`，说明整个 `tmp` 目录尚未被 Git 跟踪；
- 当前 `.gitignore` 没有忽略 `tmp/`，所以它会持续出现在 `git status` 中。

从现有内容判断，这是处理或检查 PDF 时产生的临时中间文件，不是项目运行所必需的正式源码或数据。确认以后不需要这些 PDF 检查结果时，可以删除；如果希望保留在本机但不上传 GitHub，建议在 `.gitignore` 中加入：

```gitignore
tmp/
```

删除或修改 `.gitignore` 前，仍建议先确认这些文件没有需要长期保存的人工检查结果。

## 八、同步失败时的快速诊断

```bash
git status
git branch -vv
git remote -v
git fetch origin
git log --oneline --decorate --graph -10
```

常见情况：

- `Permission denied (publickey)`：服务器 SSH Key 未配置或 GitHub 未授权；
- `Authentication failed`：HTTPS 凭据或 Token 无效；
- `Not possible to fast-forward`：服务器分支存在额外提交，需要先比较差异；
- `Your local changes would be overwritten`：服务器有未提交修改，应先查看、提交或暂存；
- 更新后网页仍是旧版本：检查服务是否重启、启动目录是否正确，以及实际运行的进程是否来自该项目目录。
