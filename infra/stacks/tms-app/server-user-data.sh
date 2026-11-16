#!/bin/bash
# API·에이전트 서버 시작 스크립트 (research R5, contracts/app-runtime.md)
# Terraform templatefile 변수: app, registry, repo, origin
set -euo pipefail

dnf install -y docker
systemctl enable --now docker

# 스왑 2GB (메모리가 잠깐 튈 때 컨테이너가 죽지 않게)
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

mkdir -p /opt/tms
cat > /opt/tms/deploy.sh <<'SCRIPT'
#!/bin/bash
# "현재 버전"(SSM /tms/app/${app}/image-tag) 이미지를 받아 컨테이너를 바꾼다. 배포(CI)도 이 스크립트를 부른다.
set -euo pipefail
export AWS_DEFAULT_REGION=ap-northeast-2

TAG=$(aws ssm get-parameter --name /tms/app/${app}/image-tag --query Parameter.Value --output text)
if [ "$TAG" = "none" ]; then
  echo "아직 배포된 이미지가 없다 (image-tag = none)"
  exit 0
fi

# /tms/app/config/<이름> → <이름 대문자, - 는 _> 환경 변수 (예: db-host → DB_HOST)
aws ssm get-parameters-by-path --path /tms/app/config --query 'Parameters[].[Name,Value]' --output text \
  | while read -r NAME VALUE; do
      KEY=$(basename "$NAME" | tr 'a-z-' 'A-Z_')
      echo "$KEY=$VALUE"
    done > /opt/tms/app.env
cat >> /opt/tms/app.env <<ENV
AWS_REGION=ap-northeast-2
DB_PORT=5432
DB_NAME=tms
APP_ORIGIN=${origin}
APP_VERSION=$TAG
ENV

aws ecr get-login-password | docker login --username AWS --password-stdin ${registry}
docker pull ${registry}/${repo}:$TAG

docker rm -f ${app} 2>/dev/null || true
docker run -d --name ${app} --restart always -p 8000:8000 \
  --env-file /opt/tms/app.env \
  --log-driver awslogs \
  --log-opt awslogs-region=ap-northeast-2 \
  --log-opt awslogs-group=/tms/app/${app} \
  --log-opt awslogs-create-group=false \
  ${registry}/${repo}:$TAG

docker image prune -af --filter "until=24h" || true
echo "배포 완료: ${repo}:$TAG"
SCRIPT
chmod +x /opt/tms/deploy.sh

/opt/tms/deploy.sh
