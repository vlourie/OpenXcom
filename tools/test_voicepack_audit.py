"""CPU regression checks for voice audit selection (no TTS model imports)."""
import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parent/'sfx'))
import audit_voicepack as A


class AuditTest(unittest.TestCase):
    def test_spoken_numbers(self):
        for text, heard in [('Батарея: сто процентов.', 'Батарея 100%.'),
                            ('Battery: one hundred percent.', 'Battery 100%.'),
                            ('Восемьсот первый. Ещё работает.', '801. Ещё работает.')]:
            self.assertEqual(A.normalized(text), A.normalized(heard))

    def test_wrong_words_are_not_accepted(self):
        self.assertLess(A.text_score(dict(text='Write him off.', heard='Right he move.', close=.545)), .75)

    def test_signal_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = A.SRC
            try:
                A.SRC = Path(tmp)
                tone = .2*np.sin(2*np.pi*220*np.arange(24000)/24000)
                for name, data in [('ok',tone),('silent',tone*0),('clipped',np.ones(24000))]:
                    sf.write(A.SRC/f'{name}.wav',data,24000)
                self.assertEqual(A.signal('ok.wav')[1]['problems'], [])
                self.assertIn('silent',A.signal('silent.wav')[1]['problems'])
                self.assertIn('clipping',A.signal('clipped.wav')[1]['problems'])
                self.assertTrue(A.signal('missing.wav')[1]['problems'])
                self.assertTrue(A.signal('../outside.wav')[1]['problems'])
            finally:
                A.SRC = old


if __name__ == '__main__':
    unittest.main()
