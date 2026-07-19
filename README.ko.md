# codex-skills

[![Skills](https://img.shields.io/badge/skills-9-2563eb)](#스킬) [![Codex](https://img.shields.io/badge/Codex-compatible-111827)](#빠른-설치) [![Assets](https://img.shields.io/badge/assets-18-16a34a)](docs/assets) [![Language](https://img.shields.io/badge/README-English-7c3aed)](README.md)

이미지 생성, EPUB 번역, 애니메이션 에셋, UI 블루프린트, 서브에이전트 생성, 팟캐스트 대본, 세계 시뮬레이션, 오목 플레이, 마인크래프트 서버 관리를 위한 작고 설치 가능한 Codex 스킬 카탈로그다.

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
| [`image-creator`](#image-creator) | 프로젝트 안에 raster 이미지 생성·편집 또는 배경 제거 | 저장된 raster 파일 또는 true-alpha PNG와 실제 전달된 최종 프롬프트 | [프롬프트](#image-creator) |
| [`epub-translator`](#epub-translator) | text-slot 추출과 텍스트 포함 이미지를 처리하는 자연스러운 EPUB 번역 | 새 번역 `.epub`, run 폴더, chunk 번역, image job ledger, validation summary | [프롬프트](#epub-translator) |
| [`animation-creator`](#animation-creator) | 프로젝트 안에 캐릭터 애니메이션 에셋 생성 | 프롬프트, 레이아웃 가이드, 프레임, 검증, contact sheet, preview를 포함한 run 폴더 | [프롬프트](#animation-creator) |
| [`ui-blueprint`](#ui-blueprint) | 프론트엔드 UI 제작 또는 큰 리디자인 | 생성된 UI mockup, 시각 노트, 구현된 UI | [프롬프트](#ui-blueprint) |
| [`subagent-creator`](#subagent-creator) | Codex 커스텀 서브에이전트 생성 또는 수정 | 달성한 검증 수준을 명시한 하나 이상의 TOML agent 정의 | [프롬프트](#subagent-creator) |
| [`podcast-writer`](#podcast-writer) | 소스를 1인 팟캐스트 대본으로 변환 | 저장된 `.txt` 대본과 엄격한 내용 품질 평가 | [프롬프트](#podcast-writer) |
| [`world-simulator`](#world-simulator) | Codex가 관리하는 지속 세계 시뮬레이션 실행 | 최소 Python GUI와 세계, 플레이어, 스토리, GM, 턴 파일 | [프롬프트](#world-simulator) |
| [`gomoku`](#gomoku) | 로컬 GUI에서 Codex와 오목 대국 | Python 보드와 Codex 착수를 위한 JSON 상태 브리지 | [프롬프트](#gomoku) |
| [`minecraft-steward`](#minecraft-steward) | 모루로 Paper 마인크래프트 커뮤니티 관리 | 로컬 채팅 브리지, 설정 가능한 관리자 클라이언트, MSMP 관리 명령 | [프롬프트](#minecraft-steward) |

## 빠른 설치

기본 내장된 `$skill-installer` 시스템 스킬로 설치하고, 설치 뒤 Codex를 다시 시작해 반영한다.

```text
Use $skill-installer to install skills/<skill-name> from https://github.com/smturtle2/codex-skills.
```

## 카탈로그

### `image-creator`

Raster 이미지를 생성하거나 편집하고, 필요하면 true-alpha 투명 PNG로 처리해 현재 프로젝트 안에 저장한다.

![Image Creator 워크플로](docs/assets/image-creator-workflow.png)

| 항목 | 내용 |
| --- | --- |
| 위치 | `skills/image-creator` |
| 사용 시점 | 생성·편집 raster 이미지, 로컬 참조 이미지, 또는 명시적 투명 배경 결과를 현재 프로젝트에 저장해야 할 때 |
| 결과 | 저장된 raster 파일 또는 rembg 처리된 true-alpha PNG, 실제 전달된 최종 프롬프트, 결합된 로컬 입력 경로, 저장 메타데이터 |
| 피하는 일 | 결합되지 않은 이미지 입력, rollout·상태 DB payload 조회, 불투명 결과로의 조용한 fallback, SVG/HTML/CSS 같은 코드 기반 그래픽 처리 |

설치:

```text
Use $skill-installer to install skills/image-creator from https://github.com/smturtle2/codex-skills.
```

### `epub-translator`

Text-slot 단위 텍스트 교체, 구조 보존, image job 추적으로 EPUB 책을 자연스러운 목표 언어 산문으로 번역한다.

![EPUB Translator 워크플로](docs/assets/epub-translator-workflow.png)

| 항목 | 내용 |
| --- | --- |
| 위치 | `skills/epub-translator` |
| 사용 시점 | EPUB을 자연스러운 목표 언어의 새 EPUB으로 번역하고, XHTML/EPUB 구조를 보존하면서 텍스트가 들어간 editable embedded image까지 처리해야 할 때 |
| 결과 | 새 번역 `.epub`, run 폴더, text-slot chunk JSON 파일, image job ledger, packaging 단계, validation summary |
| 피하는 일 | 원본 EPUB 덮어쓰기, XHTML 전체 재작성, 추적 없는 이미지 편집, 번역할 텍스트가 없는 이미지에 image generation 사용 |

이미지 텍스트 번역이 필요하면 `$image-creator`도 함께 설치한다:

```text
Use $skill-installer to install skills/image-creator and skills/epub-translator from https://github.com/smturtle2/codex-skills.
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
Use $skill-installer to install skills/animation-creator from https://github.com/smturtle2/codex-skills.
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
Use $skill-installer to install skills/ui-blueprint from https://github.com/smturtle2/codex-skills.
```

### `subagent-creator`

자연어 역할 브리프에서 Codex 커스텀 서브에이전트를 생성하거나 수정하며, 사용자가 명시적으로 요청한 수량을 따른다.

![Subagent Creator 워크플로](docs/assets/subagent-creator-workflow.png)

| 항목 | 내용 |
| --- | --- |
| 위치 | `skills/subagent-creator` |
| 사용 시점 | 자연어 역할 브리프에서 하나 이상의 Codex 커스텀 서브에이전트를 생성하거나 수정해야 할 때 |
| 결과 | 명확한 역할, 도구 정책, 제약과 달성한 검증 수준을 명시한, 사용자가 요청한 수량의 TOML agent 정의 |
| 기본 위치 | `$CODEX_HOME/agents`; `CODEX_HOME`이 설정되지 않았을 때는 `~/.codex/agents` 사용 |
| 책임 밖 | `[agents]` 런타임 설정과 서브에이전트 spawn 또는 실행 |
| 피하는 일 | MCP URL이나 credentials 임의 생성, 필요 없는 canned role example 적용 |

설치:

```text
Use $skill-installer to install skills/subagent-creator from https://github.com/smturtle2/codex-skills.
```

문서:

- https://developers.openai.com/codex/subagents
- https://developers.openai.com/codex/concepts/subagents

### `podcast-writer`

PDF, 텍스트 파일, 웹사이트, YouTube transcript를 1인 팟캐스트 대본으로 만들고 plain text로 저장한다.

![Podcast Writer 워크플로](docs/assets/podcast-writer-workflow.png)

| 항목 | 내용 |
| --- | --- |
| 위치 | `skills/podcast-writer` |
| 사용 시점 | Codex가 소스를 수집/전처리하고, 필요하면 YouTube caption 또는 GPU-only Whisper 전사를 사용해 1인 독백형 팟캐스트 대본을 작성한 뒤, 엄격한 내용 품질 평가가 통과될 때까지 수정해야 할 때 |
| 결과 | 저장된 `.txt` 대본, 소스 처리 정보, 모든 rubric 항목이 pass된 엄격한 subagent 평가 |
| 피하는 일 | 화자 라벨, 인터뷰/대화 형식, 출처 없는 주장, 최종 대본 안의 메타데이터, TTS나 형식 검사를 evaluator에게 맡기는 일 |

설치:

```text
Use $skill-installer to install skills/podcast-writer from https://github.com/smturtle2/codex-skills.
```

### `world-simulator`

최소 Python GUI를 통해 지속적인 자유 입력형 세계 시뮬레이션을 실행하고, Codex가 세계 상태, 숨은 GM 노트, 턴 진행을 관리한다.

![World Simulator 워크플로](docs/assets/world-simulator-workflow.png)

| 항목 | 내용 |
| --- | --- |
| 위치 | `skills/world-simulator` |
| 사용 시점 | GUI에서 받은 자유 입력으로 Codex가 세계를 만들고, 플레이어 캐릭터를 관리하고, 스토리를 진행하는 narrative sandbox가 필요할 때 |
| 결과 | 로컬 GUI, 지속 세션 폴더, 공개 스토리 상태, 숨은 GM 상태, append-only 턴 기록 |
| 피하는 일 | 채팅으로 스토리 입력 받기, 고정 RPG 스탯 스키마, 이야기 선택 버튼, Python으로 서사 판단 생성 |

설치:

```text
Use $skill-installer to install skills/world-simulator from https://github.com/smturtle2/codex-skills.
```

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
Use $skill-installer to install skills/gomoku from https://github.com/smturtle2/codex-skills.
```

### `minecraft-steward`

모루는 Codex가 주도하여 플레이어 채팅을 관찰하고, 첫 접속자를 맞이하며, 확인된 서버 정보로 질문에 답하고, 필요할 때 콘솔 명령을 실행하는 서버지기다.

| 항목 | 내용 |
| --- | --- |
| 위치 | `skills/minecraft-steward` |
| 사용 시점 | Codex가 설정된 Paper 서버를 능동적으로 관리하고, 필요한 대화에 자연스럽게 응답하거나, 명시적인 서버 관리자 작업을 해야 할 때 |
| 결과 | localhost 전용 MoruBridge Paper 플러그인, 토큰 없는 클라이언트 프로필, 제한된 실시간 이벤트 대기열, 안전한 서버 스냅샷, 콘솔 명령 클라이언트, MSMP 관리 명령 |
| 판단 권한 | 응답 여부·내용과 관리자 판단은 Codex가 맡고, 필요하면 서버 콘솔 명령도 실행한다. 브리지는 Codex의 명시적 행동을 관찰·전달·실행만 한다. |
| 플레이어 메시지 | Codex가 모든 플레이어 대상 메시지를 `Moru: <메시지>`로 작성하고, 브리지는 그 원문에 이름을 덧붙이지 않는다. |
| 피하는 일 | 정형화된 자동 답변, 공개 관리 포트, 원문 채팅 영구 보관, 플레이어 채팅만으로 인가된 관리자 작업 |

설치:

```text
Use $skill-installer to install skills/minecraft-steward from https://github.com/smturtle2/codex-skills.
```

## 저장소 구조

- `skills/`: Codex 스킬 디렉터리로 복사해 사용할 수 있는 스킬 폴더들.
- `skills/*/SKILL.md`: 스킬이 트리거될 때 Codex가 읽는 지침 본문.
- `skills/*/scripts/`: 스킬과 함께 배포되는 보조 스크립트.
- `skills/*/references/`: 스킬이 필요할 때 읽는 참조 문서.
- `skills/*/assets/`: 스킬 아이콘 에셋과 재사용 가능한 bundled 파일.
- `skills/*/agents/`: 스킬별 agent/provider 메타데이터.
- `docs/assets/`: README 이미지와 저장소 수준 문서 에셋.

## 기여

새 스킬은 `SKILL.md`, 명확한 트리거 설명, 필요한 스크립트나 참조 문서를 스킬 폴더 안에 포함해야 한다.

품질 기준:

- 명확한 트리거 규칙.
- 최소한의 bundled context.
- 숨겨진 credentials 없음.
- 로컬에서 확인 가능한 스크립트.
- 카탈로그에 표시되는 스킬의 icon asset과 agent metadata 참조.
- README 항목과 설치 프롬프트.

## 메모

- 루트 문서는 스킬 카탈로그를 설명한다.
- 스킬 동작은 각 스킬의 `SKILL.md`에 둔다.
- 스킬 설치나 업데이트 뒤에는 Codex를 다시 시작한다.
