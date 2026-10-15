# claude

이미 열려 있는 로컬 Claude Code 세션과 메시지를 주고받으며 작업 위임·질문·협의에 활용합니다. 필요할 때 세션 기록을 별도로 조회합니다.

[전체 스킬](../../README.ko.md#skills) · [English](claude.md)

## 설치

```text
Use $skill-installer to install skills/claude from https://github.com/smturtle2/codex-skills.
```

## 요구 사항과 준비

uv, Python 3.11 이상과 같은 운영체제 사용자가 실행한 로컬 Linux Claude Code 세션이 필요합니다. Claude를 별도로 열고, 사용할 inbox가 있는 대상 세션을 실행 상태로 유지합니다. 자동 수신이 필요하면 Claude의 `/config` → `Messages from your other sessions` → `accept`를 선택합니다.

스킬은 기존 inbox를 발견하고 연결을 관리합니다. Claude를 실행하거나 설정을 바꾸지 않습니다. 사용할 수 있는 열린 세션이 없으면 이용할 수 없습니다. 지원 버전과 프로토콜은 [네이티브 호환성](../../skills/claude/references/inbox-contract.md#native-compatibility)을 참조하세요. 선택적인 기록 조회에만 `history` extra로 제공하는 SDK를 사용합니다.

## 사용법

필요하면 세션 이름과 작업 폴더로 대상을 지정해 자연스럽게 요청합니다.

```text
$claude로 이 프로젝트에 열려 있는 세션에 이 변경의 검토를 맡겨줘.
$claude로 해당 세션에서 합의한 API 규칙을 물어봐.
$claude로 열린 세션의 최근 대화 10개를 확인해줘.
```

검토를 맡기는 것은 Claude를 서브에이전트로 활용하는 예입니다. 같은 연결로 질문하거나 협의할 수도 있습니다. 호출자가 보낼 내용과 받은 메시지의 해석·설명 방식을 정하고, 헬퍼는 메시지 본문을 원문대로 전달합니다. 필요한 맥락과 경로를 메시지에 포함하세요. 메시지는 파일을 첨부하거나 호출자의 대화 맥락을 이전하지 않으며, 경로는 대상 컴퓨터와 작업 폴더를 기준으로 합니다.

### 다대다 메시지 교환

한 연결에서 여러 지시·질문·보고를 독립적으로 주고받는 예입니다.

| 방향 | 메시지 |
| --- | --- |
| Codex → Claude | 파서의 입력 검증 문제를 검토해. 파일은 수정하지 마. |
| Codex → Claude | 이전 입력 형식도 검토에 포함해. |
| Claude → Codex | 현재 파서가 빈 입력을 0으로 처리하는 문제를 발견했어. |
| Claude → Codex | 의도한 계약에서 빈 입력을 허용해? |
| Codex → Claude | 빈 입력은 잘못된 입력이야. 이전 형식 경로도 `src/legacy_parser.py`에서 변경됐어. |
| Claude → Codex | 두 진입점 모두 살펴봤어. |
| Claude → Codex | 이전 형식 파서는 음수의 마이너스 부호도 누락해. |
| Codex → Claude | 지원하는 숫자 범위를 넘는 값의 처리도 확인해. |
| Claude → Codex | 두 경로 모두 지원 범위를 넘는 값은 이미 거부하고 있어. |
| Claude → Codex | 검토 결과는 두 가지야. 빈 입력이 0이 되고, 이전 형식의 음수는 부호가 사라져. |

호출자는 다른 작업을 진행하면서 같은 연결로 후속 메시지를 보낼 수 있습니다. Claude도 입력과 독립적으로 여러 발견 사항·진행 상황·질문을 보낼 수 있습니다.

## 수신하는 내용

Claude는 헬퍼의 회신 inbox로 네이티브 `SendMessage`를 사용해 메시지를 보냅니다. 연결은 이 메시지를 수신하며, Claude가 자기 대화에 남긴 모든 일반 답변을 수집하지 않습니다. 전송·연결 상태 이벤트도 받습니다. 전송 상태가 요청한 작업의 완료를 뜻하지 않으며, 불확실한 전송은 자동 재시도하지 않습니다.

기록 조회는 최근 사용자·어시스턴트 텍스트를 한 번 읽는 별도 기능입니다. 선택적으로 사용하며 지속 연결이 필요하지 않고, 조회 실패도 활성 연결에 영향을 주지 않습니다. Claude가 조용하다는 이유로 자동 조회하지 않습니다. 명령·개수 제한·출력은 [기록 조회](../../skills/claude/references/inbox-contract.md#history-inspection)를 참조하세요.

## 연결 수명과 기록

연결을 끊으면 헬퍼를 종료하고 회신 inbox를 정리하며, Claude는 계속 실행됩니다. 소유자의 입력 채널이 닫히거나, 선택한 세션에서 `/clear`·`/new`를 실행하거나, Claude를 종료·재시작해도 연결은 끝납니다. 다시 연결하려면 열린 대상을 명시적으로 선택해 새 연결을 시작합니다. 자세한 내용은 [연결 수명](../../skills/claude/references/inbox-contract.md#target-and-connection-lifetime)을 참조하세요.

연결마다 로컬 기록을 새 폴더에 남깁니다. 기본 위치는 호출하는 프로젝트 루트의 `.codex-skills/claude/<고유 ID>/`입니다. 메시지와 전송 결과를 확인할 수 있으며, 이 기록으로 연결을 재시작하거나 메시지를 자동 재전송하지 않습니다. 기록을 버전 관리할 의도가 없다면 Git에서 `/.codex-skills/`를 무시합니다. 자세한 내용은 [기록과 복구](../../skills/claude/references/inbox-contract.md#records-and-recovery)를 참조하세요.

연결 절차는 [에이전트 지침](../../skills/claude/SKILL.md), 메시지의 상세 계약은 [제어와 이벤트](../../skills/claude/references/inbox-contract.md#controls-and-events) 및 [전송과 전달](../../skills/claude/references/inbox-contract.md#transmission-and-delivery)을 참조하세요.
