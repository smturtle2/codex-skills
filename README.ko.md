# codex-skills

[![Skills](https://img.shields.io/badge/skills-5-2563eb)](#스킬) [![Codex](https://img.shields.io/badge/Codex-compatible-111827)](#빠른-설치) [![Assets](https://img.shields.io/badge/docs-assets-16a34a)](docs/assets) [![Language](https://img.shields.io/badge/README-English-7c3aed)](README.md)

이미지 생성, 애니메이션 에셋, UI 블루프린트, 서브에이전트 생성, 오목 플레이를 위한 작고 설치 가능한 Codex 스킬 카탈로그다.

각 스킬은 `SKILL.md` 트리거 계약과 필요한 로컬 스크립트, 참조 문서, 에셋, agent 메타데이터를 함께 담는 독립 폴더다.

언어: [English](README.md) | 한국어

![Codex 스킬 카탈로그](docs/assets/codex-skills-hero.png)

## 왜 쓰나

- Codex 스킬 디렉터리에 그대로 복사할 수 있는 독립 스킬들.
- 각 스킬마다 바로 붙여 넣을 수 있는 설치 프롬프트.
- 데모가 아니라 실제 작업용 워크플로.
- 설치 전에 훑어보기 쉬운 작은 구성.

## 스킬

| 스킬 | 적합한 작업 | 결과 | 설치 |
| --- | --- | --- | --- |
| [`image-creator`](#image-creator) | 프로젝트 안에 raster 이미지 생성 또는 편집 | 저장된 이미지 파일과 실제 전달된 최종 프롬프트 | [프롬프트](#image-creator) |
| [`animation-creator`](#animation-creator) | 프로젝트 안에 캐릭터 애니메이션 에셋 생성 | 프롬프트, 레이아웃 가이드, 프레임, 검증, contact sheet, preview를 포함한 run 폴더 | [프롬프트](#animation-creator) |
| [`ui-blueprint`](#ui-blueprint) | 프론트엔드 UI 제작 또는 큰 리디자인 | 생성된 UI mockup, 시각 노트, 구현된 UI | [프롬프트](#ui-blueprint) |
| [`subagent-creator`](#subagent-creator) | 집중된 Codex 커스텀 서브에이전트 생성 | 검증 가능한 TOML agent 정의 | [프롬프트](#subagent-creator) |
| [`gomoku`](#gomoku) | 로컬 GUI에서 Codex와 오목 대국 | Python 보드와 Codex 착수를 위한 JSON 상태 브리지 | [프롬프트](#gomoku) |

## 빠른 설치

기본 내장된 `$skill-installer` 시스템 스킬로 설치하고, 설치 뒤 Codex를 다시 시작해 반영한다.

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/<skill-name>
```

## 카탈로그

### `image-creator`

Raster 이미지를 생성하거나 편집하고 현재 프로젝트 안에 저장한다.

![Image Creator 워크플로](docs/assets/image-creator-workflow.png)

| 항목 | 내용 |
| --- | --- |
| 위치 | `skills/image-creator` |
| 사용 시점 | 생성형 또는 편집된 raster 이미지를 현재 프로젝트에 저장해야 할 때 |
| 결과 | 저장된 이미지 파일, 실제 전달된 최종 프롬프트, 입력 이미지 정보, 사용한 생성 경로 |
| 피하는 일 | 로컬 이미지 브리지 단계 밖에서 `view_image` 사용, 임의 창작 제약 추가, SVG/HTML/CSS 같은 코드 기반 그래픽 처리 |

설치:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/image-creator
```

### `animation-creator`

소스 캐릭터 이미지 또는 생성된 base 캐릭터를 기준으로 캐릭터 애니메이션 에셋을 만든다.

![Animation Creator 워크플로](docs/assets/animation-creator-workflow.png)

| 항목 | 내용 |
| --- | --- |
| 위치 | `skills/animation-creator` |
| 사용 시점 | 한 캐릭터 정체성을 유지하는 sprite strip, frame sequence, GIF/WebP/MP4 preview, 추가 행동 애니메이션이 필요할 때 |
| 결과 | canonical base reference, action prompt, layout guide, 추출 프레임, contact sheet, validation JSON, preview가 있는 run 폴더 |
| 피하는 일 | 전역 패키징, 로컬 코드로 캐릭터 그림 생성 대체, 잘리거나 slot을 침범한 프레임 수락 |

설치:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/animation-creator
```

### `ui-blueprint`

먼저 UI mockup을 생성하고, 그 시각 블루프린트를 기준으로 프론트엔드 작업을 구현한다.

![UI Blueprint 워크플로](docs/assets/ui-blueprint-workflow.png)

| 항목 | 내용 |
| --- | --- |
| 위치 | `skills/ui-blueprint` |
| 사용 시점 | 새 UI, 큰 리디자인, 시각 품질이 중요한 화면을 구현할 때 |
| 결과 | 생성된 mockup, 레이아웃과 시각 결정 노트, 기존 프론트엔드 스택에 맞춘 구현 지침 |
| 피하는 일 | 시각적으로 중요한 UI 작업에서 blueprint 건너뛰기, 좁은 버그픽스나 작은 유지보수에 이 흐름 적용 |

설치:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/ui-blueprint
```

### `subagent-creator`

자연어 역할 브리프를 집중된 Codex 커스텀 서브에이전트 하나로 바꾼다.

![Subagent Creator 워크플로](docs/assets/subagent-creator-workflow.png)

| 항목 | 내용 |
| --- | --- |
| 위치 | `skills/subagent-creator` |
| 사용 시점 | 자연어 브리프에서 하나의 집중된 Codex 커스텀 서브에이전트를 만들어야 할 때 |
| 결과 | 명확한 역할, 도구 정책, 제약, 가능한 검증을 포함한 TOML agent 정의 |
| 피하는 일 | 기본적으로 여러 agent 생성, MCP URL이나 credentials 임의 생성, 필요 없는 canned role example 적용 |

설치:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/subagent-creator
```

문서:

- https://developers.openai.com/codex/subagents
- https://developers.openai.com/codex/concepts/subagents

### `gomoku`

로컬 Python GUI에서 사용자가 오목을 두면 Codex가 기다리고, Codex view JSON을 읽어 자신의 수를 적용한다.

![Gomoku 워크플로](docs/assets/gomoku-workflow.png)

| 항목 | 내용 |
| --- | --- |
| 위치 | `skills/gomoku` |
| 사용 시점 | 로컬 Python GUI에서 사용자가 오목을 두고 Codex가 직접 다음 수를 골라 적용하게 할 때 |
| 결과 | Pygame 보드, 내부 상태 관리, 착수 검증, 승패 판정, 선택적 렌주 금수, Codex wait/apply 명령 |
| 피하는 일 | 고정 AI 엔진 구현, GUI에서 OpenAI API 호출 |

설치:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/gomoku
```

## 저장소 구조

- `skills/`: Codex 스킬 디렉터리로 복사해 사용할 수 있는 스킬 폴더들.
- `skills/*/SKILL.md`: 스킬이 트리거될 때 Codex가 읽는 지침 본문.
- `skills/*/scripts/`: 스킬과 함께 배포되는 보조 스크립트.
- `skills/*/references/`: 스킬이 필요할 때 읽는 참조 문서.
- `skills/*/agents/`: 스킬별 agent/provider 메타데이터.
- `docs/assets/`: README 이미지와 저장소 수준 문서 에셋.

## 기여

새 스킬은 `SKILL.md`, 명확한 트리거 설명, 필요한 스크립트나 참조 문서를 스킬 폴더 안에 포함해야 한다.

품질 기준:

- 명확한 트리거 규칙.
- 최소한의 bundled context.
- 숨겨진 credentials 없음.
- 로컬에서 확인 가능한 스크립트.
- README 항목과 설치 프롬프트.

## 메모

- 루트 문서는 스킬 카탈로그를 설명한다.
- 스킬 동작은 각 스킬의 `SKILL.md`에 둔다.
- 스킬 설치나 업데이트 뒤에는 Codex를 다시 시작한다.
