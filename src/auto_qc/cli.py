"""CLI 命令行入口"""
import argparse
import asyncio
import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="auto-qc 外呼通话文本质检",
        prog="auto-qc",
    )
    parser.add_argument("--data", required=True, help="源数据 Excel 文件路径")
    parser.add_argument("--rule-sets", required=True,
                        help="规则集名称，多个用逗号分隔（如 auto-pi,project-standards）")
    parser.add_argument("--output", help="报告输出路径（默认 output/<timestamp>_<run_name>/ 目录下）")
    parser.add_argument("--work-dir", help="工作目录（默认 output/<timestamp>_<run_name>/）")
    parser.add_argument("--run-name", help="运行名称（默认从数据文件名推断）")

    args = parser.parse_args()
    rule_set_names = [s.strip() for s in args.rule_sets.split(",") if s.strip()]
    if not rule_set_names:
        parser.error("--rule-sets 至少需要指定一个规则集")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = args.run_name or Path(args.data).stem
    work_dir = args.work_dir or f"output/{timestamp}_{run_name}"
    output_path = args.output or f"{work_dir}/质检报告_{timestamp}.xlsx"

    from auto_qc.qc.framework.orchestrator import run_qc
    asyncio.run(run_qc(
        data_path=args.data,
        rule_set_names=rule_set_names,
        output_path=output_path,
        work_dir=work_dir,
    ))


if __name__ == "__main__":
    main()
