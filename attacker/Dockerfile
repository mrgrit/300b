FROM ubuntu:22.04

# CCC Attacker — 13 도구 + Metasploit + Impacket + John.
# Ubuntu 22.04 server (학생 요구).

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
        nmap \
        hydra \
        sqlmap \
        nikto \
        dirb \
        gobuster \
        whatweb \
        hashcat \
        john \
        smbclient \
        python3-impacket \
        netcat-openbsd \
        curl \
        wget \
        net-tools \
        traceroute \
        iputils-ping \
        iproute2 \
        dnsutils \
        ldap-utils \
        snmp \
        snmp-mibs-downloader \
        openssh-server \
        openssh-client \
        sshpass \
        ca-certificates \
        gnupg \
        sudo \
        git \
        python3 \
        python3-pip \
        python3-venv \
        ruby \
        ruby-dev \
        build-essential \
        vim-tiny \
        less \
        jq \
        tmux \
        procps \
        tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

# Metasploit Framework — rapid7 공식 omnibus 설치 (Ubuntu 22.04 지원).
# 학생 첫 빌드 시 약 5~8 분 소요. 빌드 시간 단축을 원하면 BUILD_MSF=0 으로 끄면 됨.
ARG BUILD_MSF=1
RUN if [ "$BUILD_MSF" = "1" ]; then \
        curl -sSfL https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb -o /usr/local/bin/msfinstall \
        && chmod +x /usr/local/bin/msfinstall \
        && /usr/local/bin/msfinstall || echo "[attacker] msf install 실패 (네트워크 확인) — 계속 진행"; \
    fi

# Ubuntu 22.04 main 에 없는 도구는 별도 설치.
# seclists — wordlists 모음 (git clone, 약 800 MB).
RUN git clone --depth=1 https://github.com/danielmiessler/SecLists.git /usr/share/seclists \
    && ln -s /usr/share/seclists /opt/seclists \
    || echo "[attacker] seclists clone 실패 (네트워크 확인) — 계속 진행"

# 추가 파이썬 도구 (impacket 은 apt 로 이미 설치됨).
RUN pip install --no-cache-dir \
        crackmapexec \
        enum4linux-ng \
        ldap3 \
        pyasn1 \
        requests \
    || true

COPY common/sshd_setup.sh /usr/local/bin/sshd_setup.sh
COPY attacker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/sshd_setup.sh /usr/local/bin/entrypoint.sh

EXPOSE 22
CMD ["/usr/local/bin/entrypoint.sh"]
