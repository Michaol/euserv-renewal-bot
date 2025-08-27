# EUserv 免费 VPS 自动续约机器人

[![许可证: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

一个基于 GitHub Actions 的自动化脚本，用于自动续约 [EUserv](https://www.euserv.com/) 提供的免费VPS计划。

该脚本旨在模拟完整的人工操作流程，包括登录、处理动态会话、解决数学验证码、检查续约状态、从电子邮件中获取并提交PIN码，从而实现无人值守的自动化续约。

---

## 目录

* [中文版](#中文版)
    * [功能特性](#功能特性)
    * [工作流程](#工作流程)
    * [配置指南](#配置指南)
    * [定时任务配置](#定时任务配置)
    * [许可证](#许可证)
    * [免责声明](#免责声明)
* [English Version](#english-version)
    * [Features](#features)
    * [How It Works](#how-it-works)
    * [Setup Guide](#setup-guide)
    * [Schedule Configuration](#schedule-configuration)
    * [License](#license)
    * [Disclaimer](#disclaimer)

---

## 中文版

### 功能特性

* **完全自动化**：通过 GitHub Actions 实现每月定时自动续约。
* **安全可靠**：所有敏感信息（如密码和API密钥）均通过 GitHub Secrets 进行安全存储。
* **智能登录**: 自动处理动态的 `sess_id`，模拟真实浏览器登录。
* **验证码处理**: 集成 [TrueCaptcha](https://apitruecaptcha.org/) API 以自动解决登录过程中的数学验证码。
* **状态检查**: 续约前会先检查服务器是否确实需要续约，避免不必要的操作。
* **PIN码获取**: 自动登录Gmail邮箱，读取最新的续约PIN码邮件并解析出PIN码。

### 工作流程

1.  **登录**: 访问登录页面，获取动态 `sess_id`。
2.  **验证码**: 提交用户名和密码后，将数学验证码图片发送至 TrueCaptcha API 获取答案。
3.  **检查**: 登录成功后，导航至合同列表页面，查找免费VPS并检查是否存在“续约”按钮。
4.  **触发PIN**: 如果需要续约，则点击续约链接，触发系统向您的邮箱发送PIN码邮件。
5.  **获取PIN**: 脚本登录您的Gmail邮箱，找到当天的PIN码邮件并提取出6位PIN码。
6.  **提交PIN**: 返回Euserv页面，输入并提交PIN码，完成续约。
7.  **报告**: 在GitHub Actions的日志中输出整个流程的结果。

### 配置指南

要使此项目正常工作，请严格遵循以下步骤。

#### 准备工作

1.  一个正常使用的 **Euserv 免费VPS** 账户。
2.  一个 **Gmail 邮箱账户**，并已为其生成一个**应用专用密码**。
3.  一个 **TrueCaptcha 账户** (`apitruecaptcha.org`)，并获取您的 `userid` 和 `apikey`。
4.  一个 **GitHub 账户**。

#### 第1步：Fork 本仓库

点击本页面右上角的 **`Fork`** 按钮，将此项目复制到您自己的GitHub账户下。

#### 第2步：配置 GitHub Secrets

这是最关键的步骤。请进入您 Fork 后的仓库，点击 `Settings` -> `Secrets and variables` -> `Actions`，然后点击 `New repository secret` 按钮，逐一添加以下所有 Secret：

| Secret 名称          | 示例值                               | 描述                               |
| -------------------- | -------------------------------------- | ---------------------------------- |
| `EUSERV_USERNAME`    | `your_euserv_username`                 | 用于登录 Euserv。                  |
| `EUSERV_PASSWORD`    | `your_euserv_password`                 | 用于登录 Euserv。                  |
| `EMAIL_HOST`         | `imap.gmail.com`                       | 您的邮箱 IMAP 服务器地址。         |
| `EMAIL_USERNAME`     | `your_email@gmail.com`                 | 您的完整邮箱地址。                 |
| `EMAIL_PASSWORD`     | `abcd efgh ijkl mnop`                  | 您的邮箱**应用专用密码**。       |
| `CAPTCHA_USERID`     | `your_captcha_userid`                  | 您在 TrueCaptcha 注册的 `userid`。 |
| `CAPTCHA_APIKEY`     | `xxxxxxxxxxxxxxxxxxxx`                 | 您的 TrueCaptcha `apikey`。        |

**请务必确保 Secret 名称与上表完全一致，并将示例值替换为您自己的真实信息。**

#### 第3步：手动运行工作流进行测试

1.  点击仓库顶部的 `Actions` 标签页。
2.  在左侧选择 `Euserv VPS Renewal` 工作流。
3.  点击 `Run workflow` 按钮来手动触发一次运行。
4.  您可以点击运行中的任务，实时查看日志输出，以确认每一步都按预期执行。

### 定时任务配置

默认情况下，续约任务被设置为在**每个月的15日凌晨1点 (UTC时间)** 运行。

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

* **Fully Automated**: Scheduled monthly renewals via GitHub Actions.
* **Secure**: All sensitive credentials (passwords, API keys) are securely stored using GitHub Secrets.
* **Intelligent Login**: Automatically handles dynamic `sess_id` to mimic a real browser login.
* **CAPTCHA Solving**: Integrates with the [TrueCaptcha](https://apitruecaptcha.org/) API to solve the mathematical CAPTCHA during login.
* **Status Check**: Checks if a renewal is actually necessary before initiating the process.
* **PIN Retrieval**: Automatically logs into a Gmail account to read the latest renewal PIN email and parse the PIN code.

### How It Works

1.  **Login**: Accesses the login page to obtain a dynamic `sess_id`.
2.  **CAPTCHA**: After submitting credentials, sends the CAPTCHA image to the TrueCaptcha API to get the solution.
3.  **Check**: After a successful login, navigates to the contracts page to find the free VPS and check for a "renew" button.
4.  **Trigger PIN**: If renewal is needed, the script "clicks" the renewal link, which triggers EUserv to send a PIN email.
5.  **Fetch PIN**: The script logs into your Gmail account, finds the PIN email for the current day, and extracts the 6-digit PIN.
6.  **Submit PIN**: Returns to the EUserv page to submit the PIN and finalize the renewal.
7.  **Report**: Outputs the results of the entire process in the GitHub Actions log.

### Setup Guide

Please follow these steps carefully to get the workflow running.

#### Prerequisites

1.  An active **EUserv Free VPS** account.
2.  A **Gmail account** for which you have generated an **App Password**.
3.  A **TrueCaptcha** account (`apitruecaptcha.org`) with your `userid` and `apikey`.
4.  A **GitHub account**.

#### Step 1: Fork the Repository

Click the **`Fork`** button at the top-right of this page to copy this project to your own GitHub account.

#### Step 2: Configure GitHub Secrets

This is the most critical step. Navigate to your forked repository, go to `Settings` -> `Secrets and variables` -> `Actions`, and click the `New repository secret` button to add each of the following secrets:

| Secret Name          | Example Value                          | Description                              |
| -------------------- | -------------------------------------- | ---------------------------------------- |
| `EUSERV_USERNAME`    | `your_euserv_username`                 | Your username for EUserv.                |
| `EUSERV_PASSWORD`    | `your_euserv_password`                 | Your password for EUserv.                |
| `EMAIL_HOST`         | `imap.gmail.com`                       | Your email provider's IMAP server.       |
| `EMAIL_USERNAME`     | `your_email@gmail.com`                 | Your full email address.                 |
| `EMAIL_PASSWORD`     | `abcd efgh ijkl mnop`                  | Your email **App Password**.             |
| `CAPTCHA_USERID`     | `your_captcha_userid`                  | Your `userid` from TrueCaptcha.          |
| `CAPTCHA_APIKEY`     | `xxxxxxxxxxxxxxxxxxxx`                 | Your `apikey` from TrueCaptcha.          |

**Ensure the secret names are copied exactly and replace the example values with your own real information.**

#### Step 3: Manually Run the Workflow to Test

1.  Go to the **`Actions`** tab in your repository.
2.  Select the **`Euserv VPS Renewal`** workflow from the sidebar.
3.  Click the **`Run workflow`** button to trigger a manual run.
4.  You can click on the running job to view the live logs and verify that each step is executing as expected.

### Schedule Configuration

By default, the renewal job is scheduled to run at **01:00 UTC on the 15th of every month**.

If you wish to change this schedule, you can edit the `cron` expression in the `.github/workflows/renewal.yml` file.

### License

This project is licensed under the **GNU General Public License v3.0**. See the `LICENSE` file for details.

### Disclaimer

* This project is provided "as is". The author is not responsible for any loss of service, data, or other damages that may result from its use.
* EUserv may change its website structure or renewal process at any time, which could break this automation.
* Use at your own risk.
