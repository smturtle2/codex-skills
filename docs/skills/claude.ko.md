# claude

이미 실행 중인 Claude Code 세션을 지속 연결해 서브에이전트로 활용합니다.
지시를 보내고 보고·질문을 독립적으로 받습니다.

[전체 스킬](../../README.ko.md#skills) · [English](claude.md)

## 설치

```text
Use $skill-installer to install skills/claude from https://github.com/smturtle2/codex-skills.
```

## 요구 사항과 준비

같은 운영체제 사용자가 실행한 로컬 Linux Claude Code 세션을 지원합니다.
uv와 Python 3.11 이상을 사용합니다. 호환성 기준은 Claude Code `2.1.299`와
네이티브 peer protocol `1`입니다. 연결과 메시지 교환에는 SDK가 필요하지 않습니다.
선택적인 기록 조회에는 `history` extra로 `claude-agent-sdk==0.2.166`을 사용합니다.

Claude를 별도로 열고, 사용할 inbox가 있는 대상 세션을 실행 상태로 유지합니다.
자동 수신이 필요하면 Claude의 `/config` →
`Messages from your other sessions` → `accept`를 선택합니다. 스킬은 기존
inbox를 발견하고 연결을 관리하며, Claude를 실행하거나 설정을 바꾸지 않습니다.
사용할 수 있는 열린 세션이 없으면 이용할 수 없습니다.

## 사용법

예를 들어 “$claude로 이 프로젝트에 열려 있는 세션에 연결해서 파서 검토를
맡겨줘”라고 요청합니다. 호출하는 Codex가 지시를 정하고 결과를 판단합니다.
스킬은 탐색·전송·수신·연결 종료를 담당합니다.

`SKILL_DIR`을 설치된 스킬의 절대 경로로 설정하고, 호출하는 프로젝트의 루트에서
실행합니다.

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" sessions
```

세션 이름과 작업 폴더로 대상을 식별합니다. 연결 가능한 항목의 정확한
`target.session_id`를 사용해, **표준입력을 쓸 수 있고 실행 상태가 유지되는
호스트 실행 세션**에서 연결을 시작합니다.

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" connect \
  --session "$SESSION_ID" --run-dir "$CONNECTION_DIR"
```

명령은 포그라운드에서 계속 실행됩니다. 호스트 실행 세션의 식별자를 보관하고,
`connected`를 받은 뒤 같은 프로세스의 표준입력에 JSONL 제어 메시지를 씁니다.

```jsonl
{"type":"send","message":"파서를 검토하고 발견한 문제를 보고해."}
{"type":"send","message":"잘못된 입력도 고려해. 파일은 수정하지 마."}
```

후속 지시는 같은 연결로 보냅니다. 선택적인 `uuid`는 연결 안에서 전송 중복을
막기 위한 식별자입니다. 같은 UUID와 원문을 반복하면 저장된 전송 결과를
반환하고 다시 보내지 않습니다. 입력과 응답을 대응시키는 식별자는 아닙니다.

다른 작업을 진행하면서 표준출력의 JSONL 이벤트를 받습니다. `message`에는
선택한 `session_id`, `connection_id`, `seq`, `source: "peer"`, `uuid`, `content`가
있습니다. Claude는 받은 메시지에 포함된 발신자의 회신 주소로 네이티브
`SendMessage`를 사용해 보고·질문을 보냅니다. Claude가 자기 세션에 남긴 일반
답변은 연결로 수신하지 않습니다. 내용은 응답 태그·입출력 대응·업무 완료 판정
없이 전달합니다. `sent`, `error`, `closed`는 전송·연결 상태를 알립니다.
`closed` 뒤에도 최종 정리 오류가 올 수 있으므로 헬퍼 프로세스가 끝날 때까지
수집하고 최종 종료 코드를 확인합니다.

`delivery_status`는 검증된 네이티브 보류·거부·드롭 등의 전송 알림을 전달합니다.
`orig_msg_id`가 있으면 전송 건을 가리키며, Claude 답변을 입력에 대응시키지
않습니다. `delivered`는 보류된 메시지가 Claude에 전달되었다는 뜻이며, 읽음이나
업무 완료를 뜻하지 않습니다. 모든 수락된 메시지에 알림이 오는 것은 아닙니다.
`sent` 성공이나 알림 부재로 수신 수락을 판단하지 않으며, 자동 재시도하지 않습니다.
이 알림은 Claude의 메시지와 같은 회신 inbox로 들어옵니다.

호스트 출력 대기는 60초 미만으로 하고 같은 실행 세션에서 수집을 이어갑니다.
조회 시간 초과, Claude의 턴 종료, `idle`, `waiting`은 연결을 종료하지 않습니다.
표준입력을 유지하기 위해 PTY가 필요하다면 사용합니다. 헬퍼는 터미널 에코와
canonical 입력 길이 제한을 해제합니다.

지시에 적은 경로는 대상 컴퓨터와 작업 폴더를 기준으로 합니다. 메시지는 파일을
첨부하거나 호출하는 Codex의 대화 맥락을 이전하지 않습니다.

## 선택적인 기록 조회

필요할 때 선택한 열린 세션의 최근 대화를 별도로 확인합니다.

```sh
uv run --project "$SKILL_DIR" --extra history \
  "$SKILL_DIR/scripts/claude.py" history --session "$SESSION_ID" --limit 10
```

`--limit`은 양의 정수이며 기본값은 `10`입니다. 명령은 조회 전후에 실행 중인
대상을 검증합니다. `type: "history"`, `session_id`, `cwd`, `limit`, `messages`,
`truncated`가 있는 JSON 객체 하나를 반환합니다. 각 메시지는 `type`(`user` 또는
`assistant`), `uuid`, `content`를 가집니다. 비어 있지 않은 사용자·어시스턴트의
표시 텍스트 중 최근 지정 개수를 시간순으로 반환하며, 원문을 보존하고 thinking과
도구 블록은 제외합니다. `truncated`는 개수 제한으로 앞선 표시 메시지가 생략되었는지
나타냅니다.

이 명령은 지속 연결을 열거나 요구하지 않습니다. 결과를 연결 이벤트에 섞지
않으며, 조회 실패도 활성 연결에 영향을 주지 않습니다. 기록을 주기적으로 읽거나
Claude가 조용하다는 이유나 전송 알림이 없다는 이유로 자동 조회하지 않습니다.
닫힌 세션을 대신 사용할 수 없습니다.

## 연결 수명과 기록

다음 제어 메시지로 연결을 종료합니다.

```jsonl
{"type":"disconnect"}
```

명시적 종료, 표준입력 EOF, `SIGINT`/`SIGTERM`/`SIGHUP`, 정확히 연결한 대상의
소멸·변경은 헬퍼를 종료하고 자신의 수신 inbox를 정리합니다. 헬퍼는 Claude
자체를 종료하지 않습니다. 선택한 세션 ID·프로세스·작업 폴더·inbox에 연결됩니다.
`/clear`나 `/new`로 새 세션을 시작하면 기존 연결은 종료됩니다. Claude를 종료하거나
재시작해도 기존 연결은 끝나며, 새 프로세스가 같은 세션 ID를 재개해도 마찬가지입니다.
다시 연결하려면 열린 대상을 명시적으로 선택해 새 연결을 시작합니다. 다른 대상으로
바꾸거나 닫힌 대상의 기록을 계속 읽지 않습니다. 연결이 필요한 동안에는 호스트의
실제 입력 채널이 열려 있어야 합니다.

최초 종료 사유는 보존합니다. 종료 코드 `0`은 호출자·소유 채널의 정상 종료,
`3`은 대상 소멸·변경 또는 지원하지 않는 대상·환경입니다. 헬퍼 실행·기록·정리
실패는 종료나 대상 소실 이후에도 우선하여 `1`로 알립니다. 예상 밖 메인 루프
예외는 `internal_error`로 보고하며, 저장소나 출력이 불가능하면 오류 보고도
최선의 범위에서 수행합니다.

연결마다 새 폴더를 사용하며, 기본 위치는
`.codex-skills/claude/<고유 ID>/`입니다. `connection.json`, `events.jsonl`,
`outbox.json`을 로컬 관측 기록으로 보존합니다. 기존 폴더로 연결을 다시 시작하거나
메시지를 재전송할 수 없습니다. 이전 요청 폴더는 그대로 두며, 기존의
`send`/`status`/`read`/`wait` 명령 API는 제거합니다. 실행 기록을 버전 관리할
의도가 없다면 Git에서 `/.codex-skills/`를 무시합니다.

소켓 쓰기 성공은 네이티브 입력 수신 확인이 아닙니다. 헬퍼는 불확실한 전송을
자동 재시도하거나, 수신 설정을 바꾸거나, Claude의 도구를 강제로 중단하지 않습니다.
선택적인 SDK는 명시적으로 요청한 일회성 기록 조회에만 사용하며, 추론 클라이언트를
실행하지 않습니다. Claude의 터미널 화면은 읽지 않습니다.

에이전트 지침은 [SKILL.md](../../skills/claude/SKILL.md), 메시지 형식·이벤트
의미·대상 식별·호환성의 상세 내용은
[inbox 계약](../../skills/claude/references/inbox-contract.md)을 참조하세요.
