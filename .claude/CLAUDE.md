# CLAUDE.md — smokestack-guard

팀 공통 규칙은 저장소 루트의 `AGENTS.md`에 있다. Codex 등 다른 에이전트와 같은 규칙을 쓰기 위해 규칙은 그 파일에서만 고친다.

@../AGENTS.md

## Claude Code 전용

- `.claude/settings.json`의 `deny` 목록이 `AGENTS.md`의 금지 명령을 강제한다. 둘을 함께 고친다.
- Spec Kit 명령은 `.claude/skills/speckit-*`에 스킬로 설치되어 있다. `/speckit-specify`처럼 하이픈으로 호출한다.
- 개인 설정(커밋 작성자, 작업 환경)은 저장소 루트의 `CLAUDE.local.md`에 둔다. 이 파일은 커밋하지 않는다.
