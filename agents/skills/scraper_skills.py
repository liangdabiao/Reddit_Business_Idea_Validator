"""
数据抓取 Skills

提供 Reddit 数据抓取的业务技能
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from models.business_models import RedditPostModel, RedditCommentModel
from agents.base_agent import BaseAgent


logger = logging.getLogger(__name__)


async def search_posts_skill(
    agent: BaseAgent,
    keyword: str,
    sort: str = "relevance",
    time_filter: str = "all",
    limit: int = 100,
    subreddit: Optional[str] = None
) -> Dict[str, Any]:
    """
    搜索 Reddit 帖子

    Args:
        agent: Agent 实例
        keyword: 搜索关键词
        sort: 排序方式 (relevance/hot/top/new/comments)
        time_filter: 时间范围 (all/hour/day/week/month/year)
        limit: 返回结果数量
        subreddit: 子版块名称（None表示全站搜索）

    Returns:
        搜索结果
    """
    logger.info(f"Searching posts for keyword: {keyword}, limit: {limit}")

    try:
        # 调用 Reddit MCP 服务器
        result = await agent.use_mcp(
            server_name="reddit",
            tool_name="search_posts",
            keyword=keyword,
            sort=sort,
            time_filter=time_filter,
            limit=limit,
            subreddit=subreddit
        )

        if result.get("success"):
            posts = result.get("posts", [])
            logger.info(f"Found {len(posts)} posts for '{keyword}'")

            return {
                "success": True,
                "keyword": keyword,
                "posts": posts,
                "total_count": len(posts),
                "execution_time": result.get("execution_time", 0)
            }
        else:
            error = result.get("error", "Unknown error")
            logger.error(f"Search failed: {error}")
            return {
                "success": False,
                "keyword": keyword,
                "posts": [],
                "error": error
            }

    except Exception as e:
        logger.error(f"Search posts skill failed: {e}")
        return {
            "success": False,
            "keyword": keyword,
            "posts": [],
            "error": str(e)
        }


async def get_comments_skill(
    agent: BaseAgent,
    post_id: str,
    limit: int = 50
) -> Dict[str, Any]:
    """
    获取帖子评论

    Args:
        agent: Agent 实例
        post_id: 帖子 ID
        limit: 最大评论数

    Returns:
        评论结果
    """
    logger.info(f"Getting comments for post: {post_id}")

    try:
        # 调用 Reddit MCP 服务器
        result = await agent.use_mcp(
            server_name="reddit",
            tool_name="get_post_comments",
            post_id=post_id,
            limit=limit
        )

        if result.get("success"):
            comments = result.get("comments", [])
            logger.info(f"Got {len(comments)} comments for post '{post_id}'")

            return {
                "success": True,
                "post_id": post_id,
                "comments": comments,
                "total_count": len(comments),
                "execution_time": result.get("execution_time", 0)
            }
        else:
            error = result.get("error", "Unknown error")
            logger.error(f"Get comments failed: {error}")
            return {
                "success": False,
                "post_id": post_id,
                "comments": [],
                "error": error
            }

    except Exception as e:
        logger.error(f"Get comments skill failed: {e}")
        return {
            "success": False,
            "post_id": post_id,
            "comments": [],
            "error": str(e)
        }


async def batch_get_comments_skill(
    agent: BaseAgent,
    post_ids: List[str],
    comments_per_post: int = 20
) -> Dict[str, Any]:
    """
    批量获取评论

    Args:
        agent: Agent 实例
        post_ids: 帖子 ID 列表
        comments_per_post: 每个帖子的评论数

    Returns:
        批量评论结果
    """
    logger.info(f"Batch getting comments for {len(post_ids)} posts")

    if not post_ids:
        return {
            "success": True,
            "results": {},
            "total_comments": 0,
            "message": "No post IDs provided"
        }

    try:
        # 调用 Reddit MCP 服务器
        result = await agent.use_mcp(
            server_name="reddit",
            tool_name="batch_get_comments",
            post_ids=post_ids,
            comments_per_post=comments_per_post
        )

        if result.get("success"):
            results_dict = result.get("results", {})
            total_comments = sum(len(comments) for comments in results_dict.values())
            logger.info(f"Batch complete: {total_comments} comments total")

            return {
                "success": True,
                "results": results_dict,
                "total_comments": total_comments,
                "execution_time": result.get("execution_time", 0)
            }
        else:
            error = result.get("error", "Unknown error")
            logger.error(f"Batch get comments failed: {error}")
            return {
                "success": False,
                "results": {},
                "total_comments": 0,
                "error": error
            }

    except Exception as e:
        logger.error(f"Batch get comments skill failed: {e}")
        return {
            "success": False,
            "results": {},
            "total_comments": 0,
            "error": str(e)
        }


async def batch_scrape_skill(
    agent: BaseAgent,
    keywords: List[str],
    pages_per_keyword: int = 2,
    comments_per_post: int = 20,
    max_posts: int = 20,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """
    批量抓取：搜索帖子 + 获取评论

    Args:
        agent: Agent 实例
        keywords: 关键词列表
        pages_per_keyword: 每个关键词的搜索页数（Reddit不使用此参数，保留用于兼容）
        comments_per_post: 每个帖子的评论数
        max_posts: 最大帖子数
        progress_callback: 进度回调函数

    Returns:
        批量抓取结果
    """
    logger.info(f"Batch scraping for {len(keywords)} keywords")
    # DEBUG: Log all keywords
    logger.debug(f"[SCRAPER] All keywords to process: {keywords}")

    start_time = datetime.now()
    all_posts = []
    all_comments = {}
    keyword_results = {}

    total_keywords = len(keywords)

    for idx, keyword in enumerate(keywords):
        # DEBUG: Log each keyword being processed
        logger.debug(f"[SCRAPER] Processing keyword {idx+1}/{total_keywords}: {keyword}")
        try:
            # 更新进度
            if progress_callback:
                from models.agent_models import ProgressUpdate
                progress = idx / total_keywords  # 0-1 range
                update = ProgressUpdate(
                    step="searching",
                    progress=progress,
                    message=f"正在搜索关键词: {keyword}"
                )
                progress_callback(update)

            # 搜索帖子
            search_result = await search_posts_skill(
                agent,
                keyword=keyword,
                limit=max_posts
            )

            if not search_result.get("success"):
                logger.warning(f"Search failed for keyword '{keyword}': {search_result.get('error')}")
                keyword_results[keyword] = {
                    "success": False,
                    "posts_count": 0,
                    "comments_count": 0,
                    "error": search_result.get("error")
                }
                continue

            posts = search_result.get("posts", [])
            keyword_posts = posts[:max_posts]
            all_posts.extend(keyword_posts)

            logger.info(f"Found {len(keyword_posts)} posts for '{keyword}'")

            # 获取评论
            comments_result = {"total_comments": 0}  # 初始化默认值
            if keyword_posts and comments_per_post > 0:
                if progress_callback:
                    from models.agent_models import ProgressUpdate
                    progress = (idx + 0.5) / total_keywords  # 0-1 range
                    update = ProgressUpdate(
                        step="fetching_comments",
                        progress=progress,
                        message=f"正在获取 {keyword} 的评论..."
                    )
                    progress_callback(update)

                post_ids = [
                    p.get("post_id") 
                    for p in keyword_posts 
                    if p.get("post_id") and p.get("num_comments", 0) > 0
                ]

                skipped_count = len(keyword_posts) - len(post_ids)
                if skipped_count > 0:
                    logger.info(f"Skipping {skipped_count} posts with num_comments=0 for keyword '{keyword}'")

                if post_ids:
                    comments_result = await batch_get_comments_skill(
                        agent,
                        post_ids=post_ids,
                        comments_per_post=comments_per_post
                    )

                    if comments_result.get("success"):
                        all_comments.update(comments_result.get("results", {}))
                        logger.info(f"Got {comments_result.get('total_comments', 0)} comments for '{keyword}'")

            # 保存关键词结果
            total_comments_for_keyword = sum(
                len(all_comments.get(p.get("post_id"), []))
                for p in keyword_posts
            )

            keyword_results[keyword] = {
                "success": True,
                "posts_count": len(keyword_posts),
                "comments_count": comments_result.get("total_comments", 0) if comments_per_post > 0 else 0
            }

        except Exception as e:
            logger.error(f"Failed to scrape keyword '{keyword}': {e}")
            keyword_results[keyword] = {
                "success": False,
                "posts_count": 0,
                "comments_count": 0,
                "error": str(e)
            }

    execution_time = (datetime.now() - start_time).total_seconds()

    # 最终进度更新
    if progress_callback:
        from models.agent_models import ProgressUpdate
        update = ProgressUpdate(
            step="batch_scrape",
            progress=1.0,  # 100%
            message=f"批量抓取完成: {len(all_posts)} 条帖子, {len(all_comments)} 批次评论"
        )
        progress_callback(update)

    logger.info(f"Batch scrape complete: {len(all_posts)} posts, {len(all_comments)} comment batches in {execution_time:.2f}s")

    return {
        "success": True,
        "posts": all_posts,
        "comments": all_comments,
        "total_posts": len(all_posts),
        "total_comments": sum(len(c) for c in all_comments.values()),
        "keyword_results": keyword_results,
        "execution_time": execution_time
    }


async def batch_scrape_with_comments_skill(
    agent: BaseAgent,
    keywords: List[str],
    pages_per_keyword: int = 2,
    comments_per_post: int = 20,
    max_posts: int = 20,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """
    批量抓取：搜索帖子 + 获取评论 + 合并在一起

    与 batch_scrape_skill 的区别：
    - 返回 posts_with_comments 结构（每个 post 包含自己的 comments_data）
    - 单一数据结构，更方便后续分析

    Args:
        agent: Agent 实例
        keywords: 关键词列表
        pages_per_keyword: 每个关键词的搜索页数（Reddit不使用此参数，保留用于兼容）
        comments_per_post: 每个帖子的评论数
        max_posts: 最大帖子数
        progress_callback: 进度回调函数

    Returns:
        批量抓取结果，包含 posts_with_comments
    """
    logger.info(f"Batch scraping with comments for {len(keywords)} keywords")
    # DEBUG: Log keywords
    logger.debug(f"[SCRAPER] Keywords received: {keywords}")

    # 先使用原有的批量抓取逻辑
    scrape_result = await batch_scrape_skill(
        agent,
        keywords=keywords,
        pages_per_keyword=pages_per_keyword,
        comments_per_post=comments_per_post,
        max_posts=max_posts,
        progress_callback=progress_callback
    )

    if not scrape_result.get("success"):
        return {
            "success": False,
            "posts_with_comments": [],
            "metadata": {},
            "error": scrape_result.get("error", "Scraping failed")
        }

    # 获取原始数据
    all_posts = scrape_result.get("posts", [])
    all_comments = scrape_result.get("comments", {})

    # 将 Reddit 数据转换为统一格式
    unified_posts = [convert_reddit_post_to_unified(post) for post in all_posts]
    
    # 将 Reddit 评论转换为统一格式
    unified_comments = {}
    for post_id, comments in all_comments.items():
        unified_comments[post_id] = [convert_reddit_comment_to_unified(comment) for comment in comments]

    # 合并 comments 到 posts
    posts_with_comments = _merge_comments_to_posts(unified_posts, unified_comments)

    # 计算元数据
    metadata = {
        "total_posts": len(posts_with_comments),
        "posts_with_comments": sum(1 for p in posts_with_comments if p.get("comments_fetched")),
        "posts_without_comments": sum(1 for p in posts_with_comments if not p.get("comments_fetched")),
        "total_comments": sum(len(p.get("comments_data", [])) for p in posts_with_comments),
        "keyword_results": scrape_result.get("keyword_results", {}),
        "execution_time": scrape_result.get("execution_time", 0)
    }

    logger.info(
        f"Batch scrape with comments complete: "
        f"{len(posts_with_comments)} posts, "
        f"{metadata['posts_with_comments']} with comments, "
        f"{metadata['total_comments']} total comments"
    )

    return {
        "success": True,
        "posts_with_comments": posts_with_comments,
        "metadata": metadata
    }


# ============================================================================
# 辅助函数
# ============================================================================

def _merge_comments_to_posts(
    posts: List[Dict[str, Any]],
    comments_dict: Dict[str, List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """
    Merge comments into their parent posts

    Args:
        posts: List of posts
        comments_dict: Dictionary {post_id: [comments]}

    Returns:
        List of posts with embedded comments
    """
    posts_with_comments = []

    for post in posts:
        post_id = post.get("post_id")
        post_copy = post.copy()

        # Add comments to post
        comments = comments_dict.get(post_id, [])
        post_copy["comments_data"] = comments
        post_copy["comments_fetched"] = len(comments) > 0
        post_copy["comments_fetch_error"] = None if comments else "No comments fetched"

        posts_with_comments.append(post_copy)

    return posts_with_comments


def convert_reddit_post_to_unified(reddit_post: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 Reddit 帖子数据转换为统一格式（PostWithComments）

    Args:
        reddit_post: Reddit 帖子数据（来自 RedditPostModel）

    Returns:
        统一格式的帖子数据
    """
    unified_post = {
        "post_id": reddit_post.get("post_id"),
        "title": reddit_post.get("title", ""),
        "content": reddit_post.get("content", ""),
        "url": reddit_post.get("url"),
        "score": reddit_post.get("score", 0),
        "upvote_ratio": reddit_post.get("upvote_ratio", 0),
        "subreddit": reddit_post.get("subreddit", ""),
        "num_comments": reddit_post.get("num_comments", 0),
        "created_utc": reddit_post.get("created_utc", 0),
        "author": reddit_post.get("author", ""),
        "keyword_matched": reddit_post.get("keyword_matched"),
        "comments_data": [],
        "comments_fetched": False,
        "comments_fetch_error": None
    }
    
    return unified_post


def convert_reddit_comment_to_unified(reddit_comment: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 Reddit 评论数据转换为统一格式

    Args:
        reddit_comment: Reddit 评论数据（来自 RedditCommentModel）

    Returns:
        统一格式的评论数据
    """
    unified_comment = {
        "comment_id": reddit_comment.get("comment_id"),
        "post_id": reddit_comment.get("post_id"),
        "body": reddit_comment.get("body", ""),
        "score": reddit_comment.get("score", 0),
        "created_utc": reddit_comment.get("created_utc", 0),
        "author": reddit_comment.get("author", ""),
        "parent_id": reddit_comment.get("parent_id"),
        "depth": reddit_comment.get("depth", 0)
    }
    
    return unified_comment
