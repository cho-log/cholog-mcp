# Lambda에 올릴 서버 이미지. 로컬 docker run, Cloud Run에서도 그대로 돈다.
# 데이터(data/cholog.db)를 이미지에 넣는다. 서버는 읽기만 하므로 새 데이터 반영 = 새 이미지 배포.

# 1단계: uv로 .venv를 만든다. uv와 다운로드 캐시는 이 단계에만 남는다.
FROM python:3.13.16-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /bin/uv

# 바이트코드를 미리 만든다. Lambda는 실행 중 파일 시스템에 쓸 수 없고, 깨어나는 시간도 줄어든다.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# 의존성을 먼저 깔아 둔다. 코드만 바뀌면 이 층은 캐시를 쓴다.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

# 2단계: 실행에 필요한 것만 담는다.
FROM python:3.13.16-slim

# Lambda 이벤트를 HTTP 요청으로 바꿔 localhost:8080에 넘긴다. Lambda 밖에서는 아무 일도 하지 않는다.
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY data/cholog.db ./data/cholog.db

ENV PATH="/app/.venv/bin:$PATH" \
    CHOLOG_DB_PATH=/app/data/cholog.db \
    CHOLOG_HTTP_HOST=0.0.0.0 \
    CHOLOG_HTTP_PORT=8080 \
    AWS_LWA_PORT=8080 \
    AWS_LWA_READINESS_CHECK_PROTOCOL=tcp

EXPOSE 8080
CMD ["cholog-mcp-http"]
