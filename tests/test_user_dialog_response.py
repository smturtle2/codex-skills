from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/user-dialog/scripts'))
from dialog_response import format_response
from dialog_spec import compile_request
from dialog_spec import parse_json
from dialog_spec import validate_dependencies
from dialog_values import FieldError, active_fields, editable_values, initial_value, matches, normalize_values, option_selected, validate_values, walk
from dialog_state import read_state, save_state


def emphasized(message):
    encoded = message['text'].encode('utf-8')
    return [encoded[e['byteRange']['start']:e['byteRange']['end']].decode('utf-8')
            for e in message['text_elements']]


class UserDialogResponseTests(unittest.TestCase):
    def form(self):
        return compile_request({'title': 'Form', 'body': {'type': 'column', 'children': [
            {'type': 'input', 'id': 'number', 'label': 'Number', 'format': 'number', 'value': 7, 'required': True},
            {'type': 'input', 'id': 'date', 'label': 'Date', 'format': 'date'},
            {'type': 'input', 'id': 'notes', 'label': 'Notes', 'multiline': True},
            {'type': 'input', 'id': 'details', 'label': 'Details', 'required': True,
             'visible_when': {'ref': 'number', 'equals': 0}},
        ]}}, Path.cwd())

    def test_editable_drafts_preserve_invalid_numbers_dates_and_legacy_defaults(self):
        spec = self.form()
        defaults = {node['id']: initial_value(node) for node in walk(spec['body']) if node['type'] == 'input'}
        self.assertEqual(defaults['number'], '7')
        self.assertEqual(validate_values(spec, defaults).values['number'], 7)
        self.assertEqual(editable_values(spec, {'number': 12.5}), {'number': '12.5'})
        self.assertEqual(editable_values(spec, {'number': float('nan')}), {'number': 'nan'})
        for text in ['-', '.', '1e', 'nan', 'NaN', 'inf', '-Infinity', '1e309']:
            with self.subTest(text=text):
                draft = {'number': text, 'date': '2026-09-', 'notes': '  **원문**\n끝\n'}
                normalized = normalize_values(spec, draft)
                self.assertEqual(set(normalized.errors), {'number', 'date'})
                with self.assertRaises(FieldError):
                    validate_values(spec, normalized)
                with tempfile.TemporaryDirectory() as temp:
                    save_state(Path(temp), {'version': 3, 'draft': draft})
                    self.assertEqual(read_state(Path(temp))['draft'], draft)
        draft = {'number': '9007199254740993', 'date': '2024-02-29', 'notes': '  **원문**\n끝\n'}
        normalized = validate_values(spec, draft)
        self.assertEqual(normalized.values['number'], 9007199254740993)
        self.assertEqual(normalized.values['date'], '2024-02-29')
        self.assertIn('\n' + draft['notes'] + '\n', format_response(spec, normalized)['text'])
        for invalid in ['20260201', '2026-W01-1', '2026-02-29']:
            self.assertIn('date', normalize_values(spec, {**draft, 'date': invalid}).errors)

    def test_conditions_propagate_invalid_references_through_negation(self):
        spec = self.form()
        invalid = normalize_values(spec, {'number': 'nan'})
        for condition in [
            {'ref': 'number'}, {'not': {'ref': 'number'}},
            {'not': {'ref': 'number', 'equals': 0}},
            {'not': {'all': [{'ref': 'number', 'equals': 0}]}},
            {'not': {'any': [{'ref': 'number', 'empty': True}]}},
        ]:
            self.assertFalse(matches(condition, invalid), condition)
        valid = normalize_values(spec, {'number': '0', 'details': 'Required when zero'})
        self.assertFalse(matches({'ref': 'number'}, valid))
        self.assertTrue(matches({'not': {'ref': 'number'}}, valid))
        self.assertIn('details', [node['id'] for node, _ in active_fields(spec, valid)])
        self.assertNotIn('details', [node['id'] for node, _ in active_fields(spec, invalid)])
        bounded = compile_request({'title': 'Bounded', 'body': {'type': 'input', 'id': 'number',
                                  'label': 'Number', 'format': 'number', 'min': 0, 'max': 10}}, Path.cwd())
        outside = normalize_values(bounded, {'number': '11'})
        self.assertIn('outside allowed range', outside.errors['number'])
        self.assertFalse(matches({'not': {'ref': 'number', 'equals': 0}}, outside))
        with self.assertRaisesRegex(ValueError, 'Invalid JSON number'):
            parse_json('{"value": 1e309}')

    def test_choice_membership_and_original_asset_base_share_the_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'asset.txt').write_text('Asset')
            spec = compile_request({'title': 'Choice', 'body': {'type': 'column', 'children': [
                {'type': 'choice', 'id': 'choice', 'label': 'Choice', 'multiple': True, 'options': [
                    {'value': 'a', 'label': 'A', 'content': [{'type': 'input', 'id': 'a', 'label': 'A notes'}]},
                    {'value': 'b', 'label': 'B', 'content': [{'type': 'input', 'id': 'b', 'label': 'B notes'}]},
                ]},
                {'type': 'input', 'id': 'file', 'label': 'File', 'format': 'file', 'value': 'asset.txt'},
                {'type': 'input', 'id': 'present', 'label': 'Present', 'visible_when': {'ref': 'file'}},
            ]}}, root)
            draft = {'choice': ['a'], 'a': 'Kept', 'b': 'Omitted', 'file': 'asset.txt', 'present': 'Present'}
            normalized = validate_values(spec, draft, base=root)
            self.assertTrue(option_selected(normalized, 'choice', 'a'))
            self.assertFalse(option_selected(normalized, 'choice', 'b'))
            self.assertEqual(normalized.values['file'], str(root / 'asset.txt'))
            with patch('pathlib.Path.cwd', return_value=root / 'nested'):
                message = format_response(spec, normalized)
            self.assertIn('Present', message['text'])
            self.assertNotIn('Omitted', message['text'])

    def test_conditional_controllers_cannot_hide_themselves_or_form_cycles(self):
        number = {'type': 'input', 'id': 'n', 'label': 'Count', 'format': 'number', 'required': True, 'value': 1}
        direct = {'title': 'Count', 'body': {'type': 'group',
                  'enabled_when': {'not': {'ref': 'n', 'equals': 0}}, 'children': [number]}}
        nested = {'title': 'Count', 'body': {'type': 'group', 'visible_when': {'not': {'all': [
                  {'any': [{'ref': 'n', 'equals': 0}]}]}}, 'children': [{'type': 'choice', 'id': 'choice',
                  'label': 'Choice', 'options': [{'value': 'a', 'label': 'A', 'content': [number]}]}]}}
        self_condition = {'title': 'Count', 'body': {**number, 'visible_when': {'ref': 'n'}}}
        for request in [direct, nested, self_condition]:
            with self.subTest(request=request), self.assertRaisesRegex(ValueError, 'own field or descendant'):
                compile_request(request, Path.cwd())
        cyclic = {'title': 'Cycle', 'body': {'type': 'column', 'children': [
            {'type': 'input', 'id': 'a', 'label': 'A', 'enabled_when': {'ref': 'b'}},
            {'type': 'input', 'id': 'b', 'label': 'B', 'visible_when': {'not': {'ref': 'a'}}},
        ]}}
        with self.assertRaisesRegex(ValueError, 'Cyclic field conditions'):
            compile_request(cyclic, Path.cwd())
        option_cycle = {'title': 'Cycle', 'body': {'type': 'column', 'children': [
            {'type': 'choice', 'id': 'choice', 'label': 'Choice', 'enabled_when': {'ref': 'gate'},
             'options': [{'value': 'a', 'label': 'A', 'content': [number]}]},
            {'type': 'input', 'id': 'gate', 'label': 'Gate', 'visible_when': {'ref': 'n'}},
        ]}}
        with self.assertRaisesRegex(ValueError, 'Cyclic field conditions'):
            compile_request(option_cycle, Path.cwd())
        valid = {'title': 'Count', 'body': {'type': 'column', 'children': [number,
                 {'type': 'group', 'enabled_when': {'not': {'ref': 'n', 'equals': 0}}, 'children': [
                     {'type': 'input', 'id': 'details', 'label': 'Details', 'required': True}]}]}}
        spec = compile_request(valid, Path.cwd())
        invalid = normalize_values(spec, {'n': '-'})
        self.assertEqual([node['id'] for node, _ in active_fields(spec, invalid)], ['n'])
        with self.assertRaisesRegex(FieldError, 'invalid number'):
            format_response(spec, invalid, 'Send')
        # Legacy stored request shapes follow the same policy without touching
        # their numeric draft or already formatted submitted message.
        with self.assertRaisesRegex(ValueError, 'own field or descendant'):
            validate_dependencies(direct)

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
