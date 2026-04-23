# codex-skills

[English README](README.md)

재사용 가능한 Codex 스킬을 모아 두는 저장소다. 각 스킬은 별도 폴더에 들어가며, 기본적으로 `SKILL.md`와 필요할 때 참조 문서, 스크립트, 에셋을 함께 포함한다.

## 저장소 구조

- `skills/`: Codex 스킬 디렉터리로 복사해 사용할 수 있는 스킬 폴더들

## 설치 방법

이 저장소의 스킬은 기본 내장된 시스템 스킬 `$skill-installer`로 설치하면 된다. 각 스킬 항목 아래에는 그대로 복사해서 붙여 넣을 수 있는 한 줄 프롬프트를 적어 두었다.

스킬을 설치한 뒤에는 Codex를 다시 시작해야 반영된다.

## 현재 포함된 스킬

### `image-creator`

- 위치: `skills/image-creator`
- 목적: 사용자의 요청을 이미지 생성 모델에 적합한 프롬프트로 재구성하되 의미, 의도, 이미지 안에 들어갈 정확한 문구, 명시 제약은 보존해 raster 이미지를 생성 또는 편집
- 기본 동작: `imagegen`과 같은 이미지 생성 경로를 따르며, 기본적으로 내장 `image_gen`을 사용하고 생성에 필요한 로컬 입력 이미지만 `image_gen` 직전에 로드하며 그 브리지 단계 외에는 `view_image`를 절대 쓰지 않은 뒤 생성된 이미지를 요청한 경로나 프로젝트 루트에 저장
- 성격: 새 창작 요소를 임의로 추가하지 않고 최종 프롬프트를 간결하고 시각적으로 정리하며, 명백한 저장 경로와 파일 로딩 지시는 실행 지시로 처리
- 프롬프트 처리: 사용자의 이미지 의도와 명시 제약을 보존해 모델에 적합한 프롬프트로 재구성한 뒤, 별도 스킬 레이어 안전성/검열식 검사를 추가하지 않고 선택된 생성 경로를 호출
- 경계: 생성형 raster 이미지에 사용하며, 이미지를 만들지 않는 프롬프트 엔지니어링이나 SVG/HTML/CSS 같은 코드 기반 그래픽에는 사용하지 않음

설치:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/image-creator
```

### `ui-blueprint`

- 위치: `skills/ui-blueprint`
- 목적: 프론트엔드 UI 작업을 텍스트 계획만으로 바로 구현하지 않고, 먼저 생성된 시각 blueprint에서 출발하도록 강제
- 기본 동작: `image-creator`로 UI mockup을 만들고, 이미지를 검토한 뒤 레이아웃, 계층, 색, 타이포그래피, spacing, 상태 단서를 추출해 구현
- 성격: 모델 선택이 가능한 환경에서는 reasoning workflow를 `gpt-5.4`로 고정하되, 대상 repo의 프론트엔드 스택과 컴포넌트 관례를 유지
- 경계: 새 UI, 큰 리디자인, 시각 품질이 중요한 화면에 사용하며, 좁은 버그픽스나 작은 유지보수 수정에는 사용하지 않음

설치:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/ui-blueprint
```

### `subagent-creator`

- 위치: `skills/subagent-creator`
- 목적: 자연어 브리프만으로 하나의 집중된 Codex 커스텀 서브에이전트를 생성하거나 갱신
- 기본 동작: 보통 `~/.codex/agents/` 아래에 커스텀 에이전트 TOML 파일 하나를 작성
- 성격: 브리프에서 역할을 직접 도출하고, 기본값은 보수적으로 유지하며, 근거 없는 MCP URL이나 추가 전역 설정을 임의로 만들지 않음
- 철학: canned role example은 의도적으로 피하고, 대신 규칙, 스키마 제약, 검증 단계에 투자해 zero-shot 성질을 유지

설치:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/subagent-creator
```

이 스킬은 공식 Codex 서브에이전트 문서를 기준으로 작성됐다.

- https://developers.openai.com/codex/subagents
- https://developers.openai.com/codex/concepts/subagents

## 메모

- 이 저장소는 작게 시작해서 필요한 스킬을 추가하는 방식으로 유지한다.
- 루트 문서는 스킬 카탈로그 역할만 한다.
- 스킬별 상세 지침은 별도 README 대신 각 스킬 폴더 내부에 둔다.
