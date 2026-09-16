# user-dialog

입력 필드와 Markdown 문서, 이미지 또는 문서 파일 경로를 자유롭게 조합해 팝업을 만들고 응답을 원래 Codex 작업으로 전달합니다.

[전체 스킬](../../README.ko.md#skills) · [English](user-dialog.md)

## 설치

```text
Use $skill-installer to install skills/user-dialog from https://github.com/smturtle2/codex-skills.
```

## 런타임 요구 사항

런처는 uv로 Python 의존성을 관리합니다. Markdown과 독립 코드 블록을 사용하려면 네이티브 WebKitGTK 6.0 런타임도 필요합니다.
Debian/Ubuntu에서는 GTK 및 libadwaita 런타임 패키지와 함께 `gir1.2-webkit-6.0`을 설치하세요.

## 사용법

예를 들어 “$user-dialog를 사용해 배포 대상을 물어보고 staging과 production 버튼을 보여줘”라고 요청할 수 있습니다.

작성한 콘텐츠에는 문자열 `text` 또는 입력/선택 값의 `ref`를 받는 `markdown` 노드를 사용하세요. Markdown 파일은 `file`에서 같은 렌더러를 사용하며, 제목·테두리·원문 복사·코드 복사 컨트롤을 `display` 옵션으로 각각 설정할 수 있습니다.

본문과 입력·버튼에는 포함된 Pretendard, 코드에는 D2Coding을 사용합니다. 독립 코드와 Markdown 안의 코드 블록은 구문 색상·여백·상단 바를 공유하며, 언어명은 왼쪽, 복사 버튼은 오른쪽에 표시합니다. Markdown 파일은 기본적으로 파일명과 문서 테두리를 유지합니다. 글꼴은 로컬에서 불러오며 시스템 테마나 설치된 글꼴을 변경하지 않습니다.

## 작업 파일

대화 실행에 지속 상태가 필요하면 사용자가 위치를 지정하지 않은 경우 프로젝트 루트 기준 `.codex-skills/user-dialog/<run-id>/`를 사용합니다. 기존 위치는 옮기지 않고 그 자리에서 재개하며, 복구에 필요한 상태는 보존하고 이번 실행에서 만든 폐기 가능한 중간 파일만 정리합니다.

자세한 지침은 [SKILL.md](../../skills/user-dialog/SKILL.md)와 [뷰 계약](../../skills/user-dialog/references/view-contract.md)을 참조하세요.
