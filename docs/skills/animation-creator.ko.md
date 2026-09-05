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

## 결과물

애니메이션 WebP와 기준 이미지, 프레임 시트, 개별 프레임, 콘택트 시트, 검증 기록.

[에이전트용 지침 보기](../../skills/animation-creator/SKILL.md)
