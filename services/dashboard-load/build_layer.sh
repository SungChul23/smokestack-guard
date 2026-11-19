#!/usr/bin/env bash
# pg8000 레이어 zip을 만든다 (research R5). terraform plan 전에 사람이 한 번 실행한다.
# python-dateutil은 Lambda 런타임의 botocore와 맞춘다(<3). 레이어가 런타임 패키지보다 먼저 읽히기 때문이다.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf build/layer && mkdir -p build/layer/python
python3 -m pip install --quiet --no-compile --target build/layer/python \
  "pg8000==1.31.2" "python-dateutil==2.9.0.post0"
(cd build/layer && python3 -m zipfile -c ../pg8000_layer.zip python)
echo "build/pg8000_layer.zip"
