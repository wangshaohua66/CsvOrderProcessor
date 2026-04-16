# 使用官方 Python 3.11  slim 镜像作为基础镜像
FROM python:3.11-slim

# 设置工作目录为 /app
WORKDIR /app

# 安装系统依赖（如有需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件到容器中
COPY main.py .
COPY sample/ ./sample/

# 创建输入输出目录
RUN mkdir -p /app/input /app/output

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 设置容器启动时执行的命令
ENTRYPOINT ["python3", "main.py"]

# 默认参数（可以通过 docker run 覆盖）
CMD ["--help"]
