"""
千川电销话术生成AI后端接口
基于FastAPI和OpenAI兼容接口
集成LangGraph Agent和RAG检索
"""

import os
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import AsyncOpenAI
import Levenshtein
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from rag_module import AdPilotRAG
import uvicorn

os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""

# 加载环境变量
load_dotenv()

# 初始化FastAPI应用
app = FastAPI(
    title="千川电销话术生成API",
    description="基于大模型的电销话术智能生成接口",
    version="1.0.0"
)

# 添加CORS跨域配置
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

print("================== 成功加载终极防冲突代码！==================")

# 核心优化：延迟初始化客户端，完美避开 Windows 异步冲突 Bug
_client = None
def get_ai_client():
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url=os.getenv("BASE_URL")
        )
    return _client

# 定义System Prompt
SYSTEM_PROMPT = """你是一个专业的千川电销话术副驾驶。
核心任务：调用 search_golden_scripts 检索金牌案例，结合用户的参数，生成三段式草稿。

【绝对输出指令】
1. 必须直接输出话术正文！
2. 严禁包含任何开场白、解释性文字、分析过程或总结（例如：绝对不能输出“好的”、“为您生成”、“基于XX要求”等废话）。
3. 严禁出现“1. 破冰定位 2. 方案建议 3. 下一步动作”这样的标题序号，要把它们融合成一段自然连贯的对话口语。
4. 绝不能夸大效果，禁止使用'赋能、底层逻辑'等互联网黑话。
5. 总字数严格控制在 150 字以内。"""

# 定义请求模型
class DraftRequest(BaseModel):
    industry: str = Field(..., description="行业标签")
    avg_budget: str = Field(..., description="平均预算")
    goal: str = Field(..., description="沟通目标")
    pain_point: str = Field(..., description="核心抗单点")

class SubmitFeedbackRequest(BaseModel):
    """反馈提交请求模型"""
    session_id: str = Field(..., description="会话唯一标识")
    draft_text: str = Field(..., description="刚才 AI 生成的初稿内容")
    final_text: str = Field(..., description="销售手动修改后最终发出去的内容")

# RAG 工具
@tool
def search_golden_scripts(industry: str, budget: str, goal: str, pain_point: str) -> str:
    """
    搜索历史金牌话术

    Args:
        industry: 行业
        budget: 预算
        goal: 沟通目标
        pain_point: 核心抗单点

    Returns:
        拼接的Top-3话术
    """
    try:
        rag = AdPilotRAG()
        metadata_filter = {
            "industry": industry,
            "goal": goal
        }
        query = f"{industry} {budget} {goal} {pain_point}"
        results = rag.retrieve_best_scripts(query, metadata_filter)

        if results:
            scripts = []
            for i, result in enumerate(results, 1):
                scripts.append(f"案例{i}: {result['text']}")
            return "\n".join(scripts)
        else:
            return "未找到相关历史金牌话术"
    except Exception as e:
        return f"检索失败: {str(e)}"

async def generate_stream(request: DraftRequest) -> AsyncGenerator[str, None]:
    user_prompt = f"""
    行业: {request.industry}
    平均预算: {request.avg_budget}
    沟通目标: {request.goal}
    核心抗单点: {request.pain_point}

    请生成一段不超过150字的三段式话术：
    1. 破冰定位：说明你理解对方现状
    2. 方案建议：给出1个清晰动作建议
    3. 下一步动作：明确时间/动作
    """

    system_prompt = """你是一个专业的千川电销话术副驾驶。
核心任务：调用 search_golden_scripts 检索金牌案例，结合用户的参数，生成三段式草稿。

【绝对输出指令】
1. 必须直接输出话术正文！
2. 严禁包含任何开场白、解释性文字、分析过程或总结（例如：绝对不能输出"好的"、"为您生成"、"基于XX要求"等废话）。
3. 严禁出现"1. 破冰定位 2. 方案建议 3. 下一步动作"这样的标题序号，要把它们融合成一段自然连贯的对话口语。
4. 绝不能夸大效果，禁止使用'赋能、底层逻辑'等互联网黑话。
5. 总字数严格控制在 150 字以内。"""

    try:
        # 每次请求时动态唤醒大模型
        llm = ChatOpenAI(
            model="qwen-plus",
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url=os.getenv("BASE_URL"),
            temperature=0
        )
        agent = create_react_agent(llm, tools=[search_golden_scripts])

        inputs = {"messages": [
            ("system", system_prompt),
            ("user", user_prompt)
        ]}

        # 1. 使用最稳妥的 ainvoke 拿到最终结果
        response = await agent.ainvoke(inputs)
        final_message = response["messages"][-1].content
        
        # 2. 为了保留前端的“打字机”流式效果，手动逐字 yield
        for char in final_message:
            yield char
            await asyncio.sleep(0.02)  # 控制打字速度
            
    except Exception as e:
        yield f"[错误] 生成失败: {str(e)}"

@app.post("/api/v1/generate_draft")
async def generate_draft(request: DraftRequest):
    return StreamingResponse(
        generate_stream(request),
        media_type="text/plain"
    )

@app.get("/")
async def root():
    """
    根路径，返回API信息
    """
    return {
        "message": "千川电销话术生成API",
        "version": "1.0.0",
        "endpoints": [
            "/api/v1/generate_draft (POST)",
            "/api/v1/submit_feedback (POST)"
        ]
    }

@app.get("/health")
async def health_check():
    """
    健康检查接口
    """
    return {"status": "healthy"}

@app.post("/api/v1/submit_feedback")
async def submit_feedback(request: SubmitFeedbackRequest):
    """
    提交反馈并计算修改率

    - **session_id**: 会话唯一标识
    - **draft_text**: 刚才 AI 生成的初稿内容
    - **final_text**: 销售手动修改后最终发出去的内容

    返回修改率和自动打标结果
    """
    # 计算编辑距离
    distance = Levenshtein.distance(request.draft_text, request.final_text)

    # 计算修改率
    max_length = max(len(request.draft_text), len(request.final_text))
    edit_ratio = round(distance / max_length if max_length > 0 else 0, 2)

    # 自动打标
    if edit_ratio <= 0.2:
        tag = "Golden Case"
    elif edit_ratio >= 0.5:
        tag = "Bad Case"
    else:
        tag = "Gray Case"

    # 准备日志数据
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "session_id": request.session_id,
        "edit_ratio": edit_ratio,
        "tag": tag,
        "draft_text": request.draft_text,
        "final_text": request.final_text
    }

    # 写入日志文件
    log_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flywheel_logs.json")

    # 读取现有日志
    try:
        if os.path.exists(log_file_path):
            with open(log_file_path, "r", encoding="utf-8") as f:
                logs = json.load(f)
        else:
            logs = []
    except Exception:
        logs = []

    # 追加新日志
    logs.append(log_data)

    # 写入文件
    try:
        with open(log_file_path, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"写入日志失败: {e}")

    return {
        "session_id": request.session_id,
        "edit_ratio": edit_ratio,
        "tag": tag,
        "message": "反馈提交成功"
    }

@app.get("/api/v1/logs")
async def get_logs():
    """
    获取所有日志数据
    """
    # 读取日志文件
    log_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flywheel_logs.json")

    try:
        if os.path.exists(log_file_path):
            with open(log_file_path, "r", encoding="utf-8") as f:
                logs = json.load(f)
        else:
            logs = []
    except Exception:
        logs = []

    return logs

# 测试 LangGraph Agent
async def test_agent():
    print("\n=== 测试 LangGraph Agent ===")
    user_input = "我刚接通一个新客户，他是做美妆行业的，低预算。客户一上来就嫌贵，请帮我生成一个首次破冰的话术。"
    print(f"用户输入: {user_input}")

    # 把系统提示词硬编码进消息列表，这是最底层协议，绝对不会报错！
    system_prompt = "你是一个专业的千川电销话术副驾驶。当销售向你请求话术时，你必须先调用 search_golden_scripts 工具检索历史金牌话术（Golden Cases）。参考检索到的案例，为销售生成一段不超过 150 字的三段式草稿。绝不能夸大效果，禁止使用'赋能、底层逻辑'等互联网黑话。"

    try:
        # 动态初始化大模型和Agent
        llm = ChatOpenAI(
            model="qwen-plus",
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url=os.getenv("BASE_URL"),
            temperature=0
        )
        agent = create_react_agent(llm, tools=[search_golden_scripts])
        
        # 用 ('system', ...) 强行注入大脑
        inputs = {"messages": [
            ("system", system_prompt),
            ("user", user_input)
        ]}
        response = await agent.ainvoke(inputs)

        final_message = response["messages"][-1].content
        print("\nAgent 最终输出:")
        print(final_message)
    except Exception as e:
        print(f"\n[错误] Agent 运行失败: {str(e)}")

    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    # 启动服务，监听 8081 端口，保持永远在线
    uvicorn.run(app, host="127.0.0.1", port=8081)
