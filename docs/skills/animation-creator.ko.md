# animation-creator

동작을 의미 있는 자세 변화로 나누고, 같은 캐릭터 기준 이미지를 사용해 프레임을 생성합니다.

[스킬 목록](../../README.ko.md#skills) · [English](animation-creator.md)

<a id="install"></a>

## 설치

```text
Use $skill-installer to install skills/image-creator and skills/animation-creator from https://github.com/smturtle2/codex-skills.
```

`image-creator`도 설치하세요. 로컬 보조 스크립트는 `uv`와 rembg로 프레임을 처리합니다.

## 사용 예시

아래 요청에 캐릭터 이미지를 함께 제공합니다. 새 캐릭터를 설명해 기준 이미지부터 생성할 수도 있습니다.

```text
$animation-creator로 이 여우가 손을 흔든 뒤 기본 자세로 돌아오는 루프 WebP를 만들어줘.
```

## 작업 파일

작업 또는 재개 파일이 필요하면 프로젝트 루트 기준 `.codex-skills/animation-creator/<run-id>/`를 사용합니다. 사용자가 작업 위치를 지정하면 그 위치를 우선하고, 기존의 오래된 위치는 옮기거나 삭제하지 않고 그 자리에서 재개합니다. 재개에 필요한 데이터는 보존하고, 이번 실행에서 만든 폐기 가능한 중간 파일만 정리하며, 최종 결과물은 사용자가 요청한 위치에 둡니다.

## 결과물

애니메이션 WebP와 기준 이미지, 프레임 시트, 개별 프레임, 콘택트 시트, 검증 기록.

[에이전트용 지침 보기](../../skills/animation-creator/SKILL.md)
