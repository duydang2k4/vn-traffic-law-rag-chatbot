"""Regression checks against the reviewed local editions."""
import unittest

from scripts.pipeline.consolidate_documents import RULES, checked_input, consolidate


class ConsolidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {}
        for name, rules in RULES.items():
            base = checked_input(rules['base_document'])
            amendment = checked_input(name)
            cls.results[int(name.split('_')[2])] = (base, amendment, consolidate(base, amendment))

    def test_every_amending_body_block_accounted_for(self):
        for number, coverage, headings in [
                (236, range(15, 163), {17, 26, 53, 75, 96, 104, 147, 152, 158}),
                (238, range(17, 206), {17, 22, 35, 36, 52, 59, 65, 66, 77, 84, 97, 180, 188})]:
            base, amendment, result = self.results[number]
            covered = set(headings)
            for action in result['actions']:
                covered.add(action['instruction_position'])
            sources = [b['source'] for b in result['blocks']]
            locations = [(s['document_id'], s['position']) for s in sources]
            self.assertEqual(len(locations), len(set(locations)))
            covered.update(pos for name, pos in locations if name == amendment['document_id'])
            self.assertFalse(set(coverage) - covered)
            self.assertEqual([b['position'] for b in result['blocks']], list(range(1, len(sources)+1)))

    def test_151_repeal_insertions_and_annexes(self):
        base, amend, result = self.results[236]
        texts = [b['text'].strip() for b in result['blocks']]
        headings = [s.split('.')[0] for s in texts if s.startswith('Điều ')]
        self.assertNotIn('Điều 18', headings)
        self.assertEqual(headings[headings.index('Điều 25'):][:3], ['Điều 25', 'Điều 25a', 'Điều 26'])
        self.assertEqual(headings[headings.index('Điều 33'):][:3], ['Điều 33', 'Điều 33a', 'Điều 34'])
        external = [a for a in result['actions'] if a['status'] == 'external_document']
        self.assertEqual([a['instruction_position'] for a in external], [157])
        annex = result['blocks'][texts.index('Phụ lục I'):]
        source = amend['blocks'][179:]
        self.assertEqual([(b['text'], b.get('rows')) for b in annex],
                         [(b['text'], b.get('rows')) for b in source])

    def test_168_target_boundaries_and_phrase_edits(self):
        base, amend, result = self.results[238]
        blocks = result['blocks']
        by_origin = {(b['source']['document_id'], b['source']['position']): i for i, b in enumerate(blocks)}
        index = lambda pos: by_origin[(base['document_id'], pos)]
        self.assertTrue(blocks[index(97)-1]['text'].startswith('1a.'))
        self.assertEqual(blocks[index(1288)]['text'], base['blocks'][1287]['text'])
        self.assertEqual(blocks[index(1288)+1]['source']['position'], 184)
        self.assertEqual(index(1290), index(1288)+2)
        self.assertIn('k1)', blocks[index(1107)+1]['text'])
        self.assertNotIn('giấy chứng nhận kiểm định', blocks[index(802)]['text'].lower())
        h = blocks[index(1205)]
        self.assertIn('Điều 21 (điểm b khoản 3, điểm c khoản 5), Điều 29', h['text'])
        self.assertIn('điểm n khoản 7; khoản 9a', h['text'])
        self.assertIn('2029', blocks[index(1361)+2]['text'])
        self.assertEqual([b['source']['position'] for b in result['implementation_provisions']], list(range(210,216)))

    def test_changed_input_requires_review(self):
        base, amendment, _ = self.results[236]
        with self.assertRaisesRegex(ValueError, 'version changed'):
            consolidate(dict(base, sha256='different'), amendment)


if __name__ == '__main__':
    unittest.main()

