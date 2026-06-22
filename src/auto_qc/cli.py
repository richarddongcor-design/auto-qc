"""统一 CLI 入口 — 子命令: qc, pi, web"""
import argparse
import asyncio
import datetime
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Auto-QC — 外呼通话质量检测 + 问题挖掘平台",
        prog="auto-qc",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- qc 子命令 ---
    qc_parser = subparsers.add_parser("qc", help="质检任务")
    qc_sub = qc_parser.add_subparsers(dest="qc_action", required=True)

    qc_run = qc_sub.add_parser("run", help="运行质检")
    qc_run.add_argument("--data", required=True, help="源数据 Excel 文件路径")
    qc_run.add_argument("--rule-sets", required=True,
                        help="规则集名称，多个用逗号分隔")
    qc_run.add_argument("--output", help="报告输出路径")
    qc_run.add_argument("--work-dir", help="工作目录")

    # --- pi 子命令 ---
    pi_parser = subparsers.add_parser("pi", help="问题挖掘任务")
    pi_sub = pi_parser.add_subparsers(dest="pi_action", required=True)

    pi_run = pi_sub.add_parser("run", help="运行问题挖掘")
    pi_run.add_argument("--data", required=True, help="源数据 Excel 文件路径")
    pi_run.add_argument("--domain", default="recruitment", help="领域名称")
    pi_run.add_argument("--output", help="输出目录")

    # --- web 子命令 ---
    web_parser = subparsers.add_parser("web", help="启动 Web 服务")
    web_parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    web_parser.add_argument("--port", type=int, default=8000, help="监听端口")

    args = parser.parse_args()

    if args.command == "qc":
        _run_qc(args)
    elif args.command == "pi":
        _run_pi(args)
    elif args.command == "web":
        _run_web(args)


def _run_qc(args):
    """运行质检任务。"""
    from auto_qc.core.config import load_env_config
    load_env_config()

    try:
        from auto_qc.qc.framework.orchestrator import run_qc
    except ImportError as e:
        print(f"错误: 无法导入质检模块 — {e}")
        sys.exit(1)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = Path(args.output).stem if args.output else Path(args.data).stem
    work_dir = args.work_dir or f"output/{timestamp}_{run_name}"
    output_path = args.output or f"{work_dir}/质检报告_{timestamp}.xlsx"

    rule_set_names = [s.strip() for s in args.rule_sets.split(",") if s.strip()]
    if not rule_set_names:
        print("错误: --rule-sets 至少需要指定一个规则集")
        sys.exit(1)

    try:
        asyncio.run(run_qc(
            data_path=args.data,
            rule_set_names=rule_set_names,
            output_path=output_path,
            work_dir=work_dir,
        ))
        print(f"质检完成，报告已保存至: {output_path}")
    except Exception as e:
        print(f"错误: 质检运行失败 — {e}")
        sys.exit(1)


def _run_pi(args):
    """运行问题挖掘任务。"""
    from auto_qc.core.config import load_env_config
    load_env_config()

    try:
        from auto_qc.pi.engine.pipeline import run_pipeline
    except ImportError as e:
        print(f"错误: 无法导入问题挖掘模块 — {e}")
        sys.exit(1)

    try:
        run_pipeline(data_path=args.data, output_dir=args.output, domain=args.domain)
        print("问题挖掘完成")
    except Exception as e:
        print(f"错误: 问题挖掘运行失败 — {e}")
        sys.exit(1)


def _run_web(args):
    """启动 Web 服务（FastAPI + uvicorn）。"""
    from auto_qc.core.config import load_env_config
    load_env_config()

    try:
        import uvicorn
    except ImportError:
        print("错误: 启动 Web 服务需要安装 uvicorn，请执行: pip install uvicorn")
        sys.exit(1)

    try:
        from auto_qc.web.app import create_app
    except ImportError as e:
        print(f"错误: 无法导入 Web 模块 — {e}（Web UI 尚未就绪）")
        sys.exit(1)

    app = create_app()
    print(f"启动 Web 服务: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
