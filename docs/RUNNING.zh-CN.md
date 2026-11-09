# 本地运行展示站

[English](RUNNING.md) | **简体中文**

网站在构建时从已核验快照生成静态数据。论文总览、检索、会议年度奖项、证据详情和 CSV 导出均可通过静态服务器使用，访问者无需连接 Python API、数据库服务或模型。

## 构建并启动静态网站

使用 Python 3.12 或更新版本，以及 Node.js 20 或更新版本。数据生成脚本只依赖 Python 标准库：

```powershell
cd frontend
npm ci
npm run build
cd ..
python -m http.server 8080 --directory frontend/dist
```

访问 `http://127.0.0.1:8080/`。部署时将完整的 `frontend/dist/` 目录交给静态服务器，包括其中的 `assets/` 目录。本地也可使用 `npm run preview` 预览构建结果。

## 更新数据

通过维护流程更新版本化的 `data/exports/public-data.json`，然后重新构建并发布完整产物。构建会核对论文数量并拒绝未核验数据，生成压缩检索索引，以及分开的论文证据和年度奖项详情文件。文件名包含内容指纹，供浏览器缓存；首页始终引用同一发布版本。

筛选、排序、分页和 CSV 导出均在浏览器中处理，切换页面复用已经加载的索引。打开详情时才读取对应文件。“刷新数据”会重新加载已发布快照。

网站默认中文，右上角可切换“中文 | English”；`?lang=zh` 和 `?lang=en` 可直接选择语言。

## 可选的兼容 API

只读 Python API 继续供已有工具使用，网站本身无需连接它：

```powershell
python -m pip install -r requirements-public.txt
python scripts/prepare_data.py
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

`prepare_data.py` 不覆盖已有数据库；准备新版前请保留旧文件。

## 检查

```powershell
python scripts/validate_public_snapshot.py
node --test frontend/tests/*.test.js
```

校验检查已核验状态、论文数量、索引时间及数据库只读约束。网站只执行检索、浏览与 CSV 导出，不修改论文数据。
