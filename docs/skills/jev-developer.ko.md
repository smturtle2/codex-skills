# jev-developer

증거 표현, 유형이 지정된 질문, 답변 의미, 판단 구성에 관한 구체적인 지식을 활용해 Jev 통합을 개발합니다.

[스킬 목록](../../README.ko.md#skills) · [English](jev-developer.md)

<a id="install"></a>

## 설치

```text
Use $skill-installer to install skills/jev-developer from https://github.com/smturtle2/codex-skills.
```

## 사용

구현할 동작, 변경할 통합 또는 조사할 관찰 결과와 함께 `$jev-developer`를 호출합니다. 구현을 요청하기 전까지 설계 논의는 논의로 유지합니다.

이 스킬은 Jev가 읽는 내용, 증거 배치, 질문과 기준의 의미, 답변 해석, 요청 종속성, SDK 통합을 다룹니다. 고정된 애플리케이션 스키마, 워크플로 템플릿, 예시별 임계값이 아니라 도메인과 무관한 관계와 API 구문을 제공합니다.

## 요구 사항

번들 런타임이나 추가 스킬은 필요하지 않습니다. 실시간 추론에는 대상 프로젝트에서 TypeSafe API에 접근할 수 있고 호환되는 클라이언트 또는 HTTP 통합이 필요합니다. 문서와 기존 코드는 모델 호출 없이 검사할 수 있습니다. 버전에 따라 달라지는 세부 사항은 공식 문서와 설치된 바인딩을 기준으로 확인합니다.

## 결과

기존 프로젝트에서 요청한 설계, 구현 또는 진단과 검증 근거 및 해결되지 않은 제한 사항을 제공합니다. 필요한 경우에만 작업 자료를 `.codex-skills/jev-developer/<run-id>/`에 저장하며, 기존 실행은 원래 경로에 남겨 두고 결과물은 요청한 위치에 둡니다.

[에이전트용 지침 보기](../../skills/jev-developer/SKILL.md)
