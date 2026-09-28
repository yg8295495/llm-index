"""FastAPI 应用入口"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router

app = FastAPI(
    title="LLM-INDEX API",
    description="多维度动态加权评测系统 API",
    version="0.1.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router)


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    print("🚀 LLM-INDEX API 启动中...")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    print("👋 LLM-INDEX API 已关闭")
