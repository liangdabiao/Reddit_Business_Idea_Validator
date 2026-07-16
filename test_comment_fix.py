"""
测试评论数据合并修复
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


async def test_comment_merging():
    """测试评论数据合并"""
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

    # 执行验证 - 使用快速模式
    business_idea = "sell labubu to girls"
    print(f"\n🚀 开始验证: {business_idea}\n")
    print("="*70)

    result = await orchestrator.execute(
        task="validate_business_idea",
        context={},
        business_idea=business_idea,
        keyword_count=1,
        pages_per_keyword=1,
        comments_per_post=5,
        report_format="html",
        use_user_input_as_keyword=True
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
        step_results = data.get("step_results", {})

        # 显示数据抓取结果
        if "scrape_data" in step_results:
            sc_data = step_results["scrape_data"].get("data", {})
            metadata = sc_data.get("metadata", {})
            total_posts = metadata.get("total_posts", 0)
            posts_with_comments = metadata.get("posts_with_comments", 0)
            total_comments = metadata.get("total_comments", 0)

            print(f"📊 数据抓取:")
            print(f"   总帖子数: {total_posts}")
            print(f"   带评论帖子数: {posts_with_comments}")
            print(f"   总评论数: {total_comments}")

            # 检查第一个帖子的评论数据
            posts = sc_data.get("posts_with_comments", [])
            if posts:
                first_post = posts[0]
                comments_data = first_post.get("comments_data", [])
                print(f"\n📝 第一个帖子详情:")
                print(f"   帖子ID: {first_post.get('note_id')}")
                print(f"   标题: {first_post.get('title', '')[:50]}...")
                print(f"   评论数: {len(comments_data)}")
                if comments_data:
                    print(f"   第一条评论: {comments_data[0].get('content', '')[:50]}...")
                    print(f"   ✅ 评论数据合并成功!")
                else:
                    print(f"   ❌ 评论数据为空!")

        # 显示评论标签分析结果
        if "analyze_comments_with_tags" in step_results:
            tag_data = step_results["analyze_comments_with_tags"].get("data", {})
            tag_analysis = tag_data.get("tag_analysis", {})
            total_posts_analyzed = tag_analysis.get("total_posts_analyzed", 0)
            total_tags_applied = tag_analysis.get("total_tags_applied", 0)

            print(f"\n🏷️  评论标签分析:")
            print(f"   分析帖子数: {total_posts_analyzed}")
            print(f"   应用标签数: {total_tags_applied}")
            if total_posts_analyzed > 0:
                print(f"   ✅ 评论标签分析成功!")
            else:
                print(f"   ❌ 评论标签分析失败!")

    else:
        print(f"❌ 验证失败: {result.error}")

    print("="*70)

    return result.success


if __name__ == "__main__":
    try:
        success = asyncio.run(test_comment_merging())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户取消操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
