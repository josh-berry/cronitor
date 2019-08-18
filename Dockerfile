# Directories where Cronitor expects to find things (unless you modify this
# file and/or server.yaml):
#
# - /app - static application files for Cronitor itself
# - /cfg - directory containing rules.yaml file
# - /log - log files collected from jobs

FROM python:2-alpine
# Consider python:2-slim if there are libc problems

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY assets /app/assets
COPY templates /app/templates
COPY cronitor /app/cronitor
COPY cronitor-server /app/cronitor-server
COPY server.yaml /app/server.yaml

COPY cfg /cfg
VOLUME /cfg

VOLUME /log

EXPOSE 8434

ENV PYTHONPATH /app
CMD [ "python", "/app/cronitor-server", "-c", "/app/server.yaml" ]