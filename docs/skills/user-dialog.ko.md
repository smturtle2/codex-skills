# user-dialog

소통 목적에 맞는 팝업 인터페이스를 구성하고, 사용자의 반응을 받아 전달합니다.

[전체 스킬](../../README.ko.md#skills) · [English](user-dialog.md)

## 설치

```text
Use $skill-installer to install skills/user-dialog from https://github.com/smturtle2/codex-skills.
```

uv와 GTK4·libadwaita·PyGObject를 사용할 수 있는 Python 환경이 필요합니다. 실행기가 uv의 Python과 별도로 적합한 인터프리터를 찾습니다. 네이티브 의존성과 인터프리터 지정 방법은 [실행 환경 안내](../../skills/user-dialog/references/runtime-setup.md)에 있습니다. 현재 Linux 실행을 확인했으며 Windows·macOS는 아직 검증하지 않았습니다.

## 인터페이스

기본 외관은 블루·아담한 libadwaita입니다. 고정된 양식 목록 없이 Codex가 내용과 상호작용을 구성합니다. 관련 요청은 한 창에 모으고, 공통 실행기가 등록된 입력값을 유지하며 구조화된 응답을 반환합니다.

처음에는 내용의 첫 컨트롤에 포커스가 잡힙니다. Tab·Shift+Tab으로 이동하고, 한 줄 입력의 Enter는 기본 동작을 실행하며 여러 줄 입력에서는 줄바꿈을 유지합니다. Ctrl+Enter는 기본 동작을 실행하고, macOS에서는 Command+Enter도 지원합니다. Esc로 닫아도 입력값은 보존합니다. 화면에 맞게 포커스와 기본 동작을 조정할 수 있습니다.

## 결과물

실행 폴더에 화면 파일의 위치, 등록된 입력값, 최종 응답을 보존합니다. 생성한 화면과 보조 파일은 설치된 스킬 밖에 둡니다. 다시 열면 등록된 값을 복원하고, 제출된 응답은 창을 열지 않고 다시 읽을 수 있습니다. 창을 닫는 것은 답변 제출과 구분됩니다.

[에이전트 지침](../../skills/user-dialog/SKILL.md)
