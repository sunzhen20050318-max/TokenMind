"""URL adapters for wiki KB ingest. Each adapter takes a URL and returns
a markdown document plus metadata, ready to be saved as a wiki source."""
from tokenmind.knowledge.adapters.wechat import (
    WechatArticle,
    WechatFetchError,
    fetch_wechat_article,
    is_wechat_url,
)

__all__ = [
    "WechatArticle",
    "WechatFetchError",
    "fetch_wechat_article",
    "is_wechat_url",
]
