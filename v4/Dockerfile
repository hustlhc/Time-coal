FROM python:3.9-slim

LABEL maintainer="coal-data-team"
LABEL description="Coal Data Incremental Update Service"

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 复制父目录的核心模块（如果需要）
# COPY ../processed_data_cci_aligned/utils.py ./utils/
# COPY ../processed_data_cci_aligned/coal_data_processor.py ./
# ...（根据实际需要调整）

# 创建数据目录
RUN mkdir -p /data/raw /data/processed /data/logs

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV APP_ROOT=/app

# 默认命令
ENTRYPOINT ["python", "run_incremental.py"]
CMD ["--help"]

