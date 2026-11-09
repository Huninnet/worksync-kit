#!/usr/bin/env bash
# 漂移检测模板：线上代码 vs 本地工作区，逐文件 md5 比对
#
# 原理：文档可以骗人（没写），文件时间戳可以骗人（改在临时目录），
#       服务器上实际运行的代码骗不了人。这是接班的机械校验层。
#
# 用法：bash check-drift.sh
#   · 接班时跑一次 —— drift≠0 说明有人在线上改了没回写，或本地改了没发版
#   · 每次发版后跑一次 —— 必须 drift=0，否则解压错了包（如 /tmp 里残留旧包）
#   · 退出码：0=一致，1=有漂移
#
# ── 接入你自己的项目只需改这三处 ──────────────────────────────
# [1] REMOTE_DIR   服务器上代码的位置
# [2] TRACK        要比对的本地路径清单（相对项目根）
# [3] remote()     连接服务器的命令（ssh / 任何封装均可）
set -uo pipefail
cd "$(dirname "$0")/.."

REMOTE_DIR="/var/www/your-site"        # [1] 改这里
TRACK="src db public server.js package.json"   # [2] 改这里（空格分隔，相对项目根）

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

remote() { ssh -o BatchMode=yes -o ConnectTimeout=10 user@your-server "$1"; }   # [3] 改这里

echo "==> 1/3 收集本地代码指纹"
# 注意 TRACK 里的单文件（非目录）要单独处理 find 的报错
( for p in $TRACK; do find "$p" -type f 2>/dev/null; done ) | sort \
  | while IFS= read -r f; do md5sum "$f" 2>/dev/null; done > "$TMP/local.raw"

echo "==> 2/3 收集线上代码指纹"
remote "cd $REMOTE_DIR && for p in $(echo $TRACK); do find \"\$p\" -type f 2>/dev/null; done | sort | xargs md5sum 2>/dev/null" \
  > "$TMP/remote.raw"

# 统一成 "路径<TAB>md5" 再比对；剥掉 Windows md5sum 的二进制标记 * 和远程输出的 \r
# 另：忽略线上遗留的 *.bak.*（直接在服务器改文件留下的副本，非业务代码）
norm() { tr -d '\r' < "$1" | awk '{h=$1; sub(/^[0-9a-f]{32}[ \t]+\*?/,""); print $0 "\t" h}' | grep -v '\.bak\.' | sort; }
norm "$TMP/local.raw"  > "$TMP/local.n"
norm "$TMP/remote.raw" > "$TMP/remote.n"

ONLY_LOCAL=$(comm -23 <(cut -f1 "$TMP/local.n") <(cut -f1 "$TMP/remote.n"))
ONLY_REMOTE=$(comm -13 <(cut -f1 "$TMP/local.n") <(cut -f1 "$TMP/remote.n"))
DIFF=$(join -t "$(printf '\t')" "$TMP/local.n" "$TMP/remote.n" | awk -F'\t' '$2 != $3 {print $1}')

NL=$(printf '%s\n' "$ONLY_LOCAL" | grep -c . || true)
NR=$(printf '%s\n' "$ONLY_REMOTE" | grep -c . || true)
ND=$(printf '%s\n' "$DIFF" | grep -c . || true)

echo
echo "==> 3/3 比对结果：本地独有 $NL · 线上独有 $NR · 内容不一致 $ND"
[ "$NL" -gt 0 ] && { echo "-- 本地有、线上没有（本地改了未发版）--"; printf '   %s\n' "$ONLY_LOCAL" | head -15; }
[ "$NR" -gt 0 ] && { echo "-- 线上有、本地没有（⚠️ 线上改动未回写本地工作区）--"; printf '   %s\n' "$ONLY_REMOTE" | head -15; }
[ "$ND" -gt 0 ] && { echo "-- 内容不一致 --"; printf '   %s\n' "$DIFF" | head -15; }

if [ "$NL" -eq 0 ] && [ "$NR" -eq 0 ] && [ "$ND" -eq 0 ]; then
  echo "✅ drift=0：线上代码与本地工作区完全一致"
  exit 0
else
  echo "⚠️ drift≠0：存在漂移，先弄清归属再动手（勿直接覆盖任何一侧）"
  exit 1
fi
