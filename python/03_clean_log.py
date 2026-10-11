"""
03_clean_log.py — 生成清洗日志 xlsx
============================================================
职责：
  读取 02 脚本生成的 logs/cleaning_stats.json，
  输出项目级清洗日志 logs/cleaning_log.xlsx，便于面试展示。

输入：logs/cleaning_stats.json（02 脚本写入）
输出：logs/cleaning_log.xlsx

如果 stats.json 不存在，会自动调用 02_clean_data.py 重新生成。

运行：
    py python\\03_clean_log.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

# ---------- 路径 ----------
ROOT = Path(__file__).resolve().parent.parent
STATS_PATH = ROOT / "logs" / "cleaning_stats.json"
LOG_PATH = ROOT / "logs" / "cleaning_log.xlsx"
CLEAN_SCRIPT = ROOT / "python" / "02_clean_data.py"

# ---------- 日志条目定义（顺序 = 展示顺序）----------
LOG_ROWS = [
    ("原始行数", "raw 文件总行数（清洗前）"),
    ("删除空标题", "title 为空或清洗后变空"),
    ("非Coach噪声删除", "标题不含 coach/蔻驰（蹭型号/无关商品搜索噪声）"),
    ("价格异常删除", "价格 ≤0 或 >10000"),
    ("销量转换", "文本销量转数字（万 ×10000、删 +人付款）"),
    ("销量缺失填0", "原 sales_raw 为空，按规则填充 0"),
    ("重复删除", "按 url 或 title 去重"),
    ("最终行数", "清洗后保留行数"),
    ("去重依据", "url 优先，无则 title"),
]


def load_stats() -> dict | None:
    """读取 02 写入的 stats json。"""
    if not STATS_PATH.exists():
        return None
    try:
        with open(STATS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[警告] 读取 stats 失败：{type(e).__name__}: {e}")
        return None


def build_log_df(stats: dict) -> pd.DataFrame:
    """构建日志 DataFrame。"""
    rows = []
    for step, desc in LOG_ROWS:
        val = stats.get(step, "—")
        # 数值字段转 int 显示更清晰
        if isinstance(val, (int, float)) and step not in ("去重依据",):
            val = int(val)
        rows.append({"步骤": step, "处理数量": val, "说明": desc})

    # 字段信息附加表（面试加分：展示字段对齐）
    field_rows = []
    field_rows.append({"步骤": "原始字段", "处理数量": "、".join(stats.get("原始字段", [])), "说明": "raw xlsx 列名"})
    field_rows.append({"步骤": "最终字段", "处理数量": "、".join(stats.get("最终字段", [])), "说明": "cleaned csv 列名"})

    df = pd.DataFrame(rows + [{"步骤": "", "处理数量": "", "说明": ""}] + field_rows)
    return df


def regenerate_stats() -> bool:
    """如果 stats.json 不存在，调用 02_clean_data.py 重新生成。"""
    print(f"[信息] 未找到 {STATS_PATH.name}，调用 02_clean_data.py 重新生成...")
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, str(CLEAN_SCRIPT)],
            cwd=str(ROOT),
            capture_output=False,
        )
        return result.returncode == 0 and STATS_PATH.exists()
    except Exception as e:
        print(f"[错误] 调用 02 失败：{type(e).__name__}: {e}")
        return False


def main() -> int:
    print("=" * 60)
    print("03 生成清洗日志")
    print("=" * 60)

    stats = load_stats()
    if stats is None:
        ok = regenerate_stats()
        if not ok:
            print(f"\n[错误] 无法获取清洗统计，请先手动运行：py python\\02_clean_data.py")
            return 2
        stats = load_stats()

    # 构建日志表
    df = build_log_df(stats)

    # 保存 xlsx
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_excel(LOG_PATH, index=False, sheet_name="清洗日志")
    except Exception as e:
        print(f"[错误] 写入 xlsx 失败：{type(e).__name__}: {e}")
        print(f"        提示：如 xlsx 被其他程序（Excel）占用，请先关闭")
        return 3

    print(f"\n已生成清洗日志：{LOG_PATH}")
    print(f"\n日志内容预览：")
    print(df.to_string(index=False))

    print("\n" + "=" * 60)
    print("清洗日志生成完成。项目阶段 3 全流程结束。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
