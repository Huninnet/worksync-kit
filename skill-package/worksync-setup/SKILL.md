---
name: worksync-setup
display_name: 跨机会话同步与交接配置
display_name_en: Cross-Machine Session Sync & Handover Setup
description: 在两台或多台电脑间配置 WorkBuddy 会话状态外置同步：会话绑定本机、换机断线，本技能用 OneDrive 等网盘目录做中转通道，自动注册计划任务定时同步记忆/状态页/技能，并提供状态页、接班协议、漂移检测三模板。触发词：两台电脑同步、换电脑接班、会话同步、WorkSync、多机协作、交接状态。
description_zh: 在两台或多台电脑间配置 WorkBuddy 会话状态外置同步。会话绑定本机、换机即断线——本技能用 OneDrive（或其他网盘）目录做中转通道：自动注册计划任务每 30 分钟双向同步用户级记忆、项目状态页与技能库，附状态页五块模板、接班协议（开工三件事/收工五步）与线上漂移检测脚本，让每一次换机接班都能完整恢复上下文。
description_en: Set up cross-machine WorkBuddy session state sync via a cloud-drive hub (OneDrive etc.). Registers a scheduled task to sync user memory, project status pages and skills between machines every 30 minutes; ships status-page template, handover protocol and drift-check script so any machine can resume full context.
version: 1.0.0
author: hun8
examples_zh:
  - "我有两台电脑，帮我配置 WorkBuddy 会话和记忆的同步"
  - "换电脑后我的对话和项目状态都断了，帮我搭一套接班机制"
  - "帮我配置每天自动同步记忆和状态页到 OneDrive"
examples_en:
  - "I have two PCs, set up WorkBuddy session and memory sync between them"
  - "Help me build a handover mechanism after switching machines"
  - "Configure scheduled sync of memory and status pages to OneDrive"
---

# 跨机会话同步与交接配置

当用户需要在两台及以上电脑之间同步 WorkBuddy 会话状态（用户级记忆、项目状态页、技能库）时，按以下步骤执行。

## 背景知识（先读 references/README.md）

- WorkBuddy 的会话记录、上下文、project 索引绑定单机，**换机器即断线**（平台限制，无法改变）。
- 唯一可靠解法：**把状态外置到云盘**（OneDrive / 坚果云 / 任意两端可见的目录），由脚本定时双向同步，且**冲突不覆盖、只另存**。
- 本技能的 `scripts/sync.py` 是核心同步器：三路合并（本机→通道→对端）、永不删除、覆盖前自动备份。

## 执行步骤

1. **收集信息**（一次性问清，缺项给默认值）：
   - 云盘中转目录（默认 `$OneDrive/WorkBuddySync`；坚果云等用户改绝对路径）
   - 要同步的分组与开关（默认：用户级记忆、状态页、技能；用户可增删）
2. **安装**：把 `scripts/` 三个文件复制到用户选定的本机目录（默认 `~/WorkBuddy/WorkSync`）。
3. **配置**：参照包内 `references/README.md` 的配置说明，从模板生成 `config.json`（hub 路径、groups、interval_minutes 等），逐项向用户确认后写入。
4. **注册定时任务**：Windows 上以管理员方式运行 `scripts/install.ps1`（自动探测真实 python、注册计划任务：登录触发 + 每 interval_minutes 分钟）。
5. **初始化状态页**：把 `templates/00-当前状态.md` 复制到用户的主项目根目录，向用户解释五块结构（一句话现状/版本指针/已拍板/待办/环境事实）。
6. **交付协议**：把 `templates/接班协议.md` 交给用户，建议其放入 `~/.workbuddy/` 记忆体系；向用户解释"开工三件事 / 收工五步 / 改动必须落回 OneDrive"。
7. **验证**：手动跑一次 `python sync.py sync`，报告上行/下行/冲突计数；确认通道两端目录已生成。
8. **提示多机**：在第二台电脑上重复 2-7 步（hub 指向同一云盘目录、groups 配置一致）。

## 注意事项

- Windows 上 python 可能是微软商店占位程序（退出码 9009）——install.ps1 已内置逐候选实测，不要绕过它。
- 计划任务重注册用 `Register-ScheduledTask -Force`；不要用 `Get-Command "~\..."`（不展开 `~`）。
- 同步器**永不删除**：冲突时把双方各存一份，提示用户人工裁决——绝不静默覆盖。
- 涉及"换电脑/同步/备份"的请求，先跑 `python sync.py status` 看差异再动手。
- 详细原理、配置字段说明与真实事故复盘见 `references/`（README.md 与 case-study-交接翻车复盘.md）。
