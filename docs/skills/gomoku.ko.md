# gomoku

로컬 보드에서 돌을 두면 Codex가 판세를 읽고 다음 수를 선택합니다.

[스킬 목록](../../README.ko.md#skills) · [English](gomoku.md)

<a id="install"></a>

## 설치

```text
Use $skill-installer to install skills/gomoku from https://github.com/smturtle2/codex-skills.
```

데스크톱 GUI 환경과 Pygame을 실행할 Python이 필요합니다. 상대의 수는 Codex가 결정합니다.

## 사용 예시

```text
$gomoku로 오목을 시작해줘. 15×15 보드에서 내가 흑으로 둘게.
```

## 작업 파일

위치를 지정하지 않았다면 재개 가능한 게임 상태를 프로젝트 루트 기준 `.codex-skills/gomoku/<run-id>/`에 보관합니다. 사용자가 위치를 지정하면 그 위치를 우선하고, 기존 상태는 옮기지 않고 그 자리에서 재개합니다. 재개에 필요한 데이터는 보존하고 이번 실행에서 만든 폐기 가능한 중간 파일만 정리합니다.

## 결과물

착수 검증, 승리 판정, 선택 가능한 렌주 제한을 갖춘 Pygame 보드.

[에이전트용 지침 보기](../../skills/gomoku/SKILL.md)
