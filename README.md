# EUserv 免费 VPS 自动续约脚本 (Requests版)

[![许可证: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

一个基于 GitHub Actions 和 `requests` 库的自动化脚本，用于自动续约 [EUserv](https://www.euserv.com/) 提供的免费VPS计划。脚本通过精确模拟浏览器请求和邮件交互，实现无人值守的自动化续约。

受 [https://github.com/zensea/AutoEUServerlessWith2FA](https://github.com/zensea/AutoEUServerlessWith2FA) 和 [https://github.com/WizisCool/AutoEUServerless](https://github.com/WizisCool/AutoEUServerless) 启发

Inspired by [https://github.com/zensea/AutoEUServerlessWith2FA](https://github.com/zensea/AutoEUServerlessWith2FA) and [https://github.com/WizisCool/AutoEUServerless](https://github.com/WizisCool/AutoEUServerless)

---

## 目录

* [中文版](#中文版)
    * [功能特性](#功能特性)
    * [配置指南](#配置指南)
    * [定时任务配置](#定时任务配置)
    * [许可证](#许可证-1)
    * [免责声明](#免责声明)
* [English Version](#english-version)
    * [Features](#features-1)
    * [Setup Guide](#setup-guide-1)
    * [Schedule Configuration](#schedule-configuration-1)
    * [License](#license)
    * [Disclaimer](#disclaimer-1)

---

## 中文版

### 功能特性

* 通过 GitHub Actions 自动续约 Euserv 免费VPS。
* 处理登录、会话及**两步验证(2FA)**。
* 如遇图片验证码，则调用 TrueCaptcha API 自动识别。
* 通过 IMAP 连接 Gmail 邮箱，自动获取续约PIN码。
* 完整实现包含Token验证的精确续约流程。
* 每次运行后通过邮件发送状态报告。
* 所有凭据均通过 GitHub Secrets 安全管理。

### 配置指南

要使此项目正常工作，请严格遵循以下步骤。

#### 准备工作

1.  一个正常使用的 **Euserv 免费VPS** 账户。
2.  一个 **Gmail 邮箱账户**，并已为其生成一个**应用专用密码**。
3.  一个 **TrueCaptcha 账户** (`apitruecaptcha.org`)，并获取您的 `userid` 和 `apikey`。
4.  一个 **GitHub 账户**。

#### 第1步：Fork 本仓库

点击本页面右上角的 **`Fork`** 按钮，将此项目复制到您自己的GitHub账户下。

> **安全建议**：请确保您没有在任何时候意外地将个人凭据提交到代码中。

#### 第2步：配置 GitHub Secrets

这是最关键的步骤。请进入您 Fork 后的仓库，点击 `Settings` -> `Secrets and variables` -> `Actions`，然后点击 `New repository secret` 按钮，逐一添加以下 Secret：

| Secret 名称          | 示例值                               | 描述                               |
| -------------------- | -------------------------------------- | ---------------------------------- |
| `EUSERV_USERNAME`    | `your_euserv_username`                 | 用于登录 Euserv。                  |
| `EUSERV_PASSWORD`    | `your_euserv_password`                 | 用于登录 Euserv。                  |
| `EUSERV_2FA`         | `ABCD1234EFGH5678`                     | **(可选)** 您在Euserv后台开启2FA时获得的**Setup key**。 |
| `CAPTCHA_USERID`     | `your_captcha_userid`                  | 您在 TrueCaptcha 注册的 `userid`。 |
| `CAPTCHA_APIKEY`     | `xxxxxxxxxxxxxxxxxxxx`                 | 您的 TrueCaptcha `apikey`。        |
| `EMAIL_HOST`         | `imap.gmail.com`                       | 您的邮箱 IMAP 服务器地址。         |
| `EMAIL_USERNAME`     | `your_email@gmail.com`                 | 您的完整邮箱地址。                 |
| `EMAIL_PASSWORD`     | `abcd efgh ijkl mnop`                  | 您的邮箱**应用专用密码**。       |
| `NOTIFICATION_EMAIL` | `your_notify_email@example.com`        | 用于接收运行报告的邮箱地址。       |

**请务必确保 Secret 名称与上表完全一致，并将示例值替换为您自己的真实信息。**

> **关于2FA**: 强烈建议您在Euserv后台开启2FA。这不仅能极大地增强您账户的安全性，还很有可能让服务器信任您的登录行为，从而**跳过图片验证码识别**，为您节省API调用费用。

#### 第3步：手动运行工作流进行测试

1.  点击仓库顶部的 `Actions` 标签页。
2.  在左侧选择 `Euserv VPS Renewal` 工作流。
3.  点击 `Run workflow` 按钮来手动触发一次运行。
4.  您可以点击运行中的任务，实时查看日志输出。

### 定时任务配置

默认情况下，续约任务被设置为在**每周日的凌晨0点 (UTC时间)** 运行。对应的`cron`表达式为 `0 0 * * 0`。

如果您想修改这个时间，可以编辑 `.github/workflows/renewal.yml` 文件中的 `cron` 表达式。

### 许可证

该项目根据 **GNU General Public License v3.0** 许可证授权。详情请参阅 `LICENSE` 文件。

### 免责声明

* 本项目按“原样”提供，作者不对任何因使用此脚本可能导致的服务中断、数据丢失或其他损失负责。
* EUserv 随时可能更改其网站结构或续约流程，这可能导致此自动化脚本失效。
* 请自行承担使用风险。

---

## English Version

### Features

* Automated renewal of Euserv free VPS via GitHub Actions.
* Handles login, sessions, and **Two-Factor Authentication (2FA)**.
* Solves CAPTCHAs automatically via the TrueCaptcha API if encountered.
* Retrieves renewal PINs from a Gmail account via IMAP.
* Implements the complete and precise renewal workflow, including token exchange.
* Sends a run status report to your email after each execution.
* All credentials are managed securely via GitHub Secrets.

### Setup Guide

Please follow these steps carefully to get the workflow running.

#### Prerequisites

1.  An active **Euserv Free VPS** account.
2.  A **Gmail account** for which you have generated an **App Password**.
3.  A **TrueCaptcha** account (`apitruecaptcha.org`) with your `userid` and `apikey`.
4.  A **GitHub account**.

#### Step 1: Fork the Repository

Click the **`Fork`** button at the top-right of this page to copy this project to your own GitHub account.

> **Security Recommendation**: Please ensure you have not accidentally committed any personal credentials to the codebase at any time.

#### Step 2: Configure GitHub Secrets

This is the most critical step. Navigate to your forked repository, go to `Settings` -> `Secrets and variables` -> `Actions`, and click `New repository secret` to add each of the following secrets:

| Secret Name          | Example Value                          | Description                              |
| -------------------- | -------------------------------------- | ---------------------------------------- |
| `EUSERV_USERNAME`    | `your_euserv_username`                 | Your username for EUserv.                |
| `EUSERV_PASSWORD`    | `your_euserv_password`                 | Your password for EUserv.                |
| `EUSERV_2FA`         | `ABCD1234EFGH5678`                     | **(Optional)** The **Setup key** you get when enabling 2FA in your Euserv account. |
| `CAPTCHA_USERID`     | `your_captcha_userid`                  | Your `userid` from TrueCaptcha.          |
| `CAPTCHA_APIKEY`     | `xxxxxxxxxxxxxxxxxxxx`                 | Your `apikey` from TrueCaptcha.          |
| `EMAIL_HOST`         | `imap.gmail.com`                       | Your email provider's IMAP server.       |
| `EMAIL_USERNAME`     | `your_email@gmail.com`                 | Your full email address.                 |
| `EMAIL_PASSWORD`     | `abcd efgh ijkl mnop`                  | Your email **App Password**.             |
| `NOTIFICATION_EMAIL` | `your_notify_email@example.com`        | The email address to receive status reports. |

**Ensure the secret names are copied exactly and replace the example values with your own real information.**

> **About 2FA**: It is highly recommended to enable 2FA in your Euserv account. Not only does it significantly improve your account security, but it may also cause the server to trust your login and **skip the image CAPTCHA**, saving you API costs.

#### Step 3: Manually Run the Workflow to Test

1.  Go to the **`Actions`** tab in your repository.
2.  Select the **`Euserv VPS Renewal`** workflow from the sidebar.
3.  Click the **`Run workflow`** button to trigger a manual run.
4.  You can click on the running job to view the live logs.

### Schedule Configuration

By default, the renewal job is scheduled to run at **00:00 UTC on every Sunday**. The corresponding `cron` expression is `0 0 * * 0`.

If you wish to change this schedule, you can edit the `cron` expression in the `.github/workflows/renewal.yml` file.

### License

This project is licensed under the **GNU General Public License v3.0**. See the `LICENSE` file for details.

### Disclaimer

* This project is provided "as is". The author is not responsible for any loss of service, data, or other damages that may result from its use.
* EUserv may change its website structure or renewal process at any time, which could break this automation.
* Use at your own risk.
