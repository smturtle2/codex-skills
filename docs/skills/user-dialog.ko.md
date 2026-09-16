# user-dialog

기본 UI 요소를 JSON으로 조합해 팝업을 만들고 응답을 원래 Codex 작업으로 전달합니다.

[전체 스킬](../../README.ko.md#skills) · [English](user-dialog.md)

## 설치

```text
Use $skill-installer to install skills/user-dialog from https://github.com/smturtle2/codex-skills.
```

## 사용법

예를 들어 “$user-dialog를 사용해 배포 대상을 물어보고 staging과 production 버튼을 보여줘”라고 요청할 수 있습니다.

## 작업 파일

대화 실행에 지속 상태가 필요하면 사용자가 위치를 지정하지 않은 경우 프로젝트 루트 기준 `.codex-skills/user-dialog/<run-id>/`를 사용합니다. 기존 위치는 옮기지 않고 그 자리에서 재개하며, 복구에 필요한 상태는 보존하고 이번 실행에서 만든 폐기 가능한 중간 파일만 정리합니다.

자세한 지침은 [SKILL.md](../../skills/user-dialog/SKILL.md)와 [뷰 계약](../../skills/user-dialog/references/view-contract.md)을 참조하세요.
