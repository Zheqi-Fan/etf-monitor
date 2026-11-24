# 部署到 Cloudflare Pages（隐藏源码）

目标：**网页公开可访问，但 Python 项目代码不公开**。

```
私有仓 Zheqi-Fan/etf-monitor-app  ──push──▶  Cloudflare Pages
        （含全部源码）                        python build_site.py
                                                    ↓
                                            公开网址（只暴露 dist/）
```

> 注意：网页的 HTML/CSS/JS 必然对访客可见（浏览器要下载才能渲染）。
> 本方案隐藏的是**数据管道与方法论**（`fetch_data.py`、`config.py`、`research/` 等）。

---

## 一、一次性配置（约 3 分钟）

### 1. 注册 Cloudflare

打开 https://dash.cloudflare.com/sign-up ，用邮箱注册（免费，无需域名、无需信用卡）。

### 2. 创建 Pages 项目

1. 左侧菜单 **Workers & Pages** → **Create** → **Pages** → **Connect to Git**
2. 授权 GitHub，**只选中** `etf-monitor-app`（私有仓）
3. 点 **Begin setup**，然后填写：

| 字段 | 填什么 |
|---|---|
| Project name | `etf-monitor`（决定网址前缀，可自定义） |
| Production branch | `main` |
| Framework preset | **None** |
| **Build command** | `python build_site.py` |
| **Build output directory** | `dist` |
| Root directory | *(留空)* |

4. **Environment variables**（可选，建议加）：

| 变量 | 值 |
|---|---|
| `PYTHON_VERSION` | `3.11` |

5. 点 **Save and Deploy**，等 1–2 分钟。

### 3. 拿到网址

部署成功后上方显示：

```
https://etf-monitor.pages.dev
```

（若项目名不同，网址随之变化；也可在 **Custom domains** 绑自己的域名。）

---

## 二、之后的日常更新

数据更新流程不变：

```bash
cd "ETF Monitor"
python3 run_update.py
```

脚本会：抓数 → 校验 → 构建 `dist/` → 提交 → **推送到私有仓** → Cloudflare 自动重新构建发布。

`.env` 里的控制项：

```bash
# 只推私有仓（源码不公开）
PUBLISH_REMOTES=private

# 若想让旧 GitHub Pages 也同步更新（源码仍公开）
PUBLISH_REMOTES=private origin
```

---

## 三、验证清单

| 检查 | 命令 / 位置 |
|---|---|
| Cloudflare 构建成功 | Pages 项目 → **Deployments**，最新一条为 `Success` |
| 页面能打开 | 访问 `https://<项目名>.pages.dev` |
| 数据日期正确 | 页面顶部「数据截至」；或访问 `/data/status.js` |
| 源码未暴露 | 用无痕窗口打开 `https://github.com/Zheqi-Fan/etf-monitor-app` → 应返回 404 |
| 旧站仍在线 | 原 `https://zheqi-fan.github.io/etf-monitor/` 可访问（数据冻结） |

---

## 四、收尾：彻底撤下旧公开仓

新站确认稳定后，删除或转私有旧仓（**否则源码仍然公开**）：

- 转私有：`Settings` → 最下方 `Change visibility` → `Make private`
  - ⚠️ 免费账号私立仓的 GitHub Pages 会**同时下线**，旧站失效
- 彻底删除：`Settings` → `Delete this repository`
  - ⚠️ 不可恢复；`forks = 0`，已确认无他人副本
- 注意：GitHub 搜索、第三方镜像、搜索引擎缓存可能仍留有旧记录，删除后需数周才会自然消退

---

## 五、常见问题

**构建失败 `python: command not found`**
→ 环境变量加 `PYTHON_VERSION=3.11`；仍失败则改用 `python3 build_site.py`

**页面样式全丢 / 图表空白**
→ 检查 Build output directory 是否填 `dist`（不是 `/dist`）

**更新后页面没变**
→ Cloudflare Pages 默认缓存 HTML；页面已设 `no-cache`，强制刷新（`Cmd+Shift+R`）确认

**想绑自定义域名**
→ Pages 项目 → **Custom domains** → 添加，按提示改 DNS
