FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# 대장이 한 일을 보려고 작업 폴더의 git 기록을 읽는다.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# 머리(Claude Code)는 홈 화면 서버가 Windows 쪽에서 돌려 주므로 이 안에는 표준 라이브러리만 있으면 된다.
COPY app/ .
CMD ["python", "main.py"]
