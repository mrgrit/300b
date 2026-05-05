FROM ubuntu:22.04

# 300B Portal — AWS Console 풍 운영 대시보드.
# FastAPI + Jinja2 + HTMX (no JS bundler — 가벼움).

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        ca-certificates \
        curl \
        openssh-server \
        sudo \
        iproute2 \
        iputils-ping \
        net-tools \
        dnsutils \
        less \
        vim-tiny \
        procps \
        tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

COPY portal/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY portal/main.py        /opt/portal/main.py
COPY portal/templates/     /opt/portal/templates/
COPY portal/static/        /opt/portal/static/

COPY common/sshd_setup.sh /usr/local/bin/sshd_setup.sh
COPY portal/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY common/systemctl3.py /usr/local/bin/systemctl3.py
COPY common/journalctl3.py /usr/local/bin/journalctl3.py
RUN chmod +x /usr/local/bin/sshd_setup.sh /usr/local/bin/entrypoint.sh \
                /usr/local/bin/systemctl3.py /usr/local/bin/journalctl3.py \
    && ln -sf /usr/local/bin/systemctl3.py /usr/local/bin/systemctl \
    && ln -sf /usr/local/bin/journalctl3.py /usr/local/bin/journalctl

WORKDIR /opt/portal
EXPOSE 22 8005
CMD ["/usr/local/bin/entrypoint.sh"]
