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
    parser.add_argument("--rules", help="合规规则 Markdown 文件路径（--attribution-only 时不需要）")
    parser.add_argument("--no-attribution", action="store_true", help="关闭归因分析")
    parser.add_argument("--attribution-only", action="store_true", help="仅执行归因分析")
    parser.add_argument("--output", help="报告输出路径（默认 output/<timestamp>_<数据文件名>/ 目录下）")
    parser.add_argument("--work-dir", help="工作目录，存放中间结果（默认 output/<timestamp>_<数据文件名>/）")
    parser.add_argument("--run-name", help="运行名称，用于输出目录命名（默认从数据文件名推断）")

    args = parser.parse_args()

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # 确定运行名称
    run_name = args.run_name or Path(args.data).stem

    # 确定工作目录
    work_dir = args.work_dir or f"output/{timestamp}_{run_name}"

    # 确定输出路径
    if args.output:
        output_path = args.output
    else:
        output_path = f"{work_dir}/质检报告_{timestamp}.xlsx"

    # 模式判断
    attribution_only = args.attribution_only
    skip_attribution = args.no_attribution

    if attribution_only:
        if not args.rules:
            parser.error("--attribution-only 模式下也需要 --rules 参数")
        # TODO: 后续实现纯归因模式
        print("归因分析模式（功能待完善）...")
    else:
        if not args.rules:
            parser.error("合规检测模式需要 --rules 参数（或用 --attribution-only 仅做归因分析）")
        from auto_qc.framework.orchestrator import run_qc
        asyncio.run(run_qc(
            data_path=args.data,
            rules_path=args.rules,
            output_path=output_path,
            work_dir=work_dir,
            skip_attribution=skip_attribution,
        ))


if __name__ == "__main__":
    main()
