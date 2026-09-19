#!/bin/bash
# LLM-INDEX 启动脚本
# 用法:
#   ./start.sh          # 启动前后端
#   ./start.sh backend  # 只启动后端
#   ./start.sh frontend # 只启动前端
#   ./start.sh stop     # 停止所有服务

cd /Users/LiYuan/apps/llm-index

BACKEND_PORT=${BACKEND_PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-8080}
LOG_DIR="/tmp/llm-index-logs"

mkdir -p "$LOG_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

stop_services() {
    echo -e "${YELLOW}停止服务...${NC}"
    # 停止后端
    pkill -f "uvicorn src.main:app" 2>/dev/null && echo -e "${GREEN}✓ 后端已停止${NC}" || echo "后端未运行"
    # 停止前端
    pkill -f "python3 -m http.server $FRONTEND_PORT" 2>/dev/null && echo -e "${GREEN}✓ 前端已停止${NC}" || echo "前端未运行"
}

start_backend() {
    echo -e "${YELLOW}启动后端 (端口 $BACKEND_PORT)...${NC}"
    
    # 检查端口是否被占用
    if lsof -i :$BACKEND_PORT >/dev/null 2>&1; then
        echo -e "${YELLOW}端口 $BACKEND_PORT 已被占用，先停止旧进程${NC}"
        pkill -f "uvicorn src.main:app" 2>/dev/null
        sleep 1
    fi
    
    nohup python3 -m uvicorn src.main:app \
        --host 0.0.0.0 \
        --port $BACKEND_PORT \
        --reload \
        > "$LOG_DIR/backend.log" 2>&1 &
    
    sleep 2
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:$BACKEND_PORT/ >/dev/null 2>&1; then
        echo -e "${GREEN}✓ 后端启动成功: http://localhost:$BACKEND_PORT${NC}"
        echo "  日志: $LOG_DIR/backend.log"
    else
        echo -e "${YELLOW}后端启动中... (可能需要几秒)${NC}"
        echo "  日志: $LOG_DIR/backend.log"
    fi
}

start_frontend() {
    echo -e "${YELLOW}启动前端 (端口 $FRONTEND_PORT)...${NC}"
    
    # 检查端口是否被占用
    if lsof -i :$FRONTEND_PORT >/dev/null 2>&1; then
        echo -e "${YELLOW}端口 $FRONTEND_PORT 已被占用，先停止旧进程${NC}"
        pkill -f "python3 -m http.server $FRONTEND_PORT" 2>/dev/null
        sleep 1
    fi
    
    cd /Users/LiYuan/apps/llm-index/frontend
    nohup python3 -m http.server $FRONTEND_PORT \
        > "$LOG_DIR/frontend.log" 2>&1 &
    
    sleep 1
    echo -e "${GREEN}✓ 前端启动成功: http://localhost:$FRONTEND_PORT${NC}"
    echo "  日志: $LOG_DIR/frontend.log"
}

show_status() {
    echo -e "${YELLOW}服务状态:${NC}"
    echo -n "  后端 ($BACKEND_PORT): "
    if lsof -i :$BACKEND_PORT >/dev/null 2>&1; then
        echo -e "${GREEN}运行中${NC}"
    else
        echo -e "${RED}未运行${NC}"
    fi
    echo -n "  前端 ($FRONTEND_PORT): "
    if lsof -i :$FRONTEND_PORT >/dev/null 2>&1; then
        echo -e "${GREEN}运行中${NC}"
    else
        echo -e "${RED}未运行${NC}"
    fi
}

# 主逻辑
case "${1:-all}" in
    backend)
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    stop)
        stop_services
        ;;
    status)
        show_status
        ;;
    all)
        start_backend
        start_frontend
        show_status
        ;;
    *)
        echo "用法: $0 {backend|frontend|stop|status|all}"
        exit 1
        ;;
esac
