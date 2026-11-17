#!/bin/bash
# 배스천 SSH를 DB 터널 전용으로 묶는다 (research R10).
# - 비밀번호 로그인 끔
# - ec2-user(공용 키)는 RDS 5432로의 로컬 포워딩만 허용, 셸·TTY 없음
set -euo pipefail

cat > /etc/ssh/sshd_config.d/10-tms.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
X11Forwarding no
EOF

# Match 블록은 파일 끝까지 적용되므로 본 설정 파일 맨 끝에 붙인다.
cat >> /etc/ssh/sshd_config <<'EOF'

# tms: 공용 키는 DB 터널 전용
Match User ec2-user
    AllowTcpForwarding local
    PermitOpen ${db_host}:5432
    PermitTTY no
    ForceCommand /sbin/nologin
EOF

sshd -t
systemctl restart sshd
