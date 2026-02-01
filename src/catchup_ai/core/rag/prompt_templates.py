"""Prompt templates for RAG and summarization.

These templates are designed to work with Claude and OpenAI models.
"""

from dataclasses import dataclass


@dataclass
class ArticleContext:
    """Context article for RAG."""

    article_id: int
    title: str
    url: str
    content: str
    relevance_score: float


class PromptTemplates:
    """Collection of prompt templates for various AI tasks."""

    @staticmethod
    def rag_system_prompt() -> str:
        """System prompt for RAG-based Q&A."""
        return """You are a helpful assistant that answers questions based on the provided articles.

Rules:
1. Only use information from the provided articles to answer questions
2. If the articles don't contain relevant information, say so clearly
3. Always cite which article(s) you're using when providing information
4. Be concise but thorough
5. Use bullet points for lists when appropriate
6. If asked about something not in the articles, acknowledge the limitation

Response format:
- Provide a clear, direct answer
- Include relevant details from the articles
- Mention the source article titles when citing information"""

    @staticmethod
    def rag_user_prompt(question: str, articles: list[ArticleContext]) -> str:
        """User prompt for RAG with context articles.

        Args:
            question: User's question
            articles: List of relevant articles as context

        Returns:
            Formatted prompt with context
        """
        context_parts = []
        for i, article in enumerate(articles, 1):
            context_parts.append(
                f"[Article {i}] {article.title}\n"
                f"URL: {article.url}\n"
                f"Relevance: {article.relevance_score:.2f}\n"
                f"Content:\n{article.content}\n"
            )

        context = "\n---\n".join(context_parts)

        return f"""Based on the following articles, please answer the question.

## Articles

{context}

## Question

{question}

## Answer"""

    @staticmethod
    def summary_system_prompt() -> str:
        """System prompt for article summarization."""
        return """You are a technical news summarizer.
Your job is to create concise, informative summaries of technical articles.

Guidelines:
1. Focus on the most important and impactful information
2. Group related topics together
3. Highlight key trends and developments
4. Keep the summary scannable with clear structure
5. Include specific details when they're significant
6. Use technical terms appropriately but explain them if necessary

Output format:
1. Start with a brief overview (2-3 sentences)
2. List key highlights as bullet points
3. Group articles by topic/category if applicable"""

    @staticmethod
    def weekly_summary_prompt(articles: list[dict], period: str = "week") -> str:
        """Prompt for generating weekly/monthly summary.

        Args:
            articles: List of articles with title, url, content, category
            period: "week" or "month"

        Returns:
            Formatted prompt for summarization
        """
        article_list = []
        for i, article in enumerate(articles, 1):
            article_list.append(
                f"{i}. [{article.get('category', 'General')}] {article['title']}\n"
                f"   URL: {article['url']}\n"
                f"   Content: {article['content'][:500]}..."
            )

        articles_text = "\n\n".join(article_list)

        return f"""Please summarize the following {len(articles)} articles from the past {period}.

## Articles

{articles_text}

## Task

Create a comprehensive summary that:
1. Provides an overview of the {period}'s key developments
2. Highlights the most important news items
3. Groups related topics together
4. Identifies emerging trends

## Summary"""

    @staticmethod
    def search_enhancement_prompt(query: str) -> str:
        """Prompt to enhance search query for better retrieval.

        Args:
            query: Original user query

        Returns:
            Prompt to generate enhanced query
        """
        return f"""Given the following search query, generate an enhanced version
that would better match relevant technical articles.

Original query: {query}

Generate a search-optimized version that:
1. Expands abbreviations if any
2. Includes related technical terms
3. Keeps the core intent

Enhanced query:"""

    @staticmethod
    def classification_prompt(title: str, content: str) -> str:
        """Prompt for article classification.

        Args:
            title: Article title
            content: Article content

        Returns:
            Classification prompt
        """
        categories = [
            "AI/ML",
            "Web Development",
            "Infrastructure/DevOps",
            "Security",
            "Programming Languages",
            "Database",
            "Mobile",
            "Cloud",
            "Other",
        ]

        return f"""Classify the following article into one of these categories:
{', '.join(categories)}

Title: {title}

Content:
{content[:1000]}

Respond with only the category name and confidence score (0.0-1.0).
Format: CATEGORY | CONFIDENCE

Classification:"""
