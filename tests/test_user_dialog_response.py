from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/user-dialog/scripts'))
from dialog_response import format_response
from dialog_spec import compile_request
from dialog_state import read_state, save_state


def emphasized(message):
    encoded = message['text'].encode('utf-8')
    return [encoded[e['byteRange']['start']:e['byteRange']['end']].decode('utf-8')
            for e in message['text_elements']]


class UserDialogResponseTests(unittest.TestCase):
    def test_composed_answers_have_automatic_emphasis_and_verbatim_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            attachment = root / '보고서 [원본].txt'
            attachment.write_text('Document')
            spec = compile_request({
                'title': '원래 제목', 'message': {'title': '검토 🧑🏽‍💻', 'icon': '💬'},
                'body': {'type': 'column', 'children': [
                    {'type': 'input', 'id': 'notes', 'label': '의견', 'response_label': '의견_[원문]', 'multiline': True},
                    {'type': 'choice', 'id': 'choice', 'label': '선택', 'options': [
                        {'value': 'a', 'label': 'A_*', 'content': [
                            {'type': 'input', 'id': 'selected', 'label': '추가 의견'}]},
                        {'value': 'b', 'label': 'B', 'content': [
                            {'type': 'input', 'id': 'inactive', 'label': '미선택'}]},
                    ]},
                    {'type': 'input', 'id': 'flag', 'label': '동의', 'format': 'boolean', 'false_label': '아니요'},
                    {'type': 'input', 'id': 'file', 'label': '첨부', 'format': 'file'},
                    {'type': 'input', 'id': 'hidden', 'label': '숨김', 'visible_when': {'ref': 'flag'}},
                    {'type': 'input', 'id': 'empty', 'label': '빈 항목'},
                ]},
            }, root)
            answer = '의견_[원문]\n**사용자가 쓴 Markdown**\n🧑🏽‍💻 e\u0301\n'
            values = {'notes': answer, 'choice': 'a', 'selected': '선택된 답변', 'inactive': '제외됨',
                      'flag': False, 'file': str(attachment), 'hidden': '숨긴 답변', 'empty': ''}
            message = format_response(spec, values, '확인_[제출]')
            self.assertEqual(emphasized(message), ['[💬 Popup response · 검토 🧑🏽‍💻]', '의견_[원문]',
                                                   '선택', '추가 의견', '동의', '첨부', '→ 확인_[제출]'])
            self.assertIn('\n' + answer + '\n', message['text'])
            self.assertIn('\nA_*\n', message['text'])
            self.assertIn('\n아니요\n', message['text'])
            self.assertIn(f'\n{attachment.name}\n{attachment}\n', message['text'])
            for excluded in ['제외됨', '숨긴 답변', '미선택', '빈 항목', '\\_', '](<']:
                self.assertNotIn(excluded, message['text'])
            ranges = [e['byteRange'] for e in message['text_elements']]
            self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(ranges, ranges[1:])))
            state = {'version': 3, 'message': message}
            save_state(root, state)
            self.assertEqual(read_state(root)['message'], message)

    def test_button_only_submission_does_not_validate_or_include_fields(self):
        spec = {'title': 'Review', 'body': {'type': 'input', 'id': 'required', 'label': 'Required', 'required': True}}
        message = format_response(spec, {}, '진행', include_values=False)
        self.assertEqual(message['text'], '[💬 Popup response · Review]\n\n→ 진행\n')
        self.assertEqual(emphasized(message), ['[💬 Popup response · Review]', '→ 진행'])

    def test_unsupported_state_and_removed_node_alias_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = json.dumps({'version': 2, 'message': '**Old message**'})
            (root / 'state.json').write_text(original)
            with self.assertRaisesRegex(ValueError, 'Unsupported dialog state'):
                read_state(root)
            self.assertEqual((root / 'state.json').read_text(), original)
            with self.assertRaisesRegex(ValueError, 'Unknown node type'):
                compile_request({'title': 'Old request', 'body': {'type': 'text', 'text': 'Body'}}, root)


if __name__ == '__main__':
    unittest.main()
