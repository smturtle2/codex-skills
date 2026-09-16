# world-simulator

브라우저 Studio에서 세계를 함께 만들고, 자연어 행동으로 이어지는 지속형 1인 RPG를 플레이합니다.

[스킬 목록](../../README.ko.md#skills) · [English](world-simulator.md)

<a id="install"></a>

## 설치

```text
Use $skill-installer to install skills/world-simulator from https://github.com/smturtle2/codex-skills.
```

로컬 브라우저와 Python 실행 환경이 필요합니다. Codex가 이야기를 진행하고 런타임이 세계와 이력을 저장합니다.

## 사용 예시

```text
$world-simulator로 기억을 거래하는 도시를 만들어줘. 첫 출근을 앞둔 견습 기록관으로 플레이하고 싶어.
```

## 작업 파일

기본 저장 루트는 프로젝트 기준 `.codex-skills/world-simulator/`이며, 각 세계의 세션 ID가 그 아래 실행 폴더 이름이 됩니다. 세계 DB와 에셋은 이어서 플레이할 수 있도록 보존하고 불필요한 턴 작업 파일만 정리합니다. 사용자가 지정한 위치와 기존 세계의 경로를 유지하며, 요청한 내보내기 결과물은 지정한 목적지에 저장합니다.

## 결과물

브라우저 Studio·Play 화면, 캐릭터 시트, 세계 설정집, 시간순 이야기, 재개 가능한 `world.sqlite3` 기록.

[에이전트용 지침 보기](../../skills/world-simulator/SKILL.md)
