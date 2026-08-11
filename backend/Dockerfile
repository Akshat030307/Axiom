FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nodejs \
    npm \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
# PRD §14: installed at build time, never at runtime.
RUN playwright install --with-deps chromium

# PRD §11.3: diagram_generator.py renders Mermaid diagram *source* (the
# LLM's own text) deterministically to SVG — never through an
# image-generation model, which is why illustrations get a "not derived
# from evidence" disclaimer and diagrams don't. mermaid-cli's `mmdc` needs
# its own headless Chromium (via Puppeteer) to do this; --no-sandbox is
# required to run it as root in a container.
RUN npm install -g @mermaid-js/mermaid-cli
COPY puppeteer-config.json ./

COPY alembic.ini ./
COPY app ./app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
