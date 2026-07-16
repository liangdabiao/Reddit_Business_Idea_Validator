"""
业务创意验证启动脚本

使用方式:
    python run_agent.py 在深圳卖陈皮
    或
    python run_agent.py
    然后输入业务创意
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agents.orchestrator import OrchestratorAgent
from agents.config import ConfigManager
from agents.context_store import ContextStore
from agents.logging_config import setup_logging
from mcp_servers.reddit_server import RedditMCPServer
from mcp_servers.llm_server import create_llm_mcp_server
from mcp_servers.storage_server import create_storage_mcp_server


def print_banner():
    """打印横幅"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║         业务创意验证系统 v0.1.0                                 ║
║         Business Idea Validator Agent System                   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)


async def validate_business_idea(
    business_idea: str,
    keyword_count: int = 3,
    pages_per_keyword: int = 2,
    comments_per_post: int = 20,
    report_format: str = "html",
    use_user_input_as_keyword: bool = False
):
    """
    验证业务创意

    Args:
        business_idea: 业务创意描述
        keyword_count: 生成关键词数量
        pages_per_keyword: 每个关键词搜索页数
        comments_per_post: 每个帖子获取评论数
        report_format: 报告格式 (html/text)
        use_user_input_as_keyword: 是否直接使用用户输入作为关键词
    """
    # 初始化日志系统
    config = ConfigManager()
    log_level = config.get('logging.level', 'INFO')
    log_format = config.get('logging.format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    setup_logging(log_level=log_level, log_format=log_format)

    # 初始化上下文
    context_store = ContextStore()

    # 获取 API 配置
    reddit_config = config.get_reddit_mcp_config()
    llm_config = config.get_llm_config()

    print("🔧 初始化系统...")

    # 启动 MCP 服务器
    reddit_server = RedditMCPServer(
        client_id=reddit_config.client_id,
        client_secret=reddit_config.client_secret,
        user_agent=reddit_config.user_agent
    )
    await reddit_server.start()
    llm_server = await create_llm_mcp_server(
        llm_config.api_key,
        llm_config.base_url,
        llm_config.model_name
    )
    storage_server = await create_storage_mcp_server("agent_context/checkpoints")

    mcp_clients = {
        "reddit": reddit_server,
        "llm": llm_server,
        "storage": storage_server
    }

    print("✅ 服务启动成功")

    # 创建编排器
    orchestrator = OrchestratorAgent(config, context_store, mcp_clients)
    await orchestrator.start()

    # 设置进度回调
    def progress_callback(update):
        bar_length = 30
        filled = int(bar_length * update.progress)
        bar = "█" * filled + "░" * (bar_length - filled)
        print(f"  [{bar}] {update.progress*100:5.1f}% - {update.message}")

    orchestrator.set_progress_callback(progress_callback)

    # 执行验证
    print(f"\n🚀 开始验证: {business_idea}\n")
    print("="*70)

    result = await orchestrator.execute(
        task="validate_business_idea",
        context={},
        business_idea=business_idea,
        keyword_count=keyword_count,
        pages_per_keyword=pages_per_keyword,
        comments_per_post=comments_per_post,
        report_format=report_format,
        use_user_input_as_keyword=use_user_input_as_keyword
    )

    # 清理资源
    print("\n🧹 清理资源...")
    await orchestrator.stop()
    await reddit_server.stop()
    await llm_server.stop()
    await storage_server.stop()

    # 输出结果
    print("\n" + "="*70)
    if result.success:
        print("✅ 验证完成!\n")

        data = result.data
        state = data.get("state", {})
        step_results = data.get("step_results", {})

        # 显示执行统计
        print("📊 执行统计:")
        print(f"   总步骤: {state.get('total_steps', 0)}")
        print(f"   已完成: {state.get('completed_steps', 0)}")
        print(f"   执行时间: {result.execution_time:.1f} 秒")

        # 显示关键词生成结果
        if "generate_keywords" in step_results:
            kw_data = step_results["generate_keywords"].get("data", {})
            keywords = kw_data.get("keywords", [])
            print(f"\n🔑 生成关键词: {', '.join(keywords)}")

        # 显示数据抓取结果
        if "scrape_data" in step_results:
            sc_data = step_results["scrape_data"].get("data", {})
            # Check the new data structure for posts_with_comments
            metadata = sc_data.get("metadata", {})
            total_posts = metadata.get("total_posts", 0)
            posts_with_comments = metadata.get("posts_with_comments", 0)

            # Fallback to old structure if new structure not available
            if total_posts == 0:
                total_posts = sc_data.get('total_notes', 0)

            total_comments = metadata.get("total_comments", 0)
            if total_comments == 0:
                total_comments = sc_data.get('total_comments', 0)

            print(f"\n📊 数据抓取:")
            print(f"   笔记数: {total_posts}")
            print(f"   评论数: {total_comments}")

        # 显示综合评分
        if "combined_analysis" in step_results:
            ca_data = step_results["combined_analysis"].get("data", {})
            analysis = ca_data.get("analysis", {})
            score = analysis.get("overall_score", "N/A")
            summary = analysis.get("market_validation_summary", "")
            print(f"\n🎯 综合评分: {score}/100")
            print(f"   摘要: {summary[:100]}...")

        # 显示报告路径
        if "generate_report" in step_results:
            gr_data = step_results["generate_report"].get("data", {})
            saving = gr_data.get("saving", {})
            if saving.get("success"):
                print(f"\n📄 报告已保存:")
                print(f"   路径: {saving.get('path')}")
                print(f"   大小: {saving.get('size', 0)} 字节")
    else:
        print(f"❌ 验证失败: {result.error}")

    print("="*70)

    return result.success


def main():
    """主函数"""
    print_banner()

    # 获取业务创意和快速模式参数
    args = sys.argv[1:]
    fast_mode = False
    business_idea = ""
    
    # 解析参数
    positional_args = []
    for arg in args:
        if arg in ('--fast', '-f'):
            fast_mode = True
        elif arg in ('--pages', '-p'):
            pass  # handled below with next arg
        elif arg in ('--comments', '-c'):
            pass
        else:
            positional_args.append(arg)
    
    if positional_args:
        business_idea = " ".join(positional_args)
    else:
        print("请输入您的业务创意 (按 Enter 确认):")
        business_idea = input("> ").strip()

        if not business_idea:
            print("\n❌ 业务创意不能为空!")
            print("\n使用方式:")
            print("  python run_agent.py <业务创意> [--fast]")
            print("  示例: python run_agent.py AI productivity tools --fast")
            return 1

    # 询问是否使用快速模式（仅当没有指定 --fast 且在交互模式下）
    if not fast_mode and sys.stdin.isatty():
        print("\n⚡ 是否使用快速模式？(更少的数据，更快的执行)")
        fast_input = input("输入 y 使用快速模式，其他键使用完整模式: ").strip().lower()
        fast_mode = (fast_input == 'y')

    if fast_mode:
        keyword_count = 1
        pages_per_keyword = 1
        comments_per_post = 5
        use_user_input_as_keyword = True
        print("\n⚡ 使用快速模式: 1 关键词 × 1 页 × 5 评论")
    else:
        keyword_count = 3
        pages_per_keyword = 2
        comments_per_post = 20
        use_user_input_as_keyword = False
        print("\n📊 使用完整模式: 3 关键词 × 2 页 × 20 评论")

    # 运行验证
    try:
        success = asyncio.run(validate_business_idea(
            business_idea=business_idea,
            keyword_count=keyword_count,
            pages_per_keyword=pages_per_keyword,
            comments_per_post=comments_per_post,
            use_user_input_as_keyword=use_user_input_as_keyword
        ))

        if success:
            print("\n🎉 验证成功完成!")
            return 0
        else:
            print("\n⚠️  验证过程中出现错误，请检查日志")
            return 1

    except KeyboardInterrupt:
        print("\n\n⚠️  用户取消操作")
        return 1
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
