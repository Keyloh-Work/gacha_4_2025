# ベースイメージ：公式 Python slim
FROM python:3.11-slim

# bytecode の書き込み抑制、標準出力をバッファリングなし
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ビルドに必要なパッケージをインストールし、PostgreSQL 用ヘッダも追加
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# 依存関係を先にコピーしてインストール（キャッシュ効かせる）
COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# アプリケーションソースをコピー
COPY . .

# 実行コマンド
CMD ["python", "main.py"]
