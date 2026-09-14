# user-dialog

선언형 JSON 요청으로 팝업을 만들고 응답을 원래 Codex 작업으로 전달합니다.

[전체 스킬](../../README.ko.md#skills) · [English](user-dialog.md)

## 설치

```text
Use $skill-installer to install skills/user-dialog from https://github.com/smturtle2/codex-skills.
```

## 사용법

`SKILL_DIR`는 설치한 스킬의 절대 경로로 지정합니다.

```bash
uv run --script "$SKILL_DIR/scripts/user_dialog.py" show <request.json|-> \
  [--run-dir <path>] [--python <absolute-python>]
```

요청은 버전 1이며 `version`, `title`, `subtitle`, `body`, `actions`,
`message`, `width` 키를 사용합니다. 본문은 선언형 트리이고 요청별
Python을 로드하지 않습니다. 자세한 스키마는 [뷰 계약](../../skills/user-dialog/references/view-contract.md)을
참조하세요.

`show`는 분리된 렌더러를 시작하고 실행 상태를 반환합니다. 일반 제출은
앱 브리지를 통한 내부 도구 입력으로 Markdown을 원래 작업에 전달합니다.
`--preview`를 명시하면 원본 연결과 전달을 끄고 `message.md`를 저장하며,
실패 시 자동 미리보기 전환은 없습니다. `validate`, `templates`, `status`,
`resume`, `deliver`로 검증·템플릿·실행 복구를 수행합니다.

실행기에는 uv와 Python 3.11 이상이 필요하고, 렌더러에는 PyGObject,
GTK 4.16 이상, libadwaita 1.6 이상이 필요합니다. Linux 렌더링과 읽기 전용
원본 캡처 및 앱 브리지 실시간 전달 왕복을 확인했습니다. Windows 전송은
지원하지 않습니다. [실행 환경 안내](../../skills/user-dialog/references/runtime-setup.md)를
참조하세요.
