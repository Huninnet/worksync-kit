#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkSync - 让 WorkBuddy 的「我」在多台电脑之间保持一致。

同步对象: 身份文件(SOLe/IDENTITY/USER)、工作记忆、自定义技能。
通道: 任意一个两端都装了的云盘目录(默认 OneDrive),或 Git 仓库。

安全原则:
  1. 永不删除文件。
  2. 覆盖前先备份到 .backup/<时间戳>/。
  3. 两端都改过的文件判为冲突,保留本地,远端副本另存到 .conflicts/,由人决定。
  4. 三路合并: 用上次同步的哈希做基准,只有一端变化才自动搬。
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"
STATE_NAME = ".state.json"
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "sync.log"
MAX_LOG = 1_000_000


# ---------------------------------------------------------------- 基础设施

def expand(p: str) -> str:
    p = os.path.expandvars(os.path.expanduser(str(p)))
    return p.replace("\\", "/")


def sha(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG:
            LOG_FILE.unlink()
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except OSError:
        pass


def load_config() -> dict:
    if not CONFIG.exists():
        sys.exit(f"缺少配置文件: {CONFIG}")
    with CONFIG.open(encoding="utf-8") as f:
        return json.load(f)


def hub_path(cfg: dict) -> Path:
    raw = str(cfg.get("hub", ""))
    out = expand(raw)
    if "$" in out or "%" in out:
        sys.exit(f"通道路径无法解析: {raw} — 环境变量 {raw.split('/')[0]} 未设置。\n"
                 f"请把 config.json 的 hub 改成绝对路径，例如 D:/OneDrive/WorkBuddySync")
    return Path(out)


def device_name() -> str:
    return os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "device"


def device_state_path(hub: Path) -> Path:
    """每台设备一份状态文件：两端 7x24 在线也不会争写同一文件，
    从根上消除 .state.json 被 OneDrive 判成冲突副本的问题。"""
    return hub / f".state-{device_name()}.json"


def load_state(hub: Path) -> dict:
    """基准必须按设备各存一份：否则另一端同步后，本端就失去自己的比对基准。"""
    f = device_state_path(hub)
    data: dict = {}
    if f.exists():
        try:
            with f.open(encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, OSError):
            data = {}
    if "files" in data:  # 兼容旧版本的单份基准
        data = {"version": 2,
                "devices": {device_name(): {"seen": "", "files": data["files"]}}}
    data.setdefault("version", 2)
    data.setdefault("devices", {})
    # 兼容：旧版共享 .state.json 里可能存有本机基准，迁移后即弃用
    legacy = hub / STATE_NAME
    if not data["devices"].get(device_name(), {}).get("files") and legacy.exists():
        try:
            with legacy.open(encoding="utf-8") as fp:
                ld = json.load(fp)
            for d, info in ld.get("devices", {}).items():
                data["devices"].setdefault(d, {"seen": "", "files": {}})["files"].update(
                    info.get("files", {}))
        except (json.JSONDecodeError, OSError):
            pass
    return data


def device_base(state: dict) -> dict:
    return state.get("devices", {}).get(device_name(), {}).get("files", {})


def all_devices(hub: Path) -> dict[str, dict]:
    """汇总通道内所有设备状态文件里的设备活动（跨设备展示用）。"""
    devs: dict[str, dict] = {}
    for f in hub.glob(".state-*.json"):
        try:
            with f.open(encoding="utf-8") as fp:
                for d, info in json.load(fp).get("devices", {}).items():
                    old = devs.get(d, {}).get("seen", "")
                    if info.get("seen", "") >= old:
                        devs[d] = info
        except (json.JSONDecodeError, OSError):
            continue
    return devs


def save_state(hub: Path, state: dict) -> None:
    hub.mkdir(parents=True, exist_ok=True)
    target = device_state_path(hub)
    tmp = hub / (target.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    # OneDrive 可能正占用状态文件（如云盘同步中），短暂重试
    for i in range(5):
        try:
            tmp.replace(target)
            return
        except PermissionError:
            time.sleep(0.4 * (i + 1))
    try:
        tmp.replace(target)
    except PermissionError:
        # 仍被占用：保留 tmp，不破坏现有状态，下次同步再落盘
        pass


def backup(dst: Path, rel: str) -> None:
    """覆盖前把目标文件备份到本地 .backup/ 下。"""
    if not dst.exists():
        return
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = ROOT / ".backup" / ts / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(dst, target)
    except OSError:
        pass


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".wbsync-tmp")
    shutil.copy2(src, tmp)
    tmp.replace(dst)


# ---------------------------------------------------------------- 收集文件

def collect_local(cfg: dict) -> dict[str, Path]:
    """把「需要同步的本地文件」映射成 {仓库内相对路径: 本地绝对路径}。"""
    items: dict[str, Path] = {}

    for gname, g in cfg.get("groups", {}).items():
        if not g.get("enabled", True):
            continue
        dst_root = g.get("dst", gname)

        if "workspace_root" in g:
            wr = Path(expand(g["workspace_root"]))
            if wr.is_dir():
                for ws in sorted(wr.iterdir()):
                    mem = ws / ".workbuddy" / "memory"
                    if not (ws.is_dir() and mem.is_dir()):
                        continue
                    for f in mem.rglob("*.md"):
                        rel = f"{dst_root}/{ws.name}/{f.relative_to(mem).as_posix()}"
                        items[rel] = f

        for r in g.get("roots", []):
            src = Path(expand(r["src"]))
            if not src.is_dir():
                continue
            patterns = r.get("patterns", ["*"])
            excludes = r.get("exclude", [])
            allow_dot = r.get("dot", False)
            for f in src.rglob("*"):
                if not f.is_file():
                    continue
                if f.name.endswith(".wbsync-tmp"):
                    continue
                if f.name.startswith(".") and not allow_dot:
                    continue
                if not any(fnmatch.fnmatch(f.name, p) for p in patterns):
                    continue
                rel_parts = f.relative_to(src).parts
                if any(fnmatch.fnmatch(part, e)
                       for part in rel_parts for e in excludes):
                    continue
                rel = f"{r.get('dst', dst_root)}/{f.relative_to(src).as_posix()}"
                items[rel] = f

    return items


def resolve_targets(cfg: dict) -> list[tuple[str, Path]]:
    """生成 (仓库内前缀, 本地基准目录) 的映射，用于把远端文件还原到本地路径。"""
    pairs: list[tuple[str, Path]] = []
    for gname, g in cfg.get("groups", {}).items():
        if not g.get("enabled", True):
            continue
        dst_root = g.get("dst", gname)
        if "workspace_root" in g:
            wr = Path(expand(g["workspace_root"]))
            if wr.is_dir():
                for ws in sorted(wr.iterdir()):
                    mem = ws / ".workbuddy" / "memory"
                    if mem.is_dir():
                        pairs.append((f"{dst_root}/{ws.name}/", mem))
        for r in g.get("roots", []):
            pairs.append((r.get("dst", dst_root) + "/", Path(expand(r["src"]))))
    return pairs


def local_for(cfg: dict, rel: str) -> Path | None:
    best: tuple[str, Path] | None = None
    for prefix, base in resolve_targets(cfg):
        if rel.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, base)
    if best is None:
        return None
    return best[1] / rel[len(best[0]):]


def collect_remote(hub: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not hub.is_dir():
        return out
    for f in hub.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(hub).as_posix()
        if rel.startswith("."):
            continue
        out[rel] = f
    return out


# ---------------------------------------------------------------- 同步引擎

def try_append_merge(lp: Path, rp: Path) -> str | None:
    """追加式文本的自动合并：若一方内容是另一方的前缀（纯追加），直接取长者。

    只会命中「一端新增了内容、另一端原封不动」这一种安全情形；
    真正分叉的改动仍走人工冲突，绝不猜。返回 'local' / 'remote' / None。
    """
    if lp.suffix.lower() not in (".md", ".txt"):
        return None
    try:
        a = lp.read_text(encoding="utf-8").splitlines()
        b = rp.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if a == b:
        return None
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if not short:
        return None
    if long_[:len(short)] == short and len(long_) > len(short):
        return "local" if len(a) > len(b) else "remote"
    return None


def build_plan(cfg: dict):
    hub = hub_path(cfg)
    state = load_state(hub)
    base: dict[str, str] = device_base(state)
    unresolved = set(state.get("devices", {}).get(device_name(), {}).get("conflicts", []))
    local = collect_local(cfg)
    remote = collect_remote(hub)

    plan = []
    for rel in sorted(set(local) | set(remote)):
        lp = local.get(rel) or local_for(cfg, rel)
        rp = remote.get(rel) or (hub / rel)
        if lp is None:
            # 远端存在但本地找不到归属目录（例如 _tool 工具目录），跳过
            continue
        lh = sha(lp) if lp.exists() else None
        rh = sha(rp) if rp.exists() else None
        if lh == rh:
            continue

        if rel in unresolved:
            # 上次冲突尚未人工处理，保持挂起，绝不自动择一
            plan.append(("conflict", rel, lp, rp, "冲突未解决，需人工确认"))
            continue

        if lh and rh:
            b = base.get(rel)
            if b == lh:
                plan.append(("pull", rel, lp, rp, "远端已更新"))
            elif b == rh:
                plan.append(("push", rel, lp, rp, "本地已更新"))
            elif b is None:
                newer = "push" if lp.stat().st_mtime >= rp.stat().st_mtime else "pull"
                plan.append((newer, rel, lp, rp, "首次同步,较新者胜"))
            else:
                merged = try_append_merge(lp, rp)
                if merged == "local":
                    plan.append(("push", rel, lp, rp, "追加式合并(本地更全)"))
                elif merged == "remote":
                    plan.append(("pull", rel, lp, rp, "追加式合并(远端更全)"))
                else:
                    plan.append(("conflict", rel, lp, rp, "两端都改过"))
        elif lh and not rh:
            b = base.get(rel)
            if b is None:
                plan.append(("push", rel, lp, rp, "远端缺失"))
            elif b == lh:
                plan.append(("gone-remote", rel, lp, rp, "远端已删除,本地保留"))
            else:
                plan.append(("conflict", rel, lp, rp, "远端删除但本地已改"))
        elif rh and not lh:
            b = base.get(rel)
            if b is None or b == rh:
                plan.append(("pull", rel, lp, rp, "本地缺失"))
            else:
                plan.append(("conflict", rel, lp, rp, "本地删除但远端已改"))

    return hub, state, plan


def apply(cfg: dict, mode: str, dry: bool, quiet: bool) -> int:
    hub, state, plan = build_plan(cfg)
    if not dry:
        hub.mkdir(parents=True, exist_ok=True)

    counts = {"push": 0, "pull": 0, "conflict": 0, "skip": 0}
    lines = []

    for action, rel, lp, rp, why in plan:
        if action == "conflict":
            counts["conflict"] += 1
            lines.append(f"  冲突  {rel}  ({why}) -> 本地保留,远端副本存 .conflicts/")
            if not dry and lp and rp:
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                tgt = ROOT / ".conflicts" / ts / rel
                tgt.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(rp, tgt)
            continue

        if action == "gone-remote":
            counts["skip"] += 1
            lines.append(f"  保留  {rel}  ({why})")
            continue

        if (mode == "pull" and action == "push") or (mode == "push" and action == "pull"):
            counts["skip"] += 1
            continue

        try:
            if action == "push":
                if not dry:
                    copy_file(lp, hub / rel)
                counts["push"] += 1
                lines.append(f"  上行  {rel}")
            elif action == "pull":
                if not dry:
                    backup(lp, rel)
                    copy_file(rp, lp)
                counts["pull"] += 1
                lines.append(f"  下行  {rel}")
        except OSError as e:
            counts["skip"] += 1
            lines.append(f"  失败  {rel}  {e}")

    if not dry:
        # 重新扫描一遍,两端一致的才记账为基准
        local2 = collect_local(cfg)
        remote2 = collect_remote(hub)
        files = {}
        for rel in set(local2) & set(remote2):
            if sha(local2[rel]) == sha(remote2[rel]):
                files[rel] = sha(local2[rel])
        entry = state.setdefault("devices", {}).setdefault(device_name(), {})
        entry["files"] = files
        entry["seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry["conflicts"] = sorted({p[1] for p in plan if p[0] == "conflict"})
        entry["last_result"] = (f"上{counts['push']}/下{counts['pull']}/"
                                f"冲{counts['conflict']}/跳{counts['skip']}")
        entry["runs"] = int(entry.get("runs", 0)) + 1
        state["version"] = 2
        save_state(hub, state)

    summary = (f"上行 {counts['push']} / 下行 {counts['pull']} / "
               f"冲突 {counts['conflict']} / 跳过 {counts['skip']}")
    if not quiet:
        if lines:
            print("\n".join(lines))
        print(("\n[试运行] " if dry else "\n") + summary)
        print(f"通道: {hub}")
    log(("dryrun " if dry else "") + summary)
    return 1 if counts["conflict"] else 0


# ---------------------------------------------------------------- 命令

def cmd_status(cfg: dict) -> None:
    hub, state, plan = build_plan(cfg)
    local = collect_local(cfg)
    print(f"通道目录: {hub}  ({'存在' if hub.is_dir() else '尚未创建'})")
    print(f"本地待同步文件: {len(local)} 个")
    print(f"上次同步基准: {len(device_base(state))} 个文件")
    if state.get("devices") or all_devices(hub):
        print("各设备的最近同步时间:")
        for d, info in sorted(all_devices(hub).items(),
                              key=lambda kv: kv[1].get("seen", ""), reverse=True):
            mark = " ← 本机" if d == device_name() else ""
            print(f"  - {d}  {info.get('seen', '-')}{mark}")
    print()
    if not plan:
        print("两端已一致,无需操作。")
        return
    print(f"待处理变更 {len(plan)} 项:")
    for action, rel, lp, rp, why in plan:
        print(f"  [{action}] {rel}  ({why})")


def cmd_resume(cfg: dict) -> None:
    """在新设备上接班：先拉齐云端，再打一份交接简报。"""
    apply(cfg, "pull", dry=False, quiet=True)
    hub = hub_path(cfg)
    state = load_state(hub)

    print("=" * 52)
    print(" 跨设备交接简报")
    print("=" * 52)

    devs = sorted(all_devices(hub).items(),
                  key=lambda kv: kv[1].get("seen", ""), reverse=True)
    print("\n设备活动（最近在前）:")
    for d, info in devs:
        mark = "   ← 本机" if d == device_name() else ""
        res = f"  [{info['last_result']}]" if info.get("last_result") else ""
        print(f"  {d:<16} {info.get('seen', '-')}{res}{mark}")

    remote = collect_remote(hub)
    print(f"\n通道内文件: {len(remote)} 个")

    recent = sorted(remote.items(), key=lambda kv: kv[1].stat().st_mtime, reverse=True)[:5]
    if recent:
        print("\n最近改动:")
        for rel, p in recent:
            ts = datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M")
            print(f"  {ts}  {rel}")

    # 项目状态页是长期项目的真相源：简报必须把它们顶到最前面，
    # 否则接班的人会拿 MEMORY.md 里的旧结论当现状（2026-11-05 因此翻过车）
    pages = cfg.get("status_pages") or []
    newest_page = 0.0
    if pages:
        print("\n⚠️ 项目状态页（真相源，开工前必须先读）:")
        for raw in pages:
            p = Path(expand(raw))
            if p.exists():
                mt = p.stat().st_mtime
                newest_page = max(newest_page, mt)
                ts = datetime.fromtimestamp(mt).strftime("%m-%d %H:%M")
                head = ""
                try:
                    for line in p.read_text(encoding="utf-8").splitlines()[:12]:
                        if "最后更新" in line:
                            head = line.strip().lstrip("> ").strip()
                            break
                except OSError:
                    pass
                print(f"  {ts}  {p}")
                if head:
                    print(f"           {head}")
            else:
                print(f"  缺失    {p}")

    memo = hub / "profile" / "MEMORY.md"
    if memo.exists() and newest_page:
        memo_mt = memo.stat().st_mtime
        gap_h = (newest_page - memo_mt) / 3600
        if gap_h > 2:  # 小于两小时的差异通常是同一次工作的先后顺序，不算过期
            print(f"\n⚠️ 记忆可能已过期：状态页比 MEMORY.md 新 {gap_h:.0f} 小时。")
            print("   凡与状态页冲突，一律以状态页为准，并回来改 MEMORY.md。")

    if memo.exists():
        text = memo.read_text(encoding="utf-8").splitlines()
        print(f"\n--- 用户级 MEMORY.md（共 {len(text)} 行）---")
        for line in text[:60]:
            print(line)
        if len(text) > 60:
            print(f"...（还有 {len(text) - 60} 行，完整内容见 {memo}）")
    else:
        print("\n(通道里还没有 MEMORY.md)")


def cmd_init(cfg: dict) -> None:
    hub = hub_path(cfg)
    hub.mkdir(parents=True, exist_ok=True)
    local = collect_local(cfg)
    print(f"通道目录已就绪: {hub}")
    print(f"待纳入同步的文件: {len(local)} 个")
    groups = cfg.get("groups", {})
    for name, g in groups.items():
        flag = "开" if g.get("enabled", True) else "关"
        print(f"  [{flag}] {g.get('label', name)}")


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="sync.py",
        description="WorkBuddy 跨设备同步工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""常用:
  sync.py init        初始化通道目录
  sync.py status      查看两端差异(不改动任何文件)
  sync.py sync        双向同步
  sync.py pull        只拉取远端更新
  sync.py push        只推送本地更新
""",
    )
    ap.add_argument("command", nargs="?", default="sync",
                    choices=["init", "status", "sync", "pull", "push", "resume"])
    ap.add_argument("--dry", action="store_true", help="只演练,不写文件")
    ap.add_argument("--quiet", action="store_true", help="静默(供计划任务调用)")
    args = ap.parse_args()

    cfg = load_config()
    if args.command == "init":
        cmd_init(cfg)
    elif args.command == "status":
        cmd_status(cfg)
    elif args.command == "resume":
        cmd_resume(cfg)
    else:
        sys.exit(apply(cfg, args.command, args.dry, args.quiet))


if __name__ == "__main__":
    main()
