# WorkSync Kit · 让「同一个 AI」在多台电脑上是同一个人

> 解决的问题：AI 编码助手（如 WorkBuddy / Claude Code 等）的会话状态绑单机，
> 换一台电脑，"我"就失忆了。这个工具包 = **同步器 + 交接协议模板 + 机械校验**，
> 三层防线让多机协作不翻车。

**语言 / Language**：[简体中文](README.md) · [English](README.en.md)

## 为什么需要它

同步的**不是**聊天记录（官方云端自带），而是换机后会丢的东西：

| 内容 | 丢了会怎样 |
|---|---|
| SOUL.md / IDENTITY.md / USER.md | AI 变成一个不认识你的陌生助手 |
| memory/（工作记忆） | 之前积累的项目背景、你的偏好全部清零 |
| skills/（自定义技能） | 自己装的技能要重装 |
| 状态页 / 协议模板 | 接班没有入口，每次都要重新对齐 |

但**光同步文件还不够**。真实翻车案例（详见 [docs/case-study-交接翻车复盘.md](docs/case-study-交接翻车复盘.md)）：
AI 在临时目录改完代码、发版上线，然后挂着等待，什么都没写回——
下一台机器的 AI 查遍文档全是空白，**把同一件事重做了一遍**。
所以这个 kit 不只是同步器，还有协议和机械校验（见下）。

## 三层防线

| 层 | 措施 | 防什么 |
|---|---|---|
| 行为层 | **完成即收工**：任务做完立刻执行收工五步（落盘→写状态页→sync→漂移检测→汇报结束），不等用户说"下班" | 用户离开后收工没人做 |
| 动作层 | **发版自动留痕 + 包 md5 强校验** | 发版了但没写文档；解压到旧包 |
| 校验层 | **漂移检测**：线上代码 vs 本地工作区逐文件 md5 | 文档层全线失守时的兜底 |

一句话原则：**不依赖写文档的自觉。文档说没干活不算数，服务器上的代码说了才算。**

## 快速开始（三步）

```powershell
# 1. 取回工具（云盘目录按你本机实际位置，通常是 $env:OneDrive）
New-Item -ItemType Directory -Force "$env:USERPROFILE\WorkBuddy\WorkSync" | Out-Null
Copy-Item "$env:OneDrive\WorkBuddySync\_tool\*" "$env:USERPROFILE\WorkBuddy\WorkSync\"

# 2. 拉取云端最新状态
cd "$env:USERPROFILE\WorkBuddy\WorkSync"
python sync.py pull

# 3. 注册自动同步（开机触发 + 每 30 分钟）
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

然后把 `config.example.json` 复制为 `config.json`，改两处：
`hub`（你的云盘目录）和 `status_pages`（你的项目状态页路径）。

## 常用命令

```bash
python sync.py resume    # 换机器后第一件事：拉齐 + 打印交接简报
python sync.py status    # 只看差异，不动任何文件（建议先跑这个）
python sync.py sync      # 双向同步
python sync.py pull      # 只拉云端更新
python sync.py push      # 只推本地更新
python sync.py sync --dry  # 演练，打印但不落盘
```

## 通道

`hub` 指向两端都装了客户端的云盘目录（默认 `$OneDrive/WorkBuddySync`）——
靠云盘客户端在两个地点之间传，脚本本身不联网。
换坚果云/百度网盘也一样，改 `config.json` 里的 `hub` 即可。

## 安全原则（脚本的铁律）

1. **永不删除文件**
2. **覆盖前先备份**到 `.backup/<时间戳>/`
3. **两端都改过的文件判为冲突**：保留本地，远端副本另存 `.conflicts/`，由人决定
4. **三路合并**：用上次同步的哈希做基准，只有一端变化才自动搬

唯一的例外是**纯追加**（一方内容是另一方的前缀）的 `.md/.txt`——自动取更全的那份，不算冲突。

## 模板与协议

- [`templates/00-当前状态.md`](templates/00-当前状态.md)——项目状态页模板（五块结构 + 最近变更）
- [`templates/接班协议.md`](templates/接班协议.md)——开工三件事 / 收工五步 / 发版纪律，每条都是翻车换来的
- [`templates/check-drift.sh`](templates/check-drift.sh)——漂移检测模板，改三处即可接入你的项目
- [`docs/case-study-交接翻车复盘.md`](docs/case-study-交接翻车复盘.md)——真实事故复盘，解释每条规则为什么存在

## 真相源优先级（重要经验）

**记忆是快照，会过期；长期项目的真相源是项目根目录的 `00-当前状态.md`。**

`resume` 会把状态页顶在简报最前面（路径配在 `config.json` 的 `status_pages`），
若状态页比 `MEMORY.md` 新超过 2 小时，直接警告"记忆可能已过期"。
开工顺序固定为：`resume` → **读状态页** → 才看记忆。

## 出问题时

- 覆盖前的旧版本在 `.backup/<时间戳>/`
- 冲突时保留本地，云端那份另存 `.conflicts/<时间戳>/`，等你看完再决定
- 冲突没解决之前，该文件一直挂起，**不会被任何一端悄悄覆盖**
- 执行记录在 `logs/sync.log`

## 关闭自动同步

```powershell
Unregister-ScheduledTask -TaskName "WorkBuddy WorkSync" -Confirm:$false
```

## 说明

- `config.json` 默认只同步身份、记忆、技能三组。`workspaces`（工作空间产物）默认关闭——
  产物体积大，且代码项目应该用 Git 管，不要靠网盘同步含 `.git`、`node_modules` 的目录，容易损坏。
- 已在 Windows 10/11 + OneDrive + WorkBuddy 环境实战数月（每日自动同步，双机交接）。

## 可配置项（都改 `config.json` 一个文件）

| 想改什么 | 改哪里 |
|---|---|
| 换网盘（OneDrive → 坚果云/百度网盘…） | `hub` 改成对应云盘目录 |
| 同步频率 | `interval_minutes`（分钟数），改完重跑 `install.ps1` 生效 |
| 同步哪些内容 / 每组的开关 | `groups` 里 `enabled` 开关 + 各组的 `patterns` / `exclude` 通配符 |
| 增删要同步的目录 | 对应组 `roots` 的 `src` |
| 状态页路径（resume 简报顶部） | `status_pages` 数组，可配多个 |

## 随缘维护

个人工具，服务于作者自己的双机工作流，顺便开源。
遇到问题欢迎提 issue，**不保证回复、不承诺修复时间**；当然，PR 很欢迎。

## License

[MIT](LICENSE)
