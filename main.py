import logging
import os
from typing import Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Response

from youtube_summary.youtube import run_youtube_summary


LOG_PREFIX = "[gemini_summary_log]"
logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/")
async def index_handle():
    return {"message": "Hello Faas Function"}

# 必须加入此接口，Faas 平台用它来做部署成功检查 (health check)
@app.get("/v1/ping")
async def ping_handler():
    response = Response(content="ok", status_code=200)
    return response

def _run_summary_task(
    *,
    start: Optional[str],
    end: Optional[str],
    language: str,
    max_per_channel: Optional[int],
    output_path: str,
    title: Optional[str],
    skip_gemini: bool,
    skip_notion: bool,
) -> None:
    try:
        run_youtube_summary(
            start=start,
            end=end,
            language=language,
            max_per_channel=max_per_channel,
            output_path=output_path,
            title=title,
            skip_gemini=skip_gemini,
            skip_notion=skip_notion,
        )
    except Exception as error:  # pylint: disable=broad-except
        logger.exception("%s Background summary failed: %s", LOG_PREFIX, error)


@app.get("/youtube_summary_handle")
async def youtube_summary_handle(
    background_tasks: BackgroundTasks,
    start: Optional[str] = None,
    end: Optional[str] = None,
    language: str = "zh-CN",
    max_per_channel: Optional[int] = None,
    output_path: str = "subscription_summaries.md",
    title: Optional[str] = None,
    skip_gemini: bool = False,
    skip_notion: bool = False,
):
    background_tasks.add_task(
        _run_summary_task,
        start=start,
        end=end,
        language=language,
        max_per_channel=max_per_channel,
        output_path=output_path,
        title=title,
        skip_gemini=skip_gemini,
        skip_notion=skip_notion,
    )
    return {"status": "accepted"}

if __name__ == "__main__":
    # 目前这里是系统自定义的端口，会在创建实例时随机一个可用端口，若需自定义，参考后面高级操作部分
    port = os.getenv("_BYTEFAAS_RUNTIME_PORT")
    port = int(port) if port else 8000
    # 注意到这里的 host 必须是 None, 同时监听 ipv4 和 ipv6，否则在灰度与发布时会随机过与不过
    config = uvicorn.Config("main:app", host=None, port=port,
                            log_level="info", reload=True)
    server = uvicorn.Server(config)
    server.run()
