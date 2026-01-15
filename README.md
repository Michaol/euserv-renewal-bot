# EUserv 免费 VPS 自动续约脚本 (Requests 版)

[![许可证: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0) ![Badge](https://hitscounter.dev/api/hit?url=https%3A%2F%2Fgithub.com%2FMichaol%2Feuserv-renewal-bot&label=&icon=github&color=%23198754&message=&style=flat&tz=Asia%2FShanghai)

一个基于 GitHub Actions 和 `requests` 库的自动化脚本，用于自动续约 [EUserv](https://www.euserv.com/) 提供的免费 VPS 计划。脚本通过精确模拟浏览器请求和邮件交互，实现无人值守的自动化续约。

---

## 目录

- [中文版](#中文版)
  - [更新记录](#更新记录)
  - [功能特性](#功能特性)
  - [配置指南](#配置指南)
  - [定时任务配置](#定时任务配置)
  - [许可证](#许可证)
  - [免责声明](#免责声明)
- [English Version](#english-version)
  - [Changelog](#changelog)
  - [Features](#features)
  - [Setup Guide](#setup-guide)
  - [Schedule Configuration](#schedule-configuration)
  - [License](#license)
  - [Disclaimer](#disclaimer)

---

## 中文版

### 更新记录

#### v2.0.0 (2026-01-15) - 中文

##### 安全性与稳定性

- 🔒 移除不安全的 `eval()`，替换为基于 AST 的安全表达式解析器
- ⏱️ 为所有 HTTP 请求添加 30 秒超时，防止脚本挂起
- 📦 锁定依赖版本，确保构建一致性

##### 代码质量

- 🏗️ 新增 `RenewalBot` 类封装全局状态，提高可测试性
- 🧪 添加 21 个单元测试覆盖核心功能
- 📝 添加类型注解和 `LogLevel` 枚举统一日志格式
- ⚡ OCR 实例缓存，避免重复加载模型

##### 配置增强

- 📧 支持自定义 `SMTP_HOST` 和 `SMTP_PORT` 环境变量
- ✅ 新增启动时配置验证，明确提示缺失项

### 功能特性

- 通过 GitHub Actions 自动续约 Euserv 免费 VPS。
- 处理登录、会话及**两步验证(2FA)**。
- **双保险验证码识别**：优先使用本地 OCR (`ddddocr`)，失败后自动切换到 TrueCaptcha API。
- 通过 IMAP 连接 Gmail 邮箱，自动获取续约 PIN 码。
- 完整实现包含 Token 验证的精确续约流程。
- 每次运行后通过邮件发送状态报告。
- 所有凭据均通过 GitHub Secrets 安全管理。

### 配置指南

要使此项目正常工作，请严格遵循以下步骤。

#### 准备工作

1. 一个正常使用的 **Euserv 免费 VPS** 账户。
2. 一个 **Gmail 邮箱账户**，并已为其生成一个**应用专用密码**。
3. **(可选)** 一个 **TrueCaptcha 账户** (`apitruecaptcha.org`)，作为本地 OCR 失败时的备用方案。
4. 一个 **GitHub 账户**。

#### 第 1 步：Fork 本仓库

点击本页面右上角的 **`Fork`** 按钮，将此项目复制到您自己的 GitHub 账户下。

> **安全建议**：请确保您没有在任何时候意外地将个人凭据提交到代码中。

#### 第 2 步：配置 GitHub Secrets

这是最关键的步骤。请进入您 Fork 后的仓库，点击 `Settings` -> `Secrets and variables` -> `Actions`，然后点击 `New repository secret` 按钮，逐一添加以下 Secret：

| Secret 名称               | 示例值                          | 描述                                                                                                                              |
| ------------------------- | ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `EUSERV_USERNAME`         | `your_euserv_username`          | 用于登录 Euserv。                                                                                                                 |
| `EUSERV_PASSWORD`         | `your_euserv_password`          | 用于登录 Euserv。                                                                                                                 |
| `EUSERV_2FA`              | `ABCD1234EFGH5678`              | **(可选)** 您在 Euserv 后台开启 2FA 时获得的**Setup key**。                                                                       |
| `CAPTCHA_USERID`          | `your_captcha_userid`           | **(可选)** 您在 TrueCaptcha 注册的 `userid`，作为本地 OCR 的备用。                                                                |
| `CAPTCHA_APIKEY`          | `xxxxxxxxxxxxxxxxxxxx`          | **(可选)** 您的 TrueCaptcha `apikey`，作为本地 OCR 的备用。                                                                       |
| `EMAIL_HOST`              | `imap.gmail.com`                | 您的邮箱 IMAP 服务器地址。                                                                                                        |
| `EMAIL_USERNAME`          | `your_email@gmail.com`          | 您的完整邮箱地址。                                                                                                                |
| `EMAIL_PASSWORD`          | `abcd efgh ijkl mnop`           | 您的邮箱**应用专用密码**。                                                                                                        |
| `NOTIFICATION_EMAIL`      | `your_notify_email@example.com` | 用于接收运行报告的邮箱地址。                                                                                                      |
| `SMTP_HOST`               | `smtp.gmail.com`                | **(可选)** 手动指定 SMTP 服务器。若不提供，将尝试从 IMAP 配置推断。                                                               |
| `SMTP_PORT`               | `587`                           | **(可选)** 手动指定 SMTP 端口。默认为 587。                                                                                       |
| `PAT_WITH_WORKFLOW_SCOPE` | `ghp_xxxxxxxxxxxx`              | **(推荐)** 用于动态调度的 [Personal Access Token](https://github.com/settings/tokens/new?scopes=workflow)，需要 `workflow` 权限。 |

**请务必确保 Secret 名称与上表完全一致，并将示例值替换为您自己的真实信息。**

> **关于 2FA**: 强烈建议您在 Euserv 后台开启 2FA。这不仅能极大地增强您账户的安全性，还很有可能让服务器信任您的登录行为，从而**跳过图片验证码识别**，为您节省 API 调用费用。

#### 第 3 步：手动运行工作流进行测试

1. 点击仓库顶部的 `Actions` 标签页。
2. 在左侧选择 `Euserv VPS Renewal` 工作流。
3. 点击 `Run workflow` 按钮来手动触发一次运行。
4. 您可以点击运行中的任务，实时查看日志输出。

脚本默认在请求 PIN 码后等待 **30 秒** 再去邮箱中读取。如果您的邮件接收有延迟，可以修改 `Euserv_Renewal.py` 文件顶部的 `WAITING_TIME_OF_PIN` 常量，例如改为 `60`。

### 定时任务配置

脚本采用**动态调度机制**：

| 特性     | 说明                                                               |
| -------- | ------------------------------------------------------------------ |
| 动态调度 | 续约完成后自动更新 cron 为下次续约日期，只在需要时运行，零额外消耗 |
| 失败重试 | 失败后每 30 分钟重试，最多 3 次                                    |
| 跨天续试 | 当天全部失败后，第二天自动继续尝试                                 |
| PAT 要求 | 需要配置 `PAT_WITH_WORKFLOW_SCOPE` Secret 以启用动态调度           |

创建 PAT：[点击这里](https://github.com/settings/tokens/new?scopes=workflow) （勾选 `workflow` 权限）

### 许可证

该项目根据 **GNU General Public License v3.0** 许可证授权。详情请参阅 `LICENSE` 文件。

### 免责声明

- 本项目按“原样”提供，作者不对任何因使用此脚本可能导致的服务中断、数据丢失或其他损失负责。
- EUserv 随时可能更改其网站结构或续约流程，这可能导致此自动化脚本失效。
- 请自行承担使用风险。

---

## English Version

### Changelog

#### v2.0.0 (2026-01-15) - English

##### Security and Stability

- 🔒 Replaced unsafe `eval()` with AST-based safe expression parser
- ⏱️ Added 30-second timeout to all HTTP requests
- 📦 Locked dependency versions for consistent builds

##### Code Quality

- 🏗️ Added `RenewalBot` class to encapsulate global state
- 🧪 Added 21 unit tests covering core functionality
- 📝 Added type annotations and `LogLevel` enum for unified logging
- ⚡ Cached OCR instance to avoid reloading model

##### Configuration

- 📧 Support for custom `SMTP_HOST` and `SMTP_PORT` environment variables
- ✅ Added startup config validation with clear error messages

### Features

- Automated renewal of Euserv free VPS via GitHub Actions.
- Handles login, sessions, and **Two-Factor Authentication (2FA)**.
- **Hybrid CAPTCHA solving**: Uses local OCR (`ddddocr`) first, falls back to TrueCaptcha API if needed.
- Retrieves renewal PINs from a Gmail account via IMAP.
- Implements the complete and precise renewal workflow, including token exchange.
- Sends a run status report to your email after each execution.
- All credentials are managed securely via GitHub Secrets.

### Setup Guide

Please follow these steps carefully to get the workflow running.

#### Prerequisites

1. An active **Euserv Free VPS** account.
2. A **Gmail account** for which you have generated an **App Password**.
3. **(Optional)** A **TrueCaptcha** account (`apitruecaptcha.org`) as a fallback for local OCR.
4. A **GitHub account**.

#### Step 1: Fork the Repository

Click the **`Fork`** button at the top-right of this page to copy this project to your own GitHub account.

> **Security Recommendation**: Please ensure you have not accidentally committed any personal credentials to the codebase at any time.

#### Step 2: Configure GitHub Secrets

This is the most critical step. Navigate to your forked repository, go to `Settings` -> `Secrets and variables` -> `Actions`, and click `New repository secret` to add each of the following secrets:

| Secret Name               | Example Value                   | Description                                                                                                                                          |
| ------------------------- | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `EUSERV_USERNAME`         | `your_euserv_username`          | Your username for EUserv.                                                                                                                            |
| `EUSERV_PASSWORD`         | `your_euserv_password`          | Your password for EUserv.                                                                                                                            |
| `EUSERV_2FA`              | `ABCD1234EFGH5678`              | **(Optional)** The **Setup key** you get when enabling 2FA in your Euserv account.                                                                   |
| `CAPTCHA_USERID`          | `your_captcha_userid`           | **(Optional)** Your `userid` from TrueCaptcha, used as fallback for local OCR.                                                                       |
| `CAPTCHA_APIKEY`          | `xxxxxxxxxxxxxxxxxxxx`          | **(Optional)** Your `apikey` from TrueCaptcha, used as fallback for local OCR.                                                                       |
| `EMAIL_HOST`              | `imap.gmail.com`                | Your email provider's IMAP server.                                                                                                                   |
| `EMAIL_USERNAME`          | `your_email@gmail.com`          | Your full email address.                                                                                                                             |
| `EMAIL_PASSWORD`          | `abcd efgh ijkl mnop`           | Your email **App Password**.                                                                                                                         |
| `NOTIFICATION_EMAIL`      | `your_notify_email@example.com` | The email address to receive status reports.                                                                                                         |
| `SMTP_HOST`               | `smtp.gmail.com`                | **(Optional)** Manually specify SMTP server. Infers from IMAP if not provided.                                                                       |
| `SMTP_PORT`               | `587`                           | **(Optional)** Manually specify SMTP port. Defaults to 587.                                                                                          |
| `PAT_WITH_WORKFLOW_SCOPE` | `ghp_xxxxxxxxxxxx`              | **(Recommended)** [Personal Access Token](https://github.com/settings/tokens/new?scopes=workflow) for dynamic scheduling. Requires `workflow` scope. |

**Ensure the secret names are copied exactly and replace the example values with your own real information.**

> **About 2FA**: It is highly recommended to enable 2FA in your Euserv account. Not only does it significantly improve your account security, but it may also cause the server to trust your login and **skip the image CAPTCHA**, saving you API costs.

#### Step 3: Manually Run the Workflow to Test

1. Go to the **`Actions`** tab in your repository.
2. Select the **`Euserv VPS Renewal`** workflow from the sidebar.
3. Click the **`Run workflow`** button to trigger a manual run.
4. You can click on the running job to view the live logs.

By default, the script waits for **30 seconds** after requesting a PIN before checking your email. If you experience email delays, you can edit the `WAITING_TIME_OF_PIN` constant at the top of the `Euserv_Renewal.py` file (e.g., set it to `60`).

### Schedule Configuration

The script uses a **dynamic scheduling mechanism**:

| Feature          | Description                                                                     |
| ---------------- | ------------------------------------------------------------------------------- |
| Dynamic Schedule | Automatically updates cron to next renewal date after completion, zero overhead |
| Retry on Failure | Retries every 30 minutes on failure, up to 3 times                              |
| Cross-day Retry  | Automatically retries the next day if all attempts fail                         |
| PAT Required     | Requires `PAT_WITH_WORKFLOW_SCOPE` Secret for dynamic scheduling                |

Create PAT: [Create a Personal Access Token with workflow scope](https://github.com/settings/tokens/new?scopes=workflow)

### License

This project is licensed under the **GNU General Public License v3.0**. See the `LICENSE` file for details.

### Disclaimer

- This project is provided "as is". The author is not responsible for any loss of service, data, or other damages that may result from its use.
- EUserv may change its website structure or renewal process at any time, which could break this automation.
- Use at your own risk.
