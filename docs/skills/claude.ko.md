# claude

이미 실행 중인 Claude Code 세션의 inbox에 업무를 전달하고, 해당 세션의 응답을 읽어 Codex의 서브에이전트로 활용합니다.

[전체 스킬](../../README.ko.md#skills) · [English](claude.md)

## 설치

```text
Use $skill-installer to install skills/claude from https://github.com/smturtle2/codex-skills.
```

## 요구 사항과 준비

같은 운영체제 사용자가 실행한 로컬 Linux Claude Code 세션을 지원합니다.
uv와 Python 3.11 이상을 사용하며, 대화 기록 조회 의존성은
`claude-agent-sdk==0.2.166`으로 고정합니다. 초기 호환성 기준은 Claude Code
`2.1.299`와 네이티브 peer protocol `1`입니다.

Claude Code를 별도로 열고 대상 세션을 실행 상태로 유지합니다. 자동 수신이
필요하면 Claude의 `/config` → `Messages from your other sessions` → `accept`를
선택합니다. 스킬은 기존 inbox를 발견해 사용하며, Claude 실행·설정 변경·종료된
세션 재생성을 하지 않습니다. 세션이 열려 있어도 사용할 inbox가 없으면 연결할
수 없습니다.

## 사용법

예를 들어 “$claude를 사용해 이 프로젝트에 열려 있는 세션에 파서 검토를 맡기고
응답을 읽어줘”라고 요청할 수 있습니다. 호출하는 Codex가 업무와 지시를 정하고
결과를 판단합니다. 스킬은 연결·전송·관측을 담당합니다.

`SKILL_DIR`을 설치된 스킬의 절대 경로로 설정하고, 호출하는 프로젝트의 루트에서
실행합니다.

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" sessions
```

세션 이름과 작업 폴더로 대상을 식별한 뒤 연결 가능한 항목의 정확한
`target.session_id`를 사용합니다. 업무를 UTF-8 파일에 작성하고 고유한 실행
폴더를 정합니다.

```sh
SESSION_ID="<조회한 세션 ID>"
RUN_DIR=".codex-skills/claude/<고유 ID>"

uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" send \
  --session "$SESSION_ID" --message-file request.txt \
  --expect-reply --run-dir "$RUN_DIR"

uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" wait \
  "$RUN_DIR" --timeout 30
```

`--expect-reply`는 업무 원문을 보존하면서 기술적인 응답 식별자를 추가합니다.
Claude에게 해당 세션의 일반 답변을
`<codex-reply request-id="UUID">...</codex-reply>`로 감싸도록 요청합니다. 공유
대화의 다른 입출력과 답변을 구별하기 위한 형식이며, 업무 형식이나 성공 여부를
정하지 않습니다.

| 명령 | 용도 |
| --- | --- |
| `sessions` | 실행 중인 후보와 연결 가능 여부 조회 |
| `send --session ID --message-file PATH` | 메시지 하나를 저장하고 전송; `--expect-reply`와 `--run-dir` 선택 가능 |
| `status RUN_DIR` | 대상 가용성과 저장된 관측 갱신 |
| `read RUN_DIR` | 기다리지 않고 새 응답 조회 |
| `wait RUN_DIR --timeout N` | N초의 반복 조회 기한을 지정하며 N은 0–60 |

대기는 대응 응답을 찾거나, 대응 관계가 모호하거나, 세션이 입력을 기다리는
상태면 일찍 끝납니다. `--expect-reply`를 쓰지 않았다면 새로 관측한 답변도
대기를 끝냅니다. 대기가 일찍 끝났다는 사실로 업무 완료를 판정하지 않습니다.
기한에 도달했더라도 이미 진행 중인 세션 조회나 기록 읽기는 그 후에 끝날 수 있습니다.

후속 지시는 같은 실행 중인 세션 ID에 새 메시지와 실행 폴더로 전송합니다.
관측 명령은 원래 실행 폴더를 재사용합니다. 업무에 적은 경로는 대상 세션의
컴퓨터와 작업 폴더를 기준으로 해석됩니다. 메시지는 파일을 첨부하거나 Codex의
대화 맥락을 이전하지 않습니다.

## 결과와 복구

런타임은 세션 가용성, 전송 관측, 입력 UUID 관측, 응답 대응 관계를 따로
보고합니다. 소켓 쓰기에는 네이티브 메시지 ACK가 없습니다. 쓰기 성공은 도착
확인이 아니며, 대응 응답도 업무 완료 판정이 아닙니다. 응답은 SDK 기록 API로
읽으며 SDK 추론 실행이나 터미널 화면 읽기를 사용하지 않습니다.

대상에 접근할 때마다 정확한 세션·프로세스 시작 정보·inbox를 다시 확인하며,
소켓 자체의 식별 정보와 실제 수신 프로세스의 PID·사용자 ID도 검사합니다.
대상이 닫히거나 바뀌면 `session_unavailable`을 반환하고, 보관된 대화 기록이나
같은 이름의 다른 세션으로 대체하지 않습니다. 응답 식별자 누락·모호한 대응
관계·`history_gap`은 명시적인 관측으로 남습니다. 시간 초과는 대기만 끝내며
Claude가 수행 중인 업무를 중단하지 않습니다.

새로 관측하거나 수정된 답변은 `responses`에 나오며, 저장된 요청에는 누적
관측을 보존합니다. `matched_response`는 각 답변의 현재 내용을 기준으로 다시
판정하므로, 충돌하는 답변이나 수정으로 기존 대응 관계가 무효가 될 수 있습니다.

쓰기가 시작됐을 가능성이 생긴 뒤에는 저장된 요청을 자동으로 다시 보내지
않습니다. 같은 실행 폴더로 `send`를 반복하면 기존 요청을 관측하기만 합니다.
복구에는 `status`, `read`, `wait`를 사용합니다. 수신 설정 `hold`나 `refuse`로
입력이 나타나지 않을 수 있으며, 스킬은 설정을 바꾸지 않습니다. inbox는
Claude의 실행 중인 도구를 강제로 중단할 수 없습니다.

유효한 요청 기록을 읽은 뒤 전송이나 관측 중에 발생한 오류에는 `run_dir`,
`request_id`, 최신 관측 상태를 포함합니다. 최초 `send`가 실패했더라도 그 경로를
보존해 복구에 사용합니다.

## 작업 파일

사용자가 다른 위치를 정하지 않으면 프로젝트 루트 기준
`.codex-skills/claude/<고유 ID>/`를 사용합니다. `--run-dir`을 생략하면 고유한
기본 폴더를 만듭니다. 기존 요청은 저장한 경로에서 관측과 복구를 계속합니다.
미확인 실행은 보존하고, 이번 작업에서 만든 폐기 가능한 중간 파일만 정리합니다.
Git 프로젝트에서는 실행 기록을 버전 관리할 의도가 없는 한 `/.codex-skills/`를
무시 목록에 둡니다.

자세한 지침은 [SKILL.md](../../skills/claude/SKILL.md)를 참조하세요. 네이티브
메시지 형식, 공개·비공개 계약 구분과 오류 처리는
[inbox 계약](../../skills/claude/references/inbox-contract.md)에 설명합니다.
