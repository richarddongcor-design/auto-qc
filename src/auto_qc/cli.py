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
    parser.add_argument("--output", help="报告输出路径（默认输出到数据文件同目录）")
    parser.add_argument("--work-dir", default="./auto_qc_work", help="工作目录（临时文件存放）")

    args = parser.parse_args()

    # 确定输出路径
    if args.output:
        output_path = args.output
    else:
        data_path = Path(args.data)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(
            data_path.parent / f"{data_path.stem}_质检报告_{timestamp}.xlsx"
        )

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
            work_dir=args.work_dir,
            skip_attribution=skip_attribution,
        ))


if __name__ == "__main__":
    main()
