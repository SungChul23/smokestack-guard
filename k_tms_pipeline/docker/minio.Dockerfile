# 1. Go로 MinIO 서버 컴파일
FROM golang:1.24-alpine AS build
RUN CGO_ENABLED=0 go install github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z

# 2. 컴파일 완료된 실행 파일 이미지로 복사
FROM alpine:3.20
COPY --from=build /go/bin/minio /usr/local/bin/minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]

