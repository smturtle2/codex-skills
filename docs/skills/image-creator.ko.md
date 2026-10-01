# image-creator

래스터 이미지를 생성·편집해 프로젝트에 저장합니다. 요청하면 처음부터 투명 배경 PNG로 생성합니다.

[스킬 목록](../../README.ko.md#skills) · [English](image-creator.md)

<a id="install"></a>

## 설치

```text
Use $skill-installer to install skills/image-creator from https://github.com/smturtle2/codex-skills.
```

내장 이미지 생성 도구가 필요합니다.

일반 프롬프트에는 요청하지 않은 입자·점무늬·반복 미세 질감을 억제하는 지시를 넣고, 의도적인 재질 표현은 보존합니다. 명시한 질감과 확정 프롬프트를 우선하며, 편집 범위 밖의 원본 질감은 유지합니다.

그림체 모방을 요청하면 적합한 시각 참조를 사용하고, 가져올 표현 특징을 프롬프트에 명시합니다. 일반적인 편집이나 독창적인 이미지 생성만으로 추가 스타일 자료를 찾지는 않습니다.

## 사용 예시

```text
$image-creator로 청록색 목도리를 두른 작은 주황 여우 마스코트를 투명 배경으로 만들어 assets/fox.png에 저장해줘.
```

## 결과물

저장된 이미지, 실제 생성 프롬프트, 확인된 파일 형식·크기·요청한 투명도.

[에이전트용 지침 보기](../../skills/image-creator/SKILL.md)
