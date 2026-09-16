# podcast-writer

문서·웹사이트·YouTube 자료를 하나의 독백형 대본으로 엮고, 독립적인 내용 검토를 거쳐 다듬습니다.

[스킬 목록](../../README.ko.md#skills) · [English](podcast-writer.md)

<a id="install"></a>

## 설치

```text
Use $skill-installer to install skills/podcast-writer from https://github.com/smturtle2/codex-skills.
```

내용 검토에 서브에이전트 도구가 필요합니다. YouTube는 자막을 먼저 사용하며, 음성 전사로 대체할 때는 호환 GPU가 필요합니다.

## 사용 예시

```text
$podcast-writer로 이 자료를 초보자용 10분짜리 1인 팟캐스트 대본으로 만들어줘. 일반 텍스트로 저장해.
```

## 작업 파일

후보 대본·출처 메모·검토 상태는 프로젝트 루트 기준 `.codex-skills/podcast-writer/<run-id>/`에 보관합니다. 사용자가 작업 위치를 지정하면 그 위치를 우선하고, 기존 위치는 옮기지 않고 그 자리에서 재개합니다. 재개에 필요한 데이터는 보존하고 이번 실행에서 만든 폐기 가능한 중간 파일만 정리하며, 최종 `.txt` 대본은 요청한 위치에 저장합니다.

## 결과물

말할 내용만 담긴 `.txt` 대본. 이후 TTS나 직접 녹음에 사용할 수 있습니다.

[에이전트용 지침 보기](../../skills/podcast-writer/SKILL.md)
