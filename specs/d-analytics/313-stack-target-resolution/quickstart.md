# 빠른 확인: 굴뚝 대상 해석

[명세](spec.md) · [조사](research.md)
아래는 2026-11-18 측정을 다시 돌리는 방법과, 구현 뒤 사람이 직접 확인할 시나리오다. 측정 코드는 저장소에서 제외된 작업 폴더 `D/morph-router-20261117/redteam/`에 있다. 실행은 Kiwi·boto3·numpy가 있는 가상환경 `D/query-router-lab/.venv`로 한다. 규칙 코드는 수정하지 않는다.

## 측정 재현

```bash
cd D/morph-router-20261117/redteam
PY=../../query-router-lab/.venv/Scripts/python.exe
S=slot-eval-20261118        # slot-gold.jsonl(정답 1,043건)과 embed-cache.json이 있는 폴더

# 1. 글자·임베딩·혼합 검색 비교 (Bedrock Titan v2 호출. 캐시가 있으면 새 호출 없음)
$PY entity_embed_eval.py $S

# 2. 점수 차 임계값별 자동 선택·카드·"없음" 비율 (새 호출 없음)
$PY entity_policy_eval.py $S

# 3. 지역(시·도, 시·군)을 알려 준 뒤의 효과 (새 호출 없음)
$PY entity_region_eval.py $S
```

검색 모듈은 `entity_search.py`(글자 검색·충돌 후보), 이름 정리는 `entity_probe.py`다. 정답 세트와 질문별 결과는 `slot-eval-20261118/`에 보관했다.

## 충돌 이름 확인

```bash
$PY - <<'EOF'
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'..')
import slot_common as sc, entity_probe as ep, collections
g = collections.defaultdict(list)
for s in sc._STACKS.values(): g[ep.core(s['business'])].append(s['business'])
print({k: sorted(set(v)) for k, v in g.items() if len(set(v)) > 1})
EOF
```

기대: 크나우프석고보드, 한국제지가 `㈜`/`(주)` 쌍으로 나온다.

## 구현 뒤 사람이 확인할 시나리오

1. 굴뚝을 선택하지 않고 "포항 2번 NOx 어제 평균"을 묻는다 → 후보 카드(또는 확실하면 자동 선택)가 나오고 선택한 굴뚝이 답변에 표시된다.
2. 카드에서 "이 중에 없음" → 지역을 묻고, 시·군을 답하면 그 지역 후보 카드가 나온다. 한 번 더 없음 → 지도에서 선택 안내가 나온다.
3. 지도에서 굴뚝 A를 선택하고 "이 굴뚝 NOx 얼마야?" → A를 쓴다. 질문에 B를 명시하면 B를 쓴다.
4. "크나우프석고보드 6번"처럼 충돌 이름 → 점수와 무관하게 카드(전남 `㈜` / 울산 `(주)`)가 나온다.
5. 같은 표현을 두 번 보낸다 → 첫 번째 카드에서 고른 선택이 두 번째에는 확인 없이 적용된다(충돌 이름은 제외).
6. 임베딩 호출을 막은 상태에서 질문한다 → 오류 없이 글자 검색 결과가 나오고 기록에 degraded가 남는다.
7. 화면에서 굴뚝을 선택한 채 굴뚝 말 없이 "어제 NOx"를 묻는다 → 선택한 굴뚝으로 해석한다(선택은 후보를 제한하지 않고 우선순위만 준다).
