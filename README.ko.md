# <img src="docs/assets/catalog-mark.svg" width="32" height="32" alt=""> codex-skills

필요한 작업에 맞춰 골라 쓰는 Codex 스킬 컬렉션.

[설치](#install) · [스킬 목록](#skills) · [기여하기](CONTRIBUTING.ko.md) · [English](README.md)

<a id="install"></a>

## 설치

목록에서 스킬 이름을 골라 Codex에 요청하세요.

```text
Use $skill-installer to install skills/<skill-name> from https://github.com/smturtle2/codex-skills.
```

설치 후 `$스킬이름`과 함께 원하는 작업을 요청합니다. 각 사용 가이드에는 복사할 수 있는 설치 프롬프트, 사용 예시, 필요한 도구가 있습니다. 설치한 스킬이 보이지 않으면 Codex를 다시 시작하세요.

<a id="skills"></a>

## 스킬 목록

이름순으로 정렬했습니다. 사용 가이드는 사용법을, 지침은 Codex가 작업하는 방식을 설명합니다.

<!-- skills:start -->

### animation-creator

동작을 의미 있는 자세 변화로 나누고, 같은 캐릭터 기준 이미지를 사용해 프레임을 생성합니다.

[사용 가이드](docs/skills/animation-creator.ko.md) · [지침](skills/animation-creator/SKILL.md) · [설치](docs/skills/animation-creator.ko.md#install)

### epub-translator

EPUB을 번역해 용어와 장 사이의 맥락이 이어지는 새 판본을 만듭니다.

[사용 가이드](docs/skills/epub-translator.ko.md) · [지침](skills/epub-translator/SKILL.md) · [설치](docs/skills/epub-translator.ko.md#install)

### gomoku

로컬 보드에서 돌을 두면 Codex가 판세를 읽고 다음 수를 선택합니다.

[사용 가이드](docs/skills/gomoku.ko.md) · [지침](skills/gomoku/SKILL.md) · [설치](docs/skills/gomoku.ko.md#install)

### idea-scribe

떠오르는 생각을 원문 그대로 기록하고, 현재 유효한 내용만 읽기 좋은 문서로 정리합니다.

[사용 가이드](docs/skills/idea-scribe.ko.md) · [지침](skills/idea-scribe/SKILL.md) · [설치](docs/skills/idea-scribe.ko.md#install)

### image-creator

래스터 이미지를 생성·편집해 프로젝트에 저장합니다. 요청하면 처음부터 투명 배경 PNG로 생성합니다.

[사용 가이드](docs/skills/image-creator.ko.md) · [지침](skills/image-creator/SKILL.md) · [설치](docs/skills/image-creator.ko.md#install)

### podcast-writer

문서·웹사이트·YouTube 자료를 하나의 독백형 대본으로 엮고, 독립적인 내용 검토를 거쳐 다듬습니다.

[사용 가이드](docs/skills/podcast-writer.ko.md) · [지침](skills/podcast-writer/SKILL.md) · [설치](docs/skills/podcast-writer.ko.md#install)

### subagent-creator

역할 설명을 책임 범위와 제약이 명확한 Codex 커스텀 에이전트 정의로 바꿉니다.

[사용 가이드](docs/skills/subagent-creator.ko.md) · [지침](skills/subagent-creator/SKILL.md) · [설치](docs/skills/subagent-creator.ko.md#install)

### ui-blueprint

시각적 시안을 생성하고 디자인 결정을 정리한 뒤, 기존 프런트엔드 스택으로 화면을 구현합니다.

[사용 가이드](docs/skills/ui-blueprint.ko.md) · [지침](skills/ui-blueprint/SKILL.md) · [설치](docs/skills/ui-blueprint.ko.md#install)

### world-simulator

브라우저 Studio에서 세계를 함께 만들고, 자연어 행동으로 이어지는 지속형 1인 RPG를 플레이합니다.

[사용 가이드](docs/skills/world-simulator.ko.md) · [지침](skills/world-simulator/SKILL.md) · [설치](docs/skills/world-simulator.ko.md#install)

<!-- skills:end -->

## 스킬 추가·개선

[`skills/`](skills/)의 각 폴더에는 `SKILL.md`와 필요한 보조 파일이 들어 있습니다. 사람을 위한 사용 가이드는 [`docs/skills/`](docs/skills/)에 있습니다.

스킬 추가·수정·삭제와 목록 갱신 방법은 [기여 가이드](CONTRIBUTING.ko.md)를 참고하세요. 예시 이미지와 개별 아이콘은 선택 사항입니다.
