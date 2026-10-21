FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE LICENSE-DATA.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace
USER agent
EXPOSE 8712
ENTRYPOINT ["market-entry-agent", "--workspace", "/workspace"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8712"]
