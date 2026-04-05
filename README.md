# EUserv 免费 VPS 自动续约脚本 (Requests 版)

[![许可证: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0) [![Quality Gate](https://sonarcloud.io/api/project_badges/quality_gate?project=Michaol_euserv-renewal-bot)](https://sonarcloud.io/summary/new_code?id=Michaol_euserv-renewal-bot) ![Badge](https://hitscounter.dev/api/hit?url=https%3A%2F%2Fgithub.com%2FMichaol%2Feuserv-renewal-bot&label=&icon=github&color=%23198754&message=&style=flat&tz=Asia%2FShanghai)

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

#### v2.3.0 (2026-04-05) - 中文

##### 稳定性修复

- 🔴 **Session 过期自动重连**：新增 `_refresh_session()` 方法，续期流程耗时较长后自动重新登录，防止 `_check_post_renewal_status` 因 session 过期而失败
- 📧 **邮件编码兼容**：`_extract_email_body()` 使用 `part.get_content_charset()` 获取真实编码，支持多种邮件编码格式，避免 UTF-8 硬编码导致的解码失败

##### 代码质量

- 🔧 简化 `_handle_captcha` 参数（7→3），直接从实例读取凭据
- 🔧 简化 `_handle_2fa` 参数（3→1），内联 origin header 保持原始 `https://www.euserv.com`
- 🔧 `_renew` 返回值从 `bool` 改为 `None`（始终返回 True 无意义）
- 🔧 提取 `SERVER_LIST_RETRY_DELAY` 常量，替代 `sleep(30)` 硬编码
- 🗑️ 移除多余的 `http://` 重试适配器（Euserv 纯 HTTPS）

##### 测试改进

- ✅ 修正测试名 `test_parentheses_not_supported` → `test_parentheses_work`
- 🧹 移除 `test_safe_eval.py` 中未使用的 `pytest` import

##### CI 优化

- ⚡ 启用 Node.js 24，消除 GitHub Actions 弃用警告

<details>
<summary>v2.2.0 及更早版本</summary>

#### v2.2.0 (2026-02-19)

##### 关键修复

- 🔴 **修复 cron 调度不更新**：空服务器列表不再静默成功，改为 `EXIT_FAILURE` 并保存调试页面
- 🔴 **修复续约后 cron 丢失**：无论续约状态如何均输出下次续约日期
- 🔴 **修复测试套件**：修复因函数重命名导致的 ImportError（3 个测试文件）

##### 安全加固

- 🔒 2FA 密码和 PIN 码日志遮蔽，仅显示末 2 位
- 🛡️ 新增 `HTTPAdapter` + `Retry` 自动重试策略（5xx 状态码）
- 🌐 User-Agent 更新至 Chrome 131

##### 优化改进

- 🎯 使用 `ddddocr.set_ranges()` 限制字符集，提高数学验证码识别率
- 🧹 提取 `_clean_math_expr()` / `_try_solve_math()` 统一数学表达式处理
- 🧹 提取 `_parse_server_row()` 降低认知复杂度
- 📊 服务器列表解析增加行数日志，空结果保存 HTML 用于调试

#### v2.1.0 (2026-01-22)

##### 架构优化

- 🏗️ **Phase 3 架构统一**：将 15+ 顶层函数移入 `RenewalBot` 类
- 🧹 消除全局变量 `LOG_MESSAGES`, `CURRENT_LOGIN_ATTEMPT`, `_ocr_instance`
- ⚡ OCR 预热：启动时预加载模型，减少首次识别延迟
- 🔒 HTTP Session 资源管理：添加 `_cleanup()` 方法确保正确关闭

##### 测试覆盖

- 🧪 新增 pytest 测试套件 (`tests/test_renewal.py`)
- 🎯 9 个测试类覆盖核心功能

##### 代码质量

- 📝 10+ 函数添加完整类型注解
- 🎯 10 个常量提取 (字符串 + URL)
- 🔧 降低认知复杂度，拆分复杂方法

#### v2.0.0 (2026-01-15)

##### 安全性与稳定性

- 🔒 移除不安全的 `eval()`，替换为基于 AST 的安全表达式解析器
- ⏱️ 为所有 HTTP 请求添加 30 秒超时，防止脚本挂起
- 📦 锁定依赖版本，确保构建一致性

##### 代码质量 (v2.0.0)

- 🏗️ 新增 `RenewalBot` 类封装全局状态，提高可测试性
- 🧪 添加 21 个单元测试覆盖核心功能
- 📝 添加类型注解和 `LogLevel` 枚举统一日志格式
- ⚡ OCR 实例缓存，避免重复加载模型

##### 配置增强

- 📧 支持自定义 `SMTP_HOST` 和 `SMTP_PORT` 环境变量
- ✅ 新增启动时配置验证，明确提示缺失项

</details>

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

| Secret 名称               | 示例值                          | 描述                                                                                                                                                    |
| ------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `EUSERV_USERNAME`         | `your_euserv_username`          | 用于登录 Euserv。                                                                                                                                       |
| `EUSERV_PASSWORD`         | `your_euserv_password`          | 用于登录 Euserv。                                                                                                                                       |
| `EUSERV_2FA`              | `ABCD1234EFGH5678`              | **(可选)** 您在 Euserv 后台开启 2FA 时获得的**Setup key**。                                                                                             |
| `CAPTCHA_USERID`          | `your_captcha_userid`           | **(可选)** 您在 TrueCaptcha 注册的 `userid`，作为本地 OCR 的备用。                                                                                      |
| `CAPTCHA_APIKEY`          | `xxxxxxxxxxxxxxxxxxxx`          | **(可选)** 您的 TrueCaptcha `apikey`，作为本地 OCR 的备用。                                                                                             |
| `EMAIL_HOST`              | `imap.gmail.com`                | 您的邮箱 IMAP 服务器地址。                                                                                                                              |
| `EMAIL_USERNAME`          | `your_email@gmail.com`          | 您的完整邮箱地址。                                                                                                                                      |
| `EMAIL_PASSWORD`          | `abcd efgh ijkl mnop`           | 您的邮箱**应用专用密码**。                                                                                                                              |
| `NOTIFICATION_EMAIL`      | `your_notify_email@example.com` | 用于接收运行报告的邮箱地址。                                                                                                                            |
| `SMTP_HOST`               | `smtp.gmail.com`                | **(可选)** 手动指定 SMTP 服务器。若不提供，将尝试从 IMAP 配置推断。                                                                                     |
| `SMTP_PORT`               | `587`                           | **(可选)** 手动指定 SMTP 端口。默认为 587。                                                                                                             |
| `PAT_WITH_WORKFLOW_SCOPE` | `github_pat_xxxx`               | **(推荐)** 用于动态调度的 [Fine-grained PAT](https://github.com/settings/personal-access-tokens/new)。需设置权限：`Contents` (RW) 和 `Workflows` (RW)。 |

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

创建 PAT：[创建 Fine-grained Token](https://github.com/settings/personal-access-tokens/new)

1. **Repository access**: 选择 `Only select repositories` -> 选择本仓库
2. **Permissions**: 展开并设置 `Contents` 为 **Read and write**，`Workflows` 为 **Read and write**

### 许可证

该项目根据 **GNU General Public License v3.0** 许可证授权。详情请参阅 `LICENSE` 文件。

### 免责声明

- 本项目按"原样"提供，作者不对任何因使用此脚本可能导致的服务中断、数据丢失或其他损失负责。
- EUserv 随时可能更改其网站结构或续约流程，这可能导致此自动化脚本失效。
- 请自行承担使用风险。

---

## English Version

### Changelog

#### v2.3.0 (2026-04-05) - English

##### Stability Fixes

- 🔴 **Session expiry auto-recovery**: Added `_refresh_session()` method to re-login after long renewal flows, preventing `_check_post_renewal_status` failures due to expired sessions
- 📧 **Email encoding compatibility**: `_extract_email_body()` now uses `part.get_content_charset()` with UTF-8 fallback, supporting multiple email encodings

##### Code Quality

- 🔧 Simplified `_handle_captcha` parameters (7→3), reads credentials from instance directly
- 🔧 Simplified `_handle_2fa` parameters (3→1), inlines origin header to preserve original `https://www.euserv.com`
- 🔧 Changed `_renew` return type from `bool` to `None` (was always returning True)
- 🔧 Extracted `SERVER_LIST_RETRY_DELAY` constant, replacing hardcoded `sleep(30)`
- 🗑️ Removed redundant `http://` retry adapter (Euserv is exclusively HTTPS)

##### Test Improvements

- ✅ Fixed test name `test_parentheses_not_supported` → `test_parentheses_work`
- 🧹 Removed unused `pytest` import from `test_safe_eval.py`

##### CI Optimization

- ⚡ Enabled Node.js 24 to silence GitHub Actions deprecation warning

<details>
<summary>v2.2.0 and earlier</summary>

#### v2.2.0 (2026-02-19)

##### Critical Fixes

- 🔴 **Fix cron schedule not updating**: Empty server list now returns `EXIT_FAILURE` and saves debug HTML
- 🔴 **Fix next_cron lost after renewal**: Always output next renewal date regardless of post-renewal status
- 🔴 **Fix test suite**: Resolved ImportError in 3 test files caused by function renaming

##### Security Hardening

- 🔒 Mask 2FA codes and PINs in logs (show only last 2 digits)
- 🛡️ Added `HTTPAdapter` + `Retry` strategy for automatic retries on 5xx errors
- 🌐 Updated User-Agent to Chrome 131

##### Improvements

- 🎯 Use `ddddocr.set_ranges()` to constrain character set for better math CAPTCHA accuracy
- 🧹 Extracted `_clean_math_expr()` / `_try_solve_math()` for unified math expression handling
- 🧹 Extracted `_parse_server_row()` to reduce cognitive complexity
- 📊 Added row count logging for server list parsing; save HTML on empty results for debugging

#### v2.1.0 (2026-01-22)

##### Architecture Optimization

- 🏗️ **Phase 3 Architecture Unification**: Moved 15+ top-level functions into `RenewalBot` class
- 🧹 Eliminated global variables `LOG_MESSAGES`, `CURRENT_LOGIN_ATTEMPT`, `_ocr_instance`
- ⚡ OCR Prewarming: Preload model at startup to reduce first recognition delay
- 🔒 HTTP Session Resource Management: Added `_cleanup()` method for proper closure

##### Test Coverage

- 🧪 Added pytest test suite (`tests/test_renewal.py`)
- 🎯 9 test classes covering core functionality

##### Code Quality

- 📝 10+ functions with complete type annotations
- 🎯 10 constants extracted (strings + URLs)
- 🔧 Reduced cognitive complexity by splitting complex methods

#### v2.0.0 (2026-01-15)

##### Security and Stability

- 🔒 Replaced unsafe `eval()` with AST-based safe expression parser
- ⏱️ Added 30-second timeout to all HTTP requests
- 📦 Locked dependency versions for consistent builds

##### Code Quality (v2.0.0)

- 🏗️ Added `RenewalBot` class to encapsulate global state
- 🧪 Added 21 unit tests covering core functionality
- 📝 Added type annotations and `LogLevel` enum for unified logging
- ⚡ Cached OCR instance to avoid reloading model

##### Configuration

- 📧 Support for custom `SMTP_HOST` and `SMTP_PORT` environment variables
- ✅ Added startup config validation with clear error messages

</details>

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

| Secret Name               | Example Value                   | Description                                                                                                                                                             |
| ------------------------- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `EUSERV_USERNAME`         | `your_euserv_username`          | Your username for EUserv.                                                                                                                                               |
| `EUSERV_PASSWORD`         | `your_euserv_password`          | Your password for EUserv.                                                                                                                                               |
| `EUSERV_2FA`              | `ABCD1234EFGH5678`              | **(Optional)** The **Setup key** you get when enabling 2FA in your Euserv account.                                                                                      |
| `CAPTCHA_USERID`          | `your_captcha_userid`           | **(Optional)** Your `userid` from TrueCaptcha, used as fallback for local OCR.                                                                                          |
| `CAPTCHA_APIKEY`          | `xxxxxxxxxxxxxxxxxxxx`          | **(Optional)** Your `apikey` from TrueCaptcha, used as fallback for local OCR.                                                                                          |
| `EMAIL_HOST`              | `imap.gmail.com`                | Your email provider's IMAP server.                                                                                                                                      |
| `EMAIL_USERNAME`          | `your_email@gmail.com`          | Your full email address.                                                                                                                                                |
| `EMAIL_PASSWORD`          | `abcd efgh ijkl mnop`           | Your email **App Password**.                                                                                                                                            |
| `NOTIFICATION_EMAIL`      | `your_notify_email@example.com` | The email address to receive status reports.                                                                                                                            |
| `SMTP_HOST`               | `smtp.gmail.com`                | **(Optional)** Manually specify SMTP server. Infers from IMAP if not provided.                                                                                          |
| `SMTP_PORT`               | `587`                           | **(Optional)** Manually specify SMTP port. Defaults to 587.                                                                                                             |
| `PAT_WITH_WORKFLOW_SCOPE` | `github_pat_xxxx`               | **(Recommended)** [Fine-grained PAT](https://github.com/settings/personal-access-tokens/new) for dynamic scheduling. Permissions: `Contents` (RW) and `Workflows` (RW). |

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

Create PAT: [Create Fine-grained Token](https://github.com/settings/personal-access-tokens/new)

1. **Repository access**: Select `Only select repositories` -> Select this repository
2. **Permissions**: Set `Contents` to **Read and write**, `Workflows` to **Read and write**

### License

This project is licensed under the **GNU General Public License v3.0**. See the `LICENSE` file for details.

### Disclaimer

- This project is provided "as is". The author is not responsible for any loss of service, data, or other damages that may result from its use.
- EUserv may change its website structure or renewal process at any time, which could break this automation.
- Use at your own risk.
