# GitHub Pages 一键部署（Git Bash 里运行）

## 第一步：登录 GitHub（只需一次）

```bash
gh auth login
# 选 GitHub.com → HTTPS → Login with a web browser → 复制验证码到浏览器
```

若提示 `gh: command not found`，先**关闭并重新打开** Git Bash（已安装 GitHub CLI）。

---

## 第二步：创建仓库并推送

把 `YOUR_GITHUB_USERNAME` 换成你的 GitHub 用户名（登录 github.com 右上角可见）。

### 方式 A：用户站点 `https://用户名.github.io`（推荐）

```bash
cd /d/DESKTOP/fifa
git branch -M main

gh repo create YOUR_GITHUB_USERNAME.github.io --public --source=. --remote=origin --push
```

### 方式 B：项目站点 `https://用户名.github.io/fifa-odds/`

```bash
cd /d/DESKTOP/fifa
git branch -M main

gh repo create fifa-odds --public --source=. --remote=origin --push
```

---

## 第三步：开启 GitHub Pages

```bash
# 用户站点
gh api repos/YOUR_GITHUB_USERNAME/YOUR_GITHUB_USERNAME.github.io/pages -X POST -f build_type=workflow

# 或在网页：仓库 → Settings → Pages → Source 选 GitHub Actions
```

首次 push 后 Actions 会自动构建；约 2～5 分钟可访问：

- 用户站点：`https://YOUR_GITHUB_USERNAME.github.io`
- 项目站点：`https://YOUR_GITHUB_USERNAME.github.io/fifa-odds/`

查看部署状态：

```bash
gh run list
gh run watch
```

---

## 更新机制

- **GitHub Actions** 每 15 分钟自动抓 Polymarket + 体育彩票，生成静态页面
- 无需自己跑服务器
- 手动触发：`gh workflow run pages.yml`

---

## 无 gh 时（纯 git）

1. 在 https://github.com/new 创建仓库 `YOUR_GITHUB_USERNAME.github.io`
2. 执行：

```bash
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/YOUR_GITHUB_USERNAME.github.io.git
git branch -M main
git push -u origin main
```

3. 仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**
