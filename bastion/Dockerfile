FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 \
        python3-pip \
        python3.11-venv \
        openssh-server \
        openssh-client \
        sshpass \
        sudo \
        ca-certificates \
        curl \
        wget \
        git \
        jq \
        iproute2 \
        iputils-ping \
        net-tools \
        dnsutils \
        vim-tiny \
        less \
        procps \
        rsync \
        sqlite3 \
        cron \
        tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

# python3.11 을 기본으로.
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# 파이썬 의존성 사전 설치 (캐시).
COPY bastion/requirements-bastion.txt /tmp/requirements-bastion.txt
RUN pip install --no-cache-dir -r /tmp/requirements-bastion.txt

# bastion 핵심 코드를 컨테이너 안에 복사 — 호스트 마운트 없음.
COPY src/apps/bastion        /opt/app/apps/bastion
COPY src/packages/bastion    /opt/app/packages/bastion
COPY src/contents/playbooks  /opt/app/contents/playbooks
COPY src/data                /opt/app/data
RUN touch /opt/app/__init__.py /opt/app/apps/__init__.py /opt/app/packages/__init__.py

COPY common/sshd_setup.sh /usr/local/bin/sshd_setup.sh
COPY bastion/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/sshd_setup.sh /usr/local/bin/entrypoint.sh

WORKDIR /opt/app
EXPOSE 22 8003
CMD ["/usr/local/bin/entrypoint.sh"]
