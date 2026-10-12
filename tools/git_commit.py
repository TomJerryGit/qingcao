# tools/git_commit.py
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def commit(title: str, body_lines: list, closes: str = ""):
    """用 UTF-8 提交"""
    msg_lines = [title, ""]
    for line in body_lines:
        msg_lines.append(f"- {line}" if not line.startswith("-") else line)
    if closes:
        msg_lines.append("")
        msg_lines.append(closes)

    msg = "\n".join(msg_lines)

    # 写入临时文件
    tmp = ROOT / ".git_commit_msg.tmp"
    tmp.write_text(msg, encoding="utf-8")

    try:
        subprocess.run(
            ["git", "commit", "-F", str(tmp)],
            cwd=ROOT,
            check=True,
        )
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    # 用法：
    # python tools/git_commit.py "标题" "行1" "行2" ...
    if len(sys.argv) < 2:
        print("用法: python tools/git_commit.py <标题> [行1] [行2] ...")
        sys.exit(1)

    commit(
        title=sys.argv[1],
        body_lines=sys.argv[2:],
    )