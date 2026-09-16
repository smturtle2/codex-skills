# epub-translator

EPUB을 번역해 용어와 장 사이의 맥락이 이어지는 새 판본을 만듭니다.

[스킬 목록](../../README.ko.md#skills) · [English](epub-translator.md)

<a id="install"></a>

## 설치

```text
Use $skill-installer to install skills/epub-translator from https://github.com/smturtle2/codex-skills.
```

래스터 이미지 속 글자도 번역하려면 `image-creator`를 함께 설치하세요.

## 사용 예시

```text
$epub-translator로 book.epub을 한국어로 번역해줘. 인명과 용어를 책 전체에서 일관되게 유지해.
```

## 작업 파일

위치를 지정하지 않았다면 지속적인 번역 상태를 프로젝트 루트 기준 `.codex-skills/epub-translator/<run-id>/`에 보관합니다. 사용자가 작업 위치를 지정하면 그 위치를 우선하고, 기존의 오래된 위치는 옮기지 않고 그 자리에서 재개합니다. 재개에 필요한 데이터는 보존하고 이번 실행에서 만든 폐기 가능한 중간 파일만 정리하며, 최종 EPUB은 요청한 위치에 저장합니다.

## 결과물

번역된 `.epub`, 번역 작업 파일, 검증 요약. 읽기 순서·링크·이미지 위치를 기준으로 책을 다시 구성합니다.

[에이전트용 지침 보기](../../skills/epub-translator/SKILL.md)
