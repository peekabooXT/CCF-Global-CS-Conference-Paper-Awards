# 本地运行展示站

[English](RUNNING.md) | **简体中文**

本仓库只提供已核验论文数据、索引和只读网站。运行时无需模型服务、账户凭据或写入型管理接口。

## Python 后端

使用 Python 3.12 或更新版本，建议在独立虚拟环境中安装依赖：

```powershell
python -m pip install -r requirements-public.txt
python scripts/prepare_data.py
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

`prepare_data.py` 从版本化 JSON 创建 SQLite 文件；已有数据库时不会覆盖。更新数据前请先保存旧数据库，再准备新快照。

## 前端

```powershell
cd frontend
npm ci
npm run build
```

构建后重新启动后端，访问 `http://127.0.0.1:8000/`。开发时可运行 `npm run dev`，访问 `http://127.0.0.1:5173/`；请求转发到本机后端。

## 检查

```powershell
python scripts/validate_public_snapshot.py
node --test frontend/tests/*.test.js
```

校验检查已核验状态、论文数量、索引时间及数据库只读约束。网站只执行检索、浏览与 CSV 导出，不修改论文数据。
