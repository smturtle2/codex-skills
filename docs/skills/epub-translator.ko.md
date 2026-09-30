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

`ingest`는 비어 있지 않은 작업 폴더를 거부합니다. 기존 작업은 `status`로 재개합니다. `valid`, `text_complete`, `build_ready`는 각각 저장된 행의 유효성, 텍스트 번역 완료, 출판 준비 상태를 나타냅니다. 남은 작업은 `errors`와 `build_blockers`로 확인하며, 상태 명령이 성공했다는 사실만으로 완료를 판단하지 않습니다.

## 번역과 재개

새 작업은 흐름 스키마 3과 청크·번역 스키마 4를 사용합니다. 본문 항목은 문단이나 읽기 단위를 유지하고, 짝을 이루는 마커와 단일 마커가 강조·링크·이미지·기타 보존 콘텐츠를 담습니다. 에이전트는 마커 문법과 중첩을 보존하며 주변 텍스트를 번역합니다. 판본 스키마 2에는 `target_language`, `language_tag`, `page_progression_direction`, `text_direction`을 명시합니다.

기존 흐름 v2·청크 v3 작업은 ID와 완료된 번역 행을 보존합니다. 헬퍼는 각 행이 원본 문서의 정확한 위치에 속하는지 확인합니다. 추출에서 빠진 원문이 있으면 명시적인 `recover`로 기존 번역을 교체하지 않고 누락 항목을 추가합니다. 복구를 반복해도 기존 결과를 덮어쓰지 않으며, 추가된 항목을 번역한 뒤 빌드합니다.

[데이터 형식과 복구](../../skills/epub-translator/references/translation-data.md) · [이미지 작업](../../skills/epub-translator/references/image-jobs.md)

## 결과물

번역된 `.epub`, 재개 가능한 작업 파일, `build-report.json`을 제공합니다. 가로쓰기 본문과 새 탐색 문서를 만들고, 읽기 순서와 보조 스파인 항목을 보존하며, 정규화한 아카이브 경로와 인코딩한 리소스 URI를 사용합니다. 편집한 래스터 이미지는 반환된 바이트와 실제 MIME을 유지하고, 아카이브 확장자는 원본 확장자로 남을 수 있습니다.

SVG·수식·오디오·비디오 등 래스터 이미지 편집 대상이 아닌 미디어는 그대로 보존하고 보고하며, 헬퍼가 내부 텍스트를 번역하지는 않습니다. 헬퍼는 완성된 ZIP의 패키지 참조 관계와 선택한 리소스 바이트를 확인한 뒤 출력 파일을 원자적으로 교체합니다. `validate`는 최종 파일과 현재 작업 상태를 함께 검사하므로 번역·판본 설정·이미지를 바꿨다면 다시 빌드해야 합니다. 기계적 검증은 번역 품질을 보장하지 않습니다.

[에이전트용 지침 보기](../../skills/epub-translator/SKILL.md)
