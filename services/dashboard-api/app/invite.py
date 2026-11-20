"""초대 코드 확인 → Cognito 그룹 members에 추가

specs/a-platform/013-google-login-invite (research R6)

- 정답: SSM SecureString (INVITE_CODE_PARAM, 기본 /tms/app/secret/invite-code).
  사람이 콘솔로 등록·교체한다.
  5분 캐시라 교체가 5분 안에 반영된다. 환경 변수로 넣지 않는다.
- 비교: 앞뒤 공백 제거 + 유니코드 NFC(자모가 나뉘어 오는 입력) 뒤 상수 시간 비교
- 틀린 시도: 회원(sub)별 10분에 5번까지. 서버 메모리라 서버마다 따로 센다
- 입력한 코드 값은 로그·예외에 남기지 않는다
"""

from __future__ import annotations

import hmac
import os
import threading
import time
import unicodedata
from collections import defaultdict, deque

REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
CACHE_SECONDS = 300
MAX_FAILURES = 5
WINDOW_SECONDS = 600


class NotConfigured(Exception):
    """정답을 읽지 못함 → 아무도 통과시키지 않는다."""


class TooManyAttempts(Exception):
    pass


def normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


class InviteChecker:
    def __init__(self, ssm=None, cognito=None, clock=time.monotonic):
        self._ssm = ssm
        self._cognito = cognito
        self._clock = clock
        self._lock = threading.Lock()
        self._cached: tuple[float, str] | None = None
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    # --- AWS 클라이언트 (처음 쓸 때 만든다) ---
    def _ssm_client(self):
        if self._ssm is None:
            import boto3

            self._ssm = boto3.client("ssm", region_name=REGION)
        return self._ssm

    def _cognito_client(self):
        if self._cognito is None:
            import boto3

            self._cognito = boto3.client("cognito-idp", region_name=REGION)
        return self._cognito

    # --- 정답 ---
    def _answer(self) -> str:
        now = self._clock()
        if self._cached and now - self._cached[0] < CACHE_SECONDS:
            return self._cached[1]
        name = os.environ.get("INVITE_CODE_PARAM", "/tms/app/secret/invite-code")
        try:
            value = self._ssm_client().get_parameter(Name=name, WithDecryption=True)
            answer = normalize(value["Parameter"]["Value"])
        except Exception as e:  # 권한·없음·네트워크. 원인 종류만 남긴다
            raise NotConfigured(type(e).__name__) from None
        if not answer:
            raise NotConfigured("empty")
        self._cached = (now, answer)
        return answer

    # --- 시도 제한 ---
    def _recent_failures(self, sub: str, now: float) -> deque[float]:
        q = self._failures[sub]
        while q and now - q[0] >= WINDOW_SECONDS:
            q.popleft()
        return q

    def check(self, sub: str, code: str) -> bool:
        """맞으면 True. 제한에 걸렸으면 TooManyAttempts, 정답이 없으면 NotConfigured."""
        now = self._clock()
        with self._lock:
            if len(self._recent_failures(sub, now)) >= MAX_FAILURES:
                raise TooManyAttempts()
        answer = self._answer()
        ok = hmac.compare_digest(normalize(code).encode("utf-8"), answer.encode("utf-8"))
        if not ok:
            with self._lock:
                self._recent_failures(sub, now).append(now)
        return ok

    def add_to_members(self, username: str) -> None:
        self._cognito_client().admin_add_user_to_group(
            UserPoolId=os.environ["COGNITO_USER_POOL_ID"], Username=username, GroupName="members"
        )


checker = InviteChecker()
