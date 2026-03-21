# codex-skills

[English README](README.md)

재사용 가능한 Codex 스킬을 모아 두는 저장소다. 각 스킬은 별도 폴더에 들어가며, 기본적으로 `SKILL.md`와 필요할 때 참조 문서, 스크립트, 에셋을 함께 포함한다.

## 저장소 구조

- `skills/`: Codex 스킬 디렉터리로 복사해 사용할 수 있는 스킬 폴더들

## 현재 포함된 스킬

### `subagent-creator`

- 위치: `skills/subagent-creator`
- 목적: 자연어 브리프만으로 하나의 집중된 Codex 커스텀 서브에이전트를 생성
- 기본 동작: 보통 `~/.codex/agents/` 아래에 커스텀 에이전트 TOML 파일 하나를 작성
- 성격: 브리프에서 역할을 직접 도출하고, 기본값은 보수적으로 유지하며, 근거 없는 MCP URL이나 추가 전역 설정을 임의로 만들지 않음

이 스킬은 공식 Codex 서브에이전트 문서를 기준으로 작성됐다.

- https://developers.openai.com/codex/subagents
- https://developers.openai.com/codex/concepts/subagents

## 메모

- 이 저장소는 작게 시작해서 필요한 스킬을 추가하는 방식으로 유지한다.
- 루트 문서는 스킬 카탈로그 역할만 한다.
- 스킬별 상세 지침은 별도 README 대신 각 스킬 폴더 내부에 둔다.
