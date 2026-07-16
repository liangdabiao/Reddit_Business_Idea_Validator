"""
数据分析 Skills

提供帖子和评论分析的业务技能
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from models.business_models import (
    PostWithCommentsAnalysis,
    CombinedAnalysis,
    CommentsAnalysis,
    TagAnalysis,
    TagSystemGeneration,
    PersonaAnalysis,
    PersonaProfile
)
from agents.base_agent import BaseAgent


logger = logging.getLogger(__name__)


async def analyze_post_skill(
    agent: BaseAgent,
    post: Dict[str, Any],
    business_idea: str,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    分析单条帖子

    Args:
        agent: Agent 实例
        post: 帖子数据
        business_idea: 业务创意
        max_retries: 最大重试次数

    Returns:
        分析结果
    """
    post_id = post.get('post_id', 'unknown')
    logger.info(f"Analyzing post: {post.get('title', 'Unknown')} (id={post_id})")

    # 构建分析提示
    note_text = f"""
标题: {post.get('title', '')}
内容: {post.get('content', '')}
得分: {post.get('score', 0)}
点赞率: {post.get('upvote_ratio', 0)}
评论数: {post.get('num_comments', 0)}
作者: {post.get('author', '')}
子版块: r/{post.get('subreddit', '')}
"""

    prompt = f"""
你是一位市场分析专家。请分析以下 Reddit 帖子与业务创意的相关性：

业务创意："{business_idea}"

帖子内容：
{note_text}

请分析：
1. 相关性：这个帖子是否与业务创意相关？
   【重要】相关性判断要宽松：只要帖子内容与业务创意有**一定关联**（包括直接相关、间接相关等），都应该判断为相关。
   - 直接相关：明确提到业务创意相关的产品/服务
   - 间接相关：提到相关场景、用户需求、痛点等
   
2. 用户痛点：从帖子中提取的用户痛点或需求
3. 解决方案：帖子中提到的解决方案或产品
4. 市场信号：帖子反映的市场趋势或信号
5. 情感倾向（sentiment）：
   - positive（正面）：帖子内容积极、充满希望、表达认可或支持
   - negative（负面）：帖子内容消极、表达担忧、不满或反对
   - neutral（中性）：帖子内容客观描述，或无明显情感倾向
   注意：只有当帖子确实没有明显情感倾向时才使用neutral，不要过度使用
6. 互动评分：根据点赞/收藏/评论数给出1-10分的互动评分

请以 JSON 格式返回：
{{
    "relevant": true/false,
    "pain_points": ["痛点1", "痛点2"],
    "solutions_mentioned": ["方案1", "方案2"],
    "market_signals": ["信号1", "信号2"],
    "sentiment": "positive/negative/neutral",
    "engagement_score": 8,
    "analysis_summary": "简短分析摘要"
}}
"""

    # 重试逻辑
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.warning(f"Retry attempt {attempt}/{max_retries} for post {post_id}")
                await asyncio.sleep(2 ** attempt)  # 指数退避

            result = await agent.use_llm(
                prompt=prompt,
                response_model=PostWithCommentsAnalysis
            )

            if hasattr(result, 'model_dump'):
                analysis = result.model_dump()
            else:
                analysis = result

            logger.info(f"Analysis complete: relevant={analysis.get('relevant')}, sentiment={analysis.get('sentiment')}")

            return {
                "success": True,
                "post_id": post_id,
                "analysis": analysis
            }

        except (ValueError, ConnectionError, TimeoutError) as e:
            # 可重试的错误
            if attempt < max_retries:
                logger.warning(f"Attempt {attempt + 1} failed for post {post_id}: {type(e).__name__}: {e}")
                # 如果是 ValueError，打印更详细的信息
                if isinstance(e, ValueError):
                    import traceback
                    logger.debug(f"ValueError traceback for post {post_id}:\n{''.join(traceback.format_tb(e.__traceback__))}")
                continue
            else:
                logger.error(f"All retries exhausted for post {post_id}: {type(e).__name__}: {e}")
                # 如果是 ValueError，打印更详细的信息
                if isinstance(e, ValueError):
                    import traceback
                    logger.error(f"ValueError details for post {post_id}:\n{''.join(traceback.format_tb(e.__traceback__))}")

                # 使用 fallback 分析
                fallback_analysis = _fallback_analysis(post, business_idea)
                logger.info(f"Using fallback analysis for post {post_id}")

                return {
                    "success": False,
                    "post_id": post_id,
                    "analysis": fallback_analysis,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "fallback": True
                }

        except Exception as e:
            # 不可重试的错误（如 JSON 解析错误）
            logger.error(f"Analyze post skill failed for post {post_id}: {type(e).__name__}: {e}")
            return {
                "success": False,
                "post_id": post_id,
                "analysis": {
                    "relevant": False,
                    "pain_points": [],
                    "solutions_mentioned": [],
                    "market_signals": [],
                    "sentiment": "neutral",
                    "engagement_score": 1,
                    "analysis_summary": f"分析失败: {type(e).__name__}"
                },
                "error": str(e),
                "error_type": type(e).__name__
            }


async def analyze_post_with_comments_skill(
    agent: BaseAgent,
    post_with_comments: Dict[str, Any],
    business_idea: str,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    分析帖子及其评论（统一分析）

    将帖子和它的评论作为一个整体进行综合分析，保留上下文关系。

    Args:
        agent: Agent 实例
        post_with_comments: 帖子数据（包含 comments_data）
        business_idea: 业务创意
        max_retries: 最大重试次数

    Returns:
        分析结果
    """
    post_id = post_with_comments.get('post_id', 'unknown')
    title = post_with_comments.get('title', 'Unknown')
    logger.info(f"Analyzing post with comments: {title} (id={post_id})")

    # 构建帖子内容
    post_text = f"""
标题: {post_with_comments.get('title', '')}
内容: {post_with_comments.get('content', '')}
Reddit 评分: {post_with_comments.get('score', 0)}
点赞比例: {post_with_comments.get('upvote_ratio', 0) * 100:.1f}%
子版块: r/{post_with_comments.get('subreddit', 'unknown')}
评论数: {post_with_comments.get('num_comments', 0)}
作者: {post_with_comments.get('author', 'unknown')}
帖子链接: {post_with_comments.get('url', 'N/A')}
"""

    # 提取评论内容
    comments = post_with_comments.get('comments_data', [])
    comments_text = ""
    if comments:
        # 选取前20条评论进行分析（避免token过多）
        sample_comments = comments[:20]
        comments_text = "\n".join([
            f"- [u/{c.get('author', 'Anonymous')}] {c.get('body', '')}"
            for c in sample_comments
        ])
    else:
        comments_text = "(该帖子暂无评论)"

    # 构建统一分析提示
    prompt = f"""
你是一位资深市场分析师。请综合分析以下 Reddit 帖子及其评论，判断其与业务创意的相关性：

业务创意："{business_idea}"

=== 帖子内容 ===
{post_text}

=== 用户评论 ({len(comments)} 条，显示前 {min(20, len(comments))} 条) ===
{comments_text}

请进行综合分析：

1. 相关性判断：这个帖子（包括评论）是否与业务创意相关？
   【重要】相关性判断要宽松：只要帖子内容或评论与业务创意有**任何关联**（包括直接相关、间接相关、潜在相关、场景相关、用户群体相关等），都应该判断为相关。
   - 直接相关：明确提到业务创意相关的产品/服务
   - 间接相关：提到相关场景、用户需求、痛点等
  
2. 痛点提取：从帖子内容和用户评论中提取的用户痛点
3. 解决方案：帖子或评论中提到的解决方案或产品
4. 市场信号：从互动和讨论中识别的市场趋势或信号
5. 用户洞察：从评论中提取的关键用户洞察
6. 用户需求：评论中用户表达的具体需求
7. 评论情感（feedback_sentiment）：基于评论整体情感判断
   - positive（正面）：评论中包含赞美、满意、推荐、期待等积极情绪
   - negative（负面）：评论中包含抱怨、不满、批评、担忧等消极情绪
   - neutral（中性）：评论主要是客观描述、询问、或情绪不明显
   注意：只有当评论确实没有明显情感倾向时才使用neutral，不要过度使用
8. 整体情感（sentiment）：综合帖子和评论的整体情感倾向
   - positive（正面）：整体氛围积极，用户表达出兴趣、认可或支持
   - negative（负面）：整体氛围消极，用户表达出不满、担忧或反对
   - neutral（中性）：整体内容客观，或积极与消极情绪相当
9. 互动评分：1-10分，基于以下因素综合评估：
   - Reddit 评分（score）：考虑帖子的净投票数
   - 点赞比例（upvote_ratio）：考虑帖子获得正面评价的比例
   - 评论数量和质量：考虑讨论的深度和参与度
   - 子版块活跃度：考虑 r/{post_with_comments.get('subreddit', 'unknown')} 的社区特性

请以 JSON 格式返回：
{{
    "post_id": "{post_id}",
    "title": "{title}",
    "relevant": true/false,
    "pain_points": ["痛点1", "痛点2"],
    "solutions_mentioned": ["方案1", "方案2"],
    "market_signals": ["信号1", "信号2"],
    "user_insights": ["洞察1", "洞察2"],
    "user_needs": ["需求1", "需求2"],
    "feedback_sentiment": "positive/negative/neutral",
    "sentiment": "positive/negative/neutral",
    "engagement_score": 8,
    "analysis_summary": "简短综合分析摘要",
    "comments_count": {len(comments)}
}}
"""

    # 重试逻辑 - 失败后跳过（不使用 fallback）
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.warning(f"Retry attempt {attempt}/{max_retries} for post {post_id}")
                await asyncio.sleep(2 ** attempt)  # 指数退避

            result = await agent.use_llm(
                prompt=prompt,
                response_model=PostWithCommentsAnalysis
            )

            if hasattr(result, 'model_dump'):
                analysis = result.model_dump()
            else:
                analysis = result

            logger.info(f"Analysis complete for {post_id}: relevant={analysis.get('relevant')}, sentiment={analysis.get('sentiment')}")

            # 添加 Reddit 特有字段到分析结果
            analysis["score"] = post_with_comments.get("score", 0)
            analysis["upvote_ratio"] = post_with_comments.get("upvote_ratio", 0)
            analysis["subreddit"] = post_with_comments.get("subreddit", "")
            analysis["num_comments"] = len(comments)
            analysis["created_utc"] = post_with_comments.get("created_utc", 0)

            return {
                "success": True,
                "post_id": post_id,
                "analysis": analysis
            }

        except (ValueError, ConnectionError, TimeoutError) as e:
            # 可重试的错误
            if attempt < max_retries:
                logger.warning(f"Attempt {attempt + 1} failed for post {post_id}: {type(e).__name__}: {e}")
                # 如果是 ValueError，打印更详细的信息
                if isinstance(e, ValueError):
                    import traceback
                    logger.debug(f"ValueError traceback for post {post_id}:\n{''.join(traceback.format_tb(e.__traceback__))}")
                continue
            else:
                # 所有重试失败 - 跳过此帖子（不使用 fallback）
                logger.error(f"All retries exhausted for post {post_id}: {type(e).__name__}: {e}")
                return {
                    "success": False,
                    "post_id": post_id,
                    "analysis": None,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "skipped": True
                }

        except Exception as e:
            # 不可重试的错误
            logger.error(f"Analyze post with comments skill failed for post {post_id}: {type(e).__name__}: {e}")
            return {
                "success": False,
                "post_id": post_id,
                "analysis": None,
                "error": str(e),
                "error_type": type(e).__name__,
                "skipped": True
            }


async def analyze_comments_skill(
    agent: BaseAgent,
    comments: List[Dict[str, Any]],
    business_idea: str,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    分析评论

    Args:
        agent: Agent 实例
        comments: 评论列表或字典 {note_id: [comments]}
        business_idea: 业务创意
        max_retries: 最大重试次数

    Returns:
        评论分析结果
    """
    # 处理不同的输入格式
    if isinstance(comments, dict):
        # 如果是字典，展平所有评论
        all_comments = []
        for note_comments in comments.values():
            if isinstance(note_comments, list):
                all_comments.extend(note_comments)
        comments_list = all_comments
    else:
        comments_list = comments

    logger.info(f"Analyzing {len(comments_list)} comments")

    if not comments_list:
        return {
            "success": True,
            "total_comments": 0,
            "insights": [],
            "common_themes": [],
            "sentiment_distribution": {"positive": 0, "negative": 0, "neutral": 0}
        }

    # 选取前20条评论进行分析（避免token过多）
    sample_comments = comments_list[:40]

    comments_text = "\n".join([
        f"- [{c.get('user_nickname', 'Anonymous')}] {c.get('content', '')}"
        for c in sample_comments
    ])

    prompt = f"""
你是一位用户洞察专家。请分析以下 Reddit 评论，提取用户对业务创意的反馈：

业务创意："{business_idea}"

评论内容：
{comments_text}

请分析：
1. 用户洞察：从评论中提取的关键洞察
2. 常见主题：评论中反复出现的主题
3. 情感分布：统计评论中的情感倾向
   - positive（正面）：包含赞美、满意、推荐、期待等积极情绪的评论
   - negative（负面）：包含抱怨、不满、批评、担忧等消极情绪的评论
   - neutral（中性）：主要是客观描述、询问、或情绪不明显的评论
   注意：只有当评论确实没有明显情感倾向时才归类为neutral
4. 用户需求：用户表达的具体需求
5. 痛点抱怨：用户的痛点或抱怨

请以 JSON 格式返回：
{{
    "insights": ["洞察1", "洞察2"],
    "common_themes": ["主题1", "主题2"],
    "sentiment_distribution": {{
        "positive": 10,
        "negative": 5,
        "neutral": 5
    }},
    "user_needs": ["需求1", "需求2"],
    "pain_points": ["痛点1", "痛点2"]
}}
"""

    # 重试逻辑
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.warning(f"Retry attempt {attempt}/{max_retries} for comments analysis")
                await asyncio.sleep(2 ** attempt)  # 指数退避

            result = await agent.use_llm(
                prompt=prompt,
                response_model=CommentsAnalysis
            )

            # 转换为字典
            if hasattr(result, 'model_dump'):
                analysis_dict = result.model_dump()
            else:
                analysis_dict = result

            logger.info(f"Comments analysis complete: {len(analysis_dict.get('insights', []))} insights")

            return {
                "success": True,
                "total_comments": len(comments_list),
                "analyzed_comments": len(sample_comments),
                "analysis": analysis_dict
            }

        except (ValueError, ConnectionError, TimeoutError) as e:
            # 可重试的错误
            if attempt < max_retries:
                logger.warning(f"Attempt {attempt + 1} failed for comments analysis: {e}, will retry...")
                continue
            else:
                logger.error(f"All retries exhausted for comments analysis: {e}")
                return {
                    "success": False,
                    "total_comments": len(comments_list),
                    "analysis": {
                        "insights": [],
                        "common_themes": [],
                        "sentiment_distribution": {"positive": 0, "negative": 0, "neutral": 0},
                        "user_needs": [],
                        "pain_points": []
                    },
                    "error": str(e),
                    "error_type": type(e).__name__
                }

        except Exception as e:
            # 不可重试的错误（如 JSON 解析错误）
            logger.error(f"Analyze comments skill failed: {type(e).__name__}: {e}")
            return {
                "success": False,
                "total_comments": len(comments_list),
                "analysis": {
                    "insights": [],
                    "common_themes": [],
                    "sentiment_distribution": {"positive": 0, "negative": 0, "neutral": 0},
                    "user_needs": [],
                    "pain_points": []
                },
                "error": str(e),
                "error_type": type(e).__name__
            }


async def batch_analyze_posts_skill(
    agent: BaseAgent,
    posts: List[Dict[str, Any]],
    business_idea: str,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """
    批量分析帖子

    Args:
        agent: Agent 实例
        posts: 帖子列表
        business_idea: 业务创意
        progress_callback: 进度回调

    Returns:
        批量分析结果
    """
    logger.info(f"Batch analyzing {len(posts)} posts")

    if not posts:
        return {
            "success": True,
            "total_posts": 0,
            "analyses": [],
            "relevant_count": 0,
            "summary": {}
        }

    all_analyses = []
    relevant_posts = []

    total = len(posts)
    for idx, post in enumerate(posts):
        try:
            if progress_callback:
                # Import ProgressUpdate model
                from models.agent_models import ProgressUpdate
                progress = idx / total  # 0-1 range
                update = ProgressUpdate(
                    step="analyzing_posts",
                    progress=progress,
                    message=f"正在分析帖子 {idx + 1}/{total}"
                )
                progress_callback(update)

            result = await analyze_post_skill(agent, post, business_idea)

            if result.get("success"):
                analysis = result.get("analysis", {})
                all_analyses.append({
                    "post_id": post.get("post_id"),
                    "title": post.get("title"),
                    "analysis": analysis
                })

                if analysis.get("relevant"):
                    relevant_posts.append({
                        "post": post,
                        "analysis": analysis
                    })

        except asyncio.CancelledError:
            # 任务被取消（超时）
            logger.warning(f"Batch analysis cancelled at post {idx + 1}/{total} (likely timeout)")
            # 返回已分析的部分结果
            partial_summary = _calculate_partial_summary(all_analyses, total)
            return {
                "success": False,
                "total_posts": total,
                "analyses": all_analyses,
                "relevant_posts": relevant_posts,
                "summary": partial_summary,
                "error": f"Operation cancelled (timeout) - analysed {len(all_analyses)}/{total} posts",
                "error_type": "CancelledError",
                "completed": len(all_analyses),
                "partial": True
            }

        except Exception as e:
            logger.error(f"Failed to analyze post {post.get('post_id')}: {e}")
            continue

    # 统计摘要
    relevant_count = len(relevant_posts)
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
    avg_engagement = 0

    for a in all_analyses:
        analysis = a.get("analysis", {})
        sentiment = analysis.get("sentiment", "neutral")
        if sentiment in sentiment_counts:
            sentiment_counts[sentiment] += 1
        avg_engagement += analysis.get("engagement_score", 0)

    if all_analyses:
        avg_engagement = avg_engagement / len(all_analyses)

    summary = {
        "total_posts": len(posts),
        "analyzed_count": len(all_analyses),
        "relevant_count": relevant_count,
        "relevance_rate": relevant_count / len(all_analyses) if all_analyses else 0,
        "sentiment_distribution": sentiment_counts,
        "avg_engagement_score": avg_engagement
    }

    logger.info(f"Batch analysis complete: {relevant_count}/{len(posts)} relevant")

    return {
        "success": True,
        "total_posts": len(posts),
        "analyses": all_analyses,
        "relevant_posts": relevant_posts,
        "summary": summary
    }


async def batch_analyze_posts_with_comments_skill(
    agent: BaseAgent,
    posts_with_comments: List[Dict[str, Any]],
    business_idea: str,
    progress_callback: Optional[callable] = None,
    max_posts: Optional[int] = None
) -> Dict[str, Any]:
    """
    批量分析帖子及其评论（统一分析）

    每个帖子与其评论作为一个整体进行综合分析，失败时跳过（不使用fallback）。

    Args:
        agent: Agent 实例
        posts_with_comments: 包含评论的帖子列表
        business_idea: 业务创意
        progress_callback: 进度回调
        max_posts: 最大分析帖子数（从配置获取，如果未指定则分析全部）

    Returns:
        批量分析结果
    """
    # 应用最大帖子数限制
    if max_posts is not None and max_posts > 0:
        original_count = len(posts_with_comments)
        posts_with_comments = posts_with_comments[:max_posts]
        logger.info(f"应用 max_posts 限制: 从 {original_count} 条减少到 {len(posts_with_comments)} 条")

    logger.info(f"Batch analyzing {len(posts_with_comments)} posts with comments")

    if not posts_with_comments:
        return {
            "success": True,
            "total_posts": 0,
            "analyses": [],
            "relevant_posts": [],
            "summary": {
                "total_posts": 0,
                "successful_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "relevant_count": 0
            }
        }

    all_analyses = []
    relevant_posts = []
    successful_count = 0
    failed_count = 0
    skipped_count = 0

    total = len(posts_with_comments)
    for idx, post in enumerate(posts_with_comments):
        try:
            if progress_callback:
                from models.agent_models import ProgressUpdate
                progress = idx / total  # 0-1 range
                update = ProgressUpdate(
                    step="analyzing_posts_with_comments",
                    progress=progress,
                    message=f"正在分析帖子+评论 {idx + 1}/{total}"
                )
                progress_callback(update)

            result = await analyze_post_with_comments_skill(agent, post, business_idea)

            if result.get("success"):
                analysis = result.get("analysis", {})
                all_analyses.append({
                    "post_id": post.get("post_id"),
                    "title": post.get("title"),
                    "analysis": analysis
                })
                successful_count += 1

                if analysis.get("relevant"):
                    relevant_posts.append({
                        "post": post,
                        "analysis": analysis
                    })
            else:
                # 分析失败，跳过此帖子（不添加到结果中）
                failed_count += 1
                if result.get("skipped"):
                    skipped_count += 1
                # 记录日志但继续处理
                logger.warning(
                    f"Skipped post {post.get('post_id')}: "
                    f"{result.get('error_type', 'Unknown')}"
                )

        except asyncio.CancelledError:
            # 任务被取消（超时）
            logger.warning(f"Batch analysis cancelled at post {idx + 1}/{total} (likely timeout)")
            # 返回已分析的部分结果
            partial_summary = _calculate_partial_summary_with_comments(all_analyses, total)
            partial_summary["successful_count"] = successful_count
            partial_summary["failed_count"] = failed_count
            partial_summary["skipped_count"] = skipped_count
            return {
                "success": False,
                "total_posts": total,
                "analyses": all_analyses,
                "relevant_posts": relevant_posts,
                "summary": partial_summary,
                "error": f"Operation cancelled (timeout) - analysed {len(all_analyses)}/{total} posts",
                "error_type": "CancelledError",
                "completed": len(all_analyses),
                "partial": True
            }

        except Exception as e:
            logger.error(f"Unexpected error analyzing post {post.get('post_id')}: {e}")
            failed_count += 1
            continue

    # 统计摘要
    relevant_count = len(relevant_posts)
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
    avg_engagement = 0
    
    # Reddit 特有指标
    total_score = 0
    total_upvote_ratio = 0
    subreddit_counts = {}
    total_comments_analyzed = 0
    from datetime import datetime, timezone
    thirty_days_ago = datetime.now(timezone.utc).timestamp() - (30 * 24 * 60 * 60)
    recent_posts_count = 0

    for a in all_analyses:
        analysis = a.get("analysis", {})
        sentiment = analysis.get("sentiment", "neutral")
        if sentiment in sentiment_counts:
            sentiment_counts[sentiment] += 1
        avg_engagement += analysis.get("engagement_score", 0)
        
        # Reddit 特有指标
        total_score += analysis.get("score", 0)
        total_upvote_ratio += analysis.get("upvote_ratio", 0)
        
        # 统计子版块分布
        subreddit = analysis.get("subreddit", "unknown")
        subreddit_counts[subreddit] = subreddit_counts.get(subreddit, 0) + 1
        
        # 统计评论数
        total_comments_analyzed += analysis.get("comments_count", 0)
        
        # 统计最近30天的帖子
        publish_time = analysis.get("publish_time", 0)
        if publish_time >= thirty_days_ago:
            recent_posts_count += 1

    if all_analyses:
        avg_engagement = avg_engagement / len(all_analyses)
        avg_score = total_score / len(all_analyses)
        avg_upvote_ratio = total_upvote_ratio / len(all_analyses)
    else:
        avg_score = 0
        avg_upvote_ratio = 0

    # 计算情感倾向分数（用于报告显示）
    sentiment_score = (
        sentiment_counts["positive"] - sentiment_counts["negative"]
    ) / len(all_analyses) if all_analyses else 0

    summary = {
        "total_posts": total,
        "successful_count": successful_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "relevant_count": relevant_count,
        "relevance_rate": relevant_count / successful_count if successful_count > 0 else 0,
        "sentiment_distribution": sentiment_counts,
        "avg_engagement_score": avg_engagement,
        "avg_sentiment": sentiment_score,
        "total_comments_analyzed": total_comments_analyzed,
        "recent_posts_30days": recent_posts_count,
        "avg_score": avg_score,
        "avg_upvote_ratio": avg_upvote_ratio,
        "subreddit_distribution": subreddit_counts
    }

    logger.info(
        f"Batch analysis complete: {successful_count}/{total} successful, "
        f"{relevant_count} relevant, {skipped_count} skipped"
    )

    return {
        "success": True,
        "total_posts": total,
        "analyses": all_analyses,
        "relevant_posts": relevant_posts,
        "summary": summary
    }


async def analyze_comments_with_tags_skill(
    agent: BaseAgent,
    posts_with_comments: List[Dict[str, Any]],
    business_idea: str,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    使用标签体系分析评论

    分两个步骤：
    1. 生成标签体系 (generate_doc_description)
    2. 对每个 Post 的全部评论进行标签分析 (do_review)

    Args:
        agent: Agent 实例
        posts_with_comments: 包含评论的帖子列表
        business_idea: 业务创意
        max_retries: 最大重试次数

    Returns:
        评论标签分析结果
    """
    logger.info(f"Starting tag-based comments analysis for {len(posts_with_comments)} posts")

    # 第一步：收集相关帖子的评论文本 (only from posts relevant to the business idea)
    all_comments = []
    for post in posts_with_comments:
        # Check if the post has been analyzed and is relevant to the business idea
        # The post should have analysis data indicating relevance
        # If analysis is not available, we'll include the comments (conservative approach)
        analysis = post.get('analysis', {})
        is_relevant = analysis.get('relevant', True)  # Default to True if not specified

        if is_relevant:
            comments = post.get('comments_data', [])
            all_comments.extend(comments)
        else:
            logger.debug(f"Skipping comments from post {post.get('post_id', 'unknown')} as it is not relevant to the business idea")

    total_comments = len(all_comments)
    if total_comments == 0:
        logger.warning("No comments found for tag analysis")
        return {
            "success": True,
            "tag_analysis": {
                "crowd_scenario": {},
                "functional_value": {},
                "assurance_value": {},
                "experience_value": {},
                "total_comments_analyzed": 0,
                "total_tags_applied": 0,
                "analysis_summary": "没有找到评论数据",
                "tag_statistics": {}
            }
        }

    logger.info(f"Collected {total_comments} comments for tag analysis")

    # 为避免 token 过多，选取最多 50 条评论进行分析
    sample_comments = all_comments[:50] if total_comments > 50 else all_comments
    logger.info(f"Using {len(sample_comments)} comments for analysis (sampled from {total_comments} total)")

    # 构建评论文本内容
    comments_text = "\n".join([
        f"{i+1}. 用户: {c.get('user_nickname', 'Anonymous')}\n   评论: {c.get('content', '')}\n"
        for i, c in enumerate(sample_comments)
    ])

    # 第二步：生成标签体系
    logger.info("Step 1: Generating tag system from comments...")
    tag_generation_prompt = f"""# 构建 Reddit 商业和技术讨论标签体系

## 您的任务：
您是一位资深的 Reddit 社区分析专家。您的任务是基于我提供的 Reddit 讨论评论，为商业和技术话题构建一个结构化的、多层级的分析标签体系。这个标签体系将用于后续对每条评论进行细致的分类和打标，以便深入洞察 Reddit 社区对各种产品、服务、技术、商业模式的观点和需求。

## 核心理论知识（请先学习并理解）

1.  用户价值层级模型： 我们将从 Reddit 用户的角度出发，将他们对产品、服务、技术、商业模式的关注点和评价归纳到以下四个核心价值层级。您的标签设计需要围绕这些层级展开：
    *   人群与场景 (Crowd & Scenario): 描述的是"谁"在"什么情况下"讨论产品/服务/技术。这包括用户的身份特征、行业背景、使用场景、讨论的具体情境或期望达成的目标。
    *   功能价值 (FunctionalValue): 指产品/服务/技术为了解决用户的核心问题所提供的具体功能、性能表现以及技术特性。
    *   保障价值 (AssuranceValue): 涉及产品/服务的可靠性、安全性、隐私保护，以及客户服务、售后支持、开源生态、社区支持等方面。
    *   体验价值 (ExperienceValue): 涵盖用户在与产品/服务/技术交互的整个过程中的主观感受，包括易用性、社区氛围、学习资源、推荐意愿等。

2.  标签设计原则：
    *   层级性： 标签体系应具有清晰的层级结构（一级标签、二级标签、三级标签）。
    *   覆盖性： 能够尽可能全面地覆盖评论中用户提及的主要议题。
    *   互斥性（理想状态）： 同一级下的标签应尽可能互斥，避免语义重叠过多。
    *   简洁性： 每个标签的名称应简洁明了，尽量不超过 8 个字符。
    *   客观性： 标签本身不应包含情感倾向（如"效果好"、"质量差"），仅客观描述讨论的主题（如"功能完整性"、"性能表现"）。情感分析将在后续打标步骤中独立进行。
    *   可扩展性： 体系应具备一定的灵活性，方便未来根据新的评论内容进行补充和调整。

标签体系层级结构定义：

*   一级标签 (Level1Tag): 必须是以下四个固定维度之一：
    1.`人群与场景`
    2.`功能价值`
    3.`保障价值`
    4.`体验价值`

*   二级标签 (Level2Tag): 是对一级标签的进一步细分，代表了该价值层级下的主要关注领域。
    *   示例（可根据商业和技术讨论调整）：
        *   一级标签：`人群与场景`
            *   二级标签：`用户群体-身份特征` (分析讨论者的身份：开发者、企业用户、消费者、投资者、研究人员等)
            *   二级标签：`使用场景-应用领域` (分析产品/服务的应用场景：日常使用、商业应用、技术开发、投资决策等)
            *   二级标签：`讨论主题-话题类型` (分析讨论的具体主题：产品对比、市场分析、技术评估、商业模式等)
        *   一级标签：`功能价值`
            *   二级标签：`产品功能-核心能力` (分析产品/服务的核心功能、功能完整性、创新性等)
            *   二级标签：`性能表现-核心指标` (分析产品/服务的性能指标：速度、效率、质量、可靠性等)
            *   二级标签：`技术特性-技术优势` (分析技术架构、技术优势、技术壁垒等)
        *   一级标签：`保障价值`
            *   二级标签：`可靠性-质量保证` (分析产品/服务的稳定性、质量保证、可靠性等)
            *   二级标签：`服务支持-客户服务` (分析客户服务、售后支持、技术支持等)
            *   二级标签：`生态支持-社区商业` (分析开源生态、社区支持、商业许可、合作伙伴等)
        *   一级标签：`体验价值`
            *   二级标签：`用户体验-易用性` (分析产品/服务的易用性、界面设计、交互体验等)
            *   二级标签：`社区氛围-讨论质量` (分析讨论质量、社区活跃度、用户友好度、学习资源等)
            *   二级标签：`推荐意愿-使用意向` (分析用户推荐给他人、持续使用、购买意愿、投资意向等)

*   三级标签 (Level3Tag): 是对二级标签的具体化，代表了用户评论中实际讨论到的、更细致的主题点。这是您需要根据提供的评论文本重点设计的部分。

您的具体操作指令：

1.  仔细阅读并分析我提供的一批 Reddit 用户评论（关于商业和技术的讨论）。
2.  基于上述理论知识、层级结构定义和设计原则，为这批评论所讨论的商业和技术话题生成一个三级标签体系。
3.  一级标签和二级标签的类别和名称，您可以参考我给出的示例进行扩展或调整，使其更贴合实际评论内容，但一级标签必须是固定的四个维度。
4.  三级标签是您创造性的核心，需要您从评论中提炼用户实际讨论的具体议题点，并用简洁的词语命名。
5.  确保每个三级标签都归属于一个明确的二级标签和一级标签。
6.  输出格式要求：请以结构化的JSON格式输出您设计的标签体系。

## 业务创意背景：
{business_idea}

## Reddit 用户评论文本:
{comments_text}

请直接返回 JSON 格式的标签体系，不要包含任何其他文本。

```json
{{
  "人群场景":{{
    "用户群体-身份特征":[
      "开发者",
      "企业用户",
      "消费者"
    ],
    "使用场景-应用领域":[
      "日常使用",
      "商业应用"
    ]
  }},
  "功能价值":{{
    "产品功能-核心能力":[
      "功能完整性",
      "创新性"
    ],
    "性能表现-核心指标":[
      "性能表现",
      "质量"
    ]
  }},
  "保障价值":{{
    "可靠性-质量保证":[
      "稳定性",
      "质量保证"
    ],
    "服务支持-客户服务":[
      "客户服务",
      "售后支持"
    ]
  }},
  "体验价值":{{
    "用户体验-易用性":[
      "易用性",
      "界面设计"
    ],
    "社区氛围-讨论质量":[
      "讨论质量",
      "学习资源"
    ]
  }}
}}
```
"""

    try:
        logger.info("=" * 80)
        logger.info("[LLM REQUEST] 开始生成标签体系")
        logger.info(f"[LLM REQUEST] 业务创意: {business_idea}")
        logger.info(f"[LLM REQUEST] 评论数量: {len(sample_comments)}")
        logger.debug(f"[LLM REQUEST] Prompt 长度: {len(tag_generation_prompt)} 字符")
        logger.debug(f"[LLM REQUEST] Prompt 内容:\n{tag_generation_prompt[:1000]}...")  # 只记录前1000字符

        # 调用 LLM 生成标签体系
        tag_system_result = await agent.use_llm(
            prompt=tag_generation_prompt,
            response_model=TagSystemGeneration  # 使用 TagSystemGeneration 模型
        )

        logger.info("[LLM RESPONSE] 标签体系生成成功")
        logger.debug(f"[LLM RESPONSE] 结果类型: {type(tag_system_result)}")
        logger.debug(f"[LLM RESPONSE] 原始结果: {tag_system_result}")

        # 提取标签体系
        # tag_system_result 现在是 TagSystemGeneration 对象
        if hasattr(tag_system_result, 'model_dump'):
            tag_system = tag_system_result.model_dump()
        else:
            tag_system = tag_system_result

        logger.info(f"[LLM RESPONSE] 标签体系解析完成，包含 {len(tag_system)} 个一级分类")
        logger.debug(f"[LLM RESPONSE] 标签体系详情: {tag_system}")
        logger.info("=" * 80)

        # 第三步：对每个 Post 的全部评论进行标签分析（按 Post 分析，而非逐条评论）
        logger.info("Step 2: Analyzing each post's comments with tag system...")

        # 将标签体系转换为字符串格式，用于后续评论分析
        tag_system_str = str(tag_system)

        # 统计标签应用次数
        tag_statistics = {}
        total_tags_applied = 0

        # 按 Post 分析每个帖子的评论
        analyzed_results = []

        for post_idx, post in enumerate(posts_with_comments):
            # Check if the post has been analyzed and is relevant to the business idea
            analysis = post.get('analysis', {})
            is_relevant = analysis.get('relevant', True)  # Default to True if not specified

            if not is_relevant:
                logger.debug(f"Skipping post {post.get('post_id', 'unknown')} as it is not relevant to the business idea")
                continue

            # 获取该 Post 的所有评论
            comments = post.get('comments_data', [])
            if not comments:
                logger.debug(f"No comments for post {post.get('post_id', 'unknown')}")
                continue

            # 合并该 Post 的所有评论为一个文本
            post_comments_text = "\n".join([
                f"{i+1}. 用户: {c.get('author', 'Anonymous')}\n   评论: {c.get('body', '')}\n"
                for i, c in enumerate(comments)
            ])

            # 构建标签分析提示 - 分析该 Post 的全部评论
            tagging_prompt = f"""请基于商业和技术讨论标签体系对以下 Reddit 评论进行标签匹配分析。

## 标签体系
{tag_system_str}

## 分析规则
- 匹配标签：保留该标签
- 无关标签：移除该标签
- 负面评价：记为 -标签（例如：-易用性）

## 帖子信息
帖子ID: {post.get('post_id', 'unknown')}
帖子标题: {post.get('title', 'unknown')}
子版块: {post.get('subreddit', 'unknown')}

## 帖子评论内容（共 {len(comments)} 条）
{post_comments_text}

## 输出格式
直接返回JSON格式的标签体系结构，只保留匹配到的标签。空分类用{{}}。

示例：
```json
{{"人群场景": {{"用户群体-身份特征": ["开发者"]}}, "功能价值": {{"产品功能-核心能力": ["功能完整性"]}}}}
```

重要：直接返回JSON，不要包含任何解释文字。
"""

            try:
                logger.info("-" * 60)
                logger.info(f"[LLM REQUEST] 开始分析帖子 {post_idx + 1}/{len(posts_with_comments)}")
                logger.info(f"[LLM REQUEST] 帖子ID: {post.get('post_id')}")
                logger.info(f"[LLM REQUEST] 帖子标题: {post.get('title', '')}")
                logger.info(f"[LLM REQUEST] 评论数量: {len(comments)}")
                logger.debug(f"[LLM REQUEST] Prompt 长度: {len(tagging_prompt)} 字符")
                logger.debug(f"[LLM REQUEST] Prompt 内容:\n{tagging_prompt[:500]}...")  # 只记录前500字符

                # 调用 LLM 进行标签分析（一次调用分析该 Post 的所有评论）
                post_tags_result = await agent.use_llm(
                    prompt=tagging_prompt,
                    response_model=TagSystemGeneration  # 使用 TagSystemGeneration 模型
                )

                logger.info(f"[LLM RESPONSE] 帖子 {post.get('post_id')} 分析成功")
                logger.debug(f"[LLM RESPONSE] 结果类型: {type(post_tags_result)}")
                logger.debug(f"[LLM RESPONSE] 原始结果: {post_tags_result}")

                # 转换为字典
                if hasattr(post_tags_result, 'model_dump'):
                    post_tags = post_tags_result.model_dump()
                elif isinstance(post_tags_result, str):
                    post_tags = _extract_json_from_response(post_tags_result)
                elif isinstance(post_tags_result, dict):
                    post_tags = post_tags_result
                else:
                    logger.warning(f"[LLM RESPONSE] Unexpected post_tags_result type: {type(post_tags_result)}")
                    post_tags = {}

                logger.debug(f"[LLM RESPONSE] 解析后的标签: {post_tags}")
                logger.info(f"[LLM RESPONSE] 应用标签数量: {sum(len(v) if isinstance(v, list) else 1 for d in post_tags.values() if isinstance(d, dict) for v in d.values()) if isinstance(post_tags, dict) else 0}")
                logger.info("-" * 60)

                # 统计标签应用 - 按二级分类统计
                if isinstance(post_tags, dict):
                    for category_key, category_value in post_tags.items():
                        if isinstance(category_value, dict):
                            for subcategory_key, tags_list in category_value.items():
                                # 确保二级分类存在于统计字典中
                                if subcategory_key not in tag_statistics:
                                    tag_statistics[subcategory_key] = {}
                                
                                # 处理标签列表
                                if isinstance(tags_list, list):
                                    for tag in tags_list:
                                        if isinstance(tag, str) and tag.strip():  # Only count non-empty tags
                                            tag_statistics[subcategory_key][tag] = tag_statistics[subcategory_key].get(tag, 0) + 1
                                            total_tags_applied += 1
                                elif isinstance(tags_list, str) and tags_list.strip():  # Handle case where tags_list is a single string
                                    tag_statistics[subcategory_key][tags_list] = tag_statistics[subcategory_key].get(tags_list, 0) + 1
                                    total_tags_applied += 1
                        else:
                            logger.debug(f"Category value is not a dict: {category_key} = {category_value}")
                else:
                    logger.warning(f"Invalid post_tags format for post {post.get('post_id')}: {type(post_tags)}")
                    post_tags = {}

                analyzed_results.append({
                    "post_id": post.get('post_id'),
                    "title": post.get('title', ''),
                    "comments_count": len(comments),
                    "tags": post_tags
                })

            except Exception as e:
                logger.error("=" * 60)
                logger.error(f"[LLM ERROR] 帖子 {post.get('post_id')} 分析失败")
                logger.error(f"[LLM ERROR] 错误类型: {type(e).__name__}")
                logger.error(f"[LLM ERROR] 错误信息: {str(e)}")
                logger.error(f"[LLM ERROR] 帖子标题: {post.get('title', '')[:100]}...")
                logger.error(f"[LLM ERROR] 评论数量: {len(comments)}")
                import traceback
                logger.error(f"[LLM ERROR] 完整堆栈:\n{''.join(traceback.format_tb(e.__traceback__))}")
                logger.error("=" * 60)
                # 失败的帖子添加空标签
                analyzed_results.append({
                    "post_id": post.get('post_id'),
                    "title": post.get('title', ''),
                    "comments_count": len(comments),
                    "tags": {},
                    "error": str(e),
                    "error_type": type(e).__name__
                })

        # 聚合所有 Post 中匹配到的标签
        aggregated_tags = {
            "人群场景": {},
            "功能价值": {},
            "保障价值": {},
            "体验价值": {}
        }

        for result in analyzed_results:
            post_tags = result.get("tags", {})
            if isinstance(post_tags, dict):
                for category_key, category_value in post_tags.items():
                    # 确保分类键存在于聚合字典中
                    if category_key not in aggregated_tags:
                        aggregated_tags[category_key] = {}
                    
                    if isinstance(category_value, dict):
                        for subcategory_key, tags_list in category_value.items():
                            # 初始化子分类列表
                            if subcategory_key not in aggregated_tags[category_key]:
                                aggregated_tags[category_key][subcategory_key] = []
                            
                            # 处理标签列表
                            if isinstance(tags_list, list):
                                for tag in tags_list:
                                    if isinstance(tag, str) and tag.strip() and tag not in aggregated_tags[category_key][subcategory_key]:
                                        aggregated_tags[category_key][subcategory_key].append(tag)
                            elif isinstance(tags_list, str) and tags_list.strip():
                                # 处理单个字符串的情况
                                if tags_list not in aggregated_tags[category_key][subcategory_key]:
                                    aggregated_tags[category_key][subcategory_key].append(tags_list)
                    else:
                        logger.debug(f"Category value is not a dict during aggregation: {category_key} = {category_value}")

        # 构建最终的标签分析结果（使用聚合后的标签，而不是原始标签体系）
        tag_analysis = {
            "crowd_scenario": aggregated_tags.get("人群场景", {}),
            "functional_value": aggregated_tags.get("功能价值", {}),
            "assurance_value": aggregated_tags.get("保障价值", {}),
            "experience_value": aggregated_tags.get("体验价值", {}),
            "total_posts_analyzed": len(analyzed_results),
            "total_tags_applied": total_tags_applied,
            "analysis_summary": f"基于 {len(analyzed_results)} 个帖子的评论生成的标签体系，共应用 {total_tags_applied} 个标签",
            "tag_statistics": tag_statistics
        }

        logger.info(f"Tag analysis complete: {total_tags_applied} tags applied across {len(analyzed_results)} posts")

        # 第四步：生成用户画像
        logger.info("Step 3: Generating user personas from comments...")
        
        # 重新构建所有 Post 的评论文本用于用户画像生成
        all_comments_for_persona = []
        for post in posts_with_comments:
            analysis = post.get('analysis', {})
            is_relevant = analysis.get('relevant', True)
            if is_relevant:
                comments = post.get('comments_data', [])
                all_comments_for_persona.extend(comments)
        
        # 构建用户画像的评论文本
        persona_comments_text = "\n".join([
            f"{i+1}. 用户: {c.get('user_nickname', 'Anonymous')}\n   评论: {c.get('content', '')}\n"
            for i, c in enumerate(all_comments_for_persona)
        ])
        
        persona_generation_prompt = f"""# 你是一名用户画像分析师。

## 分析需求和概念：

### 基础属性描述
用户的静态人口统计学特征。
示例：
- 年龄：28岁
- 性别：女性
- 地理位置：上海
- 职业：全职妈妈

### 行为特征描述
用户的实际行为轨迹，体现用户"做了什么"。
示例标签：
- 月消费金额：2000元
- 购买频率：每月购买4次母婴用品
- 活跃时间段：周末、晚上

### 心理动机描述
用户行为背后的动机、价值观和偏好，体现"为什么这么做"。
示例：
- 对促销活动敏感：对满减和赠品活动高度关注
- 品牌偏好：倾向选择国际知名母婴品牌
- 商品安全性：重视商品成分和评价

### 外部环境描述
用户所处的社会环境和关系网络，体现外部影响因素。
示例：
- 社交圈：经常与其他宝妈分享购物心得
- 活跃平台：微博、母婴论坛
- 购买决策：受KOL推荐影响

### 需求痛点
明确用户的核心需求和主要问题，帮助定义用户的关键目标。
示例：
- 需求：寻找高品质、高性价比的母婴用品
- 痛点：缺乏时间，偏好快速送达
- 期待：希望平台提供可信赖的商品评价体系

## 任务要求：
请根据以下用户评论数据，生成3-5个典型用户画像。

每个画像必须包含以下信息：
1. **性别年龄估计**: 基于评论内容推测用户的性别和大致年龄段
2. **需求关键词**: 从评论中提取3-5个关键需求关键词
3. **购买动机**: 分析用户购买该产品背后的动机（3-5个）
4. **情绪语气判断**: 判断评论整体的情绪语气（积极/中性/消极）
5. **用户画像标签**: 总结3-5个描述用户特征的标签

## 业务创意背景：
{business_idea}

## 用户评论文本（显示前30条）:
{persona_comments_text[:3000]}

请以 JSON 格式返回用户画像分析结果：

```json
{{
  "personas": [
    {{
      "gender": "女性",
      "age_estimate": "25-35岁",
      "demand_keywords": ["品质", "性价比", "安全性", "便捷性", "售后服务"],
      "purchase_motivation": ["解决实际需求", "朋友推荐", "价格实惠", "品牌信任", "促销活动"],
      "emotional_tone": "积极",
      "persona_tags": ["精明消费者", "注重品质", "价格敏感", "重视口碑", "活跃于社交平台"]
    }},
    {{
      "gender": "男性",
      "age_estimate": "30-40岁",
      "demand_keywords": ["性能", "耐用性", "技术创新", "品牌", "专业"],
      "purchase_motivation": ["工作需要", "技术爱好", "升级换代", "专业推荐", "尝鲜"],
      "emotional_tone": "中性",
      "persona_tags": ["技术控", "追求性能", "理性决策", "品牌忠诚", "早期采用者"]
    }}
  ],
  "total_personas": 2,
  "analysis_summary": "基于评论内容生成的典型用户画像分析"
}}
```

请直接返回 JSON 格式的用户画像分析结果，不要包含任何其他文本。
"""

        try:
            logger.info("=" * 80)
            logger.info("[LLM REQUEST] 开始生成用户画像")
            logger.info(f"[LLM REQUEST] 业务创意: {business_idea}")
            logger.info(f"[LLM REQUEST] 评论数量: {len(all_comments_for_persona)}")
            logger.debug(f"[LLM REQUEST] Prompt 长度: {len(persona_generation_prompt)} 字符")
            logger.debug(f"[LLM REQUEST] Prompt 内容:\n{persona_generation_prompt[:1000]}...")  # 只记录前1000字符

            # 调用 LLM 生成用户画像
            persona_result = await agent.use_llm(
                prompt=persona_generation_prompt,
                response_model=PersonaAnalysis
            )

            logger.info("[LLM RESPONSE] 用户画像生成成功")
            logger.debug(f"[LLM RESPONSE] 结果类型: {type(persona_result)}")
            logger.debug(f"[LLM RESPONSE] 原始结果: {persona_result}")

            if hasattr(persona_result, 'model_dump'):
                persona_analysis = persona_result.model_dump()
            else:
                persona_analysis = persona_result

            logger.info(f"[LLM RESPONSE] 用户画像解析完成，生成 {persona_analysis.get('total_personas', 0)} 个画像")
            logger.debug(f"[LLM RESPONSE] 用户画像详情: {persona_analysis}")
            logger.info("=" * 80)

            # 将用户画像添加到标签分析结果中
            tag_analysis["persona_analysis"] = persona_analysis

            return {
                "success": True,
                "tag_analysis": tag_analysis,
                "analyzed_results": analyzed_results,
                "total_posts_analyzed": len(analyzed_results),
                "total_comments": len(all_comments_for_persona),
                "persona_analysis": persona_analysis
            }

        except Exception as e:
            logger.error("=" * 80)
            logger.error("[LLM ERROR] 用户画像生成失败")
            logger.error(f"[LLM ERROR] 错误类型: {type(e).__name__}")
            logger.error(f"[LLM ERROR] 错误信息: {str(e)}")
            import traceback
            logger.error(f"[LLM ERROR] 完整堆栈:\n{''.join(traceback.format_tb(e.__traceback__))}")
            logger.error("=" * 80)
            # 用户画像生成失败不影响标签分析结果
            return {
                "success": True,
                "tag_analysis": tag_analysis,
                "analyzed_results": analyzed_results,
                "total_posts_analyzed": len(analyzed_results),
                "total_comments": len(all_comments_for_persona),
                "persona_analysis": None,
                "persona_error": str(e),
                "persona_error_type": type(e).__name__
            }

    except Exception as e:
        logger.error("=" * 80)
        logger.error("[LLM ERROR] 标签分析整体失败")
        logger.error(f"[LLM ERROR] 错误类型: {type(e).__name__}")
        logger.error(f"[LLM ERROR] 错误信息: {str(e)}")
        logger.error(f"[LLM ERROR] 业务创意: {business_idea}")
        logger.error(f"[LLM ERROR] 帖子数量: {len(posts_with_comments)}")
        logger.error(f"[LLM ERROR] 评论总数: {total_comments}")
        import traceback
        logger.error(f"[LLM ERROR] 完整堆栈:\n{''.join(traceback.format_tb(e.__traceback__))}")
        logger.error("=" * 80)

        # 返回失败结果
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "tag_analysis": {
                "crowd_scenario": {},
                "functional_value": {},
                "assurance_value": {},
                "experience_value": {},
                "total_comments_analyzed": 0,
                "total_tags_applied": 0,
                "analysis_summary": f"分析失败: {str(e)}",
                "tag_statistics": {}
            },
            "persona_analysis": None
        }


async def generate_combined_analysis_from_posts_skill(
    agent: BaseAgent,
    posts_with_comments_analyses: Dict[str, Any],
    business_idea: str,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    从帖子分析生成综合分析报告（不使用单独的评论分析）

    Args:
        agent: Agent 实例
        posts_with_comments_analyses: 帖子+评论统一分析结果
        business_idea: 业务创意
        max_retries: 最大重试次数

    Returns:
        综合分析结果
    """
    logger.info("Generating combined analysis from posts with comments")

    # 提取关键信息
    summary = posts_with_comments_analyses.get("summary", {})
    relevant_posts = posts_with_comments_analyses.get("relevant_posts", [])

    # 收集痛点和解决方案
    all_pain_points = []
    all_solutions = []
    all_signals = []
    all_user_insights = []
    all_user_needs = []

    for item in relevant_posts:
        analysis = item.get("analysis", {})
        all_pain_points.extend(analysis.get("pain_points", []))
        all_solutions.extend(analysis.get("solutions_mentioned", []))
        all_signals.extend(analysis.get("market_signals", []))
        all_user_insights.extend(analysis.get("user_insights", []))
        all_user_needs.extend(analysis.get("user_needs", []))

    # 构建综合分析提示
    # 注意：不截取数据，将所有数据传递给 LLM 以获得全面的分析
    prompt = f"""
你是一位资深市场分析师。请根据以下数据，为业务创意生成一份综合市场验证分析报告：

业务创意："{business_idea}"

=== 数据摘要 ===
相关帖子数: {summary.get('relevant_count', 0)}
相关性比例: {summary.get('relevance_rate', 0):.1%}
平均互动评分: {summary.get('avg_engagement_score', 0):.1f}/10
情感分布: {summary.get('sentiment_distribution', {})}

=== 关键痛点（共{len(all_pain_points)}条）===
{chr(10).join(f"- {p}" for p in all_pain_points)}

=== 现有解决方案（共{len(all_solutions)}条）===
{chr(10).join(f"- {s}" for s in all_solutions)}

=== 市场信号（共{len(all_signals)}条）===
{chr(10).join(f"- {s}" for s in all_signals)}

=== 用户洞察（共{len(all_user_insights)}条）===
{chr(10).join(f"- {i}" for i in all_user_insights)}

=== 用户需求（共{len(all_user_needs)}条）===
{chr(10).join(f"- {n}" for n in all_user_needs)}

请生成综合分析报告，**重要：请基于提供的所有数据（{len(relevant_posts)}个帖子的分析）进行全面分析**，包括：
1. 综合评分 (0-100): 基于市场需求、竞争程度、用户反馈等因素
2. 市场验证摘要: 200-300字的市场验证总结
3. 关键痛点: 提取所有重要痛点（至少5-10个），按重要性排序
4. 现有解决方案: 列出所有当前市场上的解决方案（至少5个）
5. 市场机会: 基于分析发现的市场机会（至少5个）
6. 建议: 针对该业务创意的具体建议（至少5条）

请以 JSON 格式返回：
{{
    "overall_score": 75,
    "market_validation_summary": "市场验证摘要...",
    "key_pain_points": ["痛点1", "痛点2", "痛点3", ...],
    "existing_solutions": ["方案1", "方案2", ...],
    "market_opportunities": ["机会1", "机会2", "机会3", ...],
    "recommendations": ["建议1", "建议2", "建议3", ...],
    "metadata": {{
        "total_posts_analyzed": {len(relevant_posts)},
        "total_pain_points_found": {len(all_pain_points)},
        "total_solutions_found": {len(all_solutions)},
        "analysis_date": "{datetime.now().isoformat()}"
    }}
}}
"""

    # 重试逻辑
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.warning(f"Retry attempt {attempt}/{max_retries} for combined analysis")
                await asyncio.sleep(2 ** attempt)  # 指数退避

            result = await agent.use_llm(
                prompt=prompt,
                response_model=CombinedAnalysis
            )

            if hasattr(result, 'model_dump'):
                analysis = result.model_dump()
            else:
                analysis = result

            logger.info(f"Combined analysis complete: score={analysis.get('overall_score')}/100")

            return {
                "success": True,
                "analysis": analysis
            }

        except (ValueError, ConnectionError, TimeoutError) as e:
            # 可重试的错误
            if attempt < max_retries:
                logger.warning(f"Attempt {attempt + 1} failed for combined analysis: {e}, will retry...")
                continue
            else:
                logger.error(f"All retries exhausted for combined analysis: {e}")
                return {
                    "success": False,
                    "analysis": {
                        "overall_score": 50,
                        "market_validation_summary": f"分析失败（重试{max_retries}次后仍失败）: {type(e).__name__}",
                        "key_pain_points": all_pain_points[:5] if all_pain_points else [],
                        "existing_solutions": all_solutions[:5] if all_solutions else [],
                        "market_opportunities": [],
                        "recommendations": ["请重新运行分析"],
                        "metadata": {}
                    },
                    "error": str(e),
                    "error_type": type(e).__name__
                }

        except Exception as e:
            # 不可重试的错误（如 JSON 解析错误）
            logger.error(f"Generate combined analysis skill failed: {type(e).__name__}: {e}")
            return {
                "success": False,
                "analysis": {
                    "overall_score": 50,
                    "market_validation_summary": f"分析失败: {type(e).__name__}",
                    "key_pain_points": all_pain_points[:5] if all_pain_points else [],
                    "existing_solutions": all_solutions[:5] if all_solutions else [],
                    "market_opportunities": [],
                    "recommendations": ["请重新运行分析"],
                    "metadata": {}
                },
                "error": str(e),
                "error_type": type(e).__name__
            }


async def generate_combined_analysis_skill(
    agent: BaseAgent,
    posts_analyses: Dict[str, Any],
    comments_analyses: Dict[str, Any],
    business_idea: str,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    生成综合分析报告

    Args:
        agent: Agent 实例
        posts_analyses: 帖子分析结果
        comments_analyses: 评论分析结果
        business_idea: 业务创意
        max_retries: 最大重试次数

    Returns:
        综合分析结果
    """
    logger.info("Generating combined analysis")

    # 提取关键信息
    summary = posts_analyses.get("summary", {})
    relevant_posts = posts_analyses.get("relevant_posts", [])

    # 收集痛点和解决方案
    all_pain_points = []
    all_solutions = []
    all_signals = []

    for item in relevant_posts:
        analysis = item.get("analysis", {})
        all_pain_points.extend(analysis.get("pain_points", []))
        all_solutions.extend(analysis.get("solutions_mentioned", []))
        all_signals.extend(analysis.get("market_signals", []))

    # 评论分析
    comments_analysis = comments_analyses.get("analysis", {})
    user_insights = comments_analysis.get("insights", [])
    common_themes = comments_analysis.get("common_themes", [])

    # 构建综合分析提示
    # 注意：不截取数据，将所有数据传递给 LLM 以获得全面的分析
    prompt = f"""
你是一位资深市场分析师。请根据以下数据，为业务创意生成一份综合市场验证分析报告：

业务创意："{business_idea}"

=== 数据摘要 ===
相关帖子数: {summary.get('relevant_count', 0)}
相关性比例: {summary.get('relevance_rate', 0):.1%}
平均互动评分: {summary.get('avg_engagement_score', 0):.1f}/10
情感分布: {summary.get('sentiment_distribution', {})}

=== 关键痛点（共{len(all_pain_points)}条）===
{chr(10).join(f"- {p}" for p in all_pain_points)}

=== 现有解决方案（共{len(all_solutions)}条）===
{chr(10).join(f"- {s}" for s in all_solutions)}

=== 市场信号（共{len(all_signals)}条）===
{chr(10).join(f"- {s}" for s in all_signals)}

=== 用户洞察（共{len(user_insights)}条）===
{chr(10).join(f"- {i}" for i in user_insights)}

=== 常见主题（共{len(common_themes)}条）===
{chr(10).join(f"- {t}" for t in common_themes)}

请生成综合分析报告，**重要：请基于提供的所有数据（{len(relevant_posts)}个帖子的分析）进行全面分析**，包括：
1. 综合评分 (0-100): 基于市场需求、竞争程度、用户反馈等因素
2. 市场验证摘要: 200-300字的市场验证总结
3. 关键痛点: 提取所有重要痛点（至少5-10个），按重要性排序
4. 现有解决方案: 列出所有当前市场上的解决方案（至少5个）
5. 市场机会: 基于分析发现的市场机会（至少5个）
6. 建议: 针对该业务创意的具体建议（至少5条）

请以 JSON 格式返回：
{{
    "overall_score": 75,
    "market_validation_summary": "市场验证摘要...",
    "key_pain_points": ["痛点1", "痛点2", "痛点3", ...],
    "existing_solutions": ["方案1", "方案2", ...],
    "market_opportunities": ["机会1", "机会2", "机会3", ...],
    "recommendations": ["建议1", "建议2", "建议3", ...],
    "metadata": {{
        "total_posts_analyzed": {len(relevant_posts)},
        "total_pain_points_found": {len(all_pain_points)},
        "total_solutions_found": {len(all_solutions)},
        "analysis_date": "{datetime.now().isoformat()}"
    }}
}}
"""

    # 重试逻辑
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.warning(f"Retry attempt {attempt}/{max_retries} for combined analysis")
                await asyncio.sleep(2 ** attempt)  # 指数退避

            result = await agent.use_llm(
                prompt=prompt,
                response_model=CombinedAnalysis
            )

            if hasattr(result, 'model_dump'):
                analysis = result.model_dump()
            else:
                analysis = result

            logger.info(f"Combined analysis complete: score={analysis.get('overall_score')}/100")

            return {
                "success": True,
                "analysis": analysis
            }

        except (ValueError, ConnectionError, TimeoutError) as e:
            # 可重试的错误
            if attempt < max_retries:
                logger.warning(f"Attempt {attempt + 1} failed for combined analysis: {e}, will retry...")
                continue
            else:
                logger.error(f"All retries exhausted for combined analysis: {e}")
                return {
                    "success": False,
                    "analysis": {
                        "overall_score": 50,
                        "market_validation_summary": f"分析失败（重试{max_retries}次后仍失败）: {type(e).__name__}",
                        "key_pain_points": all_pain_points[:5] if all_pain_points else [],
                        "existing_solutions": all_solutions[:5] if all_solutions else [],
                        "market_opportunities": [],
                        "recommendations": ["请重新运行分析"],
                        "platform_insights": [],
                        "metadata": {}
                    },
                    "error": str(e),
                    "error_type": type(e).__name__
                }

        except Exception as e:
            # 不可重试的错误（如 JSON 解析错误）
            logger.error(f"Generate combined analysis skill failed: {type(e).__name__}: {e}")
            return {
                "success": False,
                "analysis": {
                    "overall_score": 50,
                    "market_validation_summary": f"分析失败: {type(e).__name__}",
                    "key_pain_points": all_pain_points[:5] if all_pain_points else [],
                    "existing_solutions": all_solutions[:5] if all_solutions else [],
                    "market_opportunities": [],
                    "recommendations": ["请重新运行分析"],
                    "platform_insights": [],
                    "metadata": {}
                },
                "error": str(e),
                "error_type": type(e).__name__
            }


# ============================================================================
# 辅助函数
# ============================================================================

def _extract_json_from_response(response: str) -> dict:
    """
    从 LLM 响应中提取 JSON 内容

    去除可能的 markdown 标记（```json 和 ```）

    Args:
        response: LLM 响应字符串

    Returns:
        解析后的字典
    """
    import json

    # 查找 ```json 标记
    start_idx = response.find("```json")
    if start_idx != -1:
        start_idx += 7  # 跳过 "```json"
        response = response[start_idx:]

    # 查找结束标记 ```
    end_idx = response.rfind("```")
    if end_idx != -1:
        response = response[:end_idx]

    # 去除首尾空白
    json_content = response.strip()

    try:
        return json.loads(json_content)
    except json.JSONDecodeError:
        # 如果解析失败，尝试清理后再解析
        # 移除可能的控制字符
        cleaned = ''.join(char for char in json_content if ord(char) >= 32 or char in '\n\r\t')
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"JSON content:\n{json_content[:500]}")
            raise ValueError(f"Invalid JSON response: {e}")


def _calculate_partial_summary(all_analyses: list, total_posts: int) -> dict:
    """
    计算部分分析结果的摘要

    Args:
        all_analyses: 已完成的分析列表
        total_posts: 总帖子数

    Returns:
        部分摘要字典
    """
    relevant_count = 0
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
    avg_engagement = 0

    for a in all_analyses:
        analysis = a.get("analysis", {})
        sentiment = analysis.get("sentiment", "neutral")
        if sentiment in sentiment_counts:
            sentiment_counts[sentiment] += 1
        avg_engagement += analysis.get("engagement_score", 0)

        if analysis.get("relevant"):
            relevant_count += 1

    if all_analyses:
        avg_engagement = avg_engagement / len(all_analyses)

    return {
        "total_posts": total_posts,
        "analyzed_count": len(all_analyses),
        "relevant_count": relevant_count,
        "relevance_rate": relevant_count / len(all_analyses) if all_analyses else 0,
        "sentiment_distribution": sentiment_counts,
        "avg_engagement_score": avg_engagement,
        "partial": True,
        "note": f"部分结果：仅分析了 {len(all_analyses)}/{total_posts} 篇帖子"
    }


def _calculate_partial_summary_with_comments(all_analyses: list, total_posts: int) -> dict:
    """
    计算部分分析结果的摘要（带评论的版本）

    Args:
        all_analyses: 已完成的分析列表
        total_posts: 总帖子数

    Returns:
        部分摘要字典
    """
    relevant_count = 0
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
    avg_engagement = 0

    for a in all_analyses:
        analysis = a.get("analysis", {})
        sentiment = analysis.get("sentiment", "neutral")
        if sentiment in sentiment_counts:
            sentiment_counts[sentiment] += 1
        avg_engagement += analysis.get("engagement_score", 0)

        if analysis.get("relevant"):
            relevant_count += 1

    if all_analyses:
        avg_engagement = avg_engagement / len(all_analyses)

    return {
        "total_posts": total_posts,
        "successful_count": len(all_analyses),
        "relevant_count": relevant_count,
        "relevance_rate": relevant_count / len(all_analyses) if all_analyses else 0,
        "sentiment_distribution": sentiment_counts,
        "avg_engagement_score": avg_engagement,
        "partial": True,
        "note": f"部分结果：仅分析了 {len(all_analyses)}/{total_posts} 篇帖子"
    }


def _fallback_analysis(post: Dict[str, Any], business_idea: str) -> Dict[str, Any]:
    """
    Fallback 分析 - 当 LLM 分析失败时使用简单的关键词匹配

    Args:
        post: 帖子数据
        business_idea: 业务创意

    Returns:
        分析结果字典
    """
    title = post.get('title', '').lower()
    content = post.get('content', '').lower()
    full_text = title + ' ' + content

    business_lower = business_idea.lower()

    # 简单的关键词匹配判断相关性
    # 提取业务创意中的关键词（去除常见词）
    business_keywords = set()
    for word in business_lower.split():
        if len(word) > 1 and word not in ['在', '的', '是', '和', '与', '或', '了', '吗', '呢']:
            business_keywords.add(word)

    # 检查内容中是否包含关键词
    match_count = 0
    for keyword in business_keywords:
        if keyword in full_text:
            match_count += 1

    # 相关性判断：至少匹配一个关键词
    relevant = match_count > 0 or len(business_keywords) == 0

    # 基于互动数据的评分
    score = post.get('score', 0)
    num_comments = post.get('num_comments', 0)

    # 简单的互动评分 (1-10)
    total_engagement = score + num_comments * 2
    if total_engagement > 1000:
        engagement_score = 10
    elif total_engagement > 500:
        engagement_score = 8
    elif total_engagement > 100:
        engagement_score = 6
    elif total_engagement > 50:
        engagement_score = 4
    else:
        engagement_score = 2

    # 简单的情感判断（基于关键词）
    positive_words = ['好', '棒', '推荐', '喜欢', '爱', '优秀', '完美', '不错', '值得']
    negative_words = ['差', '坏', '不好', '失望', '糟糕', '后悔', '问题', '坑']

    positive_count = sum(1 for word in positive_words if word in content)
    negative_count = sum(1 for word in negative_words if word in content)

    if positive_count > negative_count:
        sentiment = 'positive'
    elif negative_count > positive_count:
        sentiment = 'negative'
    else:
        sentiment = 'neutral'

    return {
        "relevant": relevant,
        "pain_points": ["需要人工分析痛点"],
        "solutions_mentioned": ["需要人工分析解决方案"],
        "market_signals": [f"互动数据: {total_engagement}"],
        "sentiment": sentiment,
        "engagement_score": engagement_score,
        "analysis_summary": f"[Fallback分析] 相关性:{'是' if relevant else '否'}, 互动:{total_engagement}, 情感:{sentiment}"
    }
